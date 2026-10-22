import hashlib
import pathlib
import sys

PARTITION_SIZE = 100663296
PREFIX_SIZE = 13955072
TAIL_SIZE = PARTITION_SIZE - PREFIX_SIZE
CONTROL_SHA256 = "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450"
FOOTER_SHA256 = "6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555"
CANDIDATE_SHA256 = "db2c635d5c51aed47cf6a626244bba5be6e6eeb240f0dd2d0ed0e72d85fdff00"
PRIOR_BOOTS = (
    "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
    "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a",
    "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce",
    "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7",
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450",
    "d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131",
    "5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b",
    "dc990b9517d53431fcaeebb2b0498e6e64d3e7cbbc7e469d3e0bfc73abe00075",
    "6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555",
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
)
REQUIRED_PRIOR = ("6891dc51", "13a48ff9", "d966172c", "5a513998", "dc990b95", "197aff11")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_candidate(candidate, control, footer_image, check_digests=True,
                    prior_boots=PRIOR_BOOTS, expected=CANDIDATE_SHA256):
    digest_hex = sha256(candidate)
    require(digest_hex not in prior_boots, "candidate SHA-256 repeats a prior image")
    if check_digests:
        require(sha256(control) == CONTROL_SHA256, "source is not the verified 13a48ff9 control")
        require(sha256(footer_image) == FOOTER_SHA256,
                "comparison image is not the verified 6891dc51 footer image")
    require(len(control) == PREFIX_SIZE, "source is not 13955072 bytes")
    require(len(candidate) == PARTITION_SIZE, "output is not 100663296 bytes")
    require(candidate[:PREFIX_SIZE] == control,
            "13955072-byte prefix is not byte-identical to 13a48ff9")
    require(not any(candidate[PREFIX_SIZE:]),
            "tail after the 13955072-byte prefix is not all zero")
    require(len(footer_image) == PARTITION_SIZE and footer_image[:PREFIX_SIZE] == control,
            "comparison image is not 100663296 bytes with the 13a48ff9 prefix")
    require(any(footer_image[PREFIX_SIZE:]) and footer_image[PREFIX_SIZE:] != candidate[PREFIX_SIZE:],
            "comparison image tail does not differ from the zero tail")
    if check_digests:
        require(digest_hex == expected, "candidate SHA-256 is not db2c635d")
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


def self_test(candidate, control, footer_image):
    digest = check_candidate(candidate, control, footer_image, prior_boots=())
    print(f"blank-tail fixture: OK ({digest})")
    expect_rejection(
        "changed prefix byte", "13955072-byte prefix is not byte-identical to 13a48ff9",
        patched(candidate, 4096 + 100, candidate[4096 + 100] ^ 1), control, footer_image)
    expect_rejection(
        "nonzero tail byte", "tail after the 13955072-byte prefix is not all zero",
        patched(candidate, PARTITION_SIZE - 1, 1), control, footer_image)
    expect_rejection(
        "nonzero first tail byte", "tail after the 13955072-byte prefix is not all zero",
        patched(candidate, PREFIX_SIZE, 1), control, footer_image)
    expect_rejection(
        "short image", "output is not 100663296 bytes", candidate[:-4096],
        control, footer_image)
    expect_rejection(
        "repeated 6891dc51", "candidate SHA-256 repeats a prior image", footer_image,
        control, footer_image)
    expect_rejection(
        "repeated 13a48ff9", "candidate SHA-256 repeats a prior image", control,
        control, footer_image)
    try:
        check_candidate(candidate, control, footer_image, check_digests=False,
                        prior_boots=(digest,))
    except ValueError as exc:
        require(str(exc) == "candidate SHA-256 repeats a prior image", f"unexpected failure: {exc}")
        print(f"expected repeated prior SHA failure: {exc}")
    else:
        raise ValueError("repeated prior SHA fixture was accepted")
    for repeated in REQUIRED_PRIOR:
        require(any(prior.startswith(repeated) for prior in PRIOR_BOOTS),
                f"prior SHA {repeated} is not rejected")
    require(CANDIDATE_SHA256 not in PRIOR_BOOTS, "candidate SHA-256 is listed as a prior image")
    print("prior image list: " + ", ".join(REQUIRED_PRIOR) + " rejected")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        require(len(args) == 4,
                "usage: verify-blank-tail-control.py --self-test CANDIDATE CONTROL FOOTER_IMAGE")
        blobs = [pathlib.Path(name).read_bytes() for name in args[1:]]
        require(sha256(blobs[0]) == CANDIDATE_SHA256, "self-test candidate is not db2c635d")
        self_test(*blobs)
        return
    require(len(args) == 3,
            "usage: verify-blank-tail-control.py CANDIDATE CONTROL FOOTER_IMAGE")
    candidate, control, footer_image = (pathlib.Path(n).read_bytes() for n in args)
    digest = check_candidate(candidate, control, footer_image)
    print(f"candidate: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"prefix: {PREFIX_SIZE} bytes byte-identical to 13a48ff9")
    print(f"tail: {TAIL_SIZE} bytes, every byte zero; no AVB0 block and no AVBf footer")
    print("differs from 6891dc51 only in the tail (unsigned AVB0 block and footer replaced by zeroes)")
    print("candidate SHA-256 differs from 5e866c54, 84f7f5ea, 116b1662, 1fdc2570, 55fa78ca, "
          "13a48ff9, d966172c, 5a513998, dc990b95, 6891dc51 and stock boot_a")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
