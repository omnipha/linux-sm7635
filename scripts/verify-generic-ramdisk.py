import gzip
import hashlib
import pathlib
import struct
import sys

PAGE = 4096
OLD_BOOT_SHA256 = "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def align(size):
    return (size + PAGE - 1) // PAGE * PAGE


def fields(image):
    require(len(image) >= PAGE and image[:8] == b"ANDROID!", "invalid boot magic/page")
    kernel_size, ramdisk_size, _, header_size = struct.unpack_from("<IIII", image, 8)
    require(header_size == 1584 and struct.unpack_from("<I", image, 40)[0] == 4
            and struct.unpack_from("<I", image, 1580)[0] == 0,
            "invalid header-v4 geometry/signature")
    return kernel_size, ramdisk_size


def check_empty_boot(image):
    _, ramdisk_size = fields(image)
    require(ramdisk_size == 0, "boot generic ramdisk must be empty")


def check_built(boot, init_boot, kernel, ramdisk):
    check_empty_boot(boot)
    boot_kernel_size, _ = fields(boot)
    require(boot_kernel_size == len(kernel), "boot kernel size mismatch")
    require(boot[PAGE:PAGE + len(kernel)] == kernel, "boot kernel payload mismatch")
    boot_end = PAGE + align(len(kernel))
    require(len(boot) == boot_end and not any(boot[PAGE + len(kernel):boot_end]),
            "boot contains data after the kernel")

    init_kernel_size, init_ramdisk_size = fields(init_boot)
    require(init_kernel_size == 0, "init_boot kernel must be empty")
    require(init_ramdisk_size == len(ramdisk) > 0, "init_boot ramdisk size mismatch")
    init_end = PAGE + align(len(ramdisk))
    require(init_boot[PAGE:PAGE + len(ramdisk)] == ramdisk,
            "init_boot generic ramdisk differs from verified gzip cpio")
    require(len(init_boot) == init_end and not any(init_boot[PAGE + len(ramdisk):init_end]),
            "init_boot ramdisk layout mismatch")
    require(ramdisk[:2] == b"\x1f\x8b" and gzip.decompress(ramdisk).startswith(b"070701"),
            "init_boot generic ramdisk is not gzip newc cpio")
    return boot_end


def cpio_entry(name, data, inode):
    name = name.encode() + b"\0"
    attributes = (inode, 0o100755, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0)
    entry = b"070701" + b"".join(f"{value:08x}".encode() for value in attributes) + name
    entry += bytes(-len(entry) % 4) + data
    return entry + bytes(-len(entry) % 4)


def fixture(kernel, ramdisk):
    header = bytearray(PAGE)
    header[:8] = b"ANDROID!"
    struct.pack_into("<II", header, 8, len(kernel), len(ramdisk))
    struct.pack_into("<I", header, 20, 1584)
    struct.pack_into("<I", header, 40, 4)
    return bytes(header) + kernel + bytes(-len(kernel) % PAGE) + ramdisk + bytes(-len(ramdisk) % PAGE)


def expect_rejection(label, expected, boot, init_boot, kernel, ramdisk):
    try:
        check_built(boot, init_boot, kernel, ramdisk)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def self_test():
    archive = cpio_entry("init", b"#!/bin/sh\n", 1) + cpio_entry("TRAILER!!!", b"", 2)
    ramdisk = gzip.compress(archive, mtime=0)
    kernel = b"tiny kernel"
    boot = fixture(kernel, b"")
    init_boot = fixture(b"", ramdisk)
    check_built(boot, init_boot, kernel, ramdisk)
    print("synthetic single-generic-ramdisk fixture: OK")
    duplicate = fixture(kernel, ramdisk)
    expect_rejection("duplicated small gzip cpio", "boot generic ramdisk must be empty",
                     duplicate, init_boot, kernel, ramdisk)
    expect_rejection("advertised boot ramdisk without payload", "boot generic ramdisk must be empty",
                     duplicate[:PAGE + align(len(kernel))], init_boot, kernel, ramdisk)
    expect_rejection("unadvertised boot ramdisk payload", "boot contains data after the kernel",
                     boot + ramdisk, init_boot, kernel, ramdisk)
    expect_rejection("nonempty init_boot kernel", "init_boot kernel must be empty",
                     boot, fixture(kernel, ramdisk), kernel, ramdisk)
    changed = bytearray(ramdisk)
    changed[12] ^= 1
    expect_rejection("changed init_boot cpio", "init_boot generic ramdisk differs from verified gzip cpio",
                     boot, fixture(b"", changed), kernel, ramdisk)


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    require(len(sys.argv) == 6, "usage: verify-generic-ramdisk.py STOCK_BOOT BOOT INIT_BOOT KERNEL RAMDISK")
    stock, boot, init_boot, kernel, ramdisk = (
        pathlib.Path(name).read_bytes() for name in sys.argv[1:])
    check_empty_boot(stock)
    boot_end = check_built(boot, init_boot, kernel, ramdisk)
    require(hashlib.sha256(boot).hexdigest() not in (
        OLD_BOOT_SHA256, "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
        "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7"),
        "boot image repeats an old SHA")
    print(f"stock boot ramdisk_size=0; built boot ramdisk_size=0, kernel at {PAGE}, "
          f"end={boot_end}; init_boot ramdisk_size={len(ramdisk)} at {PAGE}, kernel_size=0")
    print(f"#14 reconstruction not applicable to Path B: Image alone changed; "
          f"new boot: {len(boot)} bytes, SHA-256 {hashlib.sha256(boot).hexdigest()}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
