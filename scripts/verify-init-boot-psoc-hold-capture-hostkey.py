#!/usr/bin/env python3
import importlib.util
import pathlib
import stat
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


builder = load("build-init-boot-psoc-hold-capture-hostkey-payload.py",
               "psoc_hold_capture_hostkey_builder")
capture_checker = load("verify-init-boot-psoc-hold-capture.py",
                       "psoc_hold_capture_checker")
hostkey = builder.hostkey
capture = builder.capture
psoc = builder.psoc
prior = builder.prior
base = builder.base
modules = builder.modules
eud = builder.eud
vendor = eud.vendor
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (*capture_checker.REQUIRED_PRIOR, "7c3d915f")
require = capture_checker.require
expect_rejection = capture_checker.expect_rejection
decode_frame = capture_checker.decode_frame
SIZE_MSG = capture_checker.SIZE_MSG
KERNEL_MSG = capture_checker.KERNEL_MSG
HEADER_MSG = capture_checker.HEADER_MSG
FRAME_MSG = capture_checker.FRAME_MSG
BLOCK_MSG = capture_checker.BLOCK_MSG
GAP_MSG = capture_checker.GAP_MSG
TAIL_MSG = capture_checker.TAIL_MSG
SHA_MSG = builder.SHA_MSG
KO_MSG = capture_checker.KO_MSG
ENVELOPE_MSG = capture_checker.ENVELOPE_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
TRIGGER_MSG = builder.TRIGGER_MSG
KEY_MSG = builder.KEY_MSG
ON_WRITE = capture_checker.ON_WRITE
HOLD_CAP = capture_checker.HOLD_CAP
WPSS_PATH = capture_checker.WPSS_PATH
HOST_KEY_DIR = hostkey.HOST_KEY_DIR
HOST_KEY_PATH = hostkey.HOST_KEY_PATH


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def reject_committed_key(root, blob):
    require(not hostkey.committed_private_key(root, blob), KEY_MSG)


def pinned_public(blob):
    seed, public = hostkey.parse_blob(blob)
    require(hostkey.derive_public(seed) == public and
            hostkey.openssh_public_line(public) == hostkey.PINNED_PUBLIC_KEY, KEY_MSG)
    return public


def check_candidate(candidate, run41, run39, run38, run37, stock, source, boot,
                    vendor_boot, recovery, config, kernel, decompressor, pstore,
                    helper_input, pdmapper, tqftpserv, rmtfs_binary, sharedmem, maps,
                    library, blob):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    public = pinned_public(blob)
    require(modules.sha256(run41) == builder.MEASURED_RUN41 and len(run41) == IMAGE_SIZE,
            "run-41 reference is not the unflashed 7c3d915f image")
    require(modules.sha256(run39) == capture.MEASURED_RUN39 and len(run39) == IMAGE_SIZE,
            "run-39 reference is not the measured 0b40ac34 image")
    _, order, outside, verified_run41_cpio, _ = capture_checker.check_candidate(
        run41, run39, run38, run37, stock, source, boot, vendor_boot, recovery, config,
        kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs_binary,
        sharedmem, maps, library)

    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    by_name = {}
    for entry in entries:
        require(entry["name"] not in by_name, CPIO_MSG)
        by_name[entry["name"]] = entry

    run41_frame_size = struct.unpack_from("<I", run41, RAMDISK_SIZE_OFFSET)[0]
    run41_decoded = decode_frame(run41[PAGE:PAGE + run41_frame_size], library)
    run41_entries, _ = modules.parse_newc(run41_decoded, "run-41 debug cpio")
    run41_by_name = {entry["name"]: entry for entry in run41_entries}
    run41_init = next(entry["data"] for entry in run41_entries if entry["name"] == "init")
    run41_trigger = next(entry["data"] for entry in run41_entries
                         if entry["name"] == "bin/wpss-once")
    require(run41_trigger == builder.expected_trigger() and
            run41_init.count(capture.MARKER) == 1 and
            run41_decoded == verified_run41_cpio and
            capture.assemble(stock, vendor.encode_frame(run41_decoded, library))[0] == run41,
            "run-41 reference differs from the reproducible unflashed #116 image")

    init = by_name["init"]["data"]
    trigger = by_name["bin/wpss-once"]["data"]
    require(by_name["init"]["mode"] & 0o170777 == 0o100755, INIT_MSG)
    require(by_name["bin/wpss-once"]["mode"] & 0o170777 == 0o100755, TRIGGER_MSG)
    builder.check_init(init, run41_init)
    builder.check_trigger(trigger)
    require(trigger == run41_trigger, TRIGGER_MSG)
    require(trigger.count(ON_WRITE) == 1 and trigger.count(HOLD_CAP) == 1, TRIGGER_MSG)
    require(trigger.count(WPSS_PATH) == psoc.OLD_TRIGGER.count(WPSS_PATH) and
            trigger.count(b'printf "1\\n" >/sys/kernel/icnss/wpss_boot') == 1, TRIGGER_MSG)
    require(init.count(eud.TIMER) == 1 and init.count(b"sleep 150") == 1 and
            init.count(b"/run/keep") == 1 and
            b"/run/keep" not in init[:init.index(eud.TIMER)], INIT_MSG)
    require(init.count(hostkey.DROPBEAR_CMD) == 1 and
            init.count(hostkey.GENERATED_CMD) == 0 and
            init.count(b"/bin/dropbear -R") == 0, INIT_MSG)
    require(init.replace(hostkey.DROPBEAR_CMD, hostkey.GENERATED_CMD, 1) == run41_init and
            run41_init.replace(hostkey.GENERATED_CMD, hostkey.DROPBEAR_CMD, 1) == init,
            INIT_MSG)

    require(HOST_KEY_DIR in by_name and HOST_KEY_PATH in by_name, KEY_MSG)
    directory = by_name[HOST_KEY_DIR]
    packed = by_name[HOST_KEY_PATH]
    require(directory["mode"] & 0o170777 == 0o040700 and directory["data"] == b"", KEY_MSG)
    require(packed["mode"] & 0o170777 == 0o100600 and packed["data"] == blob, KEY_MSG)
    require(pinned_public(packed["data"]) == public, KEY_MSG)
    require(set(by_name) - {HOST_KEY_DIR, HOST_KEY_PATH} == set(run41_by_name), CPIO_MSG)
    for name, entry in run41_by_name.items():
        mine = by_name[name]
        require(mine["mode"] == entry["mode"] and
                (mine["data"] == entry["data"] or name == "init"), CPIO_MSG)
    names = [entry["name"] for entry in entries]
    require([name for name in names if name not in (HOST_KEY_DIR, HOST_KEY_PATH)] ==
            [entry["name"] for entry in run41_entries], CPIO_MSG)
    require(names.index(HOST_KEY_DIR) == names.index("etc") + 1 and
            names.index(HOST_KEY_PATH) == names.index(HOST_KEY_DIR) + 1, CPIO_MSG)

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
    rebuilt = builder.candidate_cpio(run41_decoded, blob, public)
    require(vendor.encode_frame(rebuilt, library) == expected and
            builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected, public


def self_test(candidate, run41, run39, run38, run37, stock, source, boot, vendor_boot,
              recovery, config, kernel, decompressor, pstore, helper_input, pdmapper,
              tqftpserv, rmtfs_binary, sharedmem, maps, blob):
    library = base.lz4()
    digest, order, outside, cpio, frame, public = check_candidate(
        candidate, run41, run39, run38, run37, stock, source, boot, vendor_boot, recovery,
        config, kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv,
        rmtfs_binary, sharedmem, maps, library, blob)
    print(f"init_boot psoc-hold-capture-hostkey fixture: OK ({digest})")
    print(f"pinned Dropbear host public key: {hostkey.openssh_public_line(public)}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")

    def rebuild(changed_entries):
        payload = modules.encode_newc(changed_entries, trailer)
        return psoc.prior.prior.prior.prior.prior.static.peripheral.assemble(
            stock, vendor.encode_frame(payload, library))[0]

    def with_entry(name, data):
        return [{**entry, "data": data} if entry["name"] == name else entry
                for entry in entries]

    def without(name):
        return [entry for entry in entries if entry["name"] != name]

    def case(label, message, mutated, mutated_blob=blob):
        expect_rejection(label, message, check_candidate, mutated, run41, run39, run38,
                         run37, stock, source, boot, vendor_boot, recovery, config, kernel,
                         decompressor, pstore, helper_input, pdmapper, tqftpserv,
                         rmtfs_binary, sharedmem, maps, library, mutated_blob)

    case("changed signed tail", TAIL_MSG,
         capture_checker.wpss.rmtfs.flipped(candidate, TAIL_OFFSET + 100))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG,
         capture_checker.wpss.rmtfs.flipped(candidate, PAGE + 64))
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    init = next(entry["data"] for entry in entries if entry["name"] == "init")
    trigger = next(entry["data"] for entry in entries if entry["name"] == "bin/wpss-once")
    case("-R generated host key restored", INIT_MSG, rebuild(with_entry(
        "init", init.replace(hostkey.DROPBEAR_CMD, hostkey.GENERATED_CMD, 1))))
    case("host key invocation removed", INIT_MSG, rebuild(with_entry(
        "init", init.replace(hostkey.DROPBEAR_CMD, b"", 1))))
    case("host key invocation duplicated", INIT_MSG, rebuild(with_entry(
        "init", init.replace(hostkey.DROPBEAR_CMD,
                             hostkey.DROPBEAR_CMD + hostkey.DROPBEAR_CMD, 1))))
    case("host key path retargeted", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"-r /etc/dropbear/dropbear_ed25519_host_key ",
                             b"-r /tmp/unpinned_host_key ", 1))))
    case("host key file missing from cpio", KEY_MSG, rebuild(without(HOST_KEY_PATH)))
    case("host key directory missing from cpio", KEY_MSG, rebuild(without(HOST_KEY_DIR)))
    case("host key left world-readable", KEY_MSG, rebuild(
        [{**entry, "mode": 0o100644, "fields": entry["fields"][:1] + [0o100644] +
          entry["fields"][2:]} if entry["name"] == HOST_KEY_PATH else entry
         for entry in entries]))
    other = blob[:-1] + bytes([blob[-1] ^ 0x01])
    case("host key public half unpinned", KEY_MSG, rebuild(with_entry(HOST_KEY_PATH, other)),
         other)
    case("host key replaced by an unrelated blob", KEY_MSG,
         rebuild(with_entry(HOST_KEY_PATH, b"\x00" * len(blob))), b"\x00" * len(blob))
    case("host key input not the pinned blob", KEY_MSG, candidate, blob + b" committed")
    committed = tempfile.TemporaryDirectory(dir="/tmp")
    try:
        root = pathlib.Path(committed.name) / "repository"
        root.mkdir()
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        leak = root / "hostkey.txt"
        leak.write_bytes(blob)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        expect_rejection("private key committed in the repository", KEY_MSG,
                         reject_committed_key, root, blob)
        leak.unlink()
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        require(not hostkey.committed_private_key(root, blob),
                "committed private key scan did not clear after removal")
    finally:
        committed.cleanup()
    case("150 s timer lengthened", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"\tsleep 150\n", b"\tsleep 180\n", 1))))
    case("150 s timer shortened", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"\tsleep 150\n", b"\tsleep 30\n", 1))))
    case("150 s timer removed", INIT_MSG, rebuild(with_entry(
        "init", init.replace(eud.TIMER, b"", 1))))
    case("/run/keep escape disabled", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"\tif [ ! -e /run/keep ]; then\n", b"\tif false; then\n", 1))))
    case("early /run/keep planted in init", INIT_MSG, rebuild(with_entry(
        "init", init.replace(capture.MARKER, capture.MARKER + b"mkdir -p /run/keep\n", 1))))
    case("/run/keep renamed", INIT_MSG, rebuild(with_entry(
        "init", init.replace(b"/run/keep", b"/run/hold", 1))))
    case("25 s-capped hold removed", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(psoc.HOLD_START, b"", 1))))
    case("25 s-capped hold cap raised", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(HOLD_CAP, b"/bin/busybox timeout -k 1 125 ", 1))))
    case("/dev/wlan ON write altered", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(ON_WRITE, b'printf "OFF            " >/dev/wlan', 1))))
    case("second WPSS write injected", TRIGGER_MSG, rebuild(with_entry(
        "bin/wpss-once", trigger.replace(
            psoc.WPSS_RESULT,
            psoc.WPSS_RESULT + b"printf '1\\n' >/sys/kernel/icnss/wpss_boot\n", 1))))
    case("#116 marker left unchanged", INIT_MSG, rebuild(with_entry(
        "init", init.replace(capture.MARKER, b"", 1))))
    case("#116 marker duplicated", INIT_MSG, rebuild(with_entry(
        "init", init.replace(capture.MARKER, capture.MARKER + capture.MARKER, 1))))
    case("marker regressed to the #109 wording", INIT_MSG, rebuild(with_entry(
        "init", init.replace(capture.MARKER, psoc.MARKER, 1))))
    case("reused unflashed run-41 image", INIT_MSG, run41)
    case("reused measured run-39 image", INIT_MSG, run39)

    expect_rejection("reused unflashed run-41 image", SHA_MSG, reject_prior_sha,
                     builder.MEASURED_RUN41)
    expect_rejection("reused measured run-39 image", SHA_MSG, reject_prior_sha,
                     capture.MEASURED_RUN39)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        item = next((p for p in PRIOR_IMAGES if p.startswith(prefix)), None)
        require(item is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, item)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("psoc-hold-capture-hostkey negative fixtures: OK")


def check_input(hostkey_path):
    path = pathlib.Path(hostkey_path)
    mode = path.stat().st_mode
    require(stat.S_ISREG(mode) and not mode & 0o077 and
            path.resolve().is_relative_to(HERE.parent) is False,
            "host key input must be a protected regular file outside the repository")
    blob = path.read_bytes()
    public = pinned_public(blob)
    require(hostkey.openssh_public_line(public) == hostkey.PINNED_PUBLIC_KEY,
            "pinned Dropbear host public key does not match the documented pin")
    require(not hostkey.committed_private_key(HERE.parent, blob),
            "Dropbear host key material must never be committed")
    print(f"pinned Dropbear host public key: {hostkey.openssh_public_line(public)}")
    print(f"pinned Dropbear host fingerprint: {hostkey.public_fingerprint(public)}")
    print(f"known_hosts line: {hostkey.known_hosts_line(public)}")
    print("repository carries no committed private key material")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--check-input"]:
        require(len(args) == 2, "usage: verify-init-boot-psoc-hold-capture-hostkey.py "
                "--check-input HOSTKEY")
        check_input(args[1])
        return
    require(len(args) in (22, 23) and (len(args) == 22 or args[0] == "--self-test"),
            "usage: verify-init-boot-psoc-hold-capture-hostkey.py [--self-test] CANDIDATE "
            "RUN41 RUN39 RUN38 RUN37 STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "RMTFS SHAREDMEM_KO BY_NAME MAPS_DIR HOSTKEY")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    check_input(args[-1])
    blob = pathlib.Path(args[-1]).read_bytes()
    pinned_public(blob)
    blobs = [pathlib.Path(path).read_bytes() for path in args[:-3]]
    psoc.prior.prior.prior.check_by_name(args[-3])
    maps = (psoc.prior.prior.prior.old_checker.builder
            .check_map_source(pathlib.Path(args[-2])))
    blobs.append(maps)
    blobs.append(blob)
    if self_test_mode:
        self_test(*blobs)
        return
    digest, order, outside, cpio, frame, public = check_candidate(
        *blobs[:-1], base.lz4(), blobs[-1])
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"pinned Dropbear host fingerprint: {hostkey.public_fingerprint(public)}")
    print(f"known_hosts line: {hostkey.known_hosts_line(public)}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print("session delta: from the unflashed #116 run-41 image (7c3d915f), only the "
          "Dropbear invocation changes; the deterministic host key is "
          "packaged at mode 0600 and the single 25 s-capped /dev/wlan ON hold, the "
          "one-shot WPSS trigger, the stock INI phase, the modem-holding stack, the "
          "21-module WLAN closure, the 150 s timer and /run/keep semantics are byte-exact")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} "
          f"/ {base.MAX_FRAME} bytes")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from the unflashed run-41 7c3d915f, run-39 0b40ac34, "
          "run-38 e75c5bd2, run-37 d9d8d2b8, run-36 bf2089c4 and every other prior "
          "measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
