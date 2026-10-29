#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ARCHIVE=${ARCHIVE:-$HOME/sm7635-build/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
IMAGE=${IMAGE:-$HOME/sm7635-build/out/recovery_b-userspace.img}
STOCK=${STOCK:-$HOME/phone-second-life-data/mb003/parts/recovery_b.img}
BY_NAME=${BY_NAME:-$HOME/phone-second-life-data/mb003/by-name.txt}
BUILDER="$HERE/build-recovery-b-userspace-payload.py"
ARCHIVE_SHA=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
ARCHIVE_SIZE=23713302
PART_SIZE=104857600
HEADER_OFFSET=18870272
ARCHIVE_OFFSET=18874368
HEADER_SHA=2d09f260bab4b77c51f0639d034c662d01e7e13e821507278cbd571ac038b578
STOCK_SHA=6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b
SESSION_SHA=cb8fa873c7a51915a661d91d3cd70ea50d4d19b656ac5eff8e0a87b016a50b55
TRANSITION_SHA=0b85d1dc3c05b58f703618994363a9d0dbd09ecf8139573d2db15628d2497549
GUARD_SHA=dc37428ec10330c89fa8f559626be735013004b87d0bd9a7271d9b88dfc47fe3
RADIO_SHA=6b94e3d2f5feb68df1d87b821596bbf901aec2363d1a06add23c456f13cc97c0
LEASE_SHA=86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { sha256sum "$1" | cut -d ' ' -f 1; }

if [ "${1:-}" != --inner ]; then
	[ "$#" -eq 0 ] || fail 'usage: test-pmos-self-stage.sh'
	for tool in python3 sudo unshare timeout cmp stat mktemp; do
		command -v "$tool" >/dev/null 2>&1 || fail "missing tool: $tool"
	done
	for path in "$ARCHIVE" "$IMAGE" "$STOCK" "$BY_NAME" "$BUILDER" \
		"$HERE/pmos-self-stage.sh" "$HERE/pmos-self-post.sh" \
		"$HERE/pmos-session-stage.sh" "$HERE/pmos-pid1-transition.sh" \
		"$HERE/pmos-pid1-guard.sh" "$HERE/pmos-radio-bringup.sh" \
		"$HERE/wlan-udhcpc-lease.sh"; do
		[ -f "$path" ] && [ ! -L "$path" ] || fail "missing fixture input: $path"
	done
	[ "$(stat -c %s "$ARCHIVE")" = "$ARCHIVE_SIZE" ] && [ "$(hash "$ARCHIVE")" = "$ARCHIVE_SHA" ] || fail 'unpinned userspace archive'
	[ "$(stat -c %s "$STOCK")" = "$PART_SIZE" ] && [ "$(hash "$STOCK")" = "$STOCK_SHA" ] || fail 'unpinned stock recovery_b'
	[ "$(stat -c %s "$IMAGE")" = "$PART_SIZE" ] || fail 'built recovery_b size'
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
	python3 -B "$BUILDER" --self-test "$STOCK" "$ARCHIVE" "$IMAGE" >"$WORK/builder.out" ||
		{ cat "$WORK/builder.out" >&2; fail 'recovery_b builder self-test'; }
	[ "$(awk '$(NF-2) == "recovery_b" && $(NF-1) == "->" {n++; print $NF} END {if (n != 1) exit 1}' "$BY_NAME")" = /dev/block/sde53 ] ||
		fail 'measured by-name table does not place recovery_b on sde53'
	before=$(hash "$IMAGE")
	python3 -B - "$IMAGE" "$ARCHIVE" "$WORK" "$HEADER_OFFSET" "$ARCHIVE_OFFSET" "$HEADER_SHA" "$ARCHIVE_SHA" "$ARCHIVE_SIZE" <<'PY' || fail 'image windows or fixture build'
import hashlib, pathlib, shutil, sys
image, archive, work, header_off, archive_off, header_sha, archive_sha, archive_size = sys.argv[1:]
header_off, archive_off, archive_size = map(int, (header_off, archive_off, archive_size))
work = pathlib.Path(work)
data = pathlib.Path(image).read_bytes()
header = data[header_off:header_off + 4096]
body = header.rstrip(b"\x00")
assert hashlib.sha256(header).hexdigest() == header_sha
assert body.startswith(b"OMNIPHA_VENDOR_BOOT_B_USERSPACE_V1\n") and b"psk=" not in body and b"ssid=" not in body
payload = data[archive_off:archive_off + archive_size]
assert payload == pathlib.Path(archive).read_bytes() and hashlib.sha256(payload).hexdigest() == archive_sha
with open(work / "bad-header.img", "wb") as handle:
    handle.truncate(len(data))
    handle.seek(header_off)
    handle.write(bytes([header[0] ^ 1]) + header[1:])
for name, index in (("bad-archive-first.img", archive_off), ("bad-archive-last.img", archive_off + archive_size - 1)):
    target = work / name
    shutil.copyfile(image, target)
    with open(target, "r+b") as handle:
        handle.seek(index)
        handle.write(bytes([data[index] ^ 1]))
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
	bad_header=$(attach "$WORK/bad-header.img")
	bad_first=$(attach "$WORK/bad-archive-first.img")
	bad_last=$(attach "$WORK/bad-archive-last.img")
	sudo -n timeout -k 2 40 unshare --mount --pid --net --fork --kill-child --mount-proc \
		env HOST_ARCHIVE="$ARCHIVE" SOURCE="$HERE" GOOD="$good" BAD_HEADER="$bad_header" \
		BAD_FIRST="$bad_first" BAD_LAST="$bad_last" \
		/bin/busybox sh "$0" --inner || fail 'isolated self-stage fixture'
	[ "$(hash "$IMAGE")" = "$before" ] || fail 'built recovery_b image changed'
	[ "$(hash "$ARCHIVE")" = "$ARCHIVE_SHA" ] || fail 'archive changed'
	python3 -B "$BUILDER" --verify "$STOCK" "$ARCHIVE" "$IMAGE" >/dev/null || fail 'built image no longer verifies'
	printf 'pass: host-only recovery_b self-stage fixture; builder self-test, read-only loop partition, by-name/PARTNAME, node, size, header and archive negatives rejected before staging; positive copy verified; no partition write\n'
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
	sysfs_part sde51 recovery_b "$1"
	mk_node /dev/block/sde51 "$1"
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
	[ ! -e /run/radio-bringup ] && [ ! -e /run/recovery_b.header ] || fail "$1 published radio or header state"
	[ "$(profile_sig)" = "$PROFILE_SIG" ] || fail "$1 moved or changed the protected profile"
	network_state /run/net.after
	$BB cmp -s /run/net.base.link /run/net.after.link &&
		$BB cmp -s /run/net.base.addr /run/net.after.addr || fail "$1 changed links or addresses"
	[ ! -e /run/pmos-self-scan.raw ] && [ ! -e /run/radio-bringup/scan.raw ] || fail "$1 published a scan"
	[ ! -f /run/reject.out ] || ! $BB grep -qF fixture-only-secret /run/reject.out || fail "$1 leaked the protected profile"
	[ ! -s /run/wrap.dd ] || ! $BB grep -qE ' of=/dev/| of=/sys/' /run/wrap.dd || fail "$1 wrote a device or sysfs path"
}
reject() {
	label=$1
	copy=${2:-no}
	: > /run/wrap.dd
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
	if [ "$copy" = no ]; then
		! $BB grep -qF "skip=$((ARCHIVE_OFFSET / 4096))" /run/wrap.dd || fail "$label read the archive before rejecting"
	else
		$BB grep -qF "skip=$((ARCHIVE_OFFSET / 4096))" /run/wrap.dd || fail "$label never reached the archive window"
	fi
	printf 'rejected: %s\n' "$label"
}

PART_SIZE=104857600
HEADER_OFFSET=18870272
ARCHIVE_OFFSET=18874368
ARCHIVE_SIZE=23713302
ARCHIVE_SHA=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
HEADER_SHA=2d09f260bab4b77c51f0639d034c662d01e7e13e821507278cbd571ac038b578

ip link set lo up
ip addr add 172.16.42.2/32 dev lo
start_listener
install_inputs
sysfs_part sda6 super 259:600
$BB ln -s /dev/block/sda6 /dev/block/by-name/recovery_b
use_image "$GOOD"
network_state /run/net.base
$BB sh -n "$STAGE" && $BB sh -n "$POST" || fail 'self-stage or post script syntax'
[ "$($BB sed -n 's/^PARTNAME=//p' /sys/class/block/sde51/uevent)" = recovery_b ] || fail 'sde51 PARTNAME model'
[ "$($BB cat /sys/class/block/sde51/dev)" = "$GOOD" ] && [ "$($BB stat -c '%t:%T' /dev/block/sde51)" = "$($BB printf '%x:%x' "${GOOD%%:*}" "${GOOD##*:}")" ] || fail 'sde51 numbers model'
[ "$($BB blockdev --getsize64 /dev/block/sde51)" = "$PART_SIZE" ] && [ "$($BB blockdev --getro /dev/block/sde51)" = 1 ] || fail 'sde51 size or read-only model'
$BB dd if=/dev/block/sde51 of=/run/model.header bs=4096 skip=$((HEADER_OFFSET / 4096)) count=1 2>/dev/null
[ "$(hash /run/model.header)" = "$HEADER_SHA" ] || fail 'model header digest'
$BB dd if=/dev/block/sde51 of=/run/model.archive bs=4096 skip=$((ARCHIVE_OFFSET / 4096)) count=$((ARCHIVE_SIZE / 4096)) 2>/dev/null
$BB dd if=/dev/block/sde51 bs=4096 skip=$((ARCHIVE_OFFSET / 4096 + ARCHIVE_SIZE / 4096)) count=1 2>/dev/null |
	$BB dd of=/run/model.archive bs=1 seek=$((ARCHIVE_SIZE / 4096 * 4096)) count=$((ARCHIVE_SIZE % 4096)) conv=notrunc 2>/dev/null
[ "$(hash /run/model.archive)" = "$ARCHIVE_SHA" ] || fail 'model archive digest'
$BB rm -f /run/model.header /run/model.archive
$BB dd if=/dev/zero of=/dev/block/sde51 bs=512 count=1 2>/dev/null && fail 'read-only partition model accepted a write'

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

$BB rm /sys/class/block/sde51/uevent
reject 'expected one recovery_b PARTNAME in sysfs, found 0'
$BB printf 'PARTNAME=vendor_boot_b\n' > /sys/class/block/sde51/uevent
reject 'expected one recovery_b PARTNAME in sysfs, found 0'
$BB printf 'PARTNAME=recovery_a\n' > /sys/class/block/sde51/uevent
reject 'expected one recovery_b PARTNAME in sysfs, found 0'
$BB printf 'PARTNAME=recovery_b\n' > /sys/class/block/sde51/uevent
$BB printf 'PARTNAME=recovery_b\n' > /sys/class/block/sda6/uevent
reject 'expected one recovery_b PARTNAME in sysfs, found 2'
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda6/uevent
$BB rm /sys/class/block/sde51/dev
reject 'recovery_b device numbers invalid'
$BB printf 'nope\n' > /sys/class/block/sde51/dev
reject 'recovery_b device numbers invalid'
use_image "$GOOD"

$BB rm /dev/block/sde51
$BB mknod -m 0400 /dev/block/sde51 b 259 601
reject 'recovery_b block node numbers differ from sysfs'
$BB rm /dev/block/sde51
$BB mknod -m 0400 /dev/block/sde51 c "${GOOD%%:*}" "${GOOD##*:}"
reject 'recovery_b path is not a block node'
$BB rm /dev/block/sde51
: > /dev/block/sde51
reject 'recovery_b path is not a block node'
$BB rm /dev/block/sde51
mk_node /dev/block/real "$GOOD"
$BB ln -s real /dev/block/sde51
reject 'recovery_b block path is a symlink'
$BB rm /dev/block/sde51 /dev/block/real
use_image "$GOOD"

$BB printf '1\n' > /run/wrap.size
reject 'recovery_b size mismatch (1)'
$BB printf '100663296\n' > /run/wrap.size
reject 'recovery_b size mismatch (100663296)'
$BB printf '104857599\n' > /run/wrap.size
reject 'recovery_b size mismatch (104857599)'
$BB printf '104857601\n' > /run/wrap.size
reject 'recovery_b size mismatch (104857601)'
$BB rm /run/wrap.size

use_image "$BAD_HEADER"
reject 'recovery_b payload header digest mismatch'
use_image "$BAD_FIRST"
reject 'recovery_b archive digest or size mismatch' yes
use_image "$BAD_LAST"
reject 'recovery_b archive digest or size mismatch' yes

use_image "$GOOD"
$BB rm /dev/block/sde51
$BB touch /run/wrap.session
: > /run/wrap.dd
PROFILE_SIG=$(profile_sig)
set +e
/bin/busybox sh "$STAGE" >/run/accept.out 2>&1
rc=$?
set -e
[ "$rc" != 0 ] || fail 'stubbed session stage unexpectedly succeeded'
$BB grep -qF 'FAIL: pmos-session-stage failed' /run/accept.out || { $BB cat /run/accept.out >&2; fail 'positive path did not reach the session stage'; }
$BB grep -qF 'copied userspace archive from read-only /dev/block/sde51 (sde51) and verified SHA-256' /run/accept.out || fail 'positive archive copy not reported'
[ "$($BB sed -n 1p /run/wrap.session.out)" = "0:600:$ARCHIVE_SIZE" ] && [ "$($BB sed -n 2p /run/wrap.session.out)" = "$ARCHIVE_SHA" ] || fail 'copied archive metadata or digest'
[ -b /dev/block/sde51 ] && [ ! -L /dev/block/sde51 ] && [ "$($BB stat -c '%a' /dev/block/sde51)" = 400 ] &&
	[ "$($BB stat -c '%t:%T' /dev/block/sde51)" = "$($BB printf '%x:%x' "${GOOD%%:*}" "${GOOD##*:}")" ] || fail 'script-created node'
[ ! -e /run/recovery_b.header ] || fail 'header scratch retained'
$BB grep -qF 'if=/dev/block/sde51' /run/wrap.dd || fail 'positive path did not read the by-sysfs node'
! $BB grep -qE ' of=/dev/| of=/sys/| of=/dev/block' /run/wrap.dd || fail 'positive path wrote a partition'
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
