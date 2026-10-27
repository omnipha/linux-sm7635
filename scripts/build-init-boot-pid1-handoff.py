#!/usr/bin/env python3
import importlib.util
import pathlib
import stat
import struct
import sys

HERE = pathlib.Path(__file__).parent


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


modules = load("vendor-module-closure.py", "pid1_vendor_modules")
base = load("build-init-boot-lz4-debug-ramdisk-payload.py", "pid1_lz4_base")
vendor = load("build-init-boot-vendor-modules-payload.py", "pid1_vendor_builder")
previous = load("build-init-boot-psoc-hold-wlan-node-payload.py", "pid1_previous_builder")
RUN43_SHA256 = "0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa"
TRANSITION_SHA256 = "0b85d1dc3c05b58f703618994363a9d0dbd09ecf8139573d2db15628d2497549"
GUARD_SHA256 = "dc37428ec10330c89fa8f559626be735013004b87d0bd9a7271d9b88dfc47fe3"
EXPECTED_SHA256 = "d90b22212812f022017a9eaaf6af58cce08a5bf08474a024b7ccb6317b51ffb7"
REFUSED = frozenset((*previous.PRIOR_IMAGES, RUN43_SHA256))
ANCHOR = b"setsid cttyhack /bin/sh\n"
INIT_MSG = "init must change only the unique final console command to the pinned PID1 handoff"
CPIO_MSG = "cpio must change only /init, preserving every other entry and its metadata"
SHA_MSG = "candidate repeats a stock, measured or refused image SHA-256"
FRAME_MSG = "ramdisk is not one reproducible LZ4 HC-12 block inside the stock envelope"

SETTLE = b"""PID1_TIMER_SETTLED=0
if [ -f /run/keep ] && [ ! -L /run/keep ]; then
	PID1_SETTLE_START=$(/bin/busybox awk 'NF == 2 && $1 ~ /^[0-9]+([.][0-9]+)?$/ && $2 ~ /^[0-9]+([.][0-9]+)?$/ && $1 + 0 < 1000000000000 && $2 + 0 < 1000000000000 {print $1; valid=1} END {if (NR != 1 || !valid) exit 1}' /proc/uptime 2>/dev/null) || PID1_SETTLE_START=''
	if [ -n "$PID1_SETTLE_START" ]; then
		PID1_SETTLE_PREVIOUS=$PID1_SETTLE_START
	else
		PID1_TIMER_SETTLED=failed
		log 'pid1 timer settle failed: invalid uptime; diagnostic console and SSH retained'
	fi
else
	PID1_TIMER_SETTLED=failed
	log 'pid1 timer settle failed: diagnostic hold missing; diagnostic console and SSH retained'
fi
pid1_settle_timer() {
	[ "$PID1_TIMER_SETTLED" != failed ] || return 1
	while :; do
		if [ ! -f /run/keep ] || [ -L /run/keep ]; then
			log 'pid1 timer settle failed: diagnostic hold lost; diagnostic console and SSH retained'
			break
		fi
		PID1_SETTLE_STATE=$(/bin/busybox awk -v start="$PID1_SETTLE_START" -v previous="$PID1_SETTLE_PREVIOUS" '
			NF == 2 && $1 ~ /^[0-9]+([.][0-9]+)?$/ && $2 ~ /^[0-9]+([.][0-9]+)?$/ && $1 + 0 < 1000000000000 && $2 + 0 < 1000000000000 && $1 + 0 >= previous + 0 {
				if ($1 - start >= 151.01) print "done"
				else print "waiting:" $1
				valid=1
			}
			END {if (NR != 1 || !valid) exit 1}
		' /proc/uptime 2>/dev/null) || PID1_SETTLE_STATE=''
		case "$PID1_SETTLE_STATE" in
		done)
			if [ -f /run/keep ] && [ ! -L /run/keep ]; then
				PID1_TIMER_SETTLED=1
				return 0
			fi
			log 'pid1 timer settle failed: diagnostic hold lost; diagnostic console and SSH retained'
			break ;;
		waiting:*) PID1_SETTLE_PREVIOUS=${PID1_SETTLE_STATE#waiting:}
			/bin/busybox sleep 1 || break ;;
		*) log 'pid1 timer settle failed: invalid uptime; diagnostic console and SSH retained'
			break ;;
		esac
	done
	PID1_TIMER_SETTLED=failed
	return 1
}
"""

HANDOFF = b"""setsid cttyhack /bin/sh &
PID1_REQUEST=/run/pmos-pid1-request
PID1_SCRIPT=/run/pmos-pid1-transition.sh
PID1_SHA256=@SHA256@
""" + SETTLE + b"""pid1_request_valid() {
	PID1_BOOT_ID=$(/bin/busybox cat /proc/sys/kernel/random/boot_id 2>/dev/null) || PID1_BOOT_ID=''
	case "$PID1_BOOT_ID" in
	????????-????-????-????-????????????)
		case "$PID1_BOOT_ID" in *[!0-9a-f-]*) PID1_BOOT_ID='';; esac ;;
	*) PID1_BOOT_ID='' ;;
	esac
	[ "$$" = 1 ] &&
			[ -f /run/keep ] && [ ! -L /run/keep ] &&
			[ -d /run ] && [ ! -L /run ] &&
			[ "$(/bin/busybox stat -c '%u:%a' /run 2>/dev/null)" = 0:755 ] &&
			/bin/busybox awk '$2 == "/run" {n++; if ($3 != "tmpfs") bad++} $2 == "/" {r++; if ($3 != "rootfs" && $3 != "tmpfs") bad++} END {exit(bad || n > 1 || (n == 0 && r != 1))}' /proc/mounts &&
			[ ! -L /proc/sys/kernel/random/boot_id ] &&
			[ "$(/bin/busybox id -u)" = 0 ] &&

			[ -n "$PID1_BOOT_ID" ] &&
			[ -f "$PID1_REQUEST" ] && [ ! -L "$PID1_REQUEST" ] &&
			[ "$(/bin/busybox stat -c '%u:%a:%h:%s' "$PID1_REQUEST" 2>/dev/null)" = 0:600:1:37 ] &&
			/bin/busybox printf '%s\\n' "$PID1_BOOT_ID" | /bin/busybox cmp -s - "$PID1_REQUEST" &&
			[ -f "$PID1_SCRIPT" ] && [ ! -L "$PID1_SCRIPT" ] &&
			[ "$(/bin/busybox stat -c '%u:%a:%h' "$PID1_SCRIPT" 2>/dev/null)" = 0:700:1 ] &&
			[ "$(/bin/busybox sha256sum "$PID1_SCRIPT" 2>/dev/null | /bin/busybox cut -d ' ' -f 1)" = "$PID1_SHA256" ]
}
while :; do
	if [ -e "$PID1_REQUEST" ] || [ -L "$PID1_REQUEST" ]; then
		if [ "$PID1_TIMER_SETTLED" != failed ] && pid1_request_valid &&
			pid1_settle_timer && pid1_request_valid; then
			if /bin/busybox rm -f "$PID1_REQUEST"; then
				log 'pid1 handoff accepted; sourcing pinned transition as PID1'
				if . "$PID1_SCRIPT"; then
					log 'pid1 transition returned; diagnostic console and SSH retained'
				else
					log 'pid1 transition failed; diagnostic console and SSH retained'
				fi
			fi
		else
			/bin/busybox rm -f "$PID1_REQUEST"
			log 'pid1 handoff rejected; diagnostic console and SSH retained'
		fi
	fi
	/bin/busybox sleep 1
done
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def script_bytes(path):
    path = pathlib.Path(path)
    mode = path.lstat()
    require(stat.S_ISREG(mode.st_mode) and mode.st_mode & 0o111 and
            not mode.st_mode & 0o022,
            "transition input must be a regular executable without group/world write")
    data = path.read_bytes()
    require(data.startswith(b"#!/bin/busybox sh\n") and modules.sha256(data) == TRANSITION_SHA256,
            "transition input must match the reviewed PID1 handoff SHA-256")
    guard = HERE / "pmos-pid1-guard.sh"
    require(modules.sha256(guard.read_bytes()) == GUARD_SHA256 and
            b"GUARD_SHA256=" + GUARD_SHA256.encode() in data,
            "transition guard does not match the reviewed SHA-256")
    return data


def check_refs(stock, run43, library, decode_frame):
    vendor.check_stock(stock, library)
    require(len(run43) == base.IMAGE_SIZE and modules.sha256(run43) == RUN43_SHA256,
            "previous image is not the measured 8388608-byte run-43 image")
    require(run43[:8] == b"ANDROID!" and struct.unpack_from("<I", run43, 40)[0] == 4 and
            struct.unpack_from("<I", run43, 8)[0] == 0 and
            run43[:base.RAMDISK_SIZE_OFFSET] == stock[:base.RAMDISK_SIZE_OFFSET] and
            run43[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
            run43[base.TAIL_OFFSET:] == stock[base.TAIL_OFFSET:],
            "previous image does not use the pinned stock header v4 and signed tail")
    size = struct.unpack_from("<I", run43, base.RAMDISK_SIZE_OFFSET)[0]
    require(8 < size <= base.MAX_FRAME and
            not any(run43[base.PAGE + size:base.TAIL_OFFSET]), FRAME_MSG)
    frame = run43[base.PAGE:base.PAGE + size]
    decoded = decode_frame(frame, library)
    require(vendor.encode_frame(decoded, library) == frame, FRAME_MSG)
    entries, trailer = modules.parse_newc(decoded, "run-43 generic cpio")
    require(modules.encode_newc(entries, trailer) == decoded and
            len({entry["name"] for entry in entries}) == len(entries) and
            len([entry for entry in entries if entry["name"] == "init"]) == 1 and
            not any(entry["name"].endswith(".ko") for entry in entries), CPIO_MSG)
    init = next(entry for entry in entries if entry["name"] == "init")
    require(init["mode"] & 0o170777 == 0o100755 and
            init["data"].startswith(b"#!/bin/busybox sh\n") and
            next(entry["data"] for entry in entries if entry["name"] == "run") == b"" and
            next(entry["mode"] for entry in entries if entry["name"] == "run") & 0o170777 == 0o040755 and
            init["data"].endswith(ANCHOR) and init["data"].count(ANCHOR) == 1,
            INIT_MSG)
    return entries, trailer


def expected_init(original, script):
    require(original.endswith(ANCHOR) and original.count(ANCHOR) == 1, INIT_MSG)
    digest = modules.sha256(script).encode("ascii")
    require(len(digest) == 64 and HANDOFF.count(b"@SHA256@") == 1, INIT_MSG)
    return original[:-len(ANCHOR)] + HANDOFF.replace(b"@SHA256@", digest)


def candidate_cpio(entries, trailer, script):
    original = next(entry["data"] for entry in entries if entry["name"] == "init")
    init = expected_init(original, script)
    changed = [{**entry, "data": init} if entry["name"] == "init" else entry
               for entry in entries]
    cpio = modules.encode_newc(changed, trailer)
    decoded, new_trailer = modules.parse_newc(cpio, "handoff generic cpio")
    require(len(decoded) == len(changed) and new_trailer == trailer and
            all(a["name"] == b["name"] and a["mode"] == b["mode"] and
                a["data"] == b["data"] and a["fields"][:6] == b["fields"][:6] and
                a["fields"][7:] == b["fields"][7:]
                for a, b in zip(decoded, changed)) and
            not any(entry["name"].endswith(".ko") for entry in decoded), CPIO_MSG)
    return cpio


def assemble(stock, frame):
    require(8 < len(frame) <= base.MAX_FRAME, FRAME_MSG)
    image, digest = vendor.assemble(stock, frame)
    require(digest not in REFUSED, SHA_MSG)
    require(digest == EXPECTED_SHA256, "candidate differs from reviewed PID1 image SHA-256")
    return image, digest


def build(stock, run43, script, library, decode_frame):
    entries, trailer = check_refs(stock, run43, library, decode_frame)
    cpio = candidate_cpio(entries, trailer, script)
    frame = vendor.encode_frame(cpio, library)
    return (*assemble(stock, frame), len(cpio), len(frame))


def main():
    args = sys.argv[1:]
    require(len(args) == 6 and args[0] in ("--preflight", "--build") and args[3] == "--script",
            "usage: build-init-boot-pid1-handoff.py --preflight|--build STOCK_INIT RUN43 --script TRANSITION OUTPUT")
    stock_path, run43_path, script_path, output = map(pathlib.Path,
                                                      (args[1], args[2], args[4], args[5]))
    if args[0] == "--build":
        target = output.resolve()
        require(not target.is_relative_to(HERE.parent.resolve()) and
                target not in (stock_path.resolve(), run43_path.resolve(), script_path.resolve()) and
                not output.is_symlink() and output.parent.is_dir() and
                not output.is_dir(),
                "output must be outside Git and different from every input")
    script = script_bytes(script_path)
    stock = stock_path.read_bytes()
    run43 = run43_path.read_bytes()
    verifier = load("verify-init-boot-psoc-hold-wlan-node.py", "pid1_prior_checker")
    image, digest, cpio_size, frame_size = build(stock, run43, script, base.lz4(),
                                                 verifier.hostkey_checker.decode_frame)
    print(f"transition script SHA-256: {modules.sha256(script)}")
    print(f"cpio: {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame: {frame_size}/{base.MAX_FRAME}")
    print(f"candidate: {len(image)} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        require(modules.sha256(script_path.read_bytes()) == modules.sha256(script) and
                not output.is_symlink(), "transition script or output path changed during build")
        output.write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
