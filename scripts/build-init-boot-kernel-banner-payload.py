import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


static = load("build-init-boot-static-address-payload.py", "static_address_builder")
eud = static.eud
base = static.base
modules = static.modules
MEASURED_STATIC = "995aaca380225be1b865493230164ecc49c5c958b50560d3851010bf3294e5f9"
MEASURED_PAYLOAD = "37535dd13312e2d2078c344cbf11db32260f0d35c4d3e0b2bf95a214b27b9bb8"
PRIOR_IMAGES = (*static.PRIOR_IMAGES, MEASURED_STATIC, MEASURED_PAYLOAD)
FROZEN_SOURCE = "init"
FROZEN_SHA256 = "ab2377a6ea4f852e03a24056e4087977f6d9d4c8019868c55e4d552e7b97d05b"
STARTING = b"log 'starting'\n"
BANNER = (b'log "kernel banner: $(uname -r 2>&1) '
          b'$(/bin/busybox cat /proc/version 2>&1)"\n')
BANNER_MSG = "the uname -r /proc/version banner log is missing, duplicated or moved"
DELTA_MSG = "init is not frozen #53 plus the single kernel banner log line"
FROZEN_MSG = "frozen #53 init is missing or already contains the kernel banner log"
SHA_MSG = static.SHA_MSG
TIMER_MSG = static.TIMER_MSG
LIST_MSG = static.LIST_MSG
KO_MSG = static.KO_MSG
ENVELOPE_MSG = static.ENVELOPE_MSG
require = static.require


def require_frozen(frozen, order):
    require(frozen.startswith(eud.SHEBANG) and frozen.count(STARTING) == 1 and
            frozen.count(BANNER) == 0 and b"uname" not in frozen and
            b"/proc/version" not in frozen, FROZEN_MSG)
    require(modules.sha256(frozen) == FROZEN_SHA256, FROZEN_MSG)
    static.check_init(frozen, order)
    return frozen


def frozen_init(order):
    return require_frozen((HERE.parent / "initramfs" / FROZEN_SOURCE).read_bytes(), order)


def expected_init(frozen):
    require(frozen.count(STARTING) == 1 and frozen.count(BANNER) == 0, DELTA_MSG)
    return frozen.replace(STARTING, STARTING + BANNER, 1)


def check_banner(init):
    require(init.count(BANNER) == 1, BANNER_MSG)
    require(init.count(STARTING) == 1, BANNER_MSG)
    require(init.index(BANNER) == init.index(STARTING) + len(STARTING), BANNER_MSG)
    return init.index(BANNER)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    banner = check_banner(init)
    frozen = frozen_init(order)
    stripped = init.replace(BANNER, b"", 1)
    static.check_init(stripped, order)
    require(stripped == frozen and init == expected_init(frozen), DELTA_MSG)
    return banner


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order):
    return eud.candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                              init_check=check_init)


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, ENVELOPE_MSG)
    image, digest = static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES and digest != MEASURED_STATIC and
            digest != MEASURED_PAYLOAD and digest != static.MEASURED_PERIPHERAL, SHA_MSG)
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
            "usage: build-init-boot-kernel-banner-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print("kernel banner: one log line after starting, uname -r and /proc/version")
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
