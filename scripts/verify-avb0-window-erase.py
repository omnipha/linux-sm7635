import hashlib
import pathlib
import sys

PARTITION_SIZE = 100663296
PREFIX_SIZE = 13955072
WINDOW_SIZE = 16384
TAIL_OFFSET = PREFIX_SIZE + WINDOW_SIZE
CONTROL_SHA256 = "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450"
STOCK_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
CANDIDATE_SHA256 = "e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f"
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
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
)
REQUIRED_PRIOR = ("968625c7", "db2c635d", "13a48ff9", "6891dc51", "d966172c",
                  "5a513998", "dc990b95", "197aff11")
REPEATED = "candidate SHA-256 repeats a prior image"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reject_prior_sha(digest_hex, prior_boots=PRIOR_BOOTS):
    require(digest_hex not in prior_boots, REPEATED)


def check_candidate(candidate, control, stock, check_digests=True,
                    prior_boots=PRIOR_BOOTS, expected=CANDIDATE_SHA256,
                    window_size=WINDOW_SIZE):
    digest_hex = sha256(candidate)
    reject_prior_sha(digest_hex, prior_boots)
    if check_digests:
        require(sha256(control) == CONTROL_SHA256, "source is not the verified 13a48ff9 control")
        require(sha256(stock) == STOCK_SHA256, "stock reference is not the verified 197aff11 boot_a")
    require(len(control) == PREFIX_SIZE, "source is not 13955072 bytes")
    require(len(stock) == PARTITION_SIZE, "stock reference is not 100663296 bytes")
    require(window_size == WINDOW_SIZE, "erased window is not exactly 16384 bytes")
    require(len(candidate) == PARTITION_SIZE, "output is not 100663296 bytes")
    require(candidate[:PREFIX_SIZE] == control,
            "13955072-byte prefix is not byte-identical to 13a48ff9")
    window_end = PREFIX_SIZE + window_size
    window = candidate[PREFIX_SIZE:window_end]
    require(len(window) == WINDOW_SIZE and not any(window),
            "bytes [13955072, 13971456) are not all zero")
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:],
            "bytes from 13971456 onward differ from stock boot_a 197aff11")
    require(any(stock[PREFIX_SIZE:TAIL_OFFSET]),
            "stock boot_a has no nonzero bytes in the erased window")
    if check_digests:
        require(digest_hex == expected, "candidate SHA-256 is not e7fd2022")
    return digest_hex


def expect_rejection(label, expected, *args, **kwargs):
    try:
        check_candidate(*args, check_digests=False, **kwargs)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def patched(image, offset, value):
    mutated = bytearray(image)
    mutated[offset] = value
    return bytes(mutated)


def self_test(candidate, control, stock):
    digest = check_candidate(candidate, control, stock, prior_boots=())
    print(f"avb0-window-erase fixture: OK ({digest})")
    prefix_msg = "13955072-byte prefix is not byte-identical to 13a48ff9"
    window_msg = "bytes [13955072, 13971456) are not all zero"
    tail_msg = "bytes from 13971456 onward differ from stock boot_a 197aff11"
    size_msg = "output is not 100663296 bytes"
    width_msg = "erased window is not exactly 16384 bytes"
    expect_rejection("changed prefix byte", prefix_msg,
                     patched(candidate, 4096 + 100, candidate[4096 + 100] ^ 1), control, stock)
    expect_rejection("changed last prefix byte", prefix_msg,
                     patched(candidate, PREFIX_SIZE - 1, candidate[PREFIX_SIZE - 1] ^ 1),
                     control, stock)
    expect_rejection("nonzero first window byte", window_msg,
                     patched(candidate, PREFIX_SIZE, 1), control, stock)
    expect_rejection("nonzero last window byte", window_msg,
                     patched(candidate, TAIL_OFFSET - 1, 1), control, stock)
    expect_rejection("changed first signed-tail byte", tail_msg,
                     patched(candidate, TAIL_OFFSET, candidate[TAIL_OFFSET] ^ 1), control, stock)
    expect_rejection("changed last signed-tail byte", tail_msg,
                     patched(candidate, PARTITION_SIZE - 1, candidate[PARTITION_SIZE - 1] ^ 1),
                     control, stock)
    zero_before = candidate[:PREFIX_SIZE] + bytes(WINDOW_SIZE // 2) + candidate[TAIL_OFFSET:]
    expect_rejection("window of half size", width_msg, zero_before, control, stock,
                     window_size=WINDOW_SIZE // 2)
    expect_rejection("window of half size, unlabelled", size_msg, zero_before, control, stock)
    wide = (candidate[:PREFIX_SIZE] + bytes(WINDOW_SIZE + 4096) + candidate[TAIL_OFFSET:])
    expect_rejection("window of 20480 bytes", width_msg, wide, control, stock,
                     window_size=WINDOW_SIZE + 4096)
    expect_rejection("window of 20480 bytes, unlabelled", size_msg, wide, control, stock)
    wide_same_size = (candidate[:PREFIX_SIZE] + bytes(WINDOW_SIZE + 4096) +
                      candidate[TAIL_OFFSET + 4096:])
    expect_rejection("window of 20480 bytes, same length", width_msg, wide_same_size,
                     control, stock, window_size=WINDOW_SIZE + 4096)
    narrow_same_size = (candidate[:PREFIX_SIZE] + bytes(WINDOW_SIZE - 4096) +
                        stock[TAIL_OFFSET - 4096:])
    expect_rejection("window of 12288 bytes, same length", width_msg, narrow_same_size,
                     control, stock, window_size=WINDOW_SIZE - 4096)
    expect_rejection("zero-length window", width_msg, candidate, control, stock, window_size=0)
    expect_rejection("short image", size_msg, candidate[:-4096], control, stock)
    for label, image in (("968625c7 overlay", control + stock[PREFIX_SIZE:]),
                         ("stock 197aff11", stock), ("control 13a48ff9", control)):
        digest_prior = sha256(image)
        try:
            check_candidate(image, control, stock, check_digests=False,
                            prior_boots=(digest_prior,))
        except ValueError as exc:
            require(str(exc) == REPEATED, f"{label}: unexpected failure: {exc}")
            print(f"expected repeated {label} SHA failure: {exc}")
        else:
            raise ValueError(f"repeated {label} SHA was accepted")
    try:
        check_candidate(candidate, control, stock, check_digests=False, prior_boots=(digest,))
    except ValueError as exc:
        require(str(exc) == REPEATED, f"unexpected failure: {exc}")
        print(f"expected repeated prior SHA failure: {exc}")
    else:
        raise ValueError("repeated prior SHA fixture was accepted")
    for repeated in REQUIRED_PRIOR:
        prior = next((d for d in PRIOR_BOOTS if d.startswith(repeated)), None)
        require(prior is not None, f"missing prior SHA {repeated}")
        try:
            reject_prior_sha(prior)
        except ValueError as exc:
            require(str(exc) == REPEATED, f"{repeated}: unexpected failure: {exc}")
            print(f"expected repeated {repeated} SHA failure: {exc}")
        else:
            raise ValueError(f"repeated {repeated} SHA was accepted")
    require(CANDIDATE_SHA256 not in PRIOR_BOOTS, "candidate SHA-256 is listed as a prior image")
    overlay = control + stock[PREFIX_SIZE:]
    require(sha256(overlay) == next(d for d in PRIOR_BOOTS if d.startswith("968625c7")),
            "reconstructed stock-tail overlay is not 968625c7")
    require(len(overlay) == PARTITION_SIZE, "stock-tail overlay is not 100663296 bytes")
    print("stock-tail overlay reconstructed in memory only: 968625c7 (not written, not packaged)")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        require(len(args) == 4,
                "usage: verify-avb0-window-erase.py --self-test CANDIDATE CONTROL STOCK_BOOT")
        blobs = [pathlib.Path(name).read_bytes() for name in args[1:]]
        require(sha256(blobs[0]) == CANDIDATE_SHA256, "self-test candidate is not e7fd2022")
        self_test(*blobs)
        return
    require(len(args) == 3, "usage: verify-avb0-window-erase.py CANDIDATE CONTROL STOCK_BOOT")
    candidate, control, stock = (pathlib.Path(n).read_bytes() for n in args)
    digest = check_candidate(candidate, control, stock)
    print(f"candidate: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"prefix: {PREFIX_SIZE} bytes byte-identical to 13a48ff9")
    print(f"window: [{PREFIX_SIZE}, {TAIL_OFFSET}) = {WINDOW_SIZE} bytes, every byte zero "
          "(stock holds the standalone AVB0 record there)")
    print(f"signed tail: {PARTITION_SIZE - TAIL_OFFSET} bytes from offset {TAIL_OFFSET} "
          "byte-identical to stock boot_a 197aff11")
    print("candidate SHA-256 differs from 968625c7, db2c635d, 13a48ff9, 6891dc51, d966172c, "
          "5a513998, dc990b95 and 197aff11")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
