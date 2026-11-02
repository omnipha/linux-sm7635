#!/bin/sh
set -eu
if [ "${1:-}" != --inner ]; then
	[ "$#" -eq 0 ] || exit 1
	sudo -n unshare --mount --pid --fork --mount-proc env CONTRACT="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/pmos-root-contract.sh" /bin/busybox sh "$0" --inner
	exit 0
fi
BB=/bin/busybox
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
$BB mount --make-rprivate /
root=/tmp/gate-evidence
$BB mkdir -p "$root"
$BB mount -t tmpfs -o mode=0700,size=4m tmpfs "$root"
$BB mkdir "$root/run" "$root/proc" "$root/bin" "$root/dev"
$BB cp /bin/busybox "$root/bin/busybox"
$BB mknod -m 666 "$root/dev/null" c 1 3
$BB mount -t tmpfs -o mode=0700,size=1m tmpfs "$root/run"
$BB mount -t proc proc "$root/proc"
boot=11111111-2222-3333-4444-555555555555
$BB printf '%s\n' "$boot" > "$root/run/current-boot"
panel="usb-init: pre-SSH panel node=boe card0=1 boot $boot"
record="boot $boot
pmos-self-stage: diagnostic hold and :22 verified on boot $boot
$panel
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
run_contract() {
	$BB chroot "$root" /bin/busybox sh -eu -c '
		BB=/bin/busybox
		PMOS_ROOT_CONTRACT=/contract
		export PMOS_ROOT_CONTRACT
		. /contract
		boot_record_root() { ROOT_CONTRACT_OPTS=rw; return 0; }
		boot_record_id() { br_boot=$($BB cat /run/current-boot); }
		[ "$("$BB" stat -c %u /)" = 0 ]
		[ "$("$BB" stat -c %u /contract)" = 0 ]
		[ "$("$BB" stat -c %u /.omnipha-boot-record)" = 0 ]
		"$@"
	' contract "$@"
}
$BB cp "$CONTRACT" "$root/contract"
$BB chmod 700 "$root/contract"
$BB printf '%s\n' "$record" > "$root/.omnipha-boot-record"
$BB chmod 600 "$root/.omnipha-boot-record"
$BB printf '%s\n' "$panel" > "$root/run/pmos-pre-ssh-panel.record"
$BB chmod 600 "$root/run/pmos-pre-ssh-panel.record"
before=$($BB cat "$root/.omnipha-boot-record")
if run_contract boot_record_append / 'pmos-self-post: FAIL: success-gate association before-publication refused: wlan0 is not associated (uptime 250.00)'; then
	fail 'real contract appended a failure after the terminal success line'
fi
[ "$($BB cat "$root/.omnipha-boot-record")" = "$before" ] || fail 'refused failure changed the persistent record'
run_contract boot_record_verify / 'pmos-self-post: post-cutover PID 1 on boot 11111111-2222-3333-4444-555555555555; guard identity check passed; pid1 identity check passed' || fail 'real contract refused its valid success record'
$BB rm "$root/run/pmos-pre-ssh-panel.record"
if run_contract boot_record_append / 'pmos-self-post: FAIL: success-gate association before-publication refused: wlan0 is not associated (uptime 250.00)'; then
	fail 'missing panel record allowed a post-success failure'
fi
[ "$($BB cat "$root/.omnipha-boot-record")" = "$before" ] || fail 'missing panel record changed the record'
printf 'pass: real installed boot-record contract verifies success but refuses later gate failure evidence; no image, device or partition\n'
