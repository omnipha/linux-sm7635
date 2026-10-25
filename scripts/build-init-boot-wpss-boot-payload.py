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


prior = load("build-init-boot-rmtfs-sharedmem-payload.py", "rmtfs_sharedmem_builder")
base = prior.base
modules = prior.modules
eud = prior.eud
require = prior.require

MEASURED_RUN36 = "bf2089c4f8a72591b45385829f287d24296fc88918a2b40a226ff4b1fcaede55"
PRIOR_IMAGES = (*prior.PRIOR_IMAGES, MEASURED_RUN36)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INIT_MSG = "session init differs from the byte-exact #96 session init"
CPIO_MSG = "candidate cpio differs from the #96 cpio beyond the one-shot WPSS trigger"
TRIGGER_MSG = "one-shot WPSS trigger is missing, altered or not executable"
TRIGGER_SHA256 = "16d4747e98085f4e0479f31ba37e516ab13bf864d263525f46cb2a32f8f55310"
TRIGGER = b"""\
#!/bin/busybox sh
set -u
log() { /bin/busybox printf 'wpss-once: %s\\n' "$*" >/dev/kmsg 2>/dev/null || true; }
if [ "$#" -ne 0 ] || [ -e /run/wpss-once.attempted ]; then
	log 'rejected: arguments or attempt marker present'
	exit 2
fi
WPSS=/sys/class/remoteproc/remoteproc3
MSS=/sys/class/remoteproc/remoteproc2
FW=/vendor/firmware_mnt/image/qca6750
NAME=$(/bin/busybox timeout -k 1 2 /bin/busybox cat "$WPSS/name" 2>/dev/null) || exit 3
BEFORE=$(/bin/busybox timeout -k 1 2 /bin/busybox cat "$WPSS/state" 2>/dev/null) || exit 3
MODEM_NAME=$(/bin/busybox timeout -k 1 2 /bin/busybox cat "$MSS/name" 2>/dev/null) || exit 3
MODEM_STATE=$(/bin/busybox timeout -k 1 2 /bin/busybox cat "$MSS/state" 2>/dev/null) || exit 3
log "before: wpss=$NAME/$BEFORE modem=$MODEM_NAME/$MODEM_STATE"
if [ "$NAME" != 9bb00000.remoteproc-wpss ] || [ "$BEFORE" != offline ] ||
	[ "$MODEM_NAME" != 4080000.remoteproc-mss ] || [ "$MODEM_STATE" != running ] ||
	[ "$(/bin/busybox cat /run/qrtr-services.status 2>/dev/null)" != qrtr-published ] ||
	[ "$(/bin/busybox cat /run/rmtfs.status 2>/dev/null)" != rmtfs-published ] ||
	[ ! -e /sys/bus/platform/devices/17110040.qcom,wcn6750/driver ] ||
	[ ! -w /sys/kernel/icnss/wpss_boot ]; then
	log 'rejected: measured #96 preconditions or icnss2 WPSS attribute absent'
	exit 4
fi
if ! /bin/busybox grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts; then
	log 'rejected: modem_a firmware is not mounted read-only'
	exit 5
fi
for part in mdt b00 b01 b02 b03 b04 b05 b06 b07 b08 b09 b10 b12; do
	if [ ! -r "$FW/wpss.$part" ]; then
		log "rejected: stock wpss.$part unavailable"
		exit 6
	fi
done
if ! /bin/busybox printf 'attempted\\n' >/run/wpss-once.attempted; then
	log 'rejected: cannot arm one-shot marker'
	exit 7
fi
log 'armed: issuing one stock wpss_boot=1 write'
if /bin/busybox timeout -k 1 3 /bin/busybox sh -c 'printf "1\\n" >/sys/kernel/icnss/wpss_boot'; then
	log 'stock wpss_boot write accepted (asynchronous loader; not a FW_READY result)'
else
	log 'stock wpss_boot write failed or timed out; no retry'
	exit 8
fi
/bin/busybox sleep 12
AFTER=$(/bin/busybox timeout -k 1 2 /bin/busybox cat "$WPSS/state" 2>/dev/null) || AFTER=unavailable
MODEM_AFTER=$(/bin/busybox timeout -k 1 2 /bin/busybox cat "$MSS/state" 2>/dev/null) || MODEM_AFTER=unavailable
log "after: wpss=$AFTER modem=$MODEM_AFTER; inspect continuous capture for FW_READY, wlan0 and fatal text"
"""


def check_trigger(data):
    require(data == TRIGGER and modules.sha256(data) == TRIGGER_SHA256, TRIGGER_MSG)


def candidate_cpio(run36_cpio, trigger):
    check_trigger(trigger)
    entries, trailer = modules.parse_newc(run36_cpio, "run-36 cpio")
    require("bin/wpss-once" not in {entry["name"] for entry in entries}, CPIO_MSG)
    added = prior.prior.archive_entry("bin/wpss-once", trigger, 0o100755)
    result = modules.encode_newc([*entries, added], trailer)
    decoded, _ = modules.parse_newc(result, "#101 cpio")
    require([entry["name"] for entry in decoded] ==
            [entry["name"] for entry in entries] + ["bin/wpss-once"] and
            all(a["mode"] == b["mode"] and a["data"] == b["data"]
                for a, b in zip(decoded[:-1], entries)) and
            decoded[-1]["data"] == trigger and decoded[-1]["mode"] == 0o100755 and
            not any(entry["name"].endswith(".ko") for entry in decoded), CPIO_MSG)
    return result


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, prior.prior.prior.ENVELOPE_MSG)
    image, digest = prior.prior.prior.static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    stock, run36_cpio, _frame, order, outside = prior.prepare(paths)
    init = next(entry["data"] for entry in modules.parse_newc(run36_cpio, "run-36 cpio")[0]
                if entry["name"] == "init")
    require(init == prior.expected_init(prior.prior.prior.wpss.frozen_init(order)), INIT_MSG)
    cpio = candidate_cpio(run36_cpio, TRIGGER)
    frame = eud.vendor.encode_frame(cpio, base.lz4())
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 18 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-wpss-boot-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR RMTFS "
            "SHAREDMEM_KO BY_NAME OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"WPSS: dormant one-shot stock sysfs trigger {TRIGGER_SHA256} ({len(TRIGGER)} B); "
          "init and all #96 services are byte-exact")
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
