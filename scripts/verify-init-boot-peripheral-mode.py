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


builder = load("build-init-boot-peripheral-mode-payload.py", "peripheral_builder")
eud_builder = builder.eud
checker = load("verify-init-boot-vendor-modules.py", "vendor_checker")
vendor = eud_builder.vendor
base = builder.base
modules = builder.modules
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
MEASURED_EUD = builder.MEASURED_EUD
REQUIRED_PRIOR = ("8f8b7331", "bde3a3b3", "6078269d", "cdb9458f", "3932504a",
                  "f4a00ce3", "baa33fd4", "23725940", "197aff11", "88c93077")
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
SOURCE_MSG = builder.eud.SOURCE_MSG
TIMER_MSG = builder.TIMER_MSG
MARKER_MSG = builder.eud.MARKER_MSG
BIND_MSG = builder.eud.BIND_MSG
HELPER_MSG = builder.eud.HELPER_MSG
LIST_MSG = builder.LIST_MSG
EUD_ORDER_MSG = builder.eud.EUD_ORDER_MSG
EUD_MISSING_MSG = builder.eud.EUD_MISSING_MSG
EUD_LOG_MSG = builder.EUD_LOG_MSG
CHILD_MSG = builder.CHILD_MSG
DEFERRED_MSG = builder.DEFERRED_MSG
DMESG_MSG = builder.DMESG_MSG
DELTA_MSG = builder.DELTA_MSG
FROZEN_MSG = builder.FROZEN_MSG
MISSING_WRITE_MSG = builder.MISSING_WRITE_MSG
WRITE_COUNT_MSG = builder.WRITE_COUNT_MSG
WRITE_ORDER_MSG = builder.WRITE_ORDER_MSG
EUD_BEFORE_MSG = builder.EUD_BEFORE_MSG
VALUE_MSG = builder.VALUE_MSG
PATH_MSG = builder.PATH_MSG
WAIT_MSG = builder.WAIT_MSG
READ_MSG = builder.READ_MSG
FIXED_MSG = "candidate init or helper differs from the committed sources"
ENVELOPE_MSG = builder.ENVELOPE_MSG


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images and digest != MEASURED_EUD, SHA_MSG)


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
    helper_entries = [entry for entry in entries if entry["name"] == eud_builder.HELPER_NAME]
    require(len(helper_entries) == 1, HELPER_MSG)
    init = init_entries[0]["data"]
    write = builder.check_init(init, order)
    require(init_entries[0]["mode"] & 0o170777 == 0o100755, DELTA_MSG)
    eud_builder.check_helper(helper_input)
    require(helper_entries[0]["data"] == helper_input and
            helper_entries[0]["mode"] & 0o170777 == 0o100755, HELPER_MSG)
    require(init == (HERE.parent / "initramfs" / builder.INIT_SOURCE).read_bytes(), FIXED_MSG)
    _, source_entries, _ = vendor.source_cpio(source)
    candidate_entries = [entry for entry in entries
                         if entry["name"] != eud_builder.HELPER_NAME]
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
    return digest, order, outside, decoded, expected, write


def self_test(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input):
    library = base.lz4()
    digest, order, outside, cpio, frame, write = check_candidate(
        candidate, stock, source, boot, vendor_boot, recovery, config, kernel, decompressor,
        pstore, helper_input, library)
    print(f"init_boot peripheral-mode fixture: OK ({digest})")
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
    case("zero ramdisk size", FRAME_MSG,
         candidate[:RAMDISK_SIZE_OFFSET] + struct.pack("<I", 0) +
         candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")
    good_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    good_helper = next(entry["data"] for entry in entries
                       if entry["name"] == eud_builder.HELPER_NAME)

    def spliced(new_init=None, new_helper=None, drop_helper=False, extra=()):
        changed = []
        for entry in entries:
            if entry["name"] == "init" and new_init is not None:
                entry = {**entry, "data": new_init}
            if entry["name"] == eud_builder.HELPER_NAME:
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

    role = builder.ROLE_WRITE
    case("mode write removed", MISSING_WRITE_MSG, spliced(edited(role, b"")))
    case("mode write duplicated", WRITE_COUNT_MSG, spliced(edited(role, role + role)))
    case("host value instead of peripheral", VALUE_MSG,
         spliced(edited(b"printf 'peripheral'", b"printf 'host'")))
    case("empty value instead of peripheral", VALUE_MSG,
         spliced(edited(b"printf 'peripheral'", b"printf 'none'")))
    case("hardcoded SoC mode path", PATH_MSG, spliced(
        edited(b'printf \'peripheral\' >"$GLUE/mode"',
               b'printf \'peripheral\' >/sys/devices/platform/soc/a600000.ssusb/mode')))
    inside_loop = edited(role, b"").replace(
        eud_builder.LOOP_START, eud_builder.LOOP_START + role)
    case("mode write before eud.ko/dwc3-msm.ko load", EUD_BEFORE_MSG, spliced(inside_loop))
    before_end = edited(role, b"").replace(
        eud_builder.LOAD_END, role + eud_builder.LOAD_END)
    case("mode write before module phase end", WRITE_ORDER_MSG, spliced(before_end))
    after_wait = edited(role, b"").replace(
        builder.UDC_WAIT, builder.UDC_WAIT + role)
    case("mode write after the UDC wait", WAIT_MSG, spliced(after_wait))
    case("UDC wait shortened below ten seconds", WAIT_MSG, spliced(
        edited(builder.UDC_WAIT, builder.UDC_WAIT.replace(b'-lt 40', b'-lt 10'))))
    case("mode read after the write removed", READ_MSG, spliced(
        edited(builder.MODE_READ_AFTER,
               builder.MODE_READ_AFTER.replace(b"mode readback", b"mode echoed"))))
    case("mode read before the write removed", READ_MSG, spliced(
        edited(builder.MODE_READ_BEFORE,
               builder.MODE_READ_BEFORE.replace(b"mode before", b"mode earlier"))))
    case("timer removed", TIMER_MSG, spliced(edited(eud_builder.TIMER, b"")))
    case("timer moved after the module loop", TIMER_MSG, spliced(
        edited(eud_builder.TIMER, b"").replace(
            eud_builder.LOAD_END, eud_builder.LOAD_END + eud_builder.TIMER)))
    case("timer moved inside the module loop", TIMER_MSG, spliced(
        edited(eud_builder.TIMER, b"").replace(
            eud_builder.LOOP_START, eud_builder.LOOP_START + eud_builder.TIMER)))
    case("timer budget changed", TIMER_MSG, spliced(
        edited(b"\tsleep 150\n", b"\tsleep 30\n")))
    case("loading marker removed", MARKER_MSG, spliced(edited(eud_builder.MARKER, b"")))
    case("reboot-reason bind check removed", BIND_MSG, spliced(
        edited(b"qcom-reboot-reason not bound", b"qcom-reboot-reason unseen")))
    case("EUD read-only check removed", EUD_LOG_MSG, spliced(
        edited(b"\tlog 'eud not bound'\n", b"")))
    case("child check removed", CHILD_MSG, spliced(edited(builder.CHILD_CHECK, b"")))
    case("child check moved before the bound checks", CHILD_MSG, spliced(
        edited(builder.CHILD_CHECK, b"").replace(
            b'UDC_NAMES=""\n', builder.CHILD_CHECK + b'UDC_NAMES=""\n')))
    case("old deferred logging restored", DEFERRED_MSG, spliced(
        edited(builder.NEW_DEFERRED, builder.OLD_DEFERRED)))
    case("deferred cap changed", DEFERRED_MSG, spliced(
        edited(builder.NEW_DEFERRED,
               builder.NEW_DEFERRED.replace(b'-lt 64', b'-lt 640'))))
    case("dmesg capture removed", DMESG_MSG, spliced(edited(builder.DMESG_BLOCK, b"")))
    case("dmesg capture moved before deferred logging", DMESG_MSG, spliced(
        edited(builder.DMESG_BLOCK, b"").replace(
            builder.NEW_DEFERRED, builder.DMESG_BLOCK + builder.NEW_DEFERRED)))
    case("dmesg capture cleared", DMESG_MSG, spliced(
        edited(b"/bin/busybox dmesg 2>&1", b"/bin/busybox dmesg -c 2>&1")))
    case("eud.ko missing", EUD_MISSING_MSG, spliced(
        edited(b"wcd_usbss_i2c.ko\neud.ko\n", b"wcd_usbss_i2c.ko\n")))
    case("eud.ko after dwc3-msm.ko", EUD_ORDER_MSG, spliced(
        edited(b"eud.ko\ndwc3-msm.ko\n", b"dwc3-msm.ko\neud.ko\n")))
    case("changed old module order", builder.eud.LIST_MSG, spliced(
        edited(b"gh_arm_drv.ko\nphy-qcom-ufs.ko\n", b"phy-qcom-ufs.ko\ngh_arm_drv.ko\n")))
    case("module dropped from the list", builder.eud.LIST_MSG, spliced(
        edited(b"dwc3-msm.ko\n'\n", b"'\n")))
    case("helper missing", HELPER_MSG, spliced(drop_helper=True))
    dynamic = bytearray(good_helper)
    phoff = int.from_bytes(dynamic[32:40], "little")
    phsize = int.from_bytes(dynamic[54:56], "little")
    dynamic[phoff + phsize:phoff + phsize + 4] = (3).to_bytes(4, "little")
    case("helper with an interpreter", HELPER_MSG, spliced(new_helper=bytes(dynamic)))
    case("helper altered byte", HELPER_MSG, spliced(new_helper=flipped(good_helper, 300)))
    planted = {"name": "lib/modules/outside-closure.ko",
               "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 31, 0],
               "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}
    case("ramdisk carrying a .ko", KO_MSG, spliced(extra=[planted]))
    case("second changed ramdisk entry", SOURCE_MSG, spliced(
        extra=[{"name": "outside-closure-fixture",
                "fields": [0, 0o100644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 11, 0],
                "mode": 0o100644, "data": b""}]))
    expect_rejection("frozen #49 already carrying the delta", FROZEN_MSG,
                     builder.require_frozen, good_init)

    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    expect_rejection("measured #49 SHA 88c93077", SHA_MSG, reject_prior_sha, MEASURED_EUD)
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES and digest != MEASURED_EUD, SHA_MSG)
    print("peripheral-mode negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (11, 12) and (len(args) == 11 or args[0] == "--self-test"),
            "usage: verify-init-boot-peripheral-mode.py [--self-test] CANDIDATE STOCK_INIT "
            "GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    paths = [pathlib.Path(path).read_bytes() for path in args]
    if self_test_mode:
        self_test(*paths)
        return
    digest, order, outside, cpio, frame, write = check_candidate(*paths, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} bytes")
    print(f"role write: one peripheral write at init offset {write}, discovered $GLUE/mode, "
          "read-only logs before and after")
    print("placement: after module load end and eud.ko/dwc3-msm.ko, before the 10 s UDC wait")
    print(f"self-recovery timer: {eud_builder.TIMER_BUDGET} s, unchanged; helper "
          f"{eud_builder.HELPER_SIZE} bytes, SHA-256 {eud_builder.HELPER_SHA256}")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from 88c93077, 8f8b7331, bde3a3b3, 6078269d, cdb9458f "
          "and every prior SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
