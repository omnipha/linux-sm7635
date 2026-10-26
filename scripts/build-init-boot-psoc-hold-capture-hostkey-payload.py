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


capture = load("build-init-boot-psoc-hold-capture-payload.py", "psoc_hold_capture_builder")
hostkey = load("dropbear-hostkey.py", "dropbear_hostkey")
psoc = capture.psoc
prior = capture.prior
base = capture.base
modules = capture.modules
eud = capture.eud
require = capture.require

MEASURED_RUN41 = "7c3d915f3c8554d8a551b33f1b1caf162d410c0f629fae75425f29112c2fedf0"
PRIOR_IMAGES = (*capture.PRIOR_IMAGES, MEASURED_RUN41)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INIT_MSG = ("session init differs from the unflashed #116 init beyond the pinned "
            "Dropbear host key")
KEY_MSG = hostkey.KEY_MSG
CPIO_MSG = ("candidate cpio differs from the unflashed #116 cpio beyond the pinned "
            "Dropbear host key")
TRIGGER_MSG = capture.TRIGGER_MSG

HOST_KEY_DIR = hostkey.HOST_KEY_DIR
HOST_KEY_PATH = hostkey.HOST_KEY_PATH


def expected_init(run41_init):
    require(run41_init.count(capture.MARKER) == 1 and
            run41_init.count(hostkey.GENERATED_CMD) == 1 and
            hostkey.DROPBEAR_CMD not in run41_init, INIT_MSG)
    return run41_init.replace(hostkey.GENERATED_CMD, hostkey.DROPBEAR_CMD, 1)


def check_init(init, run41_init):
    require(init == expected_init(run41_init) and init.count(capture.MARKER) == 1 and
            init.count(psoc.MARKER) == 0 and
            init.count(hostkey.DROPBEAR_CMD) == 1 and
            init.count(hostkey.GENERATED_CMD) == 0 and
            init.count(b"/bin/dropbear -R") == 0 and
            init.count(prior.PHASE) == 1 and init.count(eud.TIMER) == 1, INIT_MSG)


def expected_trigger():
    return capture.expected_trigger()


def check_trigger(trigger):
    require(trigger == expected_trigger(), TRIGGER_MSG)
    capture.check_trigger(trigger)


def check_host_key(blob, public):
    seed, parsed = hostkey.parse_blob(blob)
    require(parsed == public and len(seed) == hostkey.SEED_LEN and
            hostkey.derive_public(seed) == public and
            hostkey.openssh_public_line(public) == hostkey.PINNED_PUBLIC_KEY, KEY_MSG)
    return seed


def candidate_cpio(run41_cpio, blob, public):
    entries, trailer = modules.parse_newc(run41_cpio, "run-41 cpio")
    run41_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    run41_trigger = next(entry["data"] for entry in entries
                         if entry["name"] == "bin/wpss-once")
    require(run41_trigger == expected_trigger() and
            run41_init.count(capture.MARKER) == 1 and
            not any(entry["name"].startswith(HOST_KEY_DIR) for entry in entries), CPIO_MSG)
    check_host_key(blob, public)
    init = expected_init(run41_init)
    result = []
    for entry in entries:
        result.append({**entry, "data": init} if entry["name"] == "init" else entry)
        if entry["name"] == "etc":
            result.append(hostkey.directory_entry())
            result.append(hostkey.host_key_entry(blob))
    require(any(entry["name"] == "etc" for entry in entries), CPIO_MSG)
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#120 cpio")
    originals = [entry for entry in decoded if entry["name"] not in
                 (HOST_KEY_DIR, HOST_KEY_PATH)]
    require([entry["name"] for entry in originals] == [entry["name"] for entry in entries] and
            all(a["mode"] == b["mode"] and
                (a["data"] == b["data"] or a["name"] == "init")
                for a, b in zip(originals, entries)) and
            not any(entry["name"].endswith(".ko") for entry in decoded), CPIO_MSG)
    packed = {entry["name"]: entry for entry in decoded}
    require(packed[HOST_KEY_DIR]["mode"] == hostkey.HOST_KEY_DIR_MODE and
            packed[HOST_KEY_DIR]["data"] == b"" and
            packed[HOST_KEY_PATH]["mode"] == hostkey.HOST_KEY_MODE and
            packed[HOST_KEY_PATH]["data"] == blob, CPIO_MSG)
    check_init(init, run41_init)
    check_trigger(run41_trigger)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, psoc.prior.prior.prior.prior.prior.ENVELOPE_MSG)
    image, digest = psoc.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths, blob, public):
    require(len(paths) == 20, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37 RUN38 RUN39 RUN41")
    stock, run41_cpio, run41_frame, order, outside = capture.prepare(paths[:-1])
    run41 = pathlib.Path(paths[-1]).read_bytes()
    require(len(run41) == base.IMAGE_SIZE and modules.sha256(run41) == MEASURED_RUN41 and
            capture.assemble(stock, run41_frame)[0] == run41,
            "run-41 reference differs from the reproducible unflashed #116 image")
    cpio = candidate_cpio(run41_cpio, blob, public)
    frame = eud.vendor.encode_frame(cpio, base.lz4())
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 23 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-psoc-hold-capture-hostkey-payload.py "
            "--preflight|--build STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37 RUN38 RUN39 RUN41 HOSTKEY OUTPUT")
    blob = pathlib.Path(args[-2]).read_bytes()
    seed, public = hostkey.parse_blob(blob)
    check_host_key(blob, public)
    stock, cpio, frame, _, _ = prepare(args[1:21], blob, public)
    image, digest = assemble(stock, frame)
    print("session delta: from the unflashed #116 image, only the Dropbear invocation "
          "changes; the pinned host key replaces the -R generated "
          "key while the single bounded /dev/wlan ON hold, the one-shot WPSS trigger, "
          "the 150 s timer and /run/keep semantics stay byte-exact")
    print(f"pinned Dropbear host public key: {hostkey.openssh_public_line(public)}")
    print(f"pinned Dropbear host fingerprint: {hostkey.public_fingerprint(public)}")
    print(f"known_hosts line: {hostkey.known_hosts_line(public)}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} / {base.MAX_FRAME} bytes")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    del seed
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
