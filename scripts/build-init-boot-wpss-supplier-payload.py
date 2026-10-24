import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


ipci = load("build-init-boot-ipci-defer-payload.py", "ipci_defer_builder")
rfkill = ipci.rfkill
old = ipci.old
base = ipci.base
eud = ipci.eud
modules = ipci.modules
static = ipci.static
require = ipci.require
MEASURED_IPCI = "e5b99b7c04b85aee66a0ac295ee1a94a0d5dd208f8c7b0f4112fc0cd3f78fc5d"
PRIOR_IMAGES = (*ipci.PRIOR_IMAGES, MEASURED_IPCI)
FROZEN_SOURCE = ipci.FROZEN_SOURCE
FROZEN_SHA256 = ipci.FROZEN_SHA256
WLAN_BEGIN = ipci.WLAN_BEGIN
WLAN_END = ipci.WLAN_END
ANCHOR = ipci.ANCHOR
INS_MOD = ipci.INS_MOD
BIND_GATE = ipci.BIND_GATE
WAIT_SECONDS = ipci.WAIT_SECONDS
DELTA_MSG = ("init is not frozen #53 plus corrected wlan-init with one bounded ipci bind gate "
             "carrying one bounded WPSS supplier phase")
FROZEN_MSG = ipci.FROZEN_MSG
WLAN_MARKER_MSG = ipci.WLAN_MARKER_MSG
DEFER_MSG = ipci.DEFER_MSG
SUPPLIER_MSG = ("the single bounded WPSS supplier phase before the WLAN probe is missing, "
                "duplicated, reordered, unbounded or loads an already-present module")
SHA_MSG = ipci.SHA_MSG
TIMER_MSG = ipci.TIMER_MSG
LIST_MSG = ipci.LIST_MSG
KO_MSG = ipci.KO_MSG
ENVELOPE_MSG = ipci.ENVELOPE_MSG

GATE_OPEN = '\tif [ "$module" = qca_cld3_qca6750.ko ]; then\n'
SUPPLIER_LIST = "smp2p.ko pinctrl-spmi-gpio.ko qti-fixed-regulator.ko"
SUPPLIER_MODULES = ("smp2p.ko", "pinctrl-spmi-gpio.ko", "qti-fixed-regulator.ko")
SUPPLIER_COUNT = len(SUPPLIER_MODULES)
SUPPLIER_SHA256 = {
    "smp2p.ko": "80ad17b53885c3a45d39c66bed9410e1213b211af011f37676ba26ac5e02e511",
    "pinctrl-spmi-gpio.ko": "2bdfc52d041a7e5a067ab34658e47e52a99bb6c7b2f2fef7b7fc14ee5478fe00",
    "qti-fixed-regulator.ko": "330395e9ac2baff283f9157e7667953e5dea564a80fddb536f641d3bdfd5cb2e",
}
SUPPLIER_SIZE = {
    "smp2p.ko": 36472,
    "pinctrl-spmi-gpio.ko": 59768,
    "qti-fixed-regulator.ko": 21688,
}
WPSS_DEV = "/sys/bus/platform/devices/9bb00000.remoteproc-wpss/driver"
REGULATOR_DEV = "/sys/bus/platform/devices/soc:pm3001a-s1j/driver"
ICNSS2_DEV = "/sys/bus/platform/devices/17110040.qcom,wcn6750/driver"
SUPPLIER_PHASE = (
    '\t\twlog "supplier phase begin"\n'
    '\t\tfor supplier in smp2p.ko pinctrl-spmi-gpio.ko qti-fixed-regulator.ko; do\n'
    '\t\t\tSUPNAME=${supplier%.ko}\n'
    '\t\t\tSUPNAME=${SUPNAME//-/_}\n'
    '\t\t\tif [ -d "/sys/module/$SUPNAME" ]; then\n'
    '\t\t\t\twlog "supplier $supplier already present"\n'
    '\t\t\t\tcontinue\n'
    '\t\t\tfi\n'
    '\t\t\tSUPPATH=/lib/modules/$supplier\n'
    '\t\t\tif [ ! -r "$SUPPATH" ]; then\n'
    '\t\t\t\twlog "supplier $supplier failed: missing $SUPPATH"\n'
    '\t\t\t\tcontinue\n'
    '\t\t\tfi\n'
    '\t\t\tif err=$(/bin/busybox timeout -k 1 2 /bin/busybox insmod "$SUPPATH" 2>&1); then\n'
    '\t\t\t\twlog "supplier $supplier loaded"\n'
    '\t\t\telse\n'
    '\t\t\t\terr=$(/bin/busybox printf %s "$err" | /bin/busybox head -c 160)\n'
    '\t\t\t\twlog "supplier $supplier failed: $err"\n'
    '\t\t\tfi\n'
    '\t\tdone\n'
    '\t\tif [ -e ' + WPSS_DEV + ' ]; then\n'
    '\t\t\twlog "supplier state: wpss bound"\n'
    '\t\telse\n'
    '\t\t\twlog "supplier state: wpss unbound"\n'
    '\t\tfi\n'
    '\t\tif [ -e ' + REGULATOR_DEV + ' ]; then\n'
    '\t\t\twlog "supplier state: regulator bound"\n'
    '\t\telse\n'
    '\t\t\twlog "supplier state: regulator unbound"\n'
    '\t\tfi\n'
    '\t\tif [ -e ' + ICNSS2_DEV + ' ]; then\n'
    '\t\t\twlog "supplier state: icnss2 bound"\n'
    '\t\telse\n'
    '\t\t\twlog "supplier state: icnss2 unbound"\n'
    '\t\tfi\n'
    '\t\twlog "supplier phase end"\n'
)


def replace_one(text, before, after):
    require(text.count(before) == 1 and text.count(after) == 0, DELTA_MSG)
    return text.replace(before, after, 1)


SUPPLIER_GATE = replace_one(BIND_GATE, GATE_OPEN, GATE_OPEN + SUPPLIER_PHASE)
WLAN_BLOCK = replace_one(ipci.WLAN_BLOCK, BIND_GATE, SUPPLIER_GATE)
DELTA = WLAN_BEGIN + old.WLAN_MODULES.encode() + WLAN_BLOCK.encode() + WLAN_END


def frozen_init(order):
    return ipci.frozen_init(order)


def expected_init(frozen):
    require(frozen.count(ANCHOR) == 1 and frozen.count(DELTA) == 0, DELTA_MSG)
    return frozen.replace(ANCHOR, DELTA + ANCHOR, 1)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    supplier = SUPPLIER_PHASE.encode()
    gate_open = GATE_OPEN.encode()
    require(init.count(supplier) == 1, SUPPLIER_MSG)
    require(init.count(gate_open) == 1, SUPPLIER_MSG)
    require(init.index(gate_open) < init.index(supplier), SUPPLIER_MSG)
    require(init.count(b"bind_wait=0") == 1 and
            init.index(supplier) < init.index(b"bind_wait=0"), SUPPLIER_MSG)
    require(init.count(INS_MOD.encode()) == 1 and
            init.index(supplier) < init.index(INS_MOD.encode()), SUPPLIER_MSG)
    require(init.count(SUPPLIER_LIST.encode()) == 1 and
            init.count(b"/lib/modules/$supplier") == 1 and
            init.count(b'/bin/busybox timeout -k 1 2 /bin/busybox insmod "$SUPPATH"') == 1 and
            init.count(b'/sys/module/$SUPNAME') == 1, SUPPLIER_MSG)
    require(init.index(b"smp2p.ko") < init.index(b"pinctrl-spmi-gpio.ko") <
            init.index(b"qti-fixed-regulator.ko"), SUPPLIER_MSG)
    for state in (b'wlog "supplier state: wpss bound"',
                  b'wlog "supplier state: regulator bound"',
                  b'wlog "supplier state: icnss2 bound"',
                  b'wlog "supplier phase begin"', b'wlog "supplier phase end"'):
        require(init.count(state) == 1, SUPPLIER_MSG)
    for bad in (b"rmmod", b"modprobe", b"remoteproc-mss", b"/sys/class/remoteproc",
                b"wpss_boot", b"remoteproc2"):
        require(bad not in init, SUPPLIER_MSG)
    require(init.count(b"insmod") == 3 and
            init.count(b'insmod "/lib/modules/$module"') == 1 and
            init.count(b'/bin/busybox insmod "$SUPPATH"') == 1 and
            init.count(b'/bin/busybox insmod "$KOPATH"') == 1, SUPPLIER_MSG)
    base_init = init.replace(supplier, b"", 1)
    ipci.check_init(base_init, order)
    frozen = frozen_init(order)
    require(base_init == ipci.expected_init(frozen), DELTA_MSG)
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
    for name in SUPPLIER_MODULES:
        entry = vendor_files.get("lib/modules/" + name)
        require(entry is not None and modules.sha256(entry["data"]) == SUPPLIER_SHA256[name] and
                len(entry["data"]) == SUPPLIER_SIZE[name],
                f"supplier module {name} is not the measured stock vendor_boot provider")
    eud.vendor.check_stock(stock, library)
    init = expected_init(frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-wpss-supplier-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"supplier phase: one bounded insmod of {SUPPLIER_COUNT} stock /lib/modules suppliers "
          f"({', '.join(SUPPLIER_MODULES)}) inside the qca_cld3 gate, before the "
          f"{WAIT_SECONDS} s icnss2 bind wait and the single stock WLAN insmod; logs each load "
          "and the WPSS, regulator and icnss2 platform bind state; no rmmod, no reload, no "
          "modem remoteproc control")
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
