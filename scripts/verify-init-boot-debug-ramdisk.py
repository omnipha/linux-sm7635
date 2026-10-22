import gzip
import hashlib
import pathlib
import struct
import sys

PAGE = 4096
IMAGE_SIZE = 8388608
HEADER_SIZE = 1584
RAMDISK_SIZE_OFFSET = 12
TAIL_OFFSET = 2121728
VBMETA_SIZE = 832
FOOTER_OFFSET = IMAGE_SIZE - 64
STOCK_RAMDISK_SIZE = 2113581
RAMDISK_SIZE = 1672600
STOCK_SHA256 = "baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193"
RAMDISK_SHA256 = "caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f"
CANDIDATE_SHA256 = "f4a00ce3a1926f9b54eaa958158691efaabe90a9ea715d2bac3d424095f2f948"
PRIOR_IMAGES = (
    "baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193",
    "f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89",
    "bde3a3b3bc7ea587f195de63de76db5f14f8dfd197d6d3224904f722af18fd31",
    "6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d",
    "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253",
    "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
    "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a",
    "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce",
    "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7",
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "968625c761b8d8d8c35aafc30b86919aa03d51d1f82c7956b4d714df42e530fc",
    "db2c635d5c51aed47cf6a626244bba5be6e6eeb240f0dd2d0ed0e72d85fdff00",
    "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450",
    "6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555",
    "d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131",
    "5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b",
    "dc990b9517d53431fcaeebb2b0498e6e64d3e7cbbc7e469d3e0bfc73abe00075",
    "e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f",
    "7c409cdefe9e0f24cbe53e44d5bbab8ff50adadb9fbfb26d64917fe1a6fc4ddf",
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
)
REQUIRED_PRIOR = ("baa33fd4", "f4b987ee", "bde3a3b3", "6078269d", "23725940",
                  "5e866c54", "84f7f5ea", "116b1662", "1fdc2570", "55fa78ca",
                  "968625c7", "db2c635d", "13a48ff9", "6891dc51", "d966172c",
                  "5a513998", "dc990b95", "e7fd2022", "7c409cde", "197aff11")

REPEATED = "candidate SHA-256 repeats a prior image"
STOCK_SIZE_MSG = "stock init_boot is not 8388608 bytes"
STOCK_SHA_MSG = "stock init_boot is not the verified baa33fd4 slot-A reference"
STOCK_LAYOUT_MSG = ("stock init_boot is not header v4 with an empty kernel, a 2113581-byte "
                    "lz4 ramdisk, zero header padding and zero gap before the signed tail")
STOCK_FOOTER_MSG = ("stock AVBf footer magic, version, original size, vbmeta offset or vbmeta "
                    "size is not the verified value")
STOCK_BLOCK_MSG = "stock signed vbmeta block is not a nonzero 832-byte AVB0 block"
RAMDISK_SIZE_MSG = "debug ramdisk is not 1672600 bytes"
RAMDISK_SHA_MSG = "debug ramdisk is not the verified caa3eb82 gzip cpio"
RAMDISK_GZIP_MSG = "ramdisk is not a gzip stream"
RAMDISK_NEWC_MSG = "ramdisk is not a newc cpio archive ending in TRAILER!!!"
SIZE_MSG = "candidate is not 8388608 bytes"
HEADER_MSG = "candidate header page differs from stock beyond the ramdisk-size field"
FIELD_MSG = "candidate ramdisk-size field is not the debug ramdisk size"
KERNEL_MSG = "candidate init_boot kernel is not empty"
RAMDISK_BYTES_MSG = "candidate ramdisk bytes are not the verified debug gzip cpio"
GAP_MSG = "candidate gap between the ramdisk and the signed tail is not all zero"
TAIL_MSG = "candidate bytes from offset 2121728 differ from the stock signed tail"
SHA_MSG = "candidate SHA-256 is not f4a00ce3"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reject_prior_sha(digest_hex, prior_images=PRIOR_IMAGES):
    require(digest_hex not in prior_images, REPEATED)


def check_newc(archive):
    pos = 0
    names = []
    while True:
        require(pos + 110 <= len(archive) and archive[pos:pos + 6] == b"070701",
                RAMDISK_NEWC_MSG)
        try:
            fields = [int(archive[pos + 6 + 8 * i:pos + 14 + 8 * i], 16) for i in range(13)]
        except ValueError as exc:
            raise ValueError(RAMDISK_NEWC_MSG) from exc
        filesize, namesize = fields[6], fields[11]
        name_end = pos + 110 + namesize
        require(namesize > 0 and name_end <= len(archive) and archive[name_end - 1] == 0,
                RAMDISK_NEWC_MSG)
        name = archive[pos + 110:name_end - 1]
        data_start = (name_end + 3) // 4 * 4
        pos = (data_start + filesize + 3) // 4 * 4
        require(pos <= len(archive), RAMDISK_NEWC_MSG)
        if name == b"TRAILER!!!":
            require(filesize == 0, RAMDISK_NEWC_MSG)
            break
        names.append(name)
    require(names and not any(archive[pos:]), RAMDISK_NEWC_MSG)
    return names


def check_ramdisk(ramdisk, check_digests=True):
    require(ramdisk[:3] == b"\x1f\x8b\x08", RAMDISK_GZIP_MSG)
    try:
        archive = gzip.decompress(ramdisk)
    except (OSError, EOFError) as exc:
        raise ValueError(RAMDISK_GZIP_MSG) from exc
    check_newc(archive)
    if check_digests:
        require(len(ramdisk) == RAMDISK_SIZE, RAMDISK_SIZE_MSG)
        require(sha256(ramdisk) == RAMDISK_SHA256, RAMDISK_SHA_MSG)


def check_stock(stock, check_digests=True):
    require(len(stock) == IMAGE_SIZE, STOCK_SIZE_MSG)
    if check_digests:
        require(sha256(stock) == STOCK_SHA256, STOCK_SHA_MSG)
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", stock, 8)
    version = struct.unpack_from("<I", stock, 40)[0]
    signature = struct.unpack_from("<I", stock, 1580)[0]
    require(stock[:8] == b"ANDROID!" and kernel_size == 0 and ramdisk_size == STOCK_RAMDISK_SIZE
            and os_version == 0 and header_size == HEADER_SIZE and version == 4 and
            signature == 0 and not any(stock[HEADER_SIZE:PAGE]) and
            not any(stock[PAGE + ramdisk_size:TAIL_OFFSET]), STOCK_LAYOUT_MSG)
    require(stock[PAGE:PAGE + 4] == b"\x02\x21\x4c\x18" and
            any(stock[PAGE + 4:PAGE + ramdisk_size]), STOCK_LAYOUT_MSG)
    footer = stock[FOOTER_OFFSET:]
    magic, major, minor, original, offset, size = struct.unpack_from(">4sIIQQQ", footer)
    require((magic, major, minor, original, offset, size) ==
            (b"AVBf", 1, 0, TAIL_OFFSET, TAIL_OFFSET, VBMETA_SIZE), STOCK_FOOTER_MSG)
    require(not any(footer[36:]), STOCK_FOOTER_MSG)
    require(stock[TAIL_OFFSET:TAIL_OFFSET + 4] == b"AVB0" and
            any(stock[TAIL_OFFSET + 4:TAIL_OFFSET + VBMETA_SIZE]), STOCK_BLOCK_MSG)


def derive(stock, ramdisk):
    header = bytearray(stock[:PAGE])
    struct.pack_into("<I", header, RAMDISK_SIZE_OFFSET, len(ramdisk))
    gap = TAIL_OFFSET - PAGE - len(ramdisk)
    require(gap >= 0, "debug ramdisk does not fit before the signed tail")
    return bytes(header) + ramdisk + bytes(gap) + stock[TAIL_OFFSET:]


def check_candidate(candidate, stock, ramdisk, check_digests=True,
                    prior_images=PRIOR_IMAGES, expected=CANDIDATE_SHA256):
    digest_hex = sha256(candidate)
    reject_prior_sha(digest_hex, prior_images)
    check_stock(stock, check_digests)
    check_ramdisk(ramdisk, check_digests)
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET] and
            candidate[RAMDISK_SIZE_OFFSET + 4:PAGE] == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            HEADER_MSG)
    require(struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0] == len(ramdisk),
            FIELD_MSG)
    end = PAGE + len(ramdisk)
    require(candidate[PAGE:end] == ramdisk, RAMDISK_BYTES_MSG)
    require(not any(candidate[end:TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)
    if check_digests:
        require(digest_hex == expected, SHA_MSG)
    return digest_hex


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


def self_test(candidate, stock, ramdisk):
    digest = check_candidate(candidate, stock, ramdisk, prior_images=())
    print(f"init_boot debug-ramdisk fixture: OK ({digest})")
    require(derive(stock, ramdisk) == candidate,
            "candidate is not the stock image with only the ramdisk size, ramdisk and gap changed")
    end = PAGE + len(ramdisk)

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, ramdisk,
                         check_digests=False, prior_images=())

    case("changed first tail byte", TAIL_MSG, flipped(candidate, TAIL_OFFSET))
    case("changed signed vbmeta block byte", TAIL_MSG, flipped(candidate, TAIL_OFFSET + 100))
    case("changed last vbmeta block byte", TAIL_MSG,
         flipped(candidate, TAIL_OFFSET + VBMETA_SIZE - 1))
    case("changed tail gap byte", TAIL_MSG, patched(candidate, TAIL_OFFSET + 5000, 1))
    case("changed AVBf footer byte", TAIL_MSG, flipped(candidate, FOOTER_OFFSET + 20))
    case("changed last footer byte", TAIL_MSG, patched(candidate, IMAGE_SIZE - 1, 1))
    case("second changed header field (os version)", HEADER_MSG, patched(candidate, 16, 1))
    case("second changed header field (header version)", HEADER_MSG, patched(candidate, 40, 3))
    case("second changed header field (header size)", HEADER_MSG, patched(candidate, 21, 0x07))
    case("second changed header field (cmdline)", HEADER_MSG, patched(candidate, 44, 0x41))
    case("second changed header field (header padding)", HEADER_MSG,
         patched(candidate, PAGE - 1, 1))
    case("second changed header field (magic)", HEADER_MSG, patched(candidate, 0, 0))
    case("nonempty kernel", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 4096) + candidate[12:])
    case("ramdisk-size field left at stock value", FIELD_MSG,
         candidate[:12] + struct.pack("<I", STOCK_RAMDISK_SIZE) + candidate[16:])
    case("ramdisk-size field short by one", FIELD_MSG,
         candidate[:12] + struct.pack("<I", len(ramdisk) - 1) + candidate[16:])
    case("changed ramdisk byte", RAMDISK_BYTES_MSG, flipped(candidate, PAGE + 100))
    case("changed last ramdisk byte", RAMDISK_BYTES_MSG, flipped(candidate, end - 1))
    case("nonzero first gap byte", GAP_MSG, patched(candidate, end, 1))
    case("nonzero last gap byte", GAP_MSG, patched(candidate, TAIL_OFFSET - 1, 1))
    case("stale stock ramdisk bytes in gap", GAP_MSG,
         candidate[:end] + stock[end:TAIL_OFFSET] + candidate[TAIL_OFFSET:])
    case("short image", SIZE_MSG, candidate[:-4096])
    case("image one footer short", SIZE_MSG, candidate[:-64])
    case("long image", SIZE_MSG, candidate + bytes(4096))
    case("empty image", SIZE_MSG, b"")

    stock_lz4 = stock[PAGE:PAGE + STOCK_RAMDISK_SIZE]
    expect_rejection("stock lz4 ramdisk payload", RAMDISK_GZIP_MSG, check_ramdisk, stock_lz4,
                     check_digests=False)
    swapped = bytearray(ramdisk)
    swapped[0] = 0x04
    expect_rejection("non-gzip ramdisk magic", RAMDISK_GZIP_MSG, check_ramdisk, bytes(swapped),
                     check_digests=False)
    expect_rejection("non-gzip ramdisk in candidate", RAMDISK_GZIP_MSG, check_candidate,
                     patched(candidate, PAGE, 0x04), stock, bytes(swapped),
                     check_digests=False, prior_images=())
    plain = b"070701" + b"0" * 104 + b"TRAILER!!!\0"
    expect_rejection("plain cpio ramdisk", RAMDISK_GZIP_MSG, check_ramdisk, plain,
                     check_digests=False)
    nonarchive = gzip.compress(b"not a cpio archive" * 20, mtime=0)
    expect_rejection("gzip of non-cpio", RAMDISK_NEWC_MSG, check_ramdisk, nonarchive,
                     check_digests=False)
    truncated = gzip.compress(gzip.decompress(ramdisk)[:1024], mtime=0)[:-9]
    expect_rejection("truncated gzip", RAMDISK_GZIP_MSG, check_ramdisk, truncated,
                     check_digests=False)
    expect_rejection("wrong ramdisk size", RAMDISK_SIZE_MSG, check_ramdisk,
                     gzip.compress(gzip.decompress(ramdisk), mtime=0, compresslevel=1))
    expect_rejection("wrong ramdisk SHA", RAMDISK_SHA_MSG, check_ramdisk,
                     patched(ramdisk, 4, ramdisk[4] ^ 1), check_digests=True)
    expect_rejection("wrong stock SHA", STOCK_SHA_MSG, check_stock, flipped(stock, 100))
    expect_rejection("short stock reference", STOCK_SIZE_MSG, check_stock, stock[:-4096],
                     check_digests=False)
    expect_rejection("stock with changed ramdisk size", STOCK_LAYOUT_MSG, check_stock,
                     stock[:12] + struct.pack("<I", 1) + stock[16:], check_digests=False)
    expect_rejection("stock with nonzero gap", STOCK_LAYOUT_MSG, check_stock,
                     patched(stock, TAIL_OFFSET - 1, 1), check_digests=False)
    expect_rejection("stock footer original size", STOCK_FOOTER_MSG, check_stock,
                     flipped(stock, FOOTER_OFFSET + 19), check_digests=False)
    expect_rejection("stock footer vbmeta size", STOCK_FOOTER_MSG, check_stock,
                     flipped(stock, FOOTER_OFFSET + 31), check_digests=False)
    expect_rejection("stock signed block magic", STOCK_BLOCK_MSG, check_stock,
                     patched(stock, TAIL_OFFSET, 0), check_digests=False)
    expect_rejection("incorrect SHA", SHA_MSG, check_candidate, candidate, stock, ramdisk,
                     prior_images=(), expected="0" * 64)
    expect_rejection("repeated candidate SHA", REPEATED, check_candidate, candidate, stock,
                     ramdisk, check_digests=False, prior_images=(digest,))
    for repeated in REQUIRED_PRIOR:
        prior = next((d for d in PRIOR_IMAGES if d.startswith(repeated)), None)
        require(prior is not None, f"missing prior SHA {repeated}")
        expect_rejection(f"repeated {repeated} SHA", REPEATED, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate entry in prior SHA list")
    require(CANDIDATE_SHA256 not in PRIOR_IMAGES, "candidate SHA-256 is listed as a prior image")
    require(digest == CANDIDATE_SHA256, SHA_MSG)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        require(len(args) == 4, "usage: verify-init-boot-debug-ramdisk.py --self-test "
                "CANDIDATE STOCK_INIT_BOOT RAMDISK")
        blobs = [pathlib.Path(name).read_bytes() for name in args[1:]]
        require(sha256(blobs[0]) == CANDIDATE_SHA256, "self-test candidate is not f4a00ce3")
        self_test(*blobs)
        return
    if args[:1] == ["--source"]:
        require(len(args) == 3,
                "usage: verify-init-boot-debug-ramdisk.py --source STOCK_INIT_BOOT RAMDISK")
        stock, ramdisk = (pathlib.Path(n).read_bytes() for n in args[1:])
        check_stock(stock)
        check_ramdisk(ramdisk)
        print(f"stock init_boot: {len(stock)} bytes, SHA-256 {sha256(stock)} (baa33fd4)")
        print(f"debug ramdisk: {len(ramdisk)} bytes, SHA-256 {sha256(ramdisk)} (caa3eb82)")
        return
    require(len(args) == 3,
            "usage: verify-init-boot-debug-ramdisk.py CANDIDATE STOCK_INIT_BOOT RAMDISK")
    candidate, stock, ramdisk = (pathlib.Path(n).read_bytes() for n in args)
    digest = check_candidate(candidate, stock, ramdisk)
    names = check_newc(gzip.decompress(ramdisk))
    end = PAGE + len(ramdisk)
    print(f"candidate: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"stock: {len(stock)} bytes, SHA-256 {sha256(stock)} (baa33fd4)")
    print(f"header: bytes [0, {PAGE}) identical to stock except the ramdisk-size field at "
          f"offset {RAMDISK_SIZE_OFFSET} ({STOCK_RAMDISK_SIZE} -> {len(ramdisk)}); header v4, "
          "kernel size 0")
    print(f"ramdisk: {len(ramdisk)} bytes at [{PAGE}, {end}), SHA-256 {sha256(ramdisk)} "
          f"(caa3eb82), gzip newc cpio with {len(names)} entries")
    print(f"gap: [{end}, {TAIL_OFFSET}) = {TAIL_OFFSET - end} bytes, every byte zero")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from offset {TAIL_OFFSET} "
          f"(AVB0 {VBMETA_SIZE} bytes through terminal AVBf) identical to stock init_boot "
          "baa33fd4")
    print("candidate SHA-256 differs from baa33fd4, f4b987ee and every prior boot SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
