import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


rfkill = load("build-init-boot-wlan-rfkill-payload.py", "wlan_rfkill_builder")
old = rfkill.old
base = rfkill.base
eud = rfkill.eud
modules = rfkill.modules
static = rfkill.static
require = rfkill.require
MEASURED_RF_KILL = "9291c369ec78b081c6445b3ee85431fa9a01e2e757a59337cfd165eca741c2f3"
PRIOR_IMAGES = (*rfkill.PRIOR_IMAGES, MEASURED_RF_KILL)
FROZEN_SOURCE = rfkill.FROZEN_SOURCE
FROZEN_SHA256 = rfkill.FROZEN_SHA256
WLAN_BEGIN = rfkill.WLAN_BEGIN
WLAN_END = rfkill.WLAN_END
ANCHOR = rfkill.ANCHOR
DELTA_MSG = "init is not frozen #53 plus corrected wlan-init with one bounded ipci bind gate"
FROZEN_MSG = rfkill.FROZEN_MSG
WLAN_MARKER_MSG = rfkill.WLAN_MARKER_MSG
DEFER_MSG = "the bounded icnss2/WPSS bind gate is missing, duplicated or wrong"
SHA_MSG = rfkill.SHA_MSG
TIMER_MSG = rfkill.TIMER_MSG
LIST_MSG = rfkill.LIST_MSG
KO_MSG = rfkill.KO_MSG
ENVELOPE_MSG = rfkill.ENVELOPE_MSG

INS_MOD = '''\tif err=$(/bin/busybox timeout -k 1 2 /bin/busybox insmod "$KOPATH" 2>&1); then
'''
BIND_GATE = '''\tif [ "$module" = qca_cld3_qca6750.ko ]; then
\t\tbind_wait=0
\t\twhile [ "$bind_wait" -lt 12 ] && [ ! -e /sys/bus/platform/devices/17110040.qcom,wcn6750/driver ]; do
\t\t\tsleep 1
\t\t\tbind_wait=$((bind_wait + 1))
\t\tdone
\t\tif [ -e /sys/bus/platform/devices/9bb00000.remoteproc-wpss/driver ]; then
\t\t\twlog "ipci gate: wpss bound"
\t\telse
\t\t\twlog "ipci gate: wpss unbound"
\t\tfi
\t\tif [ -e /sys/bus/platform/devices/17110040.qcom,wcn6750/driver ]; then
\t\t\twlog "ipci gate: icnss2 bound after $bind_wait s"
\t\telse
\t\t\twlog "ipci gate: icnss2 unbound after $bind_wait s"
\t\tfi
\tfi
'''
WAIT_SECONDS = 12
WLAN_BLOCK = rfkill.WLAN_BLOCK.replace(INS_MOD, BIND_GATE + INS_MOD, 1)
DELTA = WLAN_BEGIN + old.WLAN_MODULES.encode() + WLAN_BLOCK.encode() + WLAN_END


def frozen_init(order):
    return rfkill.frozen_init(order)


def expected_init(frozen):
    require(frozen.count(ANCHOR) == 1 and frozen.count(DELTA) == 0, DELTA_MSG)
    return frozen.replace(ANCHOR, DELTA + ANCHOR, 1)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    gate = BIND_GATE.encode()
    require(init.count(gate) == 1, DEFER_MSG)
    require(init.count(INS_MOD.encode()) == 1 and init.index(gate) < init.index(INS_MOD.encode()),
            DEFER_MSG)
    base_init = init.replace(gate, b"", 1)
    rfkill.check_init(base_init, order)
    frozen = frozen_init(order)
    require(base_init == rfkill.expected_init(frozen), DELTA_MSG)
    require(init.count(DELTA) == 1, DELTA_MSG)
    stripped = init.replace(DELTA, b"", 1)
    static.check_timer(stripped)
    require(stripped.count(static.SSHD) == 1, static.SSHD_MSG)
    static.check_init(stripped, order)
    require(stripped == frozen and init == expected_init(frozen), DELTA_MSG)
    return init.index(WLAN_BEGIN)
def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order):
    return eud.candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                              init_check=check_init)


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, ENVELOPE_MSG)
    image, digest = static.peripheral.assemble(stock, frame)
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
    init = expected_init(frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-ipci-defer-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"wlan-init phase: unchanged corrected mounts and {len(old.WLAN_MODULES_LIST)}-module "
          f"closure; final insmod waits up to {WAIT_SECONDS} s for icnss2 bind and logs "
          "the WPSS and icnss2 platform driver bind states before the single insmod")
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
