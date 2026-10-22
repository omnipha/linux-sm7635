import hashlib
import pathlib
import struct
import sys

PAGE = 4096
BOOT_PARTITION_SIZE = 100663296
INIT_BOOT_PARTITION_SIZE = 8388608
VENDOR_BOOT_PARTITION_SIZE = 100663296
BOOT_VBMETA_OFFSET = 13971456
BOOT_VBMETA_SIZE = 2496
BOOT_AVB0_OFFSET = 13955072
BOOT_AVB0_SIZE = 16384
INIT_BOOT_VBMETA_OFFSET = 2121728
VENDOR_BOOT_VBMETA_OFFSET = 18255872
STOCK_BOOT_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
STOCK_INIT_SHA256 = "baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193"
STOCK_VENDOR_SHA256 = "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253"
BOOT_8_SHA256 = "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb"
BOOT_14_SHA256 = "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a"
BOOT_16_SHA256 = "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7"
BOOT_18_SHA256 = "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce"
BASE_BOOT_SHA256 = "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af"
CONTROL_BOOT_SHA256 = "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450"
RAMDISK_SHA256 = "caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f"
INIT_BOOT_SHA256 = "f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89"
VENDOR_BOOT_SHA256 = "6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d"
PRIOR_BOOTS = (BOOT_8_SHA256, BOOT_14_SHA256, BOOT_18_SHA256, BOOT_16_SHA256,
               BASE_BOOT_SHA256, CONTROL_BOOT_SHA256, STOCK_BOOT_SHA256)
RECORDED_LAYOUTS = {
    BOOT_8_SHA256: (16777216, 15097006, 1672600),
    BOOT_18_SHA256: (15753216, 15746316, 0),
}
BOOT_CASES = (
    ("boot #8/#10 5e866c54", BOOT_8_SHA256, "tested, fastboot fallback (boot_a + vendor_boot sets)"),
    ("boot #14 84f7f5ea", BOOT_14_SHA256, "tested, fastboot fallback (three-image set)"),
    ("boot #16 1fdc2570", BOOT_16_SHA256, "built, never physically flashed alone"),
    ("boot #18 116b1662", BOOT_18_SHA256, "tested, fastboot fallback (boot_a alone and three-image set)"),
    ("boot #21 55fa78ca", BASE_BOOT_SHA256, "tested boot_a alone, fastboot fallback, no marker"),
    ("boot #23 control 13a48ff9", CONTROL_BOOT_SHA256, "built, never flashed"),
    ("boot stock 197aff11", STOCK_BOOT_SHA256, "verified stock slot-A reference"),
)
INVALID = "invalid chained metadata"
INTACT = "intact metadata"
INTACT_FOOTER = "intact unsigned footer"
BYTES = "byte-verified overlay"
LAYOUT = "layout-derived (image bytes not retained)"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def align(size):
    return (size + PAGE - 1) // PAGE * PAGE


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


def vbmeta_valid(vbmeta, name):
    try:
        list(descriptors(vbmeta, name))
    except (ValueError, struct.error):
        return False
    return True


def hash_descriptors(vbmeta, name):
    found = {}
    for tag, body in descriptors(vbmeta, name):
        if tag != 2:
            continue
        require(len(body) >= 116, f"{name}: short hash descriptor")
        image_size = struct.unpack_from(">Q", body)[0]
        algorithm = body[8:40].split(b"\0", 1)[0]
        name_len, salt_len, digest_len, flags = struct.unpack_from(">IIII", body, 40)
        total = 116 + name_len + salt_len + digest_len
        require(total <= len(body) and algorithm == b"sha256" and digest_len == 32 and flags == 0,
                f"{name}: unexpected hash descriptor")
        part = body[116:116 + name_len]
        require(part not in found, f"{name}: duplicate hash descriptor")
        salt = body[116 + name_len:116 + name_len + salt_len]
        digest = body[116 + name_len + salt_len:total]
        found[part] = image_size, salt, digest
    return found


def footer(image, name):
    require(len(image) >= 64, f"{name}: image shorter than an AVB footer")
    tail = image[-64:]
    if tail[:4] != b"AVBf":
        return None
    major, minor = struct.unpack_from(">II", tail, 4)
    original, offset, size = struct.unpack_from(">QQQ", tail, 12)
    if (major, minor) != (1, 0) or original != offset or size <= 0 or \
            offset + size > len(image) - 64 or any(tail[36:]):
        return None
    return original, offset, size


def classify(image, name, partition_size, separate_offset=None, separate_size=None):
    require(len(image) == partition_size, f"{name}: overlay is not the partition size")
    parsed = footer(image, name)
    vbmeta_ok = False
    separate_ok = None
    if parsed is not None:
        _, offset, size = parsed
        vbmeta_ok = vbmeta_valid(image[offset:offset + size], name)
    if separate_offset is not None:
        record = image[separate_offset:separate_offset + separate_size]
        separate_ok = len(record) == separate_size and vbmeta_valid(record, f"{name} separate AVB0")
    return parsed is not None, vbmeta_ok, separate_ok


def overlay(stock, candidate, name):
    require(len(candidate) <= len(stock), f"{name}: candidate is larger than its stock partition")
    return candidate + stock[len(candidate):]


def layout_classification(label, size, kernel_size, ramdisk_size):
    require(size == PAGE + align(kernel_size) + align(ramdisk_size),
            f"{label}: recorded layout does not add up to the recorded size")
    require(size < BOOT_PARTITION_SIZE, f"{label}: recorded size reaches the footer")
    payload_end = PAGE + kernel_size
    require(PAGE <= BOOT_AVB0_OFFSET and payload_end >= BOOT_VBMETA_OFFSET + BOOT_VBMETA_SIZE,
            f"{label}: recorded size reaches stock metadata")
    return True, False, False


def control_state(result):
    footer_ok, vbmeta_ok, separate_ok = result
    return INTACT if footer_ok and vbmeta_ok and separate_ok else INVALID


def check_stock(stock_boot, stock_init, stock_vendor):
    require(sha256(stock_boot) == STOCK_BOOT_SHA256, "stock boot_a is not the verified reference")
    require(sha256(stock_init) == STOCK_INIT_SHA256, "stock init_boot_a is not the verified reference")
    require(sha256(stock_vendor) == STOCK_VENDOR_SHA256,
            "stock vendor_boot_a is not the verified reference")
    require((len(stock_boot), len(stock_init), len(stock_vendor)) ==
            (BOOT_PARTITION_SIZE, INIT_BOOT_PARTITION_SIZE, VENDOR_BOOT_PARTITION_SIZE),
            "stock partition sizes differ from the verified references")
    require(classify(stock_boot, "stock boot", BOOT_PARTITION_SIZE, BOOT_AVB0_OFFSET,
                     BOOT_AVB0_SIZE) == (True, True, True), "stock boot metadata is not intact")
    require(footer(stock_boot, "stock boot") == (BOOT_VBMETA_OFFSET, BOOT_VBMETA_OFFSET,
                                                BOOT_VBMETA_SIZE),
            "stock boot footer geometry differs from the verified reference")
    require(hash_descriptors(stock_boot[BOOT_VBMETA_OFFSET:BOOT_VBMETA_OFFSET + BOOT_VBMETA_SIZE],
                             "stock boot vbmeta")[b"boot"][0] == BOOT_VBMETA_OFFSET,
            "stock boot hash descriptor does not cover the footer offset")
    require(hash_descriptors(stock_boot[BOOT_AVB0_OFFSET:BOOT_AVB0_OFFSET + BOOT_AVB0_SIZE],
                             "stock boot AVB0")[b"boot"][0] == BOOT_AVB0_OFFSET,
            "stock boot separate AVB0 does not hash its kernel prefix")
    for name, image, size, offset in (
            ("stock init_boot", stock_init, INIT_BOOT_PARTITION_SIZE, INIT_BOOT_VBMETA_OFFSET),
            ("stock vendor_boot", stock_vendor, VENDOR_BOOT_PARTITION_SIZE,
             VENDOR_BOOT_VBMETA_OFFSET)):
        require(classify(image, name, size)[:2] == (True, True) and
                footer(image, name)[1] == offset,
                f"{name} metadata or vbmeta offset differs from the verified reference")


def check_candidate(candidate, base, partition_size=BOOT_PARTITION_SIZE, prior=PRIOR_BOOTS):
    require(len(candidate) == partition_size, "candidate is not the full boot partition size")
    require(candidate[:len(base)] == base,
            "candidate does not start with the verified #21 boot bytes")
    parsed = footer(candidate, "candidate")
    require(parsed is not None, "candidate has no well-formed AVB footer")
    original, offset, size = parsed
    require(original == offset == len(base),
            "candidate footer does not cover exactly the verified #21 image")
    vbmeta = candidate[offset:offset + size]
    require(vbmeta_valid(vbmeta, "candidate"), "candidate footer vbmeta is invalid")
    require(struct.unpack_from(">Q", vbmeta, 12)[0] == 0, "candidate footer is not unsigned")
    hashes = hash_descriptors(vbmeta, "candidate")
    require(list(hashes) == [b"boot"], "candidate descriptor set is not exactly boot")
    image_size, salt, digest = hashes[b"boot"]
    require(image_size == original and
            hashlib.sha256(salt + candidate[:image_size]).digest() == digest,
            "candidate hash descriptor does not match the #21 boot bytes")
    require(not any(candidate[offset + size:partition_size - 64]),
            "candidate has data between vbmeta and footer")
    digest_hex = sha256(candidate)
    require(digest_hex not in prior, "candidate repeats a prior boot SHA")
    return digest_hex, original, offset, size


def report(rows, label, digest, size, physical, evidence, result, state):
    footer_ok, vbmeta_ok, separate_ok = result
    separate = "n/a" if separate_ok is None else ("valid" if separate_ok else "invalid")
    rows.append((label, digest, size, physical, evidence, result, state))
    print(f"{label}: sha256={digest} bytes={size} footer={'valid' if footer_ok else 'invalid'} "
          f"vbmeta={'valid' if vbmeta_ok else 'invalid'} separate_avb0={separate} "
          f"state={state} [{evidence}] ({physical})")


def build_14(boot_16, ramdisk):
    image = bytearray(boot_16)
    struct.pack_into("<I", image, 12, len(ramdisk))
    return bytes(image) + ramdisk + bytes(-len(ramdisk) % PAGE)


def analyze(stock_boot, stock_init, stock_vendor, boot_16, ramdisk, boot_21, control,
            init_boot, vendor_boot, candidate=None):
    check_stock(stock_boot, stock_init, stock_vendor)
    require(sha256(boot_16) == BOOT_16_SHA256 and len(boot_16) == 15101952,
            "#16 boot is not the verified image")
    require(sha256(ramdisk) == RAMDISK_SHA256, "gzip cpio is not the verified ramdisk")
    require(sha256(boot_21) == BASE_BOOT_SHA256, "#21 boot is not the verified image")
    require(sha256(control) == CONTROL_BOOT_SHA256, "#23 control is not the verified image")
    require(sha256(init_boot) == INIT_BOOT_SHA256 and len(init_boot) < INIT_BOOT_VBMETA_OFFSET,
            "init_boot is not the verified #21 image")
    require(sha256(vendor_boot) == VENDOR_BOOT_SHA256 and len(vendor_boot) < VENDOR_BOOT_VBMETA_OFFSET,
            "vendor_boot is not the verified #21 image")
    boot_14 = build_14(boot_16, ramdisk)
    require(sha256(boot_14) == BOOT_14_SHA256, "reconstructed #14 boot does not match its SHA")
    images = {BOOT_14_SHA256: boot_14, BOOT_16_SHA256: boot_16, BASE_BOOT_SHA256: boot_21,
              CONTROL_BOOT_SHA256: control, STOCK_BOOT_SHA256: stock_boot}
    rows, states = [], {}
    for label, digest, physical in BOOT_CASES:
        if digest in images:
            image = images[digest]
            result = classify(overlay(stock_boot, image, label), label, BOOT_PARTITION_SIZE,
                              BOOT_AVB0_OFFSET, BOOT_AVB0_SIZE)
            size, evidence = len(image), BYTES
        else:
            size = RECORDED_LAYOUTS[digest][0]
            result = layout_classification(label, *RECORDED_LAYOUTS[digest])
            evidence = LAYOUT
        state = control_state(result)
        report(rows, label, digest, size, physical, evidence, result, state)
        states[digest] = state
    for label, stock, image, size, offset in (
            ("init_boot #21", stock_init, init_boot, INIT_BOOT_PARTITION_SIZE,
             INIT_BOOT_VBMETA_OFFSET),
            ("vendor_boot #21", stock_vendor, vendor_boot, VENDOR_BOOT_PARTITION_SIZE,
             VENDOR_BOOT_VBMETA_OFFSET)):
        combined = overlay(stock, image, label)
        result = classify(combined, label, size)
        require(footer(combined, label)[1] == offset, f"{label}: overlay moved the stock vbmeta")
        state = INTACT if result[:2] == (True, True) else INVALID
        report(rows, label, sha256(image), len(image),
               "built, flashed in the failed three-image sets", BYTES, result, state)
        states[label] = state
    failing = [d for _, d, _ in BOOT_CASES[:5]]
    supported = all(states[d] == INVALID for d in failing) and all(
        states[k] == INTACT for k in (CONTROL_BOOT_SHA256, STOCK_BOOT_SHA256,
                                      "init_boot #21", "vendor_boot #21"))
    candidate_digest = None
    if candidate is not None:
        require(supported, "model is not supported; candidate must not be built")
        candidate_digest, original, offset, size = check_candidate(candidate, boot_21)
        result = classify(overlay(stock_boot, candidate, "candidate"), "candidate",
                          BOOT_PARTITION_SIZE, BOOT_AVB0_OFFSET, BOOT_AVB0_SIZE)
        require(result[:2] == (True, True), "candidate overlay does not keep a valid footer")
        report(rows, "boot #25 candidate", candidate_digest, len(candidate),
               "built, never flashed", BYTES, (True, True, None), INTACT_FOOTER)
        print(f"candidate: {len(candidate)} bytes, hashed prefix {original}, vbmeta offset "
              f"{offset}, vbmeta size {size}, unsigned hash footer for boot")
    print(f"model: {'supported' if supported else 'unsupported'}")
    print("model statement: libavb model, not an observed ABL verdict")
    return supported, candidate_digest


def expect_rejection(label, expected, function, *args):
    try:
        function(*args)
    except ValueError as exc:
        require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def synthetic_vbmeta(image_size, payload, auth=0):
    name = b"boot"
    descriptor = struct.pack(">QQ", 2, 116 + len(name) + 32)
    descriptor += struct.pack(">Q", image_size) + b"sha256".ljust(32, b"\0")
    descriptor += struct.pack(">IIII", len(name), 0, 32, 0) + bytes(60)
    descriptor += name + hashlib.sha256(payload[:image_size]).digest()
    header = bytearray(256)
    header[:4] = b"AVB0"
    struct.pack_into(">II", header, 4, 1, 0)
    struct.pack_into(">QQ", header, 12, auth, len(descriptor))
    struct.pack_into(">QQ", header, 96, 0, len(descriptor))
    return bytes(header) + bytes(auth) + descriptor


def synthetic_footer(image_size, offset, size):
    tail = bytearray(64)
    tail[:4] = b"AVBf"
    struct.pack_into(">II", tail, 4, 1, 0)
    struct.pack_into(">QQQ", tail, 12, image_size, offset, size)
    return bytes(tail)


def self_test():
    stock_size = 4096
    payload = b"payload-bytes"
    vbmeta = synthetic_vbmeta(len(payload), payload)
    separate = synthetic_vbmeta(8, payload)
    stock = bytearray(stock_size)
    stock[:len(payload)] = payload
    stock[1024:1024 + len(separate)] = separate
    stock[2048:2048 + len(vbmeta)] = vbmeta
    stock[-64:] = synthetic_footer(2048, 2048, len(vbmeta))
    stock = bytes(stock)
    require(classify(overlay(stock, payload, "intact"), "intact", stock_size, 1024,
                     len(separate)) == (True, True, True), "intact footer was rejected")
    print("intact footer fixture: footer, vbmeta and separate AVB0 valid")
    require(classify(overlay(stock, b"X" * 2200, "payload"), "payload", stock_size, 1024,
                     len(separate)) == (True, False, False),
            "footer pointing into payload bytes was not detected")
    print("footer pointing into payload bytes fixture: vbmeta invalid")
    truncated = bytearray(stock)
    truncated[-1] ^= 1
    require(classify(bytes(truncated), "truncated", stock_size, 1024, len(separate)) ==
            (False, False, True), "truncated footer was accepted")
    print("truncated footer fixture: footer invalid")
    expect_rejection("candidate larger than partition",
                     "candidate: candidate is larger than its stock partition",
                     overlay, b"small", b"larger-than-stock", "candidate")
    expect_rejection("recorded layout reaching the footer",
                     "fixture: recorded size reaches the footer",
                     layout_classification, "fixture", BOOT_PARTITION_SIZE, BOOT_PARTITION_SIZE - PAGE, 0)
    expect_rejection("recorded layout missing stock metadata",
                     "fixture: recorded size reaches stock metadata",
                     layout_classification, "fixture", PAGE + align(1000), 1000, 0)
    base = bytes(PAGE * 2)
    vb = synthetic_vbmeta(len(base), base)
    good = bytearray(PAGE * 8)
    good[:len(base)] = base
    good[len(base):len(base) + len(vb)] = vb
    good[-64:] = synthetic_footer(len(base), len(base), len(vb))
    check_candidate(bytes(good), base, len(good), ())
    print("candidate fixture: unsigned well-formed footer accepted")
    bad = bytearray(good)
    bad[len(base) + len(vb) + 5] = 1
    expect_rejection("dirty candidate padding", "candidate has data between vbmeta and footer",
                     check_candidate, bytes(bad), base, len(good), ())
    expect_rejection("short candidate", "candidate is not the full boot partition size",
                     check_candidate, bytes(good[:-PAGE]), base, len(good), ())
    changed = bytearray(good)
    changed[0] ^= 1
    expect_rejection("changed #21 bytes", "candidate does not start with the verified #21 boot bytes",
                     check_candidate, bytes(changed), base, len(good), ())


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    require(len(sys.argv) in (10, 11),
            "usage: verify-post-flash-avb.py STOCK_BOOT STOCK_INIT STOCK_VENDOR BOOT_16 "
            "RAMDISK BOOT_21 CONTROL INIT_BOOT VENDOR_BOOT [CANDIDATE]")
    blobs = [pathlib.Path(name).read_bytes() for name in sys.argv[1:]]
    analyze(*blobs)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
