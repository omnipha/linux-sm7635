#!/bin/busybox sh
set -u

BB=/bin/busybox
STATE=/run/pid1-guard
HELPER_SHA=fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7
MOCK_SHA=e112e65f2e9a6dc28531b45eda218284e4afb152dc3a02b588f7a25255cce2d1
MOCK_EXT4_SHA=fe72fe25364a1a08c6482bcecb3175f2c0def38af6fc02967b1edc1d6cf28e71
MODEL='Qualcomm Technologies, Inc. Volcano QRD Pro'
umask 077

fail() { $BB printf 'pid1-guard: %s\n' "$*" >&2; exit 1; }
hash() { $BB sha256sum "$1" | $BB cut -d ' ' -f 1; }
boot_id() { $BB cat /proc/sys/kernel/random/boot_id 2>/dev/null; }
uptime() { $BB awk '{print int($1)}' /proc/uptime 2>/dev/null; }
valid_id() {
	case "$1" in
		????????-????-????-????-????????????) case "$1" in *[!0-9a-f-]*) return 1;; esac;;
		*) return 1;;
	esac
}
post_root() {
	[ -L /proc/1/exe ] &&
	[ "$(hash /proc/1/exe)" = "$(hash /bin/busybox)" ] &&
	[ "$($BB stat -Lc '%d:%i' /proc/1/root 2>/dev/null)" = "$($BB cat "$STATE/root-identity" 2>/dev/null)" ] &&
	[ "$($BB stat -c '%d:%i' / 2>/dev/null)" = "$($BB cat "$STATE/root-identity" 2>/dev/null)" ] &&
	if $BB awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts; then
		return 0
	else
		[ -f "$STATE/root-contract.sh" ] && [ ! -L "$STATE/root-contract.sh" ] &&
		. "$STATE/root-contract.sh" &&
		root_contract_switched_root /proc/1/mounts /proc/1/mountinfo
	fi
}
real_device() {
	[ "$($BB uname -m)" = aarch64 ] &&
	[ -r /proc/device-tree/model ] &&
	[ "$($BB tr -d '\000' < /proc/device-tree/model)" = "$MODEL" ] &&
	[ -f /bin/restart2 ] && [ ! -L /bin/restart2 ] &&
	[ "$($BB stat -c %s /bin/restart2)" = 872 ] &&
	[ "$(hash /bin/restart2)" = "$HELPER_SHA" ]
}
mock_device() {
	[ "$($BB uname -m)" != aarch64 ] &&
	[ -f "$STATE/mock-restart2" ] && [ ! -L "$STATE/mock-restart2" ] &&
	[ "$(hash "$STATE/mock-restart2")" = "$mock_sha" ]
}
recover() {
	$BB printf 'pid1-guard: deadline reached; requesting bootloader\n' >&2
	if [ "$mode" = real ]; then
		if real_device; then
			/bin/restart2 bootloader
		else
			$BB printf 'pid1-guard: device identity or helper changed; refusing reboot\n' >&2
		fi
	else
		if mock_device; then "$STATE/mock-restart2" bootloader; fi
		[ "$mode" = mock ] && exit 1
	fi
	$BB printf 'pid1-guard: recovery returned; no generic reboot fallback\n' >&2
	while :; do $BB sleep 60; done
}
watch() {
	mode=$1
	budget=$2
	mock_sha=$3
	[ -d "$STATE" ] && [ ! -L "$STATE" ] &&
	[ "$($BB stat -c '%u:%a' "$STATE")" = 0:700 ] || fail 'unprotected state'
	case "$mode" in real|mock) :;; *) fail 'invalid mode';; esac
	if [ "$mode" = mock ]; then [ "$mock_sha" = "$MOCK_SHA" ] || [ "$mock_sha" = "$MOCK_EXT4_SHA" ] || fail 'untrusted mock'; fi
	[ ! -e "$STATE/armed" ] && [ ! -L "$STATE/armed" ] &&
	[ ! -e "$STATE/nonce" ] && [ ! -L "$STATE/nonce" ] &&
	[ ! -e "$STATE/ack" ] && [ ! -L "$STATE/ack" ] &&
	[ ! -e "$STATE/accepted" ] && [ ! -L "$STATE/accepted" ] &&
	[ ! -e "$STATE/random" ] && [ ! -L "$STATE/random" ] &&
	[ ! -e "$STATE/.nonce-new" ] && [ ! -L "$STATE/.nonce-new" ] || fail 'stale state'
	[ "$($BB cat "$STATE/root-identity" 2>/dev/null)" = "$($BB stat -c '%d:%i' /)" ] || fail 'new root identity changed'
	[ "$($BB stat -c '%d:%i' /)" != "$($BB stat -Lc '%d:%i' /proc/1/root 2>/dev/null)" ] || fail 'already switched root'
	if [ "$mode" = real ]; then real_device || fail 'not the pinned device and helper'; else mock_device || fail 'mock changed'; fi
	id=$(boot_id)
	valid_id "$id" || fail 'invalid boot ID'
	start=$(uptime)
	case "$start" in ''|*[!0-9]*) fail 'no monotonic clock';; esac
	deadline=$((start + budget))
	$BB printf '%s\n' "$id" > "$STATE/armed" || fail 'cannot arm'
	nonce=
	while :; do
		now=$(uptime)
		case "$now" in ''|*[!0-9]*) recover;; esac
		[ "$now" -ge "$start" ] && [ "$now" -lt "$deadline" ] || recover
		[ "$(boot_id)" = "$id" ] || recover
		if post_root; then
			if [ -z "$nonce" ]; then
				[ ! -e "$STATE/ack" ] && [ ! -L "$STATE/ack" ] &&
				[ ! -e "$STATE/nonce" ] && [ ! -L "$STATE/nonce" ] &&
				[ ! -e "$STATE/.ack-new" ] && [ ! -L "$STATE/.ack-new" ] || recover
				$BB dd if=/dev/urandom of="$STATE/random" bs=32 count=1 2>/dev/null || recover
				[ "$($BB stat -c %s "$STATE/random" 2>/dev/null)" = 32 ] || recover
				nonce=$(hash "$STATE/random")
				$BB rm -f "$STATE/random"
				case "$nonce" in ????????????????????????????????????????????????????????????????)
					case "$nonce" in *[!0-9a-f]*) recover;; esac;;
					*) recover;;
				esac
				$BB printf '%s\n' "$nonce" > "$STATE/.nonce-new" || recover
				$BB mv "$STATE/.nonce-new" "$STATE/nonce" || recover
			fi
			if [ -f "$STATE/ack" ] && [ ! -L "$STATE/ack" ] &&
				[ "$($BB stat -c '%u:%a:%h:%s' "$STATE/ack")" = "0:600:1:$((${#nonce} + ${#id} + 2))" ] &&
				[ "$($BB cat "$STATE/ack")" = "$nonce $id" ] &&
				[ -f "$STATE/nonce" ] && [ ! -L "$STATE/nonce" ] &&
				[ "$($BB cat "$STATE/nonce")" = "$nonce" ] && post_root; then
				$BB printf '%s\n' "$id" > "$STATE/accepted" || recover
				$BB rm -f "$STATE/nonce" "$STATE/ack" "$STATE/random"
				exit 0
			fi
		fi
		$BB sleep 1
	done
}
arm() {
	[ "$($BB id -u)" = 0 ] || fail 'root required'
	mode=$1
	root=$2
	budget=$3
	mock_source=$4
	mock_sha=$5
	case "$budget" in ''|*[!0-9]*) fail 'invalid deadline';; esac
	[ "$budget" -ge 1 ] && [ "$budget" -le 178 ] || fail 'deadline must be 1..178 seconds'
	case "$root" in /*) [ "$root" != / ] || fail 'root must be a new mount';; *) fail 'absolute root required';; esac
	case "$root" in */) fail 'root must not have trailing slash';; esac
	[ -d "$root" ] && [ ! -L "$root" ] &&
	[ "$($BB stat -c %u "$root")" = 0 ] &&
	[ -d "$root/run" ] && [ ! -L "$root/run" ] &&
	[ "$($BB stat -c '%u:%a' "$root/run")" = 0:700 ] &&
	[ -d "$root/bin" ] && [ ! -L "$root/bin" ] &&
	[ -d "$root/proc" ] && [ ! -L "$root/proc" ] &&
	[ -d "$root/dev" ] && [ ! -L "$root/dev" ] &&
	[ -x "$root/bin/busybox" ] && [ -f "$root/bin/busybox" ] &&
	[ ! -L "$root/bin/busybox" ] &&
	[ -c "$root/dev/urandom" ] &&
	[ "$($BB stat -c '%t:%T' "$root/dev/urandom")" = 1:9 ] || fail 'new root incomplete'
	if ! $BB awk -v path="$root" '$2 == path {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/mounts; then
		contract=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
		[ -f "$contract" ] || contract="$(dirname -- "$0")/pmos-root-contract.sh"
		[ -f "$contract" ] && [ ! -L "$contract" ] && . "$contract" &&
		root_contract_pinned_userdata "$root" || fail 'new root is not mounted tmpfs or pinned userdata ext4'
	fi
	$BB awk -v path="$root/proc" '$2 == path {n++; if ($3 != "proc") bad++} END {exit(n != 1 || bad)}' /proc/mounts || fail 'new root has no proc mount'
	[ -r "$root/proc/uptime" ] && [ -r "$root/proc/1/mounts" ] &&
	[ -r "$root/proc/sys/kernel/random/boot_id" ] || fail 'new proc unavailable'
	$BB chroot "$root" /bin/busybox true || fail 'new BusyBox cannot run in root'
	[ ! -e "$root$STATE" ] && [ ! -L "$root$STATE" ] || fail 'guard state already exists'
	if [ -e "$root/bin/restart2" ] || [ -L "$root/bin/restart2" ]; then
		if [ "$mode" = real ]; then
			[ -f "$root/bin/restart2" ] && [ ! -L "$root/bin/restart2" ] &&
			[ "$($BB stat -c '%u:%a:%h:%s' "$root/bin/restart2")" = 0:755:1:872 ] &&
			[ "$(hash "$root/bin/restart2")" = "$HELPER_SHA" ] || fail 'stale RESTART2 is not the pinned helper'
		else
			[ "$mode" = mock ] || fail 'invalid mode'
			fail 'guard or RESTART2 already exists'
		fi
	fi
	[ -f "$0" ] && [ ! -L "$0" ] || fail 'guard script must be a regular file'
	[ "$($BB stat -Lc '%d:%i' /proc/1/root 2>/dev/null)" != "$($BB stat -c '%d:%i' "$root")" ] || fail 'already switched root'
	if [ "$mode" = real ]; then
		[ "$($BB uname -m)" = aarch64 ] &&
		[ -r "$root/proc/device-tree/model" ] &&
		[ "$($BB tr -d '\000' < "$root/proc/device-tree/model")" = "$MODEL" ] || fail 'not the target device'
		[ -f /bin/restart2 ] && [ ! -L /bin/restart2 ] &&
		[ "$($BB stat -c %s /bin/restart2)" = 872 ] &&
		[ "$(hash /bin/restart2)" = "$HELPER_SHA" ] || fail 'unpinned RESTART2'
	else
		[ "$mode" = mock ] && [ "$($BB uname -m)" != aarch64 ] &&
		{ [ "$mock_sha" = "$MOCK_SHA" ] || [ "$mock_sha" = "$MOCK_EXT4_SHA" ]; } || fail 'mock only with pinned fixture on non-aarch64 hosts'
		[ -f "$mock_source" ] && [ ! -L "$mock_source" ] &&
		[ "$(hash "$mock_source")" = "$mock_sha" ] || fail 'mock helper hash mismatch'
	fi
	$BB mkdir -m 700 "$root$STATE" || fail 'cannot create protected state'
	[ "$($BB stat -c '%u:%a' "$root$STATE")" = 0:700 ] || fail 'state not protected'
	$BB stat -c '%d:%i' "$root" > "$root$STATE/root-identity" || fail 'cannot pin new root'
	$BB cp "$0" "$root$STATE/guard.sh" || fail 'cannot copy guard'
	[ "$(hash "$0")" = "$(hash "$root$STATE/guard.sh")" ] || fail 'guard copy changed'
	contract=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
	[ -f "$contract" ] || contract="$(dirname -- "$0")/pmos-root-contract.sh"
	if [ -f "$contract" ] && [ ! -L "$contract" ]; then
		$BB cp "$contract" "$root$STATE/root-contract.sh" || fail 'cannot copy root contract'
		[ "$(hash "$contract")" = "$(hash "$root$STATE/root-contract.sh")" ] || fail 'root contract copy changed'
	fi
	if [ "$mode" = real ]; then
		if [ ! -e "$root/bin/restart2" ] && [ ! -L "$root/bin/restart2" ]; then
			$BB cp /bin/restart2 "$root/bin/restart2" || fail 'cannot copy RESTART2'
			$BB chmod 755 "$root/bin/restart2"
		fi
		[ -f "$root/bin/restart2" ] && [ ! -L "$root/bin/restart2" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$root/bin/restart2")" = 0:755:1:872 ] &&
		[ "$(hash "$root/bin/restart2")" = "$HELPER_SHA" ] || fail 'RESTART2 copy changed'
	else
		$BB cp "$mock_source" "$root$STATE/mock-restart2" || fail 'cannot copy mock'
		$BB chmod 700 "$root$STATE/mock-restart2"
		[ "$(hash "$root$STATE/mock-restart2")" = "$mock_sha" ] || fail 'mock copy changed'
	fi
	$BB setsid $BB chroot "$root" /bin/busybox sh "$STATE/guard.sh" watch "$mode" "$budget" "$mock_sha" </dev/null >/dev/null 2>&1 &
	pid=$!
	i=0
	while [ "$i" -lt 30 ]; do
		if [ -f "$root$STATE/armed" ] && [ ! -L "$root$STATE/armed" ] &&
			[ "$($BB cat "$root$STATE/armed")" = "$(boot_id)" ] &&
			$BB kill -0 "$pid" 2>/dev/null; then
			$BB printf 'pid1-guard: armed for %s seconds\n' "$budget" >&2
			return 0
		fi
		$BB kill -0 "$pid" 2>/dev/null || fail 'guard exited before arming'
		$BB sleep 0.1
		i=$((i + 1))
	done
	fail 'guard did not arm before cutover'
}

case "$#:${1:-}" in
	3:arm) arm real "$2" "$3" '' '';;
	5:mock-arm) arm mock "$2" "$3" "$4" "$5";;
	4:watch)
		case "$2" in real|mock) :;; *) fail 'invalid mode';; esac
		case "$3" in ''|*[!0-9]*) fail 'invalid deadline';; esac
		[ "$3" -ge 1 ] && [ "$3" -le 178 ] || fail 'invalid deadline'
		watch "$2" "$3" "$4";;
	*) fail 'usage: guard.sh arm NEW_TMPFS_ROOT SECONDS | mock-arm NEW_TMPFS_ROOT SECONDS MOCK_RESTART2 MOCK_SHA256';;
esac
