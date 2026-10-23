import gzip
import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


base = load("build-init-boot-lz4-debug-ramdisk-payload.py", "lz4_base")
modules = load("vendor-module-closure.py", "vendor_modules")
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
STOCK_SHA256 = base.STOCK_SHA256
SOURCE_SHA256 = base.GZIP_SHA256
SOURCE_CPIO_SHA256 = base.CPIO_SHA256
VENDOR_SHA256 = modules.VENDOR_SHA256
BOOT_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
CONFIG_SHA256 = "90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478"
EXPECTED_SHA256 = ""
PRIOR_IMAGES = (*base.PRIOR_IMAGES, base.RESULT_SHA256)
INIT_START = b"#!/bin/busybox sh\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_host_path(boot, vendor, stock, recovery, config_gz, kernel_source,
                     decompressor_source, pstore, library):
    require(modules.sha256(boot) == BOOT_SHA256, "boot_a is not the verified stock image")
    require(boot[:8] == b"ANDROID!" and struct.unpack_from("<I", boot, 40)[0] == 4 and
            struct.unpack_from("<I", boot, 12)[0] == 0 and
            struct.unpack_from("<I", boot, 8)[0] > 0,
            "stock boot_a must supply a kernel and no generic ramdisk")
    require(modules.sha256(stock) == STOCK_SHA256 and stock[:8] == b"ANDROID!" and
            struct.unpack_from("<I", stock, 40)[0] == 4 and
            struct.unpack_from("<II", stock, 8) == (0, base.STOCK_RAMDISK_SIZE),
            "stock init_boot_a must supply the generic ramdisk and no kernel")
    require(modules.sha256(config_gz) == CONFIG_SHA256,
            "config.gz is not the verified stock kernel config")
    config = gzip.decompress(config_gz)
    for option in (b"CONFIG_BLK_DEV_INITRD=y", b"CONFIG_RD_LZ4=y", b"CONFIG_BOOT_CONFIG=y"):
        require(option in config.splitlines(), f"stock kernel does not enable {option.decode()}")
    require(b"unpack_to_rootfs((char *)initrd_start, initrd_end - initrd_start)" in
            kernel_source and b"openflags |= O_TRUNC" in kernel_source and
            b"if (strcmp(collected, \"TRAILER!!!\") == 0)" in kernel_source,
            "kernel initrd source does not unpack concatenated cpio into one rootfs")
    require(b"ARCHIVE_MAGICNUMBER" in decompressor_source and
            b"LZ4_decompress_safe" in decompressor_source,
            "kernel source does not decompress Android LZ4 legacy blocks")
    require(b"Trying to unpack rootfs image as initramfs..." in pstore and
            b"Freeing initrd memory: 57716K" in pstore and
            b"Run /init as init process" in pstore and
            b"usb-init: starting" in pstore and
            b"rootfs image is not initramfs" not in pstore,
            "measured #42 initrd does not show the vendor+generic+recovery unpack and own init")
    modules.check_initrd_model()
    vendor_archive = modules.vendor_ramdisk_cpio(vendor, library)
    files = modules.vendor_files(vendor_archive)
    recovery_entries = modules.recovery_ramdisk_entries(recovery, library)
    return files, recovery_entries


def source_cpio(gzip_bytes):
    require(len(gzip_bytes) == base.GZIP_SIZE and
            modules.sha256(gzip_bytes) == SOURCE_SHA256,
            "source gzip is not the verified caa3eb82 debug ramdisk")
    archive = gzip.decompress(gzip_bytes)
    require(len(archive) == base.CPIO_SIZE and
            modules.sha256(archive) == SOURCE_CPIO_SHA256,
            "source cpio is not the verified 2998685e archive")
    entries, trailer = modules.parse_newc(archive, "source debug cpio")
    require(modules.encode_newc(entries, trailer) == archive,
            "source debug cpio does not round-trip with 512-byte padding")
    require(not any(entry["name"].endswith(".ko") for entry in entries),
            "source debug cpio contains .ko files")
    return archive, entries, trailer


def candidate_cpio(gzip_bytes, init_bytes, vendor_files, recovery_entries, order):
    archive, entries, trailer = source_cpio(gzip_bytes)
    init_entries = [entry for entry in entries if entry["name"] == "init"]
    require(len(init_entries) == 1 and init_entries[0]["mode"] & 0o170777 == 0o100755,
            "source cpio must contain exactly one executable /init")
    require(init_bytes.startswith(INIT_START), "new /init is not the debug busybox script")
    init_text = init_bytes.decode()
    modules.verify_init(init_text, order)
    require(init_bytes != init_entries[0]["data"], "new /init repeats the measured debug init")
    changed = []
    for entry in entries:
        if entry["name"] == "init":
            entry = {**entry, "data": init_bytes}
        changed.append(entry)
    cpio = modules.encode_newc(changed, trailer)
    new_entries, _ = modules.parse_newc(cpio, "candidate debug cpio")
    require(len(new_entries) == len(entries) and
            [entry["name"] for entry in new_entries] ==
            [entry["name"] for entry in entries] and
            sum(a["data"] != b["data"] for a, b in zip(new_entries, entries)) == 1,
            "candidate cpio changed entries besides /init")
    require(not any(entry["name"].endswith(".ko") for entry in new_entries),
            "candidate debug cpio contains a .ko")
    modules.prove_vendor_modules(vendor_files, new_entries, recovery_entries)
    return cpio


def check_stock(stock, library):
    require(len(stock) == IMAGE_SIZE and modules.sha256(stock) == STOCK_SHA256,
            "stock init_boot is not the verified 8388608-byte baa33fd4 image")
    kernel, ramdisk, os_version, header_size = struct.unpack_from("<IIII", stock, 8)
    require(stock[:8] == b"ANDROID!" and
            (kernel, ramdisk, os_version, header_size) ==
            (0, base.STOCK_RAMDISK_SIZE, 0, base.HEADER_SIZE) and
            struct.unpack_from("<I", stock, 40)[0] == 4 and
            struct.unpack_from("<I", stock, 1580)[0] == 0 and
            not any(stock[base.HEADER_SIZE:PAGE]) and
            not any(stock[PAGE + ramdisk:TAIL_OFFSET]),
            "stock init_boot header, kernel or gap differs from #42")
    footer = stock[base.FOOTER_OFFSET:]
    require(struct.unpack_from(">4sIIQQQ", footer) ==
            (b"AVBf", 1, 0, TAIL_OFFSET, TAIL_OFFSET, base.VBMETA_SIZE) and
            stock[TAIL_OFFSET:TAIL_OFFSET + 4] == b"AVB0",
            "stock signed tail is not the #42 AVB envelope")
    frame = stock[PAGE:PAGE + ramdisk]
    require(frame[:4] == base.LZ4_MAGIC and struct.unpack_from("<I", frame, 4)[0] ==
            len(frame) - 8,
            "stock generic ramdisk is not one Android LZ4 legacy block")
    stock_cpio = base.decompress(library, frame[8:], base.STOCK_CPIO_SIZE)
    require(base.compress_hc(library, stock_cpio, base.HC_LEVEL) == frame[8:],
            "host LZ4 HC-12 cannot reproduce the stock ramdisk block")
    return stock_cpio


def encode_frame(cpio, library):
    block = base.compress_hc(library, cpio, base.HC_LEVEL)
    require(base.decompress(library, block, len(cpio)) == cpio,
            "LZ4 HC-12 block does not round-trip")
    frame = base.LZ4_MAGIC + struct.pack("<I", len(block)) + block
    require(len(frame) <= base.MAX_FRAME,
            "script does not fit the stock LZ4 envelope; stop without an image")
    return frame


def assemble(stock, frame):
    header = bytearray(stock[:PAGE])
    struct.pack_into("<I", header, base.RAMDISK_SIZE_OFFSET, len(frame))
    image = bytes(header) + frame + bytes(TAIL_OFFSET - PAGE - len(frame)) + stock[TAIL_OFFSET:]
    require(len(image) == IMAGE_SIZE and image[TAIL_OFFSET:] == stock[TAIL_OFFSET:] and
            image[:base.RAMDISK_SIZE_OFFSET] == stock[:base.RAMDISK_SIZE_OFFSET] and
            image[base.RAMDISK_SIZE_OFFSET + 4:PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:PAGE],
            "candidate changed stock prefix or signed tail")
    digest = modules.sha256(image)
    require(digest not in PRIOR_IMAGES, "candidate repeats a previously measured SHA-256")
    return image, digest


def inputs(paths):
    return [pathlib.Path(path).read_bytes() for path in paths]


def prepare(paths):
    require(len(paths) == 9,
            "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE")
    stock, source, boot, vendor, recovery, config, kernel, decompressor, pstore = inputs(paths)
    library = base.lz4()
    files, recovery_entries = verify_host_path(boot, vendor, stock, recovery, config,
                                               kernel, decompressor, pstore, library)
    order, outside = modules.compute_order(files)
    check_stock(stock, library)
    init_bytes = (HERE.parent / "initramfs" / "init").read_bytes()
    cpio = candidate_cpio(source, init_bytes, files, recovery_entries, order)
    frame = encode_frame(cpio, library)
    return stock, source, cpio, frame, order, outside, library


def main():
    args = sys.argv[1:]
    require(len(args) == 11 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-vendor-modules-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE OUTPUT")
    stock, source, cpio, frame, order, outside, library = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; {len(outside)} USB additions")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"stock signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
