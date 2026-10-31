#!/bin/busybox sh
set -eu

BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
STATE=/run/radio-bringup
GUARD=/run/pid1-guard
RADIO="$STATE/pmos-radio-bringup.sh"
PROFILE="$STATE/wpa_supplicant.conf"
RADIO_SHA=7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812
umask 077

log() {
	$BB printf 'pmos-self-post: %s\n' "$*" | $BB tee -a "$STATE/self-post.log" >&2
	$BB printf 'pmos-self-post: %s\n' "$*" >/dev/kmsg 2>/dev/null || true
}
record_fail() {
	[ "${POST_RECORD_FAIL:-0}" = 0 ] || return 0
	POST_RECORD_FAIL=1
	contract=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
	[ -f "$contract" ] && [ ! -L "$contract" ] && . "$contract" || return 0
	boot_record_id || return 0
	stamp=$($BB awk 'NF == 2 && $1 ~ /^[0-9]+([.][0-9]+)?$/ {print $1; ok=1} END {exit(!ok)}' /proc/uptime 2>/dev/null) || stamp=unknown
	boot_record_append / "pmos-self-post: FAIL: $* (uptime $stamp)" || true
}
die() { log "FAIL: $*"; record_fail "$*"; exit 1; }
hash() { $BB sha256sum "$1" 2>/dev/null | $BB cut -d ' ' -f 1; }
scrub() { $BB rm -f "$PROFILE"; }
trap scrub EXIT

[ "$($BB id -u)" = 0 ] || die 'root required'
boot=$($BB cat /proc/sys/kernel/random/boot_id 2>/dev/null) || boot=
case "$boot" in
	????????-????-????-????-????????????)
		case "$boot" in *[!0-9a-f-]*) die 'invalid boot ID';; esac;;
	*) die 'invalid boot ID';;
esac

i=0
until [ "$($BB cat /run/openrc/softlevel 2>/dev/null)" = default ] &&
	/sbin/rc-service local status >/dev/null 2>&1; do
	[ "$i" -lt 60 ] || die 'OpenRC default/local not ready'
	$BB sleep 1
	i=$((i + 1))
done

[ "$($BB sha256sum /proc/1/exe | $BB cut -d ' ' -f 1)" = "$($BB sha256sum /bin/busybox | $BB cut -d ' ' -f 1)" ] &&
	{ $BB awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts ||
		{ CONTRACT="$GUARD/root-contract.sh"
		  [ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] && . "$CONTRACT" &&
		  root_contract_switched_root /proc/1/mounts /proc/1/mountinfo; }; } &&
	[ "$($BB stat -c '%d:%i' /)" = "$($BB stat -Lc '%d:%i' /proc/1/root)" ] &&
	[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] &&
	[ "$($BB stat -Lc '%d:%i' /proc/1/root)" = "$($BB cat "$GUARD/root-identity" 2>/dev/null)" ] &&
	[ "$($BB stat -c '%u:%a' "$GUARD")" = 0:700 ] ||
	die 'switched-root or guard identity check failed'
[ -f /run/keep ] && [ ! -L /run/keep ] && [ "$($BB stat -c '%u:%a' /run/keep)" = 0:600 ] ||
	die 'guest hold /run/keep absent after cutover'
[ -f "$GUARD/armed" ] && [ ! -L "$GUARD/armed" ] &&
	[ "$($BB cat "$GUARD/armed")" = "$boot" ] &&
	[ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
	[ ! -e "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
	[ ! -e "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] ||
	die 'independent recovery guard is not armed and unacknowledged'
contract=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
[ -f "$contract" ] && [ ! -L "$contract" ] && . "$contract" || die 'post-cutover boot record contract unavailable'
boot_record_append / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" ||
	die 'post-cutover boot record append refused'
boot_record_verify / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" ||
	die 'post-cutover boot record verify refused'
log "cold-start post-cutover PID 1 on boot $boot; independent recovery guard remains unacknowledged"

[ -f "$RADIO" ] && [ ! -L "$RADIO" ] &&
	[ "$($BB stat -c '%u:%a' "$RADIO")" = 0:700 ] &&
	[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || die 'pinned radio bring-up script missing'
[ -f "$PROFILE" ] && [ ! -L "$PROFILE" ] && [ -s "$PROFILE" ] &&
	[ "$($BB stat -c '%u:%a' "$PROFILE")" = 0:600 ] || die 'protected profile missing'

guest_marker() {
	stage=$1
	[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] || die "guard changed before $stage"
	[ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/nonce")" = 0:600:1:65 ] || die "guard nonce unsafe before $stage"
	nonce=$($BB cat "$GUARD/nonce")
	case "$nonce" in ????????????????????????????????????????????????????????????????)
		case "$nonce" in *[!0-9a-f]*) die "guard nonce invalid before $stage";; esac;;
		*) die "guard nonce invalid before $stage";;
	esac
	token="guest-radio-$stage-$($BB printf '%s' "$boot:$nonce:$stage" | $BB sha256sum | $BB cut -c 1-16)"
	case "$token" in *[!A-Za-z0-9_.-]*) die "invalid guest radio marker for $stage";; esac
	[ "${#token}" -ge 8 ] && [ "${#token}" -le 64 ] || die "guest radio marker length invalid for $stage"
	[ ! -e "$STATE/$stage.marker" ] && [ ! -L "$STATE/$stage.marker" ] || die "guest radio marker for $stage already exists"
	$BB printf '%s\n' "$token" > "$STATE/$stage.marker" || die "cannot record guest radio marker for $stage"
	$BB chmod 600 "$STATE/$stage.marker" || die "cannot protect guest radio marker for $stage"
	[ -f "$STATE/$stage.marker" ] && [ ! -L "$STATE/$stage.marker" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$STATE/$stage.marker")" = "0:600:1:$((${#token} + 1))" ] &&
		[ "$($BB cat "$STATE/$stage.marker")" = "$token" ] || die "guest radio marker for $stage is unsafe"
	$BB printf 'pmos-self-post: guest radio marker %s\n' "$token" >/dev/kmsg || die "cannot publish guest radio marker for $stage"
	$BB dmesg 2>/dev/null | $BB grep -F "pmos-self-post: guest radio marker $token" | $BB wc -l | $BB grep -qx 1 ||
		die "guest radio marker for $stage is not exactly once in this boot kmsg"
	printf '%s\n' "$token"
}

for stage in modem wpss driver scan; do
	marker=$(guest_marker "$stage") || die "guest radio marker for $stage failed"
	$BB sh "$RADIO" "$boot" "$stage" "$marker" || die "radio bring-up $stage failed"
done
marker=$(guest_marker services) || die 'guest radio marker for services failed'
$BB sh "$RADIO" "$boot" services "$marker" < "$PROFILE" || die 'radio bring-up services failed'
log "self-staged OpenRC wpa_supplicant and networking started on boot $boot"
