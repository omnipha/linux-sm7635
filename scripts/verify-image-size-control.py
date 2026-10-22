import gzip
import hashlib
import pathlib
import struct
import sys
import zlib

PAGE = 4096
STOCK_BOOT_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
STOCK_PAYLOAD_SHA256 = "dcbd8ae71b7e6341c3604c35360213b1d40a69ac38672e247772d4af399c3651"
DEBUG_KERNEL_SHA256 = "b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277"
STOCK_BOOT_SIZE = 100663296
KERNEL_SIZE = 13949926
STOCK_IMAGE_LENGTH = 35224064
STOCK_IMAGE_SIZE = 35913728
DEBUG_IMAGE_SIZE = 55508992
GZIP_END = PAGE + KERNEL_SIZE
AVB0_OFFSET = 13955072
VBMETA_OFFSET = 13971456
HASHED_PREFIX = VBMETA_OFFSET
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03"
ARM64_FIELDS = "<IIQQQQQQ4sI"
PRIOR_BOOTS = (
    "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
    "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a",
    "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce",
    "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7",
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450",
    "d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131",
    "5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b",
    STOCK_BOOT_SHA256,
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def hash_descriptor(vbmeta):
    require(len(vbmeta) >= 256 and vbmeta[:4] == b"AVB0", "missing AVB0")
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    offset, length = struct.unpack_from(">QQ", vbmeta, 96)
    require(256 + auth + aux <= len(vbmeta) and offset + length <= aux,
            "AVB metadata out of bounds")
    pos = 256 + auth + offset
    end = pos + length
    found = None
    while pos < end:
        require(pos + 16 <= end, "truncated AVB descriptor")
        tag, size = struct.unpack_from(">QQ", vbmeta, pos)
        require(size > 0 and pos + 16 + size <= end, "AVB descriptor out of bounds")
        body = vbmeta[pos + 16:pos + 16 + size]
        pos += 16 + size
        if tag != 2:
            continue
        require(found is None, "duplicate hash descriptor")
        require(len(body) >= 116, "short hash descriptor")
        image_size = struct.unpack_from(">Q", body)[0]
        algorithm = body[8:40].split(b"\0", 1)[0]
        name_len, salt_len, digest_len, flags = struct.unpack_from(">IIII", body, 40)
        total = 116 + name_len + salt_len + digest_len
        require(total <= len(body) and algorithm == b"sha256" and digest_len == 32 and
                flags == 0, "unexpected hash descriptor")
        part = body[116:116 + name_len]
        salt = body[116 + name_len:116 + name_len + salt_len]
        digest = body[116 + name_len + salt_len:total]
        require(part == b"boot", "hash descriptor is not boot")
        found = image_size, salt, digest
    require(found is not None, "missing boot hash descriptor")
    return found


def gzip_frame(payload):
    require(len(payload) >= 18 and payload[:10] == GZIP_HEADER,
            "gzip framing differs from the stock payload")
    require(payload[3] == 0 and struct.unpack_from("<I", payload, 4)[0] == 0 and
            payload[8] == GZIP_HEADER[8] and payload[9] == 3,
            "gzip framing differs from the stock payload")
    return payload


def recompress(image):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, 8, zlib.Z_DEFAULT_STRATEGY)
    body = compressor.compress(image) + compressor.flush()
    return (GZIP_HEADER + body +
            struct.pack("<II", zlib.crc32(image) & 0xFFFFFFFF, len(image) & 0xFFFFFFFF))


def arm64_header(image):
    require(len(image) >= 64, "arm64 Image header truncated")
    return struct.unpack_from(ARM64_FIELDS, image, 0)


def check_payload_size(payload):
    require(len(payload) <= KERNEL_SIZE, "gzip payload is longer than the stock kernel-size field")
    require(len(payload) == KERNEL_SIZE, "gzip payload is not the stock kernel-size field")


def check_control(control, stock, check_digests=True, prior_boots=PRIOR_BOOTS):
    if check_digests:
        require(len(stock) == STOCK_BOOT_SIZE and sha256(stock) == STOCK_BOOT_SHA256,
                "stock boot_a is not the verified reference")
    require(len(control) == len(stock) == STOCK_BOOT_SIZE,
            "control length is not the stock boot partition size")
    require(control[:8] == stock[:8] == b"ANDROID!", "boot header is not ANDROID!")
    require(control[:PAGE] == stock[:PAGE], "boot header page differs from stock")
    kernel_size = struct.unpack_from("<I", control, 8)[0]
    require(kernel_size == struct.unpack_from("<I", stock, 8)[0] == KERNEL_SIZE,
            "boot header kernel-size field differs from stock")
    require(control[AVB0_OFFSET:] == stock[AVB0_OFFSET:],
            "AVB record or footer bytes differ from stock")
    require(control[GZIP_END:AVB0_OFFSET] == stock[GZIP_END:AVB0_OFFSET],
            "stock zero-padding window was rewritten")
    stock_payload = gzip_frame(stock[PAGE:GZIP_END])
    payload = gzip_frame(control[PAGE:GZIP_END])
    if check_digests:
        require(len(stock_payload) == KERNEL_SIZE and sha256(stock_payload) == STOCK_PAYLOAD_SHA256,
                "stock slot-A gzip payload is not the verified reference")
    check_payload_size(payload)
    stock_image = gzip.decompress(stock_payload)
    control_image = gzip.decompress(payload)
    require(len(stock_image) == STOCK_IMAGE_LENGTH, "stock decompressed length is not verified")
    require(len(control_image) == STOCK_IMAGE_LENGTH,
            "decompressed length is not the stock Image length")
    require(control_image[:16] == stock_image[:16] and control_image[24:] == stock_image[24:],
            "a kernel byte other than image_size differs from stock")
    code0, _, text_offset, image_size, flags, reserved2, reserved3, reserved4, magic, pe = (
        arm64_header(control_image))
    stock_header = arm64_header(stock_image)
    require((code0, text_offset, flags, reserved2, reserved3, reserved4, magic, pe) ==
            (stock_header[0], stock_header[2], stock_header[4], stock_header[5],
             stock_header[6], stock_header[7], stock_header[8], stock_header[9]),
            "arm64 header field other than image_size differs from stock")
    require(text_offset == 0 and flags == 0xA and
            (reserved2, reserved3, reserved4) == (0, 0, 0) and magic == b"ARMd" and pe == 0x40,
            "arm64 Image header is not the verified contract")
    require(stock_header[3] == STOCK_IMAGE_SIZE and image_size == DEBUG_IMAGE_SIZE,
            "image_size is not the debug reservation")
    require(struct.pack("<Q", image_size) == control_image[16:24] and
            control_image[:16] == stock_image[:16] and control_image[24:] == stock_image[24:],
            "image_size change is not the single eight-byte field")
    require(payload == recompress(control_image),
            "gzip payload is not deterministic level 9 with the stock framing")
    image_size_field, salt, digest = hash_descriptor(stock[VBMETA_OFFSET:VBMETA_OFFSET + 2496])
    require(image_size_field == HASHED_PREFIX, "stock hash descriptor does not cover 13971456 bytes")
    stock_salted = hashlib.sha256(salt + stock[:HASHED_PREFIX]).digest()
    control_salted = hashlib.sha256(salt + control[:HASHED_PREFIX]).digest()
    require(stock_salted == digest, "stock salted prefix does not match its hash descriptor")
    require(control_salted != digest,
            "salted hash of the first 13971456 bytes still matches the stock descriptor")
    image_digest = sha256(control)
    require(image_digest not in prior_boots, "control SHA-256 repeats a prior boot")
    return image_digest


def expect_rejection(label, expected, *args, **kwargs):
    try:
        check_control(*args, check_digests=False, **kwargs)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def patched_image(stock_image, extra=None, append=0):
    image = bytearray(stock_image)
    image[16:24] = struct.pack("<Q", DEBUG_IMAGE_SIZE)
    if extra is not None:
        image[extra] ^= 1
    return bytes(image) + bytes(append)


def patched_boot(stock, image, payload_size=KERNEL_SIZE):
    payload = recompress(image)
    require(len(payload) <= payload_size, "fixture payload exceeds its declared size")
    control = bytearray(stock)
    control[PAGE:PAGE + len(payload)] = payload
    if len(payload) < payload_size:
        control[PAGE + len(payload):PAGE + payload_size] = bytes(payload_size - len(payload))
    return bytes(control)


def self_test():
    reference = pathlib.Path.home() / "phone-second-life-data/mb003/parts/boot_a.img"
    debug = pathlib.Path.home() / "sm7635-build/out/Image.gz"
    stock = reference.read_bytes()
    require(len(stock) == STOCK_BOOT_SIZE and sha256(stock) == STOCK_BOOT_SHA256,
            "self-test stock reference is not the verified slot-A image")
    require(sha256(debug.read_bytes()) == DEBUG_KERNEL_SHA256,
            "self-test debug Image.gz is not the verified payload")
    stock_image = gzip.decompress(stock[PAGE:GZIP_END])
    control = patched_boot(stock, patched_image(stock_image))
    digest = check_control(control, stock, check_digests=False, prior_boots=())
    print(f"stock image_size fixture: OK ({digest})")
    second = patched_image(stock_image, extra=64)
    expect_rejection("second changed kernel byte",
                     "a kernel byte other than image_size differs from stock",
                     patched_boot(stock, second), stock)
    appended = patched_image(stock_image, append=1)
    expect_rejection("appended zero tail",
                     "decompressed length is not the stock Image length",
                     patched_boot(stock, appended), stock)
    longer = recompress(patched_image(stock_image)) + b"\x01"
    try:
        check_payload_size(longer)
    except ValueError as exc:
        require(str(exc) == "gzip payload is longer than the stock kernel-size field",
                f"payload length: unexpected failure: {exc}")
        print(f"expected payload longer than stock kernel size failure: {exc}")
    else:
        raise ValueError("overlong gzip payload fixture was accepted")
    long_boot = bytearray(stock)
    long_boot[PAGE:PAGE + len(longer)] = longer
    expect_rejection("payload overrun into padding", "stock zero-padding window was rewritten",
                     bytes(long_boot), stock)
    wrong_length = bytearray(patched_image(stock_image))
    del wrong_length[-1]
    expect_rejection("decompressed length other than stock",
                     "decompressed length is not the stock Image length",
                     patched_boot(stock, bytes(wrong_length)), stock)
    try:
        check_control(control, stock, check_digests=False, prior_boots=(digest,))
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
            "usage: verify-image-size-control.py CONTROL_BOOT STOCK_BOOT")
    control, stock = (pathlib.Path(name).read_bytes() for name in sys.argv[1:])
    digest = check_control(control, stock)
    print(f"control boot: {len(control)} bytes, SHA-256 {digest}")
    print(f"image_size: {STOCK_IMAGE_SIZE} -> {DEBUG_IMAGE_SIZE} at decompressed bytes 16..23")
    print(f"decompressed length: {STOCK_IMAGE_LENGTH}; gzip payload: {KERNEL_SIZE}")
    print("header page, AVB record, signed vbmeta and footer match stock")
    print("salted SHA-256 of the first 13971456 bytes differs from the stock hash digest")
    print("control SHA-256 differs from 5e866c54, 84f7f5ea, 116b1662, 1fdc2570, "
          "55fa78ca, 13a48ff9, d966172c, 5a513998 and stock boot_a")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, zlib.error, gzip.BadGzipFile) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
