#!/bin/sh
set -eu

BB=/bin/busybox
SCRIPT_SHA=0b85d1dc3c05b58f703618994363a9d0dbd09ecf8139573d2db15628d2497549
CANDIDATE_SHA=d90b22212812f022017a9eaaf6af58cce08a5bf08474a024b7ccb6317b51ffb7
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { $BB sha256sum "$1" | $BB cut -d ' ' -f 1; }
healthy() {
	[ "$$" != 1 ] && [ "$($BB cat /proc/1/comm)" = busybox ] &&
		[ -f /run/keep ] && [ ! -L /run/keep ] &&
		[ "$($BB stat -c '%u:%a' /run)" = 0:755 ] &&
		[ "$($BB cat /run/diagnostic.pid)" = "$DIAGNOSTIC_PID" ] &&
		$BB kill -0 "$DIAGNOSTIC_PID" 2>/dev/null &&
		[ "$($BB readlink "/proc/$DIAGNOSTIC_PID/exe")" = /bin/busybox ] &&
		[ ! -e /run/pid1-guard ] && [ ! -L /run/pid1-guard ] &&
		[ ! -e /run/pmos ] && [ ! -L /run/pmos ]
}
wait_log() {
	attempt=0
	until $BB grep -Fq "$1" /run/handoff.log; do
		[ "$attempt" -lt "${2:-10}" ] || fail "PID 1 did not log: $1"
		$BB sleep 1
		attempt=$((attempt + 1))
	done
}
request() {
	$BB printf '%s\n' "$1" > /run/pmos-pid1-request
	$BB chmod 600 /run/pmos-pid1-request
	[ "$($BB stat -c '%u:%a:%h:%s' /run/pmos-pid1-request)" = 0:600:1:37 ] || fail 'request fixture invalid'
}
rejected() {
	wait_log 'pid1 handoff rejected; diagnostic console and SSH retained'
	[ ! -e /run/pmos-pid1-request ] && [ ! -L /run/pmos-pid1-request ] || fail 'rejected request survived'
	! $BB grep -Fq 'pid1 handoff accepted' /run/handoff.log || fail 'invalid request accepted'
	! $BB grep -Fq 'pid1 transition refused' /run/handoff.log || fail 'invalid request sourced transition'
	healthy || fail 'simulated diagnostic service or hold lost after rejection'
}

if [ "${1:-}" = --worker ]; then
	[ "$#" -eq 2 ] || fail 'worker usage'
	CASE=$2
	DIAGNOSTIC_PID=$($BB cat /run/diagnostic.pid)
	[ "$(hash /test-pmos-pid1-request.sh)" = "$TEST_SHA" ] || fail 'worker test source pin changed'
	healthy || fail 'initial diagnostic service or hold missing'
	[ "$(hash /run/pmos-pid1-transition.sh)" = "$SCRIPT_SHA" ] || fail 'initial script pin invalid'
	[ "$($BB stat -c '%u:%a:%h' /run/pmos-pid1-transition.sh)" = 0:700:1 ] || fail 'initial script metadata invalid'
	case "$CASE" in
		missing)
			$BB sleep 2
			[ ! -e /run/pmos-pid1-request ] && [ ! -s /run/handoff.log ] || fail 'missing request triggered handoff'
			;;
		wrong-id)
			[ "$BOOT_ID" != 00000000-0000-0000-0000-000000000000 ] || fail 'host boot ID is zero'
			request 00000000-0000-0000-0000-000000000000
			rejected
			;;
		wrong-sha)
			$BB printf 'wrong script\n' >> /run/pmos-pid1-transition.sh
			[ "$(hash /run/pmos-pid1-transition.sh)" != "$SCRIPT_SHA" ] || fail 'script mutation failed'
			request "$BOOT_ID"
			rejected
			;;
		symlink)
			$BB ln -s /run/keep /run/pmos-pid1-request
			rejected
			;;
		bad-mode)
			request "$BOOT_ID"
			$BB chmod 644 /run/pmos-pid1-request
			rejected
			;;
		valid)
			request "$BOOT_ID"
			$BB sleep 3
			[ -f /run/pmos-pid1-request ] && [ ! -L /run/pmos-pid1-request ] || fail 'early valid request consumed before timer settled'
			[ ! -s /run/handoff.log ] || fail 'early valid request triggered handoff or transition'
			healthy || fail 'simulated diagnostics lost while timer pending'
			wait_log 'pid1 handoff accepted; sourcing pinned transition as PID1' 175
			wait_log 'pid1 transition refused: root ownership or mode'
			wait_log 'pid1 transition failed; diagnostic console and SSH retained'
			[ ! -e /run/pmos-pid1-request ] && [ ! -L /run/pmos-pid1-request ] || fail 'accepted request survived'
			! $BB grep -Fq 'pid1 handoff rejected' /run/handoff.log || fail 'valid request rejected'
			[ -f /run/timer-finished ] && [ ! -e /run/timer-reboot ] || fail 'original timer child had not finished safely'
			if [ ! -f /run/accepted-at ] || ! $BB awk -v start="$SETTLE_START" '{exit($1 - start < 151)}' /run/accepted-at; then fail 'accepted before 151 seconds from console tail'; fi
			healthy || fail 'simulated diagnostics lost after sourced transition refused'
			;;
		*) fail 'invalid worker case';;
	esac
	healthy || fail 'simulated diagnostics did not survive'
	$BB printf '%s\n' "$CASE" > /run/result
	$BB kill -TERM 1
	exit 0
fi

if [ "${1:-}" = --pid1 ]; then
	[ "$#" -eq 2 ] && [ "$$" = 1 ] || fail 'not isolated PID 1'
	CASE=$2
	[ "$($BB stat -c '%u:%a' /run)" = 0:755 ] || fail 'fixture /run mode'
	$BB awk '$2 == "/" {r++; if ($3 != "tmpfs") bad++} $2 == "/run" {n++; if ($3 != "tmpfs") bad++} END {exit(bad || r != 1 || n != 1)}' /proc/mounts || fail 'fixture is not tmpfs PID 1 root/run'
	[ "$(hash /test-pmos-pid1-request.sh)" = "$TEST_SHA" ] && [ "$(hash /run/pmos-pid1-transition.sh)" = "$SCRIPT_SHA" ] && [ "$(hash /handoff.sh)" = "$HANDOFF_SHA" ] || fail 'fixture source pin changed'
	$BB touch /run/keep /run/handoff.log
	($BB sleep 150; $BB touch /run/timer-finished; [ -e /run/keep ] || $BB touch /run/timer-reboot) &
	$BB sleep 190 &
	$BB printf '%s\n' "$!" > /run/diagnostic.pid
	trap 'if [ -f /run/result ] && [ "$($BB cat /run/result)" = "$CASE" ]; then printf "pass: %s; PID 1 request gate; simulated diagnostics survived\n" "$CASE"; exit 0; fi; $BB cat /run/worker.log /run/handoff.log >&2; fail "PID 1 stopped without worker result"' TERM
	log() { case "$*" in 'pid1 handoff accepted;'*) $BB awk '{print $1}' /proc/uptime > /run/accepted-at;; esac; $BB printf '%s\n' "$*" >> /run/handoff.log; }
	SETTLE_START=$($BB awk '{print $1}' /proc/uptime)
	export SETTLE_START
	(/bin/busybox sh /test-pmos-pid1-request.sh --worker "$CASE" > /run/worker.log 2>&1 || $BB kill -TERM 1) &
	exec </dev/null 2>/run/console.log
	set +e
	. /handoff.sh
	fail 'image handoff tail returned'
fi

if [ "${1:-}" = --inner ]; then
	[ "$#" -eq 2 ] && [ "$$" = 1 ] || fail 'fixture did not enter a PID namespace'
	CASE=$2
	$BB mount --make-rprivate / || fail 'private mount namespace unavailable'
	$BB mount -t tmpfs -o mode=0755,size=32m tmpfs /run || fail 'private host run'
	ROOT=/run/pid1-request-root
	$BB mkdir "$ROOT"
	$BB mount -t tmpfs -o mode=0755,size=32m tmpfs "$ROOT" || fail 'private initial root'
	$BB mkdir -p "$ROOT/bin" "$ROOT/proc" "$ROOT/dev" "$ROOT/run" "$ROOT/oldroot"
	$BB cp /bin/busybox "$ROOT/bin/busybox"
	for applet in sh setsid cttyhack; do $BB ln -s busybox "$ROOT/bin/$applet"; done
	[ "$(hash "$HOST_TEST")" = "$TEST_SHA" ] || fail 'host test source pin changed'
	$BB cp "$HOST_TEST" "$ROOT/test-pmos-pid1-request.sh"
	[ "$(hash "$ROOT/test-pmos-pid1-request.sh")" = "$TEST_SHA" ] || fail 'copied test source pin changed'
	python3 -B - "$HOST_RUN43" "$HOST_TRANSITION" "$HOST_BUILDER" "$SCRIPT_SHA" "$HOST_CANDIDATE" "$CANDIDATE_SHA" > "$ROOT/handoff.sh" <<'PY'
import importlib.util
import pathlib
import struct
import sys

run43_path, script_path, builder_path, script_sha, candidate_path, candidate_sha = sys.argv[1:]
spec = importlib.util.spec_from_file_location("pid1_request_builder", builder_path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
modules = builder.modules
base = builder.base
run43 = pathlib.Path(run43_path).read_bytes()
script = builder.script_bytes(script_path)
builder.require(len(run43) == base.IMAGE_SIZE and modules.sha256(run43) == builder.RUN43_SHA256,
                "not the measured run-43 image")
builder.require(modules.sha256(script) == script_sha, "transition script pin changed")

def init_cpio(image):
    size = struct.unpack_from("<I", image, base.RAMDISK_SIZE_OFFSET)[0]
    builder.require(8 < size <= base.MAX_FRAME, "ramdisk frame out of bounds")
    archive, count = modules.unpack_legacy_lz4(image[base.PAGE:base.PAGE + size], base.lz4())
    builder.require(count == 1, "ramdisk not one LZ4 block")
    return archive

old, trailer = modules.parse_newc(init_cpio(run43), "run-43 cpio")
expected_cpio = builder.candidate_cpio(old, trailer, script)
candidate = pathlib.Path(candidate_path).read_bytes()
builder.require(len(candidate) == base.IMAGE_SIZE and modules.sha256(candidate) == candidate_sha,
                "built image does not match pinned final candidate SHA-256")
builder.require(candidate[:base.RAMDISK_SIZE_OFFSET] == run43[:base.RAMDISK_SIZE_OFFSET] and
                candidate[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
                run43[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
                candidate[base.TAIL_OFFSET:] == run43[base.TAIL_OFFSET:],
                "candidate envelope differs from run-43")
cpio = init_cpio(candidate)
builder.require(cpio == expected_cpio,
                "built image cpio differs from run-43 plus the pinned transition")
entries, _ = modules.parse_newc(cpio, "PID1 candidate cpio")
init = next(entry["data"] for entry in entries if entry["name"] == "init")
original = next(entry["data"] for entry in old if entry["name"] == "init")
builder.require(init == builder.expected_init(original, script),
                "reconstructed /init differs from the pinned builder output")
tail = builder.HANDOFF.replace(b"@SHA256@", script_sha.encode())
builder.require(init.endswith(tail) and init.count(tail) == 1, "image has no unique handoff tail")
sys.stdout.buffer.write(init[-len(tail):])
PY
	HANDOFF_SHA=$(hash "$ROOT/handoff.sh")
	[ -s "$ROOT/handoff.sh" ] || fail 'candidate handoff tail missing'
	BOOT_ID=$($BB cat /proc/sys/kernel/random/boot_id)
	case "$BOOT_ID" in
		????????-????-????-????-????????????) case "$BOOT_ID" in *[!0-9a-f-]*) fail 'invalid host boot ID';; esac;;
		*) fail 'invalid host boot ID';;
	esac
	export HANDOFF_SHA BOOT_ID SCRIPT_SHA TEST_SHA
	$BB mount -t proc -o nosuid,nodev,noexec proc "$ROOT/proc" || fail 'private proc mount'
	$BB mount -t tmpfs -o mode=0755 tmpfs "$ROOT/dev" || fail 'private dev mount'
	$BB mknod -m 666 "$ROOT/dev/null" c 1 3
	$BB mknod -m 600 "$ROOT/dev/console" c 5 1
	$BB mknod -m 666 "$ROOT/dev/tty" c 5 0
	$BB mount -t tmpfs -o mode=0755 tmpfs "$ROOT/run" || fail 'private PID 1 run'
	$BB cp "$HOST_TRANSITION" "$ROOT/run/pmos-pid1-transition.sh"
	$BB chmod 700 "$ROOT/run/pmos-pid1-transition.sh"
	$BB pivot_root "$ROOT" "$ROOT/oldroot" || fail 'pivot to private root'
	$BB umount -l /oldroot || fail 'detach host root'
	$BB rmdir /oldroot
	exec /bin/busybox sh /test-pmos-pid1-request.sh --pid1 "$CASE"
fi

[ "$#" -eq 0 ] || fail 'usage: test-pmos-pid1-request.sh'
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
RUN43=${RUN43:-$HOME/sm7635-build/out/init_boot-psoc-hold-wlan-node.img}
[ -f "$RUN43" ] && [ ! -L "$RUN43" ] && [ "$(hash "$RUN43")" = 0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa ] || fail 'pinned run-43 image unavailable'
[ "$(hash "$HERE/pmos-pid1-transition.sh")" = "$SCRIPT_SHA" ] || fail 'pinned transition script unavailable'
CANDIDATE=${CANDIDATE:-$HOME/sm7635-build/out/init_boot-pid1-handoff.img}
[ -f "$CANDIDATE" ] && [ ! -L "$CANDIDATE" ] && [ "$(hash "$CANDIDATE")" = "$CANDIDATE_SHA" ] || fail 'pinned final candidate image unavailable'
TEST_SHA=$(hash "$HERE/test-pmos-pid1-request.sh")
printf 'checking built candidate cpio against pinned run-43 and current transition before executing tail\n'
sudo -n true || fail 'passwordless sudo required for host namespaces'
for case in missing wrong-id wrong-sha symlink bad-mode valid; do
	[ "$(hash "$HERE/test-pmos-pid1-request.sh")" = "$TEST_SHA" ] || fail 'host test source pin changed'
	if [ "$case" = valid ]; then limit=210; else limit=25; fi
	sudo -n timeout -k 2 "$limit" unshare --mount --pid --net --fork --kill-child --mount-proc \
		env HOST_RUN43="$RUN43" HOST_CANDIDATE="$CANDIDATE" TEST_SHA="$TEST_SHA" \
		HOST_TRANSITION="$HERE/pmos-pid1-transition.sh" \
		HOST_BUILDER="$HERE/build-init-boot-pid1-handoff.py" \
		HOST_TEST="$HERE/test-pmos-pid1-request.sh" \
		/bin/busybox sh "$HERE/test-pmos-pid1-request.sh" --inner "$case" || fail "$case isolated PID 1 fixture"
done
printf 'not exercised: real guest/SSH mount prerequisites, aarch64 device model, production guard and RESTART2, switch_root, OpenRC, post-cutover ack or recovery\n'
