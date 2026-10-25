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


prior = load("build-init-boot-wlan-ini-payload.py", "wlan_ini_builder")
base = prior.base
modules = prior.modules
eud = prior.eud
require = prior.require

MEASURED_RUN38 = "e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c"
PRIOR_IMAGES = (*prior.PRIOR_IMAGES, MEASURED_RUN38)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INIT_MSG = "session init differs from the measured #106 init beyond the #109 marker"
TRIGGER_MSG = ("one-shot trigger differs from the measured #106 trigger beyond the single "
               "bounded userspace ON hold")
CPIO_MSG = "candidate cpio differs from the measured #106 cpio beyond the marker and the hold"

MARKER = b"log 'session #109: one bounded /dev/wlan ON hold with the single WPSS trigger'\n"
OLD_TRIGGER = prior.prior.TRIGGER
PRECHECK_ANCHOR = b"if ! /bin/busybox grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts; then\n"
PRECHECK = b"""\
if [ ! -c /dev/wlan ]; then
	log 'rejected: /dev/wlan control node absent before WPSS trigger'
	exit 9
fi
"""
ARM = b"log 'armed: issuing one stock wpss_boot=1 write'\n"
HOLD_START = b"""\
log 'psoc-idle hold: one bounded /dev/wlan ON write armed before WPSS trigger'
/bin/busybox timeout -k 1 25 /bin/busybox sh -c 'printf "ON             " >/dev/wlan' &
HOLD_PID=$!
"""
WPSS_WRITE = (b"if /bin/busybox timeout -k 1 3 /bin/busybox sh -c "
              b"'printf \"1\\n\" >/sys/kernel/icnss/wpss_boot'; then\n")
WPSS_TAIL = b"""\
	log 'stock wpss_boot write accepted (asynchronous loader; not a FW_READY result)'
else
	log 'stock wpss_boot write failed or timed out; no retry'
	exit 8
fi
"""
WPSS_RESULT = b"""\
	log 'stock wpss_boot write accepted (asynchronous loader; not a FW_READY result)'
	WPSS_WRITE_OK=1
else
	log 'stock wpss_boot write failed or timed out; no retry'
	WPSS_WRITE_OK=0
fi
"""
WPSS_CHECK = b"""\
if [ "$WPSS_WRITE_OK" != 1 ]; then
	exit 8
fi
"""
HOLD_WAIT = b"""\
if wait "$HOLD_PID"; then
	log 'psoc-idle hold: /dev/wlan ON write accepted'
else
	log 'psoc-idle hold: /dev/wlan ON write failed or timed out; no retry'
	exit 10
fi
"""
SLEEP12 = b"/bin/busybox sleep 12\n"
WINDOW = b"""\
if [ -e /sys/class/net/wlan0 ]; then
	HOLD_FLAGS=$(/bin/busybox cat /sys/class/net/wlan0/flags 2>/dev/null) || HOLD_FLAGS=unavailable
	HOLD_OPERSTATE=$(/bin/busybox cat /sys/class/net/wlan0/operstate 2>/dev/null) || HOLD_OPERSTATE=unavailable
	log "psoc-idle hold: window end wlan0 flags=$HOLD_FLAGS operstate=$HOLD_OPERSTATE"
else
	log 'psoc-idle hold: window end wlan0 absent'
fi
"""


def expected_init(run38_init):
    require(run38_init.count(prior.MARKER) == 1 and MARKER not in run38_init, INIT_MSG)
    return run38_init.replace(prior.MARKER, MARKER, 1)


def expected_trigger():
    old_block = WPSS_WRITE + WPSS_TAIL
    new_block = WPSS_WRITE + WPSS_RESULT + HOLD_WAIT + WPSS_CHECK
    require(OLD_TRIGGER.count(PRECHECK_ANCHOR) == 1 and OLD_TRIGGER.count(ARM) == 1 and
            OLD_TRIGGER.count(old_block) == 1 and OLD_TRIGGER.count(SLEEP12) == 1 and
            all(phase not in OLD_TRIGGER for phase in
                (PRECHECK, HOLD_START, HOLD_WAIT, WINDOW)),
            TRIGGER_MSG)
    return (OLD_TRIGGER.replace(PRECHECK_ANCHOR, PRECHECK + PRECHECK_ANCHOR, 1)
            .replace(ARM, ARM + HOLD_START, 1)
            .replace(old_block, new_block, 1)
            .replace(SLEEP12, SLEEP12 + WINDOW, 1))


def check_init(init, run38_init):
    require(init == expected_init(run38_init) and init.count(MARKER) == 1 and
            init.count(prior.PHASE) == 1 and init.count(prior.MARKER) == 0, INIT_MSG)


def check_trigger(trigger):
    require(trigger == expected_trigger() and
            all(trigger.count(phase) == 1 for phase in
                (PRECHECK, HOLD_START, HOLD_WAIT, WINDOW, WPSS_RESULT, WPSS_CHECK)) and
            trigger.count(b'printf "ON             " >/dev/wlan') == 1 and
            trigger.count(b"/sys/kernel/icnss/wpss_boot") ==
            OLD_TRIGGER.count(b"/sys/kernel/icnss/wpss_boot") and
            trigger.count(b"/run/wpss-once.attempted") ==
            OLD_TRIGGER.count(b"/run/wpss-once.attempted") and
            trigger.count(b"remoteproc") == OLD_TRIGGER.count(b"remoteproc") and
            not any(value in trigger for value in
                    (b"wpa_supplicant", b"ip link set wlan0", b"rmmod", b"insmod")),
            TRIGGER_MSG)
    require(trigger.index(PRECHECK) < trigger.index(PRECHECK_ANCHOR) <
            trigger.index(ARM) < trigger.index(HOLD_START) <
            trigger.index(WPSS_WRITE) < trigger.index(WPSS_RESULT) <
            trigger.index(HOLD_WAIT) < trigger.index(WPSS_CHECK) <
            trigger.index(SLEEP12) < trigger.index(WINDOW), TRIGGER_MSG)


def candidate_cpio(run38_cpio):
    entries, trailer = modules.parse_newc(run38_cpio, "run-38 cpio")
    run38_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    run38_trigger = next(entry["data"] for entry in entries
                         if entry["name"] == "bin/wpss-once")
    require(run38_trigger == OLD_TRIGGER, CPIO_MSG)
    init = expected_init(run38_init)
    trigger = expected_trigger()
    result = [{**entry, "data": init if entry["name"] == "init" else trigger}
              if entry["name"] in ("init", "bin/wpss-once") else entry for entry in entries]
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#109 cpio")
    require([entry["name"] for entry in decoded] == [entry["name"] for entry in entries] and
            all(a["mode"] == b["mode"] and
                (a["data"] == b["data"] or a["name"] in ("init", "bin/wpss-once"))
                for a, b in zip(decoded, entries)) and
            not any(entry["name"].endswith(".ko") for entry in decoded), CPIO_MSG)
    check_init(init, run38_init)
    check_trigger(trigger)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, prior.prior.prior.prior.prior.ENVELOPE_MSG)
    image, digest = prior.prior.prior.prior.prior.static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 18, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37 RUN38")
    stock, run38_cpio, run38_frame, order, outside = prior.prepare(paths[:-1])
    run38 = pathlib.Path(paths[-1]).read_bytes()
    require(len(run38) == base.IMAGE_SIZE and modules.sha256(run38) == MEASURED_RUN38 and
            prior.assemble(stock, run38_frame)[0] == run38,
            "run-38 reference differs from the reproducible measured #106 image")
    cpio = candidate_cpio(run38_cpio)
    frame = eud.vendor.encode_frame(cpio, base.lz4())
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 20 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-psoc-hold-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR RMTFS "
            "SHAREDMEM_KO BY_NAME RUN37 RUN38 OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:19])
    image, digest = assemble(stock, frame)
    print("session delta: only the #109 init marker and the one-shot trigger's single "
          "bounded /dev/wlan ON hold differ from the measured #106 image")
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
