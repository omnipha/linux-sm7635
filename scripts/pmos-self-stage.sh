#!/bin/busybox sh
set -eu

BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
LOG=/run/pmos-self-stage.log
TARBALL=/run/pmos-session.tar.gz
ARCHIVE_SHA=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
ARCHIVE_SIZE=23713302
PART_SIZE=100663296
HEADER_OFFSET=18870272
ARCHIVE_OFFSET=18874368
HEADER_SHA=2d09f260bab4b77c51f0639d034c662d01e7e13e821507278cbd571ac038b578
STAGE_SHA=cb8fa873c7a51915a661d91d3cd70ea50d4d19b656ac5eff8e0a87b016a50b55
TRANSITION_SHA=0b85d1dc3c05b58f703618994363a9d0dbd09ecf8139573d2db15628d2497549
GUARD_SHA=dc37428ec10330c89fa8f559626be735013004b87d0bd9a7271d9b88dfc47fe3
RADIO_SHA=6b94e3d2f5feb68df1d87b821596bbf901aec2363d1a06add23c456f13cc97c0
LEASE_SHA=86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896
umask 077

log() {
	$BB printf 'pmos-self-stage: %s\n' "$*" | $BB tee -a "$LOG" >&2
	$BB printf 'pmos-self-stage: %s\n' "$*" >/dev/kmsg 2>/dev/null || true
}
die() { log "FAIL: $*"; exit 1; }
hash() { $BB sha256sum "$1" 2>/dev/null | $BB cut -d ' ' -f 1; }

PIN_KEY=/etc/dropbear/dropbear_ed25519_host_key
PIN_PUB=AAAAC3NzaC1lZDI1NTE5AAAAIA2ioqI4txcs3PSJWvcgSd/qBuDuCC50OIvIpKsjrjql
GUEST=/run/pmos

pin_session_hostkey() {
	[ -f "$PIN_KEY" ] && [ ! -L "$PIN_KEY" ] &&
		[ "$($BB stat -c '%u:%a' "$PIN_KEY")" = 0:600 ] || die 'pinned host key missing or not root-only'
	[ -f "$GUEST/run/dropbear-session.pid" ] && [ ! -L "$GUEST/run/dropbear-session.pid" ] || die 'guest :2222 pidfile absent'
	old=$($BB cat "$GUEST/run/dropbear-session.pid")
	case "$old" in ''|*[!0-9]*) die 'guest :2222 pid invalid';; esac
	[ "$($BB readlink "/proc/$old/root" 2>/dev/null)" = "$GUEST" ] || die 'guest :2222 process is not in the guest root'
	$BB kill "$old" || die 'cannot stop the ephemeral-key :2222 service'
	n=0
	while [ -d "/proc/$old" ]; do
		[ "$n" -lt 20 ] || die 'ephemeral-key :2222 service did not stop'
		$BB sleep 0.5
		n=$((n + 1))
	done
	$BB rm -f "$GUEST/run/dropbear-session.pid"
	[ ! -L "$GUEST/etc/dropbear/session_host_key" ] && [ ! -L "$GUEST/etc/dropbear/session_host_key.new" ] || die 'guest host key path is a symlink'
	$BB cp "$PIN_KEY" "$GUEST/etc/dropbear/session_host_key.new" || die 'cannot stage the pinned host key'
	$BB chmod 600 "$GUEST/etc/dropbear/session_host_key.new"
	$BB mv -f "$GUEST/etc/dropbear/session_host_key.new" "$GUEST/etc/dropbear/session_host_key" || die 'cannot install the pinned host key'
	got=$($BB chroot "$GUEST" /usr/bin/dropbearkey -y -f /etc/dropbear/session_host_key 2>/dev/null | $BB awk '/^ssh-ed25519 / {print $2}') || got=
	[ "$got" = "$PIN_PUB" ] || die 'guest host key differs from the pinned public key'
	$BB chroot "$GUEST" /usr/bin/dropbearkey -y -f /etc/dropbear/session_host_key > "$GUEST/run/second-hostkey.pub" 2>/dev/null || die 'cannot refresh the guest public key'
	$BB chmod 600 "$GUEST/run/second-hostkey.pub"
	$BB chroot "$GUEST" /bin/sh -c 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid' >>"$LOG" 2>&1 || die 'pinned-key :2222 did not start'
	$BB sleep 1
	[ -f "$GUEST/run/dropbear-session.pid" ] && [ ! -L "$GUEST/run/dropbear-session.pid" ] || die 'pinned-key :2222 pidfile missing'
	new=$($BB cat "$GUEST/run/dropbear-session.pid")
	case "$new" in ''|*[!0-9]*) die 'pinned-key :2222 pid invalid';; esac
	[ "$new" != "$old" ] && [ "$($BB readlink "/proc/$new/root" 2>/dev/null)" = "$GUEST" ] &&
		$BB tr '\000' ' ' < "/proc/$new/cmdline" | $BB grep -q 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' &&
		$BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {guest++} $2 == "022A10AC:0016" && $4 == "0A" {diagnostic++} END {exit(guest != 1 || diagnostic != 1)}' /proc/net/tcp ||
		die 'pinned-key :2222 or diagnostic :22 unhealthy'
	$BB printf 'pmos-self-stage: guest :2222 host key ssh-ed25519 %s\n' "$PIN_PUB" >/dev/kmsg 2>/dev/null || true
	log 'guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request'
}

[ "$($BB id -u)" = 0 ] || die 'root required'
$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox ||
	$BB grep -qa busybox /proc/1/cmdline || die 'PID 1 is not the diagnostic init'
boot=$($BB cat /proc/sys/kernel/random/boot_id 2>/dev/null) || boot=
case "$boot" in
	????????-????-????-????-????????????)
		case "$boot" in *[!0-9a-f-]*) die 'invalid boot ID';; esac;;
	*) die 'invalid boot ID';;
esac

for spec in \
	"/run/pmos-session-stage.sh $STAGE_SHA" \
	"/run/pmos-pid1-transition.sh $TRANSITION_SHA" \
	"/run/pmos-pid1-guard.sh $GUARD_SHA" \
	"/run/pmos-radio-bringup.sh $RADIO_SHA" \
	"/run/wlan-udhcpc-lease.sh $LEASE_SHA"
do
	set -- $spec
	[ -f "$1" ] && [ ! -L "$1" ] &&
		[ "$($BB stat -c '%u:%a' "$1")" = 0:700 ] &&
		[ "$(hash "$1")" = "$2" ] || die "unpinned or unsafe script $1"
done
[ -f /run/pmos-self-post.sh ] && [ ! -L /run/pmos-self-post.sh ] &&
	[ "$($BB stat -c '%u:%a' /run/pmos-self-post.sh)" = 0:700 ] ||
	die 'missing or unsafe post-cutover helper'
[ -f /run/wpa_supplicant.conf ] && [ ! -L /run/wpa_supplicant.conf ] &&
	[ -s /run/wpa_supplicant.conf ] &&
	[ "$($BB stat -c '%u:%a' /run/wpa_supplicant.conf)" = 0:600 ] ||
	die 'protected profile missing or not root-only'

wait_n=0
while [ ! -f /run/keep ] || [ -L /run/keep ]; do
	up=$($BB awk '{print int($1)}' /proc/uptime 2>/dev/null) || up=
	case "$up" in ''|*[!0-9]*) die 'no monotonic clock';; esac
	[ "$wait_n" -lt 145 ] && [ "$up" -lt 145 ] || die 'diagnostic hold not set before self-recovery deadline'
	$BB sleep 1
	wait_n=$((wait_n + 1))
done
$BB awk '$2 == "022A10AC:0016" && $4 == "0A" {n++} END {exit(n != 1)}' /proc/net/tcp ||
	die 'diagnostic :22 listener absent'
if [ ! -f /run/keep ] || [ -L /run/keep ]; then
	die 'diagnostic hold absent'
fi
log "diagnostic hold and :22 verified on boot $boot"

part_dev=
part_count=0
for uevent in /sys/class/block/*/uevent; do
	[ -r "$uevent" ] || continue
	if [ "$($BB sed -n 's/^PARTNAME=//p' "$uevent" 2>/dev/null)" = vendor_boot_b ]; then
		dir=${uevent%/uevent}
		part_dev=${dir##*/}
		part_count=$((part_count + 1))
	fi
done
[ "$part_count" = 1 ] && [ -n "$part_dev" ] ||
	die "expected one vendor_boot_b PARTNAME in sysfs, found $part_count"
devnum=$($BB cat "/sys/class/block/$part_dev/dev" 2>/dev/null) || devnum=
case "$devnum" in [0-9]*:[0-9]*) :;; *) die 'vendor_boot_b device numbers invalid';; esac
major=${devnum%%:*}
minor=${devnum##*:}
$BB mkdir -p /dev/block
node="/dev/block/$part_dev"
if [ -b "$node" ]; then
	[ ! -L "$node" ] || die 'vendor_boot_b block path is a symlink'
	[ "$($BB stat -c '%t:%T' "$node")" = "$($BB printf '%x:%x' "$major" "$minor")" ] ||
		die 'vendor_boot_b block node numbers differ from sysfs'
else
	[ ! -e "$node" ] && [ ! -L "$node" ] || die 'vendor_boot_b path is not a block node'
	$BB mknod -m 0400 "$node" b "$major" "$minor" || die 'cannot create vendor_boot_b block node'
fi
[ "$($BB stat -c '%t:%T' "$node")" = "$($BB printf '%x:%x' "$major" "$minor")" ] ||
	die 'vendor_boot_b node verification failed'
size=$($BB timeout -k 1 2 $BB blockdev --getsize64 "$node" 2>/dev/null) || size=
[ "$size" = "$PART_SIZE" ] || die "vendor_boot_b size mismatch (${size:-unknown})"

hdr=/run/vendor_boot_b.header
$BB rm -f "$hdr"
$BB timeout -k 1 5 $BB dd if="$node" of="$hdr" bs=4096 skip=$((HEADER_OFFSET / 4096)) count=1 2>/dev/null ||
	{ $BB rm -f "$hdr"; die 'cannot read vendor_boot_b payload header'; }
[ "$(hash "$hdr")" = "$HEADER_SHA" ] ||
	{ $BB rm -f "$hdr"; die 'vendor_boot_b payload header digest mismatch'; }
$BB rm -f "$hdr"

[ ! -e "$TARBALL" ] && [ ! -L "$TARBALL" ] || die 'tarball path already exists'
full_blocks=$((ARCHIVE_SIZE / 4096))
rem_bytes=$((ARCHIVE_SIZE % 4096))
skip_blocks=$((ARCHIVE_OFFSET / 4096))
$BB timeout -k 2 30 $BB dd if="$node" of="$TARBALL" bs=4096 skip="$skip_blocks" count="$full_blocks" 2>/dev/null ||
	{ $BB rm -f "$TARBALL"; die 'vendor_boot_b archive block copy failed'; }
if [ "$rem_bytes" -gt 0 ]; then
	page=/run/vendor_boot_b.page
	$BB rm -f "$page"
	$BB timeout -k 1 5 $BB dd if="$node" of="$page" bs=4096 skip=$((skip_blocks + full_blocks)) count=1 2>/dev/null ||
		{ $BB rm -f "$TARBALL" "$page"; die 'vendor_boot_b archive tail copy failed'; }
	$BB dd if="$page" of="$TARBALL" bs=1 seek="$((full_blocks * 4096))" count="$rem_bytes" conv=notrunc 2>/dev/null ||
		{ $BB rm -f "$TARBALL" "$page"; die 'vendor_boot_b archive tail copy failed'; }
	$BB rm -f "$page"
fi
$BB chmod 600 "$TARBALL"
[ "$($BB stat -c '%u:%a:%s' "$TARBALL")" = "0:600:$ARCHIVE_SIZE" ] &&
	[ "$(hash "$TARBALL")" = "$ARCHIVE_SHA" ] ||
	{ $BB rm -f "$TARBALL"; die 'vendor_boot_b archive digest or size mismatch'; }
log "copied userspace archive from read-only $node ($part_dev) and verified SHA-256"

$BB sh /run/pmos-session-stage.sh || die 'pmos-session-stage failed'
pin_session_hostkey
$BB rm -f "$TARBALL"
$BB sh /run/pmos-radio-bringup.sh "$boot" prepare || die 'pmos-radio-bringup prepare failed'

post_sha=$(hash /run/pmos-self-post.sh)
$BB cp /run/pmos-radio-bringup.sh /run/pmos/run/radio-bringup/pmos-radio-bringup.sh
$BB chmod 700 /run/pmos/run/radio-bringup/pmos-radio-bringup.sh
[ "$(hash /run/pmos/run/radio-bringup/pmos-radio-bringup.sh)" = "$RADIO_SHA" ] ||
	die 'guest radio script digest mismatch'
$BB cp /run/pmos-self-post.sh /run/pmos/run/radio-bringup/pmos-self-post.sh
$BB chmod 700 /run/pmos/run/radio-bringup/pmos-self-post.sh
[ "$(hash /run/pmos/run/radio-bringup/pmos-self-post.sh)" = "$post_sha" ] ||
	die 'guest post-cutover helper digest mismatch'
$BB mv /run/wpa_supplicant.conf /run/pmos/run/radio-bringup/wpa_supplicant.conf
$BB chmod 600 /run/pmos/run/radio-bringup/wpa_supplicant.conf
[ -f /run/pmos/run/radio-bringup/wpa_supplicant.conf ] &&
	[ ! -L /run/pmos/run/radio-bringup/wpa_supplicant.conf ] &&
	[ "$($BB stat -c '%u:%a' /run/pmos/run/radio-bringup/wpa_supplicant.conf)" = 0:600 ] ||
	die 'guest protected profile invalid'

hook=/run/pmos/etc/local.d/10-omnipha-self-stage.start
[ ! -e "$hook" ] && [ ! -L "$hook" ] || die 'local.d startup hook already exists'
$BB printf '%s\n' '#!/bin/busybox sh' '( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )' > "$hook"
$BB chmod 700 "$hook"
[ "$($BB stat -c '%u:%a' "$hook")" = 0:700 ] || die 'local.d startup hook mode invalid'

[ ! -e /run/pmos-pid1-request ] && [ ! -L /run/pmos-pid1-request ] || die 'PID 1 request already exists'
$BB printf '%s\n' "$boot" > /run/.pmos-pid1-request.tmp
$BB chmod 600 /run/.pmos-pid1-request.tmp
$BB mv /run/.pmos-pid1-request.tmp /run/pmos-pid1-request
[ "$($BB stat -c '%u:%a:%h:%s' /run/pmos-pid1-request)" = 0:600:1:37 ] ||
	{ $BB rm -f /run/pmos-pid1-request; die 'PID 1 request metadata invalid'; }
log "staged postmarketOS root and armed PID 1 request for boot $boot"
