#!/bin/sh
# Host fixture for the bounded pre-switch_root boot record on a loop-backed
# ext4 userdata root. Proves: (a) a complete record survives an interrupted
# transition and reads back after remount; (b) a failure at a named stage
# leaves that line and no later line; (c) a symlink, wrong root or over-bound
# record refuses the append/verify and the transition. No device involved.
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
CONTRACT="$HERE/pmos-root-contract.sh"

if [ "${1:-}" != --inner ]; then
	[ "$#" -eq 0 ] || { printf 'usage: test-pmos-boot-record.sh\n' >&2; exit 1; }
	[ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] || { printf 'FAIL: missing contract\n' >&2; exit 1; }
	STAGE="$HERE/pmos-session-stage.sh"
	[ -f "$STAGE" ] && [ ! -L "$STAGE" ] || { printf 'FAIL: missing session stage\n' >&2; exit 1; }
	STAGED=$(mktemp "${TMPDIR:-/tmp}/pmos-boot-record-stage.XXXXXXXX")
	python3 -B - "$HERE/build-init-boot-persistent-root.py" "$STAGE" "$STAGED" <<'PY'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('builder', sys.argv[1])
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
pathlib.Path(sys.argv[3]).write_bytes(builder.current_scripts()['pmos-session-stage.sh'])
PY
	sudo -n true || { printf 'FAIL: passwordless sudo required\n' >&2; exit 1; }
	WORK=$(mktemp -d "${TMPDIR:-/tmp}/pmos-boot-record.XXXXXXXX")
	: > "$WORK/loops"
	cleanup() {
		while read -r dev; do sudo -n /sbin/losetup -d "$dev" >/dev/null 2>&1 || true; done < "$WORK/loops"
		rm -rf -- "$WORK"
		rm -f -- "$STAGED"
	}
	trap cleanup EXIT
	truncate -s 268435456 "$WORK/userdata.img"
	/sbin/mke2fs -q -F -t ext4 -b 4096 "$WORK/userdata.img"
	dev=$(sudo -n /sbin/losetup -f --show "$WORK/userdata.img")
	printf '%s\n' "$dev" >> "$WORK/loops"
	nums="$((0x$(stat -c %t "$dev"))):$((0x$(stat -c %T "$dev")))"
	sudo -n timeout -k 2 120 unshare --mount --pid --fork --kill-child --mount-proc \
		env SOURCE="$CONTRACT" STAGED="$STAGED" MAIN_NUMS="$nums" /bin/busybox sh "$0" --inner
	printf 'pass: boot record fixtures; complete record with the post-cutover line survives interrupted transition and remount readback; failure at named stage keeps prefix only; refusal path keeps the reached lines plus bounded FAIL lines and no success line; symlink/wrong-root/over-bound/foreign-boot refusals; valid foreign record rotates and the new boot opens; rotation refusals leave the prior record; no device\n'
	exit 0
fi

BB=/bin/busybox
export BB
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

$BB mount --make-rprivate / || fail 'private mount namespace'
$BB mount -t tmpfs -o mode=0755,size=16m tmpfs /run || fail 'run tmpfs'
$BB mount -t tmpfs -o mode=0755,size=1m tmpfs /dev || fail 'dev tmpfs'
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 666 /dev/zero c 1 5
$BB mknod -m 666 /dev/urandom c 1 9
$BB mkdir -p /dev/block /sys/class/block
$BB mount -t tmpfs -o mode=0755,size=1m tmpfs /sys/class/block || fail 'sysfs block model'
$BB mkdir -p /sys/class/block/sda13
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
$BB printf '%s\n' "$MAIN_NUMS" > /sys/class/block/sda13/dev
$BB mknod -m 0400 /dev/block/sda13 b "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}"
. "$SOURCE"
umask 077

boot=$($BB cat /proc/sys/kernel/random/boot_id)
[ -n "$boot" ] || fail 'no boot ID'
R=/run/pmos
mount_root() {
	$BB mkdir -m 700 "$R"
	$BB mount -t ext4 -o ro,noload /dev/block/sda13 "$R" || fail 'cannot mount fixture ext4 root'
	root_contract_pinned_userdata "$R" || fail 'fixture root not pinned'
	root_contract_promote "$R" || fail 'fixture root not promoted'
	root_contract_pinned_userdata "$R" || fail 'fixture root lost pin after promote'
	$BB find "$R" -mindepth 1 -maxdepth 1 ! -name lost+found -exec $BB rm -rf {} +
}
mount_root

# (a) complete record on the persistent root survives an abrupt teardown
# (interrupted transition model: no umount, no sync beyond the helpers).
boot_record_open "$R" || fail 'record open refused'
boot_record_append "$R" "pmos-self-stage: diagnostic hold and :22 verified on boot $boot" || fail 'append 1 refused'
boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root' || fail 'append 2 refused'
boot_record_append "$R" 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' || fail 'append 3 refused'
boot_record_append "$R" 'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)' || fail 'append 4 refused'
boot_record_append "$R" 'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)' || fail 'append 5 refused'
boot_record_append "$R" "pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract" || fail 'append 6 refused'
boot_record_append "$R" 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request' || fail 'append 7 refused'
boot_record_append "$R" 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' || fail 'append 8 refused'
boot_record_append "$R" "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot" || fail 'append 9 refused'
boot_record_append "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'append 10 refused'
boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'transition record verify refused'
boot_record_append "$R" "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" || fail 'append 11 refused'
boot_record_verify "$R" "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" || fail 'post-cutover record verify refused'
# Interrupted transition: drop the mount without unmount (lazy model) and remount read-only.
$BB umount -l "$R" || fail 'lazy detach'
$BB mount -t ext4 -o ro,noload /dev/block/sda13 "$R" || fail 'remount after interruption'
expected="boot $boot
pmos-self-stage: diagnostic hold and :22 verified on boot $boot
pmos-stage: using unpacked persistent postmarketOS root
pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts
pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)
pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)
pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract
pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request
radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover
pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot
usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init
pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"
[ "$($BB cat "$R/.omnipha-boot-record")" = "$expected" ] || fail 'complete record did not survive interruption'
size=$($BB stat -c %s "$R/.omnipha-boot-record")
[ "$size" -le "$boot_record_bound" ] || fail 'record over bound'
$BB printf 'a: complete record including the post-cutover line survived interruption and remount (%s bytes)\n' "$size"
$BB umount "$R" || fail 'unmount after (a)'
$BB rmdir "$R"

# (b) failure at a named stage leaves that line and no later line
mount_root
boot_record_open "$R" || fail 'record (b) open refused'
boot_record_append "$R" "pmos-self-stage: diagnostic hold and :22 verified on boot $boot" || fail 'record (b) append 1 refused'
boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root' || fail 'record (b) append 2 refused'
boot_record_append "$R" 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' || fail 'record (b) append 3 refused'
$BB umount -l "$R" || fail 'lazy detach (b)'
$BB mount -t ext4 -o ro,noload /dev/block/sda13 "$R" || fail 'remount (b)'
partial="boot $boot
pmos-self-stage: diagnostic hold and :22 verified on boot $boot
pmos-stage: using unpacked persistent postmarketOS root
pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts"
[ "$($BB cat "$R/.omnipha-boot-record")" = "$partial" ] || fail 'failure did not leave exactly the reached prefix'
root_contract_pinned_userdata "$R" || fail 'fixture root (b) not pinned'
if boot_record_append "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'; then
	fail 'transition appended its line after a mid-sequence failure'
fi
[ "$($BB cat "$R/.omnipha-boot-record")" = "$partial" ] || fail 'refused append changed the record'
$BB printf 'b: failure left the named stage prefix and no later line\n'
$BB umount "$R" || fail 'unmount after (b)'
$BB rmdir "$R"

# (c) symlink, wrong root and over-bound refusals
mount_root
$BB ln -s /run/keep "$R/.omnipha-boot-record"
if boot_record_open "$R"; then fail 'symlinked record accepted'; fi
$BB rm "$R/.omnipha-boot-record"
$BB printf 'stale\n' > "$R/.omnipha-boot-record"
$BB chmod 600 "$R/.omnipha-boot-record"
if boot_record_open "$R"; then fail 'pre-existing record accepted'; fi
$BB rm "$R/.omnipha-boot-record"
boot_record_open "$R" || fail 'record (c) open refused'
$BB printf '%s\n' "$($BB head -c 4400 /dev/zero | $BB tr '\0' 'x')" > "$R/.omnipha-boot-record"
$BB chmod 600 "$R/.omnipha-boot-record"
[ "$($BB stat -c %s "$R/.omnipha-boot-record")" -gt "$boot_record_bound" ] || fail 'over-bound fixture not over bound'
if boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root'; then
	fail 'over-bound record accepted an append'
fi
if boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'; then
	fail 'over-bound record verified'
fi
$BB rm "$R/.omnipha-boot-record"
boot_record_open "$R" || fail 'record (c) reopen refused'
$BB printf 'PARTNAME=other\n' > /sys/class/block/sda13/uevent
if boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root'; then
	fail 'wrong-root append accepted'
fi
if boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'; then
	fail 'wrong-root verify accepted'
fi
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
$BB printf 'c: symlink, pre-existing, over-bound and wrong-root cases all refused\n'
$BB umount "$R" || fail 'unmount after (c)'
$BB rmdir "$R"

mount_root
PMOS_ROOT="$R"
PMOS_ROOT_KIND=ext4
{
	$BB printf 'if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then\n'
	$BB awk '/^[[:space:]]+boot_record_open "\$PMOS_ROOT"/{on=1} on{print; if ($0 ~ /hold append refused/) exit}' "$STAGED"
	$BB printf 'fi\n'
} > /run/injected-open
$BB grep -q 'boot_record_open' /run/injected-open || fail 'injected open block missing'
$BB grep -q 'boot record hold append refused' /run/injected-open || fail 'injected hold append missing'
. /run/injected-open || fail 'injected open/hold block refused'
hold="boot $boot
pmos-self-stage: diagnostic hold and :22 verified on boot $boot"
[ "$($BB cat "$R/.omnipha-boot-record")" = "$hold" ] || fail 'injected open did not write boot and hold first'
boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root' || fail 'injected sequence append refused'
boot_record_append "$R" 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' || fail 'injected sequence dev append refused'
boot_record_append "$R" 'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)' || fail 'injected sequence ssh append refused'
boot_record_append "$R" 'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)' || fail 'injected sequence staged append refused'
boot_record_append "$R" "pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract" || fail 'injected sequence mount append refused'
boot_record_append "$R" 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request' || fail 'injected sequence key append refused'
boot_record_append "$R" 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' || fail 'injected sequence radio append refused'
boot_record_append "$R" "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot" || fail 'injected sequence request append refused'
boot_record_append "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'injected sequence transition append refused'
boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'injected transition record verify refused'
boot_record_append "$R" "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" || fail 'injected sequence post-cutover append refused'
boot_record_verify "$R" "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" || fail 'injected post-cutover record verify refused'
[ "$($BB cat "$R/.omnipha-boot-record")" = "$expected" ] || fail 'injected full record content differs'
$BB printf 'd: injected session-stage open/hold wrote the prefix; full ordered record verified\n'
$BB umount "$R" || fail 'unmount after injected case'
$BB rmdir "$R"

# (e) post-cutover refusal path: one FAIL line with the uptime stamp, no
# success line, no later line; a second FAIL is allowed, a third is refused;
# a record copied from a previous boot (foreign boot ID) is refused.
mount_root
boot_record_open "$R" || fail 'record (e) open refused'
boot_record_append "$R" "pmos-self-stage: diagnostic hold and :22 verified on boot $boot" || fail 'record (e) append 1 refused'
boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root' || fail 'record (e) append 2 refused'
boot_record_append "$R" 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' || fail 'record (e) append 3 refused'
boot_record_append "$R" 'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)' || fail 'record (e) append 4 refused'
boot_record_append "$R" 'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)' || fail 'record (e) append 5 refused'
boot_record_append "$R" "pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract" || fail 'record (e) append 6 refused'
boot_record_append "$R" 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request' || fail 'record (e) append 7 refused'
boot_record_append "$R" 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' || fail 'record (e) append 8 refused'
boot_record_append "$R" "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot" || fail 'record (e) append 9 refused'
boot_record_append "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'record (e) append 10 refused'
stamp=$($BB awk '{print $1}' /proc/uptime)
boot_record_append "$R" "pmos-self-post: FAIL: independent recovery guard is not armed and unacknowledged (uptime $stamp)" ||
	fail 'record (e) first FAIL append refused'
refused_record="boot $boot
pmos-self-stage: diagnostic hold and :22 verified on boot $boot
pmos-stage: using unpacked persistent postmarketOS root
pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts
pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)
pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)
pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract
pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request
radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover
pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot
usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init
pmos-self-post: FAIL: independent recovery guard is not armed and unacknowledged (uptime $stamp)"
[ "$($BB cat "$R/.omnipha-boot-record")" = "$refused_record" ] ||
	fail 'refusal did not leave the transition line plus exactly one FAIL line'
if boot_record_append "$R" "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"; then
	fail 'success line accepted after a FAIL line'
fi
if boot_record_append "$R" 'radio-bringup: later stage line'; then
	fail 'later non-FAIL line accepted after a FAIL line'
fi
boot_record_append "$R" "pmos-self-post: FAIL: second bounded failure (uptime $stamp)" || fail 'record (e) second FAIL append refused'
if boot_record_append "$R" "pmos-self-post: FAIL: third failure beyond the bound (uptime $stamp)"; then
	fail 'third FAIL line accepted over the post-cutover bound'
fi
if boot_record_verify "$R" "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"; then
	fail 'success verify accepted a refusal record'
fi
$BB printf 'e: refusal left the reached lines plus exactly two bounded FAIL lines; success and later lines refused\n'
$BB umount "$R" || fail 'unmount after (e)'
$BB rmdir "$R"

# (f) state copied from a previous boot: a record whose boot line names a
# foreign boot ID is refused by append and verify on this boot.
mount_root
$BB printf '%s\n' "boot 11111111-2222-3333-4444-555555555555" > "$R/.omnipha-boot-record"
$BB chmod 600 "$R/.omnipha-boot-record"
if boot_record_append "$R" 'pmos-stage: using unpacked persistent postmarketOS root'; then
	fail 'foreign-boot record append accepted'
fi
if boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'; then
	fail 'foreign-boot record verify accepted'
fi
	$BB printf 'f: record state copied from a previous boot refused\n'
	$BB umount "$R" || fail 'unmount after (f)'
	$BB rmdir "$R"

	# (g) valid prior record present: rotate to the per-boot archive, open a
	# fresh record for this boot, then remount and read both files back.
	foreign=11111111-2222-3333-4444-555555555555
	prior="boot $foreign
pmos-self-stage: diagnostic hold and :22 verified on boot $foreign
pmos-stage: using unpacked persistent postmarketOS root"
	mount_root
	$BB printf '%s\n' "$prior" > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	boot_record_open "$R" || fail 'valid prior record did not rotate and open'
	[ "$($BB cat "$R/.omnipha-boot-record")" = "boot $boot" ] || fail 'fresh record is not this boot'
	[ "$($BB stat -c '%u:%a:%h' "$R/.omnipha-boot-record")" = 0:600:1 ] || fail 'fresh record is not root-only link-count-1'
	[ -f "$R/.omnipha-boot-record-$foreign" ] && [ ! -L "$R/.omnipha-boot-record-$foreign" ] || fail 'rotated archive missing'
	[ "$($BB cat "$R/.omnipha-boot-record-$foreign")" = "$prior" ] || fail 'rotated archive content changed'
	[ "$($BB stat -c '%u:%a:%h' "$R/.omnipha-boot-record-$foreign")" = 0:600:1 ] || fail 'rotated archive is not root-only link-count-1'
	boot_record_append "$R" "pmos-self-stage: diagnostic hold and :22 verified on boot $boot" || fail 'append after rotation refused'
	$BB umount -l "$R" || fail 'lazy detach after rotation'
	$BB mount -t ext4 -o ro,noload /dev/block/sda13 "$R" || fail 'remount after rotation'
	[ "$($BB cat "$R/.omnipha-boot-record")" = "boot $boot
pmos-self-stage: diagnostic hold and :22 verified on boot $boot" ] || fail 'rotated fresh record did not survive remount'
	[ "$($BB cat "$R/.omnipha-boot-record-$foreign")" = "$prior" ] || fail 'rotated archive did not survive remount'
	$BB printf 'g: valid prior record rotated to the per-boot archive; new boot opened and survived remount\n'
	$BB umount "$R" || fail 'unmount after (g)'
	$BB rmdir "$R"

	# (h) rotation refusals: symlink, hard link, wrong mode, wrong owner,
	# over-bound, hostile first line, same-boot, and a pre-existing archive
	# all refuse and leave the prior record in place.
	rotate_refused() {
		label=$1
		before=$($BB cat "$R/.omnipha-boot-record")
		if boot_record_open "$R"; then fail "$label accepted"; fi
		[ "$($BB cat "$R/.omnipha-boot-record")" = "$before" ] || fail "$label changed the prior record"
	}
	mount_root
	$BB ln -s /run/keep "$R/.omnipha-boot-record"
	if boot_record_open "$R"; then fail 'symlinked prior record rotated'; fi
	[ -L "$R/.omnipha-boot-record" ] || fail 'symlink refusal replaced the prior record'
	$BB rm "$R/.omnipha-boot-record"
	$BB printf '%s\n' "$prior" > "$R/.omnipha-boot-record"
	$BB ln "$R/.omnipha-boot-record" "$R/.omnipha-boot-record-extra"
	$BB chmod 600 "$R/.omnipha-boot-record" "$R/.omnipha-boot-record-extra"
	rotate_refused 'hardlinked prior record'
	$BB rm "$R/.omnipha-boot-record-extra"
	$BB chmod 644 "$R/.omnipha-boot-record"
	rotate_refused 'wrong-mode prior record'
	$BB chmod 600 "$R/.omnipha-boot-record"
	$BB chown 1:0 "$R/.omnipha-boot-record"
	rotate_refused 'wrong-owner prior record'
	$BB chown 0:0 "$R/.omnipha-boot-record"
	$BB printf '%s\n' "$($BB head -c 4400 /dev/zero | $BB tr '\0' 'x')" > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	rotate_refused 'over-bound prior record'
	$BB printf 'not a boot line\n' > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	rotate_refused 'hostile prior record'
	$BB printf 'boot %s\n' "GGGGGGGG-2222-3333-4444-555555555555" > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	rotate_refused 'non-hex prior boot ID'
	$BB printf 'boot %s\n' "$boot" > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	rotate_refused 'same-boot prior record'
	$BB printf '%s\n' "$prior" > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	$BB printf 'archive\n' > "$R/.omnipha-boot-record-$foreign"
	$BB chmod 600 "$R/.omnipha-boot-record-$foreign"
	rotate_refused 'pre-existing archive'
	[ "$($BB cat "$R/.omnipha-boot-record-$foreign")" = archive ] || fail 'pre-existing archive changed'
	$BB rm "$R/.omnipha-boot-record-$foreign"
	$BB ln -s /run/keep "$R/.omnipha-boot-record-$foreign"
	rotate_refused 'symlinked archive'
	[ -L "$R/.omnipha-boot-record-$foreign" ] || fail 'symlink archive refusal replaced the archive'
	$BB rm "$R/.omnipha-boot-record-$foreign"
	$BB printf 'PARTNAME=other\n' > /sys/class/block/sda13/uevent
	$BB printf '%s\n' "$prior" > "$R/.omnipha-boot-record"
	$BB chmod 600 "$R/.omnipha-boot-record"
	if boot_record_open "$R"; then fail 'wrong-root rotation accepted'; fi
	[ "$($BB cat "$R/.omnipha-boot-record")" = "$prior" ] || fail 'wrong-root rotation changed the prior record'
	[ ! -e "$R/.omnipha-boot-record-$foreign" ] && [ ! -L "$R/.omnipha-boot-record-$foreign" ] || fail 'wrong-root rotation created an archive'
	$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
	boot_record_open "$R" || fail 'valid prior record refused after rotation refusals'
	$BB printf 'h: rotation refusals left every hostile prior record in place\n'
	$BB umount "$R" || fail 'unmount after (h)'
	$BB rmdir "$R"
	exit 0
