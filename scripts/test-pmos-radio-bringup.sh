#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$HERE/pmos-radio-bringup.sh"
if [ "${1:-}" != --inner ]; then
	[ -f "$SCRIPT" ] || exit 1
	sudo -n unshare --mount --pid --fork --mount-proc env HERE="$HERE" SCRIPT="$SCRIPT" /bin/busybox sh "$0" --inner
	exit 0
fi

BB=/bin/busybox
INI_SHA=57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4
KO_SHA=c2dbdcd119955b7212d61eeb00528b8b69012a3e7f9528ceb1738b6081ee6e0b
HELPER_SHA=fef7e5da780d59a02a558b912d30fccb905ceb3b4e6a964ed666d1897f3987d2
LEASE_SHA=86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896
NETWORKING_SHA=334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c
WPA_SERVICE_SHA=a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f
WPA_CONF_SHA=1600be060d3cdebb0663363f791fc1927ca1463f7a09e1f1f26b6e3ce390d1a1
RMTFS_SHA=d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd
RMTFS_BIN=${RMTFS_BIN:-$HOME/sm7635-build/out/rmtfs}
BOOT=11111111-2222-3333-4444-555555555555
fail() { $BB printf 'FAIL: %s\n' "$*" >&2; exit 1; }
expect() { $BB grep -q "$2" "$1" || { $BB cat "$1" >&2; fail "$3"; }; }
run_stage() { $BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" "$@" >"$R/tmp/$1.out" 2>&1 || { $BB cat "$R/tmp/$1.out" >&2; fail "$1"; }; }
reject_stage() {
	label=$1
	shift
	$BB chroot "$R" /bin/busybox sh /radio.sh "$@" >"$R/tmp/$label.out" 2>&1 && fail "$label accepted"
	expect "$R/tmp/$label.out" "$label:" "$label did not name its failure"
}

$BB mount --make-rprivate /
R=/tmp/radio-root
$BB mkdir -p "$R"
$BB mount -t tmpfs -o mode=0755,size=256m tmpfs "$R"
for d in bin sbin usr/bin usr/sbin etc dev run sys proc mnt vendor tmp; do
	$BB mkdir -p "$R/$d"
done
$BB cp /bin/busybox "$R/bin/busybox"
for applet in sh awk cat chmod cp cut dd dmesg grep id insmod ln ls mkdir mknod mount printf ps readlink rm rmmod sed sha256sum sleep stat timeout touch tr umount; do
	$BB ln -sf busybox "$R/bin/$applet"
done
$BB cp "$SCRIPT" "$R/radio.sh"
$BB mknod -m 666 "$R/dev/null" c 1 3
$BB mknod -m 666 "$R/dev/kmsg" c 1 11
$BB mkdir -p "$R/proc/sys/kernel/random" "$R/proc/1" "$R/mnt/vendor/etc/wifi/qca6750" "$R/mnt/vendor/firmware/wlan/qca_cld/qca6750"
$BB printf '%s\n' "$BOOT" > "$R/proc/sys/kernel/random/boot_id"
$BB ln -sf /bin/busybox "$R/proc/1/exe"
$BB touch "$R/run/keep"
$BB cp "$HERE/wlan-udhcpc-lease.sh" "$R/run/wlan-udhcpc-lease.sh"
[ "$($BB sha256sum "$R/run/wlan-udhcpc-lease.sh" | $BB cut -d ' ' -f 1)" = "$LEASE_SHA" ] || fail 'lease helper digest'

python3 -B - "$HERE/build-init-boot-psoc-hold-payload.py" "$INI_SHA" "$R/mnt/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini" "$HELPER_SHA" "$R/bin/wpss-once" "$KO_SHA" "$R/tmp/qca.ko" "$R/radio.sh" <<'PY'
import hashlib
import importlib.util
import pathlib
import sys

payload, ini_sha, ini_path, helper_sha, helper_path, ko_sha, ko_path, script_path = sys.argv[1:]
spec = importlib.util.spec_from_file_location('psoc_hold', pathlib.Path(payload))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
trigger = mod.expected_trigger()
assert hashlib.sha256(trigger).hexdigest() == helper_sha
pathlib.Path(helper_path).write_bytes(trigger)
pathlib.Path(helper_path).chmod(0o755)
ini = b'gDot11Mode=0\n'
ko = b'\x7fELF'
pathlib.Path(ini_path).write_bytes(ini)
pathlib.Path(ko_path).write_bytes(ko)
text = pathlib.Path(script_path).read_text()
assert ini_sha in text and ko_sha in text and helper_sha in text
text = text.replace(ini_sha, hashlib.sha256(ini).hexdigest())
text = text.replace(ko_sha, hashlib.sha256(ko).hexdigest())
pathlib.Path(script_path).write_text(text)
PY

$BB ln -s /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini "$R/mnt/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini"
$BB cp -a "$R/mnt/vendor/." "$R/vendor/"
for service in pd-mapper tqftpserv rmtfs; do
	$BB printf '%s: published QRTR service\n' "$service" > "$R/run/$service.log"
done
$BB printf 'rmtfs: mapped stock UIO /dev/uio0 address 0x1000 size 0x2000\nrmtfs: published QRTR service 14 version 1 instance 0\n' > "$R/run/rmtfs.log"
$BB printf 'qrtr-published\n' > "$R/run/qrtr-services.status"
$BB printf 'rmtfs-published\n' > "$R/run/rmtfs.status"
if [ -f "$RMTFS_BIN" ] && [ "$($BB sha256sum "$RMTFS_BIN" | $BB cut -d ' ' -f 1)" = "$RMTFS_SHA" ]; then
	$BB cp "$RMTFS_BIN" "$R/bin/rmtfs"
else
	$BB printf '\177ELFmock-rmtfs\n' > "$R/bin/rmtfs"
	rmtfs_mock_sha=$($BB sha256sum "$R/bin/rmtfs" | $BB cut -d ' ' -f 1)
	$BB sed -i "s/$RMTFS_SHA/$rmtfs_mock_sha/" "$R/radio.sh"
fi
$BB chmod 755 "$R/bin/rmtfs"
$BB mkdir -p "$R/proc/628" "$R/sys/class/uio/uio0/maps/map0" "$R/sys/class/block/sdf2" "$R/sys/class/block/sdf3" "$R/dev/block" "$R/boot"
$BB printf 'rmtfs\n' > "$R/proc/628/comm"
$BB ln -sf /bin/rmtfs "$R/proc/628/exe"
$BB ln -sf / "$R/proc/628/root"
$BB printf '7f000000-7f002000 rw-s 00000000 00:00 0 /dev/uio0\n' > "$R/proc/628/maps"
$BB printf 'rmtfs\n' > "$R/sys/class/uio/uio0/name"
$BB printf '242:0\n' > "$R/sys/class/uio/uio0/dev"
$BB printf '1000\n' > "$R/sys/class/uio/uio0/maps/map0/addr"
$BB printf '2000\n' > "$R/sys/class/uio/uio0/maps/map0/size"
$BB mknod -m 0600 "$R/dev/uio0" c 242 0
$BB printf 'PARTNAME=modemst1\n' > "$R/sys/class/block/sdf2/uevent"
$BB printf 'PARTNAME=modemst2\n' > "$R/sys/class/block/sdf3/uevent"
$BB printf '259:18\n' > "$R/sys/class/block/sdf2/dev"
$BB printf '259:19\n' > "$R/sys/class/block/sdf3/dev"
$BB mknod -m 0400 "$R/dev/block/sdf2" b 259 18
$BB mknod -m 0400 "$R/dev/block/sdf3" b 259 19
$BB printf '%512s\n' '' > "$R/tmp/modemst.img"
$BB ln -s /dev/block/sdf2 "$R/boot/modemst1"
$BB ln -s /dev/block/sdf3 "$R/boot/modemst2"
$BB mkdir -p "$R/run/pmos/run" "$R/run/pmos/dev"
$BB printf 'tmpfs /run/pmos tmpfs rw 0 0\ntmpfs /run/pmos/run tmpfs rw 0 0\nerofs /vendor erofs ro 0 0\n' > "$R/proc/mounts"
$BB mknod -m 0600 "$R/dev/wlan" c 495 0

$BB mv "$R/bin/busybox" "$R/bin/busybox.real"
$BB cat > "$R/bin/busybox" <<'WRAP'
#!/bin/busybox.real sh
BB=/bin/busybox.real
case "${1:-}" in
	ps) exec "$BB" cat /tmp/ps.txt;;
	dd)
		case "${2:-}" in
			if=*/dev/block/sdf[23])
				node=${2#if=}
				[ -b "$node" ] && [ -r /tmp/modemst.img ] || exit 1
				exit 0
				;;
		esac
		exec "$BB" "$@"
		;;
	dmesg) exec "$BB" cat /tmp/dmesg.txt;;
	sleep) exit 0;;
	mount)
		if [ "${2:-}" = /vendor/firmware_mnt ] || [ "${4:-}" = /vendor/firmware_mnt ]; then
			"$BB" cp -a /proc/358/root/vendor/firmware_mnt/. /vendor/firmware_mnt/
			"$BB" grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts ||
				"$BB" printf '/dev/block/sde6 /vendor/firmware_mnt vfat ro,relatime 0 0\n' >> /proc/mounts
			exit 0
		fi
		exec "$BB" mount "$@"
		;;
	insmod)
		"$BB" printf 'insmod %s\n' "$2" >> /tmp/mod.log
		"$BB" mkdir -p /sys/module/qca_cld3_qca6750
		if [ -f /tmp/reload-ready ]; then
			"$BB" mkdir -p /sys/class/net/wlan0 /sys/class/ieee80211/phy0
			"$BB" printf '0x1002\n' > /sys/class/net/wlan0/flags
		fi
		exit 0
		;;
	rmmod)
		"$BB" printf 'rmmod %s\n' "$2" >> /tmp/mod.log
		"$BB" rm -rf /sys/module/qca_cld3_qca6750
		"$BB" touch /tmp/reload-ready
		exit 0
		;;
	timeout)
		shift 4
		if [ "${1:-}" = /bin/busybox ] && [ "${2:-}" = sh ] && [ "${3:-}" = -c ]; then
			case "$4" in
				*remoteproc2/state*) [ -r /vendor/firmware_mnt/image/modem.mdt ] && [ -c /proc/628/root/dev/uio0 ] && [ -b /proc/628/root/dev/block/sdf2 ] && [ -b /proc/628/root/dev/block/sdf3 ] && [ -L /proc/628/root/boot/modemst1 ] && [ -L /proc/628/root/boot/modemst2 ] || exit 1; "$BB" printf 'running\n' > /sys/class/remoteproc/remoteproc2/state; exit 0;;
				*wpss_boot*) [ -r /vendor/firmware_mnt/image/qca6750/wpss.mdt ] || exit 1; "$BB" printf 'running\n' > /sys/class/remoteproc/remoteproc3/state; exit 0;;
				*'/dev/wlan'*) exit 124;;
			esac
		fi
		exec "$@"
		;;
esac
exec "$BB" "$@"
WRAP
$BB chmod 755 "$R/bin/busybox"
reject_stage prepare wrong-boot prepare
run_stage prepare
[ -f "$R/run/pmos/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini" ] || fail 'staged INI missing'
[ "$($BB readlink "$R/run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini")" = /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini ] || fail 'staged INI symlink'
[ "$($BB sha256sum "$R/run/pmos/run/radio-bringup/wpss-once" | $BB cut -d ' ' -f 1)" = "$HELPER_SHA" ] || fail 'staged helper hash'
[ "$($BB sha256sum "$R/run/pmos/run/radio-bringup/wlan-udhcpc-lease.sh" | $BB cut -d ' ' -f 1)" = "$LEASE_SHA" ] || fail 'staged lease helper hash'
[ -c "$R/run/pmos/dev/wlan" ] && [ "$($BB stat -c '%t:%T' "$R/run/pmos/dev/wlan")" = '1ef:0' ] || fail 'copied /dev/wlan node'
reject_stage prepare "$BOOT" prepare
$BB rm -r "$R/run/pmos/vendor" "$R/run/pmos/run/radio-bringup" "$R/run/pmos/dev/wlan"
$BB printf 'corrupt\n' > "$R/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini"
reject_stage prepare "$BOOT" prepare
$BB printf 'gDot11Mode=0\n' > "$R/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini"
run_stage prepare

$BB cp -a "$R/run/pmos/vendor" "$R/vendor-switched"
$BB rm -r "$R/vendor"
$BB mv "$R/vendor-switched" "$R/vendor"
$BB cp -a "$R/run/pmos/run/." "$R/run/"
[ "$($BB stat -c '%t:%T' "$R/run/pmos/dev/wlan")" = "$($BB stat -c '%t:%T' "$R/dev/wlan")" ] || fail 'guest wlan node differs'
$BB printf 'ID="postmarketos"\n' > "$R/etc/os-release"
$BB mkdir -p "$R/run/openrc" "$R/run/pid1-guard" "$R/sys/class/remoteproc/remoteproc2" "$R/sys/class/remoteproc/remoteproc3" "$R/sys/class/net" "$R/sys/class/ieee80211" "$R/sys/class/wlan/wlan" "$R/sys/module"
$BB printf 'default\n' > "$R/run/openrc/softlevel"
$BB printf '%s\n' "$BOOT" > "$R/run/pid1-guard/accepted"
$BB printf 'tmpfs / tmpfs rw 0 0\n' > "$R/proc/1/mounts"
$BB printf '#!/bin/busybox sh\nexit 0\n' > "$R/sbin/rc-service"
$BB chmod 755 "$R/sbin/rc-service"
$BB printf '4080000.remoteproc-mss\n' > "$R/sys/class/remoteproc/remoteproc2/name"
$BB printf '9bb00000.remoteproc-wpss\n' > "$R/sys/class/remoteproc/remoteproc3/name"
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc2/state"
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc3/state"
$BB mkdir -p "$R/proc/358/root/mnt/vendor_dlkm/lib/modules" "$R/proc/358/root/vendor/etc/wifi/qca6750" "$R/proc/358/root/vendor/firmware_mnt/image/qca6750"
$BB cp "$R/tmp/qca.ko" "$R/proc/358/root/mnt/vendor_dlkm/lib/modules/qca_cld3_qca6750.ko"
$BB cp "$R/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini" "$R/proc/358/root/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini"
$BB printf 'fw\n' > "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt"
for part in mdt b00 b01 b02 b03 b04 b05 b06 b07 b08 b09 b10 b12; do
	$BB printf 'fw\n' > "$R/proc/358/root/vendor/firmware_mnt/image/qca6750/wpss.$part"
done
$BB printf 'pd-mapper\ntqftpserv\nrmtfs\n' > "$R/tmp/ps.txt"
$BB printf 'capture-ok\nicnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB mkdir -p "$R/sys/bus/platform/devices/17110040.qcom,wcn6750/driver" "$R/sys/kernel/icnss" "$R/sys/class/wlan/wlan"
$BB touch "$R/sys/kernel/icnss/wpss_boot"
$BB cat > "$R/sbin/ip" <<'IP'
#!/bin/busybox.real sh
[ "$*" = "link set wlan0 up" ] || exit 1
/bin/busybox.real printf '0x1003\n' > /sys/class/net/wlan0/flags
IP
$BB cat > "$R/usr/sbin/iw" <<'IW'
#!/bin/busybox.real sh
[ "$*" = "dev wlan0 scan" ] || exit 1
/bin/busybox.real printf 'BSS 02:00:00:00:00:01(on wlan0)\n\tfreq: 2412\nBSS 02:00:00:00:00:02(on wlan0)\n\tfreq: 5180\n'
IW
$BB chmod 755 "$R/sbin/ip" "$R/usr/sbin/iw"

reject_stage modem "$BOOT" modem
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc2/state"
reject_stage modem "$BOOT" modem missing-marker
$BB mv "$R/sys/class/uio/uio0/name" "$R/tmp/uio-name.hidden"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'kernel sharedmem UIO is not the rmtfs client' 'missing UIO reason'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed with the sharedmem UIO absent'
$BB mv "$R/tmp/uio-name.hidden" "$R/sys/class/uio/uio0/name"
$BB mv "$R/run/radio-bringup/rmtfs.pid" "$R/tmp/rmtfs.pid.hidden"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'expected exactly one pinned rmtfs process' 'copied status marker accepted without prepared rmtfs'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed without the prepared rmtfs process identity'
$BB mv "$R/tmp/rmtfs.pid.hidden" "$R/run/radio-bringup/rmtfs.pid"
$BB mv "$R/run/radio-bringup/rmtfs.log" "$R/tmp/rmtfs.log.hidden"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'rmtfs did not log the UIO map and QRTR publish' 'missing rmtfs publish log reason'
$BB mv "$R/tmp/rmtfs.log.hidden" "$R/run/radio-bringup/rmtfs.log"
$BB mv "$R/proc/628/maps" "$R/tmp/rmtfs.maps.hidden"
$BB printf '' > "$R/proc/628/maps"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'rmtfs does not hold the mapped sharedmem UIO' 'missing UIO mapping reason'
$BB mv "$R/tmp/rmtfs.maps.hidden" "$R/proc/628/maps"
$BB printf 'PARTNAME=other\n' > "$R/sys/class/block/sdf3/uevent"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'modemst2 PARTNAME changed' 'wrong backing partition reason'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed with the wrong modemst backing'
$BB printf 'PARTNAME=modemst2\n' > "$R/sys/class/block/sdf3/uevent"
$BB rm "$R/tmp/modemst.img"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'modemst1 backing node is not readable' 'unreadable backing store reason'
$BB printf '%512s\n' '' > "$R/tmp/modemst.img"
$BB rm "$R/proc/628/root"
$BB mkdir -p "$R/proc/628/root/dev/block" "$R/proc/628/root/boot" "$R/proc/628/root/run"
$BB cp -a "$R/dev/uio0" "$R/proc/628/root/dev/uio0"
$BB cp -a "$R/dev/block/sdf2" "$R/proc/628/root/dev/block/sdf2"
$BB cp -a "$R/dev/block/sdf3" "$R/proc/628/root/dev/block/sdf3"
$BB cp -a "$R/boot/modemst1" "$R/proc/628/root/boot/modemst1"
$BB cp -a "$R/boot/modemst2" "$R/proc/628/root/boot/modemst2"
$BB mv "$R/proc/628/exe" "$R/tmp/rmtfs.exe.hidden"
$BB ln -s /bin/busybox.real "$R/proc/628/exe"
reject_stage modem "$BOOT" modem capture-ok
expect "$R/tmp/modem.out" 'expected exactly one pinned rmtfs process' 'non-pinned rmtfs reason'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed against a non-pinned rmtfs process'
$BB rm "$R/proc/628/exe"
$BB mv "$R/tmp/rmtfs.exe.hidden" "$R/proc/628/exe"
$BB mv "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt" "$R/tmp/modem.mdt.hidden"
reject_stage modem "$BOOT" modem capture-ok
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed before firmware was reachable'
$BB mv "$R/tmp/modem.mdt.hidden" "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt"
$BB rm "$R/proc/628/root/boot/modemst1" "$R/proc/628/root/boot/modemst2" "$R/proc/628/root/dev/uio0" "$R/proc/628/root/dev/block/sdf2"
run_stage modem capture-ok
expect "$R/tmp/modem.out" 'restored backing links: uio0 sdf2 modemst1 modemst2' 'cutover-deleted rmtfs paths not restored'
[ -c "$R/proc/628/root/dev/uio0" ] && [ -b "$R/proc/628/root/dev/block/sdf2" ] && [ -b "$R/proc/628/root/dev/block/sdf3" ] &&
	[ "$($BB readlink "$R/proc/628/root/boot/modemst1")" = /dev/block/sdf2 ] &&
	[ "$($BB readlink "$R/proc/628/root/boot/modemst2")" = /dev/block/sdf3 ] || fail 'rmtfs backing links not restored before start'
[ -r "$R/vendor/firmware_mnt/image/modem.mdt" ] || fail 'modem firmware not bound before start'
[ "$($BB cat "$R/sys/class/remoteproc/remoteproc2/state")" = running ] || fail 'modem not running'
run_stage modem capture-ok
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc2/state"
reject_stage modem "$BOOT" modem capture-ok
$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc2/state"

$BB rm "$R/dev/wlan"
reject_stage wpss "$BOOT" wpss capture-ok
expect "$R/tmp/wpss.out" 'no /dev/wlan and no valid live wlan class device' 'missing wlan class device accepted'
$BB printf '495:0\n' > "$R/sys/class/wlan/wlan/dev"
$BB printf 'Character devices:\n 496 qcwlanstate\nBlock devices:\n 495 qcwlanstate\n' > "$R/proc/devices"
reject_stage wpss "$BOOT" wpss capture-ok
expect "$R/tmp/wpss.out" 'wlan class major does not match one character qcwlanstate' 'block or mismatched qcwlanstate major accepted'
[ ! -e "$R/dev/wlan" ] && [ ! -e "$R/run/radio-bringup/wpss.attempted" ] || fail 'wpss armed or left node on qcwlanstate major mismatch'
$BB printf 'Character devices:\n 495 qcwlanstate\nBlock devices:\n' > "$R/proc/devices"
$BB touch "$R/dev/wlan"
reject_stage wpss "$BOOT" wpss capture-ok
expect "$R/tmp/wpss.out" '/dev/wlan is not a character node' 'non-character /dev/wlan accepted'
[ ! -e "$R/run/radio-bringup/wpss.attempted" ] || fail 'wpss armed with non-character /dev/wlan'
$BB rm "$R/dev/wlan"
$BB mknod -m 0600 "$R/dev/wlan" c 494 0
reject_stage wpss "$BOOT" wpss capture-ok
expect "$R/tmp/wpss.out" 'existing /dev/wlan differs from live wlan class device or is not root-only' 'mismatched copied /dev/wlan accepted'
[ ! -e "$R/run/radio-bringup/wpss.attempted" ] || fail 'wpss armed with a mismatched /dev/wlan node'
$BB rm "$R/dev/wlan"
run_stage wpss capture-ok
expect "$R/tmp/wpss.out" 'derived /dev/wlan character 495:0' 'wpss did not derive /dev/wlan from class device'
expect "$R/tmp/wpss.out" 'helper exit 10' 'wpss did not accept helper exit 10'
[ -c "$R/dev/wlan" ] && [ "$($BB stat -c '%t:%T:%a' "$R/dev/wlan")" = '1ef:0:600' ] || fail 'derived /dev/wlan node invalid'
[ "$($BB cat "$R/sys/class/remoteproc/remoteproc3/state")" = running ] || fail 'wpss not running'
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc3/state"
reject_stage wpss "$BOOT" wpss capture-ok
$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc3/state"

run_stage driver capture-ok
[ "$($BB wc -l < "$R/tmp/mod.log")" -eq 3 ] || fail 'driver did not run insmod -> rmmod -> insmod'
[ -d "$R/sys/class/net/wlan0" ] && [ -d "$R/sys/class/ieee80211/phy0" ] || fail 'wlan0/phy0 not registered'
$BB rm -rf "$R/sys/class/net/wlan0"
reject_stage driver "$BOOT" driver capture-ok
$BB mkdir -p "$R/sys/class/net/wlan0"
$BB printf '0x1002\n' > "$R/sys/class/net/wlan0/flags"

run_stage scan
expect "$R/tmp/scan.out" 'BSS count 2' 'scan count not reported'
[ "$($BB stat -c '%a' "$R/run/radio-bringup/scan.raw")" = 600 ] || fail 'scan output not root-only'
reject_stage scan "$BOOT" scan

$BB mkdir -p "$R/etc/init.d" "$R/etc/conf.d" "$R/etc/network" "$R/etc/wpa_supplicant" "$R/etc/runlevels/sysinit" "$R/etc/runlevels/boot" "$R/etc/runlevels/default" "$R/etc/runlevels/nonetwork" "$R/etc/runlevels/shutdown" "$R/proc/452" "$R/proc/net"
$BB printf '#!/sbin/openrc-run\n' > "$R/etc/init.d/networking"
$BB printf '#!/sbin/openrc-run\nsupervisor=supervise-daemon\n' > "$R/etc/init.d/wpa_supplicant"
$BB printf 'wpa_supplicant_args=""\n' > "$R/etc/conf.d/wpa_supplicant"
net_sha=$($BB sha256sum "$R/etc/init.d/networking" | $BB cut -d ' ' -f 1)
wpa_sha=$($BB sha256sum "$R/etc/init.d/wpa_supplicant" | $BB cut -d ' ' -f 1)
conf_sha=$($BB sha256sum "$R/etc/conf.d/wpa_supplicant" | $BB cut -d ' ' -f 1)
$BB sed -i "s/$NETWORKING_SHA/$net_sha/; s/$WPA_SERVICE_SHA/$wpa_sha/; s/$WPA_CONF_SHA/$conf_sha/" "$R/radio.sh"
$BB cp "$HERE/wlan-udhcpc-lease.sh" "$R/run/radio-bringup/wlan-udhcpc-lease.sh"
$BB chmod 700 "$R/run/radio-bringup/wlan-udhcpc-lease.sh"
$BB ln -s /etc/init.d/local "$R/etc/runlevels/default/local"
$BB ln -s /sbin/ip "$R/bin/ip-bad"
$BB cat > "$R/sbin/rc-service" <<'RC'
#!/bin/busybox sh
case "$1 $2 $3" in
	'local status ') exit 0;;
	'networking status '|'wpa_supplicant status ') [ -f "/run/radio-bringup/$1.started" ];;
	'-D wpa_supplicant start')
		/bin/busybox printf 'wpa\n' >> /run/radio-bringup/order
		[ ! -e /run/radio-bringup/wpa-fail ] || exit 1
		/bin/busybox touch /run/radio-bringup/wpa_supplicant.started;;
	'-D networking start')
		/bin/busybox printf 'net\n' >> /run/radio-bringup/order
		[ -f /etc/wpa_supplicant/wpa_supplicant.conf ] && [ -s /etc/network/interfaces ] || exit 1
		/bin/busybox touch /run/radio-bringup/networking.started;;
	*) exit 1;;
esac
RC
$BB chmod 755 "$R/sbin/rc-service"
$BB cat > "$R/sbin/ifquery" <<'IFQUERY'
#!/bin/busybox sh
if [ "$*" = '-i /etc/network/interfaces --list -a' ]; then
	/bin/busybox printf 'lo\nwlan0\n'
else
	exit 1
fi
IFQUERY
$BB chmod 755 "$R/sbin/ifquery"
$BB printf '%s\0' dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid > "$R/proc/452/cmdline"
$BB ln -s / "$R/proc/452/root"
$BB printf '452\n' > "$R/run/dropbear-session.pid"
$BB printf '  0: 022A10AC:08AE 00000000:0000 0A 0 0 0 0 0 0 0\n' > "$R/proc/net/tcp"

reject_stage services "$BOOT" services missing-marker
reject_stage services "$BOOT" services capture-ok
expect "$R/tmp/services.out" 'OpenRC or /sbin/ip prerequisites changed' 'missing service prerequisites reason'
$BB rm "$R/bin/ip-bad"
$BB touch "$R/sbin/wpa_supplicant" "$R/sbin/ifup"
$BB chmod 755 "$R/sbin/wpa_supplicant" "$R/sbin/ifup"
for service in sshd udev tmpfs; do
	$BB ln -s "/etc/init.d/$service" "$R/etc/runlevels/default/$service"
	reject_stage services "$BOOT" services capture-ok
	expect "$R/tmp/services.out" 'another OpenRC service enabled' "pre-enabled $service accepted"
	$BB rm "$R/etc/runlevels/default/$service"
done
$BB printf 'wpa_supplicant_args="-f /run/log"\n' > "$R/etc/conf.d/wpa_supplicant"
reject_stage services "$BOOT" services capture-ok
expect "$R/tmp/services.out" 'unexpected supplicant arguments; no -f supported' 'supplicant -f accepted'
$BB printf 'wpa_supplicant_args=""\n' > "$R/etc/conf.d/wpa_supplicant"
$BB ln -s /sbin/ip "$R/bin/ip"
reject_stage services "$BOOT" services capture-ok
expect "$R/tmp/services.out" 'OpenRC or /sbin/ip prerequisites changed' 'bin/ip not refused'
$BB rm "$R/bin/ip"
$BB mv "$R/run/dropbear-session.pid" "$R/tmp/ssh-pid.hidden"
reject_stage services "$BOOT" services capture-ok
expect "$R/tmp/services.out" 'guest :2222 pidfile absent' 'missing guest SSH accepted'
$BB mv "$R/tmp/ssh-pid.hidden" "$R/run/dropbear-session.pid"
$BB printf 'fatal error received: mock\n' >> "$R/tmp/dmesg.txt"
reject_stage services "$BOOT" services capture-ok
expect "$R/tmp/services.out" 'radio fatal in this boot' 'modem fatal accepted'
$BB printf 'capture-ok\nicnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services capture-ok </dev/null > "$R/tmp/missing-profile.out" 2>&1 && fail 'missing profile accepted'
expect "$R/tmp/missing-profile.out" 'profile missing or not root-only' 'missing profile reason'
[ ! -e "$R/etc/wpa_supplicant/wpa_supplicant.conf" ] && [ ! -e "$R/etc/runlevels/default/networking" ] || fail 'missing profile enabled services'
$BB touch "$R/run/radio-bringup/wpa-fail"
$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="synthetic"\npsk="synthetic-only"\n}\n' | $BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services capture-ok > "$R/tmp/wpa-fail.out" 2>&1 && fail 'failed wpa service accepted'
expect "$R/tmp/wpa-fail.out" 'wpa_supplicant first service error' 'first failed service not reported'
[ "$($BB cat "$R/run/radio-bringup/order")" = wpa ] && [ ! -e "$R/run/radio-bringup/networking.started" ] || fail 'networking attempted after wpa failure'
$BB rm "$R/run/radio-bringup/wpa-fail" "$R/run/radio-bringup/order" "$R/run/radio-bringup/services.attempted" "$R/etc/network/interfaces" "$R/etc/wpa_supplicant/wpa_supplicant.conf" "$R/etc/conf.d/networking" "$R/bin/run-parts" "$R/sbin/udhcpc" "$R/run/radio-bringup/ifquery-wlan" "$R/run/radio-bringup/lease-wrapper.sh" "$R/etc/runlevels/default/wpa_supplicant" "$R/etc/runlevels/default/networking"
$BB printf 'wpa_supplicant_args=""\n' > "$R/etc/conf.d/wpa_supplicant"
$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="synthetic"\npsk="synthetic-only"\n}\n' | $BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services capture-ok > "$R/tmp/services-ok.out" 2>&1 || { $BB cat "$R/tmp/services-ok.out" >&2; fail 'services stage failed'; }
expect "$R/tmp/services-ok.out" 'OpenRC wpa_supplicant then networking started' 'services stage summary missing'
[ "$($BB cat "$R/run/radio-bringup/order")" = 'wpa
net' ] || fail 'services did not start wpa_supplicant then networking'
[ "$($BB stat -c '%u:%a' "$R/etc/wpa_supplicant/wpa_supplicant.conf")" = 0:600 ] &&
	[ "$($BB stat -c '%u:%a' "$R/etc/network/interfaces")" = 0:600 ] &&
	[ "$($BB stat -c '%u:%a' "$R/etc/conf.d/networking")" = 0:600 ] || fail 'service config permissions'
$BB grep -q '^wpa_supplicant_if="wlan0"$' "$R/etc/conf.d/wpa_supplicant" || fail 'supplicant not pinned to wlan0'
$BB grep -q '^IP_CMD=/sbin/ip$' "$R/run/radio-bringup/lease-wrapper.sh" &&
	$BB grep -q 'dhcp-script /run/radio-bringup/lease-wrapper.sh' "$R/etc/network/interfaces" &&
	[ "$($BB stat -c '%u:%a' "$R/run/radio-bringup/lease-wrapper.sh")" = 0:700 ] || fail 'IP_CMD=/sbin/ip lease wrapper missing'
[ "$($BB find "$R/etc/runlevels" -type l | $BB sort)" = "$R/etc/runlevels/default/local
$R/etc/runlevels/default/networking
$R/etc/runlevels/default/wpa_supplicant" ] || fail 'unexpected enabled OpenRC runlevel entries'
reject_stage services "$BOOT" services capture-ok
$BB printf 'pass: host-only radio bring-up stages, one-shot guards, fail-closed /dev/wlan derivation, helper exit 10, single reload, root-only scan, pinned lease-helper staging and OpenRC wpa_supplicant/networking stage verified\n'
