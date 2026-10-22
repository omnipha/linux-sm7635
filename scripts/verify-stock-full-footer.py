import hashlib
import pathlib
import struct
import sys

PAGE = 4096
PARTITION_SIZE = 100663296
PREFIX_SIZE = 13955072
VBMETA_SIZE = 448
FOOTER_SIZE = 64
CONTROL_SHA256 = "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450"
DEBUG_BOOT_SHA256 = "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af"
DEBUG_BOOT_SIZE = 15753216
FULL_FOOTER_SHA256 = "d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131"
CANDIDATE_SHA256 = "6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555"
SALT = bytes.fromhex("d41d8cd98f00b204e9800998ecf8427e")
RELEASE = b"avbtool 1.4.0"
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
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_footer(image):
    tail = image[-FOOTER_SIZE:]
    require(tail[:4] == b"AVBf", "image has no AVB footer")
    major, minor = struct.unpack_from(">II", tail, 4)
    original, offset, size = struct.unpack_from(">QQQ", tail, 12)
    require((major, minor) == (1, 0), "AVB footer version is not 1.0")
    require(not any(tail[36:]), "AVB footer reserved bytes are not zero")
    return original, offset, size


def parse_vbmeta(vbmeta):
    require(len(vbmeta) == VBMETA_SIZE and vbmeta[:4] == b"AVB0", "footer block is not AVB0")
    require(struct.unpack_from(">II", vbmeta, 4) == (1, 0), "AVB0 libavb version is not 1.0")
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    algorithm = struct.unpack_from(">I", vbmeta, 28)[0]
    require(algorithm == 0, "AVB algorithm is not NONE")
    require(auth == 0, "AVB authentication block is not empty")
    require(256 + auth + aux == VBMETA_SIZE, "AVB0 block is not 448 bytes")
    require(all(struct.unpack_from(">Q", vbmeta, field)[0] == 0 for field in (40, 56, 72, 88)),
            "unsigned AVB0 carries hash, signature or key data")
    desc_offset, desc_size = struct.unpack_from(">QQ", vbmeta, 96)
    require(desc_offset == 0 and desc_size + 256 <= VBMETA_SIZE and desc_size <= aux,
            "AVB descriptor block out of bounds")
    rollback, flags, location = struct.unpack_from(">QII", vbmeta, 112)
    require((rollback, flags, location) == (0, 0, 0), "AVB rollback index or flags are not zero")
    require(vbmeta[128:176].rstrip(b"\0") == RELEASE and not any(vbmeta[176:256]),
            "AVB release string is not avbtool 1.4.0")
    pos = 256 + desc_offset
    end = pos + desc_size
    require(pos + 16 <= end, "AVB descriptor header out of bounds")
    tag, size = struct.unpack_from(">QQ", vbmeta, pos)
    require(tag == 2 and pos + 16 + size == end, "AVB descriptor set is not exactly one hash descriptor")
    require(not any(vbmeta[end:]), "AVB0 block has data after its descriptors")
    body = vbmeta[pos + 16:end]
    require(len(body) >= 116, "AVB hash descriptor too short")
    image_size = struct.unpack_from(">Q", body)[0]
    algorithm_name = body[8:40].rstrip(b"\0")
    name_len, salt_len, digest_len, descriptor_flags = struct.unpack_from(">IIII", body, 40)
    require(116 + name_len + salt_len + digest_len <= len(body) and
            not any(body[116 + name_len + salt_len + digest_len:]),
            "AVB hash descriptor sizes are out of bounds")
    name = body[116:116 + name_len]
    salt = body[116 + name_len:116 + name_len + salt_len]
    digest = body[116 + name_len + salt_len:116 + name_len + salt_len + digest_len]
    require(algorithm_name == b"sha256" and digest_len == 32,
            "AVB hash algorithm is not sha256")
    require(name == b"boot" and descriptor_flags == 0, "AVB hash descriptor is not boot with flags 0")
    return image_size, salt, digest, pos + 16


def patch_descriptor(vbmeta, image_size, digest):
    _, _, _, body = parse_vbmeta(vbmeta)
    patched = bytearray(vbmeta)
    struct.pack_into(">Q", patched, body, image_size)
    digest_at = body + 116 + len(b"boot") + len(SALT)
    patched[digest_at:digest_at + 32] = digest
    return bytes(patched)


def check_candidate(candidate, control, debug_boot, full_footer, check_digests=True,
                    prior_boots=PRIOR_BOOTS, expected=CANDIDATE_SHA256):
    if check_digests:
        require(sha256(control) == CONTROL_SHA256, "source is not the verified 13a48ff9 control")
        require(sha256(debug_boot) == DEBUG_BOOT_SHA256 and len(debug_boot) == DEBUG_BOOT_SIZE,
                "comparison boot is not the verified 55fa78ca image")
        require(sha256(full_footer) == FULL_FOOTER_SHA256,
                "comparison footer image is not the verified d966172c image")
    require(len(control) == PREFIX_SIZE, "source is not 13955072 bytes")
    require(len(candidate) == PARTITION_SIZE, "output is not 100663296 bytes")
    require(candidate[:PREFIX_SIZE] == control,
            "13955072-byte prefix is not byte-identical to 13a48ff9")
    original, offset, size = parse_footer(candidate)
    require(original == PREFIX_SIZE and offset == PREFIX_SIZE and size == VBMETA_SIZE,
            "footer does not reference a 448-byte AVB0 block at offset 13955072")
    require(candidate[PREFIX_SIZE:PREFIX_SIZE + 4] == b"AVB0", "no AVB0 at offset 13955072")
    vbmeta = candidate[PREFIX_SIZE:PREFIX_SIZE + VBMETA_SIZE]
    image_size, salt, digest, _ = parse_vbmeta(vbmeta)
    require(salt == SALT, "AVB hash salt is not d41d8cd98f00b204e9800998ecf8427e")
    require(image_size == PREFIX_SIZE, "AVB hash descriptor does not cover 13955072 bytes")
    require(hashlib.sha256(salt + candidate[:image_size]).digest() == digest,
            "AVB hash descriptor digest does not match the 13a48ff9 prefix")
    require(not any(candidate[PREFIX_SIZE + VBMETA_SIZE:-FOOTER_SIZE]),
            "data between the AVB0 block and the footer")
    require(len(full_footer) == PARTITION_SIZE and len(debug_boot) < PARTITION_SIZE,
            "comparison images have unexpected sizes")
    require(full_footer[:len(debug_boot)] == debug_boot,
            "comparison footer image does not start with the debug boot")
    debug_original, debug_offset, debug_size = parse_footer(full_footer)
    require(debug_original == debug_offset == len(debug_boot) and debug_size == VBMETA_SIZE,
            "comparison footer does not cover exactly the debug boot")
    debug_vbmeta = full_footer[debug_offset:debug_offset + debug_size]
    debug_image_size, debug_salt, debug_digest, _ = parse_vbmeta(debug_vbmeta)
    require(debug_image_size == len(debug_boot) and debug_salt == SALT,
            "comparison footer descriptor differs from the same salt and covered size")
    require(candidate[:8] == full_footer[:8] and
            candidate[12:PAGE] == full_footer[12:PAGE],
            "boot header differs from d966172c beyond the kernel-size field")
    kernel_size = struct.unpack_from("<I", candidate, 8)[0]
    debug_kernel_size = struct.unpack_from("<I", full_footer, 8)[0]
    require(kernel_size != debug_kernel_size and
            PAGE < PAGE + kernel_size <= PREFIX_SIZE and
            PAGE < PAGE + debug_kernel_size <= len(debug_boot),
            "kernel payload sizes are not the stock and debug payloads")
    require(candidate[PAGE:PAGE + kernel_size] != full_footer[PAGE:PAGE + debug_kernel_size],
            "kernel payload is not the stock payload instead of the debug payload")
    require(patch_descriptor(debug_vbmeta, PREFIX_SIZE, digest) == vbmeta,
            "AVB0 block differs from d966172c beyond the hash descriptor size and digest")
    footer_prefix = struct.pack(">QQ", PREFIX_SIZE, PREFIX_SIZE)
    debug_footer = bytearray(full_footer[-FOOTER_SIZE:])
    debug_footer[12:28] = footer_prefix
    require(bytes(debug_footer) == candidate[-FOOTER_SIZE:],
            "footer differs from d966172c beyond the original size and vbmeta offset")
    require(not any(full_footer[debug_offset + debug_size:-FOOTER_SIZE]),
            "comparison image has data between its AVB0 block and footer")
    digest_hex = sha256(candidate)
    require(digest_hex not in prior_boots, "candidate SHA-256 repeats a prior image")
    if check_digests:
        require(digest_hex == expected, "candidate SHA-256 is not 6891dc51")
    return digest_hex, original, offset, size, kernel_size, debug_kernel_size


def expect_rejection(label, expected, *args, **kwargs):
    try:
        check_candidate(*args, check_digests=False, **kwargs)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def patched(candidate, edits):
    image = bytearray(candidate)
    for offset, value in edits:
        image[offset:offset + len(value)] = value
    return bytes(image)


def refresh_digest(candidate, salt):
    image = bytearray(candidate)
    body = PREFIX_SIZE + 256 + 16
    digest_at = body + 116 + len(b"boot") + len(salt)
    image[digest_at:digest_at + 32] = hashlib.sha256(salt + bytes(image[:PREFIX_SIZE])).digest()
    return bytes(image)


def self_test(candidate, control, debug_boot, full_footer):
    digest, *_ = check_candidate(candidate, control, debug_boot, full_footer, prior_boots=())
    print(f"unsigned stock footer fixture: OK ({digest})")
    body = PREFIX_SIZE + 256 + 16
    salt_at = body + 116 + len(b"boot")
    algorithm_at = PREFIX_SIZE + 28
    expect_rejection(
        "changed prefix byte", "13955072-byte prefix is not byte-identical to 13a48ff9",
        patched(candidate, [(PAGE + 100, bytes([candidate[PAGE + 100] ^ 1]))]),
        control, debug_boot, full_footer)
    expect_rejection(
        "signed algorithm", "AVB algorithm is not NONE",
        patched(candidate, [(algorithm_at, struct.pack(">I", 1))]),
        control, debug_boot, full_footer)
    other_salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    expect_rejection(
        "different salt", "AVB hash salt is not d41d8cd98f00b204e9800998ecf8427e",
        refresh_digest(patched(candidate, [(salt_at, other_salt)]), other_salt),
        control, debug_boot, full_footer)
    expect_rejection(
        "wrong footer placement", "footer does not reference a 448-byte AVB0 block at offset 13955072",
        patched(candidate, [(len(candidate) - 52, struct.pack(">QQ", PREFIX_SIZE, PREFIX_SIZE + 4096))]),
        control, debug_boot, full_footer)
    expect_rejection(
        "truncated image", "output is not 100663296 bytes", candidate[:-PAGE],
        control, debug_boot, full_footer)
    expect_rejection(
        "stale digest", "AVB hash descriptor digest does not match the 13a48ff9 prefix",
        patched(candidate, [(body + 116 + len(b"boot") + len(SALT), bytes(32))]),
        control, debug_boot, full_footer)
    try:
        check_candidate(candidate, control, debug_boot, full_footer, check_digests=False,
                        prior_boots=(digest,))
    except ValueError as exc:
        require(str(exc) == "candidate SHA-256 repeats a prior image", f"unexpected failure: {exc}")
        print(f"expected repeated prior SHA failure: {exc}")
    else:
        raise ValueError("repeated prior SHA fixture was accepted")
    for repeated in ("13a48ff9", "d966172c", "dc990b95", "5a513998", "55fa78ca", "116b1662"):
        require(any(prior.startswith(repeated) for prior in PRIOR_BOOTS),
                f"prior SHA {repeated} is not rejected")
    print("prior image list: 13a48ff9, d966172c, dc990b95, 5a513998, 55fa78ca, 116b1662 rejected")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        require(len(args) == 5,
                "usage: verify-stock-full-footer.py --self-test CANDIDATE CONTROL DEBUG_BOOT FULL_FOOTER")
        blobs = [pathlib.Path(name).read_bytes() for name in args[1:]]
        require(sha256(blobs[0]) == CANDIDATE_SHA256, "self-test candidate is not 6891dc51")
        self_test(*blobs)
        return
    require(len(args) == 4,
            "usage: verify-stock-full-footer.py CANDIDATE CONTROL DEBUG_BOOT FULL_FOOTER")
    candidate, control, debug_boot, full_footer = (pathlib.Path(n).read_bytes() for n in args)
    digest, original, offset, size, kernel_size, debug_kernel_size = check_candidate(
        candidate, control, debug_boot, full_footer)
    print(f"candidate: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"prefix: {PREFIX_SIZE} bytes byte-identical to 13a48ff9")
    print(f"footer: original size {original}, AVB0 offset {offset}, AVB0 size {size}, "
          "algorithm NONE, sha256 boot descriptor, salt d41d8cd98f00b204e9800998ecf8427e")
    print(f"differs from d966172c only in the kernel payload (stock {kernel_size} bytes, "
          f"debug {debug_kernel_size} bytes) and the resulting hash descriptor")
    print("candidate SHA-256 differs from 5e866c54, 84f7f5ea, 116b1662, 1fdc2570, 55fa78ca, "
          "13a48ff9, d966172c, 5a513998, dc990b95 and stock boot_a")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
