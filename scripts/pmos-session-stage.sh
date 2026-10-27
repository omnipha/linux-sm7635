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

[ ! -e "$PMOS_ROOT" ] && [ ! -L "$PMOS_ROOT" ] || die "$PMOS_ROOT already exists; teardown first"
$BB mkdir -p "$PMOS_ROOT" || die "cannot create $PMOS_ROOT"
$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"
log "extracted userspace to $PMOS_ROOT"

$BB grep -q 'ID="postmarketos"' "$PMOS_ROOT/usr/lib/os-release" ||
	die "staged userspace is not postmarketOS"

for d in proc sys dev run tmp; do $BB mkdir -p "$PMOS_ROOT/$d"; done
[ -d "$PMOS_ROOT/dev" ] && [ ! -L "$PMOS_ROOT/dev" ] || die "invalid guest dev directory"
[ -f "$AUTH_KEYS" ] || die "no authorized_keys to reuse ($AUTH_KEYS)"
$BB mkdir -p "$PMOS_ROOT/root/.ssh"
$BB cp "$AUTH_KEYS" "$PMOS_ROOT/root/.ssh/authorized_keys" || die "cannot stage authorized_keys"
$BB chmod 700 "$PMOS_ROOT/root" "$PMOS_ROOT/root/.ssh"
$BB chmod 600 "$PMOS_ROOT/root/.ssh/authorized_keys"
$BB printf 'root:!:0:0:99999:7:::\n' > "$PMOS_ROOT/etc/shadow"
$BB chmod 600 "$PMOS_ROOT/etc/shadow"
log "reused existing pinned authorized_keys; locked password; key-only"

for d in proc sys; do
	$BB mount --bind "/$d" "$PMOS_ROOT/$d" || die "bind $d failed"
done
$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$PMOS_ROOT/dev" || die "guest dev tmpfs failed"
$BB awk -v path="$PMOS_ROOT/dev" '$2 == path && $3 == "tmpfs" {found++} END {exit(found != 1)}' /proc/mounts &&
	$BB awk -v path="$PMOS_ROOT/dev" '$5 == path {guest = $3} $5 == "/dev" {outer = $3} END {exit(!guest || !outer || guest == outer)}' /proc/self/mountinfo ||
	die "guest dev is not a separate tmpfs"

node() {
	path="$PMOS_ROOT/dev/$1"
	[ ! -e "$path" ] && [ ! -L "$path" ] || die "guest node $1 already exists"
	$BB mknod -m "$4" "$path" c "$2" "$3" || die "cannot create guest node $1"
	[ -c "$path" ] && [ ! -L "$path" ] &&
		[ "$($BB stat -c '%t:%T %a' "$path")" = "$($BB printf '%x:%x %s' "$2" "$3" "$4")" ] ||
		die "invalid guest node $1"
}
node null 1 3 666
node zero 1 5 666
node random 1 8 666
node urandom 1 9 666
node tty 5 0 666
$BB mkdir "$PMOS_ROOT/dev/pts" || die "guest pts directory failed"
$BB mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$PMOS_ROOT/dev/pts" || die "private devpts failed"
$BB awk -v path="$PMOS_ROOT/dev/pts" '$2 == path && $3 == "devpts" && $4 ~ /(^|,)ptmxmode=666(,|$)/ {found++} END {exit(found != 1)}' /proc/mounts &&
	$BB awk -v path="$PMOS_ROOT/dev/pts" '$5 == path {guest = $3} $5 == "/dev/pts" {outer = $3} END {exit(!guest || (outer && guest == outer))}' /proc/self/mountinfo ||
	die "guest devpts is not a private instance"
[ -c "$PMOS_ROOT/dev/pts/ptmx" ] &&
	[ "$($BB stat -c '%t:%T %a' "$PMOS_ROOT/dev/pts/ptmx")" = '5:2 666' ] ||
	die "guest devpts ptmx is invalid"
[ ! -e "$PMOS_ROOT/dev/ptmx" ] && [ ! -L "$PMOS_ROOT/dev/ptmx" ] || die "guest ptmx already exists"
$BB ln -s pts/ptmx "$PMOS_ROOT/dev/ptmx" || die "cannot link guest ptmx"
[ -L "$PMOS_ROOT/dev/ptmx" ] &&
	[ "$($BB readlink "$PMOS_ROOT/dev/ptmx")" = pts/ptmx ] &&
	[ "$($BB stat -L -c '%t:%T %a' "$PMOS_ROOT/dev/ptmx")" = '5:2 666' ] ||
	die "guest ptmx is not connected to private devpts"
for spec in 'null 1:3 666' 'zero 1:5 666' 'random 1:8 666' 'urandom 1:9 666' 'tty 5:0 666'; do
	set -- $spec
	[ -c "$PMOS_ROOT/dev/$1" ] && [ ! -L "$PMOS_ROOT/dev/$1" ] &&
		[ "$($BB stat -c '%t:%T %a' "$PMOS_ROOT/dev/$1")" = "$2 $3" ] ||
		die "missing or incorrect guest node $1"
done
$BB chroot "$PMOS_ROOT" /bin/sh -ec '[ -c /dev/tty ] && [ -c /dev/null ] && [ -c /dev/ptmx ] && [ -c /dev/pts/ptmx ]' ||
	die "guest device paths unavailable in chroot"
log "bound proc/sys; guest-only tmpfs dev, verified nodes and private devpts"

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
