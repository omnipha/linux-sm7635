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

$BB mkdir -p /run/run90
$BB cat > /run/run90/mounts <<'EOF'
/dev/block/sda13 / ext4 rw,relatime,norecovery 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0
tmpfs /run tmpfs rw,nosuid,nodev,size=8192k,mode=700 0 0
tmpfs /dev tmpfs rw,relatime,size=1024k 0 0
devpts /dev/pts devpts rw,relatime,mode=620,ptmxmode=666 0 0
configfs /sys/kernel/config configfs rw,nosuid,nodev,noexec,relatime 0 0
EOF
$BB cat > /run/run90/mountinfo <<EOF
41 1 $MAIN_NUMS / / rw,relatime - ext4 /dev/block/sda13 rw,norecovery
42 41 0:5 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
43 41 0:6 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sysfs rw
44 41 0:7 / /run rw,nosuid,nodev - tmpfs tmpfs rw,size=8192k,mode=700
45 41 0:8 / /dev rw,relatime - tmpfs tmpfs rw,size=1024k
46 45 0:9 / /dev/pts rw,relatime - devpts devpts rw,mode=620,ptmxmode=666
47 43 0:10 / /sys/kernel/config rw,nosuid,nodev,noexec,relatime - configfs configfs rw
EOF
root_contract_switched_root /run/run90/mounts /run/run90/mountinfo ||
	fail 'run-90 post-cutover fixture (single rw,relatime,norecovery sda13 root) rejected'
[ "$ROOT_CONTRACT_KIND" = ext4 ] && [ "$ROOT_CONTRACT_NODE" = /dev/block/sda13 ] &&
	[ "$ROOT_CONTRACT_SIZE" = 241421725696 ] && [ "$ROOT_CONTRACT_OPTS" = rw,relatime,norecovery ] ||
	fail 'run-90 post-cutover fixture identity mismatch'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda6/uevent
root_contract_switched_root /run/run90/mounts /run/run90/mountinfo &&
	fail 'switched root accepted with two userdata PARTNAME blocks'
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda6/uevent
$BB printf '48 41 %s /vendor/firmware_mnt /vendor/firmware_mnt rw,relatime - ext4 /dev/block/sda13 rw,norecovery\n' "$MAIN_NUMS" >> /run/run90/mountinfo
root_contract_switched_root /run/run90/mounts /run/run90/mountinfo &&
	fail 'switched root with a second same-partition mount accepted'
$BB mkdir -p /run/run93
$BB cat > /run/run93/mounts <<'EOF'
/dev/block/sda13 / ext4 rw,relatime,norecovery 0 0
tmpfs /run tmpfs rw,nosuid,nodev,relatime,size=8192k,mode=700 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0
configfs /sys/kernel/config configfs rw,nosuid,nodev,noexec,relatime 0 0
tmpfs /dev tmpfs rw,nosuid,noexec,relatime,size=10240k,mode=755 0 0
devpts /dev/pts devpts rw,relatime,mode=620,ptmxmode=666 0 0
securityfs /sys/kernel/security securityfs rw,nosuid,nodev,noexec,relatime 0 0
debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,relatime 0 0
fusectl /sys/fs/fuse/connections fusectl rw,nosuid,nodev,noexec,relatime 0 0
selinuxfs /sys/fs/selinux selinuxfs rw,nosuid,nodev,noexec,relatime 0 0
pstore /sys/fs/pstore pstore rw,nosuid,nodev,noexec,relatime 0 0
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime 0 0
EOF
$BB cat > /run/run93/mountinfo <<EOF
28 1 $MAIN_NUMS / / rw,relatime - ext4 /dev/block/sda13 rw,norecovery
29 28 0:21 / /run rw,nosuid,nodev,relatime - tmpfs tmpfs rw,size=8192k,mode=700
30 28 0:22 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
31 28 0:18 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sysfs rw
32 31 0:16 / /sys/kernel/config rw,nosuid,nodev,noexec,relatime - configfs configfs rw
33 28 0:23 / /dev rw,nosuid,noexec,relatime - tmpfs tmpfs rw,size=10240k,mode=755
34 33 0:24 / /dev/pts rw,relatime - devpts devpts rw,mode=620,ptmxmode=666
35 31 0:5 / /sys/kernel/security rw,nosuid,nodev,noexec,relatime - securityfs securityfs rw
36 31 0:6 / /sys/kernel/debug rw,nosuid,nodev,noexec,relatime - debugfs debugfs rw
37 31 0:25 / /sys/fs/fuse/connections rw,nosuid,nodev,noexec,relatime - fusectl fusectl rw
38 31 0:15 / /sys/fs/selinux rw,nosuid,nodev,noexec,relatime - selinuxfs selinuxfs rw
39 31 0:26 / /sys/fs/pstore rw,nosuid,nodev,noexec,relatime - pstore pstore rw
40 33 0:27 / /dev/shm rw,nosuid,noexec,relatime - tmpfs shm rw
EOF
root_contract_switched_root /run/run93/mounts /run/run93/mountinfo ||
	fail 'run-93 live post-cutover fixture (measured /proc/1/mountinfo, single sda13 root) rejected'
[ "$ROOT_CONTRACT_KIND" = ext4 ] && [ "$ROOT_CONTRACT_NODE" = /dev/block/sda13 ] &&
	[ "$ROOT_CONTRACT_SIZE" = 241421725696 ] && [ "$ROOT_CONTRACT_OPTS" = rw,relatime,norecovery ] ||
	fail 'run-93 live post-cutover fixture identity mismatch'
$BB printf '48 28 8:13 /vendor/firmware_mnt /vendor/firmware_mnt rw,relatime - ext4 /dev/block/sda13 rw,norecovery\n' >> /run/run93/mountinfo
root_contract_switched_root /run/run93/mounts /run/run93/mountinfo &&
	fail 'run-93 fixture with a hypothetical second 8:13 mount accepted'
$BB sed -i '$d' /run/run93/mountinfo
# Run 94 (#263): the full live /sys/class/block walk (146 devices, boot
# ec970efc, read-only capture) replaces the two-block fake before the
# switched-root replay; loop/ram devices carry no PARTNAME uevent entry,
# exactly like the live sysfs. Real node shape: regular root block node
# 0400, devnum 8:13, sysfs size 471526808 sectors, blockdev --getsize64
# 241421725696 (exact fit inside the default 33554432..241421725696
# bounds; the interactive self-post shell measured rc=1, no ROOT_CONTRACT_
# variable set, so the defaults apply).
for rc_dev in loop0 loop1 loop10 loop11 loop12 loop13 loop14 loop15 \
	loop2 loop3 loop4 loop5 loop6 loop7 loop8 loop9 \
	ram0 ram1 ram10 ram11 ram12 ram13 ram14 ram15 \
	ram2 ram3 ram4 ram5 ram6 ram7 ram8 ram9 \
	sda sda1 sda10 sda11 sda12 sda13 sda2 sda3 sda4 sda5 sda6 sda7 sda8 sda9 \
	sdb sdb1 sdb2 sdb3 sdb4 sdb5 \
	sdc sdc1 sdc2 sdc3 sdc4 sdc5 \
	sdd sdd1 sdd2 sdd3 \
	sde sde1 sde10 sde11 sde12 sde13 sde14 sde15 sde16 sde17 sde18 sde19 \
	sde2 sde20 sde21 sde22 sde23 sde24 sde25 sde26 sde27 sde28 sde29 \
	sde3 sde30 sde31 sde32 sde33 sde34 sde35 sde36 sde37 sde38 sde39 \
	sde4 sde40 sde41 sde42 sde43 sde44 sde45 sde46 sde47 sde48 sde49 \
	sde5 sde50 sde51 sde52 sde53 sde54 sde55 sde56 sde57 sde58 sde59 \
	sde6 sde60 sde61 sde62 sde63 sde64 sde65 sde66 sde67 sde68 sde69 \
	sde7 sde70 sde71 sde72 sde73 sde74 sde75 sde76 sde77 \
	sde8 sde9 sdf sdf1 sdf2 sdf3 sdf4 sdf5; do
	case "$rc_dev" in
		loop0) set_part loop0 - 7:0;;
		loop1) set_part loop1 - 7:8;;
		loop10) set_part loop10 - 7:80;;
		loop11) set_part loop11 - 7:88;;
		loop12) set_part loop12 - 7:96;;
		loop13) set_part loop13 - 7:104;;
		loop14) set_part loop14 - 7:112;;
		loop15) set_part loop15 - 7:120;;
		loop2) set_part loop2 - 7:16;;
		loop3) set_part loop3 - 7:24;;
		loop4) set_part loop4 - 7:32;;
		loop5) set_part loop5 - 7:40;;
		loop6) set_part loop6 - 7:48;;
		loop7) set_part loop7 - 7:56;;
		loop8) set_part loop8 - 7:64;;
		loop9) set_part loop9 - 7:72;;
		ram0) set_part ram0 - 1:0;;
		ram1) set_part ram1 - 1:1;;
		ram10) set_part ram10 - 1:10;;
		ram11) set_part ram11 - 1:11;;
		ram12) set_part ram12 - 1:12;;
		ram13) set_part ram13 - 1:13;;
		ram14) set_part ram14 - 1:14;;
		ram15) set_part ram15 - 1:15;;
		ram2) set_part ram2 - 1:2;;
		ram3) set_part ram3 - 1:3;;
		ram4) set_part ram4 - 1:4;;
		ram5) set_part ram5 - 1:5;;
		ram6) set_part ram6 - 1:6;;
		ram7) set_part ram7 - 1:7;;
		ram8) set_part ram8 - 1:8;;
		ram9) set_part ram9 - 1:9;;
		sda) set_part sda - 8:0;;
		sda1) set_part sda1 ssd 8:1;;
		sda10) set_part sda10 vbmeta_vendor_b 8:10;;
		sda11) set_part sda11 metadata 8:11;;
		sda12) set_part sda12 rawdump 8:12;;
		sda13) set_part sda13 userdata 8:13;;
		sda2) set_part sda2 persist 8:2;;
		sda3) set_part sda3 misc 8:3;;
		sda4) set_part sda4 keystore 8:4;;
		sda5) set_part sda5 frp 8:5;;
		sda6) set_part sda6 super 8:6;;
		sda7) set_part sda7 vbmeta_system_a 8:7;;
		sda8) set_part sda8 vbmeta_system_b 8:8;;
		sda9) set_part sda9 vbmeta_vendor_a 8:9;;
		sdb) set_part sdb - 8:16;;
		sdb1) set_part sdb1 xbl_a 8:17;;
		sdb2) set_part sdb2 xbl_config_a 8:18;;
		sdb3) set_part sdb3 multiimgqti_a 8:19;;
		sdb4) set_part sdb4 multiimgoem_a 8:20;;
		sdb5) set_part sdb5 apdp 8:21;;
		sdc) set_part sdc - 8:32;;
		sdc1) set_part sdc1 xbl_b 8:33;;
		sdc2) set_part sdc2 xbl_config_b 8:34;;
		sdc3) set_part sdc3 multiimgqti_b 8:35;;
		sdc4) set_part sdc4 multiimgoem_b 8:36;;
		sdc5) set_part sdc5 apdpb 8:37;;
		sdd) set_part sdd - 8:48;;
		sdd1) set_part sdd1 ALIGN_TO_128K_1 8:49;;
		sdd2) set_part sdd2 cdt 8:50;;
		sdd3) set_part sdd3 ddr 8:51;;
		sde) set_part sde - 8:64;;
		sde1) set_part sde1 uefi_a 8:65;;
		sde10) set_part sde10 keymaster_a 8:74;;
		sde11) set_part sde11 boot_a 8:75;;
		sde12) set_part sde12 devcfg_a 8:76;;
		sde13) set_part sde13 qupfw_a 8:77;;
		sde14) set_part sde14 vbmeta_a 8:78;;
		sde15) set_part sde15 dtbo_a 8:79;;
		sde16) set_part sde16 uefisecapp_a 259:0;;
		sde17) set_part sde17 imagefv_a 259:1;;
		sde18) set_part sde18 shrm_a 259:2;;
		sde19) set_part sde19 vm-bootsys_a 259:3;;
		sde2) set_part sde2 aop_a 8:66;;
		sde20) set_part sde20 cpucp_a 259:4;;
		sde21) set_part sde21 featenabler_a 259:5;;
		sde22) set_part sde22 vendor_boot_a 259:6;;
		sde23) set_part sde23 qmcs 259:7;;
		sde24) set_part sde24 qweslicstore_a 259:8;;
		sde25) set_part sde25 recovery_a 259:9;;
		sde26) set_part sde26 xbl_ramdump_a 259:10;;
		sde27) set_part sde27 init_boot_a 259:11;;
		sde28) set_part sde28 cpucp_dtb_a 259:12;;
		sde29) set_part sde29 pvmfw_a 259:13;;
		sde3) set_part sde3 aop_config_a 8:67;;
		sde30) set_part sde30 uefi_b 259:14;;
		sde31) set_part sde31 aop_b 259:15;;
		sde32) set_part sde32 aop_config_b 259:16;;
		sde33) set_part sde33 tz_b 259:17;;
		sde34) set_part sde34 hyp_b 259:18;;
		sde35) set_part sde35 modem_b 259:19;;
		sde36) set_part sde36 bluetooth_b 259:20;;
		sde37) set_part sde37 abl_b 259:21;;
		sde38) set_part sde38 dsp_b 259:22;;
		sde39) set_part sde39 keymaster_b 259:23;;
		sde4) set_part sde4 tz_a 8:68;;
		sde40) set_part sde40 boot_b 259:24;;
		sde41) set_part sde41 devcfg_b 259:25;;
		sde42) set_part sde42 qupfw_b 259:26;;
		sde43) set_part sde43 vbmeta_b 259:27;;
		sde44) set_part sde44 dtbo_b 259:28;;
		sde45) set_part sde45 uefisecapp_b 259:29;;
		sde46) set_part sde46 imagefv_b 259:30;;
		sde47) set_part sde47 shrm_b 259:31;;
		sde48) set_part sde48 vm-bootsys_b 259:32;;
		sde49) set_part sde49 cpucp_b 259:33;;
		sde5) set_part sde5 hyp_a 8:69;;
		sde50) set_part sde50 featenabler_b 259:34;;
		sde51) set_part sde51 vendor_boot_b 259:35;;
		sde52) set_part sde52 qweslicstore_b 259:36;;
		sde53) set_part sde53 recovery_b 259:37;;
		sde54) set_part sde54 xbl_ramdump_b 259:38;;
		sde55) set_part sde55 init_boot_b 259:39;;
		sde56) set_part sde56 cpucp_dtb_b 259:40;;
		sde57) set_part sde57 pvmfw_b 259:41;;
		sde58) set_part sde58 devinfo 259:42;;
		sde59) set_part sde59 toolsfv 259:43;;
		sde6) set_part sde6 modem_a 8:70;;
		sde60) set_part sde60 logfs 259:44;;
		sde61) set_part sde61 nt_log 259:45;;
		sde62) set_part sde62 nt_kmsg 259:46;;
		sde63) set_part sde63 nt_uefi 259:47;;
		sde64) set_part sde64 nt_reserve1 259:48;;
		sde65) set_part sde65 nt_reserve2 259:49;;
		sde66) set_part sde66 binfo 259:50;;
		sde67) set_part sde67 storsec 259:51;;
		sde68) set_part sde68 uefivarstore 259:52;;
		sde69) set_part sde69 secdata 259:53;;
		sde7) set_part sde7 bluetooth_a 8:71;;
		sde70) set_part sde70 vm-persist 259:54;;
		sde71) set_part sde71 mdcompress 259:55;;
		sde72) set_part sde72 connsec 259:56;;
		sde73) set_part sde73 tzsc 259:57;;
		sde74) set_part sde74 spunvm 259:58;;
		sde75) set_part sde75 xbl_sc_test_mode 259:59;;
		sde76) set_part sde76 xbl_sc_logs 259:60;;
		sde77) set_part sde77 dpm 259:61;;
		sde8) set_part sde8 abl_a 8:72;;
		sde9) set_part sde9 dsp_a 8:73;;
		sdf) set_part sdf - 8:80;;
		sdf1) set_part sdf1 ALIGN_TO_128K_2 8:81;;
		sdf2) set_part sdf2 modemst1 8:82;;
		sdf3) set_part sdf3 modemst2 8:83;;
		sdf4) set_part sdf4 fsg 8:84;;
		sdf5) set_part sdf5 fsc 8:85;;
	esac
done
$BB mkdir -p /run/run94
$BB cp /run/run93/mounts /run/run94/mounts
$BB sed "s/^28 1 $MAIN_NUMS /28 1 8:13 /" /run/run93/mountinfo > /run/run94/mountinfo
$BB rm /dev/block/sda13
$BB mknod -m 0400 /dev/block/sda13 b 8 13
$BB printf '471526808\n' > /sys/class/block/sda13/size
$BB cat > /run/run94/bb <<'EOF'
#!/bin/busybox sh
if [ "$1" = blockdev ] && [ "$2" = --getsize64 ] && [ "$3" = /dev/block/sda13 ]; then
	/bin/busybox printf '241421725696\n'
	exit 0
fi
exec /bin/busybox "$@"
EOF
$BB chmod 700 /run/run94/bb
( BB=/run/run94/bb
	root_contract_switched_root /run/run94/mounts /run/run94/mountinfo ||
		fail 'run-94 live block walk + live node inputs rejected by the unchanged contract'
	[ "$ROOT_CONTRACT_KIND" = ext4 ] && [ "$ROOT_CONTRACT_NODE" = /dev/block/sda13 ] &&
		[ "$ROOT_CONTRACT_SIZE" = 241421725696 ] &&
		[ "$ROOT_CONTRACT_OPTS" = rw,relatime,norecovery ] ||
		fail 'run-94 live-input fixture identity mismatch' ) || fail 'run-94 live-input replay failed'
$BB printf 'PARTNAME=userdata\n' > /sys/class/block/sda6/uevent
( BB=/run/run94/bb; root_contract_switched_root /run/run94/mounts /run/run94/mountinfo ) &&
	fail 'run-94 live block walk accepted with a second userdata PARTNAME'
$BB printf 'PARTNAME=super\n' > /sys/class/block/sda6/uevent
$BB rm /sys/class/block/sda13/size
$BB printf '%s\n' "$MAIN_NUMS" > /sys/class/block/sda13/dev
mk_bnode /dev/block/sda13 "$MAIN_NUMS"

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
