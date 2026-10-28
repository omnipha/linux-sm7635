#!/bin/busybox sh
set -eu

BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
STATE=/run/radio-bringup
INI=etc/wifi/qca6750/WCNSS_qcom_cfg.ini
INI_SHA=57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4
KO=mnt/vendor_dlkm/lib/modules/qca_cld3_qca6750.ko
KO_SHA=c2dbdcd119955b7212d61eeb00528b8b69012a3e7f9528ceb1738b6081ee6e0b
HELPER_SHA=fef7e5da780d59a02a558b912d30fccb905ceb3b4e6a964ed666d1897f3987d2
MSS=/sys/class/remoteproc/remoteproc2
WPSS=/sys/class/remoteproc/remoteproc3

fail() { $BB printf 'radio-bringup: FAIL %s: %s\n' "$stage" "$*" >&2; exit 1; }
report() { $BB printf 'radio-bringup: %s\n' "$*" >&2; }
hash() { $BB sha256sum "$1" 2>/dev/null | $BB cut -d ' ' -f 1; }
state() { $BB timeout -k 1 2 $BB cat "$1/state" 2>/dev/null; }

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || { $BB printf 'usage: BOOT_ID prepare|modem|wpss|driver|scan|all [CAPTURE_MARKER]\n' >&2; exit 2; }
boot=$1
stage=$2
marker=${3:-}
case "$stage" in prepare|modem|wpss|driver|scan|all) :;; *) fail 'unknown stage';; esac
[ "$($BB cat /proc/sys/kernel/random/boot_id)" = "$boot" ] || fail 'boot ID mismatch'
[ -f /run/keep ] && [ ! -L /run/keep ] || fail 'diagnostic or guest hold absent'
[ "$($BB id -u)" = 0 ] || fail 'not root'

if [ "$stage" = prepare ]; then
	$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox || fail 'PID 1 is not the diagnostic busybox init'
	[ -d /run/pmos/run ] && [ ! -L /run/pmos/run ] &&
		$BB awk '$2 == "/run/pmos" && $3 == "tmpfs" {n++} END {exit(n != 1)}' /proc/mounts &&
		$BB awk '$2 == "/run/pmos/run" && $3 == "tmpfs" {n++} END {exit(n != 1)}' /proc/mounts ||
		fail 'staged postmarketOS tmpfs not ready before cutover'
	[ ! -e /run/pmos/vendor ] && [ ! -L /run/pmos/vendor ] || fail 'guest vendor path already exists'
	[ -f "/vendor/$INI" ] && [ ! -L /vendor ] &&
		$BB awk '$2 == "/vendor" && $4 ~ /(^|,)ro(,|$)/ {n++} END {exit(n < 1)}' /proc/mounts || fail 'stock vendor_a not bound read-only at /vendor'
	[ "$(hash "/vendor/$INI")" = "$INI_SHA" ] || fail 'stock INI digest mismatch'
	[ -f /bin/wpss-once ] && [ ! -L /bin/wpss-once ] && [ "$(hash /bin/wpss-once)" = "$HELPER_SHA" ] || fail 'diagnostic one-shot helper digest mismatch'
	for service in pd-mapper tqftpserv rmtfs; do
		[ -f "/run/$service.log" ] && $BB grep -q "$service: published QRTR service" "/run/$service.log" || fail "$service has not published"
	done
	[ "$($BB cat /run/qrtr-services.status 2>/dev/null)" = qrtr-published ] &&
		[ "$($BB cat /run/rmtfs.status 2>/dev/null)" = rmtfs-published ] || fail 'service status markers missing'
	$BB mkdir -p /run/pmos/vendor/etc/wifi/qca6750 /run/pmos/vendor/firmware/wlan/qca_cld/qca6750
	$BB cp "/vendor/$INI" "/run/pmos/vendor/$INI"
	$BB chmod 444 "/run/pmos/vendor/$INI"
	$BB ln -s /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini /run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini
	[ "$($BB readlink /run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini)" = /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini ] &&
		[ "$(hash "/run/pmos/vendor/$INI")" = "$INI_SHA" ] || fail 'staged INI is not reachable through the stock firmware path'
	$BB mkdir -p -m 700 "/run/pmos/run/radio-bringup"
	$BB cp /bin/wpss-once /run/pmos/run/radio-bringup/wpss-once
	$BB chmod 700 /run/pmos/run/radio-bringup/wpss-once
	[ "$(hash /run/pmos/run/radio-bringup/wpss-once)" = "$HELPER_SHA" ] || fail 'staged helper digest mismatch'
	$BB printf 'qrtr-published\n' > /run/pmos/run/qrtr-services.status
	$BB printf 'rmtfs-published\n' > /run/pmos/run/rmtfs.status
	if [ -c /dev/wlan ]; then
		wlan_id=$($BB stat -c '%t %T' /dev/wlan)
		set -- $wlan_id
		$BB mknod -m 0600 /run/pmos/dev/wlan c "$((0x$1))" "$((0x$2))" || fail 'cannot copy the init-created wlan control node'
		[ "$($BB stat -c '%t:%T' /run/pmos/dev/wlan)" = "$($BB stat -c '%t:%T' /dev/wlan)" ] || fail 'copied wlan node differs'
		report 'guest wlan control node copied from the init-created node'
	else
		report 'no init-created /dev/wlan to copy; the wpss stage will derive it from the live class device or stop'
	fi
	report 'stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover'
	exit 0
fi

$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox &&
	$BB awk '$2 == "/" && $3 == "tmpfs" {n++} END {exit(n != 1)}' /proc/1/mounts &&
	$BB grep -q 'ID="postmarketos"' /etc/os-release &&
	[ "$($BB cat /run/openrc/softlevel 2>/dev/null)" = default ] &&
	/sbin/rc-service local status >/dev/null 2>&1 || fail 'post-cutover PID 1 or default/local absent'
[ "$($BB cat /run/pid1-guard/accepted 2>/dev/null)" = "$boot" ] || fail 'PID 1 guard not acknowledged on this boot'
[ "$(hash /vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini)" = "$INI_SHA" ] || fail 'pre-cutover staged stock INI missing'
[ "$($BB cat "$MSS/name")" = 4080000.remoteproc-mss ] &&
	[ "$($BB cat "$WPSS/name")" = 9bb00000.remoteproc-wpss ] || fail 'unexpected remoteproc identities'
$BB mkdir -p -m 700 "$STATE"
[ "$($BB stat -c '%u:%a' "$STATE")" = 0:700 ] || fail 'radio state not root-only'

oldroot=
find_oldroot() {
	[ -n "$oldroot" ] && return 0
	for root in /proc/[0-9]*/root; do
		[ -f "$root/$KO" ] && [ -f "$root/vendor/$INI" ] || continue
		[ "$(hash "$root/$KO")" = "$KO_SHA" ] &&
			[ "$(hash "$root/vendor/$INI")" = "$INI_SHA" ] || continue
		oldroot=$root
		return 0
	done
	return 1
}

capture_gate() {
	[ -n "$marker" ] || fail 'fresh host capture selftest marker required before a risky stage'
	case "$marker" in *[!A-Za-z0-9_.-]*) fail 'invalid capture marker';; esac
	$BB dmesg 2>/dev/null | $BB grep -qF "$marker" || fail 'host-verified capture marker is not in this boot kmsg'
}

once() {
	[ ! -e "$STATE/$1.attempted" ] && [ ! -L "$STATE/$1.attempted" ] || fail "$1 already attempted; no retry"
	$BB printf '%s\n' "$boot" > "$STATE/$1.attempted" || fail "cannot arm $1 marker"
}

bind_firmware_mnt() {
	find_oldroot || fail 'no surviving old-root process exposes the stock module and INI'
	[ -r "$oldroot/vendor/firmware_mnt/image/modem.mdt" ] &&
		[ -r "$oldroot/vendor/firmware_mnt/image/qca6750/wpss.mdt" ] ||
		fail 'stock modem_a firmware is not reachable'
	if ! $BB grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts; then
		[ ! -e /vendor/firmware_mnt ] && [ ! -L /vendor/firmware_mnt ] || fail 'firmware_mnt path already present but not the read-only vfat'
		$BB mkdir /vendor/firmware_mnt
		$BB mount --bind "$oldroot/vendor/firmware_mnt" /vendor/firmware_mnt || fail 'stock firmware bind failed'
		$BB mount -o remount,bind,ro /vendor/firmware_mnt || { $BB umount /vendor/firmware_mnt; fail 'firmware bind not read-only; bind removed'; }
		$BB grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts || fail 'firmware bind is not the read-only vfat'
	fi
	[ -r /vendor/firmware_mnt/image/modem.mdt ] &&
		[ -r /vendor/firmware_mnt/image/qca6750/wpss.mdt ] ||
		fail 'modem_a firmware not readable at /vendor/firmware_mnt/image'
}

modem() {
	stage=modem
	[ "$(state "$MSS")" = running ] && { report 'modem already running; untouched'; return 0; }
	[ "$(state "$MSS")" = offline ] || fail 'modem is neither offline nor running'
	capture_gate
	[ "$($BB cat /run/qrtr-services.status 2>/dev/null)" = qrtr-published ] &&
		[ "$($BB cat /run/rmtfs.status 2>/dev/null)" = rmtfs-published ] || fail 'staged service markers missing'
	for service in pd-mapper tqftpserv rmtfs; do
		$BB ps | $BB grep -v grep | $BB grep -q "$service" || fail "$service is not running"
	done
	bind_firmware_mnt
	once modem
	$BB printf 'radio-bringup: guarded remoteproc2 start\n' > /dev/kmsg
	$BB timeout -k 1 10 $BB sh -c 'printf "start\n" > /sys/class/remoteproc/remoteproc2/state' || fail 'modem start failed or timed out'
	i=0
	until [ "$(state "$MSS")" = running ]; do
		[ "$i" -lt 20 ] || fail 'modem did not reach running within 20 s'
		i=$((i + 1))
		$BB sleep 1
	done
	$BB sleep 5
	[ "$(state "$MSS")" = running ] && $BB dmesg | $BB grep -q 'icnss2_qmi: QMI DMS service connected' ||
		fail 'modem did not hold with QMI DMS connected'
	report 'modem running past 5 s; QMI DMS connected'
}

wpss() {
	stage=wpss
	[ "$(state "$WPSS")" = running ] && { report 'WPSS already running; untouched'; return 0; }
	[ "$(state "$WPSS")" = offline ] && [ "$(state "$MSS")" = running ] || fail 'WPSS must be offline with the modem running'
	capture_gate
	bind_firmware_mnt
	[ ! -e /run/wpss-once.attempted ] || fail 'wpss-once already attempted'
	[ -f "$STATE/wpss-once" ] && [ ! -L "$STATE/wpss-once" ] && [ "$(hash "$STATE/wpss-once")" = "$HELPER_SHA" ] || fail 'staged helper missing or digest mismatch'
	if [ ! -c /dev/wlan ]; then
		numbers=$($BB cat /sys/class/wlan/wlan/dev 2>/dev/null) || numbers=
		case "$numbers" in [0-9]*:[0-9]*) :;; *) fail 'no /dev/wlan and no live wlan class device; input needed: wlan control node';; esac
		major=${numbers%%:*}
		minor=${numbers##*:}
		case "$major$minor" in *[!0-9]*) fail 'malformed wlan class numbers';; esac
		$BB awk -v m="$major" '$1 == m && $2 == "qcwlanstate" {n++} END {exit(n != 1)}' /proc/devices || fail 'wlan class major does not match qcwlanstate'
		$BB timeout -k 1 2 $BB mknod -m 0600 /dev/wlan c "$major" "$minor" || fail 'mknod /dev/wlan failed'
		[ "$($BB stat -c '%t:%T' /dev/wlan)" = "$($BB printf '%x:%x' "$major" "$minor")" ] || { $BB rm -f /dev/wlan; fail '/dev/wlan numbers differ'; }
	fi
	once wpss
	rc=0
	$BB sh "$STATE/wpss-once" > "$STATE/wpss.log" 2>&1 || rc=$?
	case "$rc" in 0|10) :;; *) fail "one-shot helper exit $rc; no retry";; esac
	[ "$(state "$WPSS")" = running ] && $BB dmesg | $BB grep -q 'icnss2: WLAN FW is ready' || fail 'WPSS or WLAN firmware not ready'
	report "WPSS running and WLAN firmware ready (helper exit $rc; 10 is only the optional ON hold)"
}

wlan_present() {
	[ -e /sys/class/net/wlan0 ] && [ -d /sys/class/ieee80211/phy0 ]
}

driver() {
	stage=driver
	wlan_present && { report 'wlan0 and phy0 already registered; untouched'; return 0; }
	[ "$(state "$MSS")" = running ] && [ "$(state "$WPSS")" = running ] || fail 'both remoteprocs must be running'
	capture_gate
	find_oldroot || fail 'no surviving old-root process exposes the stock module'
	once driver
	if [ ! -d /sys/module/qca_cld3_qca6750 ]; then
		$BB printf 'radio-bringup: one qca_cld3 insmod\n' > /dev/kmsg
		$BB timeout -k 1 15 $BB insmod "$oldroot/$KO" > "$STATE/insmod.log" 2>&1 || report 'insmod failed; the one bounded reload remains'
		$BB sleep 3
	fi
	if ! wlan_present; then
		$BB printf 'radio-bringup: one qca_cld3 reload\n' > /dev/kmsg
		if [ -d /sys/module/qca_cld3_qca6750 ]; then
			$BB timeout -k 1 10 $BB rmmod qca_cld3_qca6750 > "$STATE/rmmod.log" 2>&1 || fail 'rmmod failed or timed out; stop'
			[ ! -d /sys/module/qca_cld3_qca6750 ] || fail 'module remained loaded after rmmod; stop'
		fi
		$BB timeout -k 1 15 $BB insmod "$oldroot/$KO" > "$STATE/reload.log" 2>&1 || fail 'reload failed or timed out; stop'
		$BB sleep 3
	fi
	wlan_present || fail 'wlan0 or phy0 absent after one insmod and one reload; stop'
	[ "$(state "$MSS")" = running ] && [ "$(state "$WPSS")" = running ] || fail 'a remoteproc left running'
	report 'wlan0 and phy0 registered; both remoteprocs running'
}

scan() {
	stage=scan
	wlan_present || fail 'wlan0 or phy0 not registered'
	[ ! -e "$STATE/scan.raw" ] && [ ! -L "$STATE/scan.raw" ] || fail 'scan already recorded; no repeat'
	/sbin/ip link set wlan0 up || fail 'wlan0 link-up failed'
	flags=$($BB cat /sys/class/net/wlan0/flags)
	[ $((flags & 1)) -eq 1 ] || fail 'wlan0 is not IFF_UP'
	rc=0
	( umask 077; $BB timeout -k 2 20 /usr/sbin/iw dev wlan0 scan > "$STATE/scan.raw" 2> "$STATE/scan.err" ) || rc=$?
	[ "$rc" = 0 ] || fail "bounded scan exit $rc (private result retained in guest RAM)"
	count=$($BB grep -c '^BSS ' "$STATE/scan.raw") || count=0
	[ "$count" -gt 0 ] || fail 'bounded scan returned no BSS'
	report "bounded scan exit 0; BSS count $count (raw scan stays root-only in guest RAM)"
}

case "$stage" in
	modem) modem;;
	wpss) wpss;;
	driver) driver;;
	scan) scan;;
	all) modem; wpss; driver; scan;;
esac
