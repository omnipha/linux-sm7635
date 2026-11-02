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
# trace-begin
trace() {
	log "self-post-trace: $* rc=$?" || true
}
trace_state() {
	for t_name in armed nonce accepted ack root-identity root-contract.sh guard.sh; do
		if [ -e "$GUARD/$t_name" ] || [ -L "$GUARD/$t_name" ]; then
			t_info=$($BB stat -c '%F %u:%a:%h:%s' "$GUARD/$t_name" 2>/dev/null) || t_info=stat-failed
			case "$t_name" in
				armed|accepted|root-identity) t_val=$($BB cat "$GUARD/$t_name" 2>/dev/null) || t_val=unreadable;;
				*) t_val=-;;
			esac
			log "self-post-trace: state $1 guard/$t_name present [$t_info] value=$t_val" || true
		else
			log "self-post-trace: state $1 guard/$t_name absent" || true
		fi
	done
	t_info=$($BB stat -c '%u:%a' "$GUARD" 2>/dev/null) || t_info=absent
	log "self-post-trace: state $1 guard dir $t_info boot=${boot:-unset}" || true
	for t_path in /run/keep /run/pmos-root-contract.sh; do
		if [ -e "$t_path" ] || [ -L "$t_path" ]; then
			t_info=$($BB stat -c '%F %u:%a:%h:%s' "$t_path" 2>/dev/null) || t_info=stat-failed
			log "self-post-trace: state $1 $t_path present [$t_info]" || true
		else
			log "self-post-trace: state $1 $t_path absent" || true
		fi
	done
	t_up=$($BB cat /proc/uptime 2>/dev/null) || t_up=unknown
	log "self-post-trace: state $1 uptime $t_up" || true
}
# trace-end
record_fail() {
	trace "record_fail entry: $*"
	trace_state "record_fail"
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

trace 'start'
trace_state 'start'
trace 'pre check root required'
[ "$($BB id -u)" = 0 ] || die 'root required'
trace 'post check root required'
trace 'pre check boot id'
boot=$($BB cat /proc/sys/kernel/random/boot_id 2>/dev/null) || boot=
case "$boot" in
	????????-????-????-????-????????????)
		case "$boot" in *[!0-9a-f-]*) die 'invalid boot ID';; esac;;
	*) die 'invalid boot ID';;
esac
trace 'post check boot id'

trace 'openrc wait enter'
i=0
until [ "$($BB cat /run/openrc/softlevel 2>/dev/null)" = default ] &&
	/sbin/rc-service local status >/dev/null 2>&1; do
	[ "$i" -lt 60 ] || die 'OpenRC default/local not ready'
	$BB sleep 1
	i=$((i + 1))
done
trace 'openrc wait exit'

trace 'pre check switched-root and guard identity'
[ "$($BB sha256sum /proc/1/exe | $BB cut -d ' ' -f 1)" = "$($BB sha256sum /bin/busybox | $BB cut -d ' ' -f 1)" ] &&
	trace 'pid1 exe identity passed' &&
	{ $BB awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts ||
		{ CONTRACT="$GUARD/root-contract.sh"
		  trace 'root mounts not all tmpfs; guard contract fallback entered'
		  [ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] && . "$CONTRACT" &&
		  trace 'guard contract sourced' &&
		  root_contract_switched_root /proc/1/mounts /proc/1/mountinfo; }; } &&
	trace 'root mount table or guard contract passed' &&
	[ "$($BB stat -c '%d:%i' /)" = "$($BB stat -Lc '%d:%i' /proc/1/root)" ] &&
	trace 'pid1 root identity passed' &&
	[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] &&
	trace 'guard armed boot id passed' &&
	[ "$($BB stat -Lc '%d:%i' /proc/1/root)" = "$($BB cat "$GUARD/root-identity" 2>/dev/null)" ] &&
	trace 'guard root identity passed' &&
	[ "$($BB stat -c '%u:%a' "$GUARD")" = 0:700 ] ||
	die 'switched-root or guard identity check failed'
trace 'post check switched-root and guard identity'
trace 'pre check run keep'
[ -f /run/keep ] && [ ! -L /run/keep ] && [ "$($BB stat -c '%u:%a' /run/keep)" = 0:600 ] ||
	die 'guest hold /run/keep absent after cutover'
trace 'post check run keep'
trace 'pre check guard armed and unacknowledged'
i=0
while [ ! -f "$GUARD/nonce" ] || [ -L "$GUARD/nonce" ]; do
	[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] &&
		[ ! -e "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
		[ ! -e "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] ||
		die 'independent recovery guard is not armed and unacknowledged'
	[ "$i" -lt 20 ] || die 'independent recovery guard is not armed and unacknowledged'
	trace "guard nonce wait $i"
	$BB sleep 1
	i=$((i + 1))
done
[ -f "$GUARD/armed" ] && [ ! -L "$GUARD/armed" ] &&
	[ "$($BB cat "$GUARD/armed")" = "$boot" ] &&
	[ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
	[ ! -e "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
	[ ! -e "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] ||
	die 'independent recovery guard is not armed and unacknowledged'
trace 'post check guard armed and unacknowledged'
trace 'pre check post-cutover contract'
contract=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
[ -f "$contract" ] && [ ! -L "$contract" ] || contract="$GUARD/root-contract.sh"
[ -f "$contract" ] && [ ! -L "$contract" ] && . "$contract" || die 'post-cutover boot record contract unavailable'
trace 'post check post-cutover contract'
trace 'record append entry'
trace_state 'append-entry'
boot_record_append / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" ||
	die 'post-cutover boot record append refused'
trace 'record append exit'
trace 'record verify entry'
boot_record_verify / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" ||
	die 'post-cutover boot record verify refused'
trace 'record verify exit'
log "cold-start post-cutover PID 1 on boot $boot; independent recovery guard remains unacknowledged"

trace 'pre check pinned radio script'
[ -f "$RADIO" ] && [ ! -L "$RADIO" ] &&
	[ "$($BB stat -c '%u:%a' "$RADIO")" = 0:700 ] &&
	[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || die 'pinned radio bring-up script missing'
trace 'post check pinned radio script'
trace 'pre check protected profile'
[ -f "$PROFILE" ] && [ ! -L "$PROFILE" ] && [ -s "$PROFILE" ] &&
	[ "$($BB stat -c '%u:%a' "$PROFILE")" = 0:600 ] || die 'protected profile missing'
trace 'post check protected profile'

guest_marker() {
	stage=$1
	trace "guest marker $stage entry"
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
	trace "radio stage $stage entry"
	marker=$(guest_marker "$stage") || die "guest radio marker for $stage failed"
	$BB sh "$RADIO" "$boot" "$stage" "$marker" || die "radio bring-up $stage failed"
done
trace 'radio stage services entry'
marker=$(guest_marker services) || die 'guest radio marker for services failed'
$BB sh "$RADIO" "$boot" services "$marker" < "$PROFILE" || die 'radio bring-up services failed'
log "self-staged OpenRC wpa_supplicant and networking started on boot $boot"
