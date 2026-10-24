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


builder = load("build-init-boot-wlan-rfkill-payload.py", "wlan_rfkill_builder")
super_mod = load("super-wlan-closure.py", "super_wlan_closure")
previous = load("verify-init-boot-wlan-closure.py", "wlan_closure_checker")
checker = previous.checker
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
REQUIRED_PRIOR = (*previous.REQUIRED_PRIOR, "2faab7e2")
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
DELTA_MSG = builder.DELTA_MSG
FROZEN_MSG = builder.FROZEN_MSG
ENVELOPE_MSG = builder.ENVELOPE_MSG
MOUNT_MSG = builder.MOUNT_MSG
MODULE_MSG = builder.MODULE_MSG
FIRMWARE_MSG = builder.FIRMWARE_MSG
WLAN_MARKER_MSG = builder.old.WLAN_MARKER_MSG
RFKILL_MSG = super_mod.RFKILL_MSG
BY_NAME_MSG = super_mod.BY_NAME_MSG


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


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
    wlan_offset = builder.check_init(init, order)
    require(init_entries[0]["mode"] & 0o170777 == 0o100755, DELTA_MSG)
    eud.check_helper(helper_input)
    require(helper_entries[0]["data"] == helper_input and
            helper_entries[0]["mode"] & 0o170777 == 0o100755, eud.HELPER_MSG)
    frozen = builder.old.frozen_init(order)
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
    return digest, order, outside, decoded, expected, wlan_offset


def self_test(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input):
    library = base.lz4()
    digest, order, outside, cpio, frame, wlan_offset = check_candidate(
        candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, library)
    print(f"init_boot wlan-rfkill fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, source, boot,
                         vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, library)

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

    case("loop minor guessed as the loop index (run-27 regression)", MOUNT_MSG, spliced(edited(
        b'/bin/busybox mknod "$LOOPNODE" b "${LOOPNUM%%:*}" "${LOOPNUM##*:}"',
        b'/bin/busybox mknod "/dev/loop$2" b "${LOOPNUM%%:*}" "$2"')))
    case("fstype assumed erofs without the magic probe", MOUNT_MSG, spliced(edited(
        b'/bin/busybox hexdump -n 4 -s 1024', b'/bin/busybox true -n 4 -s 1024')))
    case("system_dlkm mount removed", MOUNT_MSG, spliced(edited(
        b"if wlan_loop system_dlkm_a 10 4797235200 /mnt/system_dlkm; then", b"if false; then")))
    case("system_dlkm_a and vendor_a mounted from a second guessed super loop", MOUNT_MSG,
         spliced(edited(b"wlan_loop system_dlkm_a 10 4797235200 /mnt/system_dlkm",
                        b"wlan_loop system_dlkm_a 10 4797235200 /mnt/super/system_dlkm")))
    case("rfkill.ko loaded from vendor_dlkm instead of system_dlkm", MODULE_MSG, spliced(edited(
        b"\trfkill.ko)\n\t\tKOPATH=/mnt/system_dlkm/lib/modules/6.1.84-android14-11-"
        b"gf4b0d69fdf34-ab12786779/kernel/net/rfkill/rfkill.ko ;;",
        b"\trfkill.ko)\n\t\tKOPATH=/mnt/vendor_dlkm/lib/modules/rfkill.ko ;;")))
    missing_rfkill = HERE / "fixtures" / "system_dlkm" / super_mod.RFKILL_PATH
    require(not missing_rfkill.exists(), "rfkill-absent fixture unexpectedly contains rfkill.ko")
    expect_rejection("rfkill.ko absent from verified system_dlkm", RFKILL_MSG,
                     super_mod.verify_rfkill, missing_rfkill)
    expect_rejection("vendor_a by-name device falsely claimed", BY_NAME_MSG,
                     super_mod.verify_by_name, HERE / "fixtures" / "vendor_a.by-name.absent")
    case("cfg80211 loaded before rfkill", MODULE_MSG, spliced(edited(
        b"qcom_q6v5_pas.ko\nrfkill.ko\ncfg80211.ko\n",
        b"qcom_q6v5_pas.ko\ncfg80211.ko\nrfkill.ko\n")))
    case("rfkill.ko removed from the closure entirely", MODULE_MSG, spliced(edited(
        b"rfkill.ko\ncfg80211.ko\n", b"cfg80211.ko\n")))
    case("modem_a firmware mount removed", FIRMWARE_MSG, spliced(edited(
        b"mount -t vfat -o ro,nosuid,nodev,noexec /dev/block/sde6 /vendor/firmware_mnt",
        b"true # -t vfat -o ro,nosuid,nodev,noexec /dev/block/sde6 /vendor/firmware_mnt")))
    case("modem_a fstype assumed without the FAT probe", FIRMWARE_MSG, spliced(edited(
        b'/bin/busybox hexdump -n 8 -s 82', b'/bin/busybox true # -n 8 -s 82')))
    case("firmware mountpoint moved off the stock path", FIRMWARE_MSG, spliced(edited(
        b"/vendor/firmware_mnt/image/qca6750/bdwlan.elf",
        b"/mnt/modem/image/qca6750/bdwlan.elf")))
    case("planted .ko", KO_MSG, spliced(extra=[{
        "name": "lib/modules/outside-wlan.ko",
        "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 21, 0],
        "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}]))
    case("timer removed", TIMER_MSG, spliced(edited(eud.TIMER, b"")))
    case("timer lengthened", TIMER_MSG, spliced(edited(b"\tsleep 150\n", b"\tsleep 180\n")))
    case("wlan-init begin marker removed", WLAN_MARKER_MSG, spliced(edited(
        builder.WLAN_BEGIN, b"")))
    case("wlan-init begin marker duplicated", WLAN_MARKER_MSG, spliced(edited(
        builder.WLAN_BEGIN, builder.WLAN_BEGIN * 2)))
    expect_rejection("frozen #53 already carrying wlan-init", FROZEN_MSG,
                     builder.old.require_frozen, good_init, order)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES and wlan_offset > 0, SHA_MSG)
    print("wlan-rfkill negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (11, 12) and (len(args) == 11 or args[0] == "--self-test"),
            "usage: verify-init-boot-wlan-rfkill.py [--self-test] CANDIDATE STOCK_INIT "
            "GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    paths = [pathlib.Path(path).read_bytes() for path in args]
    if self_test_mode:
        self_test(*paths)
        return
    digest, order, outside, cpio, frame, wlan_offset = check_candidate(*paths, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} bytes")
    print(f"wlan-init phase at offset {wlan_offset}: probed super extents through "
          f"sysfs-derived loop nodes (system_dlkm_a, vendor_a, vendor_dlkm_a), modem_a "
          f"firmware vfat mount, rfkill before cfg80211, capped logging")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper "
          f"{eud.HELPER_SIZE} bytes, SHA-256 {eud.HELPER_SHA256}")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from 2faab7e2 and every prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
