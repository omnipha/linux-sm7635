import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


lfs = load("build-init-boot-live-fatal-stream-payload.py", "live_fatal_stream_builder")
wpss = lfs.wpss
base = lfs.base
eud = lfs.eud
modules = lfs.modules
static = lfs.static
require = lfs.require
MEASURED_LIVE = "ae2ccff760b47efd1663fea6d6e614e2e1523ccdfcd258612354b2ceb4baf47e"
PRIOR_IMAGES = (*lfs.PRIOR_IMAGES, MEASURED_LIVE)
FROZEN_SOURCE = lfs.FROZEN_SOURCE
FROZEN_SHA256 = lfs.FROZEN_SHA256
FROZEN_MSG = lfs.FROZEN_MSG
SHA_MSG = lfs.SHA_MSG
TIMER_MSG = lfs.TIMER_MSG
LIST_MSG = lfs.LIST_MSG
KO_MSG = lfs.KO_MSG
ENVELOPE_MSG = lfs.ENVELOPE_MSG
DELTA_MSG = ("init is not the exact measured #81 init with the session marker reworded "
             "to the single #83 retry marker")
MARKER_MSG = ("the single #83 session marker after the armed timer is missing, duplicated, "
              "moved, reworded, carries the reused #81 marker text, or the init diverges "
              "from the measured #75 init elsewhere")
KEEP_MSG = lfs.KEEP_MSG
REMOTE_MSG = lfs.REMOTE_MSG
STARTING = lfs.STARTING
SESSION_MARKER = (
    b"log 'session #83: capture-gated retry - selftest marker proves a live console "
    b"line before the guarded start'\n")


def expected_init(frozen):
    measured81 = lfs.expected_init(frozen)
    require(measured81.count(eud.TIMER) == 1 and measured81.count(SESSION_MARKER) == 0 and
            measured81.count(lfs.SESSION_MARKER) == 1, DELTA_MSG)
    return measured81.replace(lfs.SESSION_MARKER, SESSION_MARKER, 1)


def check_init(init, order):
    require(init.count(eud.TIMER) == 1, TIMER_MSG)
    require(init.count(SESSION_MARKER) == 1, MARKER_MSG)
    require(init.count(lfs.SESSION_MARKER) == 0, MARKER_MSG)
    require(init.count(b"session #81") == 0 and init.count(b"session #83") == 1, MARKER_MSG)
    marker = init.index(SESSION_MARKER)
    require(init.index(STARTING) < init.index(eud.TIMER) < marker <
            init.index(eud.LOAD_BEGIN), MARKER_MSG)
    require(init.count(b"/run/keep") == 1 and
            b"/run/keep" not in init[:init.index(eud.TIMER)], KEEP_MSG)
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
            "usage: build-init-boot-retry-marker-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"session delta: only the marker reworded to the single #83 retry log after the "
          f"armed {eud.TIMER_BUDGET} s timer; no remoteproc start in init; #75 supplier "
          "phase and order, bounded WPSS/icnss2 bind gate, read-only mounts, single stock "
          "WLAN load, module closures, USB/key-only SSH path and timer unchanged")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
