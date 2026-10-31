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
	printf 'pass: boot record fixtures; complete record survives interrupted transition and remount readback; failure at named stage keeps prefix only; symlink/wrong-root/over-bound refusals; no device\n'
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
boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'complete record verify refused'
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
usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init"
[ "$($BB cat "$R/.omnipha-boot-record")" = "$expected" ] || fail 'complete record did not survive interruption'
size=$($BB stat -c %s "$R/.omnipha-boot-record")
[ "$size" -le "$boot_record_bound" ] || fail 'record over bound'
$BB printf 'a: complete record survived interruption and remount (%s bytes)\n' "$size"
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
boot_record_verify "$R" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || fail 'injected full record verify refused'
[ "$($BB cat "$R/.omnipha-boot-record")" = "$expected" ] || fail 'injected full record content differs'
$BB printf 'd: injected session-stage open/hold wrote the prefix; full ordered record verified\n'
$BB umount "$R" || fail 'unmount after injected case'
$BB rmdir "$R"
exit 0
