import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


banner = load("build-init-boot-kernel-banner-payload.py", "kernel_banner_builder")
static = banner.static
eud = banner.eud
base = banner.base
modules = banner.modules
require = static.require
MEASURED_BANNER = "cafcabb67a1d79f7877b59a1daff25d92fd8fc6ecb5d5128f44ab8cc17af541c"
MEASURED_EXT4_BOOT = "0ca048d554857b469aadf6a55e6fd70cc1cb51cd72eff8f6f98e451bb595f72b"
MEASURED_EXT4_GZIP = "d259b744465eb48b2c42ddcedcf89f6d2608638c6b04f3c2c534fa27b66d7738"
MEASURED_EXT4_IMAGE = "7be448b91b618cbe1dbda9659dfeeb2d554f702091c39453bfa44497c280377e"
MEASURED_EXT4_CONFIG = "c6d8a4e86301d314adc8724b7b3d985d81b9cff2074e0e917ed976a46df3ebd9"
MEASURED_KALLSYMS_IMAGE = "724d8a6b3eac37046941458b83059d00a48ed37fc0f70a9f6a3224c38e86af6a"
MEASURED_KALLSYMS_CONFIG = "05c70f1a766c7f2d265dc538363445ae581d158a1e60d93313e0c35a0aa2dfd0"
PRIOR_IMAGES = (*banner.PRIOR_IMAGES, MEASURED_BANNER, MEASURED_EXT4_BOOT,
                MEASURED_EXT4_GZIP, MEASURED_EXT4_IMAGE, MEASURED_EXT4_CONFIG,
                MEASURED_KALLSYMS_IMAGE, MEASURED_KALLSYMS_CONFIG)
FROZEN_SOURCE = banner.FROZEN_SOURCE
FROZEN_SHA256 = banner.FROZEN_SHA256
STARTING = banner.STARTING
OLD_BANNER = banner.BANNER
BANNER = OLD_BANNER.replace(b"kernel banner: ", b"kernel banner #63: ", 1)
BANNER_MSG = banner.BANNER_MSG
DELTA_MSG = banner.DELTA_MSG
FROZEN_MSG = banner.FROZEN_MSG
SHA_MSG = banner.SHA_MSG
TIMER_MSG = banner.TIMER_MSG
LIST_MSG = banner.LIST_MSG
KO_MSG = banner.KO_MSG
ENVELOPE_MSG = banner.ENVELOPE_MSG


def require_frozen(frozen, order):
    return banner.require_frozen(frozen, order)


def frozen_init(order):
    return banner.frozen_init(order)


def expected_init(frozen):
    require(frozen.count(STARTING) == 1 and frozen.count(BANNER) == 0 and
            frozen.count(OLD_BANNER) == 0, DELTA_MSG)
    return frozen.replace(STARTING, STARTING + BANNER, 1)


def check_banner(init):
    require(init.count(BANNER) == 1, BANNER_MSG)
    require(init.count(STARTING) == 1, BANNER_MSG)
    require(init.count(OLD_BANNER) == 0, BANNER_MSG)
    require(init.index(BANNER) == init.index(STARTING) + len(STARTING), BANNER_MSG)
    return init.index(BANNER)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    banner_offset = check_banner(init)
    frozen = frozen_init(order)
    stripped = init.replace(BANNER, b"", 1)
    static.check_init(stripped, order)
    require(stripped == frozen and init == expected_init(frozen), DELTA_MSG)
    return banner_offset


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
            "usage: build-init-boot-initcall-debug-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print("kernel banner #63: one log line after starting, uname -r and /proc/version")
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
