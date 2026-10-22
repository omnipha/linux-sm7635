import gzip
import hashlib
import importlib.util
import pathlib
import struct
import sys

SCRIPT = pathlib.Path(__file__).with_name("build-init-boot-lz4-debug-ramdisk-payload.py")
spec = importlib.util.spec_from_file_location("init_boot_lz4_builder", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

PAGE = builder.PAGE
IMAGE_SIZE = builder.IMAGE_SIZE
HEADER_SIZE = builder.HEADER_SIZE
RAMDISK_SIZE_OFFSET = builder.RAMDISK_SIZE_OFFSET
TAIL_OFFSET = builder.TAIL_OFFSET
MAX_FRAME = builder.MAX_FRAME
VBMETA_SIZE = builder.VBMETA_SIZE
FOOTER_OFFSET = builder.FOOTER_OFFSET
STOCK_RAMDISK_SIZE = builder.STOCK_RAMDISK_SIZE
GZIP_SIZE = builder.GZIP_SIZE
CPIO_SIZE = builder.CPIO_SIZE
HC_LEVEL = builder.HC_LEVEL
LZ4_MAGIC = builder.LZ4_MAGIC
STOCK_SHA256 = builder.STOCK_SHA256
GZIP_SHA256 = builder.GZIP_SHA256
CPIO_SHA256 = builder.CPIO_SHA256
FRAME_SIZE = builder.FRAME_SIZE
BLOCK_SIZE = builder.BLOCK_SIZE
CANDIDATE_SHA256 = builder.RESULT_SHA256
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (
    "baa33fd4", "f4a00ce3", "f4b987ee", "bde3a3b3", "6078269d", "23725940",
    "5e866c54", "84f7f5ea", "116b1662", "1fdc2570", "55fa78ca", "968625c7",
    "db2c635d", "13a48ff9", "6891dc51", "d966172c", "5a513998", "dc990b95",
    "e7fd2022", "7c409cde", "197aff11", "7cd886a2", "f1406364", "65fc21c4",
    "93e7625f", "c4f7dbee",
)

REPEATED = "candidate SHA-256 repeats a prior image"
STOCK_SIZE_MSG = "stock init_boot is not 8388608 bytes"
STOCK_SHA_MSG = "stock init_boot is not the verified baa33fd4 slot-A reference"
STOCK_LAYOUT_MSG = "stock init_boot is not header v4 with an empty kernel and stock LZ4 ramdisk"
STOCK_FOOTER_MSG = "stock AVBf footer does not point at the signed tail"
STOCK_BLOCK_MSG = "stock signed tail does not start with a nonzero 832-byte AVB0 block"
GZIP_SIZE_MSG = "debug gzip is not 1672600 bytes"
GZIP_SHA_MSG = "debug gzip is not the verified caa3eb82 archive"
GZIP_MSG = "debug input is not a valid gzip stream"
CPIO_MSG = "unpacked debug cpio is not the verified newc archive"
SIZE_MSG = "candidate is not 8388608 bytes"
HEADER_MSG = "candidate header page differs from stock beyond the ramdisk-size field"
FIELD_MSG = "candidate ramdisk-size field is not the expected frame size"
KERNEL_MSG = "candidate init_boot kernel is not empty"
FRAME_MSG = "ramdisk is not one Android LZ4 legacy frame"
BLOCK_MSG = "ramdisk LZ4 block is not the level-12 encoding of the verified debug cpio"
GAP_MSG = "candidate gap between ramdisk and signed tail is not all zero"
TAIL_MSG = "candidate bytes from offset 2121728 differ from the stock signed tail"
SHA_MSG = "candidate SHA-256 is not 3932504a"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, REPEATED)


def check_stock(stock, check_digests=True):
    require(len(stock) == IMAGE_SIZE, STOCK_SIZE_MSG)
    if check_digests:
        require(sha256(stock) == STOCK_SHA256, STOCK_SHA_MSG)
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", stock, 8)
    require(stock[:8] == b"ANDROID!" and kernel_size == 0 and
            ramdisk_size == STOCK_RAMDISK_SIZE and os_version == 0 and
            header_size == HEADER_SIZE and struct.unpack_from("<I", stock, 40)[0] == 4 and
            struct.unpack_from("<I", stock, 1580)[0] == 0 and
            not any(stock[HEADER_SIZE:PAGE]) and
            not any(stock[PAGE + ramdisk_size:TAIL_OFFSET]), STOCK_LAYOUT_MSG)
    stock_frame = stock[PAGE:PAGE + ramdisk_size]
    require(stock_frame[:4] == LZ4_MAGIC and
            struct.unpack_from("<I", stock_frame, 4)[0] == len(stock_frame) - 8,
            STOCK_LAYOUT_MSG)
    footer = stock[FOOTER_OFFSET:]
    require(struct.unpack_from(">4sIIQQQ", footer) ==
            (b"AVBf", 1, 0, TAIL_OFFSET, TAIL_OFFSET, VBMETA_SIZE) and
            not any(footer[36:]), STOCK_FOOTER_MSG)
    require(stock[TAIL_OFFSET:TAIL_OFFSET + 4] == b"AVB0" and
            any(stock[TAIL_OFFSET + 4:TAIL_OFFSET + VBMETA_SIZE]), STOCK_BLOCK_MSG)


def check_gzip(gzip_bytes, check_digests=True):
    require(gzip_bytes[:3] == b"\x1f\x8b\x08", GZIP_MSG)
    try:
        archive = gzip.decompress(gzip_bytes)
    except (OSError, EOFError) as exc:
        raise ValueError(GZIP_MSG) from exc
    require(len(archive) == CPIO_SIZE and sha256(archive) == CPIO_SHA256, CPIO_MSG)
    builder.check_newc(archive)
    if check_digests:
        require(len(gzip_bytes) == GZIP_SIZE, GZIP_SIZE_MSG)
        require(sha256(gzip_bytes) == GZIP_SHA256, GZIP_SHA_MSG)
    return archive


def check_frame(frame, archive, library, check_digests=True):
    require(len(frame) >= 9 and len(frame) <= MAX_FRAME and frame[:4] == LZ4_MAGIC,
            FRAME_MSG)
    block_size = struct.unpack_from("<I", frame, 4)[0]
    require(block_size > 0 and block_size == len(frame) - 8, FRAME_MSG)
    try:
        decoded = builder.decompress(library, frame[8:], len(archive))
    except ValueError as exc:
        raise ValueError(BLOCK_MSG) from exc
    require(decoded == archive, BLOCK_MSG)
    if check_digests:
        require(len(frame) == FRAME_SIZE and block_size == BLOCK_SIZE and
                builder.compress_hc(library, archive, HC_LEVEL) == frame[8:], BLOCK_MSG)


def check_candidate(candidate, stock, gzip_bytes, library, check_digests=True,
                    prior_images=PRIOR_IMAGES, expected=CANDIDATE_SHA256):
    digest = sha256(candidate)
    reject_prior_sha(digest, prior_images)
    check_stock(stock, check_digests)
    archive = check_gzip(gzip_bytes, check_digests)
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET] and
            candidate[RAMDISK_SIZE_OFFSET + 4:PAGE] == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            HEADER_MSG)
    require(struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0] == FRAME_SIZE,
            FIELD_MSG)
    end = PAGE + FRAME_SIZE
    check_frame(candidate[PAGE:end], archive, library, check_digests)
    require(not any(candidate[end:TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)
    if check_digests:
        require(digest == expected, SHA_MSG)
    return digest


def expect_rejection(label, message, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except ValueError as exc:
        require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def patched(image, offset, value):
    mutated = bytearray(image)
    mutated[offset] = value
    return bytes(mutated)


def flipped(image, offset):
    return patched(image, offset, image[offset] ^ 1)


def self_test(candidate, stock, gzip_bytes, library):
    digest = check_candidate(candidate, stock, gzip_bytes, library)
    archive = check_gzip(gzip_bytes)
    frame = candidate[PAGE:PAGE + FRAME_SIZE]
    require(builder.legacy_frame(library, archive) == frame,
            "candidate frame is not the reproducible HC level-12 block")
    print(f"init_boot lz4-debug-ramdisk fixture: OK ({digest})")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, gzip_bytes,
                         library, check_digests=False, prior_images=())

    for offset in (TAIL_OFFSET, TAIL_OFFSET + 100, TAIL_OFFSET + VBMETA_SIZE - 1,
                   TAIL_OFFSET + 5000, FOOTER_OFFSET, IMAGE_SIZE - 1):
        case(f"changed signed tail byte at {offset}", TAIL_MSG, flipped(candidate, offset))
    for offset in (0, 16, 20, 40, 44, PAGE - 1):
        case(f"second changed header field at {offset}", HEADER_MSG, flipped(candidate, offset))
    case("nonempty kernel", KERNEL_MSG, patched(candidate, 8, 1))
    case("wrong ramdisk-size field", FIELD_MSG, patched(candidate, 12, 1))
    case("gzip payload", FRAME_MSG,
         candidate[:PAGE] + gzip_bytes + bytes(FRAME_SIZE - len(gzip_bytes)) +
         candidate[PAGE + FRAME_SIZE:])
    case("modern LZ4 frame magic", FRAME_MSG, patched(candidate, PAGE, 0x04))
    case("changed compressed block", BLOCK_MSG, flipped(candidate, PAGE + 50))
    case("nonzero gap", GAP_MSG, patched(candidate, PAGE + FRAME_SIZE, 1))
    case("short image", SIZE_MSG, candidate[:-4096])
    case("moved signed tail", TAIL_MSG,
         candidate[:TAIL_OFFSET] + bytes(PAGE) + stock[TAIL_OFFSET:IMAGE_SIZE - PAGE])

    def bad_frame(label, message, data):
        expect_rejection(label, message, check_frame, data, archive, library,
                         check_digests=False)

    bad_frame("gzip frame", FRAME_MSG, gzip_bytes)
    bad_frame("modern LZ4 frame", FRAME_MSG, b"\x04\x22\x4d\x18" + frame[4:])
    half = len(archive) // 2
    first = builder.compress_hc(library, archive[:half], HC_LEVEL)
    second = builder.compress_hc(library, archive[half:], HC_LEVEL)
    bad_frame("two LZ4 blocks", FRAME_MSG, LZ4_MAGIC + struct.pack("<I", len(first)) +
              first + struct.pack("<I", len(second)) + second)
    altered = bytearray(archive)
    altered[200] ^= 1
    wrong_block = builder.compress_hc(library, bytes(altered), HC_LEVEL)
    wrong_frame = LZ4_MAGIC + struct.pack("<I", len(wrong_block)) + wrong_block
    bad_frame("block decompresses to different cpio", BLOCK_MSG, wrong_frame)
    bad_frame("truncated LZ4 block", FRAME_MSG, frame[:-1])

    expect_rejection("wrong gzip SHA", GZIP_SHA_MSG, check_gzip,
                     patched(gzip_bytes, 4, gzip_bytes[4] ^ 1))
    expect_rejection("wrong stock SHA", STOCK_SHA_MSG, check_stock, flipped(stock, 100))
    expect_rejection("wrong stock size", STOCK_SIZE_MSG, check_stock,
                     stock[:-PAGE], check_digests=False)
    expect_rejection("moved stock tail offset", STOCK_FOOTER_MSG, check_stock,
                     flipped(stock, FOOTER_OFFSET + 27), check_digests=False)
    expect_rejection("wrong expected SHA", SHA_MSG, check_candidate, candidate, stock,
                     gzip_bytes, library, prior_images=(), expected="0" * 64)
    expect_rejection("repeated candidate SHA", REPEATED, check_candidate, candidate, stock,
                     gzip_bytes, library, prior_images=(digest,))
    for repeated in REQUIRED_PRIOR:
        prior = next((d for d in PRIOR_IMAGES if d.startswith(repeated)), None)
        require(prior is not None, f"missing prior SHA {repeated}")
        expect_rejection(f"repeated {repeated} SHA", REPEATED, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate entry in prior SHA list")
    require(digest not in PRIOR_IMAGES, REPEATED)


def main():
    args = sys.argv[1:]
    library = builder.lz4()
    if args[:1] == ["--self-test"]:
        require(len(args) == 4, "usage: verify-init-boot-lz4-debug-ramdisk.py --self-test "
                "CANDIDATE STOCK_INIT_BOOT GZIP")
        candidate, stock, gzip_bytes = (pathlib.Path(n).read_bytes() for n in args[1:])
        self_test(candidate, stock, gzip_bytes, library)
        return
    if args[:1] == ["--source"]:
        require(len(args) == 3, "usage: verify-init-boot-lz4-debug-ramdisk.py --source "
                "STOCK_INIT_BOOT GZIP")
        stock, gzip_bytes = (pathlib.Path(n).read_bytes() for n in args[1:])
        check_stock(stock)
        archive = check_gzip(gzip_bytes)
        print(f"stock init_boot: {len(stock)} bytes, SHA-256 {sha256(stock)} (baa33fd4)")
        print(f"debug gzip: {len(gzip_bytes)} bytes, SHA-256 {sha256(gzip_bytes)} (caa3eb82)")
        print(f"debug cpio: {len(archive)} bytes, SHA-256 {sha256(archive)}")
        return
    require(len(args) == 3, "usage: verify-init-boot-lz4-debug-ramdisk.py "
            "CANDIDATE STOCK_INIT_BOOT GZIP")
    candidate, stock, gzip_bytes = (pathlib.Path(n).read_bytes() for n in args)
    digest = check_candidate(candidate, stock, gzip_bytes, library)
    print(f"candidate: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"stock: {len(stock)} bytes, SHA-256 {sha256(stock)} (baa33fd4)")
    print(f"header: [0, {PAGE}) stock-identical except ramdisk size at {RAMDISK_SIZE_OFFSET}: "
          f"{STOCK_RAMDISK_SIZE} -> {FRAME_SIZE}; header v4, kernel size 0")
    print(f"ramdisk: [{PAGE}, {PAGE + FRAME_SIZE}), {FRAME_SIZE} bytes; "
          f"Android LZ4 legacy magic 02214c18, one {BLOCK_SIZE}-byte block, HC level {HC_LEVEL}")
    print(f"decompressed cpio: {CPIO_SIZE} bytes, SHA-256 {CPIO_SHA256} (from caa3eb82)")
    print(f"gap: [{PAGE + FRAME_SIZE}, {TAIL_OFFSET}) = "
          f"{TAIL_OFFSET - PAGE - FRAME_SIZE} zero bytes")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, "
          f"including {VBMETA_SIZE}-byte AVB0 and terminal AVBf, identical to stock")
    print("candidate SHA-256 differs from baa33fd4, f4a00ce3, f4b987ee and all prior SHAs")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
