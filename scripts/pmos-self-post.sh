#!/bin/busybox sh
set -eu

BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
STATE=/run/radio-bringup
GUARD=/run/pid1-guard
RADIO="$STATE/pmos-radio-bringup.sh"
PROFILE="$STATE/wpa_supplicant.conf"
RELEASE=/run/self-stage-capture-marker
RADIO_SHA=6b94e3d2f5feb68df1d87b821596bbf901aec2363d1a06add23c456f13cc97c0
umask 077

log() {
	$BB printf 'pmos-self-post: %s\n' "$*" | $BB tee -a "$STATE/self-post.log" >&2
	$BB printf 'pmos-self-post: %s\n' "$*" >/dev/kmsg 2>/dev/null || true
}
die() { log "FAIL: $*"; exit 1; }
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
	$BB awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts &&
	[ "$($BB stat -c '%d:%i' /)" = "$($BB stat -Lc '%d:%i' /proc/1/root)" ] &&
	[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] &&
	[ "$($BB stat -Lc '%d:%i' /proc/1/root)" = "$($BB cat "$GUARD/root-identity" 2>/dev/null)" ] &&
	[ "$($BB stat -c '%u:%a' "$GUARD")" = 0:700 ] ||
	die 'switched-root or guard identity check failed'
[ -f /run/keep ] && [ ! -L /run/keep ] && [ "$($BB stat -c '%u:%a' /run/keep)" = 0:600 ] ||
	die 'guest hold /run/keep absent after cutover'
log "post-cutover PID 1 on boot $boot; waiting for the host-owned guard ack"

i=0
until [ -f "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/accepted")" = "0:600:1:37" ] &&
	[ "$($BB cat "$GUARD/accepted")" = "$boot" ] &&
	[ ! -e "$GUARD/nonce" ] && [ ! -e "$GUARD/ack" ]; do
	[ "$i" -lt 150 ] || die 'host-owned guard ack not seen before the guard deadline'
	$BB sleep 1
	i=$((i + 1))
done
log "host-owned guard ack accepted on boot $boot"

[ -f "$RADIO" ] && [ ! -L "$RADIO" ] &&
	[ "$($BB stat -c '%u:%a' "$RADIO")" = 0:700 ] &&
	[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || die 'pinned radio bring-up script missing'
[ -f "$PROFILE" ] && [ ! -L "$PROFILE" ] && [ -s "$PROFILE" ] &&
	[ "$($BB stat -c '%u:%a' "$PROFILE")" = 0:600 ] || die 'protected profile missing'

used=
next_marker() {
	log "waiting for a fresh host-verified capture marker at $RELEASE for stage $1"
	i=0
	while [ ! -f "$RELEASE" ] || [ -L "$RELEASE" ]; do
		[ "$i" -lt 1200 ] || die "no host-verified capture marker released for $1"
		$BB sleep 2
		i=$((i + 2))
	done
	[ "$($BB stat -c '%u:%a:%h' "$RELEASE")" = 0:600:1 ] || die 'capture marker release is not root-only'
	[ "$($BB wc -l < "$RELEASE")" = 1 ] || die 'capture marker release is not exactly one line'
	marker=$($BB cat "$RELEASE")
	case "$marker" in
		''|*[!A-Za-z0-9_.-]*) die 'invalid capture marker release';;
	esac
	[ "${#marker}" -ge 8 ] && [ "${#marker}" -le 64 ] || die 'capture marker length invalid'
	case " $used " in *" $marker "*) die 'capture marker reused for another risky stage';; esac
	$BB dmesg 2>/dev/null | $BB grep -qF "$marker" || die 'released capture marker is not in this boot kmsg'
	$BB rm -f "$RELEASE"
	used="$used $marker"
}

for stage in modem wpss driver scan; do
	next_marker "$stage"
	$BB sh "$RADIO" "$boot" "$stage" "$marker" || die "radio bring-up $stage failed"
done
next_marker services
$BB sh "$RADIO" "$boot" services "$marker" < "$PROFILE" || die 'radio bring-up services failed'
log "self-staged OpenRC wpa_supplicant and networking started on boot $boot"
