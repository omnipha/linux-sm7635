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
for applet in sh awk cat chmod cp cut dmesg grep id insmod ln ls mkdir mknod mount printf ps readlink rm rmmod sha256sum sleep stat timeout touch umount; do
	$BB ln -sf busybox "$R/bin/$applet"
done
$BB cp "$SCRIPT" "$R/radio.sh"
$BB mknod -m 666 "$R/dev/null" c 1 3
$BB mknod -m 666 "$R/dev/kmsg" c 1 11
$BB mkdir -p "$R/proc/sys/kernel/random" "$R/proc/1" "$R/mnt/vendor/etc/wifi/qca6750" "$R/mnt/vendor/firmware/wlan/qca_cld/qca6750"
$BB printf '%s\n' "$BOOT" > "$R/proc/sys/kernel/random/boot_id"
$BB ln -sf /bin/busybox "$R/proc/1/exe"
$BB touch "$R/run/keep"

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
$BB printf 'qrtr-published\n' > "$R/run/qrtr-services.status"
$BB printf 'rmtfs-published\n' > "$R/run/rmtfs.status"
$BB mkdir -p "$R/run/pmos/run" "$R/run/pmos/dev"
$BB printf 'tmpfs /run/pmos tmpfs rw 0 0\ntmpfs /run/pmos/run tmpfs rw 0 0\nerofs /vendor erofs ro 0 0\n' > "$R/proc/mounts"
$BB mknod -m 0600 "$R/dev/wlan" c 495 0

reject_stage prepare wrong-boot prepare
run_stage prepare
[ -f "$R/run/pmos/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini" ] || fail 'staged INI missing'
[ "$($BB readlink "$R/run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini")" = /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini ] || fail 'staged INI symlink'
[ "$($BB sha256sum "$R/run/pmos/run/radio-bringup/wpss-once" | $BB cut -d ' ' -f 1)" = "$HELPER_SHA" ] || fail 'staged helper hash'
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
$BB mv "$R/bin/busybox" "$R/bin/busybox.real"
$BB cat > "$R/bin/busybox" <<'WRAP'
#!/bin/busybox.real sh
BB=/bin/busybox.real
case "${1:-}" in
	ps) exec "$BB" cat /tmp/ps.txt;;
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
				*remoteproc2/state*) [ -r /vendor/firmware_mnt/image/modem.mdt ] || exit 1; "$BB" printf 'running\n' > /sys/class/remoteproc/remoteproc2/state; exit 0;;
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
$BB mkdir -p "$R/sys/bus/platform/devices/17110040.qcom,wcn6750/driver" "$R/sys/kernel/icnss"
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
$BB mv "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt" "$R/tmp/modem.mdt.hidden"
reject_stage modem "$BOOT" modem capture-ok
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed before firmware was reachable'
$BB mv "$R/tmp/modem.mdt.hidden" "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt"
run_stage modem capture-ok
[ -r "$R/vendor/firmware_mnt/image/modem.mdt" ] || fail 'modem firmware not bound before start'
[ "$($BB cat "$R/sys/class/remoteproc/remoteproc2/state")" = running ] || fail 'modem not running'
run_stage modem capture-ok
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc2/state"
reject_stage modem "$BOOT" modem capture-ok
$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc2/state"

run_stage wpss capture-ok
expect "$R/tmp/wpss.out" 'helper exit 10' 'wpss did not accept helper exit 10'
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
$BB printf 'pass: host-only radio bring-up stages, one-shot guards, helper exit 10, single reload and root-only scan verified\n'
