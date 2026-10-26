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


hostkey_builder = load(
    "build-init-boot-psoc-hold-capture-hostkey-payload.py",
    "psoc_hold_capture_hostkey_builder",
)
capture = hostkey_builder.capture
hostkey = hostkey_builder.hostkey
psoc = hostkey_builder.psoc
prior = hostkey_builder.prior
base = hostkey_builder.base
modules = hostkey_builder.modules
eud = hostkey_builder.eud
require = hostkey_builder.require

MEASURED_RUN42 = "8b62520fe6288361fd15faa573587a0d1be1e0788f780c62440677a60b739801"
PRIOR_IMAGES = (*hostkey_builder.PRIOR_IMAGES, MEASURED_RUN42)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INIT_MSG = (
    "session init differs from the measured run-42 #120 init beyond the single "
    "fail-closed wlan-node phase"
)
KEY_MSG = hostkey_builder.KEY_MSG
CPIO_MSG = (
    "candidate cpio differs from the measured run-42 #120 cpio beyond the session "
    "init wlan-node phase"
)
TRIGGER_MSG = hostkey_builder.TRIGGER_MSG
NODE_MSG = (
    "the fail-closed /dev/wlan wlan-node phase is missing, altered, duplicated, "
    "misplaced, hardcoded or not cross-checked against /proc/devices"
)

HOST_KEY_DIR = hostkey_builder.HOST_KEY_DIR
HOST_KEY_PATH = hostkey_builder.HOST_KEY_PATH

NODE_ANCHOR = b"log 'wlan-init: end'\n"
NODE_BEGIN = (
    b"log 'wlan-node phase begin: fail-closed /dev/wlan node from the live "
    b"qcwlanstate class device'\n"
)
NODE_END = b"log 'wlan-node phase end'\n"
NODE_PHASE = b"""\
log 'wlan-node phase begin: fail-closed /dev/wlan node from the live qcwlanstate class device'
if [ ! -e /sys/class/wlan/wlan ]; then
\tlog 'wlan-node: rejected: /sys/class/wlan/wlan class device absent; no node, no WPSS helper'
elif [ ! -r /sys/class/wlan/wlan/dev ]; then
\tlog 'wlan-node: rejected: /sys/class/wlan/wlan/dev unreadable; no node, no WPSS helper'
elif ! WLAN_DEVNUM=$(/bin/busybox cat /sys/class/wlan/wlan/dev 2>/dev/null); then
\tlog 'wlan-node: rejected: /sys/class/wlan/wlan/dev read failed; no node, no WPSS helper'
else
\tcase "$WLAN_DEVNUM" in
\t''|*[!0-9:]*|*:*:*|*:|:*)
\t\tlog "wlan-node: rejected: malformed device number '$WLAN_DEVNUM'; no node, no WPSS helper" ;;
\t*)
\t\tWLAN_MAJOR=$((10#${WLAN_DEVNUM%%:*}))
\t\tWLAN_MINOR=$((10#${WLAN_DEVNUM##*:}))
\t\tWLAN_REG_MAJOR=''
\t\tWLAN_SECTION='unknown'
\t\tif [ -r /proc/devices ]; then
\t\t\twhile read -r proc_major proc_name; do
\t\t\t\tif [ "$proc_name" = qcwlanstate ]; then
\t\t\t\t\tcase "$proc_major" in
\t\t\t\t\t''|*[!0-9]*) ;;
\t\t\t\t\t*) if [ "$WLAN_SECTION" = 'char' ]; then
\t\t\t\t\t\tWLAN_REG_MAJOR="$WLAN_REG_MAJOR $((10#$proc_major))"
\t\t\t\t\t\tfi ;;
\t\t\t\t\tesac
\t\t\t\telif [ "$proc_major $proc_name" = 'Character devices:' ]; then
\t\t\t\t\tWLAN_SECTION='char'
\t\t\t\telif [ "$proc_major $proc_name" = 'Block devices:' ]; then
\t\t\t\t\tWLAN_SECTION='block'
\t\t\t\tfi
\t\t\tdone </proc/devices
\t\tfi
\t\tWLAN_COUNT=0
\t\tWLAN_REG_FIRST=''
\t\tfor token in $WLAN_REG_MAJOR; do
\t\t\tWLAN_COUNT=$((WLAN_COUNT + 1))
\t\t\tWLAN_REG_FIRST=$token
\t\tdone
\t\tif [ "$WLAN_COUNT" -ne 1 ] || [ -z "$WLAN_REG_FIRST" ] || [ "$WLAN_REG_FIRST" != "$WLAN_MAJOR" ]; then
\t\t\tlog "wlan-node: rejected: qcwlanstate major match '${WLAN_REG_MAJOR# }' does not match sysfs major $WLAN_MAJOR; no node, no WPSS helper"
\t\telif [ -e /dev/wlan ]; then
\t\t\tlog 'wlan-node: rejected: /dev/wlan already exists; no second attempt, no WPSS helper'
\t\telif ! /bin/busybox timeout -k 1 2 /bin/busybox mknod -m 0600 /dev/wlan c "$WLAN_MAJOR" "$WLAN_MINOR"; then
\t\t\t/bin/busybox rm -f /dev/wlan
\t\t\tlog "wlan-node: rejected: mknod /dev/wlan c $WLAN_MAJOR $WLAN_MINOR failed or timed out; no node, no WPSS helper"
\t\telif ! [ -c /dev/wlan ]; then
\t\t\t/bin/busybox rm -f /dev/wlan
\t\t\tlog 'wlan-node: rejected: /dev/wlan is not a character device; node removed; no WPSS helper'
\t\telif ! WLAN_GOT=$(/bin/busybox stat -c '%t:%T' /dev/wlan 2>/dev/null) ||
\t\t\t[ "$WLAN_GOT" != "$(/bin/busybox printf '%x:%x' "$WLAN_MAJOR" "$WLAN_MINOR")" ]; then
\t\t\t/bin/busybox rm -f /dev/wlan
\t\t\tlog "wlan-node: rejected: /dev/wlan verify failed (want $WLAN_MAJOR:$WLAN_MINOR got ${WLAN_GOT:-none}); node removed; no WPSS helper"
\t\telse
\t\t\tlog "wlan-node: /dev/wlan verified character $WLAN_MAJOR:$WLAN_MINOR mode 0600"
\t\tfi ;;
\tesac
fi
log 'wlan-node phase end'
"""


def expected_init(run42_init):
    require(
        run42_init.count(NODE_ANCHOR) == 1
        and NODE_PHASE not in run42_init
        and run42_init.count(capture.MARKER) == 1
        and run42_init.count(hostkey.DROPBEAR_CMD) == 1,
        INIT_MSG,
    )
    return run42_init.replace(NODE_ANCHOR, NODE_ANCHOR + NODE_PHASE, 1)


def check_init(init, run42_init):
    require(
        init.count(NODE_BEGIN) == 1 and init.count(NODE_END) == 1,
        NODE_MSG,
    )
    begin = init.index(NODE_BEGIN)
    packed_phase = init[begin : init.index(NODE_END, begin) + len(NODE_END)]
    require(packed_phase == NODE_PHASE and b"495" not in packed_phase, NODE_MSG)
    require(
        NODE_PHASE.count(b"/sys/class/wlan/wlan/dev") == 4
        and NODE_PHASE.count(b"/proc/devices") == 2
        and NODE_PHASE.count(b"timeout -k 1 2 /bin/busybox mknod -m 0600 /dev/wlan c")
        == 1
        and NODE_PHASE.count(b"qcwlanstate") == 3
        and NODE_PHASE.count(b'case "$WLAN_DEVNUM" in') == 1
        and NODE_PHASE.count(b"mknod -m 0600 /dev/wlan") == 1,
        NODE_MSG,
    )
    require(
        init.index(b"qca_cld3_qca6750.ko\n")
        < begin
        < init.index(NODE_END)
        < init.index(b"log 'console ready'\n"),
        NODE_MSG,
    )
    require(
        init == expected_init(run42_init)
        and init.count(NODE_PHASE) == 1
        and init.count(NODE_ANCHOR) == 1
        and init.count(capture.MARKER) == 1
        and init.count(psoc.MARKER) == 0
        and init.count(hostkey.DROPBEAR_CMD) == 1
        and init.count(hostkey.GENERATED_CMD) == 0
        and init.count(prior.PHASE) == 1
        and init.count(eud.TIMER) == 1,
        INIT_MSG,
    )


def expected_trigger():
    return hostkey_builder.expected_trigger()


def check_trigger(trigger):
    require(trigger == expected_trigger(), TRIGGER_MSG)
    hostkey_builder.check_trigger(trigger)


def check_host_key(blob, public):
    return hostkey_builder.check_host_key(blob, public)


def candidate_cpio(run42_cpio, blob, public):
    entries, trailer = modules.parse_newc(run42_cpio, "run-42 cpio")
    run42_init = next(entry["data"] for entry in entries if entry["name"] == "init")
    run42_trigger = next(
        entry["data"] for entry in entries if entry["name"] == "bin/wpss-once"
    )
    require(
        run42_trigger == expected_trigger()
        and run42_init.count(capture.MARKER) == 1
        and run42_init.count(NODE_PHASE) == 0,
        CPIO_MSG,
    )
    check_host_key(blob, public)
    init = expected_init(run42_init)
    result = [
        {**entry, "data": init} if entry["name"] == "init" else entry
        for entry in entries
    ]
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#124 cpio")
    require(
        [entry["name"] for entry in decoded] == [entry["name"] for entry in entries]
        and all(
            a["mode"] == b["mode"] and (a["data"] == b["data"] or a["name"] == "init")
            for a, b in zip(decoded, entries)
        )
        and next(entry["data"] for entry in decoded if entry["name"] == "init") == init
        and not any(entry["name"].endswith(".ko") for entry in decoded),
        CPIO_MSG,
    )
    check_init(init, run42_init)
    check_trigger(run42_trigger)
    return cpio


def assemble(stock, frame):
    require(
        len(frame) <= base.MAX_FRAME, psoc.prior.prior.prior.prior.prior.ENVELOPE_MSG
    )
    image, digest = psoc.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths, blob, public):
    require(
        len(paths) == 21,
        "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
        "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
        "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37 RUN38 RUN39 RUN41 RUN42",
    )
    stock, run42_cpio, _, order, outside = hostkey_builder.prepare(
        paths[:-1], blob, public
    )
    run42 = pathlib.Path(paths[-1]).read_bytes()
    require(
        len(run42) == base.IMAGE_SIZE
        and modules.sha256(run42) == MEASURED_RUN42
        and hostkey_builder.assemble(
            stock, eud.vendor.encode_frame(run42_cpio, base.lz4())
        )[0]
        == run42,
        "run-42 reference differs from the reproducible measured #120 image",
    )
    cpio = candidate_cpio(run42_cpio, blob, public)
    frame = eud.vendor.encode_frame(cpio, base.lz4())
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(
        len(args) == 24 and args[0] in ("--preflight", "--build"),
        "usage: build-init-boot-psoc-hold-wlan-node-payload.py "
        "--preflight|--build STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
        "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
        "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37 RUN38 RUN39 RUN41 HOSTKEY RUN42 "
        "OUTPUT",
    )
    blob = pathlib.Path(args[-3]).read_bytes()
    seed, public = hostkey.parse_blob(blob)
    check_host_key(blob, public)
    stock, cpio, frame, _, _ = prepare(args[1:21] + args[22:23], blob, public)
    image, digest = assemble(stock, frame)
    print(
        "session delta: from the measured run-42 #120 image, only the single fail-closed "
        "wlan-node phase after the WLAN closure differs; it reads the live "
        "/sys/class/wlan/wlan/dev, cross-checks the qcwlanstate major in /proc/devices, "
        "mknods /dev/wlan mode 0600 only on an exact match, verifies the character "
        "device and its exact major:minor, and never hard-codes an observed number"
    )
    print(f"pinned Dropbear host public key: {hostkey.openssh_public_line(public)}")
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
