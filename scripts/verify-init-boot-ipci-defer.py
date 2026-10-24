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


builder = load("build-init-boot-ipci-defer-payload.py", "ipci_defer_builder")
rfkill_checker = load("verify-init-boot-wlan-rfkill.py", "wlan_rfkill_checker")
checker = rfkill_checker.checker
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
REQUIRED_PRIOR = (*rfkill_checker.REQUIRED_PRIOR, "9291c369")
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
MOUNT_MSG = rfkill_checker.MOUNT_MSG
MODULE_MSG = rfkill_checker.MODULE_MSG
FIRMWARE_MSG = rfkill_checker.FIRMWARE_MSG
WLAN_MARKER_MSG = builder.WLAN_MARKER_MSG
DEFER_MSG = builder.DEFER_MSG


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
    frozen = builder.rfkill.frozen_init(order)
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
    print(f"init_boot ipci-defer fixture: OK ({digest})")
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
        return static.peripheral.assemble(stock, vendor.encode_frame(payload, library))[0]

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

    gate = builder.BIND_GATE.encode()
    insmod = builder.INS_MOD.encode()
    case("bind gate removed (run-28 regression)", DEFER_MSG, spliced(edited(gate, b"")))
    case("bind gate duplicated", DEFER_MSG, spliced(edited(
        gate + insmod, gate + gate + insmod)))
    case("bind gate applied to every module", DEFER_MSG, spliced(edited(
        b'\tif [ "$module" = qca_cld3_qca6750.ko ]; then',
        b'\tif true; then')))
    case("bind gate moved after the insmod", DEFER_MSG, spliced(edited(
        gate + insmod, insmod + gate)))
    case("bind gate wait lengthened", DEFER_MSG, spliced(edited(
        b'"$bind_wait" -lt 12 ]', b'"$bind_wait" -lt 60 ]')))
    case("bind gate wait removed", DEFER_MSG, spliced(edited(
        b'while [ "$bind_wait" -lt 12 ] && [ ! -e /sys/bus/platform/devices/17110040.qcom,wcn6750/driver ]; do',
        b'while false; do')))
    case("icnss2 bind check retargeted", DEFER_MSG, spliced(edited(
        b"/sys/bus/platform/devices/17110040.qcom,wcn6750/driver",
        b"/sys/bus/platform/devices/17110041.qcom,wcn6750/driver", count=2)))
    case("wpss bind check removed", DEFER_MSG, spliced(edited(
        b'\t\tif [ -e /sys/bus/platform/devices/9bb00000.remoteproc-wpss/driver ]; then\n'
        b'\t\t\twlog "ipci gate: wpss bound"\n'
        b'\t\telse\n'
        b'\t\t\twlog "ipci gate: wpss unbound"\n'
        b'\t\tfi\n', b"")))
    case("bind gate logging removed", DEFER_MSG, spliced(edited(
        b'wlog "ipci gate: icnss2 unbound after $bind_wait s"',
        b'true # ipci gate: icnss2 unbound after $bind_wait s')))
    case("gate sleep unbounded", DEFER_MSG, spliced(edited(
        b'\t\t\tsleep 1\n\t\t\tbind_wait=$((bind_wait + 1))',
        b'\t\t\ttrue\n\t\t\tbind_wait=$((bind_wait + 1))')))
    case("loop-minor regression reimported", MOUNT_MSG, spliced(edited(
        b'/bin/busybox mknod "$LOOPNODE" b "${LOOPNUM%%:*}" "${LOOPNUM##*:}"',
        b'/bin/busybox mknod "/dev/loop$2" b "${LOOPNUM%%:*}" "$2"')))
    case("rfkill.ko loaded from vendor_dlkm", MODULE_MSG, spliced(edited(
        b"\trfkill.ko)\n\t\tKOPATH=/mnt/system_dlkm/lib/modules/6.1.84-android14-11-"
        b"gf4b0d69fdf34-ab12786779/kernel/net/rfkill/rfkill.ko ;;",
        b"\trfkill.ko)\n\t\tKOPATH=/mnt/vendor_dlkm/lib/modules/rfkill.ko ;;")))
    case("cfg80211 loaded before rfkill", MODULE_MSG, spliced(edited(
        b"qcom_q6v5_pas.ko\nrfkill.ko\ncfg80211.ko\n",
        b"qcom_q6v5_pas.ko\ncfg80211.ko\nrfkill.ko\n")))
    case("planted .ko", KO_MSG, spliced(extra=[{
        "name": "lib/modules/outside-wlan.ko",
        "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 21, 0],
        "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}]))
    case("timer removed", TIMER_MSG, spliced(edited(eud.TIMER, b"")))
    case("timer lengthened", TIMER_MSG, spliced(edited(b"\tsleep 150\n", b"\tsleep 180\n")))
    case("wlan-init begin marker removed", WLAN_MARKER_MSG, spliced(edited(
        builder.WLAN_BEGIN, b"")))
    expect_rejection("frozen #53 already carrying wlan-init", FROZEN_MSG,
                     builder.rfkill.old.require_frozen, good_init, order)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES and wlan_offset > 0, SHA_MSG)
    print("ipci-defer negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (11, 12) and (len(args) == 11 or args[0] == "--self-test"),
            "usage: verify-init-boot-ipci-defer.py [--self-test] CANDIDATE STOCK_INIT "
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
    print(f"wlan-init phase at offset {wlan_offset}: unchanged corrected mounts and "
          f"21-module closure; the final qca_cld3_qca6750.ko insmod is preceded by a "
          f"{builder.WAIT_SECONDS} s bounded icnss2 bind wait that logs the WPSS and "
          f"icnss2 platform driver bind states")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper "
          f"{eud.HELPER_SIZE} bytes, SHA-256 {eud.HELPER_SHA256}")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from 9291c369 and every prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
