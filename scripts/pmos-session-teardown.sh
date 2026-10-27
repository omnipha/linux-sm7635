#!/bin/busybox sh
set -eu

BB=/bin/busybox
PMOS_ROOT=/run/pmos
PMOS_TARBALL=/run/pmos-session.tar.gz
LOG=/run/pmos-teardown.log

log() { $BB printf 'pmos-teardown: %s\n' "$*" | $BB tee -a "$LOG" >&2; }
die() { log "FAIL: $*; leaving guest rootfs intact"; exit 1; }

[ ! -L "$PMOS_ROOT" ] && [ ! -L "$PMOS_ROOT/dev" ] &&
	[ ! -L "$PMOS_ROOT/dev/pts" ] && [ ! -L "$PMOS_ROOT/sys" ] &&
	[ ! -L "$PMOS_ROOT/proc" ] || die "guest mount path is a symlink"

check_mounts() {
	$BB awk -v root="$PMOS_ROOT" '
		$2 == root || index($2, root "/") == 1 {
			if ($2 == root "/proc" && $3 == "proc") proc++
			else if ($2 == root "/sys" && $3 == "sysfs") sys++
			else if ($2 == root "/dev" && $3 == "tmpfs") dev++
			else if ($2 == root "/dev/pts" && $3 == "devpts") pts++
			else bad++
		}
		END {exit(bad || proc > 1 || sys > 1 || dev > 1 || pts > 1 || (pts && !dev))}
	' /proc/mounts || die "unexpected, duplicated or shared guest mount"
	$BB awk -v dev="$PMOS_ROOT/dev" -v pts="$PMOS_ROOT/dev/pts" '
		$5 == dev {guest_dev = $3} $5 == "/dev" {outer_dev = $3}
		$5 == pts {guest_pts = $3} $5 == "/dev/pts" {outer_pts = $3}
		END {exit((guest_dev && (!outer_dev || guest_dev == outer_dev)) ||
			(guest_pts && outer_pts && guest_pts == outer_pts))}
	' /proc/self/mountinfo || die "guest dev or devpts shares diagnostic filesystem"
}

check_mounts
if [ -f "$PMOS_ROOT/run/dropbear-session.pid" ]; then
	pid=$($BB cat "$PMOS_ROOT/run/dropbear-session.pid")
	case "$pid" in ''|*[!0-9]*) die "invalid second SSH pidfile";; esac
	if [ -d "/proc/$pid" ]; then
		[ "$($BB readlink "/proc/$pid/root" 2>/dev/null || true)" = "$PMOS_ROOT" ] &&
			$BB tr '\0' ' ' < "/proc/$pid/cmdline" | $BB grep -q 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' ||
			die "pidfile does not identify the guest SSH"
		$BB kill "$pid" || die "cannot stop second SSH"
		log "stopped second SSH (pid $pid)"
	fi
fi

for d in dev/pts dev sys proc; do
	check_mounts
	if $BB awk -v path="$PMOS_ROOT/$d" '$2 == path {found++} END {exit(found != 1)}' /proc/mounts; then
		$BB umount "$PMOS_ROOT/$d" || die "unmount $d"
		log "unmounted $d"
	fi
done
check_mounts
if [ -d "$PMOS_ROOT" ]; then
	$BB rm -rf "$PMOS_ROOT" || die "remove rootfs"
	log "removed $PMOS_ROOT"
fi
[ -f "$PMOS_TARBALL" ] && $BB rm -f "$PMOS_TARBALL" && log "removed staged tarball" || true

$BB grep -q ':0016 ' /proc/net/tcp && log "diagnostic :22 listener still present" ||
	log "WARNING: diagnostic :22 listener not seen"
$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox && log "PID 1 unchanged" || true
[ -e /run/keep ] && log "/run/keep present" || log "note: /run/keep absent"
log "teardown complete; guest is clean for coordinator session close"
