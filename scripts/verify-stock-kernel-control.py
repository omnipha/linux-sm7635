import gzip
import hashlib
import pathlib
import struct
import sys

PAGE = 4096
STOCK_BOOT_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
STOCK_PAYLOAD_SHA256 = "dcbd8ae71b7e6341c3604c35360213b1d40a69ac38672e247772d4af399c3651"
STOCK_PAYLOAD_SIZE = 13949926
STOCK_IMAGE_SIZE = 35224064
BASE_BOOT_SHA256 = "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af"
PRIOR_BOOTS = (
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce",
    "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a",
    "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
    "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7",
)
BASE_CMDLINE = (b"console=ttynull stack_depot_disable=on cgroup_disable=pressure "
                b"kasan.page_alloc.sample=10 kasan.stacktrace=off kvm-arm.mode=protected "
                b"bootconfig ioremap_guard loglevel=6")
ARM64_FIELDS = "<IIQQQQQQ4sI"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def align(size):
    return (size + PAGE - 1) // PAGE * PAGE


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def kernel_of(image):
    require(len(image) >= PAGE and image[:8] == b"ANDROID!", "invalid boot magic")
    size = struct.unpack_from("<I", image, 8)[0]
    require(size > 0 and PAGE + size <= len(image), "kernel payload out of bounds")
    return image[PAGE:PAGE + size]


def arm64_header(image):
    require(len(image) >= 64, "arm64 Image header truncated")
    return struct.unpack_from(ARM64_FIELDS, image, 0)


def check_control(control, base, stock, check_digests=True, prior_boots=PRIOR_BOOTS):
    require(control[:8] == base[:8] == stock[:8] == b"ANDROID!", "boot magic mismatch")
    if check_digests:
        require(sha256(stock) == STOCK_BOOT_SHA256, "stock boot_a is not the verified reference")
        require(sha256(base) == BASE_BOOT_SHA256, "base boot is not the verified #21 image")
    stock_payload = kernel_of(stock)
    base_payload = kernel_of(base)
    payload = kernel_of(control)
    if check_digests:
        require(len(stock_payload) == STOCK_PAYLOAD_SIZE and
                sha256(stock_payload) == STOCK_PAYLOAD_SHA256,
                "stock slot-A gzip payload is not the verified reference")
    require(payload == stock_payload,
            "control gzip payload is not byte-identical to the stock slot-A payload")
    require(payload != base_payload, "control still carries the #21 kernel payload")
    require(struct.unpack_from("<I", control, 8)[0] == len(stock_payload),
            "control kernel size does not equal stock payload size")

    require(control[:8] == base[:8] and control[12:PAGE] == base[12:PAGE],
            "control header page differs from #21 beyond the kernel-size field")
    require(struct.unpack_from("<I", control, 12)[0] == 0 and
            struct.unpack_from("<I", control, 40)[0] == 4 and
            struct.unpack_from("<I", control, 20)[0] == 1584 and
            struct.unpack_from("<I", control, 16)[0] == 0 and
            struct.unpack_from("<I", control, 1580)[0] == 0,
            "control header is not the #21 header-v4 empty-ramdisk geometry")
    cmdline = control[44:1580].split(b"\x00", 1)[0]
    require(cmdline == BASE_CMDLINE == base[44:1580].split(b"\x00", 1)[0],
            "control command line differs from #21")
    require(not any(control[1584:PAGE]), "control header padding is not zero")

    end = PAGE + len(payload)
    require(len(control) == PAGE + align(len(payload)),
            "control image length is not the page-aligned kernel end")
    require(not any(control[end:]), "control has non-zero data after the kernel")
    require(control[-64:-60] != b"AVBf" and b"AVB0" not in control[end:],
            "control carries AVB metadata")
    require(control[PAGE + len(payload):PAGE + align(len(payload))] ==
            bytes(align(len(payload)) - len(payload)), "control page padding is not zero")

    control_image = gzip.decompress(payload)
    base_image = gzip.decompress(base_payload)
    stock_image = gzip.decompress(stock_payload)
    require(control_image == stock_image, "control decompressed Image differs from stock")
    if check_digests:
        require(len(control_image) == STOCK_IMAGE_SIZE, "stock Image size is not the verified size")
    code0, _, text_offset, image_size, flags, r2, r3, r4, magic, pe = arm64_header(control_image)
    b_code0, _, b_text, b_size, b_flags, b_r2, b_r3, b_r4, b_magic, b_pe = arm64_header(base_image)
    require(magic == b_magic == b"ARMd", "arm64 Image magic missing")
    require(text_offset == b_text == 0, "arm64 Image text_offset is not zero in both images")
    require(code0 == b_code0 and code0 == 0xFA405A4D, "arm64 Image branch/MZ header differs")
    require(flags == b_flags, "arm64 Image flags differ")
    require((r2, r3, r4) == (b_r2, b_r3, b_r4) == (0, 0, 0), "arm64 Image reserved fields differ")
    require(pe == b_pe == 0x40, "arm64 Image PE header offset differs")
    require(image_size >= len(control_image) and b_size >= len(base_image),
            "arm64 Image effective size is smaller than the file")

    digest = sha256(control)
    require(digest not in prior_boots and digest != STOCK_BOOT_SHA256,
            "control SHA-256 repeats a prior boot")
    return digest, len(control), len(payload)


def expect_rejection(label, expected, *args):
    try:
        check_control(*args, check_digests=False)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def fixture_image(text_offset=0, flags=0xA, filler=b"x"):
    image = bytearray(0x100)
    struct.pack_into(ARM64_FIELDS, image, 0, 0xFA405A4D, 0, text_offset, 0x200, flags,
                     0, 0, 0, b"ARMd", 0x40)
    return bytes(image) + filler * 64


def fixture_boot(payload, cmdline=BASE_CMDLINE):
    header = bytearray(PAGE)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(payload))
    struct.pack_into("<I", header, 20, 1584)
    struct.pack_into("<I", header, 40, 4)
    header[44:44 + len(cmdline)] = cmdline
    return bytes(header) + payload + bytes(-len(payload) % PAGE)


def self_test():
    stock_payload = gzip.compress(fixture_image(filler=b"s"), mtime=0)
    base_payload = gzip.compress(fixture_image(filler=b"b" * 2), mtime=0)
    stock = fixture_boot(stock_payload, b"")
    base = fixture_boot(base_payload)
    control = fixture_boot(stock_payload)
    digest, size, kernel = check_control(control, base, stock, check_digests=False)
    print(f"synthetic control fixture: OK ({size} bytes, kernel {kernel})")

    changed = bytearray(stock_payload)
    changed[-9] ^= 1
    expect_rejection("changed payload byte", "control gzip payload is not byte-identical to the "
                     "stock slot-A payload", fixture_boot(bytes(changed)), base, stock)
    expect_rejection("base payload kept", "control gzip payload is not byte-identical to the "
                     "stock slot-A payload", base, base, stock)
    padded = bytearray(control)
    padded[-1] = 1
    expect_rejection("dirty page padding", "control has non-zero data after the kernel",
                     bytes(padded), base, stock)
    expect_rejection("appended data", "control image length is not the page-aligned kernel end",
                     control + bytes(PAGE), base, stock)
    changed_header = bytearray(control)
    changed_header[1000] ^= 1
    expect_rejection("changed command line", "control header page differs from #21 beyond the "
                     "kernel-size field", bytes(changed_header), base, stock)
    ramdisk = bytearray(control)
    struct.pack_into("<I", ramdisk, 12, 1)
    expect_rejection("nonempty generic ramdisk", "control header page differs from #21 beyond "
                     "the kernel-size field", bytes(ramdisk), base, stock)
    bad_text = gzip.compress(fixture_image(text_offset=0x80000, filler=b"s"), mtime=0)
    expect_rejection("nonzero text_offset", "arm64 Image text_offset is not zero in both images",
                     fixture_boot(bad_text), base, fixture_boot(bad_text, b""))
    bad_flags = gzip.compress(fixture_image(flags=0x2, filler=b"s"), mtime=0)
    expect_rejection("different arm64 flags", "arm64 Image flags differ",
                     fixture_boot(bad_flags), base, fixture_boot(bad_flags, b""))
    try:
        check_control(control, base, stock, check_digests=False, prior_boots=(digest,))
    except ValueError as exc:
        require(str(exc) == "control SHA-256 repeats a prior boot", f"unexpected failure: {exc}")
        print(f"expected repeated prior boot failure: {exc}")
    else:
        raise ValueError("repeated prior boot fixture was accepted")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    require(len(sys.argv) == 4,
            "usage: verify-stock-kernel-control.py CONTROL_BOOT BASE_21_BOOT STOCK_BOOT")
    control, base, stock = (pathlib.Path(name).read_bytes() for name in sys.argv[1:])
    digest, size, kernel = check_control(control, base, stock)
    print(f"control boot: {size} bytes, SHA-256 {digest}")
    print(f"control gzip payload: {kernel} bytes at {PAGE}, byte-identical to stock slot-A "
          f"payload {STOCK_PAYLOAD_SHA256}")
    print("control header/cmdline/empty ramdisk/page alignment equal #21 apart from kernel size "
          "and image length")
    print("control and #21 Image share arm64 header: MZ branch, text_offset 0, flags, "
          "reserved zero, ARMd magic, PE offset 0x40")
    print("control SHA-256 differs from 55fa78ca, 116b1662, 84f7f5ea, 5e866c54, 1fdc2570 "
          "and stock boot_a")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
