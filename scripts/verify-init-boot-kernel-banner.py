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


builder = load("build-init-boot-kernel-banner-payload.py", "kernel_banner_builder")
static_checker = load("verify-init-boot-static-address.py", "static_address_checker")
checker = static_checker.checker
eud = builder.eud
vendor = eud.vendor
base = builder.base
modules = builder.modules
static = builder.static
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = ("9f89fe8d", "995aaca3", "88c93077", "8f8b7331", "55fa78ca",
                  "5a513998", "dc990b95", "13a48ff9", "37535dd1", "bde3a3b3",
                  "6078269d")
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
VENDOR_MSG = checker.VENDOR_MSG
SHA_MSG = builder.SHA_MSG
KO_MSG = builder.KO_MSG
SOURCE_MSG = eud.SOURCE_MSG
TIMER_MSG = builder.TIMER_MSG
LIST_MSG = builder.LIST_MSG
BANNER_MSG = builder.BANNER_MSG
DELTA_MSG = builder.DELTA_MSG
FROZEN_MSG = builder.FROZEN_MSG
ENVELOPE_MSG = builder.ENVELOPE_MSG


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images and digest != builder.MEASURED_STATIC and
            digest != builder.MEASURED_PAYLOAD and digest != static.MEASURED_PERIPHERAL,
            SHA_MSG)


def check_candidate(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
                    decompressor, pstore, helper_input, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    vendor.check_stock(stock, library)
    vendor_files, recovery_entries = vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, LIST_MSG)
    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = checker.decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    init_entries = [entry for entry in entries if entry["name"] == "init"]
    require(len(init_entries) == 1, DELTA_MSG)
    helper_entries = [entry for entry in entries if entry["name"] == eud.HELPER_NAME]
    require(len(helper_entries) == 1, eud.HELPER_MSG)
    init = init_entries[0]["data"]
    banner = builder.check_init(init, order)
    require(init_entries[0]["mode"] & 0o170777 == 0o100755, DELTA_MSG)
    eud.check_helper(helper_input)
    require(helper_entries[0]["data"] == helper_input and
            helper_entries[0]["mode"] & 0o170777 == 0o100755, eud.HELPER_MSG)
    frozen = builder.frozen_init(order)
    require(init == builder.expected_init(frozen), DELTA_MSG)
    _, source_entries, _ = vendor.source_cpio(source)
    candidate_entries = [entry for entry in entries if entry["name"] != eud.HELPER_NAME]
    require([entry["name"] for entry in candidate_entries] ==
            [entry["name"] for entry in source_entries], SOURCE_MSG)
    untouched = [(entry, original)
                 for entry, original in zip(candidate_entries, source_entries)
                 if entry["name"] != "init"]
    require(all(entry["data"] == original["data"] and entry["mode"] == original["mode"] and
                entry["fields"][:6] == original["fields"][:6] and
                entry["fields"][7:13] == original["fields"][7:13]
                for entry, original in untouched), SOURCE_MSG)
    try:
        modules.prove_vendor_modules(vendor_files, entries, recovery_entries)
    except ValueError as exc:
        raise ValueError(VENDOR_MSG) from exc
    expected = vendor.encode_frame(decoded, library)
    require(expected == candidate[PAGE:PAGE + frame_size], BLOCK_MSG)
    require(len(expected) <= base.MAX_FRAME, ENVELOPE_MSG)
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
    return digest, order, outside, decoded, expected, banner


def self_test(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input):
    library = base.lz4()
    digest, order, outside, cpio, frame, banner = check_candidate(
        candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, library)
    print(f"init_boot kernel-banner fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, source, boot,
                         vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, library)

    case("changed signed tail", TAIL_MSG, flipped(candidate, TAIL_OFFSET + 100))
    case("changed footer byte", TAIL_MSG, flipped(candidate, IMAGE_SIZE - 1))
    case("changed AVB0 header byte", TAIL_MSG, flipped(candidate, TAIL_OFFSET))
    case("second changed header field", HEADER_MSG, flipped(candidate, 16))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, flipped(candidate, PAGE + 64))
    case("modern LZ4 frame magic", FRAME_MSG,
         candidate[:PAGE] + b"\x04\x22\x4d\x18" + candidate[PAGE + 4:])
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("ramdisk size beyond the stock envelope", FRAME_MSG,
         candidate[:RAMDISK_SIZE_OFFSET] + struct.pack("<I", base.MAX_FRAME + 1) +
         candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")
    good_init = next(entry["data"] for entry in entries if entry["name"] == "init")

    def spliced(new_init=None, extra=()):
        changed = [{**entry, "data": new_init} if entry["name"] == "init" and
                   new_init is not None else entry for entry in entries]
        payload = modules.encode_newc(changed + list(extra), trailer)
        return builder.assemble(stock, vendor.encode_frame(payload, library))[0]

    def edited(old, new, count=1):
        require(good_init.count(old) == count, f"fixture anchor missing: {old!r}")
        return good_init.replace(old, new)

    expect_rejection("banner log removed rebuilds measured #53 image", SHA_MSG,
                     spliced, edited(builder.BANNER, b""))
    case("banner log duplicated", BANNER_MSG, spliced(edited(
        builder.BANNER, builder.BANNER * 2)))
    case("banner log moved", BANNER_MSG, spliced(edited(builder.BANNER, b"").replace(
        b"log 'console ready'\n", builder.BANNER + b"log 'console ready'\n")))
    case("banner reports uname -a", BANNER_MSG, spliced(edited(
        b"uname -r 2>&1", b"uname -a 2>&1")))
    case("second diagnostic line", static.DELTA_MSG, spliced(edited(
        builder.BANNER, builder.BANNER + b"log 'kernel banner extra'\n")))
    case("timer removed", TIMER_MSG, spliced(edited(eud.TIMER, b"")))
    case("timer lengthened", TIMER_MSG, spliced(edited(b"\tsleep 150\n", b"\tsleep 180\n")))
    case("changed module order", eud.LIST_MSG, spliced(edited(
        b"gh_arm_drv.ko\nphy-qcom-ufs.ko\n", b"phy-qcom-ufs.ko\ngh_arm_drv.ko\n")))
    case("second role write", static.peripheral.WRITE_COUNT_MSG, spliced(edited(
        static.peripheral.ROLE_WRITE, static.peripheral.ROLE_WRITE * 2)))
    case("changed gadget function", static.DELTA_MSG, spliced(edited(
        b"$G/functions/ncm.usb0", b"$G/functions/rndis.usb0", count=2)))
    case("address log removed", static.ADDRESS_COUNT_MSG, spliced(edited(
        b"\t\t\tlog 'usb0 address 172.16.42.2/24: added'\n", b"")))
    planted = {"name": "lib/modules/outside-closure.ko",
               "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 31, 0],
               "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}
    case("planted .ko", KO_MSG, spliced(extra=[planted]))
    expect_rejection("frozen #53 already carrying the banner", FROZEN_MSG,
                     builder.require_frozen, good_init, order)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES and banner > 0, SHA_MSG)
    print("kernel-banner negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (11, 12) and (len(args) == 11 or args[0] == "--self-test"),
            "usage: verify-init-boot-kernel-banner.py [--self-test] CANDIDATE STOCK_INIT "
            "GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    paths = [pathlib.Path(path).read_bytes() for path in args]
    if self_test_mode:
        self_test(*paths)
        return
    digest, order, outside, cpio, frame, banner = check_candidate(*paths, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} bytes")
    print(f"kernel banner at init offset {banner}: uname -r and /proc/version, one line")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper "
          f"{eud.HELPER_SIZE} bytes, SHA-256 {eud.HELPER_SHA256}")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from 995aaca3, 9f89fe8d, 37535dd1 and every prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
