#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ARCHIVE=${ARCHIVE:-$HOME/sm7635-build/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
IMAGE=${IMAGE:-$HOME/sm7635-build/out/userdata-userspace.img}
BY_NAME=${BY_NAME:-$HOME/phone-second-life-data/mb003/by-name.txt}
BUILDER="$HERE/build-userdata-userspace-payload.py"
ARCHIVE_SHA=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
ARCHIVE_SIZE=23713302
PART_SIZE=33554432
SESSION_SHA=be70a27305145cabc15b70469ae7a0434fab352fb9c3d681943f73d22b92938a
TRANSITION_SHA=e1dba7135e2335c22aee0a5c0f4edb247fad5acd8100377cba3771abe5044e36
GUARD_SHA=f72a68a4c3a0e9bb7e72aa88883dcc9087a684985f5af688e34ea13c0226d3ad
RADIO_SHA=04fe93d76c5048122f1a413457c0e0f1b1abd13f78f3518d8bb12abb18762dd1
LEASE_SHA=86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { sha256sum "$1" | cut -d ' ' -f 1; }

if [ "${1:-}" != --inner ]; then
	[ "$#" -eq 0 ] || fail 'usage: test-pmos-self-stage.sh'
	for tool in python3 sudo unshare timeout cmp stat mktemp; do
		command -v "$tool" >/dev/null 2>&1 || fail "missing tool: $tool"
	done
	for path in "$ARCHIVE" "$IMAGE" "$BY_NAME" "$BUILDER" \
		"$HERE/pmos-self-stage.sh" "$HERE/pmos-self-post.sh" \
		"$HERE/pmos-session-stage.sh" "$HERE/pmos-pid1-transition.sh" \
		"$HERE/pmos-pid1-guard.sh" "$HERE/pmos-radio-bringup.sh" \
		"$HERE/wlan-udhcpc-lease.sh"; do
		[ -f "$path" ] && [ ! -L "$path" ] || fail "missing fixture input: $path"
	done
	[ "$(stat -c %s "$ARCHIVE")" = "$ARCHIVE_SIZE" ] && [ "$(hash "$ARCHIVE")" = "$ARCHIVE_SHA" ] || fail 'unpinned userspace archive'
	[ "$(stat -c %s "$IMAGE")" = "$PART_SIZE" ] || fail 'built userdata size'
	[ "$(hash "$HERE/pmos-session-stage.sh")" = "$SESSION_SHA" ] || fail 'session stage pin changed'
	[ "$(hash "$HERE/pmos-pid1-transition.sh")" = "$TRANSITION_SHA" ] || fail 'transition pin changed'
	[ "$(hash "$HERE/pmos-pid1-guard.sh")" = "$GUARD_SHA" ] || fail 'guard pin changed'
	[ "$(hash "$HERE/pmos-radio-bringup.sh")" = "$RADIO_SHA" ] || fail 'radio pin changed'
	[ "$(hash "$HERE/wlan-udhcpc-lease.sh")" = "$LEASE_SHA" ] || fail 'lease pin changed'
	export PYTHONDONTWRITEBYTECODE=1
	WORK=$(mktemp -d "${TMPDIR:-/tmp}/pmos-self-stage.XXXXXXXX")
	: > "$WORK/loops"
	cleanup() {
		while read -r dev; do sudo -n /sbin/losetup -d "$dev" >/dev/null 2>&1 || true; done < "$WORK/loops"
		rm -rf -- "$WORK"
	}
	trap cleanup EXIT
	python3 -B "$BUILDER" --self-test "$ARCHIVE" "$IMAGE" >"$WORK/builder.out" ||
		{ cat "$WORK/builder.out" >&2; fail 'userdata builder self-test'; }
	[ "$(awk '$(NF-2) == "userdata" && $(NF-1) == "->" {n++; print $NF} END {if (n != 1) exit 1}' "$BY_NAME")" = /dev/block/sda13 ] ||
		fail 'measured by-name table does not place userdata on sda13'
	before=$(hash "$IMAGE")
	python3 -B - "$HERE" "$ARCHIVE" "$IMAGE" "$WORK" <<'PY' || fail 'negative image fixtures'
import importlib.util, io, pathlib, sys, tarfile
here, archive, image, work = sys.argv[1:]
spec = importlib.util.spec_from_file_location("builder", pathlib.Path(here) / "build-userdata-userspace-payload.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
work = pathlib.Path(work)
payload = pathlib.Path(archive).read_bytes()
good = pathlib.Path(image).read_bytes()
assert builder.makefs(payload, work / "repro.img") == good
(work / "bad-fs.img").write_bytes(bytes(len(good)))
at = good.index(payload[:4096])
assert good.count(payload[:4096]) == 1
flipped = bytearray(good)
flipped[at + 1000] ^= 1
(work / "bad-byte.img").write_bytes(bytes(flipped))

def pack(members):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
        for name, kind, data, extra in members:
            info = tarfile.TarInfo(name)
            info.mtime = builder.TIMESTAMP
            if kind == "dir":
                info.type, info.mode = tarfile.DIRTYPE, 0o700
                bundle.addfile(info)
            elif kind == "link":
                info.type, info.linkname = tarfile.SYMTYPE, extra
                bundle.addfile(info)
            else:
                info.size, info.mode = len(data), extra
                bundle.addfile(info, io.BytesIO(data))
    return raw.getvalue()

d = builder.DIRECTORY
p = builder.ARCHIVE_PATH
builder.makefs_tar(pack([(d, "dir", b"", 0), (d + "/real.tar.gz", "file", payload, 0o444), (p, "link", b"", "real.tar.gz")]), work / "bad-link.img")
builder.makefs_tar(pack([(d, "dir", b"", 0), (p, "file", payload[:-1], 0o444)]), work / "bad-short.img")
builder.makefs_tar(pack([(d, "dir", b"", 0), (p, "file", payload, 0o644)]), work / "bad-mode.img")
builder.makefs_tar(pack([(d, "dir", b"", 0)]), work / "bad-missing.img")
PY
	sudo -n true || fail 'passwordless sudo required'
	attach() {
		dev=$(sudo -n /sbin/losetup -r -f --show "$1") || fail "cannot attach read-only $1"
		printf '%s\n' "$dev" >> "$WORK/loops"
		[ "$(sudo -n /sbin/blockdev --getro "$dev")" = 1 ] || fail 'loop device is writable'
		t=$(stat -c %t "$dev")
		m=$(stat -c %T "$dev")
		printf '%s:%s' "$((0x$t))" "$((0x$m))"
	}
	good=$(attach "$IMAGE")
	bad_fs=$(attach "$WORK/bad-fs.img")
	bad_byte=$(attach "$WORK/bad-byte.img")
	bad_link=$(attach "$WORK/bad-link.img")
	bad_short=$(attach "$WORK/bad-short.img")
	bad_mode=$(attach "$WORK/bad-mode.img")
	bad_missing=$(attach "$WORK/bad-missing.img")
	rw_dev=$(sudo -n /sbin/losetup -f --show "$WORK/repro.img") || fail 'cannot attach writable fixture copy'
	printf '%s\n' "$rw_dev" >> "$WORK/loops"
	bad_rw="$((0x$(stat -c %t "$rw_dev"))):$((0x$(stat -c %T "$rw_dev")))"
	sudo -n timeout -k 2 120 unshare --mount --pid --net --fork --kill-child --mount-proc \
		env HOST_ARCHIVE="$ARCHIVE" SOURCE="$HERE" GOOD="$good" BAD_FS="$bad_fs" \
		BAD_BYTE="$bad_byte" BAD_LINK="$bad_link" BAD_SHORT="$bad_short" \
		BAD_MODE="$bad_mode" BAD_MISSING="$bad_missing" BAD_RW="$bad_rw" \
		/bin/busybox sh "$0" --inner || fail 'isolated self-stage fixture'
	[ "$(hash "$IMAGE")" = "$before" ] || fail 'built userdata image changed'
	[ "$(hash "$ARCHIVE")" = "$ARCHIVE_SHA" ] || fail 'archive changed'
	python3 -B "$BUILDER" --verify "$ARCHIVE" "$IMAGE" >/dev/null || fail 'built image no longer verifies'
	sh "$HERE/test-pmos-reboot-hold.sh" || fail 'reboot-hold fixture'
	printf 'pass: host-only userdata self-stage fixture; builder self-test, read-only loop ext4 mounted ro,noload, PARTNAME, node, size, filesystem, file-content, symlink, mode and missing-file negatives rejected before staging; positive copy verified; reboot-hold over diagnostic :22 inside 145 s with wrong-boot, stale-key, symlink and late negatives; no partition write\n'
	exit 0
fi

REAL=/bin/busybox
BB=/run/busybox.real
STAGE="$SOURCE/pmos-self-stage.sh"
POST="$SOURCE/pmos-self-post.sh"
SESSION="$SOURCE/pmos-session-stage.sh"
TRANSITION="$SOURCE/pmos-pid1-transition.sh"
GUARD="$SOURCE/pmos-pid1-guard.sh"
RADIO="$SOURCE/pmos-radio-bringup.sh"
LEASE="$SOURCE/wlan-udhcpc-lease.sh"
PROFILE_TEXT='ctrl_interface=/run/wpa_supplicant
network={
	ssid="fixture"
	psk="fixture-only-secret"
}
'
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { $BB sha256sum "$1" | $BB cut -d ' ' -f 1; }

$REAL mount --make-rprivate / || fail 'private mount namespace unavailable'
$REAL mount -t tmpfs -o mode=0755,size=96m tmpfs /run || fail 'fixture run'
$REAL cp "$REAL" /run/busybox.real
BB=/run/busybox.real
$BB chmod 755 /run/busybox.real
$BB cat > /run/wrap <<'WRAP'
#!/run/busybox.real sh
R=/run/busybox.real
case "${1:-}" in
	dd) "$R" printf '%s\n' "$*" >> /run/wrap.dd;;
	mount)
		"$R" printf '%s\n' "$*" >> /run/wrap.mount
		if [ -f /run/wrap.rw ] && [ "${2:-}" = -t ] && [ "${4:-}" = -o ]; then
			exec "$R" mount -t "$3" -o rw,noload "$6" "$7"
		fi;;
	blockdev)
		if [ -f /run/wrap.size ] && [ "${2:-}" = --getsize64 ]; then exec "$R" cat /run/wrap.size; fi;;
	sleep) [ ! -f /run/wrap.nosleep ] || exit 0;;
	sh)
		if [ "${2:-}" = /run/pmos-session-stage.sh ] && [ -f /run/wrap.session ]; then
			"$R" stat -c '%u:%a:%s' /run/pmos-session.tar.gz > /run/wrap.session.out
			"$R" sha256sum /run/pmos-session.tar.gz | "$R" cut -d ' ' -f 1 >> /run/wrap.session.out
			exit 1
		fi;;
esac
exec "$R" "$@"
WRAP
$BB chmod 755 /run/wrap
target=$($BB readlink -f "$REAL")
$BB mount --bind /run/wrap "$target" || fail 'cannot install fixture busybox wrapper'
$BB mount -t tmpfs -o mode=0755,size=4m tmpfs /dev || fail 'fixture dev'
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 666 /dev/zero c 1 5
$BB mknod -m 666 /dev/urandom c 1 9
$BB mkdir -p /dev/block/by-name
$BB mkdir -p /sys/class/block
$BB mount -t tmpfs -o mode=0755,size=1m tmpfs /sys/class/block || fail 'fixture block class'
$BB mkdir -p /root/.ssh
$BB mount -t tmpfs -o mode=0700,size=1m tmpfs /root || fail 'fixture root'
$BB mkdir -p /root/.ssh
$BB printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixtureOnlyKeyMaterial fixture\n' > /root/.ssh/authorized_keys
$BB chmod 600 /root/.ssh/authorized_keys

sysfs_part() {
	$BB mkdir -p "/sys/class/block/$1"
	$BB printf 'PARTNAME=%s\n' "$2" > "/sys/class/block/$1/uevent"
	$BB printf '%s\n' "$3" > "/sys/class/block/$1/dev"
}
mk_node() {
	$BB rm -f "$1"
	$BB mknod -m 0400 "$1" b "${2%%:*}" "${2##*:}"
}
use_image() {
	sysfs_part sda13 userdata "$1"
	mk_node /dev/block/sda13 "$1"
}
install_inputs() {
	umask 077
	$BB cp "$SESSION" /run/pmos-session-stage.sh
	$BB cp "$TRANSITION" /run/pmos-pid1-transition.sh
	$BB cp "$GUARD" /run/pmos-pid1-guard.sh
	$BB cp "$RADIO" /run/pmos-radio-bringup.sh
	$BB cp "$LEASE" /run/wlan-udhcpc-lease.sh
	$BB cp "$POST" /run/pmos-self-post.sh
	$BB chmod 700 /run/pmos-session-stage.sh /run/pmos-pid1-transition.sh /run/pmos-pid1-guard.sh \
		/run/pmos-radio-bringup.sh /run/wlan-udhcpc-lease.sh /run/pmos-self-post.sh
	$BB printf '%s' "$PROFILE_TEXT" > /run/wpa_supplicant.conf
	$BB chmod 600 /run/wpa_supplicant.conf
	$BB touch /run/keep
	umask 022
}
start_listener() {
	python3 -c 'import socket,time; s=socket.socket(); s.bind(("172.16.42.2",22)); s.listen(); time.sleep(120)' &
	listener=$!
	n=0
	until $BB awk '$2 == "022A10AC:0016" && $4 == "0A" {c++} END {exit(c != 1)}' /proc/net/tcp; do
		[ "$n" -lt 50 ] || fail 'fixture :22 listener did not start'
		$BB sleep 0.1
		n=$((n + 1))
	done
}
stop_listener() {
	$BB kill "$listener" 2>/dev/null || true
	wait "$listener" 2>/dev/null || true
}
network_state() {
	ip -o link > "$1.link"
	ip -o addr > "$1.addr"
	$BB awk '{print $2, $4}' /proc/net/tcp > "$1.tcp"
}
profile_sig() {
	if [ -L /run/wpa_supplicant.conf ]; then
		printf 'symlink:%s' "$($BB readlink /run/wpa_supplicant.conf)"
	elif [ -f /run/wpa_supplicant.conf ]; then
		printf '%s:%s' "$($BB stat -c '%u:%a:%s' /run/wpa_supplicant.conf)" "$(hash /run/wpa_supplicant.conf)"
	else
		printf absent
	fi
}
not_published() {
	[ ! -e /run/pmos ] && [ ! -L /run/pmos ] || fail "$1 published a guest root"
	[ ! -e /run/pmos-pid1-request ] && [ ! -L /run/pmos-pid1-request ] || fail "$1 armed a PID 1 request"
	[ ! -e /run/radio-bringup ] || fail "$1 published radio state"
	if [ "$1" != 'userdata mount path already exists before' ] && [ "$1" != 'userdata mount path already exists' ]; then
		[ ! -e /run/omnipha-userspace ] || fail "$1 left the mount path"
	fi
	! $BB grep -qF /run/omnipha-userspace /proc/mounts || fail "$1 left userdata mounted"
	[ "$(profile_sig)" = "$PROFILE_SIG" ] || fail "$1 moved or changed the protected profile"
	network_state /run/net.after
	$BB cmp -s /run/net.base.link /run/net.after.link &&
		$BB cmp -s /run/net.base.addr /run/net.after.addr || fail "$1 changed links or addresses"
	[ ! -e /run/pmos-self-scan.raw ] && [ ! -e /run/radio-bringup/scan.raw ] || fail "$1 published a scan"
	[ ! -f /run/reject.out ] || ! $BB grep -qF fixture-only-secret /run/reject.out || fail "$1 leaked the protected profile"
	[ ! -s /run/wrap.dd ] || ! $BB grep -qE ' of=/dev/| of=/sys/' /run/wrap.dd || fail "$1 wrote a device or sysfs path"
	[ ! -s /run/wrap.mount ] || ! $BB grep -E 'ext4' /run/wrap.mount | $BB grep -qvF -- 'mount -t ext4 -o ro,noload /dev/block/sda13 /run/omnipha-userspace' || fail "$1 mounted userdata other than ro,noload"
}
reject() {
	label=$1
	: > /run/wrap.dd
	: > /run/wrap.mount
	$BB rm -f /run/reject.out
	PROFILE_SIG=$(profile_sig)
	not_published "$label before"
	set +e
	/bin/busybox sh "$STAGE" >/run/reject.out 2>&1
	rc=$?
	set -e
	[ "$rc" != 0 ] || fail "$label accepted"
	$BB grep -qF "FAIL: $label" /run/reject.out || { $BB cat /run/reject.out >&2; fail "$label did not name its failure"; }
	[ ! -e /run/pmos-session.tar.gz ] && [ ! -L /run/pmos-session.tar.gz ] || fail "$label left the archive staged"
	not_published "$label"
	printf 'rejected: %s\n' "$label"
}

PART_SIZE=33554432
ARCHIVE_SIZE=23713302
ARCHIVE_SHA=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26

ip link set lo up
ip addr add 172.16.42.2/32 dev lo
start_listener
install_inputs
sysfs_part sda6 super 259:600
$BB ln -s /dev/block/sda6 /dev/block/by-name/userdata
use_image "$GOOD"
network_state /run/net.base
$BB sh -n "$STAGE" && $BB sh -n "$POST" || fail 'self-stage or post script syntax'
[ "$($BB sed -n 's/^PARTNAME=//p' /sys/class/block/sda13/uevent)" = userdata ] || fail 'sda13 PARTNAME model'
[ "$($BB cat /sys/class/block/sda13/dev)" = "$GOOD" ] && [ "$($BB stat -c '%t:%T' /dev/block/sda13)" = "$($BB printf '%x:%x' "${GOOD%%:*}" "${GOOD##*:}")" ] || fail 'sda13 numbers model'
[ "$($BB blockdev --getsize64 /dev/block/sda13)" = "$PART_SIZE" ] && [ "$($BB blockdev --getro /dev/block/sda13)" = 1 ] || fail 'sda13 size or read-only model'
$BB dd if=/dev/zero of=/dev/block/sda13 bs=512 count=1 2>/dev/null && fail 'read-only partition model accepted a write'
$BB mkdir -m 700 /run/rwprobe
$BB mount -t ext4 -o rw /dev/block/sda13 /run/rwprobe 2>/dev/null || fail 'probe mount failed'
$BB awk '$2 == "/run/rwprobe" && $4 ~ /(^|,)ro(,|$)/ {ok=1} END {exit(ok != 1)}' /proc/mounts || fail 'read-only loop mounted read-write'
$BB umount /run/rwprobe && $BB rmdir /run/rwprobe || fail 'probe unmount failed'
: > /run/wrap.mount

$BB rm /run/keep
$BB touch /run/wrap.nosleep
reject 'diagnostic hold not set before self-recovery deadline'
$BB rm /run/wrap.nosleep
$BB touch /run/keep

$BB rm /run/wpa_supplicant.conf
reject 'protected profile missing or not root-only'
install_inputs
$BB chmod 644 /run/wpa_supplicant.conf
reject 'protected profile missing or not root-only'
: > /run/wpa_supplicant.conf
$BB chmod 600 /run/wpa_supplicant.conf
reject 'protected profile missing or not root-only'
install_inputs
$BB mv /run/wpa_supplicant.conf /run/profile.real
$BB ln -s /run/profile.real /run/wpa_supplicant.conf
reject 'protected profile missing or not root-only'
$BB rm /run/wpa_supplicant.conf
$BB mv /run/profile.real /run/wpa_supplicant.conf
$BB chmod 644 /run/pmos-self-post.sh
reject 'missing or unsafe post-cutover helper'
$BB chmod 700 /run/pmos-self-post.sh
$BB rm /run/pmos-self-post.sh
reject 'missing or unsafe post-cutover helper'
install_inputs
$BB chmod 644 /run/pmos-radio-bringup.sh
reject 'unpinned or unsafe script /run/pmos-radio-bringup.sh'
$BB chmod 700 /run/pmos-radio-bringup.sh
$BB printf '\n' >> /run/pmos-pid1-guard.sh
reject 'unpinned or unsafe script /run/pmos-pid1-guard.sh'
$BB rm /run/pmos-session-stage.sh
reject 'unpinned or unsafe script /run/pmos-session-stage.sh'
install_inputs

stop_listener
reject 'diagnostic :22 listener absent'
start_listener

$BB rm /sys/class/block/sda13/uevent
reject 'expected one userdata PARTNAME in sysfs, found 0'
$BB printf 'PARTNAME=vendor_boot_b\n' > /sys/class/block/sda13/uevent
reject 'expected one userdata PARTNAME in sysfs, found 0'
$BB printf 'PARTNAME=recovery_b\n' > /sys/class/block/sda13/uevent
reject 'expected one userdata PARTNAME in sysfs, found 0'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda6/uevent
reject 'expected one userdata PARTNAME in sysfs, found 2'
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda6/uevent
$BB rm /sys/class/block/sda13/dev
reject 'userdata device numbers invalid'
$BB printf 'nope\n' > /sys/class/block/sda13/dev
reject 'userdata device numbers invalid'
use_image "$GOOD"

$BB rm /dev/block/sda13
$BB mknod -m 0400 /dev/block/sda13 b 259 601
reject 'userdata block node numbers differ from sysfs'
$BB rm /dev/block/sda13
$BB mknod -m 0400 /dev/block/sda13 c "${GOOD%%:*}" "${GOOD##*:}"
reject 'userdata path is not a block node'
$BB rm /dev/block/sda13
: > /dev/block/sda13
reject 'userdata path is not a block node'
$BB rm /dev/block/sda13
mk_node /dev/block/real "$GOOD"
$BB ln -s real /dev/block/sda13
reject 'userdata block path is a symlink'
$BB rm /dev/block/sda13 /dev/block/real
use_image "$GOOD"

$BB printf '1\n' > /run/wrap.size
reject 'userdata size below image (1)'
$BB printf '33554431\n' > /run/wrap.size
reject 'userdata size below image (33554431)'
$BB rm /run/wrap.size

$BB mkdir /run/omnipha-userspace
reject 'userdata mount path already exists'
$BB rmdir /run/omnipha-userspace
: > /run/pmos-session.tar.gz
set +e
/bin/busybox sh "$STAGE" >/run/reject.out 2>&1
rc=$?
set -e
[ "$rc" != 0 ] && $BB grep -qF 'FAIL: tarball path already exists' /run/reject.out || { $BB cat /run/reject.out >&2; fail 'preexisting tarball path accepted'; }
! $BB grep -qF /run/omnipha-userspace /proc/mounts && [ ! -e /run/omnipha-userspace ] || fail 'preexisting tarball path left userdata mounted'
$BB rm -f /run/pmos-session.tar.gz
printf 'rejected: tarball path already exists\n'

use_image "$BAD_FS"
reject 'cannot mount userdata read-only without journal replay'
use_image "$BAD_BYTE"
reject 'userdata archive digest mismatch'
use_image "$BAD_LINK"
reject 'userdata archive missing, symlinked or wrong size'
use_image "$BAD_SHORT"
reject 'userdata archive missing, symlinked or wrong size'
use_image "$BAD_MODE"
reject 'userdata archive missing, symlinked or wrong size'
use_image "$BAD_MISSING"
reject 'userdata archive missing, symlinked or wrong size'

use_image "$BAD_RW"
$BB touch /run/wrap.rw
reject 'userdata mount is not read-only ext4 with noload'
$BB rm /run/wrap.rw
use_image "$GOOD"
$BB rm /dev/block/sda13
$BB touch /run/wrap.session
: > /run/wrap.dd
: > /run/wrap.mount
PROFILE_SIG=$(profile_sig)
set +e
/bin/busybox sh "$STAGE" >/run/accept.out 2>&1
rc=$?
set -e
[ "$rc" != 0 ] || fail 'stubbed session stage unexpectedly succeeded'
$BB grep -qF 'FAIL: pmos-session-stage failed' /run/accept.out || { $BB cat /run/accept.out >&2; fail 'positive path did not reach the session stage'; }
$BB grep -qF 'copied userspace archive from read-only /dev/block/sda13 (sda13) and verified SHA-256' /run/accept.out || fail 'positive archive copy not reported'
[ "$($BB sed -n 1p /run/wrap.session.out)" = "0:600:$ARCHIVE_SIZE" ] && [ "$($BB sed -n 2p /run/wrap.session.out)" = "$ARCHIVE_SHA" ] || fail 'copied archive metadata or digest'
[ -b /dev/block/sda13 ] && [ ! -L /dev/block/sda13 ] && [ "$($BB stat -c '%a' /dev/block/sda13)" = 400 ] &&
	[ "$($BB stat -c '%t:%T' /dev/block/sda13)" = "$($BB printf '%x:%x' "${GOOD%%:*}" "${GOOD##*:}")" ] || fail 'script-created node'
[ "$($BB wc -l < /run/wrap.mount)" = 1 ] && $BB grep -qxF -- 'mount -t ext4 -o ro,noload /dev/block/sda13 /run/omnipha-userspace' /run/wrap.mount || fail 'positive path did not mount userdata ro,noload'
[ ! -e /run/omnipha-userspace ] && ! $BB grep -qF /run/omnipha-userspace /proc/mounts || fail 'positive path left userdata mounted'
[ ! -s /run/wrap.dd ] || ! $BB grep -qE ' of=' /run/wrap.dd || fail 'positive path wrote a partition'
[ ! -e /run/pmos ] && [ ! -e /run/pmos-pid1-request ] && [ ! -e /run/radio-bringup ] || fail 'stubbed positive path published guest state'
[ "$(profile_sig)" = "$PROFILE_SIG" ] || fail 'positive path changed the profile before staging'
network_state /run/net.after
$BB cmp -s /run/net.base.link /run/net.after.link && $BB cmp -s /run/net.base.addr /run/net.after.addr || fail 'positive path changed links or addresses'
! $BB grep -qF fixture-only-secret /run/accept.out || fail 'positive path leaked the protected profile'

hook_line=$($BB grep -F 'setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh' "$STAGE")
[ "$hook_line" = '$BB printf '\''%s\n'\'' '\''#!/bin/busybox sh'\'' '\''( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )'\'' > "$hook"' ] || fail 'staged OpenRC hook changed'
hook=/run/hook.test
eval "$hook_line"
$BB chmod 700 "$hook"
[ "$($BB sed -n 1p /run/hook.test)" = '#!/bin/busybox sh' ] && [ "$($BB wc -l < /run/hook.test)" = 2 ] || fail 'extracted hook shape'
$BB grep -qF 'sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 &' /run/hook.test || fail 'extracted hook does not detach the post helper'
$BB mkdir -m 700 /run/radio-bringup
$BB printf '%s\n' '#!/bin/busybox sh' \
	'echo "$$ $(/bin/busybox awk "{print \$6}" /proc/$$/stat)" > /run/radio-bringup/stub.start' \
	'echo stub-output' \
	'echo stub-error >&2' \
	'/bin/busybox sleep 4' \
	': > /run/radio-bringup/stub.done' > /run/radio-bringup/pmos-self-post.sh
$BB chmod 700 /run/radio-bringup/pmos-self-post.sh
hook_t0=$($BB awk '{print int($1 * 100)}' /proc/uptime)
set +e
hook_out=$($BB timeout -k 1 2 $BB sh -c 'eval "$1"' sh "$($BB cat /run/hook.test)" 2>&1)
hook_rc=$?
set -e
hook_t1=$($BB awk '{print int($1 * 100)}' /proc/uptime)
[ "$hook_rc" = 0 ] || fail "hook did not return cleanly under timeout 2 (rc $hook_rc)"
[ "$((hook_t1 - hook_t0))" -lt 150 ] || fail 'hook waited for the post helper'
[ -z "$hook_out" ] || fail 'hook leaked post helper output'
n=0
until [ -f /run/radio-bringup/stub.start ]; do
	[ "$n" -lt 30 ] || fail 'detached post helper never started'
	$BB sleep 0.1
	n=$((n + 1))
done
read -r stub_pid stub_sid < /run/radio-bringup/stub.start
[ "$stub_pid" = "$stub_sid" ] || fail 'post helper is not its own session leader'
[ -d "/proc/$stub_pid" ] && [ ! -e /run/radio-bringup/stub.done ] || fail 'post helper did not outlive the hook return'
n=0
until [ -f /run/radio-bringup/stub.done ]; do
	[ "$n" -lt 80 ] || fail 'detached post helper did not outlive timeout 2'
	$BB sleep 0.1
	n=$((n + 1))
done
$BB rm -rf /run/radio-bringup /run/hook.test

marker_model() {
	label=$1
	want=$2
	used_in=$3
	dmesg_has=$4
	: > /run/wrap.dd
	$BB printf '%s\n' "kernel: unrelated line" "kernel: $dmesg_has" > /run/model.dmesg
	$BB printf '%s\n' '#!/run/busybox.real sh' \
		'case "${1:-}" in' \
		'	sleep) exit 0;;' \
		'	dmesg) exec /run/busybox.real cat /run/model.dmesg;;' \
		'esac' \
		'exec /run/busybox.real "$@"' > /run/bbshim
	$BB chmod 700 /run/bbshim
	out=$(
		BB=/run/bbshim
		RELEASE=/run/self-stage-capture-marker
		used=$used_in
		log() { :; }
		die() { printf 'FAIL: %s\n' "$*"; exit 1; }
		marker_source=$(/run/busybox.real sed -n '/^next_marker() {$/,/^}$/p' "$POST")
		[ "$($BB printf '%s\n' "$marker_source" | $BB wc -l)" = 20 ] || die 'marker function extraction changed'
		eval "$marker_source"
		next_marker model
		printf 'used=%s\n' "$used"
		[ ! -e "$RELEASE" ] || printf 'release-left\n'
	) && rc=0 || rc=$?
	case "$want" in
		ok:*)
			[ "$rc" = 0 ] || fail "marker model $label rejected: $out"
			[ "$out" = "used=${want#ok:}" ] || fail "marker model $label state: $out"
			;;
		*)
			[ "$rc" != 0 ] || fail "marker model $label accepted"
			[ "$out" = "FAIL: $want" ] || fail "marker model $label wrong failure: $out"
			;;
	esac
	/run/busybox.real rm -f /run/self-stage-capture-marker /run/marker.real
	printf 'model: %s\n' "$label"
}
marker_file() {
	umask 077
	$BB printf '%b' "$1" > /run/self-stage-capture-marker
	$BB chmod "${2:-600}" /run/self-stage-capture-marker
	umask 022
}
marker_file 'capture_0123\n'
marker_model 'valid marker' 'ok: capture_0123' '' 'capture_0123 seen'
marker_file 'capture_0123\n'
marker_model 'second distinct marker' 'ok: older_marker capture_0123' ' older_marker' 'capture_0123 seen'
marker_file 'capture_0123\n'
marker_model 'reused marker' 'capture marker reused for another risky stage' ' capture_0123' 'capture_0123 seen'
marker_file 'capture_0123\n'
marker_model 'marker absent from kmsg' 'released capture marker is not in this boot kmsg' '' 'other_marker_9'
marker_file 'capture_0123\n' 644
marker_model 'mode 644' 'capture marker release is not root-only' '' 'capture_0123'
marker_file 'capture_0123\n'
$BB ln /run/self-stage-capture-marker /run/marker.real
marker_model 'hard-linked marker' 'capture marker release is not root-only' '' 'capture_0123'
marker_file 'capture_0123'
marker_model 'no trailing newline' 'capture marker release is not exactly one line' '' 'capture_0123'
marker_file 'capture_0123\nsecond_line\n'
marker_model 'two lines' 'capture marker release is not exactly one line' '' 'capture_0123'
marker_file '\n'
marker_model 'empty marker' 'invalid capture marker release' '' 'capture_0123'
marker_file 'capture 0123\n'
marker_model 'space in marker' 'invalid capture marker release' '' 'capture 0123'
marker_file 'cap/ture_0123\n'
marker_model 'slash in marker' 'invalid capture marker release' '' 'cap/ture_0123'
marker_file 'short_7\n'
marker_model 'marker of 7 characters' 'capture marker length invalid' '' 'short_7'
long65=$($BB awk 'BEGIN {for (i = 0; i < 65; i++) printf "a"}')
marker_file "$long65\\n"
marker_model 'marker of 65 characters' 'capture marker length invalid' '' "$long65"
$BB ln -s /run/model.dmesg /run/self-stage-capture-marker
marker_model 'symlinked marker never accepted' 'no host-verified capture marker released for model' '' 'capture_0123'
marker_model 'absent marker times out' 'no host-verified capture marker released for model' '' 'capture_0123'
$BB rm -f /run/bbshim /run/model.dmesg

if [ -x /usr/bin/qemu-aarch64 ]; then
	$BB mkdir -p /run/qemu
	$BB mount -t tmpfs -o mode=0700,size=256m tmpfs /run/qemu || fail 'QEMU smoke root'
	$BB timeout -k 2 20 $BB tar -xzf /run/pmos-session.tar.gz -C /run/qemu ./bin/busybox ./lib/ld-musl-aarch64.so.1 ./lib/libc.musl-aarch64.so.1 || fail 'cannot extract copied archive busybox'
	[ -x /run/qemu/bin/busybox ] || fail 'copied archive missing busybox'
	[ "$(/usr/bin/qemu-aarch64 -L /run/qemu /run/qemu/bin/busybox uname -m)" = aarch64 ] || fail 'QEMU aarch64 busybox smoke'
	$BB umount /run/qemu
	qemu_note='QEMU aarch64 busybox from the copied archive ran'
else
	qemu_note='QEMU unavailable, smoke skipped'
fi
stop_listener
printf 'pass: %s\n' "$qemu_note"
