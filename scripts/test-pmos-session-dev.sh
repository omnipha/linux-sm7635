#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ARCHIVE=${ARCHIVE:-$HOME/sm7635-build/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
PIN=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
GUARD="$HERE/pmos-pid1-guard.sh"
TRANSITION="$HERE/pmos-pid1-transition.sh"
GUARD_PIN=$(awk -F= '$1 == "GUARD_SHA256" {n++; print $2} END {if (n != 1) exit 1}' "$TRANSITION")
[ "$GUARD_PIN" = "$(sha256sum "$GUARD" | cut -d ' ' -f 1)" ] || { printf 'FAIL: transition guard pin differs from guard script\n' >&2; exit 1; }

if [ "${1:-}" != --inner ]; then
	case "${1:-}" in ''|--stage-only) :;; *) printf 'usage: %s [--stage-only]\n' "$0" >&2; exit 1;; esac
	[ -f "$ARCHIVE" ] || { printf 'missing public session archive: %s\n' "$ARCHIVE" >&2; exit 1; }
	printf '%s  %s\n' "$PIN" "$ARCHIVE" | sha256sum -c -
	sudo -n true
	sudo -n unshare --mount --pid --net --fork --mount-proc \
		env HOST_ARCHIVE="$ARCHIVE" SOURCE="$HERE" /bin/busybox sh "$0" --inner "${1:-}"
	exit
fi

BB=/bin/busybox
export BB
STAGE="$SOURCE/pmos-session-stage.sh"
TEARDOWN="$SOURCE/pmos-session-teardown.sh"
TRANSITION="$SOURCE/pmos-pid1-transition.sh"
GUARD="$SOURCE/pmos-pid1-guard.sh"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
mounts_clear() {
	$BB awk '$2 == "/run/pmos" || index($2, "/run/pmos/") == 1 {bad++} END {exit(bad != 0)}' /proc/mounts || fail 'guest mounts remain'
}
root_mount() {
	$BB mkdir -m 700 /run/pmos
	$BB mount -t tmpfs -o mode=0700,size=256m tmpfs /run/pmos || fail 'fixture guest root mount'
	$BB mount --make-private /run/pmos || fail 'fixture guest root isolation'
}
run_mount() {
	$BB mkdir -m 700 /run/pmos/run
	$BB mount -t tmpfs -o mode=0700,size=8m,nosuid,nodev tmpfs /run/pmos/run || fail 'fixture guest run mount'
	$BB mount --make-private /run/pmos/run || fail 'fixture guest run isolation'
}
run_check() {
	[ -d /run/pmos/run ] && [ ! -L /run/pmos/run ] &&
		[ "$($BB stat -c '%u:%a' /run/pmos/run)" = 0:700 ] || fail 'guest run not root-only'
	$BB awk '$2 == "/run/pmos/run" {n++; if ($1 != "tmpfs" || $3 != "tmpfs" || $4 !~ /(^|,)size=8192k(,|$)/ || $4 !~ /(^|,)mode=700(,|$)/) bad++} END {exit(n != 1 || bad)}' /proc/mounts || fail 'guest run size/type'
	$BB awk '
		$5 == "/" {host = $3}
		$5 == "/run" {outer[$3] = 1}
		$5 == "/run/pmos" {base++; parent = $1; root = $3}
		$5 == "/run/pmos/run" {
			n++; id = $3; run_parent = $2
			if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++
			for (i = 7; i <= NF && $i != "-"; i++)
				if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
		}
		{ids[NR] = $3; paths[NR] = $5}
		END {
			for (i = 1; i <= NR; i++) if (ids[i] == id && paths[i] != "/run/pmos/run") bad++
			exit(n != 1 || bad || base != 1 || !host ||
				run_parent != parent || id == host || (id in outer) || id == root)
		}
	' /proc/self/mountinfo || fail 'guest run not separate/private'
}
archive_retained() {
	[ -f /run/pmos-session.tar.gz ] || fail 'archive erased after rejected teardown'
}
reject_run_teardown() {
	$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail "$1 accepted"
	archive_retained
	$BB awk '$2 == "/run/pmos" {n++} END {exit(n != 1)}' /proc/mounts || fail 'rejected root unmounted'
	outer_intact
}
clear_rejected_run() {
	if $BB awk '$2 == "/run/pmos/run" {n++} END {exit(n != 1)}' /proc/mounts; then
		$BB umount /run/pmos/run || fail 'fixture run cleanup'
	fi
	$BB umount /run/pmos || fail 'fixture root cleanup'
	$BB rmdir /run/pmos || fail 'fixture root removal'
	mounts_clear
	outer_intact
}
outer_intact() {
	[ -c /dev/tty ] && [ "$($BB stat -c '%t:%T' /dev/tty)" = '5:0' ] && [ -c /dev/pts/ptmx ] && [ ! -e /dev/guest-only ] || fail 'guest nodes leaked to diagnostic dev'
	[ "$($BB stat -c '%t:%T' /dev/ptmx)" = '5:2' ] || fail 'diagnostic ptmx changed'
	[ -f /dev/diagnostic-marker ] || fail 'diagnostic dev marker lost'
	[ -e /run/keep ] && [ "$($BB readlink /proc/1/exe)" = /usr/bin/busybox ] || fail 'diagnostic init/keep changed'
	$BB kill -0 "$diagnostic_pid" && $BB grep -q ':0016 ' /proc/net/tcp || fail 'diagnostic listener changed'
}
stop_guest() {
	if [ -d /run/pmos ]; then had_root=1; else had_root=0; fi
	$BB sh "$TEARDOWN" >/run/teardown.out 2>&1 || { $BB cat /run/teardown.out >&2; $BB awk '$2 == "/run/pmos" || index($2, "/run/pmos/") == 1 {print $2, $3, $4}' /proc/mounts >&2; fail teardown; }
	mounts_clear
	[ ! -e /run/pmos ] || fail 'root still exists'
	[ "$had_root" = 0 ] || [ ! -e /run/pmos-session.tar.gz ] || fail 'safe teardown retained archive'
	$BB awk '$2 == "/sys/kernel/config" && $3 == "configfs" {n++} END {exit(n != 1)}' /proc/mounts || fail 'diagnostic configfs mount changed'
	outer_intact
}
expect_stage_failure() {
	$BB sh "$1" >/run/stage.out 2>&1 && fail "invalid stage succeeded: $1"
	[ -z "${2:-}" ] || $BB grep -q "FAIL: $2" /run/stage.out || { $BB cat /run/stage.out >&2; fail "stage did not reject: $2"; }
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
expect_transition_failure() {
	if (log() { $BB printf '%s\n' "$*"; }; . "$TRANSITION") >/run/transition.out 2>&1; then
		fail "unsafe transition accepted: $1"
	fi
	$BB grep -q "pid1 transition refused: $1" /run/transition.out || { $BB cat /run/transition.out >&2; fail "transition did not reject: $1"; }
	[ ! -e /run/pmos/run/pid1-guard ] && [ ! -L /run/pmos/run/pid1-guard ] || fail 'failed pre-arm transition created guard state'
	outer_intact
}
transition_check() {
	run_check
	[ -f /run/pmos/run/keep ] && [ ! -L /run/pmos/run/keep ] &&
		[ "$($BB stat -c '%u:%a' /run/pmos/run/keep)" = 0:600 ] || fail 'guest hold not preserved'
	[ -f /run/pmos/run/second-hostkey.pub ] && [ ! -L /run/pmos/run/second-hostkey.pub ] &&
		[ "$($BB stat -c '%u:%a' /run/pmos/run/second-hostkey.pub)" = 0:600 ] || fail 'guest public host key missing'
	[ -f /run/pmos/run/dropbear-session.pid ] && [ ! -L /run/pmos/run/dropbear-session.pid ] || fail 'guest pidfile missing'
	pid=$($BB cat /run/pmos/run/dropbear-session.pid)
	case "$pid" in ''|*[!0-9]*) fail 'guest pidfile invalid';; esac
	[ "$($BB readlink "/proc/$pid/root")" = /run/pmos ] &&
		[ "$($BB stat -Lc '%d:%i' "/proc/$pid/root")" = "$($BB stat -c '%d:%i' /run/pmos)" ] || fail 'guest SSH root changed'
	$BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {guest++} $2 == "022A10AC:0016" && $4 == "0A" {diagnostic++} END {exit(guest != 1 || diagnostic != 1)}' /proc/net/tcp || fail 'staged listener health'
	[ "$(awk -F= '$1 == "GUARD_SHA256" {n++; print $2} END {if (n != 1) exit 1}' "$TRANSITION")" = "$(sha256sum "$GUARD" | cut -d ' ' -f 1)" ] || fail 'guard pin mismatch'
}
ancestry_check() {
	python3 - "$TRANSITION" <<'PY' || fail 'transition mountinfo ancestry models'
import pathlib, subprocess, sys

source = pathlib.Path(sys.argv[1]).read_text()
prefix = '$BB awk -v root="$ROOT" \''
suffix = "' /proc/self/mountinfo || { fail 'mount propagation or ancestry invalid'; return 1; }"
assert source.count(suffix) == 1
program = source.rsplit(prefix, 1)[1].split(suffix, 1)[0]
assert 'function isolated()' in program
live = [line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]
host_paths = {'/', '/run', '/dev', '/dev/pts', '/proc', '/sys', '/sys/kernel/config'}
guest_paths = {'/run/pmos', '/run/pmos/run', '/run/pmos/dev', '/run/pmos/dev/pts', '/run/pmos/proc', '/run/pmos/sys', '/run/pmos/sys/kernel/config'}

def entry(rows, path):
    matches = [row for row in rows if row[4] == path]
    assert matches and (path in host_paths or len(matches) == 1), (path, len(matches))
    return matches[-1]

def check(label, rows, accepted):
    result = subprocess.run(['/bin/busybox', 'awk', '-v', 'root=/run/pmos', program], input='\n'.join(' '.join(row) for row in rows) + '\n', text=True, capture_output=True)
    assert (result.returncode == 0) == accepted, (label, result.returncode, result.stdout, result.stderr)

check('live mountinfo', live, True)
selected = [row[:] for row in live if row[4] in host_paths | guest_paths]
run_mounts = [row for row in selected if row[4] == '/run']
assert run_mounts and entry(selected, '/run/pmos')[1] == run_mounts[-1][0]
assert all(row[-3] == 'tmpfs' for row in run_mounts)

separate = [row[:] for row in selected if row[4] != '/run']
outer = run_mounts[-1][:]
outer[1] = entry(separate, '/')[0]
separate.insert(1, outer)
check('separate tmpfs /run', separate, True)
wrong_parent = [row[:] for row in separate]
entry(wrong_parent, '/run/pmos')[1] = entry(wrong_parent, '/')[0]
check('separate tmpfs /run wrong ancestor', wrong_parent, False)

rootfs = [row[:] for row in selected if row[4] != '/run']
entry(rootfs, '/run/pmos')[1] = entry(rootfs, '/')[0]
entry(rootfs, '/')[2] = '0:1'
entry(rootfs, '/')[-3:-1] = ['rootfs', 'rootfs']
assert not any(row[4] == '/run' for row in rootfs)
check('rootfs /run directory', rootfs, True)

wrong_parent = [row[:] for row in rootfs]
entry(wrong_parent, '/run/pmos')[1] = entry(wrong_parent, '/dev')[0]
check('rootfs /run wrong ancestor', wrong_parent, False)

for layout, rows in [('separate tmpfs /run', separate), ('rootfs /run directory', rootfs)]:
    wrong_child = [row[:] for row in rows]
    entry(wrong_child, '/run/pmos/run')[1] = entry(wrong_child, '/')[0]
    check(layout + ' wrong guest run parent', wrong_child, False)
    for path in sorted(guest_paths):
        if not any(row[4] == path for row in rows):
            continue
        for propagation in ('shared:987654', 'master:987654', 'propagate_from:987654', 'unbindable'):
            nonprivate = [row[:] for row in rows]
            mount = entry(nonprivate, path)
            mount.insert(mount.index('-'), propagation)
            check(layout + ' ' + propagation + ' ' + path, nonprivate, False)
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
umask 077
$BB touch /run/keep
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir -p /root/.ssh
ssh-keygen -q -t ed25519 -N '' -f /run/client_key
ssh-keygen -q -t ed25519 -N '' -f /run/bad_key
ssh-keygen -q -t ed25519 -N '' -f /run/bad_host_key
$BB cp /run/client_key.pub /root/.ssh/authorized_keys
ip link set lo up
ip addr add 172.16.42.2/32 dev lo
python3 -c 'import socket,time; s=socket.socket(); s.bind(("172.16.42.2",22)); s.listen(); time.sleep(900)' &
diagnostic_pid=$!
$BB sleep 1
outer_intact

$BB sh "$TEARDOWN" >/run/teardown.out 2>&1 || fail 'empty teardown'
archive_retained
outer_intact
$BB rm /run/pmos-session.tar.gz
expect_stage_failure "$STAGE"
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB printf x >> /run/pmos-session.tar.gz
expect_stage_failure "$STAGE"
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir /run/pmos
$BB mkdir /run/pmos/run
$BB printf '%s\n' "$diagnostic_pid" > /run/pmos/run/dropbear-session.pid
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'unmounted diagnostic pidfile accepted'
archive_retained
outer_intact
$BB rm -r /run/pmos
root_mount
run_mount
$BB printf '%s\n' "$diagnostic_pid" > /run/pmos/run/dropbear-session.pid
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'diagnostic pidfile accepted'
archive_retained
outer_intact
$BB rm /run/pmos/run/dropbear-session.pid
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage missing-root.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB rm "$PMOS_ROOT/sbin/openrc"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/missing-root.sh
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage missing-local.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB rm "$PMOS_ROOT/etc/init.d/local"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/missing-local.sh 'local OpenRC service or configuration missing'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage missing-local-dir.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB rm -r "$PMOS_ROOT/etc/local.d"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/missing-local-dir.sh 'local OpenRC service or configuration missing'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage local-hook.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB touch "$PMOS_ROOT/etc/local.d/10-test.start"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/local-hook.sh 'unexpected local startup hook'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage preenabled-ssh.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB ln -s /etc/init.d/sshd "$PMOS_ROOT/etc/runlevels/default/sshd"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/preenabled-ssh.sh 'unexpected enabled OpenRC service'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage preenabled-udev.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB ln -s /etc/init.d/udev "$PMOS_ROOT/etc/runlevels/sysinit/udev"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/preenabled-udev.sh 'unexpected enabled OpenRC service'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage bad-local-link.sh '$BB ln -s /etc/init.d/local "$PMOS_ROOT/etc/runlevels/default/local"' '$BB ln -s /etc/init.d/missing "$PMOS_ROOT/etc/runlevels/default/local"'
expect_stage_failure /run/bad-local-link.sh 'local OpenRC service link invalid'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage corrupt-root.sh 'log "extracted userspace to $PMOS_ROOT"' '$BB printf x > "$PMOS_ROOT/bin/busybox"; log "extracted userspace to $PMOS_ROOT"'
expect_stage_failure /run/corrupt-root.sh
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
mutate_stage no-run.sh '$BB mount -t tmpfs -o mode=0700,size=8m,nosuid,nodev tmpfs "$PMOS_ROOT/run" || die "guest run tmpfs failed"' ':'
$BB sh /run/no-run.sh >/run/stage.out 2>&1 && fail 'stage without separate run accepted'
archive_retained
outer_intact
$BB awk '$2 == "/run/pmos/run" {bad++} END {exit(bad != 0)}' /proc/mounts || fail 'failed stage unexpectedly mounted run'
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
mutate_stage shared-run.sh '$BB mount --make-private "$PMOS_ROOT/run" || die "cannot isolate guest run"' '$BB mount --make-shared "$PMOS_ROOT/run" || die "cannot isolate guest run"'
$BB sh /run/shared-run.sh >/run/stage.out 2>&1 && fail 'stage with shared run accepted'
archive_retained
outer_intact
$BB awk '$5 == "/run/pmos/run" {n++; if ($0 !~ / shared:[0-9]+ /) bad++} END {exit(n != 1 || bad)}' /proc/self/mountinfo || fail 'failed stage run not shared'
reject_run_teardown 'failed stage with shared run'
$BB mount --make-private /run/pmos/run
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz

root_mount
$BB mkdir /run/pmos/run
$BB touch /run/pmos/partial-extraction
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
python3 -c 'import socket,time; s=socket.socket(); s.bind(("172.16.42.2",2222)); s.listen(); time.sleep(900)' &
second_pid=$!
$BB sleep 1
reject_run_teardown 'live second listener without run mount'
$BB grep -q 'second SSH listener still live' /run/reject.out || fail 'live second listener not checked'
$BB kill "$second_pid"
wait "$second_pid" 2>/dev/null || true
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
$BB mkdir -p /run/pmos/dev
$BB mount -t tmpfs tmpfs /run/pmos/dev
reject_run_teardown 'guest child without run mount'
$BB grep -q 'unexpected, duplicated or incorrectly sized guest mount' /run/reject.out || fail 'guest child not rejected without run'
$BB awk '$2 == "/run/pmos/dev" {n++} END {exit(n != 1)}' /proc/mounts || fail 'guest child removed without run'
$BB umount /run/pmos/dev
clear_rejected_run
root_mount
$BB mkdir /run/pmos/unknown
$BB mount -t tmpfs tmpfs /run/pmos/unknown
reject_run_teardown 'unknown child without run mount'
$BB grep -q 'unexpected, duplicated or incorrectly sized guest mount' /run/reject.out || fail 'unknown child not rejected without run'
$BB umount /run/pmos/unknown
clear_rejected_run
root_mount
$BB mkdir /run/pmos/run
$BB printf '%s\n' "$diagnostic_pid" > /run/pmos/run/dropbear-session.pid
reject_run_teardown 'unmounted guest run pidfile'
$BB grep -q 'guest run absent with second SSH pidfile' /run/reject.out || fail 'unmounted guest pidfile not checked'
$BB rm /run/pmos/run/dropbear-session.pid
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
$BB mkdir /run/pmos/run
$BB mount --make-shared /run/pmos
reject_run_teardown 'shared root without run mount'
$BB grep -q 'guest mount identity or source invalid' /run/reject.out || fail 'shared root not checked'
$BB mount --make-private /run/pmos
clear_rejected_run
root_mount
$BB mkdir /run/pmos/duplicate
$BB mount --bind /run/pmos /run/pmos/duplicate
reject_run_teardown 'duplicate root identity without run mount'
$BB grep -q 'unexpected, duplicated or incorrectly sized guest mount' /run/reject.out || fail 'duplicate root not rejected without run'
$BB umount /run/pmos/duplicate
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
$BB mkdir /run/pmos/run
$BB cp "$BB" /run/pmos/busybox
$BB chroot /run/pmos /busybox sleep 900 &
guest_pid=$!
$BB sleep 1
reject_run_teardown 'live guest process without run mount'
$BB grep -q 'guest process still live' /run/reject.out || fail 'live guest process not checked'
$BB kill "$guest_pid"
wait "$guest_pid" 2>/dev/null || true
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
$BB mkdir /run/pmos/run
$BB umount /run/pmos
$BB mount -t tmpfs -o mode=0700,size=128m tmpfs /run/pmos
reject_run_teardown 'wrong-sized root without run mount'
$BB grep -q 'unexpected, duplicated or incorrectly sized guest mount' /run/reject.out || fail 'wrong-sized root not checked without run'
clear_rejected_run
root_mount
$BB mkdir /run/pmos/run
$BB mount --bind /run /run/pmos/run
reject_run_teardown 'shared diagnostic run mount'
[ -e /run/pmos/run/keep ] || fail 'shared run mount changed'
clear_rejected_run
root_mount
$BB mkdir /run/pmos/run
$BB mount -t tmpfs -o mode=0700,size=4m tmpfs /run/pmos/run
reject_run_teardown 'wrong-sized guest run'
clear_rejected_run
root_mount
run_mount
$BB mkdir /run/pmos/run/duplicate
$BB mount --bind /run/pmos/run /run/pmos/run/duplicate
reject_run_teardown 'duplicate guest run identity'
$BB umount /run/pmos/run/duplicate
clear_rejected_run
root_mount
run_mount
$BB mkdir /run/pmos/run/unknown
$BB mount -t tmpfs tmpfs /run/pmos/run/unknown
reject_run_teardown 'unknown guest run child'
$BB umount /run/pmos/run/unknown
clear_rejected_run
root_mount
run_mount
$BB mount --make-shared /run/pmos/run
reject_run_teardown 'shared propagation guest run'
$BB mount --make-private /run/pmos/run
clear_rejected_run
root_mount
run_mount
$BB mkdir -p /run/pmos/dev/pts /run/pmos/sys /run/pmos/proc
$BB mount -t proc proc /run/pmos/proc
$BB mount -t sysfs sysfs /run/pmos/sys
if $BB awk '$2 == "/sys/kernel/config" && $3 == "configfs" {n++} END {exit(n != 1)}' /proc/mounts; then
	$BB mount -t configfs configfs /run/pmos/sys/kernel/config || fail 'fixture configfs'
fi
$BB mount -t tmpfs -o mode=0755 tmpfs /run/pmos/dev
$BB mkdir /run/pmos/dev/pts
$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts /run/pmos/dev/pts
stop_guest
$BB awk '/unmounted dev\/pts/ {pts=NR} /unmounted dev$/ {dev=NR} /unmounted sys\/kernel\/config$/ {config=NR} /unmounted sys$/ {sys=NR} /unmounted proc$/ {proc=NR} /unmounted run$/ {run=NR} /unmounted guest root$/ {root=NR} END {exit(!(pts && pts<dev && dev<sys && sys<proc && proc<run && run<root && (!config || (dev<config && config<sys))))}' /run/teardown.out || fail 'mounts not removed in reverse order'
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
run_mount
$BB ln -s /dev /run/pmos/dev
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'symlinked guest dev accepted'
archive_retained
[ -L /run/pmos/dev ] && outer_intact || fail 'symlinked dev cleaned unsafely'
$BB rm /run/pmos/dev
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
run_mount
$BB mkdir -p /run/pmos/dev
$BB mount --bind /dev /run/pmos/dev
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'shared outer dev accepted'
archive_retained
[ -d /run/pmos/dev ] && outer_intact || fail 'shared mount cleaned unsafely'
$BB umount /run/pmos/dev
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
run_mount
$BB mkdir -p /run/pmos/dev/pts
$BB mount -t tmpfs tmpfs /run/pmos/dev/pts
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'unexpected nested mount accepted'
archive_retained
$BB awk '$2 == "/run/pmos/dev/pts" {found++} END {exit(found != 1)}' /proc/mounts || fail 'unexpected nested mount removed'
$BB umount /run/pmos/dev/pts
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
root_mount
$BB umount /run/pmos
$BB mount -t tmpfs -o mode=0700,size=128m tmpfs /run/pmos
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'wrong root size accepted'
archive_retained
$BB awk '$2 == "/run/pmos" && $3 == "tmpfs" {n++} END {exit(n != 1)}' /proc/mounts || fail 'wrong-sized root unmounted'
$BB umount /run/pmos
$BB rmdir /run/pmos
root_mount
run_mount
$BB mkdir /run/pmos/duplicate
$BB mount --bind /run/pmos /run/pmos/duplicate
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'duplicate root identity accepted'
archive_retained
$BB umount /run/pmos/duplicate
$BB rmdir /run/pmos/duplicate
stop_guest
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB mkdir /run/pmos
$BB mount --bind /run /run/pmos
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'shared run root accepted'
archive_retained
$BB umount /run/pmos
$BB rmdir /run/pmos
$BB sh "$STAGE" >/run/stage.out 2>&1 || { $BB cat /run/stage.out >&2; fail 'fresh stage'; }
run_check
$BB awk '$2 == "/run/pmos" {n++; if ($1 != "tmpfs" || $3 != "tmpfs" || $4 !~ /(^|,)size=262144k(,|$)/ || $4 !~ /(^|,)mode=700(,|$)/) bad++} END {exit(n != 1 || bad)}' /proc/mounts || fail 'guest root size/type'
$BB awk '$5 == "/run/pmos" {n++; guest = $3} $5 == "/run" {run[$3] = 1} $5 == "/" {host = $3} END {exit(n != 1 || !host || (guest in run) || guest == host)}' /proc/self/mountinfo || fail 'guest root identity'
[ -x /run/pmos/sbin/openrc ] && [ ! -L /run/pmos/sbin/openrc ] && [ -x /run/pmos/bin/busybox ] && [ ! -L /run/pmos/bin/busybox ] || fail 'missing distro init binaries'
[ "$($BB readlink /run/pmos/sbin/init)" = ../bin/busybox ] || fail 'guest init symlink'
$BB printf '::sysinit:/sbin/openrc sysinit\n::sysinit:/sbin/openrc boot\n::wait:/sbin/openrc default\n' | $BB cmp - /run/pmos/etc/inittab || fail 'guest inittab includes unwanted services'
actual=$($BB find /run/pmos/etc/runlevels -mindepth 1 | $BB sort)
expected=$($BB printf '%s\n' /run/pmos/etc/runlevels/boot /run/pmos/etc/runlevels/default /run/pmos/etc/runlevels/default/local /run/pmos/etc/runlevels/nonetwork /run/pmos/etc/runlevels/shutdown /run/pmos/etc/runlevels/sysinit)
[ "$actual" = "$expected" ] || fail 'unexpected OpenRC runlevel inventory'
[ "$($BB readlink /run/pmos/etc/runlevels/default/local)" = /etc/init.d/local ] &&
	[ -x /run/pmos/etc/init.d/local ] && [ -d /run/pmos/etc/local.d ] || fail 'enabled local service not backed by distro script'
for service in dropbear sshd networking wpa_supplicant udev devfs tmpfs zram-init; do
	for level in /run/pmos/etc/runlevels/*; do
		[ ! -e "$level/$service" ] && [ ! -L "$level/$service" ] || fail "forbidden OpenRC service $service"
	done
done
[ -c /run/pmos/dev/console ] && [ "$($BB stat -c '%t:%T %a' /run/pmos/dev/console)" = '5:1 600' ] &&
	[ -c /run/pmos/dev/kmsg ] && [ "$($BB stat -c '%t:%T %a' /run/pmos/dev/kmsg)" = '1:b 600' ] || fail 'guest console/kmsg invalid'
[ -c /run/pmos/dev/tty ] && [ "$($BB stat -c '%t:%T' /run/pmos/dev/tty)" = '5:0' ] || fail 'guest tty incorrect'
[ "$($BB readlink /run/pmos/dev/ptmx)" = pts/ptmx ] || fail 'guest ptmx disconnected'
transition_check
ancestry_check
if [ "${2:-}" != --stage-only ]; then
	$BB mv /run/pmos/run/keep /run/pmos/run/keep-test
	expect_transition_failure 'init, root or device inputs missing'
	$BB mv /run/pmos/run/keep-test /run/pmos/run/keep
	$BB cp "$GUARD" /run/pmos-pid1-guard.sh
	$BB chmod 700 /run/pmos-pid1-guard.sh
	$BB printf x >> /run/pmos-pid1-guard.sh
	expect_transition_failure 'guard digest mismatch'
	$BB cp "$GUARD" /run/pmos-pid1-guard.sh
	[ "$(sha256sum /run/pmos-pid1-guard.sh | cut -d ' ' -f 1)" = "$(sha256sum "$GUARD" | cut -d ' ' -f 1)" ] || fail 'guard input copy changed'
	$BB mv /run/pmos-pid1-guard.sh /run/pmos-pid1-guard-test.sh
	expect_transition_failure 'guard input missing'
	$BB mv /run/pmos-pid1-guard-test.sh /run/pmos-pid1-guard.sh
	$BB mv /run/pmos/run/dropbear-session.pid /run/pmos/run/dropbear-session-test.pid
	expect_transition_failure 'either SSH service absent'
	$BB mv /run/pmos/run/dropbear-session-test.pid /run/pmos/run/dropbear-session.pid
	$BB printf '%s\n' "$diagnostic_pid" > /run/pmos/run/dropbear-session.pid
	expect_transition_failure 'second service changed'
	$BB printf '%s\n' "$pid" > /run/pmos/run/dropbear-session.pid
	transition_check
	expect_transition_failure 'independent recovery guard not armed'
	$BB mount --make-shared /run/pmos/dev || fail 'shared guest dev fixture'
	$BB awk '$5 == "/run/pmos/dev" {n++; if ($0 !~ / shared:[0-9]+ /) bad++} index($5, "/run/pmos/") == 1 && $0 ~ / shared:[0-9]+ / {shared++} END {exit(n != 1 || bad || shared != 1)}' /proc/self/mountinfo || fail 'exactly one guest mount did not become shared'
	expect_transition_failure 'mount propagation or ancestry invalid'
	$BB mount --make-private /run/pmos/dev || fail 'restore private guest dev'
	expect_transition_failure 'independent recovery guard not armed'
	transition_check
fi
outer_intact
$BB mknod -m 600 /run/pmos/dev/guest-only c 1 3
outer_intact
$BB rm /run/pmos/dev/guest-only
$BB mkdir /run/pmos/run/live
$BB mount -t tmpfs tmpfs /run/pmos/run/live
$BB sh "$TEARDOWN" >/run/reject.out 2>&1 && fail 'live nested mount accepted'
archive_retained
$BB awk '$2 == "/run/pmos/run/live" {found++} END {exit(found != 1)}' /proc/mounts || fail 'live mount removed'
transition_check
outer_intact
$BB umount /run/pmos/run/live
transition_check
outer_intact
if $BB awk '$2 == "/sys/kernel/config" && $3 == "configfs" {n++} END {exit(n != 1)}' /proc/mounts; then
	$BB awk '$2 == "/run/pmos/sys/kernel/config" && $3 == "configfs" {n++} END {exit(n != 1)}' /proc/mounts || fail 'guest configfs mount missing'
	$BB awk '$5 == "/sys/kernel/config" {host = $1} $5 == "/run/pmos/sys/kernel/config" {n++; guest = $1} END {exit(n != 1 || !host || host == guest)}' /proc/self/mountinfo || fail 'diagnostic configfs mount moved'
fi

$BB awk '/^ssh-ed25519 / {print "[172.16.42.2]:2222 " $0}' /run/pmos/run/second-hostkey.pub > /run/known_hosts
[ -s /run/known_hosts ] || fail 'missing synthetic guest host key'
$BB awk '{print "[172.16.42.2]:2222 " $0}' /run/bad_host_key.pub > /run/bad-known_hosts
ssh -q -T -p 2222 -i /run/bad_key -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/known_hosts root@172.16.42.2 true >/run/ssh-reject.out 2>&1 && fail 'wrong client key authenticated'
ssh -q -T -p 2222 -i /run/client_key -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/bad-known_hosts root@172.16.42.2 true >/run/ssh-reject.out 2>&1 && fail 'wrong server key authenticated'
ssh -q -T -p 2222 -i /run/client_key -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/known_hosts root@172.16.42.2 \
	'test "$(id -u)" = 0 && test ! -t 0 && test -c /dev/tty && test "$(cat /etc/alpine-release)" = 3.21.9 && test ! -e /run/openrc/softlevel' || fail 'non-PTY key-only command'
($BB sleep 5) | ssh -q -tt -p 2222 -i /run/client_key -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/known_hosts root@172.16.42.2 \
	'test -t 0 && test -t 1 && test -c /dev/tty && test -c /dev/pts/0 && test "$(/bin/busybox readlink /dev/ptmx)" = pts/ptmx' >/run/pty.out 2>&1 || { $BB cat /run/pty.out >&2; $BB grep -E 'pty|PTY|tty|TIOCS|Child connection|auth|Exit|signal' /run/pmos-stage.log >&2; fail 'key-only guest PTY allocation'; }
$BB unshare --mount $BB sh -c '
	$BB mount --make-rprivate / || exit 1
	$BB chroot /run/pmos /sbin/openrc sysinit &&
		$BB chroot /run/pmos /sbin/openrc boot &&
		$BB chroot /run/pmos /sbin/openrc default
' >/run/openrc.out 2>&1 || { $BB cat /run/openrc.out >&2; fail 'staged OpenRC runlevel pass'; }
ssh -q -T -p 2222 -i /run/client_key -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/run/known_hosts root@172.16.42.2 \
	'test "$(cat /run/openrc/softlevel)" = default && /sbin/rc-service local status && test "$(/bin/rc-status --crashed)" = ""' || { $BB cat /run/openrc.out >&2; fail 'OpenRC default softlevel or local service status'; }
$BB unshare --mount $BB sh -c '$BB mount --make-rprivate /; $BB chroot /run/pmos /sbin/rc-service networking start' >/run/net-neg.out 2>&1 || true
$BB grep -q 'could not parse /etc/network/interfaces' /run/net-neg.out &&
	! $BB chroot /run/pmos /sbin/rc-service networking status >/dev/null 2>&1 || { $BB cat /run/net-neg.out >&2; fail 'networking started without /etc/network/interfaces'; }
$BB unshare --mount $BB sh -c '$BB mount --make-rprivate /; $BB chroot /run/pmos /sbin/rc-service tmpfs start' >/run/tmpfs-neg.out 2>&1 || true
$BB grep -q 'deviceinfo file is missing' /run/tmpfs-neg.out &&
	! $BB chroot /run/pmos /sbin/rc-service tmpfs status >/dev/null 2>&1 || { $BB cat /run/tmpfs-neg.out >&2; fail 'tmpfs started without deviceinfo'; }
$BB unshare --mount $BB sh -c '$BB mount --make-rprivate /; $BB chroot /run/pmos /sbin/rc-service udev start' >/run/udev-neg.out 2>&1 || true
$BB grep -q 'Udev requires /dev to be a mounted devtmpfs' /run/udev-neg.out &&
	! $BB chroot /run/pmos /sbin/rc-service udev status >/dev/null 2>&1 || { $BB cat /run/udev-neg.out >&2; fail 'udev started on guest-private /dev tmpfs'; }
transition_check
outer_intact
stop_guest
$BB kill "$diagnostic_pid"
if [ "${2:-}" = --stage-only ]; then
	printf 'pass: host-only 256m guest root and separate 8m private guest run with keep/SSH, failed stage and unsafe teardown negatives, non-PTY and PTY key-only SSH; transition preconditions pending\n'
else
	printf 'pass: host-only 256m guest root and separate 8m private guest run with keep/SSH, isolated mounts, failed stage and unsafe teardown negatives, non-PTY and PTY key-only SSH; device PID 1 and PTY unmeasured\n'
fi
