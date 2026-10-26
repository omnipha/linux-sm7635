#!/usr/bin/env python3
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


builder = load("build-init-boot-psoc-hold-capture-payload.py", "psoc_hold_capture_builder")
psoc_checker = load("verify-init-boot-psoc-hold.py", "psoc_hold_checker")
psoc = builder.psoc
prior = builder.prior
wpss = psoc_checker.wpss
base_checker = psoc_checker.base_checker
base = builder.base
modules = builder.modules
eud = builder.eud
vendor = eud.vendor
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (*psoc_checker.REQUIRED_PRIOR, "0b40ac34")
require = wpss.require
expect_rejection = wpss.expect_rejection
decode_frame = wpss.decode_frame
SIZE_MSG = wpss.SIZE_MSG
KERNEL_MSG = wpss.KERNEL_MSG
HEADER_MSG = wpss.HEADER_MSG
FRAME_MSG = wpss.FRAME_MSG
BLOCK_MSG = wpss.BLOCK_MSG
GAP_MSG = wpss.GAP_MSG
TAIL_MSG = wpss.TAIL_MSG
SHA_MSG = builder.SHA_MSG
KO_MSG = wpss.KO_MSG
ENVELOPE_MSG = wpss.ENVELOPE_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
TRIGGER_MSG = builder.TRIGGER_MSG
ON_WRITE = b'printf "ON             " >/dev/wlan'
HOLD_CAP = b"/bin/busybox timeout -k 1 25 "
WPSS_PATH = b"/sys/kernel/icnss/wpss_boot"


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def check_candidate(candidate, run39, run38, run37, stock, source, boot, vendor_boot,
                    recovery, config, kernel, decompressor, pstore, helper_input, pdmapper,
                    tqftpserv, rmtfs_binary, sharedmem, maps, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(modules.sha256(run39) == builder.MEASURED_RUN39 and len(run39) == IMAGE_SIZE,
            "run-39 reference is not the measured 0b40ac34 image")
    require(modules.sha256(run38) == psoc.MEASURED_RUN38 and len(run38) == IMAGE_SIZE,
            "run-38 reference is not the measured e75c5bd2 image")
    require(modules.sha256(run37) == prior.MEASURED_RUN37 and len(run37) == IMAGE_SIZE,
            "run-37 reference is not the measured d9d8d2b8 image")
    _, order, outside, verified_run39_cpio, _ = psoc_checker.check_candidate(
        run39, run38, run37, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs_binary, sharedmem,
        maps, library)

    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    by_name = {}
    for entry in entries:
        require(entry["name"] not in by_name, CPIO_MSG)
        by_name[entry["name"]] = entry

    run39_frame_size = struct.unpack_from("<I", run39, RAMDISK_SIZE_OFFSET)[0]
    run39_decoded = decode_frame(run39[PAGE:PAGE + run39_frame_size], library)
    run39_entries, _ = modules.parse_newc(run39_decoded, "run-39 debug cpio")
    run39_by_name = {entry["name"]: entry for entry in run39_entries}
    run39_init = next(entry["data"] for entry in run39_entries if entry["name"] == "init")
    run39_trigger = next(entry["data"] for entry in run39_entries
                         if entry["name"] == "bin/wpss-once")
    require(run39_trigger == builder.expected_trigger() and
            run39_init.count(psoc.MARKER) == 1 and
            run39_decoded == verified_run39_cpio and
            psoc.assemble(stock, vendor.encode_frame(run39_decoded, library))[0] == run39,
            "run-39 reference differs from the reproducible measured #109 image")

    init = by_name["init"]["data"]
    trigger = by_name["bin/wpss-once"]["data"]
    require(by_name["init"]["mode"] & 0o170777 == 0o100755, INIT_MSG)
    require(by_name["bin/wpss-once"]["mode"] & 0o170777 == 0o100755, TRIGGER_MSG)
    builder.check_init(init, run39_init)
    builder.check_trigger(trigger)
    require(trigger == run39_trigger, TRIGGER_MSG)
    require(trigger.count(ON_WRITE) == 1 and trigger.count(HOLD_CAP) == 1, TRIGGER_MSG)
    require(trigger.count(WPSS_PATH) == psoc.OLD_TRIGGER.count(WPSS_PATH) and
            trigger.count(b'printf "1\\n" >/sys/kernel/icnss/wpss_boot') == 1, TRIGGER_MSG)
    require(init.count(eud.TIMER) == 1 and init.count(b"sleep 150") == 1 and
            init.count(b"/run/keep") == 1 and
            b"/run/keep" not in init[:init.index(eud.TIMER)], INIT_MSG)
    require(init.replace(builder.MARKER, psoc.MARKER, 1) == run39_init and
            run39_init.replace(psoc.MARKER, builder.MARKER, 1) == init, INIT_MSG)
    require(set(by_name) == set(run39_by_name), CPIO_MSG)
    for name, entry in run39_by_name.items():
        mine = by_name[name]
        require(mine["mode"] == entry["mode"] and
                (mine["data"] == entry["data"] or name == "init"), CPIO_MSG)
    require([entry["name"] for entry in entries] ==
            [entry["name"] for entry in run39_entries], CPIO_MSG)

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
    rebuilt = builder.candidate_cpio(run39_decoded)
    require(vendor.encode_frame(rebuilt, library) == expected and
            builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected


def self_test(candidate, run39, run38, run37, stock, source, boot, vendor_boot, recovery,
              config, kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv,
              rmtfs_binary, sharedmem, maps):
    library = base.lz4()
    digest, order, outside, cpio, frame = check_candidate(
        candidate, run39, run38, run37, stock, source, boot, vendor_boot, recovery, config,
        kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs_binary,
        sharedmem, maps, library)
    print(f"init_boot psoc-hold-capture fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")

    def rebuild(changed_entries):
        payload = modules.encode_newc(changed_entries, trailer)
        return psoc.prior.prior.prior.prior.prior.static.peripheral.assemble(
            stock, vendor.encode_frame(payload, library))[0]

    def with_entry(name, data):
        return [{**entry, "data": data} if entry["name"] == name else entry
                for entry in entries]

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, run39, run38, run37,
                         stock, source, boot, vendor_boot, recovery, config, kernel,
                         decompressor, pstore, helper_input, pdmapper, tqftpserv,
                         rmtfs_binary, sharedmem, maps, library)

    case("changed signed tail", TAIL_MSG, wpss.rmtfs.flipped(candidate, TAIL_OFFSET + 100))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, wpss.rmtfs.flipped(candidate, PAGE + 64))
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    init = next(entry["data"] for entry in entries if entry["name"] == "init")
    trigger = next(entry["data"] for entry in entries if entry["name"] == "bin/wpss-once")
    case("25 s-capped hold removed", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.HOLD_START, b"", 1))))
    case("25 s-capped hold duplicated", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.HOLD_START,
                                         psoc.HOLD_START + psoc.HOLD_START, 1))))
    case("25 s-capped hold cap raised", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(HOLD_CAP, b"/bin/busybox timeout -k 1 125 ", 1))))
    case("25 s-capped hold moved after WPSS write", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.HOLD_START, b"", 1).replace(
            psoc.WPSS_RESULT, psoc.WPSS_RESULT + psoc.HOLD_START, 1))))
    case("hold wait removed", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.HOLD_WAIT, b"", 1))))
    case("hold wait moved after observation window", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.HOLD_WAIT, b"", 1).replace(
            psoc.WINDOW, psoc.WINDOW + psoc.HOLD_WAIT, 1))))
    case("/dev/wlan ON write altered", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(ON_WRITE, b'printf "OFF            " >/dev/wlan', 1))))
    case("/dev/wlan ON write removed", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(ON_WRITE, b"/bin/busybox true", 1))))
    case("/dev/wlan ON write retargeted", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(b">/dev/wlan", b">/dev/null", 1))))
    case("/dev/wlan precheck removed", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.PRECHECK, b"", 1))))
    case("window sample removed", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.WINDOW, b"", 1))))
    case("second WPSS write injected", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(
            psoc.WPSS_RESULT,
            psoc.WPSS_RESULT + b"printf '1\\n' >/sys/kernel/icnss/wpss_boot\n", 1))))
    case("wpa_supplicant association injected", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger + b"/bin/busybox wpa_supplicant -i wlan0 &\n")))
    case("rmmod/insmod injected", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger + b"/bin/busybox rmmod qca_cld3_qca6750\n")))
    case("/dev/wlan write injected into init", INIT_MSG, rebuild(with_entry(
        "init", init + b"printf 'ON             ' >/dev/wlan\n")))
    case("150 s timer lengthened", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"\tsleep 150\n", b"\tsleep 180\n", 1))))
    case("150 s timer shortened", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"\tsleep 150\n", b"\tsleep 30\n", 1))))
    case("150 s timer removed", INIT_MSG, rebuild(with_entry(
        "init", init.replace(eud.TIMER, b"", 1))))
    case("/run/keep escape disabled", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"\tif [ ! -e /run/keep ]; then\n", b"\tif false; then\n", 1))))
    case("early /run/keep planted in init", INIT_MSG, rebuild(with_entry(
        "init", init.replace(builder.MARKER, builder.MARKER + b"mkdir -p /run/keep\n", 1))))
    case("#116 marker removed", INIT_MSG, rebuild(with_entry("init",
         init.replace(builder.MARKER, b"", 1))))
    case("#116 marker duplicated", INIT_MSG, rebuild(with_entry(
        "init", init.replace(builder.MARKER, builder.MARKER + builder.MARKER, 1))))
    case("#116 marker reworded", INIT_MSG, rebuild(with_entry(
        "init", init.replace(builder.MARKER,
                             b"log 'session #116: capture-gated rerun'\n", 1))))
    case("marker left at the #109 wording", INIT_MSG, rebuild(with_entry(
        "init", init.replace(builder.MARKER, psoc.MARKER, 1))))
    case("marker left at the #106 wording", INIT_MSG, rebuild(with_entry(
        "init", init.replace(builder.MARKER, prior.MARKER, 1))))
    case("session #116 label renumbered", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"session #116", b"session #117", 1))))
    case("INI phase removed from init", INIT_MSG, rebuild(with_entry(
        "init", init.replace(prior.PHASE, b"", 1))))
    case("reused measured run-39 layout", INIT_MSG, run39)
    case("reused measured run-38 layout", INIT_MSG, run38)

    expect_rejection("reused measured run-39 image", SHA_MSG, reject_prior_sha,
                     builder.MEASURED_RUN39)
    expect_rejection("reused measured run-38 image", SHA_MSG, reject_prior_sha,
                     psoc.MEASURED_RUN38)
    expect_rejection("reused measured run-37 image", SHA_MSG, reject_prior_sha,
                     prior.MEASURED_RUN37)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        item = next((p for p in PRIOR_IMAGES if p.startswith(prefix)), None)
        require(item is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, item)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("psoc-hold-capture negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (20, 21) and (len(args) == 20 or args[0] == "--self-test"),
            "usage: verify-init-boot-psoc-hold-capture.py [--self-test] CANDIDATE RUN39 "
            "RUN38 RUN37 STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG "
            "KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV RMTFS "
            "SHAREDMEM_KO BY_NAME MAPS_DIR")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    blobs = [pathlib.Path(path).read_bytes() for path in args[:-2]]
    psoc.prior.prior.prior.check_by_name(args[-2])
    maps = (psoc.prior.prior.prior.old_checker.builder
            .check_map_source(pathlib.Path(args[-1])))
    blobs.append(maps)
    if self_test_mode:
        self_test(*blobs)
        return
    digest, order, outside, cpio, frame = check_candidate(*blobs, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print("session delta: from the measured #109 run-39 image (0b40ac34), only the init "
          "session marker is changed; the single 25 s-capped /dev/wlan ON hold, the "
          "one-shot WPSS trigger, the stock INI phase, the modem-holding stack, the "
          "21-module WLAN closure, the USB/key-only SSH path, the 150 s timer and "
          "/run/keep semantics are byte-exact")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} "
          f"/ {base.MAX_FRAME} bytes")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from run-39 0b40ac34, run-38 e75c5bd2, run-37 "
          "d9d8d2b8, run-36 bf2089c4, 8dddb8c7, 35866d56, ae2ccff7, 4216af26 and every "
          "other prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
