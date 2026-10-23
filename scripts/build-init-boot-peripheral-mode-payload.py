import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


eud = load("build-init-boot-eud-softdep-payload.py", "eud_builder")
base = eud.base
modules = eud.modules
MEASURED_EUD = "88c93077d5079d4dc81ce723299faab756bf5b52a5af8ebe99c84f68ea9ae0aa"
PRIOR_IMAGES = (*eud.PRIOR_IMAGES, MEASURED_EUD)
INIT_SOURCE = "init"
FROZEN_SOURCE = eud.INIT_SOURCE
MODE_BLOCK = (
    b'GLUE=""\n'
    b"for device in /sys/bus/platform/devices/*; do\n"
    b'\tcase "$device" in\n'
    b'\t*/a600000.ssusb) [ -e "$device" ] && GLUE=$device ;;\n'
    b"\tesac\n"
    b"done\n"
    b'if [ -n "$GLUE" ] && [ -e "$GLUE/driver" ] && '
    b"[ -e /sys/bus/platform/drivers/msm-dwc3/a600000.ssusb ]; then\n"
    b'\tif [ -e "$GLUE/mode" ]; then\n'
    b"\t\tlog 'a600000.ssusb msm-dwc3 mode attribute exists'\n"
    b'\t\tif current=$(/bin/busybox cat "$GLUE/mode" 2>&1); then\n'
    b'\t\t\tlog "a600000.ssusb mode before: $current"\n'
    b"\t\telse\n"
    b'\t\t\tlog "a600000.ssusb mode read failed: $current"\n'
    b"\t\tfi\n"
    b"\t\tif err=$({ printf 'peripheral' >\"$GLUE/mode\"; } 2>&1); then\n"
    b"\t\t\tlog 'a600000.ssusb mode write peripheral: accepted (not a UDC)'\n"
    b"\t\telse\n"
    b'\t\t\tlog "a600000.ssusb mode write peripheral failed: $err"\n'
    b"\t\tfi\n"
    b'\t\tif readback=$(/bin/busybox cat "$GLUE/mode" 2>&1); then\n'
    b'\t\t\tlog "a600000.ssusb mode readback: $readback"\n'
    b"\t\telse\n"
    b'\t\t\tlog "a600000.ssusb mode readback failed: $readback"\n'
    b"\t\tfi\n"
    b"\telse\n"
    b"\t\tlog 'a600000.ssusb msm-dwc3 mode attribute missing; no role write'\n"
    b"\tfi\n"
    b"else\n"
    b"\tlog 'a600000.ssusb msm-dwc3 device not bound or missing; no role write'\n"
    b"fi\n"
    b"\n")
CHILD_CHECK = (
    b'if [ -n "$GLUE" ] && [ -e "$GLUE/a600000.dwc3" ]; then\n'
    b"\tlog 'a600000.dwc3 child exists under a600000.ssusb'\n"
    b'\tif [ -e "$GLUE/a600000.dwc3/driver" ]; then\n'
    b"\t\tlog 'a600000.dwc3 child bound'\n"
    b"\telse\n"
    b"\t\tlog 'a600000.dwc3 child not bound'\n"
    b"\tfi\n"
    b"else\n"
    b"\tlog 'a600000.dwc3 child missing under a600000.ssusb'\n"
    b"fi\n")
OLD_DEFERRED = (
    b"if [ -r /sys/kernel/debug/devices_deferred ]; then\n"
    b"\twhile read -r line; do\n"
    b'\t\tcase "$line" in\n'
    b'\t\ta600000.ssusb*) log "a600000.ssusb deferred: $line" ;;\n'
    b"\t\tesac\n"
    b"\tdone </sys/kernel/debug/devices_deferred\n"
    b"fi\n")
NEW_DEFERRED = (
    b"if [ -r /sys/kernel/debug/devices_deferred ]; then\n"
    b"\tn=0\n"
    b"\twhile IFS= read -r line; do\n"
    b'\t\tcase "$line" in\n'
    b"\t\ta600000.*)\n"
    b'\t\t\tif [ "$n" -lt 64 ]; then\n'
    b'\t\t\t\tlog "a600000 device deferred: $line"\n'
    b"\t\t\t\tn=$((n + 1))\n"
    b"\t\t\tfi ;;\n"
    b"\t\tesac\n"
    b"\tdone </sys/kernel/debug/devices_deferred\n"
    b'\tlog "a600000 deferred lines logged: $n (cap 64)"\n'
    b"fi\n")
DMESG_BLOCK = (
    b"/bin/busybox dmesg 2>&1 | {\n"
    b"\tn=0\n"
    b"\tseen=0\n"
    b"\twhile IFS= read -r line; do\n"
    b'\t\tcase "$line" in\n'
    b"\t\t*'usb-init: module load end'*) seen=1 ;;\n"
    b"\t\t*usb-init:*) ;;\n"
    b"\t\t*msm-dwc3*|*dwc3*|*DWC3*|*phy*|*PHY*|*repeater*|*REPEATER*)\n"
    b'\t\t\tif [ "$seen" -eq 1 ] && [ "$n" -lt 64 ]; then\n'
    b'\t\t\t\tlog "usb dmesg: $line"\n'
    b"\t\t\t\tn=$((n + 1))\n"
    b"\t\t\tfi ;;\n"
    b"\t\tesac\n"
    b"\tdone\n"
    b'\tlog "usb dmesg lines logged: $n (cap 64)"\n'
    b"}\n")
UDC_WAIT = (
    b'UDC=""\n'
    b"i=0\n"
    b'while [ "$i" -lt 40 ]; do\n'
    b"\tfor candidate in /sys/class/udc/*; do\n"
    b'\t\tif [ -e "$candidate" ]; then\n'
    b"\t\t\tUDC=${candidate##*/}\n"
    b"\t\t\tbreak\n"
    b"\t\tfi\n"
    b"\tdone\n"
    b'\t[ -n "$UDC" ] && break\n'
    b"\tsleep 0.25\n"
    b"\ti=$((i + 1))\n"
    b"done\n")
SSUSB_CHECK = (
    b"if [ -e /sys/bus/platform/drivers/msm-dwc3/a600000.ssusb ]; then\n"
    b"\tlog 'a600000.ssusb bound'\n"
    b"else\n"
    b"\tlog 'a600000.ssusb not bound'\n"
    b"fi\n")
ROLE_WRITE = b"\t\tif err=$({ printf 'peripheral' >\"$GLUE/mode\"; } 2>&1); then\n"
MODE_TARGET = b'>"$GLUE/mode"'
MODE_READ_BEFORE = (
    b'\t\tif current=$(/bin/busybox cat "$GLUE/mode" 2>&1); then\n'
    b'\t\t\tlog "a600000.ssusb mode before: $current"\n')
MODE_READ_AFTER = (
    b'\t\tif readback=$(/bin/busybox cat "$GLUE/mode" 2>&1); then\n'
    b'\t\t\tlog "a600000.ssusb mode readback: $readback"\n')
UDC_ANCHOR = b'UDC=""\n'
FROZEN_SHA256 = "8fa9b571b7e957cd64a68ebc5075fa198d8f3c53f5fef9ea065e312310d9bb7b"
MISSING_WRITE_MSG = "init is missing the single peripheral mode write"
WRITE_COUNT_MSG = "init does not contain exactly one peripheral mode write"
WRITE_ORDER_MSG = "the peripheral mode write is not after the module phase"
EUD_BEFORE_MSG = "the peripheral mode write is not after eud.ko and dwc3-msm.ko load"
VALUE_MSG = "the mode write is not exactly the value peripheral"
PATH_MSG = "the mode write uses a hardcoded SoC path instead of the discovered device"
TIMER_MSG = "the self-recovery timer was removed or moved"
LIST_MSG = "init module list is not the verified 127-module order"
WAIT_MSG = "the UDC wait is not the unchanged 40 by 0.25 second loop after the mode write"
READ_MSG = "mode logging is not read-only before and after the single write"
EUD_LOG_MSG = "the read-only EUD and ssusb bound checks are missing or moved"
CHILD_MSG = "the read-only a600000.dwc3 child check is missing or moved"
DEFERRED_MSG = "deferred-probe logging is not the exact bounded read-only replacement"
DMESG_MSG = "the read-only dmesg capture is missing, moved or not read-only"
DELTA_MSG = "init is not frozen #49 plus the exact peripheral-mode delta"
FROZEN_MSG = "frozen #49 init is missing or already contains the peripheral-mode delta"
SOURCE_MSG = "embedded init differs from the committed peripheral-mode source"
KO_MSG = eud.KO_MSG
ENVELOPE_MSG = eud.ENVELOPE_MSG
SHA_MSG = "candidate repeats a previously measured SHA-256"
require = eud.require


def require_frozen(frozen):
    require(frozen.startswith(eud.SHEBANG) and frozen.count(MODE_BLOCK) == 0 and
            frozen.count(ROLE_WRITE) == 0 and frozen.count(CHILD_CHECK) == 0 and
            frozen.count(DMESG_BLOCK) == 0 and frozen.count(OLD_DEFERRED) == 1 and
            frozen.count(NEW_DEFERRED) == 0 and frozen.count(UDC_ANCHOR) == 1 and
            frozen.count(eud.EUD_CHECK) == 1 and frozen.count(SSUSB_CHECK) == 1 and
            frozen.count(UDC_WAIT) == 1, FROZEN_MSG)
    require(modules.sha256(frozen) == FROZEN_SHA256, FROZEN_MSG)
    return frozen


def frozen_init():
    return require_frozen(
        (HERE.parent / "initramfs" / FROZEN_SOURCE).read_bytes())


def expected_init(frozen):
    require(frozen.count(OLD_DEFERRED) == 1 and frozen.count(UDC_ANCHOR) == 1 and
            frozen.count(SSUSB_CHECK) == 1 and frozen.count(eud.EUD_CHECK) == 1, DELTA_MSG)
    result = frozen.replace(UDC_ANCHOR, MODE_BLOCK + UDC_ANCHOR, 1)
    result = result.replace(SSUSB_CHECK, SSUSB_CHECK + CHILD_CHECK, 1)
    return result.replace(OLD_DEFERRED, NEW_DEFERRED + DMESG_BLOCK, 1)


def check_eud_before(init, write):
    start = init.index(eud.LOOP_START)
    end = init.index(b"done\n", start)
    require(init.index(b"eud.ko\n") < init.index(b"dwc3-msm.ko\n") < start and
            start < end < init.index(eud.LOAD_END) < write, EUD_BEFORE_MSG)


def check_mode(init):
    require(b"a600000.ssusb/mode" not in init and b"/sys/devices/" not in init,
            PATH_MSG)
    writes = init.count(MODE_TARGET)
    peripheral = init.count(b"printf 'peripheral'")
    require(writes >= 1 or peripheral >= 1, MISSING_WRITE_MSG)
    require(b"printf 'host'" not in init and b"printf 'none'" not in init and
            b"printf 'otg'" not in init and peripheral == writes, VALUE_MSG)
    require(writes == 1 and init.count(ROLE_WRITE) == 1, WRITE_COUNT_MSG)
    write = init.index(ROLE_WRITE)
    require(write > init.index(eud.INSMOD), EUD_BEFORE_MSG)
    require(write > init.index(eud.LOAD_END), WRITE_ORDER_MSG)
    require(write < init.index(UDC_ANCHOR), WAIT_MSG)
    check_eud_before(init, write)
    require(init.count(MODE_READ_BEFORE) == 1 and init.count(MODE_READ_AFTER) == 1 and
            init.index(MODE_READ_BEFORE) < write < init.index(MODE_READ_AFTER), READ_MSG)
    require(init.count(MODE_BLOCK) == 1 and init.index(MODE_BLOCK) < write, WRITE_COUNT_MSG)
    return write


def check_wait(init, write):
    require(init.count(UDC_WAIT) == 1 and write < init.index(UDC_WAIT), WAIT_MSG)
    require(init.count(b"sleep 0.25\n") == 1 and init.count(b'-lt 40') == 1 and
            40 * 0.25 >= 10, WAIT_MSG)
    require(init.index(UDC_WAIT) < init.index(b'if [ -z "$UDC" ]; then'), WAIT_MSG)


def check_eud_log(init):
    require(eud.EUD_CHECK.endswith(OLD_DEFERRED), EUD_LOG_MSG)
    head = eud.EUD_CHECK[:len(eud.EUD_CHECK) - len(OLD_DEFERRED)]
    log_line = b'log "udc names:${UDC_NAMES:- none}"\n'
    require(init.count(head) == 1 and init.count(log_line) == 1 and
            init.index(log_line) < init.index(head) <
            init.index(b'if [ -z "$UDC" ]; then'), EUD_LOG_MSG)
    require(init.count(b"eud not bound") == 1 and
            init.count(b"a600000.ssusb not bound") == 1, EUD_LOG_MSG)


def check_logs(init):
    require(init.count(CHILD_CHECK) == 1, CHILD_MSG)
    require(init.count(OLD_DEFERRED) == 0 and init.count(NEW_DEFERRED) == 1 and
            init.count(b'a600000 device deferred: $line') == 1, DEFERRED_MSG)
    require(init.count(DMESG_BLOCK) == 1, DMESG_MSG)
    require(init.index(b"a600000.ssusb not bound") < init.index(CHILD_CHECK) <
            init.index(NEW_DEFERRED), CHILD_MSG)
    require(init.index(NEW_DEFERRED) < init.index(DMESG_BLOCK) <
            init.index(b'if [ -z "$UDC" ]; then'), DMESG_MSG)
    require(init.count(b"/bin/busybox dmesg") == 1 and b"dmesg -c" not in init and
            b"dmesg -n" not in init and b"dmesg -C" not in init, DMESG_MSG)


def check_timer(init):
    require(init.count(eud.TIMER) == 1 and
            init.index(eud.TIMER) < init.index(eud.LOAD_BEGIN), TIMER_MSG)
    eud.check_timer(init)


def check_list(init, order):
    eud.check_list(init, order)
    listed = modules.init_list(init.decode())
    require(len(listed) == 127 and listed == order, LIST_MSG)
    require(listed.index(eud.EUD_MODULE) + 1 == listed.index(eud.DWC3_MODULE), LIST_MSG)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    check_list(init, order)
    check_timer(init)
    eud.check_marker(init)
    check_eud_log(init)
    eud.check_bind(init)
    write = check_mode(init)
    check_wait(init, write)
    check_logs(init)
    frozen = frozen_init()
    eud.check_init(frozen, order)
    require(init == expected_init(frozen), DELTA_MSG)
    return write


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order):
    return eud.candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                              init_check=check_init)


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, ENVELOPE_MSG)
    image, digest = eud.vendor.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 10, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER")
    stock, source, boot, vendor_boot, recovery, config, kernel, decompressor, pstore, helper = (
        pathlib.Path(path).read_bytes() for path in paths)
    library = base.lz4()
    vendor_files, recovery_entries = eud.vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, LIST_MSG)
    eud.vendor.check_stock(stock, library)
    init = (HERE.parent / "initramfs" / INIT_SOURCE).read_bytes()
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-peripheral-mode-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; eud.ko immediately before "
          f"dwc3-msm.ko; list SHA-256 {modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print("role write: one peripheral write through discovered $GLUE/mode after module "
          "load and before the 10 s UDC wait")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper {eud.HELPER_SIZE} "
          f"bytes, SHA-256 {eud.HELPER_SHA256[:8]}")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
