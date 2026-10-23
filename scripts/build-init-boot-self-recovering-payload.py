import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


vendor = load("build-init-boot-vendor-modules-payload.py", "vendor_builder")
base = vendor.base
modules = vendor.modules
MEASURED_VENDOR = "cdb9458f515bce3f1059f89cab0d7a78945f20e73f3cb7b34645c15646aab42a"
PRIOR_IMAGES = (*vendor.PRIOR_IMAGES, MEASURED_VENDOR)
SOURCE_SHA256 = "6806922e9e5138df25ee13e5f11d4fad555479830436e283b040b6e666133f96"
HELPER_NAME = "bin/restart2"
HELPER_SHA256 = "fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7"
HELPER_SIZE = 872
TIMER_BUDGET = 150
SHEBANG = b"#!/bin/busybox sh\n"
LOOP_START = b"for module in $VENDOR_MODULES; do\n"
INSMOD = b'\tif err=$(insmod "/lib/modules/$module" 2>&1); then\n'
LOAD_BEGIN = b"log 'module load begin'\n"
LOAD_END = b"log 'module load end'\n"
TIMER = (b"{\n"
         b"\tsleep " + str(TIMER_BUDGET).encode() + b"\n"
         b"\tif [ ! -e /run/keep ]; then\n"
         b"\t\tlog 'self-recovery -> bootloader'\n"
         b"\t\t/bin/restart2 bootloader\n"
         b"\t\tlog 'self-recovery RESTART2 failed; falling back to reboot -f'\n"
         b"\t\treboot -f\n"
         b"\tfi\n"
         b"} &\n")
MARKER = b'\tlog "loading $module"\n'
BIND_CHECK = (b"if [ -n \"$(find /sys/bus/platform/drivers/qcom-reboot-reason "
              b"-mindepth 1 -maxdepth 1 -type l ! -name module 2>/dev/null)\" ]; then\n"
              b"\tlog 'qcom-reboot-reason bound'\n"
              b"else\n"
              b"\tlog 'qcom-reboot-reason not bound'\n"
              b"fi\n")
TIMER_MSG = "init self-recovery timer is missing or not independent of the module loop"
MARKER_MSG = "init loading marker does not precede every insmod"
BIND_MSG = "init has no qcom-reboot-reason bind check after the module phase"
HELPER_MSG = "bin/restart2 is missing, dynamic or not the reproducible arm64 RESTART2 helper"
SOURCE_MSG = "candidate debug cpio changes entries besides init and bin/restart2"
BASELINE_MSG = "init is not the #44 init plus the marker, bind check and timer"
KO_MSG = "candidate debug cpio contains a .ko file"
ENVELOPE_MSG = "script does not fit the stock LZ4 envelope; stop without an image"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def insert_once(data, anchor, insertion):
    require(data.count(anchor) == 1, f"init has no unique insertion point: {anchor!r}")
    return data.replace(anchor, anchor + insertion)


def expected_init(baseline):
    result = insert_once(baseline, b"log 'starting'\n", TIMER)
    result = insert_once(result, LOOP_START, MARKER)
    return insert_once(result, LOAD_END, BIND_CHECK)


def check_timer(init):
    require(init.count(TIMER) == 1, TIMER_MSG)
    start = init.index(TIMER)
    require(start < init.index(LOAD_BEGIN), TIMER_MSG)
    require(LOOP_START not in init[:start] and b"done\n" not in init[start:start + len(TIMER)],
            TIMER_MSG)
    require(init.count(f"\tsleep {TIMER_BUDGET}\n".encode()) == 1 and
            init.count(b"/bin/restart2 bootloader") == 1 and
            init.count(b"\t\treboot -f\n") == 1 and init.count(b"/run/keep") == 1, TIMER_MSG)
    return start


def check_marker(init):
    require(init.count(MARKER) == 1 and init.count(b"insmod ") == 1, MARKER_MSG)
    marker = init.index(MARKER)
    require(init.index(LOOP_START) < marker < init.index(INSMOD) and
            b"done\n" not in init[init.index(LOOP_START):marker], MARKER_MSG)
    order = modules.init_list(init.decode())
    require(len(order) == modules.CLOSURE_SIZE and
            modules.sha256(modules.render_list(order).encode()) == modules.ORDER_SHA256,
            "init module list differs from the verified #44 closure")
    return marker


def check_bind(init):
    require(init.count(BIND_CHECK) == 1 and
            init.index(LOAD_END) < init.index(BIND_CHECK) <
            init.index(b"for candidate in /sys/class/udc/*; do"), BIND_MSG)
    require(init.count(b"qcom-reboot-reason not bound") == 1, BIND_MSG)


def check_helper(helper):
    require(helper is not None and len(helper) == HELPER_SIZE, HELPER_MSG)
    require(helper[:6] == b"\x7fELF\x02\x01", HELPER_MSG)
    require(int.from_bytes(helper[16:18], "little") == 2, HELPER_MSG)
    require(int.from_bytes(helper[18:20], "little") == 183, HELPER_MSG)
    offset = int.from_bytes(helper[32:40], "little")
    size = int.from_bytes(helper[54:56], "little")
    count = int.from_bytes(helper[56:58], "little")
    require(size == 56 and count and offset + size * count <= len(helper), HELPER_MSG)
    types = [int.from_bytes(helper[offset + i * size:offset + i * size + 4], "little")
             for i in range(count)]
    require(1 in types and 2 not in types and 3 not in types, HELPER_MSG)
    require(modules.sha256(helper) == HELPER_SHA256, HELPER_MSG)
    require(modules.sha256((HERE.parent / "initramfs" / "restart2.c").read_bytes()) ==
            SOURCE_SHA256, "RESTART2 helper source SHA changed")


def check_init(init, order):
    require(init.startswith(SHEBANG), BASELINE_MSG)
    check_timer(init)
    check_marker(init)
    check_bind(init)
    baseline = (HERE.parent / "initramfs" / "init-44-vendor-modules").read_bytes()
    require(baseline.startswith(SHEBANG) and baseline.count(TIMER) == 0 and
            baseline.count(MARKER) == 0 and baseline.count(BIND_CHECK) == 0,
            "#44 init unexpectedly already carries the #47 additions")
    modules.verify_init(baseline.decode(), order)
    require(init == expected_init(baseline), BASELINE_MSG)
    require(modules.init_list(init.decode()) == order, "init module list differs from #44")


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order):
    _, entries, trailer = vendor.source_cpio(source)
    check_init(init, order)
    check_helper(helper)
    require(not any(entry["name"] == HELPER_NAME for entry in entries), SOURCE_MSG)
    changed = []
    for entry in entries:
        if entry["name"] == "init":
            entry = {**entry, "data": init}
        changed.append(entry)
        if entry["name"] == "bin/dropbear":
            changed.append({"name": HELPER_NAME,
                            "fields": [0, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 13, 0],
                            "mode": 0o100755, "data": helper})
    require(len(changed) == len(entries) + 1 and
            len([entry for entry in changed if entry["name"] == "init"]) == 1, SOURCE_MSG)
    cpio = modules.encode_newc(changed, trailer)
    unpacked, _ = modules.parse_newc(cpio, "self-recovering debug cpio")
    by_name = {entry["name"]: entry for entry in unpacked}
    require([entry["name"] for entry in unpacked] ==
            [entry["name"] for entry in changed] and
            all(a["data"] == b["data"] and a["mode"] == b["mode"]
                for a, b in zip(unpacked, changed)), SOURCE_MSG)
    differ = [entry["name"] for entry in entries
              if by_name[entry["name"]]["data"] != entry["data"]]
    added = [entry["name"] for entry in unpacked if entry["name"] not in
             {entry["name"] for entry in entries}]
    require(differ == ["init"] and added == [HELPER_NAME] and
            by_name[HELPER_NAME]["data"] == helper and
            by_name[HELPER_NAME]["mode"] & 0o170777 == 0o100755, SOURCE_MSG)
    require(not any(entry["name"].endswith(".ko") for entry in unpacked), KO_MSG)
    modules.prove_vendor_modules(vendor_files, unpacked, recovery_entries)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, ENVELOPE_MSG)
    image, digest = vendor.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES and digest != MEASURED_VENDOR,
            "candidate repeats a previously measured SHA-256")
    return image, digest


def prepare(paths):
    require(len(paths) == 10, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER")
    stock, source, boot, vendor_boot, recovery, config, kernel, decompressor, pstore, helper = (
        pathlib.Path(path).read_bytes() for path in paths)
    library = base.lz4()
    vendor_files, recovery_entries = vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_order(vendor_files)
    vendor.check_stock(stock, library)
    init = (HERE.parent / "initramfs" / "init-47-self-recovering").read_bytes()
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-self-recovering-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; {len(outside)} USB additions; "
          f"list SHA-256 {modules.ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"self-recovery timer: {TIMER_BUDGET} s, independent subshell; helper {HELPER_SIZE} "
          f"bytes, SHA-256 {HELPER_SHA256[:8]}")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
