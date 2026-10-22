import hashlib
import pathlib
import struct
import subprocess
import sys

PAGE = 4096
STOCK_BOOT_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
STOCK_BOOT_SIZE = 100663296
KERNEL_SIZE = 13949926
GZIP_END = PAGE + KERNEL_SIZE
PADDING_START = 13954022
PADDING_END = 13955072
AVB0_OFFSET = 13955072
AVB0_SIZE = 16384
VBMETA_OFFSET = 13971456
VBMETA_SIZE = 2496
FOOTER_SIZE = 64
CHANGED_OFFSET = 13954122
CHANGED_VALUE = 1
HASHED_PREFIX = VBMETA_OFFSET
PUBLIC_KEY_SHA1 = "407b99d1f65947192fb4591e5732bc1b1da9d95a"
ALGORITHM = "SHA256_RSA4096"
PRIOR_BOOTS = (
    "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
    "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a",
    "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce",
    "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7",
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450",
    "d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131",
    STOCK_BOOT_SHA256,
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def descriptors(vbmeta, name):
    require(len(vbmeta) >= 256 and vbmeta[:4] == b"AVB0", f"{name}: missing AVB0")
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    offset, length = struct.unpack_from(">QQ", vbmeta, 96)
    require(256 + auth + aux <= len(vbmeta) and offset + length <= aux,
            f"{name}: AVB metadata out of bounds")
    pos = 256 + auth + offset
    end = pos + length
    while pos < end:
        require(pos + 16 <= end, f"{name}: truncated AVB descriptor")
        tag, size = struct.unpack_from(">QQ", vbmeta, pos)
        require(size > 0 and pos + 16 + size <= end, f"{name}: AVB descriptor out of bounds")
        yield tag, vbmeta[pos + 16:pos + 16 + size]
        pos += 16 + size


def hash_descriptor(vbmeta, name):
    found = None
    for tag, body in descriptors(vbmeta, name):
        if tag != 2:
            continue
        require(found is None, f"{name}: duplicate hash descriptor")
        require(len(body) >= 116, f"{name}: short hash descriptor")
        image_size = struct.unpack_from(">Q", body)[0]
        algorithm = body[8:40].split(b"\0", 1)[0]
        name_len, salt_len, digest_len, flags = struct.unpack_from(">IIII", body, 40)
        total = 116 + name_len + salt_len + digest_len
        require(total <= len(body) and algorithm == b"sha256" and digest_len == 32 and flags == 0,
                f"{name}: unexpected hash descriptor")
        part = body[116:116 + name_len]
        salt = body[116 + name_len:116 + name_len + salt_len]
        digest = body[116 + name_len + salt_len:total]
        found = part, image_size, salt, digest
    require(found is not None and found[0] == b"boot", f"{name}: missing boot hash descriptor")
    return found[1:]


def public_key_sha1(vbmeta):
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    offset, length = struct.unpack_from(">QQ", vbmeta, 64)
    start = 256 + auth + offset
    require(offset + length <= aux and start + length <= len(vbmeta), "public key out of bounds")
    return hashlib.sha1(vbmeta[start:start + length]).hexdigest()


def algorithm_name(vbmeta):
    auth = struct.unpack_from(">Q", vbmeta, 12)[0]
    require(auth == 576, "signed vbmeta authentication block is not SHA256_RSA4096")
    return ALGORITHM


def descriptor_set(vbmeta, name):
    found = []
    for tag, body in descriptors(vbmeta, name):
        if tag == 2:
            name_len = struct.unpack_from(">I", body, 40)[0]
            found.append(("hash", body[116:116 + name_len]))
        elif tag == 1:
            found.append(("property", body[: struct.unpack_from(">Q", body)[0]]))
        elif tag == 3:
            found.append(("hashtree", body[: struct.unpack_from(">I", body, 68)[0]]))
        elif tag == 4:
            found.append(("chain", body[76:76 + struct.unpack_from(">I", body, 4)[0]]))
        else:
            found.append((tag, hashlib.sha256(body).digest()))
    return tuple(found)


def info_image(image, name):
    require(len(image) >= FOOTER_SIZE and image[-64:-60] == b"AVBf", f"{name}: missing AVB footer")
    major, minor = struct.unpack_from(">II", image, len(image) - 60)
    original, offset, size = struct.unpack_from(">QQQ", image, len(image) - 52)
    require((major, minor) == (1, 0) and original == offset and size > 0 and
            offset + size <= len(image) - FOOTER_SIZE and not any(image[-28:]),
            f"{name}: malformed AVB footer")
    vbmeta = image[offset:offset + size]
    image_size, _, digest = hash_descriptor(vbmeta, name)
    return {
        "algorithm": algorithm_name(vbmeta),
        "public_key_sha1": public_key_sha1(vbmeta),
        "image_size": len(image),
        "original_image_size": original,
        "descriptors": descriptor_set(vbmeta, name),
        "hash_image_size": image_size,
        "digest": digest,
        "vbmeta": vbmeta,
    }


def avbtool_info(path):
    avbtool = pathlib.Path.home() / ".local/var/pmbootstrap/chroot_native/usr/bin/avbtool"
    output = subprocess.run([sys.executable, avbtool, "info_image", "--image", path],
                            check=True, capture_output=True, text=True).stdout.splitlines()
    fields = {}
    require("Descriptors:" in output, "avbtool info_image reported no descriptors")
    for line in output:
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields, tuple(output[output.index("Descriptors:") + 1:])


def regions(image):
    kernel = struct.unpack_from("<I", image, 8)[0]
    require(image[:8] == b"ANDROID!" and kernel == KERNEL_SIZE,
            "boot header kernel size is not the stock payload size")
    return {
        "gzip": image[PAGE:GZIP_END],
        "header": image[:PAGE],
        "avb0": image[AVB0_OFFSET:AVB0_OFFSET + AVB0_SIZE],
        "vbmeta": image[VBMETA_OFFSET:VBMETA_OFFSET + VBMETA_SIZE],
        "footer": image[-FOOTER_SIZE:],
    }


def check_control(control, stock, check_digests=True, prior_boots=PRIOR_BOOTS, paths=None):
    if check_digests:
        require(len(stock) == STOCK_BOOT_SIZE and sha256(stock) == STOCK_BOOT_SHA256,
                "stock boot_a is not the verified reference")
    require(len(control) == len(stock) == STOCK_BOOT_SIZE,
            "control length is not the stock boot partition size")
    require(PADDING_START <= CHANGED_OFFSET < PADDING_END and CHANGED_OFFSET >= GZIP_END,
            "selected offset is outside the hashed padding")
    require(stock[CHANGED_OFFSET] == 0, "selected padding byte is not zero")
    differences = [index for index, (left, right) in enumerate(zip(control, stock, strict=True))
                   if left != right]
    require(differences == [CHANGED_OFFSET] and control[CHANGED_OFFSET] == CHANGED_VALUE,
            "control changes a byte other than the selected padding offset")
    control_regions = regions(control)
    stock_regions = regions(stock)
    require(control_regions == stock_regions,
            "gzip payload, header, AVB0 record, vbmeta or footer differs from stock")
    require(control[GZIP_END:PADDING_END] != stock[GZIP_END:PADDING_END] and
            not any(stock[GZIP_END:PADDING_END]),
            "stock padding window is not zero or the control did not change it")
    stock_info = info_image(stock, "stock boot")
    control_info = info_image(control, "control boot")
    for field in ("algorithm", "public_key_sha1", "image_size", "original_image_size",
                  "descriptors"):
        require(control_info[field] == stock_info[field],
                f"avbtool info_image {field} differs from stock")
    if paths is not None:
        control_path, stock_path = paths
        stock_fields, stock_descriptors = avbtool_info(stock_path)
        control_fields, control_descriptors = avbtool_info(control_path)
        reported = {
            "algorithm": "Algorithm",
            "public_key_sha1": "Public key (sha1)",
            "image_size": "Image size",
            "original_image_size": "Original image size",
        }
        for field, label in reported.items():
            require(control_fields[label] == stock_fields[label] == {
                "algorithm": ALGORITHM,
                "public_key_sha1": PUBLIC_KEY_SHA1,
                "image_size": f"{STOCK_BOOT_SIZE} bytes",
                "original_image_size": f"{HASHED_PREFIX} bytes",
            }[field], f"avbtool info_image {label} differs from stock")
        require(control_descriptors == stock_descriptors and len(stock_descriptors) == 11,
                "avbtool info_image descriptor set differs from stock")
    require(stock_info["algorithm"] == ALGORITHM and
            stock_info["public_key_sha1"] == PUBLIC_KEY_SHA1 and
            stock_info["image_size"] == STOCK_BOOT_SIZE and
            stock_info["original_image_size"] == HASHED_PREFIX and
            stock_info["hash_image_size"] == HASHED_PREFIX,
            "stock info_image fields are not the verified reference")
    _, salt, digest = hash_descriptor(stock_regions["vbmeta"], "stock vbmeta")
    stock_salted = hashlib.sha256(salt + stock[:HASHED_PREFIX]).digest()
    control_salted = hashlib.sha256(salt + control[:HASHED_PREFIX]).digest()
    require(stock_salted == digest == stock_info["digest"],
            "stock salted prefix does not match its hash descriptor")
    require(control_salted != digest, "control salted prefix still matches the stock digest")
    image_digest = sha256(control)
    require(image_digest not in prior_boots, "control SHA-256 repeats a prior boot")
    return image_digest


def expect_rejection(label, expected, *args):
    try:
        check_control(*args, check_digests=False)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def self_test():
    reference = pathlib.Path.home() / "phone-second-life-data/mb003/parts/boot_a.img"
    stock = reference.read_bytes()
    require(len(stock) == STOCK_BOOT_SIZE and sha256(stock) == STOCK_BOOT_SHA256,
            "self-test stock reference is not the verified slot-A image")
    outside_reference = bytearray(stock)
    outside_reference[GZIP_END - 1] ^= 1
    expect_rejection("byte outside padding window",
                     "control changes a byte other than the selected padding offset",
                     bytes(outside_reference), stock)
    control = bytearray(stock)
    control[CHANGED_OFFSET] = CHANGED_VALUE
    digest = check_control(bytes(control), stock, check_digests=False, prior_boots=())
    print(f"stock one-byte fixture: OK ({digest})")
    outside = bytearray(control)
    outside[GZIP_END - 1] = 1
    expect_rejection("byte outside padding window",
                     "control changes a byte other than the selected padding offset",
                     bytes(outside), stock)
    payload = bytearray(control)
    payload[PAGE + 10] ^= 1
    expect_rejection("changed gzip payload",
                     "control changes a byte other than the selected padding offset",
                     bytes(payload), stock)
    second = bytearray(control)
    second[CHANGED_OFFSET + 1] = 1
    expect_rejection("second padding byte",
                     "control changes a byte other than the selected padding offset",
                     bytes(second), stock)
    wrong = bytearray(stock)
    wrong[PADDING_START] = 1
    expect_rejection("different padding offset",
                     "control changes a byte other than the selected padding offset",
                     bytes(wrong), stock)
    dirty = bytearray(stock)
    dirty[CHANGED_OFFSET] = 2
    expect_rejection("nonzero source byte", "selected padding byte is not zero",
                     bytes(dirty), bytes(dirty))
    short = bytearray(control[:-1])
    expect_rejection("short image", "control length is not the stock boot partition size",
                     bytes(short), stock)
    try:
        check_control(bytes(control), stock, check_digests=False, prior_boots=(digest,))
    except ValueError as exc:
        require(str(exc) == "control SHA-256 repeats a prior boot", f"unexpected failure: {exc}")
        print(f"expected repeated prior boot failure: {exc}")
    else:
        raise ValueError("repeated prior boot fixture was accepted")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    require(len(sys.argv) == 3,
            "usage: verify-hash-boundary-control.py CONTROL_BOOT STOCK_BOOT")
    control, stock = (pathlib.Path(name).read_bytes() for name in sys.argv[1:])
    digest = check_control(control, stock, paths=tuple(sys.argv[1:]))
    print(f"control boot: {len(control)} bytes, SHA-256 {digest}")
    print(f"changed byte: offset {CHANGED_OFFSET} only, 0x00 -> 0x{CHANGED_VALUE:02x}")
    print("gzip payload, header page, separate AVB0, signed vbmeta and footer match stock")
    print(f"info_image: {ALGORITHM}, public key {PUBLIC_KEY_SHA1}, "
          f"image {STOCK_BOOT_SIZE}, original {HASHED_PREFIX}, stock descriptor set")
    print("salted SHA-256 of the first 13971456 bytes differs from the stock hash digest")
    print("control SHA-256 differs from 5e866c54, 84f7f5ea, 116b1662, 1fdc2570, "
          "55fa78ca, 13a48ff9, d966172c and stock boot_a")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
