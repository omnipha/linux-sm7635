#!/bin/busybox sh
set -eu

BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
PMOS_TARBALL=/run/pmos-session.tar.gz
PMOS_SHA256=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
PMOS_ROOT=/run/pmos
PMOS_SSH_PORT=2222
PMOS_MIN_MEM_KB=400000
AUTH_KEYS=/root/.ssh/authorized_keys
LOG=/run/pmos-stage.log

log() { $BB printf 'pmos-stage: %s\n' "$*" | $BB tee -a "$LOG" >&2; }
die() { log "FAIL: $*"; exit 1; }

$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox ||
	$BB grep -qa busybox /proc/1/cmdline || die "PID 1 is not the diagnostic init"
$BB grep -q ':0016 ' /proc/net/tcp || die "diagnostic :22 listener absent"

avail=$($BB awk '/MemAvailable/ {print $2; exit}' /proc/meminfo)
[ -n "$avail" ] && [ "$avail" -ge "$PMOS_MIN_MEM_KB" ] ||
	die "MemAvailable ${avail:-0} kB below ${PMOS_MIN_MEM_KB} kB floor"
log "MemAvailable ${avail} kB ok"

[ -f "$PMOS_TARBALL" ] || die "missing staged tarball $PMOS_TARBALL"
$BB printf '%s  %s\n' "$PMOS_SHA256" "$PMOS_TARBALL" | $BB sha256sum -c - ||
	die "tarball SHA-256 mismatch"
log "tarball SHA-256 verified"

[ ! -e "$PMOS_ROOT" ] || die "$PMOS_ROOT already exists; teardown first"
$BB mkdir -p "$PMOS_ROOT" || die "cannot create $PMOS_ROOT"
$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"
log "extracted userspace to $PMOS_ROOT"

$BB grep -q 'ID="postmarketos"' "$PMOS_ROOT/usr/lib/os-release" ||
	die "staged userspace is not postmarketOS"

for d in proc sys dev dev/pts run tmp; do $BB mkdir -p "$PMOS_ROOT/$d"; done
[ -f "$AUTH_KEYS" ] || die "no authorized_keys to reuse ($AUTH_KEYS)"
$BB mkdir -p "$PMOS_ROOT/root/.ssh"
$BB cp "$AUTH_KEYS" "$PMOS_ROOT/root/.ssh/authorized_keys" || die "cannot stage authorized_keys"
$BB chmod 700 "$PMOS_ROOT/root" "$PMOS_ROOT/root/.ssh"
$BB chmod 600 "$PMOS_ROOT/root/.ssh/authorized_keys"
$BB printf 'root:!:0:0:99999:7:::\n' > "$PMOS_ROOT/etc/shadow"
$BB chmod 600 "$PMOS_ROOT/etc/shadow"
log "reused existing pinned authorized_keys; locked password; key-only"

for d in proc sys dev; do
	$BB mount --bind "/$d" "$PMOS_ROOT/$d" || die "bind $d failed"
done
$BB mkdir -p "$PMOS_ROOT/dev/pts"
$BB mount -t devpts devpts "$PMOS_ROOT/dev/pts" || die "devpts failed"
[ -e "$PMOS_ROOT/dev/ptmx" ] || $BB ln -sf /dev/pts/ptmx "$PMOS_ROOT/dev/ptmx" 2>/dev/null || true
log "bound proc/sys/dev into chroot with private devpts"

$BB chroot "$PMOS_ROOT" /bin/sh -ec \
	'grep -E "^(PRETTY_NAME|ID)=" /etc/os-release; echo kernel=$(uname -r) userland=$(cat /etc/alpine-release); apk --version; uname -m' \
	>> "$LOG" 2>&1 || die "chroot shell/identity failed"
$BB chroot "$PMOS_ROOT" /bin/sh -ec 'iw --version; wpa_supplicant -v | head -1; ip -V' \
	>> "$LOG" 2>&1 || die "chroot network tools failed"
$BB grep -E '^(PRETTY_NAME|ID)=|^kernel=|^apk-tools|^aarch64$|^iw version|^wpa_supplicant v|^ip utility' "$LOG" >&2

$BB chroot "$PMOS_ROOT" /usr/bin/dropbearkey -t ed25519 -f /etc/dropbear/session_host_key \
	>> "$LOG" 2>&1 || die "second SSH host key generation failed"
$BB chmod 600 "$PMOS_ROOT/etc/dropbear/session_host_key"
$BB chroot "$PMOS_ROOT" /usr/bin/dropbearkey -y -f /etc/dropbear/session_host_key \
	> "$PMOS_ROOT/run/second-hostkey.pub" || die "cannot read second SSH public key"
$BB chmod 600 "$PMOS_ROOT/run/second-hostkey.pub"
$BB grep -E '^ssh-ed25519|^Fingerprint' "$PMOS_ROOT/run/second-hostkey.pub" >&2

$BB chroot "$PMOS_ROOT" /bin/sh -c \
	"dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:$PMOS_SSH_PORT -P /run/dropbear-session.pid" \
	>>"$LOG" 2>&1 || die "second dropbear did not start"
$BB sleep 1
$BB grep -q ":$(printf '%04X' "$PMOS_SSH_PORT") " /proc/net/tcp ||
	die "second SSH listener not present on port $PMOS_SSH_PORT"
log "second key-only SSH listening on 172.16.42.2:$PMOS_SSH_PORT (diagnostic :22 untouched)"

$BB grep -q ':0016 ' /proc/net/tcp || die "diagnostic :22 listener disappeared"
log "STAGED ok; enter with: ssh -p $PMOS_SSH_PORT root@172.16.42.2 (accept the printed key)"
