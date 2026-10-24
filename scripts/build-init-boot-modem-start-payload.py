import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


wpss = load("build-init-boot-wpss-supplier-payload.py", "wpss_supplier_builder")
ipci = wpss.ipci
rfkill = ipci.rfkill
old = ipci.old
base = ipci.base
eud = ipci.eud
modules = ipci.modules
static = ipci.static
require = ipci.require
MEASURED_WPSS = "5a61de0e39d4cc8f985d38f0be2e39ce3054cae3b94a5fc64df9617f93e563ed"
PRIOR_IMAGES = (*wpss.PRIOR_IMAGES, MEASURED_WPSS)
FROZEN_SOURCE = ipci.FROZEN_SOURCE
FROZEN_SHA256 = ipci.FROZEN_SHA256
WLAN_BEGIN = ipci.WLAN_BEGIN
WLAN_END = ipci.WLAN_END
ANCHOR = ipci.ANCHOR
INS_MOD = ipci.INS_MOD
BIND_GATE = ipci.BIND_GATE
WAIT_SECONDS = ipci.WAIT_SECONDS
DELTA_MSG = ("init is not frozen #53 plus corrected wlan-init with one bounded ipci bind gate "
             "carrying one bounded WPSS supplier phase and one bounded single modem start")
FROZEN_MSG = ipci.FROZEN_MSG
WLAN_MARKER_MSG = ipci.WLAN_MARKER_MSG
DEFER_MSG = ipci.DEFER_MSG
SUPPLIER_MSG = ("the single bounded WPSS supplier phase before the WLAN probe is missing, "
                "duplicated, reordered, unbounded or loads an already-present module")
MODEM_MSG = ("the single guarded bounded one-time modem remoteproc2 start between the supplier "
             "phase and the WLAN probe is missing, duplicated, unguarded, unbounded, retargeted "
             "or writes any other remoteproc value")
SHA_MSG = ipci.SHA_MSG
TIMER_MSG = ipci.TIMER_MSG
LIST_MSG = ipci.LIST_MSG
KO_MSG = ipci.KO_MSG
ENVELOPE_MSG = ipci.ENVELOPE_MSG

GATE_OPEN = wpss.GATE_OPEN
SUPPLIER_PHASE = wpss.SUPPLIER_PHASE
SUPPLIER_GATE = wpss.SUPPLIER_GATE
MSS_NAME = "/sys/class/remoteproc/remoteproc2/name"
MSS_STATE = "/sys/class/remoteproc/remoteproc2/state"
START_WRITE = "/bin/busybox sh -c 'printf start >" + MSS_STATE + "'"
MODEM_PHASE = (
    '\t\twlog "modem start phase begin"\n'
    '\t\tif [ ! -e /sys/class/remoteproc/remoteproc2 ]; then\n'
    '\t\t\twlog "modem start failed: missing /sys/class/remoteproc/remoteproc2"\n'
    '\t\telif MSTATE=$(/bin/busybox timeout -k 1 2 /bin/busybox cat ' + MSS_STATE + ' 2>/dev/null); then\n'
    '\t\t\tif MNAME=$(/bin/busybox timeout -k 1 2 /bin/busybox cat ' + MSS_NAME + ' 2>/dev/null); then\n'
    '\t\t\t\twlog "modem name: $MNAME"\n'
    '\t\t\telse\n'
    '\t\t\t\twlog "modem name read failed"\n'
    '\t\t\tfi\n'
    '\t\t\twlog "modem state: $MSTATE"\n'
    '\t\t\tif [ "$MSTATE" = "running" ]; then\n'
    '\t\t\t\twlog "modem start skipped: already running"\n'
    '\t\t\telif [ "$MSTATE" = "offline" ]; then\n'
    '\t\t\t\tif err=$(/bin/busybox timeout -k 1 10 ' + START_WRITE + ' 2>&1); then\n'
    '\t\t\t\t\twlog "modem start write accepted"\n'
    '\t\t\t\telse\n'
    '\t\t\t\t\terr=$(/bin/busybox printf %s "$err" | /bin/busybox head -c 160)\n'
    '\t\t\t\t\twlog "modem start write failed: $err"\n'
    '\t\t\t\tfi\n'
    '\t\t\telse\n'
    '\t\t\t\twlog "modem start skipped: state $MSTATE"\n'
    '\t\t\tfi\n'
    '\t\t\tif MSTATE=$(/bin/busybox timeout -k 1 2 /bin/busybox cat ' + MSS_STATE + ' 2>/dev/null); then\n'
    '\t\t\t\twlog "modem state after start: $MSTATE"\n'
    '\t\t\telse\n'
    '\t\t\t\twlog "modem state read failed after start"\n'
    '\t\t\tfi\n'
    '\t\telse\n'
    '\t\t\twlog "modem state read failed before start"\n'
    '\t\tfi\n'
    '\t\twlog "modem start phase end"\n'
)


def replace_one(text, before, after):
    require(text.count(before) == 1 and text.count(after) == 0, DELTA_MSG)
    return text.replace(before, after, 1)


GATE_CLOSE = '\tfi\n'
require(SUPPLIER_GATE.endswith(GATE_CLOSE), DELTA_MSG)
MODSUP_GATE = SUPPLIER_GATE[:-len(GATE_CLOSE)] + MODEM_PHASE + GATE_CLOSE
WLAN_BLOCK = replace_one(ipci.WLAN_BLOCK, BIND_GATE, MODSUP_GATE)
DELTA = WLAN_BEGIN + old.WLAN_MODULES.encode() + WLAN_BLOCK.encode() + WLAN_END


def frozen_init(order):
    return ipci.frozen_init(order)


def expected_init(frozen):
    require(frozen.count(ANCHOR) == 1 and frozen.count(DELTA) == 0, DELTA_MSG)
    return frozen.replace(ANCHOR, DELTA + ANCHOR, 1)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    supplier = SUPPLIER_PHASE.encode()
    modem = MODEM_PHASE.encode()
    insmod = INS_MOD.encode()
    require(init.count(modem) == 1, MODEM_MSG)
    require(init.count(supplier) == 1, SUPPLIER_MSG)
    require(init.count(b"bind_wait=0") == 1, SUPPLIER_MSG)
    require(init.index(supplier) < init.index(b"bind_wait=0") <
            init.index(b'wlog "ipci gate: icnss2 unbound after $bind_wait s"') <
            init.index(modem) < init.index(insmod) and
            init.index(modem) + len(modem) < init.index(insmod), MODEM_MSG)
    require(init.count(START_WRITE.encode()) == 1, MODEM_MSG)
    require(init.count(b'/bin/busybox timeout -k 1 10 /bin/busybox sh -c') == 1, MODEM_MSG)
    require(init.count(b'printf start >/sys/class/remoteproc/remoteproc2/state') == 1, MODEM_MSG)
    require(init.count(MSS_STATE.encode()) == 3 and init.count(MSS_NAME.encode()) == 1 and
            init.count(b"/sys/class/remoteproc/remoteproc2 ") == 1 and
            init.count(b"remoteproc3") == 0 and init.count(b"remoteproc1") == 0 and
            init.count(b"remoteproc4") == 0, MODEM_MSG)
    require(init.count(b'[ "$MSTATE" = "running" ]') == 1 and
            init.count(b'[ "$MSTATE" = "offline" ]') == 1, MODEM_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox cat "
                       b"/sys/class/remoteproc/remoteproc2/state") == 2, MODEM_MSG)
    for state in (b'wlog "modem start phase begin"', b'wlog "modem start phase end"',
                  b'wlog "modem name: $MNAME"', b'wlog "modem name read failed"',
                  b'wlog "modem state: $MSTATE"',
                  b'wlog "modem state after start: $MSTATE"',
                  b'wlog "modem state read failed after start"',
                  b'wlog "modem state read failed before start"',
                  b'wlog "modem start skipped: already running"',
                  b'wlog "modem start skipped: state $MSTATE"',
                  b'wlog "modem start write accepted"',
                  b'wlog "modem start write failed: $err"',
                  b'wlog "modem start failed: missing /sys/class/remoteproc/remoteproc2"'):
        require(init.count(state) == 1, MODEM_MSG)
    require(b"stop" not in init and b"rmmod" not in init and b"modprobe" not in init and
            b"remoteproc-mss" not in init and b"wpss_boot" not in init and
            b"remoteproc1" not in init and b"remoteproc3" not in init and
            b"remoteproc4" not in init, MODEM_MSG)
    require(init.count(b">/sys/class/remoteproc/") == 1 and
            init.count(b"/sys/class/remoteproc/remoteproc2/state") == 3 and
            init.count(b"/sys/class/remoteproc/remoteproc2/name") == 1 and
            init.count(b"rmmod") == 0 and init.count(b"modprobe") == 0 and
            init.count(b'/bin/busybox insmod "/mnt/vendor_dlkm/lib/modules/'
                       b'qcom_q6v5_pas.ko') == 0, MODEM_MSG)
    require(init.count(insmod) == 1 and
            init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox insmod") == 2 and
            init.count(b"/bin/busybox insmod") == 2, MODEM_MSG)
    base_init = init.replace(modem, b"", 1)
    wpss.check_init(base_init, order)
    frozen = frozen_init(order)
    require(base_init == wpss.expected_init(frozen), DELTA_MSG)
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
    for name in wpss.SUPPLIER_MODULES:
        entry = vendor_files.get("lib/modules/" + name)
        require(entry is not None and modules.sha256(entry["data"]) == wpss.SUPPLIER_SHA256[name] and
                len(entry["data"]) == wpss.SUPPLIER_SIZE[name],
                f"supplier module {name} is not the measured stock vendor_boot provider")
    eud.vendor.check_stock(stock, library)
    init = expected_init(frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-modem-start-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"supplier phase: one bounded insmod of {wpss.SUPPLIER_COUNT} stock /lib/modules "
          f"suppliers ({', '.join(wpss.SUPPLIER_MODULES)}) inside the qca_cld3 gate, unchanged "
          f"from #75")
    print("modem phase: one guarded bounded single write of start to "
          "/sys/class/remoteproc/remoteproc2/state after the supplier phase and bind gate "
          f"and before the single stock WLAN insmod; a running modem is left untouched; logs "
          "the remoteproc name, write result and resulting state; no rmmod, no reload, no "
          "stop, no other remoteproc write")
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
