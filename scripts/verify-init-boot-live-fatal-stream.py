import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


builder = load("build-init-boot-live-fatal-stream-payload.py", "live_fatal_stream_builder")
previous = load("verify-init-boot-wpss-supplier.py", "wpss_supplier_checker")
modem_start = load("build-init-boot-modem-start-payload.py", "modem_start_builder")
SESSION79_MARKER = b"log 'session #79: modem start deferred to key-only SSH live diagnosis'\n"
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
REQUIRED_PRIOR = (*previous.REQUIRED_PRIOR, "5a61de0e", "560c98e5", "4216af26")
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
ENVELOPE_MSG = builder.ENVELOPE_MSG
MOUNT_MSG = previous.MOUNT_MSG
MODULE_MSG = previous.MODULE_MSG
DEFER_MSG = builder.wpss.DEFER_MSG
SUPPLIER_MSG = builder.wpss.SUPPLIER_MSG
MARKER_MSG = builder.MARKER_MSG
KEEP_MSG = builder.KEEP_MSG
REMOTE_MSG = builder.REMOTE_MSG


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
    for name in builder.wpss.SUPPLIER_MODULES:
        entry = vendor_files.get("lib/modules/" + name)
        require(entry is not None and modules.sha256(entry["data"]) ==
                builder.wpss.SUPPLIER_SHA256[name] and len(entry["data"]) ==
                builder.wpss.SUPPLIER_SIZE[name],
                f"supplier module {name} is not the measured stock vendor_boot provider")
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
    frozen = builder.wpss.frozen_init(order)
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


def test_timer(init):
    require(init.count(eud.TIMER) == 1, TIMER_MSG)
    with tempfile.TemporaryDirectory(prefix="sm7635-timer-") as temporary:
        directory = pathlib.Path(temporary)
        timer = eud.TIMER.decode().replace("/run/keep", '"$KEEP"').replace(
            "/bin/restart2 bootloader", "restart2 bootloader")
        harness = (
            'sleep() { [ "$1" = 150 ] || exit 27; printf "wait %s\\n" "$1" >>"$LOG"; '
            '[ "$SSH_VERIFIED" = 1 ] && touch "$KEEP"; return 0; }\n'
            'log() { printf "log %s\\n" "$1" >>"$LOG"; }\n'
            'restart2() { printf "restart2 %s\\n" "$1" >>"$LOG"; }\n'
            'reboot() { printf "reboot %s\\n" "$1" >>"$LOG"; }\n'
            + timer + 'wait\n')
        for verified, expected in (
            ("0", ["wait 150", "log self-recovery -> bootloader", "restart2 bootloader",
                   "log self-recovery RESTART2 failed; falling back to reboot -f",
                   "reboot -f"]),
            ("1", ["wait 150"])):
            keep = directory / "keep"
            log = directory / "events"
            keep.unlink(missing_ok=True)
            log.unlink(missing_ok=True)
            result = subprocess.run(["bash", "-c", harness], timeout=5, check=False,
                                    env={**os.environ, "KEEP": str(keep), "LOG": str(log),
                                         "SSH_VERIFIED": verified}, capture_output=True)
            require(result.returncode == 0 and log.read_text().splitlines() == expected and
                    keep.exists() == (verified == "1"), TIMER_MSG)
    print("150 s timer simulated clock: missing SSH/keep -> RESTART2 bootloader; "
          "verified SSH -> worker keep before deadline: OK")
    print("note: this userspace timer does not cover the expected kernel panic")


def self_test(candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input):
    library = base.lz4()
    digest, order, outside, cpio, frame, wlan_offset = check_candidate(
        candidate, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, library)
    print(f"init_boot live-fatal-stream fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, stock, source, boot,
                         vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, library)

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")
    good_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    test_timer(good_init)

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
    case("second changed header field", HEADER_MSG, flipped(candidate, 16))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, flipped(candidate, PAGE + 64))
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("ramdisk exceeds signed-tail envelope", FRAME_MSG,
         candidate[:RAMDISK_SIZE_OFFSET] + struct.pack("<I", base.MAX_FRAME + 1) +
         candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    marker = builder.SESSION_MARKER
    timer = eud.TIMER
    supplier = builder.wpss.SUPPLIER_PHASE.encode()
    insmod = builder.wpss.INS_MOD.encode()
    case("session marker removed", MARKER_MSG, spliced(edited(marker, b"")))
    case("session marker duplicated", MARKER_MSG, spliced(edited(marker, marker + marker)))
    case("session marker moved before timer", MARKER_MSG, spliced(
        good_init.replace(marker, b"", 1).replace(timer, marker + timer, 1)))
    case("session marker moved into module phase", MARKER_MSG, spliced(
        good_init.replace(marker, b"", 1).replace(
            b"log 'module load begin'\n", b"log 'module load begin'\n" + marker, 1)))
    case("marker reworded", MARKER_MSG, spliced(edited(
        marker, b"log 'session #81: fatal stream'\n")))
    case("marker replaced by the #79 marker", MARKER_MSG, spliced(edited(
        marker, SESSION79_MARKER)))
    case("second marker line added", MARKER_MSG, spliced(edited(
        marker, marker + b"log 'session #81: second line'\n")))
    case("pre-SSH keep created", KEEP_MSG, spliced(edited(
        marker, marker + b"mkdir -p /run/keep\n")))
    case("pre-timer keep created", MARKER_MSG, spliced(
        good_init.replace(marker, b"", 1).replace(timer, b"mkdir -p /run/keep\n" + timer, 1)))
    case("timer disabled by unconditional keep", TIMER_MSG, spliced(edited(
        b"\tif [ ! -e /run/keep ]; then", b"\tif false; then")))
    case("init-time modem start added", REMOTE_MSG, spliced(edited(
        marker, marker + b"/bin/busybox sh -c 'printf start "
        b">/sys/class/remoteproc/remoteproc2/state'\n")))
    case("init-time modem start before supplier phase", REMOTE_MSG, spliced(
        good_init.replace(supplier, b"/bin/busybox sh -c 'printf start "
        b">/sys/class/remoteproc/remoteproc2/state'\n" + supplier, 1)))
    case("wpss boot added", REMOTE_MSG, spliced(edited(
        marker, marker + b"echo 1 >/sys/module/icnss2/parameters/wpss_boot\n")))
    case("rmmod added", REMOTE_MSG, spliced(edited(
        marker, marker + b"rmmod qca_cld3_qca6750\n")))
    case("modprobe added", REMOTE_MSG, spliced(edited(
        marker, marker + b"modprobe qca_cld3_qca6750\n")))
    case("timer removed", TIMER_MSG, spliced(edited(timer, b"")))
    case("timer lengthened", TIMER_MSG, spliced(edited(b"\tsleep 150\n", b"\tsleep 180\n")))
    case("timer shortened", TIMER_MSG, spliced(edited(b"\tsleep 150\n", b"\tsleep 30\n")))
    case("timer restart2 removed", TIMER_MSG, spliced(edited(
        b"\t\t/bin/restart2 bootloader\n", b"\t\ttrue\n")))
    case("supplier phase removed", SUPPLIER_MSG, spliced(edited(supplier, b"")))
    case("supplier phase duplicated", SUPPLIER_MSG, spliced(edited(supplier, supplier + supplier)))
    case("supplier order reversed", SUPPLIER_MSG, spliced(edited(
        builder.wpss.SUPPLIER_LIST.encode(),
        b"pinctrl-spmi-gpio.ko smp2p.ko qti-fixed-regulator.ko")))
    case("supplier insmod timeout removed", SUPPLIER_MSG, spliced(edited(
        b'/bin/busybox timeout -k 1 2 /bin/busybox insmod "$SUPPATH"',
        b'/bin/busybox insmod "$SUPPATH"')))
    case("bind gate removed", SUPPLIER_MSG, spliced(edited(
        b"\t\tbind_wait=0\n", b"")))
    case("bind gate wait lengthened", DEFER_MSG, spliced(edited(
        b'"$bind_wait" -lt 12 ]', b'"$bind_wait" -lt 60 ]')))
    case("entire WLAN phase removed", SUPPLIER_MSG, spliced(edited(
        builder.wpss.DELTA, b"")))
    case("wlan module list truncated", MODULE_MSG, spliced(edited(
        b"wlan_firmware_service.ko", b"wlan_firmware_service_x.ko")))
    case("WLAN insmod repeated", SUPPLIER_MSG, spliced(edited(insmod, insmod + insmod)))
    case("planted .ko", KO_MSG, spliced(extra=[{
        "name": "lib/modules/outside-wlan.ko",
        "fields": [0, 0o100644, 0, 0, 1, 0, 8, 0, 0, 0, 0, 21, 0],
        "mode": 0o100644, "data": b"\x7fELF\x02\x01\x01\x00"}]))
    case("rfkill from wrong partition", MODULE_MSG, spliced(edited(
        b"\trfkill.ko)\n\t\tKOPATH=/mnt/system_dlkm/lib/modules/6.1.84-android14-11-"
        b"gf4b0d69fdf34-ab12786779/kernel/net/rfkill/rfkill.ko ;;",
        b"\trfkill.ko)\n\t\tKOPATH=/mnt/vendor_dlkm/lib/modules/rfkill.ko ;;")))
    case("loop minor guessed", MOUNT_MSG, spliced(edited(
        b'/bin/busybox mknod "$LOOPNODE" b "${LOOPNUM%%:*}" "${LOOPNUM##*:}"',
        b'/bin/busybox mknod "/dev/loop$2" b "${LOOPNUM%%:*}" "$2"')))
    expect_rejection("reused measured #75 init", MARKER_MSG,
                     builder.check_init,
                     builder.wpss.expected_init(builder.wpss.frozen_init(order)), order)
    expect_rejection("reused measured #77 modem-start init", MARKER_MSG,
                     builder.check_init,
                     modem_start.expected_init(modem_start.frozen_init(order)), order)
    expect_rejection("#77 init with the session marker added", REMOTE_MSG,
                     builder.check_init,
                     modem_start.expected_init(
                         modem_start.frozen_init(order)).replace(timer, timer + marker, 1), order)
    expect_rejection("reused measured #79 live-session init", MARKER_MSG,
                     builder.check_init,
                     builder.wpss.expected_init(builder.wpss.frozen_init(order)).replace(
                         timer, timer + SESSION79_MARKER, 1), order)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        prior = next((item for item in PRIOR_IMAGES if item.startswith(prefix)), None)
        require(prior is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, prior)
    for prior in PRIOR_IMAGES:
        expect_rejection(f"repeated {prior[:8]} SHA", SHA_MSG, reject_prior_sha, prior)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES and wlan_offset > 0, SHA_MSG)
    print("live-fatal-stream negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (11, 12) and (len(args) == 11 or args[0] == "--self-test"),
            "usage: verify-init-boot-live-fatal-stream.py [--self-test] CANDIDATE STOCK_INIT "
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
    print(f"wlan-init phase at offset {wlan_offset}: the measured #75 init unchanged - "
          f"{builder.wpss.SUPPLIER_COUNT}-module supplier phase and order, "
          f"{builder.wpss.WAIT_SECONDS} s bounded icnss2 bind gate, read-only mounts, "
          "single stock WLAN load, module closures; no remoteproc start in init")
    print(f"session marker: one #81 log after the armed {eud.TIMER_BUDGET} s timer, before "
          "the module phase; /run/keep only from the SSH worker after verified key-only SSH")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper "
          f"{eud.HELPER_SIZE} bytes, SHA-256 {eud.HELPER_SHA256[:8]}; a userspace timer "
          "does not cover the expected kernel panic")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from 4216af26, 560c98e5, 5a61de0e and every prior "
          "measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
