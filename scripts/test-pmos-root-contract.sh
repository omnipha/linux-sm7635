#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ARCHIVE=${ARCHIVE:-$HOME/sm7635-build/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
PIN=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
MOCK_SHA=e112e65f2e9a6dc28531b45eda218284e4afb152dc3a02b588f7a25255cce2d1
HELPER_SHA=fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { sha256sum "$1" | cut -d ' ' -f 1; }

if [ "${1:-}" != --inner ] && [ "${1:-}" != --pid1-ext4 ] && [ "${1:-}" != --ext4-worker ]; then
	[ "$#" -eq 0 ] || fail 'usage: test-pmos-root-contract.sh'
	[ -f "$ARCHIVE" ] && [ ! -L "$ARCHIVE" ] && [ "$(hash "$ARCHIVE")" = "$PIN" ] || fail 'missing or unpinned session archive'
	for path in "$HERE/pmos-root-contract.sh" "$HERE/pmos-session-stage.sh" \
		"$HERE/pmos-session-teardown.sh" "$HERE/pmos-pid1-transition.sh" \
		"$HERE/pmos-pid1-guard.sh" "$HERE/pmos-pid1-ack.sh"; do
		[ -f "$path" ] && [ ! -L "$path" ] || fail "missing script: $path"
	done
	HELPER=${HELPER:-$HOME/sm7635-build/out/restart2}
	[ -f "$HELPER" ] && [ ! -L "$HELPER" ] && [ "$(hash "$HELPER")" = "$HELPER_SHA" ] || fail 'missing or unpinned restart2 fixture'
	sudo -n true || fail 'passwordless sudo required'
	WORK=$(mktemp -d "${TMPDIR:-/tmp}/pmos-root-contract.XXXXXXXX")
	: > "$WORK/loops"
	: > "$WORK/loops"
	: > "$WORK/inners"
	cleanup() {
		while read -r inner; do sudo -n rm -rf -- "$inner" >/dev/null 2>&1 || true; done < "$WORK/inners"
		while read -r dev; do sudo -n /sbin/losetup -d "$dev" >/dev/null 2>&1 || true; done < "$WORK/loops"
		rm -rf -- "$WORK"
	}
	trap cleanup EXIT
	truncate -s 268435456 "$WORK/userdata.img"
	/sbin/mke2fs -q -F -t ext4 -b 4096 "$WORK/userdata.img"
	truncate -s 33554432 "$WORK/other.img"
	/sbin/mke2fs -q -F -t ext4 -b 4096 "$WORK/other.img"
	truncate -s 241421725696 "$WORK/userdata.img"
	truncate -s 268435456 "$WORK/oversize.img"
	/sbin/mke2fs -q -F -t ext4 -b 4096 "$WORK/oversize.img"
	truncate -s 241421726208 "$WORK/oversize.img"
	dev_main=$(sudo -n /sbin/losetup -f --show "$WORK/userdata.img") || fail 'cannot attach userdata loop'
	printf '%s\n' "$dev_main" >> "$WORK/loops"
	dev_other=$(sudo -n /sbin/losetup -f --show "$WORK/other.img") || fail 'cannot attach secondary loop'
	printf '%s\n' "$dev_other" >> "$WORK/loops"
	dev_over=$(sudo -n /sbin/losetup -f --show "$WORK/oversize.img") || fail 'cannot attach oversize loop'
	printf '%s\n' "$dev_over" >> "$WORK/loops"
	main_nums="$((0x$(stat -c %t "$dev_main"))):$((0x$(stat -c %T "$dev_main")))"
	other_nums="$((0x$(stat -c %t "$dev_other"))):$((0x$(stat -c %T "$dev_other")))"
	over_nums="$((0x$(stat -c %t "$dev_over"))):$((0x$(stat -c %T "$dev_over")))"
	sudo -n timeout -k 2 180 unshare --mount --pid --net --fork --kill-child --mount-proc \
		env HOST_ARCHIVE="$ARCHIVE" HELPER="$HELPER" SOURCE="$HERE" MAIN_NUMS="$main_nums" OTHER_NUMS="$other_nums" \
		OVER_NUMS="$over_nums" /bin/busybox sh "$0" --inner
	for case in ack timeout; do
		inner=$(mktemp -d "$WORK/pid1-ext4.XXXXXXXX")
		printf '%s\n' "$inner" >> "$WORK/inners"
		sudo -n timeout -k 2 90 unshare --mount --pid --net --fork --kill-child --mount-proc \
			env HOST_ARCHIVE="$ARCHIVE" SOURCE="$HERE" MAIN_NUMS="$main_nums" OTHER_NUMS="$other_nums" \
			HOST_RUN="/mnt/pmos-root-fixture-$case" INNER="$inner" CASE="$case" HOST_TEST="$0" \
			/bin/busybox sh "$0" --pid1-ext4
	done
	exit 0
fi

BB=/bin/busybox
export BB
if [ "${1:-}" = --ext4-worker ]; then
	CASE=$2
	boot=$3
	HOST_RUN=$4
	trap '[ -f /proc/1/root/run/worker.ok ] || $BB kill -TERM 1 2>/dev/null || true' EXIT
	i=0
	until [ -f /proc/1/root/run/pid1-guard/nonce ] || [ -f /proc/1/root/run/pid1-guard/recovery-request ]; do
		[ "$i" -lt 30 ] || fail 'ext4 guard did not publish nonce after switch_root'
		$BB sleep 0.2
		i=$((i + 1))
	done
	$BB awk '$1 == "/dev/block/sda13" && $2 == "/" && $3 == "ext4" {n++} END {exit(n != 1)}' /proc/1/mounts ||
		fail 'PID 1 root is not switched to ext4 /dev/block/sda13'

	if [ "$CASE" = timeout ]; then
		i=0
		until [ -f /proc/1/root/run/pid1-guard/recovery-request ]; do
			[ "$i" -lt 20 ] || fail 'ext4 guard timeout did not request recovery'
			$BB sleep 1
			i=$((i + 1))
		done
		[ "$($BB cat /proc/1/root/run/pid1-guard/recovery-request)" = bootloader ] || fail 'ext4 timeout recovery request invalid'
		printf 'pass: ext4-timeout; real BusyBox PID 1 switch_root to loop-backed userdata ext4, real guard watch on ext4 switched root, no ack within 3 s, pinned mock recovery request created; no device recovery\n'
		$BB printf 'ok\n' > /proc/1/root/run/worker.ok
		$BB kill -TERM 1
		exit 0
	fi
	$BB cp /proc/1/root/sys/class/block/sda13/uevent "$HOST_RUN/uevent.saved"
	$BB printf 'PARTNAME=super\n' > /proc/1/root/sys/class/block/sda13/uevent
	if sh "$SOURCE/pmos-pid1-ack.sh" "$boot" "$HOST_RUN/known_hosts" "$HOST_RUN/client_key" >"$HOST_RUN/ack-bad.out" 2>&1; then
		fail 'ack accepted switched ext4 root with wrong PARTNAME'
	fi
	$BB grep -q 'strict-key post-cutover probe failed' "$HOST_RUN/ack-bad.out" ||
		{ $BB cat "$HOST_RUN/ack-bad.out" >&2; fail 'ack wrong PARTNAME failure reason'; }
	$BB cp "$HOST_RUN/uevent.saved" /proc/1/root/sys/class/block/sda13/uevent
	sh "$SOURCE/pmos-pid1-ack.sh" "$boot" "$HOST_RUN/known_hosts" "$HOST_RUN/client_key" >"$HOST_RUN/ack.out" 2>&1 ||
		{ $BB cat "$HOST_RUN/ack.out" >&2; fail 'real ext4 switched-root ack failed'; }
	$BB grep -q "pid1-ack: accepted on boot $boot" "$HOST_RUN/ack.out" || fail 'ack acceptance message missing'
	[ "$($BB cat /proc/1/root/run/pid1-guard/accepted)" = "$boot" ] || fail 'guard accepted file missing or wrong boot'
	[ ! -e /proc/1/root/run/pid1-guard/recovery-request ] && [ ! -L /proc/1/root/run/pid1-guard/recovery-request ] || fail 'ack caused mock recovery'
	$BB cp "$SOURCE/pmos-self-post.sh" /proc/1/root/run/pmos-self-post.sh
	$BB cp "$SOURCE/pmos-radio-bringup.sh" /proc/1/root/run/pmos-radio-bringup.sh
	$BB chmod 700 /proc/1/root/run/pmos-self-post.sh /proc/1/root/run/pmos-radio-bringup.sh
	$BB mkdir -p -m 700 /proc/1/root/run/radio-bringup /proc/1/root/run/openrc
	$BB printf 'default\n' > /proc/1/root/run/openrc/softlevel
	$BB cat > /proc/1/root/sbin/rc-service <<'RCS'
#!/bin/busybox sh
exit 0
RCS
	$BB chmod 755 /proc/1/root/sbin/rc-service
	$BB cp /proc/1/root/sys/class/block/sda13/uevent "$HOST_RUN/uevent.saved"
	$BB printf 'PARTNAME=super\n' > /proc/1/root/sys/class/block/sda13/uevent
	$BB chroot /proc/1/root /bin/busybox sh /run/pmos-self-post.sh >"$HOST_RUN/post-bad.out" 2>&1 && fail 'self-post accepted ext4 switched root with wrong PARTNAME'
	$BB grep -q 'switched-root or guard identity check failed' "$HOST_RUN/post-bad.out" || fail 'self-post wrong PARTNAME failure reason'
	$BB chroot /proc/1/root /bin/busybox sh /run/pmos-radio-bringup.sh "$boot" modem capture-ok >"$HOST_RUN/radio-bad.out" 2>&1 && fail 'radio bring-up accepted ext4 switched root with wrong PARTNAME'
	$BB grep -q 'post-cutover PID 1 or default/local absent' "$HOST_RUN/radio-bad.out" || fail 'radio wrong PARTNAME failure reason'
	$BB cp "$HOST_RUN/uevent.saved" /proc/1/root/sys/class/block/sda13/uevent
	$BB rm -f /proc/1/root/run/pid1-guard/accepted /proc/1/root/run/pid1-guard/ack
	$BB printf '%s\n' fixture-nonce > /proc/1/root/run/pid1-guard/nonce
	$BB chroot /proc/1/root /bin/busybox sh -c '
BB=/bin/busybox
. /run/pid1-guard/root-contract.sh
boot=$($BB cat /proc/sys/kernel/random/boot_id)
root_contract_switched_root /proc/1/mounts /proc/1/mountinfo || exit 1
boot_record_open / || exit 1
for line in \
	"pmos-self-stage: diagnostic hold and :22 verified on boot $boot" \
	"pmos-stage: using unpacked persistent postmarketOS root" \
	"pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts" \
	"pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)" \
	"pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)" \
	"pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract" \
	"pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request" \
	"radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover" \
	"pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot" \
	"usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init"; do
	boot_record_append / "$line" || exit 1
done' || fail 'self-post fixture pre-cutover record refused on the persistent root'
	$BB chroot /proc/1/root /bin/busybox sh /run/pmos-self-post.sh >"$HOST_RUN/post-ok.out" 2>&1 && fail 'self-post succeeded without radio script at /run/radio-bringup'
	$BB grep -q 'cold-start post-cutover PID 1.*independent recovery guard remains unacknowledged' "$HOST_RUN/post-ok.out" || { $BB cat "$HOST_RUN/post-ok.out" >&2; fail 'self-post rejected valid ext4 switched root'; }
	$BB grep -q "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" /proc/1/root/.omnipha-boot-record ||
		{ $BB cat /proc/1/root/.omnipha-boot-record >&2; fail 'post-cutover record line missing on the persistent root'; }
	$BB chroot /proc/1/root /bin/busybox sh /run/pmos-radio-bringup.sh "$boot" modem capture-ok >"$HOST_RUN/radio-ok.out" 2>&1 && fail 'radio bring-up succeeded without staged INI'
	$BB grep -q 'pre-cutover staged stock INI missing' "$HOST_RUN/radio-ok.out" || { $BB cat "$HOST_RUN/radio-ok.out" >&2; fail 'radio bring-up rejected valid ext4 switched root'; }
	printf 'pass: ext4-ack; real BusyBox PID 1 switch_root to loop-backed userdata ext4 with surviving pre-cutover Dropbear PID and pinned key, real guard watch on ext4 switched root, strict key-only SSH before/after, ack/self-post/radio rejected on wrong PARTNAME and accepted after restoring userdata; no device recovery\n'
	$BB printf 'ok\n' > /proc/1/root/run/worker.ok
	$BB kill -TERM 1
	exit 0
fi
if [ "${1:-}" = --pid1-ext4 ]; then
	[ "$$" = 1 ] || fail 'not isolated PID 1'
	[ "$CASE" = ack ] || [ "$CASE" = timeout ] || fail 'invalid ext4 pid1 case'
	$BB mount --make-rprivate / || fail 'private mount namespace'
	$BB mount -t tmpfs -o mode=0755,size=64m tmpfs /run || fail 'host run tmpfs'
	$BB mount -t tmpfs -o mode=0755 tmpfs /dev || fail 'host dev tmpfs'
	$BB mknod -m 666 /dev/null c 1 3
	$BB mknod -m 666 /dev/zero c 1 5
	$BB mknod -m 666 /dev/random c 1 8
	$BB mknod -m 666 /dev/urandom c 1 9
	$BB mknod -m 666 /dev/ptmx c 5 2
	$BB mknod -m 666 /dev/tty c 5 0
	$BB mkdir -p /dev/pts /dev/block /sys/class/block /root/.ssh
	$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts /dev/pts
	$BB mount -t tmpfs -o mode=0755,size=1m tmpfs /sys/class/block || fail 'host sysfs block tmpfs'
	$BB mount -t tmpfs -o mode=0700 tmpfs /root || fail 'host root tmpfs'
	$BB mkdir -p /root/.ssh "$HOST_RUN"
	$BB mount -t tmpfs -o mode=0755,size=16m tmpfs "$HOST_RUN" || fail 'worker state tmpfs'
	umask 077
	$BB touch /run/keep
	$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
	$BB chmod 600 /run/pmos-session.tar.gz
	$BB cp "$SOURCE/pmos-root-contract.sh" /run/pmos-root-contract.sh
	$BB chmod 700 /run/pmos-root-contract.sh
	ssh-keygen -q -t ed25519 -N '' -f "$HOST_RUN/client_key"
	$BB cp "$HOST_RUN/client_key.pub" /root/.ssh/authorized_keys
	$BB chmod 600 /root/.ssh/authorized_keys
	umask 022
	ip link set lo up
	ip addr add 172.16.42.2/32 dev lo
	python3 -c 'import socket,time; s=socket.socket(); s.bind(("172.16.42.2",22)); s.listen(); time.sleep(900)' &
	$BB sleep 1
	$BB mkdir -p /sys/class/block/sda13 /sys/class/block/sda6
	$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
	$BB printf '%s\n' "$MAIN_NUMS" > /sys/class/block/sda13/dev
	$BB printf 'PARTNAME=super\n' > /sys/class/block/sda6/uevent
	$BB printf '%s\n' "$OTHER_NUMS" > /sys/class/block/sda6/dev
	$BB mknod -m 0400 /dev/block/sda13 b "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}"
	$BB mknod -m 0400 /dev/block/sda6 b "${OTHER_NUMS%%:*}" "${OTHER_NUMS##*:}"
	$BB umount -f /run/pmos >/dev/null 2>&1 || true
	$BB mkdir -m 700 /run/pmos
	$BB mount -t ext4 -o ro,noload /dev/block/sda13 /run/pmos || fail 'cannot mount ext4 userdata root'
	$BB mount --make-private /run/pmos
	$BB mount -o remount,rw /dev/block/sda13 /run/pmos
	$BB find /run/pmos -mindepth 1 -maxdepth 1 ! -name 'lost+found' -exec $BB rm -rf -- {} +
	$BB mount -o remount,ro,noload /dev/block/sda13 /run/pmos
	PMOS_ROOT_KIND=ext4 SOURCE="$SOURCE" $BB sh "$SOURCE/pmos-session-stage.sh" >"$HOST_RUN/stage.out" 2>&1 ||
		{ $BB cat "$HOST_RUN/stage.out" >&2; fail 'ext4 pid1 stage failed'; }
	$BB mv /run/pmos/bin/busybox /run/pmos/bin/distro-busybox
	$BB cp /bin/busybox /run/pmos/bin/busybox
	[ -f /run/pmos/bin/busybox ] && [ ! -L /run/pmos/bin/busybox ] || fail 'fixture busybox is not a regular file'
	$BB chroot /run/pmos /bin/busybox true || fail 'native busybox cannot run before fixture applets'
	[ -f /run/pmos/bin/busybox ] && [ ! -L /run/pmos/bin/busybox ] || fail 'fixture native busybox changed'
	$BB rm -f /run/pmos/sbin/init
	$BB cat > /run/pmos/init <<'INIT'
#!/bin/busybox sh
trap '[ -f /run/worker.ok ] && exit 0; exit 1' TERM
while :; do /bin/busybox sleep 1; done
INIT
	$BB chmod 755 /run/pmos/init
	$BB cp /run/pmos/init /run/pmos/sbin/init
	$BB chmod 755 /run/pmos/sbin/init
	$BB cp /run/pmos-root-contract.sh /run/pmos/run/pmos-root-contract.sh
	$BB chmod 700 /run/pmos/run/pmos-root-contract.sh
	$BB cp /run/pmos-root-contract.sh /run/pmos/run/pmos-root-contract.sh
	$BB chmod 700 /run/pmos/run/pmos-root-contract.sh
	$BB mkdir -p /run/pmos/sys/class/block
	$BB mount --bind /sys/class/block /run/pmos/sys/class/block
	$BB mount --make-private /run/pmos/sys/class/block
	$BB awk '/^ssh-ed25519 / {printf "[172.16.42.2]:2222 %s %s\n", $1, $2}' /run/pmos/run/second-hostkey.pub > "$HOST_RUN/known_hosts"
	$BB chmod 600 "$HOST_RUN/known_hosts"
	$BB cat > "$HOST_RUN/mock-ext4" <<'MOCK'
#!/bin/busybox sh
set -eu
b=/bin/busybox
s=/run/pid1-guard
[ "$#" -eq 1 ] && [ "$1" = bootloader ] || exit 2
$b awk '$2 == "/" {n++; if ($3 != "tmpfs" && $3 != "ext4") bad++} END {exit(n != 1 || bad)}' /proc/mounts || exit 2
[ "$($b stat -c '%u:%a' "$s")" = 0:700 ] || exit 2
[ "$($b stat -c '%d:%i' /)" = "$($b cat "$s/root-identity")" ] || exit 2
[ ! -e "$s/recovery-request" ] && [ ! -L "$s/recovery-request" ] || exit 2
$b printf 'bootloader\n' > "$s/recovery-request"
MOCK
	$BB chmod 700 "$HOST_RUN/mock-ext4"
	[ "$(hash "$HOST_RUN/mock-ext4")" = fe72fe25364a1a08c6482bcecb3175f2c0def38af6fc02967b1edc1d6cf28e71 ] || fail 'ext4 mock SHA changed'
	$BB cp "$SOURCE/pmos-pid1-guard.sh" /run/pmos-pid1-guard.sh
	$BB chmod 700 /run/pmos-pid1-guard.sh
	if [ "$CASE" = ack ]; then budget=25; else budget=3; fi
	PMOS_ROOT_CONTRACT=/run/pmos-root-contract.sh $BB sh /run/pmos-pid1-guard.sh \
		mock-arm /run/pmos "$budget" "$HOST_RUN/mock-ext4" \
		fe72fe25364a1a08c6482bcecb3175f2c0def38af6fc02967b1edc1d6cf28e71 >"$HOST_RUN/arm.out" 2>&1 ||
		{ $BB cat "$HOST_RUN/arm.out" >&2; fail 'ext4 guard arm failed'; }
	[ -f /run/pmos/run/pid1-guard/armed ] || fail 'ext4 guard not armed'
	boot=$($BB cat /proc/sys/kernel/random/boot_id)
	unshare --mount --propagation slave env SOURCE="$SOURCE" /bin/busybox sh "$HOST_TEST" --ext4-worker "$CASE" "$boot" "$HOST_RUN" &
	$BB mount -t tmpfs -o mode=0755,size=16m tmpfs "$INNER"
	$BB mkdir -p "$INNER/bin" "$INNER/pmos" "$INNER/oldroot"
	$BB touch "$INNER/init"
	$BB cp /bin/busybox "$INNER/bin/busybox"
	$BB mount --move /run/pmos "$INNER/pmos"
	$BB pivot_root "$INNER" "$INNER/oldroot"
	$BB umount -l /oldroot
	exec /bin/busybox switch_root /pmos /sbin/init
fi
CONTRACT="$SOURCE/pmos-root-contract.sh"
STAGE="$SOURCE/pmos-session-stage.sh"
TEARDOWN="$SOURCE/pmos-session-teardown.sh"
TRANSITION="$SOURCE/pmos-pid1-transition.sh"
GUARD="$SOURCE/pmos-pid1-guard.sh"
ACK="$SOURCE/pmos-pid1-ack.sh"

$BB mount --make-rprivate / || fail 'private mount namespace unavailable'
$BB mount -t tmpfs -o mode=0700 tmpfs /root || fail 'fixture root'
$BB mount -t tmpfs -o mode=0755 tmpfs /dev || fail 'fixture dev'
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 666 /dev/zero c 1 5
$BB mknod -m 666 /dev/random c 1 8
$BB mknod -m 666 /dev/urandom c 1 9
$BB mknod -m 666 /dev/ptmx c 5 2
$BB mknod -m 666 /dev/tty c 5 0
$BB mkdir -p /dev/pts /dev/block /sys/class/block
$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts /dev/pts
$BB mount -t tmpfs -o mode=0755,size=1m tmpfs /sys/class/block || fail 'fixture sysfs block'
$BB mount -t tmpfs -o mode=0755,size=64m tmpfs /run || fail 'fixture run'

umask 077
$BB cp "$CONTRACT" /run/pmos-root-contract.sh
$BB cp "$GUARD" /run/pmos-pid1-guard.sh
$BB chmod 700 /run/pmos-root-contract.sh /run/pmos-pid1-guard.sh
$BB touch /run/keep
$BB cp "$HOST_ARCHIVE" /run/pmos-session.tar.gz
$BB chmod 600 /run/pmos-session.tar.gz
$BB mkdir -p /root/.ssh
ssh-keygen -q -t ed25519 -N '' -f /run/client_key
$BB cp /run/client_key.pub /root/.ssh/authorized_keys
$BB chmod 600 /root/.ssh/authorized_keys
umask 022

ip link set lo up
ip addr add 172.16.42.2/32 dev lo
python3 -c 'import socket,time; s=socket.socket(); s.bind(("172.16.42.2",22)); s.listen(); time.sleep(900)' &
diag_pid=$!
$BB sleep 1

set_part() {
	$BB mkdir -p "/sys/class/block/$1"
	$BB printf 'PARTNAME=%s\n' "$2" > "/sys/class/block/$1/uevent"
	$BB printf '%s\n' "$3" > "/sys/class/block/$1/dev"
}
mk_bnode() {
	$BB rm -f "$1"
	$BB mknod -m 0400 "$1" b "${2%%:*}" "${2##*:}"
}

set_part sda13 userdata "$MAIN_NUMS"
set_part sda6 super "$OTHER_NUMS"
mk_bnode /dev/block/sda13 "$MAIN_NUMS"
mk_bnode /dev/block/sda6 "$OTHER_NUMS"
[ "$($BB blockdev --getsize64 /dev/block/sda13)" = 241421725696 ] || fail 'userdata fixture is not the measured partition size'

. "$CONTRACT"

$BB mkdir -m 700 /run/pmos
$BB mount -t ext4 -o rw /dev/block/sda13 /run/pmos
$BB mount --make-private /run/pmos
PMOS_ROOT_KIND=ext4 $BB sh "$STAGE" >/run/reject.out 2>&1 && fail 'writable unpromoted ext4 root accepted'
$BB grep -q 'FAIL: userdata root cannot be promoted read-write' /run/reject.out || { $BB cat /run/reject.out >&2; fail 'writable unpromoted root reason'; }
$BB umount /run/pmos

$BB mount -t ext4 -o ro /dev/block/sda13 /run/pmos
$BB mount --make-private /run/pmos
root_contract_pinned_userdata /run/pmos && fail 'ext4 root without noload accepted'
$BB umount /run/pmos

$BB mount -t ext4 -o ro,noload /dev/block/sda13 /run/pmos
$BB mount --make-shared /run/pmos
root_contract_pinned_userdata /run/pmos && fail 'shared ext4 root accepted'
$BB mount --make-private /run/pmos
root_contract_pinned_userdata /run/pmos || fail 'pinned ro,noload userdata root rejected'

$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda6/uevent
root_contract_pinned_userdata /run/pmos && fail 'duplicate userdata PARTNAME accepted'
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda6/uevent

$BB printf 'PARTNAME=other\n' > /sys/class/block/sda13/uevent
root_contract_pinned_userdata /run/pmos && fail 'wrong PARTNAME accepted'
$BB rm /sys/class/block/sda13/uevent
root_contract_pinned_userdata /run/pmos && fail 'missing PARTNAME accepted'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent

$BB printf '%s\n' "$OTHER_NUMS" > /sys/class/block/sda13/dev
root_contract_pinned_userdata /run/pmos && fail 'mismatched sysfs dev numbers accepted'
$BB printf '%s\n' "$MAIN_NUMS" > /sys/class/block/sda13/dev

$BB rm /dev/block/sda13
$BB ln -s sda6 /dev/block/sda13
root_contract_pinned_userdata /run/pmos && fail 'symlinked block node accepted'
$BB rm /dev/block/sda13
mk_bnode /dev/block/sda13 "$MAIN_NUMS"

[ "$ROOT_CONTRACT_SIZE" = 241421725696 ] || fail 'positive case is not the measured userdata size'
ROOT_CONTRACT_MIN_BYTES=241421725697 root_contract_pinned_userdata /run/pmos && fail 'undersized userdata accepted'
ROOT_CONTRACT_MAX_BYTES=241421725695 root_contract_pinned_userdata /run/pmos && fail 'one-byte-over-maximum userdata accepted'
[ "$ROOT_CONTRACT_MAX_BYTES" = 241421725696 ] || fail 'measured userdata maximum changed'
set_part sda14 super "$OVER_NUMS"
mk_bnode /dev/block/sda14 "$OVER_NUMS"
[ "$($BB blockdev --getsize64 /dev/block/sda14)" = 241421726208 ] || fail 'oversize fixture node has wrong size'
$BB mkdir /run/dup
$BB mount -t ext4 -o ro,noload /dev/block/sda14 /run/dup
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda13/uevent
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda14/uevent
( ROOT_CONTRACT_MAX_BYTES=241421726208; root_contract_pinned_userdata /run/dup ) || fail 'oversize fixture is not otherwise valid userdata'
$BB cat > /run/size-bb <<'SIZE'
#!/bin/busybox sh
if [ "$1" = blockdev ] && [ "$2" = --getsize64 ] && [ "$3" = /dev/block/sda14 ]; then
	/bin/busybox printf '241421725697\n'
	exit 0
fi
exec /bin/busybox "$@"
SIZE
$BB chmod 700 /run/size-bb
[ "$(/run/size-bb blockdev --getsize64 /dev/block/sda14)" = 241421725697 ] || fail 'one-byte-oversize node report missing'
( BB=/run/size-bb; root_contract_pinned_userdata /run/dup ) && fail 'one-byte-oversize userdata node accepted'
root_contract_pinned_userdata /run/dup && fail 'oversized userdata node accepted'
$BB umount /run/dup
$BB rmdir /run/dup
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda14/uevent
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
root_contract_pinned_userdata /run/pmos || fail 'measured userdata root rejected after oversize rejection'

$BB mkdir /run/dup
$BB mount -t ext4 -o ro,noload /dev/block/sda13 /run/dup
root_contract_pinned_userdata /run/pmos && fail 'duplicate userdata mount accepted'
$BB umount /run/dup
$BB rmdir /run/dup

PMOS_ROOT_KIND=ext4 $BB sh "$STAGE" >/run/stage.out 2>&1 || { $BB cat /run/stage.out >&2; fail 'positive ext4 userdata stage failed'; }
$BB awk '$1 == "/dev/block/sda13" && $2 == "/run/pmos" && $3 == "ext4" && $4 ~ /(^|,)rw(,|$)/ {n++} END {exit(n != 1)}' /proc/mounts || fail 'staged ext4 root not promoted rw'
$BB awk '$2 == "/run/pmos/run" && $3 == "tmpfs" && $4 ~ /(^|,)size=8192k(,|$)/ && $4 ~ /(^|,)mode=700(,|$)/ {n++} END {exit(n != 1)}' /proc/mounts || fail 'ext4 root lost separate 8m tmpfs /run'
$BB awk '$2 == "/run/pmos/dev" && $3 == "tmpfs" {n++} END {exit(n != 1)}' /proc/mounts || fail 'ext4 root lost separate tmpfs /dev'
$BB awk '$2 == "/run/pmos/dev/pts" && $3 == "devpts" {n++} END {exit(n != 1)}' /proc/mounts || fail 'ext4 root lost private devpts'
root_contract_stage_root /run/pmos && [ "$ROOT_CONTRACT_KIND" = ext4 ] || fail 'staged ext4 root rejected by contract'

$BB printf 'PARTNAME=super\n' > /sys/class/block/sda13/uevent
if (log() { $BB printf '%s\n' "$*"; }; . "$TRANSITION") >/run/tr.out 2>&1; then
	fail 'transition accepted ext4 root with wrong PARTNAME'
fi
$BB grep -q 'pid1 transition refused: root or child mount invalid' /run/tr.out || fail 'transition wrong PARTNAME reason'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent

$BB cp "$HELPER" /run/pmos/bin/restart2
$BB chmod 755 /run/pmos/bin/restart2
[ "$($BB stat -c '%u:%a:%h:%s' /run/pmos/bin/restart2)" = 0:755:1:872 ] &&
	[ "$(hash /run/pmos/bin/restart2)" = "$HELPER_SHA" ] || fail 'prior-boot pinned helper missing'
$BB awk '
	/^	if \[ -e "\$root\/bin\/restart2" \] \|\| \[ -L "\$root\/bin\/restart2" \]; then$/ {
		print "\t[ ! -e \"$root$STATE\" ] && [ ! -L \"$root$STATE\" ] &&"
		print "\t[ ! -e \"$root/bin/restart2\" ] && [ ! -L \"$root/bin/restart2\" ] || fail '\''guard or RESTART2 already exists'\''"
		skip = 1
		next
	}
	skip && /^	fi$/ { skip = 0; next }
	!skip { print }
' "$GUARD" > /run/pmos-pid1-guard-old.sh
$BB chmod 700 /run/pmos-pid1-guard-old.sh
$BB sh /run/pmos-pid1-guard-old.sh arm /run/pmos 160 >/run/guard-old.out 2>&1 && fail 'old guard accepted prior helper'
$BB grep -q 'guard or RESTART2 already exists' /run/guard-old.out ||
	{ $BB cat /run/guard-old.out >&2; fail 'old guard did not reproduce the measured RESTART2 refusal'; }
[ ! -e /run/pmos/run/pid1-guard ] && [ ! -L /run/pmos/run/pid1-guard ] || fail 'old refusal created guard state'
if $BB sh "$GUARD" arm /run/pmos 160 >/run/guard-reject.out 2>&1; then
	fail 'guard armed on non-target host with prior-boot helper'
fi
$BB grep -q 'not the target device' /run/guard-reject.out ||
	{ $BB cat /run/guard-reject.out >&2; fail 'pinned prior-boot helper not accepted before device check'; }
if (log() { $BB printf '%s\n' "$*"; }; . "$TRANSITION") >/run/tr.out 2>&1; then
	fail 'transition armed real guard on non-target host'
fi
$BB grep -q 'pid1-guard: not the target device' /run/tr.out &&
	$BB grep -q 'pid1 transition refused: independent recovery guard not armed' /run/tr.out ||
	{ $BB cat /run/tr.out >&2; fail 'transition did not reach pinned device check'; }
[ ! -e /run/pmos/run/pid1-guard ] && [ ! -L /run/pmos/run/pid1-guard ] || fail 'prior-boot refusal created guard state'
$BB rm /run/pmos/bin/restart2

$BB cat > /run/mock <<'MOCK'
#!/bin/busybox sh
set -eu
b=/bin/busybox
s=/run/pid1-guard
[ "$#" -eq 1 ] && [ "$1" = bootloader ] || exit 2
$b awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/mounts || exit 2
[ "$($b stat -c '%u:%a' "$s")" = 0:700 ] || exit 2
[ "$($b stat -c '%d:%i' /)" = "$($b cat "$s/root-identity")" ] || exit 2
[ ! -e "$s/recovery-request" ] && [ ! -L "$s/recovery-request" ] || exit 2
$b printf 'bootloader\n' > "$s/recovery-request"
MOCK
$BB chmod 700 /run/mock
[ "$(hash /run/mock)" = "$MOCK_SHA" ] || fail 'mock sha'
$BB mv /run/pmos/bin/busybox /run/pmos/bin/distro-busybox
$BB cp /bin/busybox /run/pmos/bin/busybox
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda13/uevent
$BB sh "$GUARD" mock-arm /run/pmos 10 /run/mock "$MOCK_SHA" >/run/guard.out 2>&1 && fail 'guard accepted ext4 root with wrong PARTNAME'
$BB grep -q 'new root is not mounted tmpfs or pinned userdata ext4' /run/guard.out || fail 'guard wrong PARTNAME reason'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
$BB sh "$GUARD" mock-arm /run/pmos 30 /run/mock "$MOCK_SHA" >/run/guard.out 2>&1 || { $BB cat /run/guard.out >&2; fail 'guard rejected pinned ext4 userdata root'; }
[ -f /run/pmos/run/pid1-guard/armed ] && [ -f /run/pmos/run/pid1-guard/root-contract.sh ] || fail 'guard did not arm and stage root-contract on ext4 root'
for p in /proc/[0-9]*; do
	[ "$($BB stat -Lc '%d:%i' "$p/root" 2>/dev/null || true)" = "$($BB stat -c '%d:%i' /run/pmos)" ] || continue
	[ "${p#/proc/}" != "$($BB cat /run/pmos/run/dropbear-session.pid)" ] || continue
	$BB kill "${p#/proc/}" 2>/dev/null || true
done
$BB rm -rf /run/pmos/run/pid1-guard
$BB mv /run/pmos/bin/distro-busybox /run/pmos/bin/busybox
plant_helper() {
	$BB rm -f /run/pmos/bin/restart2
	$BB cp "$HELPER" /run/pmos/bin/restart2
	$BB chmod 755 /run/pmos/bin/restart2
}
reject_helper() {
	$BB sh "$GUARD" arm /run/pmos 160 >/run/guard-reuse.out 2>&1 && fail "$1"
	$BB grep -q "$2" /run/guard-reuse.out || { $BB cat /run/guard-reuse.out >&2; fail "$1 reason"; }
	if [ "$2" = 'guard state already exists' ]; then
		[ -e /run/pmos/run/pid1-guard ] || [ -L /run/pmos/run/pid1-guard ] || fail "$1 removed existing state"
	else
		[ ! -e /run/pmos/run/pid1-guard ] && [ ! -L /run/pmos/run/pid1-guard ] || fail "$1 created guard state"
	fi
}
plant_helper
$BB ln -sf restart2 /run/pmos/bin/restart2-link
$BB rm /run/pmos/bin/restart2
$BB mv /run/pmos/bin/restart2-link /run/pmos/bin/restart2
reject_helper 'symlinked prior helper' 'stale RESTART2 is not the pinned helper'
$BB rm /run/pmos/bin/restart2
plant_helper
$BB ln /run/pmos/bin/restart2 /run/pmos/bin/restart2-extra
reject_helper 'hardlinked prior helper' 'stale RESTART2 is not the pinned helper'
$BB rm /run/pmos/bin/restart2 /run/pmos/bin/restart2-extra
plant_helper
$BB chmod 700 /run/pmos/bin/restart2
reject_helper 'unprotected prior helper' 'stale RESTART2 is not the pinned helper'
plant_helper
$BB printf x >> /run/pmos/bin/restart2
reject_helper 'modified prior helper' 'stale RESTART2 is not the pinned helper'
$BB rm /run/pmos/bin/restart2
$BB printf 'not the pinned helper\n' > /run/pmos/bin/restart2
$BB chmod 755 /run/pmos/bin/restart2
reject_helper 'foreign prior helper' 'stale RESTART2 is not the pinned helper'
$BB rm /run/pmos/bin/restart2
plant_helper
$BB mkdir -m 700 /run/pmos/run/pid1-guard
reject_helper 'foreign guard state' 'guard state already exists'
$BB rm -rf /run/pmos/run/pid1-guard
$BB ln -s /run /run/pmos/run/pid1-guard
reject_helper 'symlinked guard state' 'guard state already exists'
$BB rm /run/pmos/run/pid1-guard
plant_helper
$BB sh "$GUARD" arm /run/pmos 160 >/run/guard-reuse.out 2>&1 && fail 'host fixture reached real recovery'
$BB grep -q 'not the target device' /run/guard-reuse.out ||
	{ $BB cat /run/guard-reuse.out >&2; fail 'valid prior helper was rejected before the device pin'; }
[ ! -e /run/pmos/run/pid1-guard ] && [ ! -L /run/pmos/run/pid1-guard ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' /run/pmos/bin/restart2)" = 0:755:1:872 ] &&
	[ "$(hash /run/pmos/bin/restart2)" = "$HELPER_SHA" ] || fail 'valid prior helper changed before the device pin'
$BB rm -rf /run/pmos/run/pid1-guard
$BB rm /run/pmos/bin/restart2
$BB mv /run/pmos/bin/busybox /run/pmos/bin/distro-busybox
$BB cp /bin/busybox /run/pmos/bin/busybox
$BB sh "$GUARD" mock-arm /run/pmos 30 /run/mock "$MOCK_SHA" >/run/guard-reuse.out 2>&1 ||
	{ $BB cat /run/guard-reuse.out >&2; fail 'mock guard did not arm after helper reuse cases'; }
[ -f /run/pmos/run/pid1-guard/armed ] && [ ! -L /run/pmos/run/pid1-guard/armed ] &&
	[ "$($BB cat /run/pmos/run/pid1-guard/armed)" = "$($BB cat /proc/sys/kernel/random/boot_id)" ] || fail 'mock guard deadline or armed state changed'
for p in /proc/[0-9]*; do
	[ "$($BB stat -Lc '%d:%i' "$p/root" 2>/dev/null || true)" = "$($BB stat -c '%d:%i' /run/pmos)" ] || continue
	[ "${p#/proc/}" != "$($BB cat /run/pmos/run/dropbear-session.pid)" ] || continue
	$BB kill "${p#/proc/}" 2>/dev/null || true
done
$BB rm -rf /run/pmos/run/pid1-guard
$BB mv /run/pmos/bin/distro-busybox /run/pmos/bin/busybox

$BB printf 'PARTNAME=super\n' > /sys/class/block/sda13/uevent
$BB sh "$TEARDOWN" >/run/td-bad.out 2>&1 && fail 'teardown accepted ext4 root with wrong PARTNAME'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda13/uevent
$BB sh "$TEARDOWN" >/run/td-ok.out 2>&1 || { $BB cat /run/td-ok.out >&2; fail 'teardown rejected valid ext4 userdata root'; }
[ ! -e /run/pmos ] && ! $BB grep -q '/run/pmos' /proc/mounts || fail 'ext4 teardown left root mounted'

$BB mkdir -m 700 /run/switched
$BB printf '/dev/block/sda13 / ext4 rw,relatime,noload 0 0\n' > /run/switched/mounts
$BB printf '91 1 %s / / rw,relatime - ext4 /dev/block/sda13 rw,noload\n' "$MAIN_NUMS" > /run/switched/mountinfo
root_contract_switched_root /run/switched/mounts /run/switched/mountinfo && [ "$ROOT_CONTRACT_KIND" = ext4 ] && [ "$ROOT_CONTRACT_SIZE" = 241421725696 ] || fail 'switched ext4 userdata root rejected'
$BB rm /dev/block/sda13
$BB printf '471526809\n' > /sys/class/block/sda13/size
root_contract_switched_root /run/switched/mounts /run/switched/mountinfo && fail 'switched one-byte-oversize userdata accepted'
$BB rm /sys/class/block/sda13/size
mk_bnode /dev/block/sda13 "$MAIN_NUMS"
$BB printf '/dev/block/sda6 / ext4 rw,relatime,noload 0 0\n' > /run/switched/mounts
$BB printf '91 1 %s / / rw,relatime - ext4 /dev/block/sda6 rw,noload\n' "$OTHER_NUMS" > /run/switched/mountinfo
root_contract_switched_root /run/switched/mounts /run/switched/mountinfo && fail 'switched non-userdata ext4 root accepted'
$BB printf '/dev/block/sda13 / f2fs rw,relatime 0 0\n' > /run/switched/mounts
$BB printf '91 1 %s / / rw,relatime - f2fs /dev/block/sda13 rw\n' "$MAIN_NUMS" > /run/switched/mountinfo
root_contract_switched_root /run/switched/mounts /run/switched/mountinfo && fail 'switched non-ext4 root accepted'
$BB printf '/dev/block/sda13 / ext4 rw,relatime,noload 0 0\n' > /run/switched/mounts
$BB printf '91 1 %s / / rw,relatime shared:1 - ext4 /dev/block/sda13 rw,noload\n' "$MAIN_NUMS" > /run/switched/mountinfo
root_contract_switched_root /run/switched/mounts /run/switched/mountinfo && fail 'switched shared ext4 root accepted'

$BB kill "$diag_pid" 2>/dev/null || true
printf 'pass: host-only root-type contract fixture; pinned PARTNAME=userdata ext4 root accepted (ro,noload pin -> rw,noload promote, stage, transition, guard arm, switched-root check, teardown) and all weakened root/mount/partition cases rejected\n'
