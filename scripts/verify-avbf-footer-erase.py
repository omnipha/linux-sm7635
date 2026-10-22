import hashlib
import pathlib
import struct
import sys

PARTITION_SIZE = 100663296
PREFIX_SIZE = 13955072
WINDOW_SIZE = 16384
TAIL_OFFSET = PREFIX_SIZE + WINDOW_SIZE
FOOTER_SIZE = 64
FOOTER_OFFSET = PARTITION_SIZE - FOOTER_SIZE
VBMETA_SIZE = 2496
PREFIX_SHA256 = "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450"
STOCK_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
SOURCE_SHA256 = "e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f"
CANDIDATE_SHA256 = "7c409cdefe9e0f24cbe53e44d5bbab8ff50adadb9fbfb26d64917fe1a6fc4ddf"
PRIOR_BOOTS = (
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
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
)
REQUIRED_PRIOR = ("e7fd2022", "db2c635d", "6891dc51", "13a48ff9", "968625c7",
                  "d966172c", "5a513998", "dc990b95", "197aff11")
REPEATED = "candidate SHA-256 repeats a prior image"
SOURCE_SIZE_MSG = "source is not 100663296 bytes"
SOURCE_SHA_MSG = "source SHA-256 is not e7fd2022"
STOCK_SIZE_MSG = "stock reference is not 100663296 bytes"
STOCK_SHA_MSG = "stock reference is not the verified 197aff11 boot_a"
PREFIX_MSG = "13955072-byte source prefix is not the verified 13a48ff9 control"
WINDOW_MSG = "source bytes [13955072, 13971456) are not all zero"
SIGNED_MSG = "source bytes from 13971456 onward differ from stock boot_a 197aff11"
STOCK_WINDOW_MSG = "stock boot_a has no nonzero bytes in the erased AVB0 window"
STOCK_FOOTER_MSG = ("stock AVBf footer magic, version, original size, vbmeta offset or vbmeta "
                    "size is not the verified value")
STOCK_BLOCK_MSG = "stock signed vbmeta block is not a 2496-byte AVB0 block followed by zeros"
SOURCE_FOOTER_MSG = "source footer is not the nonzero stock AVBf footer"
SIZE_MSG = "output is not 100663296 bytes"
BEFORE_MSG = "bytes before offset 100663232 are not byte-identical to source e7fd2022"
ZERO_MSG = "final 64 bytes [100663232, 100663296) are not all zero"
SHA_MSG = "candidate SHA-256 is not 7c409cde"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reject_prior_sha(digest_hex, prior_boots=PRIOR_BOOTS):
    require(digest_hex not in prior_boots, REPEATED)


def check_stock(stock, check_digests=True):
    require(len(stock) == PARTITION_SIZE, STOCK_SIZE_MSG)
    if check_digests:
        require(sha256(stock) == STOCK_SHA256, STOCK_SHA_MSG)
    require(any(stock[PREFIX_SIZE:TAIL_OFFSET]), STOCK_WINDOW_MSG)
    footer = stock[FOOTER_OFFSET:]
    magic, major, minor, original, offset, size = struct.unpack_from(">4sIIQQQ", footer)
    require((magic, major, minor, original, offset, size) ==
            (b"AVBf", 1, 0, TAIL_OFFSET, TAIL_OFFSET, VBMETA_SIZE), STOCK_FOOTER_MSG)
    require(not any(footer[36:]), STOCK_FOOTER_MSG)
    block = stock[offset:offset + size]
    require(block[:4] == b"AVB0" and any(block[4:]) and
            not any(stock[offset + size:FOOTER_OFFSET]), STOCK_BLOCK_MSG)


def check_source(source, stock, check_digests=True):
    require(len(source) == PARTITION_SIZE, SOURCE_SIZE_MSG)
    if check_digests:
        require(sha256(source) == SOURCE_SHA256, SOURCE_SHA_MSG)
    check_stock(stock, check_digests)
    require(sha256(source[:PREFIX_SIZE]) == PREFIX_SHA256, PREFIX_MSG)
    require(not any(source[PREFIX_SIZE:TAIL_OFFSET]), WINDOW_MSG)
    require(source[TAIL_OFFSET:] == stock[TAIL_OFFSET:], SIGNED_MSG)
    require(any(source[FOOTER_OFFSET:]), SOURCE_FOOTER_MSG)


def check_candidate(candidate, source, stock, check_digests=True,
                    prior_boots=PRIOR_BOOTS, expected=CANDIDATE_SHA256):
    digest_hex = sha256(candidate)
    reject_prior_sha(digest_hex, prior_boots)
    check_source(source, stock, check_digests)
    require(len(candidate) == PARTITION_SIZE, SIZE_MSG)
    require(candidate[:FOOTER_OFFSET] == source[:FOOTER_OFFSET], BEFORE_MSG)
    footer = candidate[FOOTER_OFFSET:]
    require(len(footer) == FOOTER_SIZE and not any(footer), ZERO_MSG)
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


def derive(source):
    return source[:FOOTER_OFFSET] + bytes(FOOTER_SIZE)


def self_test(candidate, source, stock):
    digest = check_candidate(candidate, source, stock, prior_boots=())
    print(f"avbf-footer-erase fixture: OK ({digest})")
    require(derive(source) == candidate, "candidate is not the source with only the footer zeroed")

    def source_case(label, expected, mutated, **kwargs):
        expect_rejection(label, expected, check_source, mutated, stock, **kwargs)
        expect_rejection(label + " via candidate", expected, check_candidate,
                         derive(mutated), mutated, stock, prior_boots=(), **kwargs)

    source_case("wrong source SHA", SOURCE_SHA_MSG, patched(source, 100, source[100] ^ 1))
    source_case("short source length", SOURCE_SIZE_MSG, source[:-4096])
    source_case("long source length", SOURCE_SIZE_MSG, source + bytes(4096))
    expect_rejection("short stock reference", STOCK_SIZE_MSG, check_source, source, stock[:-4096])
    expect_rejection("wrong stock SHA", STOCK_SHA_MSG, check_source, source,
                     patched(stock, 100, stock[100] ^ 1))
    nocheck = {"check_digests": False}
    source_case("changed source prefix byte", PREFIX_MSG,
                patched(source, 4096 + 100, source[4096 + 100] ^ 1), **nocheck)
    source_case("changed last source prefix byte", PREFIX_MSG,
                patched(source, PREFIX_SIZE - 1, source[PREFIX_SIZE - 1] ^ 1), **nocheck)
    source_case("changed first erased AVB0 window byte", WINDOW_MSG,
                patched(source, PREFIX_SIZE, 1), **nocheck)
    source_case("changed last erased AVB0 window byte", WINDOW_MSG,
                patched(source, TAIL_OFFSET - 1, 1), **nocheck)
    source_case("changed first signed vbmeta block byte", SIGNED_MSG,
                patched(source, TAIL_OFFSET, source[TAIL_OFFSET] ^ 1), **nocheck)
    source_case("changed signed vbmeta block byte", SIGNED_MSG,
                patched(source, TAIL_OFFSET + 1000, source[TAIL_OFFSET + 1000] ^ 1), **nocheck)
    source_case("changed last signed vbmeta block byte", SIGNED_MSG,
                patched(source, TAIL_OFFSET + VBMETA_SIZE - 1,
                        source[TAIL_OFFSET + VBMETA_SIZE - 1] ^ 1), **nocheck)
    source_case("changed gap byte after signed block", SIGNED_MSG,
                patched(source, TAIL_OFFSET + VBMETA_SIZE, 1), **nocheck)
    source_case("changed source footer byte", SIGNED_MSG,
                patched(source, FOOTER_OFFSET + 4, source[FOOTER_OFFSET + 4] ^ 1), **nocheck)
    zero_footer_stock = derive(stock)
    expect_rejection("zero footer in stock reference", STOCK_FOOTER_MSG, check_stock,
                     zero_footer_stock, check_digests=False)
    expect_rejection("wrong stock footer original size", STOCK_FOOTER_MSG, check_stock,
                     patched(stock, FOOTER_OFFSET + 19, stock[FOOTER_OFFSET + 19] ^ 1),
                     check_digests=False)
    expect_rejection("wrong stock footer vbmeta size", STOCK_FOOTER_MSG, check_stock,
                     patched(stock, FOOTER_OFFSET + 31, stock[FOOTER_OFFSET + 31] ^ 1),
                     check_digests=False)
    expect_rejection("stock signed block magic", STOCK_BLOCK_MSG, check_stock,
                     patched(stock, TAIL_OFFSET, 0), check_digests=False)

    def candidate_case(label, expected, mutated):
        expect_rejection(label, expected, check_candidate, mutated, source, stock,
                         prior_boots=())

    candidate_case("changed candidate prefix byte", BEFORE_MSG,
                   patched(candidate, 4096 + 100, candidate[4096 + 100] ^ 1))
    candidate_case("changed candidate erased AVB0 window byte", BEFORE_MSG,
                   patched(candidate, PREFIX_SIZE + 5, 1))
    candidate_case("changed candidate signed vbmeta block byte", BEFORE_MSG,
                   patched(candidate, TAIL_OFFSET + 100, candidate[TAIL_OFFSET + 100] ^ 1))
    candidate_case("one-byte change in zero gap before footer", BEFORE_MSG,
                   patched(candidate, FOOTER_OFFSET - 1, 1))
    candidate_case("one-byte change at middle of gap", BEFORE_MSG,
                   patched(candidate, 50000000, 1))
    candidate_case("changed final byte before the footer", BEFORE_MSG,
                   patched(candidate, FOOTER_OFFSET - 1, 0xff))
    candidate_case("nonzero first output-footer byte", ZERO_MSG,
                   patched(candidate, FOOTER_OFFSET, 1))
    candidate_case("nonzero output-footer byte", ZERO_MSG,
                   patched(candidate, FOOTER_OFFSET + 31, 1))
    candidate_case("nonzero last output-footer byte", ZERO_MSG,
                   patched(candidate, PARTITION_SIZE - 1, 1))
    candidate_case("short output", SIZE_MSG, candidate[:-4096])
    candidate_case("output one footer short", SIZE_MSG, candidate[:-FOOTER_SIZE])
    candidate_case("long output", SIZE_MSG, candidate + bytes(64))
    candidate_case("unerased footer (source unchanged)", ZERO_MSG, source)
    expect_rejection("incorrect SHA", SHA_MSG, check_candidate, candidate, source, stock,
                     prior_boots=(), expected="0" * 64)
    expect_rejection("repeated candidate SHA", REPEATED, check_candidate, candidate, source,
                     stock, prior_boots=(digest,))
    for label, image in (("source e7fd2022", source), ("stock 197aff11", stock)):
        expect_rejection(f"candidate equals {label}", REPEATED, check_candidate, image,
                         source, stock)
    for repeated in REQUIRED_PRIOR:
        prior = next((d for d in PRIOR_BOOTS if d.startswith(repeated)), None)
        require(prior is not None, f"missing prior SHA {repeated}")
        expect_rejection(f"repeated {repeated} SHA", REPEATED, reject_prior_sha, prior)
    require(CANDIDATE_SHA256 not in PRIOR_BOOTS, "candidate SHA-256 is listed as a prior image")
    require(digest == CANDIDATE_SHA256, SHA_MSG)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        require(len(args) == 4,
                "usage: verify-avbf-footer-erase.py --self-test CANDIDATE SOURCE STOCK_BOOT")
        blobs = [pathlib.Path(name).read_bytes() for name in args[1:]]
        require(sha256(blobs[0]) == CANDIDATE_SHA256, "self-test candidate is not 7c409cde")
        self_test(*blobs)
        return
    if args[:1] == ["--source"]:
        require(len(args) == 3, "usage: verify-avbf-footer-erase.py --source SOURCE STOCK_BOOT")
        source, stock = (pathlib.Path(n).read_bytes() for n in args[1:])
        check_source(source, stock)
        print(f"source: {len(source)} bytes, SHA-256 {sha256(source)} (e7fd2022)")
        return
    require(len(args) == 3, "usage: verify-avbf-footer-erase.py CANDIDATE SOURCE STOCK_BOOT")
    candidate, source, stock = (pathlib.Path(n).read_bytes() for n in args)
    digest = check_candidate(candidate, source, stock)
    footer = stock[FOOTER_OFFSET:]
    original, offset, size = struct.unpack_from(">QQQ", footer, 12)
    print(f"candidate: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"source: SHA-256 {sha256(source)} (e7fd2022), {len(source)} bytes")
    print(f"prefix: first {PREFIX_SIZE} bytes of source are the verified 13a48ff9 control")
    print(f"AVB0 window: [{PREFIX_SIZE}, {TAIL_OFFSET}) = {WINDOW_SIZE} bytes, every byte zero")
    print(f"signed block: {size} bytes at {offset} (AVB0), identical to stock boot_a 197aff11; "
          f"stock AVBf footer: version 1.0, original size {original}, vbmeta offset {offset}, "
          f"vbmeta size {size}")
    print(f"bytes [0, {FOOTER_OFFSET}) are byte-identical to source e7fd2022")
    print(f"bytes [{FOOTER_OFFSET}, {PARTITION_SIZE}) = {FOOTER_SIZE} bytes, every byte zero "
          "(stock AVBf footer erased)")
    print("candidate SHA-256 differs from e7fd2022, db2c635d, 6891dc51, 13a48ff9, 968625c7, "
          "d966172c, 5a513998, dc990b95 and 197aff11")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
