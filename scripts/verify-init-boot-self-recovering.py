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


builder = load("build-init-boot-self-recovering-payload.py", "self_recovering_builder")
checker = load("verify-init-boot-vendor-modules.py", "vendor_checker")
vendor = builder.vendor
base = builder.base
modules = builder.modules
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = ("cdb9458f", "3932504a", "f4a00ce3", "baa33fd4", "23725940", "197aff11")
require = checker.require
flipped = checker.flipped
expect_rejection = checker.expect_rejection
SIZE_MSG = checker.SIZE_MSG
KERNEL_MSG = checker.KERNEL_MSG
HEADER_MSG = checker.HEADER_MSG
FRAME_MSG = checker.FRAME_MSG
BLOCK_MSG = checker.BLOCK_MSG
GAP_MSG = checker.GAP_MSG
TAIL_MSG = checker.TAIL_MSG
SHA_MSG = checker.SHA_MSG
VENDOR_MSG = checker.VENDOR_MSG
KO_MSG = builder.KO_MSG
SOURCE_MSG = builder.SOURCE_MSG
TIMER_MSG = builder.TIMER_MSG
MARKER_MSG = builder.MARKER_MSG
BIND_MSG = builder.BIND_MSG
HELPER_MSG = builder.HELPER_MSG
BASELINE_MSG = builder.BASELINE_MSG
LIST_MSG = "init module list differs from the verified #44 closure"
FIXED_MSG = "candidate init or helper differs from the committed sources"


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def check_candidate(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
                    decompressor, pstore, helper_input, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    vendor.check_stock(stock, library)
    vendor_files, recovery_entries = vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_order(vendor_files)
    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = checker.decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    init_entries = [entry for entry in entries if entry["name"] == "init"]
    require(len(init_entries) == 1, BASELINE_MSG)
    helper_entries = [entry for entry in entries if entry["name"] == builder.HELPER_NAME]
    init = init_entries[0]["data"]
    builder.check_init(init, order)
    builder.check_helper(helper_entries[0]["data"] if len(helper_entries) == 1 else None)
    require(helper_entries[0]["mode"] & 0o170777 == 0o100755, HELPER_MSG)
    require(init == (HERE.parent / "initramfs" / "init").read_bytes() and
            helper_entries[0]["data"] == helper_input, FIXED_MSG)
    _, source_entries, _ = vendor.source_cpio(source)
    names = [entry["name"] for entry in entries if entry["name"] != builder.HELPER_NAME]
    original = {entry["name"]: entry for entry in source_entries}
    require(names == [entry["name"] for entry in source_entries] and
            all(entry["data"] == original[entry["name"]]["data"]
                for entry in entries if entry["name"] not in ("init", builder.HELPER_NAME)),
            SOURCE_MSG)
    try:
        modules.prove_vendor_modules(vendor_files, entries, recovery_entries)
    except ValueError as exc:
        raise ValueError(VENDOR_MSG) from exc
    expected = vendor.encode_frame(decoded, library)
    require(expected == candidate[PAGE:PAGE + frame_size], BLOCK_MSG)
    require(len(expected) <= base.MAX_FRAME, builder.ENVELOPE_MSG)
    require(candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET] and
            candidate[RAMDISK_SIZE_OFFSET + 4:PAGE] == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            HEADER_MSG)
    require(not any(candidate[PAGE + frame_size:TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)
    digest = modules.sha256(candidate)
    reject_prior_sha(digest)
    rebuilt = builder.candidate_cpio(source, init, helper_input, vendor_files,
                                     recovery_entries, order)
    require(vendor.encode_frame(rebuilt, library) == expected and
            builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected


def self_test(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input):
    library = base.lz4()
    digest, order, outside, cpio, frame = check_candidate(
        candidate, stock, source, boot, vendor_boot, recovery, config, kernel, decompressor,
        pstore, helper_input, library)
    print(f"init_boot self-recovering fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, source, boot,
                         vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, library)

    case("changed signed tail", TAIL_MSG, flipped(candidate, TAIL_OFFSET + 100))
    case("changed footer byte", TAIL_MSG, flipped(candidate, IMAGE_SIZE - 1))
    case("second changed header field", HEADER_MSG, flipped(candidate, 16))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, flipped(candidate, PAGE + 64))
    case("modern LZ4 frame magic", FRAME_MSG,
         candidate[:PAGE] + b"\x04\x22\x4d\x18" + candidate[PAGE + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")
    good_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    good_helper = next(entry["data"] for entry in entries
                       if entry["name"] == builder.HELPER_NAME)

    def spliced(new_init=None, new_helper=None, drop_helper=False, extra=()):
        changed = []
        for entry in entries:
            if entry["name"] == "init" and new_init is not None:
                entry = {**entry, "data": new_init}
            if entry["name"] == builder.HELPER_NAME:
                if drop_helper:
                    continue
                if new_helper is not None:
                    entry = {**entry, "data": new_helper}
            changed.append(entry)
        payload = modules.encode_newc(changed + list(extra), trailer)
        return builder.assemble(stock, vendor.encode_frame(payload, library))[0]

    def edited(old, new, count=1):
        require(good_init.count(old) == count, f"fixture anchor missing: {old!r}")
        return good_init.replace(old, new)

    case("init without timer", TIMER_MSG, spliced(edited(builder.TIMER, b"")))
    moved = edited(builder.TIMER, b"").replace(
        builder.LOOP_START, builder.LOOP_START + builder.TIMER)
    case("timer inside the module loop", TIMER_MSG, spliced(moved))
    case("timer after the module loop", TIMER_MSG, spliced(
        edited(builder.TIMER, b"").replace(builder.LOAD_END, builder.LOAD_END + builder.TIMER)))
    case("timer without keep file", TIMER_MSG, spliced(edited(b"/run/keep", b"/run/hold")))
    case("loading marker removed", MARKER_MSG, spliced(edited(builder.MARKER, b"")))
    case("loading marker after insmod", MARKER_MSG, spliced(
        edited(builder.MARKER, b"").replace(builder.INSMOD, builder.INSMOD + builder.MARKER)))
    case("reboot-reason bind check removed", BIND_MSG, spliced(edited(builder.BIND_CHECK, b"")))
    case("changed module list", LIST_MSG, spliced(
        edited(b"gh_arm_drv.ko\nphy-qcom-ufs.ko\n", b"phy-qcom-ufs.ko\ngh_arm_drv.ko\n")))
    case("helper missing", HELPER_MSG, spliced(drop_helper=True))
    dynamic = bytearray(good_helper)
    phoff = int.from_bytes(dynamic[32:40], "little")
    phsize = int.from_bytes(dynamic[54:56], "little")
    dynamic[phoff + phsize:phoff + phsize + 4] = (3).to_bytes(4, "little")
    case("helper with an interpreter", HELPER_MSG, spliced(new_helper=bytes(dynamic)))
    case("helper not aarch64", HELPER_MSG, spliced(
        new_helper=good_helper[:18] + (62).to_bytes(2, "little") + good_helper[20:]))
    case("helper altered byte", HELPER_MSG, spliced(new_helper=flipped(good_helper, 300)))
    case("helper truncated", HELPER_MSG, spliced(new_helper=good_helper[:-8]))
    planted = {"name": "lib/modules/outside-closure.ko",
               "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 31, 0],
               "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}
    case("ramdisk carrying a .ko", KO_MSG, spliced(extra=[planted]))

    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("self-recovering negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (11, 12) and (len(args) == 11 or args[0] == "--self-test"),
            "usage: verify-init-boot-self-recovering.py [--self-test] CANDIDATE STOCK_INIT "
            "GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    paths = [pathlib.Path(path).read_bytes() for path in args]
    if self_test_mode:
        self_test(*paths)
        return
    digest, order, outside, cpio, frame = check_candidate(*paths, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} bytes")
    print(f"self-recovery timer: {builder.TIMER_BUDGET} s subshell before the module loop; "
          "loading marker precedes the only insmod; qcom-reboot-reason bind check follows")
    print(f"helper: static aarch64 ELF, {builder.HELPER_SIZE} bytes, "
          f"SHA-256 {builder.HELPER_SHA256}")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from cdb9458f, 3932504a, f4a00ce3, baa33fd4 "
          "and every prior SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
