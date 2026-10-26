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


psoc = load("build-init-boot-psoc-hold-payload.py", "psoc_hold_builder")
prior = psoc.prior
base = psoc.base
modules = psoc.modules
eud = psoc.eud
require = psoc.require

MEASURED_RUN39 = "0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7"
PRIOR_IMAGES = (*psoc.PRIOR_IMAGES, MEASURED_RUN39)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INIT_MSG = "session init differs from the measured #109 init beyond the #116 marker"
TRIGGER_MSG = ("one-shot trigger is not the byte-exact #109 trigger carrying the single "
               "bounded /dev/wlan ON hold")
CPIO_MSG = "candidate cpio differs from the measured #109 cpio beyond the marker"

MARKER = (b"log 'session #116: capture-gated rerun of the #109 single bounded /dev/wlan "
          b"ON hold'\n")


def expected_init(run39_init):
    require(run39_init.count(psoc.MARKER) == 1 and MARKER not in run39_init, INIT_MSG)
    return run39_init.replace(psoc.MARKER, MARKER, 1)


def check_init(init, run39_init):
    require(init == expected_init(run39_init) and init.count(MARKER) == 1 and
            init.count(psoc.MARKER) == 0 and init.count(prior.MARKER) == 0 and
            init.count(prior.PHASE) == 1 and init.count(eud.TIMER) == 1, INIT_MSG)


def expected_trigger():
    return psoc.expected_trigger()


def check_trigger(trigger):
    require(trigger == expected_trigger(), TRIGGER_MSG)
    psoc.check_trigger(trigger)


def candidate_cpio(run39_cpio):
    entries, trailer = modules.parse_newc(run39_cpio, "run-39 cpio")
    run39_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    run39_trigger = next(entry["data"] for entry in entries
                         if entry["name"] == "bin/wpss-once")
    require(run39_trigger == expected_trigger() and
            run39_init.count(psoc.MARKER) == 1, CPIO_MSG)
    init = expected_init(run39_init)
    result = [{**entry, "data": init if entry["name"] == "init" else entry["data"]}
              for entry in entries]
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#116 cpio")
    require([entry["name"] for entry in decoded] == [entry["name"] for entry in entries] and
            all(a["mode"] == b["mode"] and
                (a["data"] == b["data"] or a["name"] == "init")
                for a, b in zip(decoded, entries)) and
            not any(entry["name"].endswith(".ko") for entry in decoded), CPIO_MSG)
    check_init(init, run39_init)
    check_trigger(run39_trigger)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, psoc.prior.prior.prior.prior.prior.ENVELOPE_MSG)
    image, digest = psoc.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 19, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37 RUN38 RUN39")
    stock, run39_cpio, run39_frame, order, outside = psoc.prepare(paths[:-1])
    run39 = pathlib.Path(paths[-1]).read_bytes()
    require(len(run39) == base.IMAGE_SIZE and modules.sha256(run39) == MEASURED_RUN39 and
            psoc.assemble(stock, run39_frame)[0] == run39,
            "run-39 reference differs from the reproducible measured #109 image")
    cpio = candidate_cpio(run39_cpio)
    frame = eud.vendor.encode_frame(cpio, base.lz4())
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 21 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-psoc-hold-capture-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR RMTFS "
            "SHAREDMEM_KO BY_NAME RUN37 RUN38 RUN39 OUTPUT")
    stock, cpio, frame, _, _ = prepare(args[1:20])
    image, digest = assemble(stock, frame)
    print("session delta: only the #116 init marker differs from the measured #109 "
          "image; the single bounded /dev/wlan ON hold, the one-shot WPSS trigger, the "
          "150 s timer and /run/keep semantics are byte-exact")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} / {base.MAX_FRAME} bytes")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
