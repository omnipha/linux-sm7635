#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ARCHIVE=${ARCHIVE:-$HOME/sm7635-build/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
PIN=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26

if [ "${1:-}" != --inner ]; then
	[ -f "$ARCHIVE" ] || { printf 'missing public session archive: %s\n' "$ARCHIVE" >&2; exit 1; }
	printf '%s  %s\n' "$PIN" "$ARCHIVE" | sha256sum -c -
	sudo -n true
	sudo -n unshare --mount --pid --net --fork --mount-proc \
		env HOST_ARCHIVE="$ARCHIVE" SOURCE="$HERE" /bin/busybox sh "$0" --inner
	exit
fi

BB=/bin/busybox
STAGE="$SOURCE/pmos-session-stage.sh"
TEARDOWN="$SOURCE/pmos-session-teardown.sh"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
mounts_clear() {
	$BB awk '$2 == "/run/pmos" || index($2, "/run/pmos/") == 1 {bad++} END {exit(bad != 0)}' /proc/mounts || fail 'guest mounts remain'
}
outer_intact() {
	[ -c /dev/tty ] && [ "$($BB stat -c '%t:%T' /dev/tty)" = '5:0' ] && [ -c /dev/pts/ptmx ] && [ ! -e /dev/guest-only ] || fail 'guest nodes leaked to diagnostic dev'
	[ "$($BB stat -c '%t:%T' /dev/ptmx)" = '5:2' ] || fail 'diagnostic ptmx changed'
	[ -f /dev/diagnostic-marker ] || fail 'diagnostic dev marker lost'
	[ -e /run/keep ] && [ "$($BB readlink /proc/1/exe)" = /usr/bin/busybox ] || fail 'diagnostic init/keep changed'
	$BB kill -0 "$diagnostic_pid" && $BB grep -q ':0016 ' /proc/net/tcp || fail 'diagnostic listener changed'
}
stop_guest() {
	$BB sh "$TEARDOWN" >/run/teardown.out 2>&1 || { $BB cat /run/teardown.out >&2; $BB awk '$2 == "/run/pmos" || index($2, "/run/pmos/") == 1 {print $2, $3, $4}' /proc/mounts >&2; fail teardown; }
	mounts_clear
	[ ! -e /run/pmos ] || fail 'root still exists'
	outer_intact
}
expect_stage_failure() {
	$BB sh "$1" >/run/stage.out 2>&1 && fail "invalid stage succeeded: $1"
	outer_intact
	stop_guest
}
mutate_stage() {
	python3 - "$STAGE" "/run/$1" "$2" "$3" <<'PY'
import pathlib, sys
source, destination, old, new = sys.argv[1:]
text = pathlib.Path(source).read_text()
assert text.count(old) == 1, old
pathlib.Path(destination).write_text(text.replace(old, new, 1))
PY
}

$BB mount --make-rprivate / || fail 'private mount namespace unavailable'
$BB mount -t tmpfs -o mode=0700 tmpfs /root || fail 'fixture root isolation'
$BB mount -t tmpfs -o mode=0755 tmpfs /dev || fail 'diagnostic fixture dev'
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 666 /dev/zero c 1 5
$BB mknod -m 666 /dev/urandom c 1 9
$BB mknod -m 666 /dev/random c 1 8
$BB mknod -m 666 /dev/ptmx c 5 2
$BB mknod -m 666 /dev/tty c 5 0
$BB mkdir /dev/pts
$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts /dev/pts
$BB touch /dev/diagnostic-marker
$BB mount -t tmpfs -o mode=0755 tmpfs /run || fail 'fixture RAM run'
$BB touch /run/keep
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir -p /root/.ssh
ssh-keygen -q -t ed25519 -N '' -f /run/client_key
$BB cp /run/client_key.pub /root/.ssh/authorized_keys
ip link set lo up
ip addr add 172.16.42.2/32 dev lo
python3 -c 'import socket,time; s=socket.socket(); s.bind(("172.16.42.2",22)); s.listen(); time.sleep(900)' &
diagnostic_pid=$!
$BB sleep 1
outer_intact

$BB sh "$TEARDOWN" >/run/teardown.out 2>&1 || fail 'empty teardown'
outer_intact
expect_stage_failure "$STAGE"
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir /run/pmos
$BB mkdir /run/pmos/run
$BB printf '%s\n' "$diagnostic_pid" > /run/pmos/run/dropbear-session.pid
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'diagnostic pidfile accepted'
outer_intact
$BB rm /run/pmos/run/dropbear-session.pid
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage bad-tty.sh 'node tty 5 0 666' 'node tty 5 1 666'
expect_stage_failure /run/bad-tty.sh
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage missing-tty.sh 'node tty 5 0 666' ':'
expect_stage_failure /run/missing-tty.sh
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage bad-ptmx.sh 'ln -s pts/ptmx "$PMOS_ROOT/dev/ptmx"' 'ln -s pts/wrong "$PMOS_ROOT/dev/ptmx"'
expect_stage_failure /run/bad-ptmx.sh
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage no-devpts.sh 'newinstance,ptmxmode=0666,mode=0620' 'ptmxmode=0000,mode=0620'
expect_stage_failure /run/no-devpts.sh
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz

$BB mkdir -p /run/pmos/dev /run/pmos/sys /run/pmos/proc
$BB mount --bind /proc /run/pmos/proc
$BB mount --bind /sys /run/pmos/sys
$BB mount -t tmpfs -o mode=0755 tmpfs /run/pmos/dev
$BB mkdir /run/pmos/dev/pts
$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts /run/pmos/dev/pts
stop_guest
$BB awk '/unmounted dev\/pts/ {pts=NR} /unmounted dev$/ {dev=NR} /unmounted sys$/ {sys=NR} /unmounted proc$/ {proc=NR} END {exit(!(pts && pts<dev && dev<sys && sys<proc))}' /run/teardown.out || fail 'mounts not removed in reverse order'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir /run/pmos
$BB ln -s /dev /run/pmos/dev
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'symlinked guest dev accepted'
[ -L /run/pmos/dev ] && outer_intact || fail 'symlinked dev cleaned unsafely'
$BB rm /run/pmos/dev
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir -p /run/pmos/dev
$BB mount --bind /dev /run/pmos/dev
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'shared outer dev accepted'
[ -d /run/pmos/dev ] && outer_intact || fail 'shared mount cleaned unsafely'
$BB umount /run/pmos/dev
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir -p /run/pmos/dev/pts
$BB mount -t tmpfs tmpfs /run/pmos/dev/pts
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'unexpected nested mount accepted'
$BB awk '$2 == "/run/pmos/dev/pts" {found++} END {exit(found != 1)}' /proc/mounts || fail 'unexpected nested mount removed'
$BB umount /run/pmos/dev/pts
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz

$BB sh "$STAGE" >/run/stage.out 2>&1 || { $BB cat /run/stage.out >&2; fail 'fresh stage'; }
[ -c /run/pmos/dev/tty ] && [ "$($BB stat -c '%t:%T' /run/pmos/dev/tty)" = '5:0' ] || fail 'guest tty incorrect'
[ "$($BB readlink /run/pmos/dev/ptmx)" = pts/ptmx ] || fail 'guest ptmx disconnected'
outer_intact
$BB mknod -m 600 /run/pmos/dev/guest-only c 1 3
outer_intact
$BB rm /run/pmos/dev/guest-only
$BB mkdir /run/pmos/run/live
$BB mount -t tmpfs tmpfs /run/pmos/run/live
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'live nested mount accepted'
$BB awk '$2 == "/run/pmos/run/live" {found++} END {exit(found != 1)}' /proc/mounts || fail 'live mount removed'
outer_intact
$BB umount /run/pmos/run/live
outer_intact

$BB awk '/^ssh-ed25519 / {print "[172.16.42.2]:2222 " $0}' /run/pmos/run/second-hostkey.pub > /run/known_hosts
[ -s /run/known_hosts ] || fail 'missing synthetic guest host key'
ssh -q -T -p 2222 -i /run/client_key -o BatchMode=yes -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/known_hosts root@172.16.42.2 \
	'test "$(id -u)" = 0 && test ! -t 0 && test -c /dev/tty && test "$(cat /etc/alpine-release)" = 3.21.9' || fail 'non-PTY key-only command'
($BB sleep 5) | ssh -q -tt -p 2222 -i /run/client_key -o BatchMode=yes -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/known_hosts root@172.16.42.2 \
	'test -t 0 && test -t 1 && test -c /dev/tty && test -c /dev/pts/0 && test "$(/bin/busybox readlink /dev/ptmx)" = pts/ptmx' >/run/pty.out 2>&1 || { $BB cat /run/pty.out >&2; $BB grep -E 'pty|PTY|tty|TIOCS|Child connection|auth|Exit|signal' /run/pmos-stage.log >&2; fail 'key-only guest PTY allocation'; }
outer_intact
stop_guest
$BB kill "$diagnostic_pid"
printf 'pass: isolated host guest /dev, failed and partial stage, reverse teardown, non-PTY and PTY key-only SSH; device PTY unmeasured\n'
