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
base = wpss.base
eud = wpss.eud
modules = wpss.modules
static = wpss.static
require = wpss.require
MEASURED_WPSS = "5a61de0e39d4cc8f985d38f0be2e39ce3054cae3b94a5fc64df9617f93e563ed"
MEASURED_MODEM = "560c98e5909af99921122610f4ce1b1899030685b32ae1b7d32991181f628749"
MEASURED_SESSION = "4216af26089281b135c145eb96da281781b03d73c24cedd6255232456b4f7938"
PRIOR_IMAGES = (*wpss.PRIOR_IMAGES, MEASURED_WPSS, MEASURED_MODEM, MEASURED_SESSION)
FROZEN_SOURCE = wpss.FROZEN_SOURCE
FROZEN_SHA256 = wpss.FROZEN_SHA256
FROZEN_MSG = ipci.FROZEN_MSG
SHA_MSG = ipci.SHA_MSG
TIMER_MSG = ipci.TIMER_MSG
LIST_MSG = ipci.LIST_MSG
KO_MSG = ipci.KO_MSG
ENVELOPE_MSG = ipci.ENVELOPE_MSG
DELTA_MSG = "init is not the exact measured #75 init plus one #81 session marker"
MARKER_MSG = ("the single #81 session marker after the armed timer is missing, duplicated, "
              "moved, reworded, or the init diverges from the measured #75 init elsewhere")
KEEP_MSG = "init creates /run/keep before a verified key-only SSH session"
REMOTE_MSG = "init controls a remoteproc, unloads or reloads a module"
STARTING = b"log 'starting'\n"
SESSION_MARKER = (
    b"log 'session #81: fatal-stream run - host dmesg -w opened before the guarded start'\n")


def expected_init(frozen):
    measured = wpss.expected_init(frozen)
    require(measured.count(eud.TIMER) == 1 and measured.count(SESSION_MARKER) == 0 and
            measured.count(STARTING) == 1, DELTA_MSG)
    return measured.replace(eud.TIMER, eud.TIMER + SESSION_MARKER, 1)


def check_init(init, order):
    require(init.count(eud.TIMER) == 1, TIMER_MSG)
    require(init.count(SESSION_MARKER) == 1, MARKER_MSG)
    marker = init.index(SESSION_MARKER)
    require(init.index(STARTING) < init.index(eud.TIMER) < marker <
            init.index(eud.LOAD_BEGIN), MARKER_MSG)
    require(init.count(b"/run/keep") == 1 and
            b"/run/keep" not in init[:init.index(eud.TIMER)], KEEP_MSG)
    require(init.count(b"session #81") == 1, MARKER_MSG)
    require(b"rmmod" not in init and b"modprobe" not in init and
            b"/sys/class/remoteproc" not in init and b"wpss_boot" not in init and
            b"remoteproc2" not in init, REMOTE_MSG)
    measured = init.replace(SESSION_MARKER, b"", 1)
    offset = wpss.check_init(measured, order)
    require(measured == wpss.expected_init(wpss.frozen_init(order)) and
            init == expected_init(wpss.frozen_init(order)), DELTA_MSG)
    static.check_timer(measured)
    return offset


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
        require(entry is not None and modules.sha256(entry["data"]) ==
                wpss.SUPPLIER_SHA256[name] and len(entry["data"]) ==
                wpss.SUPPLIER_SIZE[name],
                f"supplier module {name} is not the measured stock vendor_boot provider")
    eud.vendor.check_stock(stock, library)
    init = expected_init(wpss.frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-live-fatal-stream-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"session delta: one #81 session-only log after the armed {eud.TIMER_BUDGET} s "
          "timer; no remoteproc start in init; #75 supplier phase and order, bounded "
          "WPSS/icnss2 bind gate, read-only mounts, single stock WLAN load, module "
          "closures, USB/key-only SSH path and timer unchanged")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
