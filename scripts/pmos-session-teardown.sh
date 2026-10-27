#!/bin/busybox sh
set -eu

BB=/bin/busybox
PMOS_ROOT=/run/pmos
PMOS_TARBALL=/run/pmos-session.tar.gz
LOG=/run/pmos-teardown.log

log() { $BB printf 'pmos-teardown: %s\n' "$*" | $BB tee -a "$LOG" >&2; }

if [ -f "$PMOS_ROOT/run/dropbear-session.pid" ]; then
	pid=$($BB cat "$PMOS_ROOT/run/dropbear-session.pid" 2>/dev/null || true)
	[ -n "$pid" ] && $BB kill "$pid" 2>/dev/null && log "stopped second SSH (pid $pid)" || true
fi

for d in dev/pts dev sys proc; do
	if $BB grep -q " $PMOS_ROOT/$d " /proc/mounts; then
		$BB umount "$PMOS_ROOT/$d" || { log "FAIL: unmount $d; leaving rootfs intact"; exit 1; }
		log "unmounted $d"
	fi
done

if [ -d "$PMOS_ROOT" ]; then
	$BB rm -rf "$PMOS_ROOT" && log "removed $PMOS_ROOT" || { log "FAIL: remove rootfs"; exit 1; }
fi
[ -f "$PMOS_TARBALL" ] && $BB rm -f "$PMOS_TARBALL" && log "removed staged tarball" || true

$BB grep -q ':0016 ' /proc/net/tcp && log "diagnostic :22 listener still present" ||
	log "WARNING: diagnostic :22 listener not seen"
$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox && log "PID 1 unchanged" || true
[ -e /run/keep ] && log "/run/keep present" || log "note: /run/keep absent"
log "teardown complete; guest is clean for coordinator session close"
