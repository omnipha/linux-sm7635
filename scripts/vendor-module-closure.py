import ctypes
import hashlib
import heapq
import pathlib
import re
import struct
import sys

PAGE = 4096
VENDOR_SHA256 = "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253"
RECOVERY_SHA256 = "0c6767698ebb069064b450b109cde6a1172b478e30000fe852e7d9bc19dbae9e"
VENDOR_RAMDISK_SIZE = 8821389
VENDOR_CPIO_SIZE = 29905920
VENDOR_BLOCKS = 4
VENDOR_KO_COUNT = 317
VENDOR_BOOTCONFIG_SIZE = 175
RECOVERY_RAMDISK_SIZE = 48350666
LOAD_COUNT = 110
RECOVERY_COUNT = 314
CLOSURE_SIZE = 126
OUTSIDE_LOAD = 16
DWC3_CLOSURE = 34
ORDER_SHA256 = "57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08"
MEASURED_INITRD_KIB = {"stock": 10680, "lz4-debug": 57716}
LZ4_LEGACY_MAGIC = 0x184C2102
LZ4_CHUNK = 8 * 1024 * 1024
USB_ADDITIONS = (
    "phy-generic.ko",
    "phy-msm-ssusb-qmp.ko",
    "phy-msm-snps-eusb2.ko",
    "dwc3-msm.ko",
    "repeater.ko",
    "repeater-qti-pmic-eusb2.ko",
)
MODULE_DIR = "lib/modules"
METADATA = ("modules.dep", "modules.softdep", "modules.load", "modules.load.recovery")
LIST_PATTERN = re.compile(r"^VENDOR_MODULES='\n((?:[A-Za-z0-9_.-]+\n)+)'$", re.MULTILINE)
LOAD_PATTERN = re.compile(
    r"^log 'module load begin'\n"
    r"for module in \$VENDOR_MODULES; do\n"
    r"\tif err=\$\(insmod \"/lib/modules/\$module\" 2>&1\); then\n"
    r"\t\tlog \"module \$module loaded\"\n"
    r"\telse\n"
    r"\t\tlog \"module \$module failed: \$err\"\n"
    r"\tfi\n"
    r"done\n"
    r"log 'module load end'\n$", re.MULTILINE)
NEWC_ALIGN = 4
ARCHIVE_BLOCK = 512


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def lz4_library():
    library = ctypes.CDLL("liblz4.so.1")
    library.LZ4_decompress_safe.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    library.LZ4_decompress_safe.restype = ctypes.c_int
    return library


def unpack_legacy_lz4(frame, library):
    require(len(frame) >= 8 and struct.unpack_from("<I", frame)[0] == LZ4_LEGACY_MAGIC,
            "ramdisk is not an Android LZ4 legacy stream")
    pos = 4
    parts = []
    while pos < len(frame):
        require(pos + 4 <= len(frame), "LZ4 legacy stream is truncated")
        chunk = struct.unpack_from("<I", frame, pos)[0]
        require(chunk != 0, "LZ4 legacy stream has a zero-length block")
        pos += 4
        require(pos + chunk <= len(frame), "LZ4 legacy block runs past the ramdisk")
        output = ctypes.create_string_buffer(LZ4_CHUNK)
        size = library.LZ4_decompress_safe(frame[pos:pos + chunk], output, chunk, LZ4_CHUNK)
        require(size > 0, "LZ4 legacy block does not decode")
        parts.append(output.raw[:size])
        pos += chunk
    return b"".join(parts), len(parts)


def parse_newc(archive, label):
    pos = 0
    entries = []
    while True:
        require(pos + 110 <= len(archive) and archive[pos:pos + 6] == b"070701",
                f"{label} is not a newc archive ending in TRAILER!!!")
        try:
            fields = [int(archive[pos + 6 + 8 * i:pos + 14 + 8 * i], 16) for i in range(13)]
        except ValueError as exc:
            raise ValueError(f"{label} is not a newc archive ending in TRAILER!!!") from exc
        size, name_size = fields[6], fields[11]
        name_end = pos + 110 + name_size
        require(name_size > 0 and name_end <= len(archive) and archive[name_end - 1] == 0,
                f"{label} has a malformed entry name")
        name = archive[pos + 110:name_end - 1].decode()
        data_start = (name_end + 3) // 4 * 4
        data_end = data_start + size
        require(data_end <= len(archive), f"{label} entry runs past the archive")
        entry = {"name": name, "fields": fields, "mode": fields[1],
                 "data": archive[data_start:data_end]}
        if name == "TRAILER!!!":
            end = (data_end + 3) // 4 * 4
            require(not any(archive[end:]), f"{label} has data after TRAILER!!!")
            return entries, entry
        entries.append(entry)
        pos = (data_end + 3) // 4 * 4


def encode_newc(entries, trailer):
    out = bytearray()
    for entry in list(entries) + [trailer]:
        name = entry["name"].encode() + b"\0"
        fields = list(entry["fields"])
        fields[6] = len(entry["data"])
        fields[11] = len(name)
        out += b"070701" + b"".join(f"{value:08X}".encode() for value in fields)
        out += name
        out += bytes(-(110 + len(name)) % NEWC_ALIGN)
        out += entry["data"]
        out += bytes(-len(entry["data"]) % NEWC_ALIGN)
    out += bytes(-len(out) % ARCHIVE_BLOCK)
    return bytes(out)


def vendor_ramdisk_cpio(vendor, library):
    require(sha256(vendor) == VENDOR_SHA256,
            "vendor_boot is not the verified 23725940 slot-A image")
    require(vendor[:8] == b"VNDRBOOT" and struct.unpack_from("<II", vendor, 8) == (4, PAGE),
            "vendor_boot is not header v4 with 4096-byte pages")
    ramdisk_size = struct.unpack_from("<I", vendor, 24)[0]
    header_size, dtb_size = struct.unpack_from("<II", vendor, 2096)
    table_size, table_count, table_entry = struct.unpack_from("<III", vendor, 2112)
    bootconfig_size = struct.unpack_from("<I", vendor, 2124)[0]
    require(ramdisk_size == VENDOR_RAMDISK_SIZE and header_size == 2128 and
            bootconfig_size == VENDOR_BOOTCONFIG_SIZE,
            "vendor_boot ramdisk, header or bootconfig size differs from the verified image")
    require(table_count == 1 and table_entry == 108 and table_size == 108,
            "vendor_boot must carry exactly one 108-byte vendor ramdisk table entry")

    def align(value):
        return (value + PAGE - 1) // PAGE * PAGE

    table_offset = PAGE + align(ramdisk_size) + align(dtb_size)
    entry_size, entry_offset, entry_type = struct.unpack_from("<III", vendor, table_offset)
    require((entry_size, entry_offset, entry_type) == (ramdisk_size, 0, 1),
            "vendor ramdisk table entry is not the single PLATFORM fragment")
    archive, blocks = unpack_legacy_lz4(vendor[PAGE:PAGE + ramdisk_size], library)
    require(blocks == VENDOR_BLOCKS and len(archive) == VENDOR_CPIO_SIZE,
            "vendor ramdisk is not the verified four-block cpio")
    return archive


def recovery_ramdisk_entries(recovery, library):
    require(sha256(recovery) == RECOVERY_SHA256,
            "recovery_a is not the verified 0c676769 slot-A image")
    require(recovery[:8] == b"ANDROID!" and struct.unpack_from("<I", recovery, 40)[0] == 4 and
            struct.unpack_from("<I", recovery, 8)[0] == 0 and
            struct.unpack_from("<I", recovery, 12)[0] == RECOVERY_RAMDISK_SIZE,
            "recovery_a is not header v4 with an empty kernel and the verified ramdisk")
    archive, _ = unpack_legacy_lz4(recovery[PAGE:PAGE + RECOVERY_RAMDISK_SIZE], library)
    entries, _ = parse_newc(archive, "recovery ramdisk cpio")
    return entries


def module_key(name):
    base = name.rsplit("/", 1)[-1]
    if base.endswith(".ko"):
        base = base[:-3]
    return base.replace("-", "_")


def base_name(path):
    return path.rsplit("/", 1)[-1]


def vendor_files(archive):
    entries, _ = parse_newc(archive, "vendor ramdisk cpio")
    names = [entry["name"] for entry in entries]
    require(len(names) == len(set(names)), "vendor ramdisk cpio repeats a path")
    files = {entry["name"]: entry for entry in entries}
    for name in names:
        require(name == name.lstrip("/") and ".." not in name.split("/") and "\0" not in name,
                "vendor ramdisk cpio has a non-canonical path")
    require(not any(name in ("init", "sbin/init") for name in names),
            "vendor ramdisk unexpectedly supplies an init")
    modules = [name for name in names if name.endswith(".ko")]
    require(len(modules) == VENDOR_KO_COUNT, "vendor ramdisk does not carry 317 .ko files")
    for name in modules:
        entry = files[name]
        require(name.startswith(MODULE_DIR + "/") and name.count("/") == 2 and
                entry["mode"] & 0o170000 == 0o100000 and
                entry["data"][:6] == b"\x7fELF\x02\x01" and
                struct.unpack_from("<H", entry["data"], 18)[0] == 183,
                f"vendor module is not an arm64 ELF under {MODULE_DIR}: {name}")
    for name in METADATA:
        require(f"{MODULE_DIR}/{name}" in files, f"vendor ramdisk is missing {name}")
    for directory in ("lib", MODULE_DIR):
        require(directory in files and files[directory]["mode"] & 0o170000 == 0o040000,
                f"vendor ramdisk {directory} is not a directory")
    return files


def read_lists(files):
    def text(name):
        return files[f"{MODULE_DIR}/{name}"]["data"].decode()

    modules = {base_name(name) for name in files if name.endswith(".ko")}
    deps = {}
    for line in text("modules.dep").splitlines():
        if not line.strip():
            continue
        require(":" in line, "modules.dep line has no colon")
        key, value = line.split(":", 1)
        key = base_name(key.strip())
        require(key in modules and key not in deps, "modules.dep key is unknown or repeated")
        deps[key] = [base_name(item) for item in value.split()]
    require(set(deps) == modules, "modules.dep keys differ from the .ko files")
    for key, items in deps.items():
        require(all(item in modules and item != key for item in items),
                f"modules.dep dependency of {key} is not a vendor module")
    softdeps = {}
    for line in text("modules.softdep").splitlines():
        fields = line.split()
        if not fields or fields[0] != "softdep":
            continue
        pre = []
        mode = None
        for token in fields[2:]:
            if token in ("pre:", "post:"):
                mode = token
            elif mode == "pre:":
                pre.append(token)
        softdeps[fields[1]] = [module_key(item) for item in pre]
    load = [base_name(item) for item in text("modules.load").split()]
    recovery = [base_name(item) for item in text("modules.load.recovery").split()]
    require(len(load) == LOAD_COUNT and len(recovery) == RECOVERY_COUNT,
            "modules.load or modules.load.recovery has an unexpected length")
    require(len(set(load)) == len(load) and set(load) <= modules and set(recovery) <= modules,
            "module lists name unknown or repeated modules")
    require(all(item in recovery for item in USB_ADDITIONS) and
            not any(item in load for item in USB_ADDITIONS),
            "USB additions are not exactly the recovery-only modules")
    return modules, deps, softdeps, load, recovery


def compute_order(files):
    modules, deps, softdeps, load, recovery = read_lists(files)
    closure = set(load) | set(USB_ADDITIONS)
    pending = list(closure)
    while pending:
        item = pending.pop()
        for dependency in deps[item]:
            if dependency not in closure:
                closure.add(dependency)
                pending.append(dependency)
    priority = {}
    for index, item in enumerate(load):
        priority[item] = index
    for index, item in enumerate(recovery):
        priority.setdefault(item, len(load) + index)
    for item in sorted(closure):
        priority.setdefault(item, len(load) + len(recovery))
    by_key = {module_key(item): item for item in closure}
    edges = {item: set() for item in closure}
    incoming = {item: 0 for item in closure}

    def link(first, second):
        if first != second and second not in edges[first]:
            edges[first].add(second)
            incoming[second] += 1

    for item in closure:
        for dependency in deps[item]:
            link(dependency, item)
        for soft in softdeps.get(module_key(item), []):
            if soft in by_key:
                link(by_key[soft], item)
    heap = [(priority[item], item) for item in closure if incoming[item] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, item = heapq.heappop(heap)
        order.append(item)
        for follower in sorted(edges[item]):
            incoming[follower] -= 1
            if incoming[follower] == 0:
                heapq.heappush(heap, (priority[follower], follower))
    require(len(order) == len(closure), "module dependency graph has a cycle")
    position = {item: index for index, item in enumerate(order)}
    for item in order:
        require(all(position[dependency] < position[item] for dependency in deps[item]),
                f"load order places {item} before one of its modules.dep dependencies")
    require(set(load) <= set(order) and set(USB_ADDITIONS) <= set(order),
            "closure lost a required module")
    outside = [item for item in order if item not in set(load)]
    require(len(order) == CLOSURE_SIZE and len(outside) == OUTSIDE_LOAD,
            "closure is not 126 modules with 16 outside modules.load")
    require(all(f"{MODULE_DIR}/{item}" in files for item in order),
            "closure names a module the vendor ramdisk does not carry")
    require(len(set(deps["dwc3-msm.ko"]) | {"dwc3-msm.ko"}) == DWC3_CLOSURE,
            "dwc3-msm modules.dep closure changed")
    require(sha256(render_list(order).encode()) == ORDER_SHA256,
            "computed load order differs from the verified closure")
    return order, outside


def render_list(order):
    return "VENDOR_MODULES='\n" + "".join(f"{item}\n" for item in order) + "'"


def init_list(init_text):
    matches = LIST_PATTERN.findall(init_text)
    require(len(matches) == 1, "init must hold exactly one VENDOR_MODULES block")
    return matches[0].split()


def verify_init(init_text, order):
    require(init_list(init_text) == order, "init module list differs from the computed closure")
    require(len(LOAD_PATTERN.findall(init_text)) == 1,
            "init does not insmod and record each module result")
    checks = (
        "mount -t proc proc /proc", "mount -t sysfs sysfs /sys",
        "mount -t devtmpfs devtmpfs /dev", "log 'module load begin'",
        'if err=$(insmod "/lib/modules/$module" 2>&1); then',
        "log 'module load end'",
        "log \"udc names:${UDC_NAMES:- none}\"",
        "log 'no UDC; USB gadget not bound'",
        'log "deferred probe pending: $line"',
        'if err=$({ printf \'%s\' "$UDC" >"$G/UDC"; } 2>&1); then',
        'log "gadget bound to $UDC"',
        'log "gadget bind failed for $UDC: $err"',
        "log 'console ready'", "/bin/dropbear -R -p 172.16.42.2:22",
    )
    require(all(init_text.count(token) == 1 for token in checks),
            "init is missing a required mount, load, UDC, bind or console path")
    require(all(init_text.index(token) < init_text.index("log 'module load begin'")
                for token in checks[:3]), "init loads modules before proc/sys/devtmpfs mounts")
    require(init_text.count("for candidate in /sys/class/udc/*; do") == 2 and
            init_text.index("log 'module load end'") <
            init_text.index("for candidate in /sys/class/udc/*; do"),
            "init waits for the UDC before loading modules")
    require(init_text.count("insmod ") == 1 and "modprobe " not in init_text,
            "init has another module load path outside the closure")


def initrd_kib(*sizes):
    return (sum(sizes) + PAGE - 1) // PAGE * PAGE // 1024


def merged_rootfs(*archives):
    rootfs = {}
    for entries in archives:
        for entry in entries:
            rootfs[entry["name"]] = entry
    return rootfs


def prove_vendor_modules(vendor_files_map, generic_entries, recovery_entries):
    names = set(vendor_files_map)
    tree = {name for name in names if name == "lib" or name.startswith("lib/")}
    require(len(tree) == 2 + VENDOR_KO_COUNT + len(METADATA) + 2,
            "vendor ramdisk lib tree has an unexpected size")
    for label, entries in (("generic", generic_entries), ("recovery", recovery_entries)):
        clash = sorted(entry["name"] for entry in entries
                       if entry["name"] in tree or entry["name"] in names)
        require(not clash, f"{label} ramdisk would mask vendor path {clash[:3]}")
    vendor_entries = list(vendor_files_map.values())
    for order in ((vendor_entries, generic_entries),
                  (generic_entries, vendor_entries),
                  (vendor_entries, generic_entries, recovery_entries),
                  (vendor_entries, recovery_entries, generic_entries),
                  (recovery_entries, vendor_entries, generic_entries)):
        rootfs = merged_rootfs(*order)
        for name in tree:
            survivor = rootfs[name]
            original = vendor_files_map[name]
            require(survivor["data"] == original["data"] and
                    survivor["mode"] == original["mode"],
                    f"initrd concatenation changes vendor path {name}")
    require(len(tree) > 0 and not any(entry["name"].endswith(".ko")
                                      for entry in generic_entries),
            "generic ramdisk carries a .ko file")
    return len(tree)


def check_initrd_model():
    require(initrd_kib(VENDOR_RAMDISK_SIZE, 2113581, VENDOR_BOOTCONFIG_SIZE) ==
            MEASURED_INITRD_KIB["stock"],
            "initrd size model does not reproduce the measured stock Android value")
    require(initrd_kib(VENDOR_RAMDISK_SIZE, 1927750, RECOVERY_RAMDISK_SIZE,
                       VENDOR_BOOTCONFIG_SIZE) == MEASURED_INITRD_KIB["lz4-debug"],
            "initrd size model does not reproduce the measured #42 value")


def main():
    args = sys.argv[1:]
    require(len(args) in (1, 2) and (len(args) == 1 or args[0] == "--list"),
            "usage: vendor-module-closure.py [--list] VENDOR_BOOT")
    vendor = pathlib.Path(args[-1]).read_bytes()
    archive = vendor_ramdisk_cpio(vendor, lz4_library())
    order, outside = compute_order(vendor_files(archive))
    if args[0] == "--list":
        print(render_list(order))
        return
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")
    print("outside modules.load: " + " ".join(outside))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error, KeyError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
