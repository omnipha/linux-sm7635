import ctypes
import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


builder = load("build-init-boot-vendor-modules-payload.py", "vendor_builder")
base = builder.base
modules = builder.modules
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
HC_LEVEL = base.HC_LEVEL
LZ4_MAGIC = base.LZ4_MAGIC
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = ("3932504a", "f4a00ce3", "baa33fd4", "23725940", "197aff11")
SIZE_MSG = "candidate is not 8388608 bytes"
KERNEL_MSG = "candidate init_boot kernel is not empty"
HEADER_MSG = "candidate header differs from stock beyond the ramdisk-size field"
FRAME_MSG = "candidate ramdisk is not one Android LZ4 legacy block inside the stock envelope"
BLOCK_MSG = "candidate LZ4 block is not the level-12 encoding of the module-loading cpio"
GAP_MSG = "candidate gap between ramdisk and signed tail is not all zero"
TAIL_MSG = "candidate bytes from offset 2121728 differ from the stock signed tail"
SHA_MSG = "candidate repeats a previously measured SHA-256"
KO_MSG = "candidate debug cpio contains a .ko file"
LOAD_MSG = "candidate debug cpio init does not load the closure before the UDC wait"
SOURCE_MSG = "candidate debug cpio changes entries besides init"
VENDOR_MSG = "stock vendor ramdisk does not contribute lib/modules to the init rootfs"
ENVELOPE_MSG = "script does not fit the stock LZ4 envelope; stop without an image"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def decode_frame(frame, library):
    require(len(frame) >= 9 and len(frame) <= base.MAX_FRAME and frame[:4] == LZ4_MAGIC and
            struct.unpack_from("<I", frame, 4)[0] == len(frame) - 8, FRAME_MSG)
    output = ctypes.create_string_buffer(modules.LZ4_CHUNK)
    size = library.LZ4_decompress_safe(frame[8:], output, len(frame) - 8, modules.LZ4_CHUNK)
    require(size > 0, BLOCK_MSG)
    return output.raw[:size]


def check_candidate(candidate, stock, source, boot, vendor, recovery, config, kernel,
                    decompressor, pstore, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    builder.check_stock(stock, library)
    vendor_files, recovery_entries = builder.verify_host_path(
        boot, vendor, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_order(vendor_files)
    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    init_entries = [entry for entry in entries if entry["name"] == "init"]
    require(len(init_entries) == 1, LOAD_MSG)
    try:
        modules.verify_init(init_entries[0]["data"].decode(), order)
    except ValueError as exc:
        raise ValueError(LOAD_MSG) from exc
    _, source_entries, _ = builder.source_cpio(source)
    require([entry["name"] for entry in entries] ==
            [entry["name"] for entry in source_entries] and
            init_entries[0]["data"] ==
            (HERE.parent / "initramfs" / "init-44-vendor-modules").read_bytes() and
            all(entry["data"] == source_entries[index]["data"]
                for index, entry in enumerate(entries) if entry["name"] != "init"),
            SOURCE_MSG)
    try:
        modules.prove_vendor_modules(vendor_files, entries, recovery_entries)
    except ValueError as exc:
        raise ValueError(VENDOR_MSG) from exc
    expected = builder.encode_frame(decoded, library)
    require(expected == candidate[PAGE:PAGE + frame_size], BLOCK_MSG)
    require(len(expected) <= base.MAX_FRAME, ENVELOPE_MSG)
    require(candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET] and
            candidate[RAMDISK_SIZE_OFFSET + 4:PAGE] == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            HEADER_MSG)
    require(not any(candidate[PAGE + frame_size:TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)
    digest = modules.sha256(candidate)
    reject_prior_sha(digest)
    require(builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected


def expect_rejection(label, message, function, *args):
    try:
        function(*args)
    except ValueError as exc:
        require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        print(f"expected {label} failure: {exc}")
    else:
        raise ValueError(f"{label}: invalid fixture was accepted")


def flipped(data, offset):
    changed = bytearray(data)
    changed[offset] ^= 1
    return bytes(changed)


def self_test(candidate, stock, source, boot, vendor, recovery, config, kernel,
              decompressor, pstore):
    library = base.lz4()
    digest, order, outside, cpio, frame = check_candidate(
        candidate, stock, source, boot, vendor, recovery, config, kernel, decompressor,
        pstore, library)
    print(f"init_boot vendor-modules fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, source, boot,
                         vendor, recovery, config, kernel, decompressor, pstore, library)

    case("changed signed tail", TAIL_MSG, flipped(candidate, TAIL_OFFSET + 100))
    case("changed footer byte", TAIL_MSG, flipped(candidate, IMAGE_SIZE - 1))
    case("second changed header field", HEADER_MSG, flipped(candidate, 16))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, flipped(candidate, PAGE + 64))
    case("modern LZ4 frame magic", FRAME_MSG,
         candidate[:PAGE] + b"\x04\x22\x4d\x18" + candidate[PAGE + 4:])
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")

    def rebuilt(changed_entries, extra=()):
        return modules.encode_newc(list(changed_entries) + list(extra), trailer)

    def spliced(payload):
        encoded = builder.encode_frame(payload, library)
        return builder.assemble(stock, encoded)[0]

    stripped = []
    for entry in entries:
        if entry["name"] == "init":
            data = entry["data"]
            for token in (b"log 'module load begin'\n",
                          b"for module in $VENDOR_MODULES; do\n",
                          b"log 'module load end'\n"):
                data = data.replace(token, b"")
            entry = {**entry, "data": data}
        stripped.append(entry)
    case("ramdisk without the load path", LOAD_MSG, spliced(rebuilt(stripped)))

    planted = {"name": "lib/modules/outside-closure.ko",
               "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 31, 0],
               "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}
    case("ramdisk carrying a .ko", KO_MSG, spliced(rebuilt(entries, [planted])))

    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("vendor-modules negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (10, 11) and (len(args) == 10 or args[0] == "--self-test"),
            "usage: verify-init-boot-vendor-modules.py [--self-test] CANDIDATE STOCK_INIT "
            "GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    paths = [pathlib.Path(path).read_bytes() for path in args]
    if self_test_mode:
        self_test(*paths)
        return
    digest, order, outside, cpio, frame = check_candidate(*paths, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")
    print(f"USB additions: {' '.join(outside)}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {HC_LEVEL}, {len(frame)} bytes")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from 3932504a, f4a00ce3, baa33fd4 and every prior SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
