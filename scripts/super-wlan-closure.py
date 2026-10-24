import hashlib
import heapq
import importlib.util
import pathlib
import re
import struct
import sys

HERE = pathlib.Path(__file__).parent
SECTOR = 512
GEOMETRY_OFFSET = 4096
GEOMETRY_BACKUP_OFFSET = 8192
METADATA_OFFSET = 12288
HEADER_SIZE = 256
LP_MAGIC = 0x414C5030
GEOMETRY_MAGIC = 0x616C4467
TABLES_SIZE = 1104
TABLES_SHA256 = "6450425f59afbd39ef89d337757eff697cb0f6e9df21a20a785eba6fbd49a251"
SUPER_SIZE = 9663676416
METADATA_SLOTS = 3
LOGICAL_BLOCK_SIZE = 4096
PARTITION_COUNT = 14
EXTENT_COUNT = 7
GROUP_COUNT = 3
BLOCKDEV_COUNT = 1
SLOT_A_EXTENTS = 7
VENDOR_DLKM = "vendor_dlkm_a"
VENDOR = "vendor_a"
SYSTEM_DLKM = "system_dlkm_a"
VENDOR_DLKM_OFFSET = 6947864576
VENDOR_DLKM_BYTES = 32669696
VENDOR_OFFSET = 5678039040
VENDOR_BYTES = 1269284864
SYSTEM_DLKM_OFFSET = 4797235200
SYSTEM_DLKM_BYTES = 11804672
FIRST_EXTENT_OFFSET = 1048576
GEOMETRY_PAGE_SHA256 = "a797e50acc7aed7027d6de98620698281edbe05974b2b81f58504a608a410bf8"
METADATA_PAGE_SHA256 = "a70e6c7a22115732c69f43b52284c7d4838a8ba0a03ca39158c69adef1143e95"
ERAFS_PAGE_SHA256 = {
    VENDOR_DLKM: "76e2d1c59b70b3c6d914fcd65d5e1d8ee8dfb320ccee1cacd30a652e479edc66",
    VENDOR: "5f728e99ec4375e552d51228cfe78087f9109388871a93925e92274307e984d5",
    SYSTEM_DLKM: "e26c9d5abd6e8c60dc0475e4fc732970a5b379b5274fd48cf7320a563143e3ce",
}
EROFS_MAGIC = b"\xe2\xe1\xf5\xe0"
SUPER_MSG = "super image is not the measured slot-A logical-partition geometry"
CLOSURE_MSG = "WLAN closure differs from the measured stock dependency order"
RFKILL_MSG = "rfkill.ko is not the measured system_dlkm provider"
METADATA_NAMES = ("modules.dep", "modules.load", "modules.softdep", "modules.blocklist")
TARGETS = ("qcom_q6v5_pas.ko", "qca_cld3_qca6750.ko", "icnss2.ko",
           "cnss_plat_ipc_qmi_svc.ko", "qrtr-smd.ko")
CLOSURE_SIZE = 20
NEW_SIZE = 14
OLD_SIZE = 6
CLOSURE_SHA256 = "c426856643f9443fcf97c3ea0a70331514448facc33527285e02093dcde3af73"
WLAN_ORDER = (
    "qmi_helpers.ko", "qcom_ramdump.ko", "qcom_pil_info.ko", "qcom_glink.ko",
    "qcom_glink_smem.ko", "qcom_smd.ko", "rproc_qcom_common.ko", "pdr_interface.ko",
    "qcom_sysmon.ko", "qcom_q6v5.ko", "qcom_q6v5_pas.ko", "cfg80211.ko",
    "qrtr-smd.ko", "cnss_plat_ipc_qmi_svc.ko", "wlan_firmware_service.ko",
    "cnss_nl.ko", "cnss_prealloc.ko", "icnss2.ko", "cnss_utils.ko",
    "qca_cld3_qca6750.ko",
)
RFKILL = "rfkill.ko"
RFKILL_SIZE = 63817
RFKILL_SHA256 = "773ddddb360d8de4212da9a327124e97f5b8fe94626a82e44fdcfb689adabb47"
RFKILL_PATH = "lib/modules/6.1.84-android14-11-gf4b0d69fdf34-ab12786779/kernel/net/rfkill/rfkill.ko"
LOOP_MAX_PART = 7
BY_NAME = {"super": "sda6", "modem_a": "sde6"}
BY_NAME_MSG = "the measured by-name table does not place super on sda6 and modem_a on sde6"


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


modules = load("vendor-module-closure.py", "vendor_module_closure")
require = modules.require
sha256 = modules.sha256


def geometry(image, size=SUPER_SIZE):
    require(size == SUPER_SIZE and len(image) >= METADATA_OFFSET + HEADER_SIZE + TABLES_SIZE,
            SUPER_MSG)
    for slot in range(METADATA_SLOTS * 2):
        page = image[METADATA_OFFSET + slot * 65536:
                     METADATA_OFFSET + slot * 65536 + LOGICAL_BLOCK_SIZE]
        require(len(page) == LOGICAL_BLOCK_SIZE and
                sha256(page) == METADATA_PAGE_SHA256, SUPER_MSG)
    for slot in range(2):
        page = image[GEOMETRY_OFFSET + slot * LOGICAL_BLOCK_SIZE:
                     GEOMETRY_OFFSET + (slot + 1) * LOGICAL_BLOCK_SIZE]
        require(sha256(page) == GEOMETRY_PAGE_SHA256, SUPER_MSG)

    def check_geometry(offset):
        record = image[offset:offset + 52]
        magic, size = struct.unpack_from("<II", record)
        require(magic == GEOMETRY_MAGIC and size == 52, SUPER_MSG)
        digest = hashlib.sha256(record[:8] + b"\0" * 32 + record[40:size]).digest()
        require(digest == record[8:40], SUPER_MSG)
        maximum, slots, block = struct.unpack_from("<III", record, 40)
        require((maximum, slots, block) == (65536, METADATA_SLOTS, LOGICAL_BLOCK_SIZE), SUPER_MSG)

    check_geometry(GEOMETRY_OFFSET)
    check_geometry(GEOMETRY_BACKUP_OFFSET)
    header = image[METADATA_OFFSET:METADATA_OFFSET + HEADER_SIZE]
    magic, major, minor, header_size = struct.unpack_from("<IHHI", header)
    require(magic == LP_MAGIC and (major, minor, header_size) == (10, 2, HEADER_SIZE), SUPER_MSG)
    tables_size, = struct.unpack_from("<I", header, 44)
    require(tables_size == TABLES_SIZE, SUPER_MSG)
    header_digest = hashlib.sha256(header[:12] + b"\0" * 32 + header[44:HEADER_SIZE]).digest()
    require(header_digest == header[12:44], SUPER_MSG)
    tables = image[METADATA_OFFSET + HEADER_SIZE:METADATA_OFFSET + HEADER_SIZE + TABLES_SIZE]
    require(sha256(tables) == TABLES_SHA256, SUPER_MSG)
    descriptors = [struct.unpack_from("<III", header, 80 + index * 12) for index in range(4)]
    counts = (PARTITION_COUNT, EXTENT_COUNT, GROUP_COUNT, BLOCKDEV_COUNT)
    require(all(item[1] == count for item, count in zip(descriptors, counts)), SUPER_MSG)
    partitions = {}
    for index in range(descriptors[0][1]):
        start = descriptors[0][0] + index * descriptors[0][2]
        record = tables[start:start + descriptors[0][2]]
        name = record[:36].split(b"\0", 1)[0].decode()
        first, count = struct.unpack_from("<II", record, 40)
        partitions[name] = (first, count)
    extents = []
    for index in range(descriptors[1][1]):
        start = descriptors[1][0] + index * descriptors[1][2]
        sectors, target_type, target_data, target_source = struct.unpack_from("<QIQI", tables, start)
        require(target_type == 0 and target_source == 0, SUPER_MSG)
        extents.append((target_data * SECTOR, sectors * SECTOR))
    expected = {
        VENDOR_DLKM: (VENDOR_DLKM_OFFSET, VENDOR_DLKM_BYTES),
        VENDOR: (VENDOR_OFFSET, VENDOR_BYTES),
        SYSTEM_DLKM: (SYSTEM_DLKM_OFFSET, SYSTEM_DLKM_BYTES),
    }
    for name, value in expected.items():
        first, count = partitions[name]
        require(count == 1 and extents[first] == value, SUPER_MSG)
    require(all(partitions[f"{name}_b"][1] == 0 for name in
                ("odm", "product", "system", "system_dlkm", "system_ext", "vendor", "vendor_dlkm")),
            SUPER_MSG)
    require(len([name for name in partitions if partitions[name][1]]) == SLOT_A_EXTENTS, SUPER_MSG)
    require(min(offset for offset, _ in extents) == FIRST_EXTENT_OFFSET, SUPER_MSG)
    return expected


def module_text(files, name):
    return files[name].decode()


def dependencies(files):
    modules_present = {name for name in files if name.endswith(".ko")}
    deps = {}
    for line in module_text(files, "modules.dep").splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        key = key.rsplit("/", 1)[-1]
        require(key in modules_present and key not in deps, CLOSURE_MSG)
        deps[key] = [item.rsplit("/", 1)[-1] for item in value.split()]
    require(set(deps) == modules_present, CLOSURE_MSG)
    for key, items in deps.items():
        require(all(item in modules_present and item != key for item in items), CLOSURE_MSG)
    return deps


def load_order(files):
    listed = [line.strip() for line in module_text(files, "modules.load").splitlines() if line.strip()]
    return {name: index for index, name in enumerate(listed)}


def compute_closure(files, old_order):
    deps = dependencies(files)
    priority = load_order(files)
    require(all(target in deps and target in priority for target in TARGETS), CLOSURE_MSG)
    closure = set()
    pending = list(TARGETS)
    while pending:
        item = pending.pop()
        if item in closure:
            continue
        closure.add(item)
        pending.extend(dependency for dependency in deps[item] if dependency not in closure)
    edges = {item: set() for item in closure}
    incoming = {item: 0 for item in closure}

    def link(first, second):
        if first != second and second not in edges[first]:
            edges[first].add(second)
            incoming[second] += 1

    for item in closure:
        for dependency in deps[item]:
            link(dependency, item)
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
    require(len(order) == len(closure) == CLOSURE_SIZE, CLOSURE_MSG)
    position = {item: index for index, item in enumerate(order)}
    for item in order:
        require(all(position[dependency] < position[item] for dependency in deps[item]), CLOSURE_MSG)
    old = set(old_order)
    new = [item for item in order if item not in old]
    already = [item for item in order if item in old]
    require(len(new) == NEW_SIZE and len(already) == OLD_SIZE, CLOSURE_MSG)
    require(tuple(order) == WLAN_ORDER, CLOSURE_MSG)
    require(sha256("\n".join(order).encode()) == CLOSURE_SHA256, CLOSURE_MSG)
    require(all(item in files and files[item][:4] == b"\x7fELF" for item in order), CLOSURE_MSG)
    blocklist = module_text(files, "modules.blocklist")
    require(not any(re.search(rf"\b{item[:-3]}\b", blocklist) for item in order), CLOSURE_MSG)
    return order, new, already


def verify_mounted(super_path, vendor_dlkm_root, vendor_root, system_dlkm_root, old_order):
    super_path = pathlib.Path(super_path)
    with super_path.open("rb") as handle:
        require(handle.seek(0, 2) == SUPER_SIZE, SUPER_MSG)
        handle.seek(0)
        image = handle.read(METADATA_OFFSET + 5 * 65536 + LOGICAL_BLOCK_SIZE)
        geometry(image)
        for name, offset in ((VENDOR_DLKM, VENDOR_DLKM_OFFSET), (VENDOR, VENDOR_OFFSET),
                             (SYSTEM_DLKM, SYSTEM_DLKM_OFFSET)):
            handle.seek(offset)
            page = handle.read(LOGICAL_BLOCK_SIZE)
            require(sha256(page) == ERAFS_PAGE_SHA256[name] and
                    page[1024:1028] == EROFS_MAGIC, SUPER_MSG)
    vendor_dlkm_root = pathlib.Path(vendor_dlkm_root)
    vendor_root = pathlib.Path(vendor_root)
    system_dlkm_root = pathlib.Path(system_dlkm_root)
    module_dir = vendor_dlkm_root / "lib" / "modules"
    files = {path.name: path.read_bytes() for path in module_dir.iterdir() if path.is_file()}
    for name in METADATA_NAMES:
        require(name in files, CLOSURE_MSG)
    order, new, already = compute_closure(files, old_order)
    sizes = {name: len(files[name]) for name in order}
    require(sum(sizes.values()) == 20464888, CLOSURE_MSG)
    verify_rfkill(system_dlkm_root / RFKILL_PATH)
    link = vendor_root / "lib" / "modules"
    require(link.is_symlink() and link.readlink().as_posix() == "/vendor_dlkm/lib/modules",
            CLOSURE_MSG)
    return order, new, already, sizes


def verify_rfkill(path):
    rfkill = pathlib.Path(path)
    require(rfkill.is_file(), RFKILL_MSG)
    rfkill_bytes = rfkill.read_bytes()
    require(len(rfkill_bytes) == RFKILL_SIZE and rfkill_bytes[:4] == b"\x7fELF" and
            sha256(rfkill_bytes) == RFKILL_SHA256, RFKILL_MSG)
    return rfkill_bytes


def verify_by_name(path):
    text = pathlib.Path(path).read_text()
    found = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 10 and fields[-2] == "->" and fields[-1].startswith("/dev/block/"):
            found[fields[-3]] = fields[-1].rsplit("/", 1)[-1]
    for name, device in BY_NAME.items():
        require(found.get(name) == device, BY_NAME_MSG)
    require("vendor_a" not in found and "system_dlkm_a" not in found, BY_NAME_MSG)
    return found


def old_order_from_list(path):
    text = pathlib.Path(path).read_text()
    match = re.search(r"^VENDOR_MODULES='\n((?:[A-Za-z0-9_.-]+\n)+)'$", text, re.MULTILINE)
    require(match, "old order list is not a VENDOR_MODULES block")
    listed = match.group(1).split()
    require(len(listed) == 127, "old order list is not the 127-module recovery closure")
    return listed


def main():
    args = sys.argv[1:]
    require(len(args) in (1, 2, 6) and
            (len(args) == 1 or
             (len(args) == 2 and args[0] == "--verify-by-name") or
             (len(args) == 6 and args[0] == "--verify-mounted")),
            "usage: super-wlan-closure.py [--verify-mounted SUPER VENDOR_DLKM_ROOT "
            "VENDOR_ROOT SYSTEM_DLKM_ROOT OLD_ORDER] [--verify-by-name BY_NAME] SUPER_IMAGE")
    if args[0] == "--verify-by-name":
        found = verify_by_name(args[1])
        print(f"by-name: super -> {found['super']}, modem_a -> {found['modem_a']}; "
              "vendor_a and system_dlkm_a are not GPT partitions")
        return
    if args[0] == "--verify-mounted":
        old_order = old_order_from_list(args[5])
        order, new, already, sizes = verify_mounted(args[1], args[2], args[3], args[4],
                                                    old_order)
        print(f"WLAN closure: {len(order)} modules, {len(new)} new beyond the recovery "
              f"127, {len(already)} already loaded, {sum(sizes.values())} bytes")
        for index, name in enumerate(order):
            tag = "new" if name in new else "recovery-loaded"
            print(f"  {index + 1:2}. {name:28} {sizes[name]:9} bytes  {tag}")
        print(f"rfkill.ko provider: {RFKILL_PATH} ({RFKILL_SIZE} bytes, system_dlkm, "
              f"SHA-256 {RFKILL_SHA256[:8]})")
        print(f"closure list SHA-256: {CLOSURE_SHA256}")
        return
    with pathlib.Path(args[0]).open("rb") as handle:
        require(handle.seek(0, 2) == SUPER_SIZE, SUPER_MSG)
        handle.seek(0)
        image = handle.read(METADATA_OFFSET + 5 * 65536 + LOGICAL_BLOCK_SIZE)
    geometry(image)
    print(f"super geometry: {PARTITION_COUNT} partitions, {SLOT_A_EXTENTS} slot-A extents, "
          f"tables SHA-256 {TABLES_SHA256[:8]}")
    print(f"{VENDOR_DLKM}: offset {VENDOR_DLKM_OFFSET}, {VENDOR_DLKM_BYTES} bytes, erofs")
    print(f"{VENDOR}: offset {VENDOR_OFFSET}, {VENDOR_BYTES} bytes, erofs")
    print(f"{SYSTEM_DLKM}: offset {SYSTEM_DLKM_OFFSET}, {SYSTEM_DLKM_BYTES} bytes, erofs")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error, UnicodeError, KeyError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
