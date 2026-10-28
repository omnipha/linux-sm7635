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
$BB awk '$2 == "022A10AC:0016" && $4 == "0A" {n++} END {exit(n != 1)}' /proc/net/tcp || die "diagnostic :22 listener absent"
[ -d /run ] && [ ! -L /run ] &&
	$BB awk '
		$2 == "/run" {n++; if ($3 != "tmpfs") bad++}
		$2 == "/" {r++; if ($3 != "rootfs" && $3 != "tmpfs") root_bad++}
		END {exit(bad || (!n && (r != 1 || root_bad)))}
	' /proc/mounts ||
	die "diagnostic /run is not RAM-backed"

avail=$($BB awk '/MemAvailable/ {print $2; exit}' /proc/meminfo)
[ -n "$avail" ] && [ "$avail" -ge "$PMOS_MIN_MEM_KB" ] ||
	die "MemAvailable ${avail:-0} kB below ${PMOS_MIN_MEM_KB} kB floor"
log "MemAvailable ${avail} kB ok"

[ -f "$PMOS_TARBALL" ] && [ ! -L "$PMOS_TARBALL" ] || die "missing or symlinked staged tarball $PMOS_TARBALL"
[ "$($BB stat -c %a "$PMOS_TARBALL")" = 600 ] || die "staged tarball not root-only"
$BB printf '%s  %s\n' "$PMOS_SHA256" "$PMOS_TARBALL" | $BB sha256sum -c - ||
	die "tarball SHA-256 mismatch"
log "tarball SHA-256 verified"

[ ! -e "$PMOS_ROOT" ] && [ ! -L "$PMOS_ROOT" ] || die "$PMOS_ROOT already exists; teardown first"
$BB mkdir -m 700 "$PMOS_ROOT" || die "cannot create $PMOS_ROOT"
[ "$($BB stat -c %a "$PMOS_ROOT")" = 700 ] || die "guest root mountpoint not private"
$BB mount -t tmpfs -o mode=0700,size=256m,nosuid tmpfs "$PMOS_ROOT" || die "guest root tmpfs failed"
$BB mount --make-private "$PMOS_ROOT" || die "cannot isolate guest root mount"
$BB awk -v root="$PMOS_ROOT" '
	$2 == root {n++; if ($1 != "tmpfs" || $3 != "tmpfs" || $4 !~ /(^|,)size=262144k(,|$)/ || $4 !~ /(^|,)mode=700(,|$)/) bad++}
	END {exit(n != 1 || bad)}
' /proc/mounts &&
	$BB awk -v root="$PMOS_ROOT" '
		$5 == "/" {host_root = $3}
		$5 == "/run" {host_run = $3}
		$5 == root {n++; id = $3; if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++}
		{ids[NR] = $3; paths[NR] = $5}
		END {
			for (i = 1; i <= NR; i++) if (ids[i] == id && paths[i] != root) bad++
			exit(n != 1 || bad || !host_root || id == host_root || (host_run && id == host_run))
		}
	' /proc/self/mountinfo || die "guest root is not a separate 256m tmpfs"
for d in proc sys dev run tmp; do
	[ ! -L "$PMOS_ROOT/$d" ] || die "symlinked guest $d"
	$BB mkdir -p "$PMOS_ROOT/$d" || die "cannot create guest $d"
done
$BB mount -t tmpfs -o mode=0700,size=8m,nosuid,nodev tmpfs "$PMOS_ROOT/run" || die "guest run tmpfs failed"
$BB mount --make-private "$PMOS_ROOT/run" || die "cannot isolate guest run"
[ "$($BB stat -c '%u:%a' "$PMOS_ROOT/run")" = 0:700 ] &&
	$BB awk -v root="$PMOS_ROOT" -v path="$PMOS_ROOT/run" '
		$2 == path {n++; if ($1 != "tmpfs" || $3 != "tmpfs" || $4 !~ /(^|,)size=8192k(,|$)/ || $4 !~ /(^|,)mode=700(,|$)/) bad++}
		$2 != root && index($2, root "/") == 1 && $2 != path {bad++}
		END {exit(n != 1 || bad)}
	' /proc/mounts &&
	$BB awk -v root="$PMOS_ROOT" -v path="$PMOS_ROOT/run" '
		$5 == "/" {host_root = $3}
		$5 == "/run" {host_run = $3}
		$5 == root {base++; base_id = $1; base_dev = $3}
		$5 == path {
			n++; id = $3; parent = $2
			if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++
			for (i = 7; i <= NF && $i != "-"; i++)
				if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
		}
		{ids[NR] = $3; paths[NR] = $5}
		END {
			for (i = 1; i <= NR; i++) if (ids[i] == id && paths[i] != path) bad++
			exit(n != 1 || bad || base != 1 || parent != base_id || !host_root ||
				id == base_dev || id == host_root || (host_run && id == host_run))
		}
	' /proc/self/mountinfo || die "guest run is not a private root-only 8m tmpfs"
$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"
$BB chmod 700 "$PMOS_ROOT" || die "cannot secure guest root"
$BB chmod 700 "$PMOS_ROOT/run" || die "cannot secure guest run"
[ "$($BB stat -c '%u:%a' "$PMOS_ROOT/run")" = 0:700 ] &&
	$BB awk -v path="$PMOS_ROOT/run" '$2 == path {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/mounts ||
	die "extraction changed guest run mount"
log "extracted userspace to $PMOS_ROOT"
$BB grep -q 'ID="postmarketos"' "$PMOS_ROOT/usr/lib/os-release" ||
	die "staged userspace is not postmarketOS"
for path in "$PMOS_ROOT/etc" "$PMOS_ROOT/root" "$PMOS_ROOT/root/.ssh" "$PMOS_ROOT/etc/dropbear" "$PMOS_ROOT/sbin"; do
	[ -d "$path" ] && [ ! -L "$path" ] || die "unsafe guest directory $path"
done
[ -x "$PMOS_ROOT/sbin/openrc" ] && [ ! -L "$PMOS_ROOT/sbin/openrc" ] &&
	[ -x "$PMOS_ROOT/bin/busybox" ] && [ ! -L "$PMOS_ROOT/bin/busybox" ] ||
	die "missing distro openrc or busybox binary"
[ ! -e "$PMOS_ROOT/sbin/init" ] && [ ! -L "$PMOS_ROOT/sbin/init" ] || die "guest init already exists"
for level in sysinit boot default nonetwork shutdown; do
	path="$PMOS_ROOT/etc/runlevels/$level"
	[ -d "$path" ] && [ ! -L "$path" ] || die "missing or unsafe OpenRC runlevel $level"
	for entry in "$path"/* "$path"/.[!.]* "$path"/..?*; do
		[ ! -e "$entry" ] && [ ! -L "$entry" ] || die "unexpected enabled OpenRC service"
	done
done
[ -f "$PMOS_ROOT/etc/init.d/local" ] && [ ! -L "$PMOS_ROOT/etc/init.d/local" ] &&
	[ -x "$PMOS_ROOT/etc/init.d/local" ] &&
	[ -d "$PMOS_ROOT/etc/local.d" ] && [ ! -L "$PMOS_ROOT/etc/local.d" ] ||
	die "local OpenRC service or configuration missing"
for hook in "$PMOS_ROOT"/etc/local.d/*.start; do
	[ ! -e "$hook" ] && [ ! -L "$hook" ] || die "unexpected local startup hook"
done
$BB ln -s /etc/init.d/local "$PMOS_ROOT/etc/runlevels/default/local" || die "cannot enable RAM-only local service"
[ "$($BB readlink "$PMOS_ROOT/etc/runlevels/default/local")" = /etc/init.d/local ] ||
	die "local OpenRC service link invalid"
$BB ln -s ../bin/busybox "$PMOS_ROOT/sbin/init" || die "cannot link guest init"
[ "$($BB readlink "$PMOS_ROOT/sbin/init")" = ../bin/busybox ] || die "guest init link invalid"
$BB printf '::sysinit:/sbin/openrc sysinit\n::sysinit:/sbin/openrc boot\n::wait:/sbin/openrc default\n' > "$PMOS_ROOT/etc/inittab"
$BB chmod 600 "$PMOS_ROOT/etc/inittab"
[ -e /run/keep ] && [ ! -L /run/keep ] || die "diagnostic hold absent"
[ ! -e "$PMOS_ROOT/run/keep" ] && [ ! -L "$PMOS_ROOT/run/keep" ] || die "guest hold pre-exists"
$BB touch "$PMOS_ROOT/run/keep" || die "cannot retain old 150 s hold after cutover"
$BB chmod 600 "$PMOS_ROOT/run/keep" || die "cannot protect guest hold"
[ -f "$PMOS_ROOT/run/keep" ] && [ ! -L "$PMOS_ROOT/run/keep" ] &&
	[ "$($BB stat -c '%u:%a' "$PMOS_ROOT/run/keep")" = 0:600 ] || die "guest hold invalid"
[ -d "$PMOS_ROOT/dev" ] && [ ! -L "$PMOS_ROOT/dev" ] || die "invalid guest dev directory"
[ -f "$AUTH_KEYS" ] || die "no authorized_keys to reuse ($AUTH_KEYS)"
$BB mkdir -p "$PMOS_ROOT/root/.ssh"
$BB cp "$AUTH_KEYS" "$PMOS_ROOT/root/.ssh/authorized_keys" || die "cannot stage authorized_keys"
$BB chmod 700 "$PMOS_ROOT/root" "$PMOS_ROOT/root/.ssh"
$BB chmod 600 "$PMOS_ROOT/root/.ssh/authorized_keys"
$BB printf 'root:!:0:0:99999:7:::\n' > "$PMOS_ROOT/etc/shadow"
$BB chmod 600 "$PMOS_ROOT/etc/shadow"
log "reused existing pinned authorized_keys; locked password; key-only"

$BB mount -t proc -o nosuid,nodev,noexec proc "$PMOS_ROOT/proc" || die "guest proc mount failed"
$BB mount --make-private "$PMOS_ROOT/proc" || die "cannot isolate guest proc"
$BB mount -t sysfs -o nosuid,nodev,noexec sysfs "$PMOS_ROOT/sys" || die "guest sysfs mount failed"
$BB mount --make-private "$PMOS_ROOT/sys" || die "cannot isolate guest sysfs"
for spec in "proc proc" "sys sysfs"; do
	set -- $spec
	$BB awk -v path="$PMOS_ROOT/$1" -v type="$2" '$2 == path {n++; if ($3 != type) bad++} END {exit(n != 1 || bad)}' /proc/mounts &&
		$BB awk -v path="$PMOS_ROOT/$1" -v outer="/$1" -v type="$2" '
			$5 == path {n++; guest = $1; if ($4 != "/" || index($0, " - " type " " type " ") == 0) bad++}
			$5 == outer {host = $1}
			END {exit(n != 1 || bad || (host && guest == host))}
		' /proc/self/mountinfo || die "guest $1 mount invalid"
done
if $BB awk '$2 == "/sys/kernel/config" {n++; if ($3 != "configfs") bad++} END {exit(n != 1 || bad)}' /proc/mounts; then
	[ -d "$PMOS_ROOT/sys/kernel" ] && [ ! -L "$PMOS_ROOT/sys/kernel" ] &&
		[ -d "$PMOS_ROOT/sys/kernel/config" ] && [ ! -L "$PMOS_ROOT/sys/kernel/config" ] || die "guest configfs path invalid"
	$BB mount -t configfs -o nosuid,nodev,noexec configfs "$PMOS_ROOT/sys/kernel/config" || die "guest configfs mount failed"
	$BB mount --make-private "$PMOS_ROOT/sys/kernel/config" || die "cannot isolate guest configfs"
	$BB awk -v path="$PMOS_ROOT/sys/kernel/config" '$2 == path {n++; if ($3 != "configfs") bad++} END {exit(n != 1 || bad)}' /proc/mounts &&
		$BB awk -v path="$PMOS_ROOT/sys/kernel/config" '
			$5 == path {n++; guest = $1; if ($4 != "/" || $0 !~ / - configfs configfs /) bad++}
			$5 == "/sys/kernel/config" {outer = $1}
			END {exit(n != 1 || bad || !outer || outer == guest)}
		' /proc/self/mountinfo || die "guest configfs mount invalid"
elif $BB awk '$2 == "/sys/kernel/config" {n++} END {exit(n != 0)}' /proc/mounts; then
	:
else
	die "unexpected diagnostic configfs mount"
fi
$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$PMOS_ROOT/dev" || die "guest dev tmpfs failed"
$BB awk -v path="$PMOS_ROOT/dev" '$2 == path {found++; if ($3 != "tmpfs") bad++} END {exit(found != 1 || bad)}' /proc/mounts &&
	$BB awk -v path="$PMOS_ROOT/dev" '
		$5 == path {n++; guest = $3; if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++}
		$5 == "/dev" {outer = $3}
		END {exit(n != 1 || bad || (outer && guest == outer))}
	' /proc/self/mountinfo ||
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
node console 5 1 600
node kmsg 1 11 600
$BB mkdir "$PMOS_ROOT/dev/pts" || die "guest pts directory failed"
$BB mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$PMOS_ROOT/dev/pts" || die "private devpts failed"
$BB awk -v path="$PMOS_ROOT/dev/pts" '$2 == path {found++; if ($3 != "devpts" || $4 !~ /(^|,)ptmxmode=666(,|$)/) bad++} END {exit(found != 1 || bad)}' /proc/mounts &&
	$BB awk -v path="$PMOS_ROOT/dev/pts" '
		$5 == path {n++; guest = $3; if ($4 != "/" || $0 !~ / - devpts devpts /) bad++}
		$5 == "/dev/pts" {outer = $3}
		END {exit(n != 1 || bad || (outer && guest == outer))}
	' /proc/self/mountinfo ||
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
for spec in 'null 1:3 666' 'zero 1:5 666' 'random 1:8 666' 'urandom 1:9 666' 'tty 5:0 666' 'console 5:1 600' 'kmsg 1:b 600'; do
	set -- $spec
	[ -c "$PMOS_ROOT/dev/$1" ] && [ ! -L "$PMOS_ROOT/dev/$1" ] &&
		[ "$($BB stat -c '%t:%T %a' "$PMOS_ROOT/dev/$1")" = "$2 $3" ] ||
		die "missing or incorrect guest node $1"
done
$BB chroot "$PMOS_ROOT" /bin/sh -ec '[ -c /dev/tty ] && [ -c /dev/null ] && [ -c /dev/ptmx ] && [ -c /dev/pts/ptmx ]' ||
	die "guest device paths unavailable in chroot"
$BB chroot "$PMOS_ROOT" /bin/busybox --help >/dev/null 2>&1 &&
	$BB chroot "$PMOS_ROOT" /sbin/openrc --version >> "$LOG" 2>&1 ||
	die "guest busybox or openrc binary cannot execute"
log "mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts"

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
[ -f "$PMOS_ROOT/run/dropbear-session.pid" ] && [ ! -L "$PMOS_ROOT/run/dropbear-session.pid" ] ||
	die "second SSH pidfile missing"
pid=$($BB cat "$PMOS_ROOT/run/dropbear-session.pid")
case "$pid" in ''|*[!0-9]*) die "invalid second SSH pid";; esac
[ -d "/proc/$pid" ] &&
	[ "$($BB readlink "/proc/$pid/root" 2>/dev/null)" = "$PMOS_ROOT" ] &&
	[ "$($BB stat -Lc '%d:%i' "/proc/$pid/root")" = "$($BB stat -c '%d:%i' "$PMOS_ROOT")" ] &&
	$BB tr '\000' ' ' < "/proc/$pid/cmdline" | $BB grep -q "dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:$PMOS_SSH_PORT -P /run/dropbear-session.pid " ||
	die "second SSH process not pinned to guest root"
$BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {guest++} $2 == "022A10AC:0016" && $4 == "0A" {diagnostic++} END {exit(guest != 1 || diagnostic != 1)}' /proc/net/tcp ||
	die "second or diagnostic SSH listener absent"
log "second key-only SSH listening on 172.16.42.2:$PMOS_SSH_PORT (diagnostic :22 untouched)"
log "STAGED ok; enter with: ssh -p $PMOS_SSH_PORT root@172.16.42.2 (accept the printed key)"
