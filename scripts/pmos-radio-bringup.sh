#!/bin/busybox sh
set -eu

BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
STATE=/run/radio-bringup
INI=etc/wifi/qca6750/WCNSS_qcom_cfg.ini
INI_SHA=57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4
KO=mnt/vendor_dlkm/lib/modules/qca_cld3_qca6750.ko
KO_SHA=c2dbdcd119955b7212d61eeb00528b8b69012a3e7f9528ceb1738b6081ee6e0b
RMTFS_SHA=d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd
HELPER_SHA=fef7e5da780d59a02a558b912d30fccb905ceb3b4e6a964ed666d1897f3987d2
LEASE_SHA=86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896
NETWORKING_SHA=334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c
WPA_SERVICE_SHA=a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f
WPA_CONF_SHA=1600be060d3cdebb0663363f791fc1927ca1463f7a09e1f1f26b6e3ce390d1a1
MSS=/sys/class/remoteproc/remoteproc2
WPSS=/sys/class/remoteproc/remoteproc3

fail() { $BB printf 'radio-bringup: FAIL %s: %s\n' "$stage" "$*" >&2; exit 1; }
report() { $BB printf 'radio-bringup: %s\n' "$*" >&2; }
hash() { $BB sha256sum "$1" 2>/dev/null | $BB cut -d ' ' -f 1; }
state() { $BB timeout -k 1 2 $BB cat "$1/state" 2>/dev/null; }

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || { $BB printf 'usage: BOOT_ID prepare|modem|wpss|driver|scan|services|all [CAPTURE_MARKER]\n' >&2; exit 2; }
boot=$1
stage=$2
marker=${3:-}
case "$stage" in prepare|modem|wpss|driver|scan|services|all) :;; *) fail 'unknown stage';; esac
[ "$($BB cat /proc/sys/kernel/random/boot_id)" = "$boot" ] || fail 'boot ID mismatch'
[ -f /run/keep ] && [ ! -L /run/keep ] || fail 'diagnostic or guest hold absent'
[ "$($BB id -u)" = 0 ] || fail 'not root'

rmtfs_inputs() {
	phase=$1
	rmtfs_pid=
	n=0
	for dir in /proc/[0-9]*; do
		[ "$($BB cat "$dir/comm" 2>/dev/null)" = rmtfs ] || continue
		if [ "$phase" = pre ]; then
			[ "$(hash "$dir/exe")" = "$RMTFS_SHA" ] || continue
		else
			[ "$($BB cat "$STATE/rmtfs.pid" 2>/dev/null)" = "${dir##*/}" ] &&
				[ "$(hash "$dir/exe")" = "$RMTFS_SHA" ] || continue
		fi
		rmtfs_pid=${dir##*/}
		n=$((n + 1))
	done
	[ "$n" = 1 ] || fail "expected exactly one pinned rmtfs process, found $n"
	rmtfs_root=/proc/$rmtfs_pid/root
	if [ "$phase" = pre ]; then
		rmtfs_log=$rmtfs_root/run/rmtfs.log
	else
		[ "$($BB cat "$STATE/rmtfs.pid" 2>/dev/null)" = "$rmtfs_pid" ] || fail 'surviving rmtfs PID does not match the prepared service'
		rmtfs_log=$STATE/rmtfs.log
	fi
	[ -f "$rmtfs_log" ] && [ ! -L "$rmtfs_log" ] &&
		$BB grep -q 'rmtfs: published QRTR service' "$rmtfs_log" &&
		$BB grep -q 'rmtfs: mapped stock UIO' "$rmtfs_log" || fail 'rmtfs did not log the UIO map and QRTR publish'
	$BB grep -q '/dev/uio0' "/proc/$rmtfs_pid/maps" || fail 'rmtfs does not hold the mapped sharedmem UIO'
	[ "$($BB cat /sys/class/uio/uio0/name 2>/dev/null)" = rmtfs ] || fail 'kernel sharedmem UIO is not the rmtfs client'
	uio_id=$($BB cat /sys/class/uio/uio0/dev)
	case "$uio_id" in [0-9]*:[0-9]*) :;; *) fail 'rmtfs UIO numbers invalid';; esac
	if [ "$phase" = post ] && [ ! -c "$rmtfs_root/dev/uio0" ]; then
		[ ! -e "$rmtfs_root/dev/uio0" ] && [ ! -L "$rmtfs_root/dev/uio0" ] || fail 'rmtfs UIO path is not a character node'
		$BB mkdir -p "$rmtfs_root/dev" || fail 'cannot restore the rmtfs dev directory'
		$BB mknod -m 0600 "$rmtfs_root/dev/uio0" c "${uio_id%%:*}" "${uio_id##*:}" || fail 'cannot restore the rmtfs UIO node'
		rmtfs_restored="${rmtfs_restored:-} uio0"
	fi
	[ -c "$rmtfs_root/dev/uio0" ] &&
		[ "$($BB stat -c '%t:%T' "$rmtfs_root/dev/uio0")" = "$($BB printf '%x:%x' "${uio_id%%:*}" "${uio_id##*:}")" ] ||
		fail 'sharedmem UIO node absent or differs from sysfs'
	for part in sdf2:modemst1 sdf3:modemst2; do
		device=${part%%:*}
		name=${part##*:}
		[ "$($BB sed -n 's/^PARTNAME=//p' "/sys/class/block/$device/uevent" 2>/dev/null)" = "$name" ] || fail "$name PARTNAME changed"
		if [ "$phase" = post ] && [ ! -b "$rmtfs_root/dev/block/$device" ]; then
			[ ! -e "$rmtfs_root/dev/block/$device" ] && [ ! -L "$rmtfs_root/dev/block/$device" ] || fail "$name backing node differs"
			devnum=$($BB cat "/sys/class/block/$device/dev")
			case "$devnum" in [0-9]*:[0-9]*) :;; *) fail "$name device numbers invalid";; esac
			$BB mkdir -p "$rmtfs_root/dev/block" || fail "cannot restore the rmtfs block directory"
			$BB mknod -m 0400 "$rmtfs_root/dev/block/$device" b "${devnum%%:*}" "${devnum##*:}" || fail "cannot restore the $name block node"
			rmtfs_restored="${rmtfs_restored:-} $device"
		fi
		[ -b "$rmtfs_root/dev/block/$device" ] || fail "$name backing block node absent from the rmtfs root"
		devnum=$($BB cat "/sys/class/block/$device/dev")
		[ "$($BB stat -c '%t:%T' "$rmtfs_root/dev/block/$device")" = "$($BB printf '%x:%x' "${devnum%%:*}" "${devnum##*:}")" ] || fail "$name backing node differs from sysfs"
		if [ "$phase" = pre ]; then
			[ "$($BB readlink "$rmtfs_root/boot/$name" 2>/dev/null)" = "/dev/block/$device" ] || fail "$name backing link absent before cutover"
		elif [ -L "$rmtfs_root/boot/$name" ]; then
			[ "$($BB readlink "$rmtfs_root/boot/$name")" = "/dev/block/$device" ] || fail "$name backing link differs from the measured target"
		else
			[ ! -e "$rmtfs_root/boot/$name" ] || fail "$name backing path is not the measured link"
			$BB mkdir -p "$rmtfs_root/boot" || fail "cannot restore the rmtfs /boot directory"
			$BB ln -s "/dev/block/$device" "$rmtfs_root/boot/$name" || fail "cannot restore the $name backing link"
			rmtfs_restored="${rmtfs_restored:-} $name"
		fi
		$BB dd if="$rmtfs_root/dev/block/$device" of=/dev/null bs=512 count=1 2>/dev/null || fail "$name backing node is not readable"
	done
}

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
	[ -f /run/wlan-udhcpc-lease.sh ] && [ ! -L /run/wlan-udhcpc-lease.sh ] &&
		[ "$(hash /run/wlan-udhcpc-lease.sh)" = "$LEASE_SHA" ] || fail 'diagnostic lease helper digest mismatch'
	for service in pd-mapper tqftpserv rmtfs; do
		[ -f "/run/$service.log" ] && $BB grep -q "$service: published QRTR service" "/run/$service.log" || fail "$service has not published"
	done
	[ "$($BB cat /run/qrtr-services.status 2>/dev/null)" = qrtr-published ] &&
		[ "$($BB cat /run/rmtfs.status 2>/dev/null)" = rmtfs-published ] || fail 'service status markers missing'
	rmtfs_inputs pre
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
	$BB cp /run/wlan-udhcpc-lease.sh /run/pmos/run/radio-bringup/wlan-udhcpc-lease.sh
	$BB chmod 700 /run/pmos/run/radio-bringup/wlan-udhcpc-lease.sh
	[ "$(hash /run/pmos/run/radio-bringup/wlan-udhcpc-lease.sh)" = "$LEASE_SHA" ] || fail 'staged lease helper digest mismatch'
	$BB printf 'qrtr-published\n' > /run/pmos/run/qrtr-services.status
	$BB printf 'rmtfs-published\n' > /run/pmos/run/rmtfs.status
	$BB cp /run/rmtfs.log /run/pmos/run/radio-bringup/rmtfs.log
	$BB chmod 600 /run/pmos/run/radio-bringup/rmtfs.log
	$BB printf '%s\n' "$rmtfs_pid" > /run/pmos/run/radio-bringup/rmtfs.pid
	$BB chmod 600 /run/pmos/run/radio-bringup/rmtfs.pid
	report "pinned rmtfs pid $rmtfs_pid holds the mapped sharedmem UIO and has its read-only modemst paths before cutover"
	if [ -e /dev/wlan ] || [ -L /dev/wlan ]; then
		[ -c /dev/wlan ] && [ ! -L /dev/wlan ] || fail 'init-created /dev/wlan is not a character node'
		wlan_id=$($BB stat -c '%t %T' /dev/wlan)
		set -- $wlan_id
		$BB mknod -m 0600 /run/pmos/dev/wlan c "$((0x$1))" "$((0x$2))" || fail 'cannot copy the init-created wlan control node'
		[ "$($BB stat -c '%t:%T:%a' /run/pmos/dev/wlan)" = "$1:$2:600" ] || fail 'copied wlan node differs'
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

bind_rmtfs_storage() {
	rmtfs_restored=
	rmtfs_inputs post
	for name in modemst1 modemst2; do
		case $name in modemst1) device=sdf2;; *) device=sdf3;; esac
		[ "$($BB readlink "$rmtfs_root/boot/$name")" = "/dev/block/$device" ] || fail "$name backing link missing after restore"
	done
	report "rmtfs pid $rmtfs_pid keeps the mapped UIO and QRTR service; restored backing links:${rmtfs_restored:- none needed}"
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
	bind_rmtfs_storage
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
	numbers=$($BB cat /sys/class/wlan/wlan/dev 2>/dev/null) || numbers=
	case "$numbers" in ''|*[!0-9:]*|*:*:*|*:|:*) fail 'no /dev/wlan and no valid live wlan class device; input needed: wlan control node';; *:*) :;; *) fail 'no /dev/wlan and no valid live wlan class device; input needed: wlan control node';; esac
	major=${numbers%%:*}
	minor=${numbers##*:}
	$BB awk -v m="$major" '$1 == "Character" {s=1} $1 == "Block" {s=0} s && $1 == m && $2 == "qcwlanstate" {n++} END {exit(n != 1)}' /proc/devices || fail 'wlan class major does not match one character qcwlanstate'
	if [ -c /dev/wlan ]; then
		[ ! -L /dev/wlan ] && [ "$($BB stat -c '%t:%T:%a' /dev/wlan)" = "$($BB printf '%x:%x:600' "$major" "$minor")" ] || fail 'existing /dev/wlan differs from live wlan class device or is not root-only'
	else
		[ ! -e /dev/wlan ] && [ ! -L /dev/wlan ] || fail '/dev/wlan is not a character node; no replacement'
		$BB timeout -k 1 2 $BB mknod -m 0600 /dev/wlan c "$major" "$minor" || { $BB rm -f /dev/wlan; fail 'mknod /dev/wlan failed; node removed'; }
		[ -c /dev/wlan ] && [ "$($BB stat -c '%t:%T:%a' /dev/wlan)" = "$($BB printf '%x:%x:600' "$major" "$minor")" ] || { $BB rm -f /dev/wlan; fail '/dev/wlan numbers or permissions differ; node removed'; }
		report "derived /dev/wlan character $major:$minor from the live qcwlanstate class device"
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

install_service_config() {
	umask 077
	$BB cat > /etc/wpa_supplicant/wpa_supplicant.conf || fail 'profile transfer failed'
	[ -s /etc/wpa_supplicant/wpa_supplicant.conf ] &&
		[ "$($BB stat -c '%u:%a' /etc/wpa_supplicant/wpa_supplicant.conf)" = 0:600 ] || {
		$BB rm -f /etc/wpa_supplicant/wpa_supplicant.conf
		fail 'profile missing or not root-only'
	}
	$BB printf '#!/bin/busybox sh\nIP_CMD=/sbin/ip\nexport IP_CMD\nexec /bin/busybox sh /run/radio-bringup/wlan-udhcpc-lease.sh "$@"\n' > "$STATE/lease-wrapper.sh"
	$BB chmod 700 "$STATE/lease-wrapper.sh"
	$BB printf 'auto wlan0\niface wlan0 inet dhcp\n\tdhcp-script /run/radio-bringup/lease-wrapper.sh\n\tudhcpc-opts -t 5 -T 3 -A 5 -n\n' > /etc/network/interfaces
	$BB chmod 600 /etc/network/interfaces
	$BB printf 'ifquery=/run/radio-bringup/ifquery-wlan\n' > /etc/conf.d/networking
	$BB chmod 600 /etc/conf.d/networking
	$BB printf '#!/bin/busybox sh\nif [ "$#" = 4 ] && [ "$1" = -i ] && [ "$2" = /etc/network/interfaces ] && [ "$3" = --list ] && [ "$4" = -a ]; then /bin/busybox printf "wlan0\\n"; exit 0; fi\nexec /sbin/ifquery "$@"\n' > "$STATE/ifquery-wlan"
	$BB chmod 700 "$STATE/ifquery-wlan"
	$BB ln -s busybox /bin/run-parts
	$BB ln -s ../bin/busybox /sbin/udhcpc
	[ "$(/sbin/ifquery -i /etc/network/interfaces --list -a)" = 'lo
wlan0' ] || fail 'unexpected ifupdown interface inventory'
	[ "$("$STATE/ifquery-wlan" -i /etc/network/interfaces --list -a)" = wlan0 ] || fail 'WLAN-only interface selector failed'
	[ "$($BB stat -c '%u:%a' /etc/network/interfaces)" = 0:600 ] &&
		[ "$($BB stat -c '%u:%a' /etc/conf.d/networking)" = 0:600 ] || fail 'service config not root-only'
	$BB ln -s /etc/init.d/wpa_supplicant /etc/runlevels/default/wpa_supplicant
	$BB ln -s /etc/init.d/networking /etc/runlevels/default/networking
}

services() {
	stage=services
	capture_gate
	wlan_present && [ "$(state "$MSS")" = running ] && [ "$(state "$WPSS")" = running ] || fail 'radio not ready for OpenRC services'
	$BB dmesg > "$STATE/services-kmsg" 2>/dev/null || fail 'radio kmsg unavailable'
	if $BB grep -Eiq 'fatal error received:|fs_device_efs_rmts.c|hdd_psoc_idle_timeout_callback|kernel panic' "$STATE/services-kmsg"; then fail 'radio fatal in this boot'; fi
	$BB rm "$STATE/services-kmsg"
	[ -f /run/dropbear-session.pid ] && [ ! -L /run/dropbear-session.pid ] || fail 'guest :2222 pidfile absent'
	pid=$($BB cat /run/dropbear-session.pid)
	case "$pid" in ''|*[!0-9]*) fail 'guest :2222 pid invalid';; esac
	[ -r "/proc/$pid/cmdline" ] && [ "$($BB stat -Lc '%d:%i' "/proc/$pid/root" 2>/dev/null)" = "$($BB stat -c '%d:%i' /)" ] &&
		$BB tr '\000' ' ' < "/proc/$pid/cmdline" | $BB grep -q 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' &&
		$BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {n++} END {exit(n != 1)}' /proc/net/tcp || fail 'guest :2222 not healthy'
	[ ! -t 0 ] || fail 'profile must arrive on standard input from pinned key-only SSH'
	[ -f "$STATE/wlan-udhcpc-lease.sh" ] && [ ! -L "$STATE/wlan-udhcpc-lease.sh" ] &&
		[ "$($BB stat -c '%u:%a' "$STATE/wlan-udhcpc-lease.sh")" = 0:700 ] &&
		[ "$(hash "$STATE/wlan-udhcpc-lease.sh")" = "$LEASE_SHA" ] || fail 'pinned lease helper absent'
	for spec in "networking $NETWORKING_SHA" "wpa_supplicant $WPA_SERVICE_SHA"; do
		set -- $spec
		[ -f "/etc/init.d/$1" ] && [ ! -L "/etc/init.d/$1" ] && [ "$(hash "/etc/init.d/$1")" = "$2" ] || fail "unexpected $1 service"
	done
	[ -f /etc/conf.d/wpa_supplicant ] && [ ! -L /etc/conf.d/wpa_supplicant ] &&
		[ "$(hash /etc/conf.d/wpa_supplicant)" = "$WPA_CONF_SHA" ] || fail 'unexpected supplicant arguments; no -f supported'
	[ -x /sbin/rc-service ] && [ -x /sbin/ifup ] && [ -x /sbin/ip ] &&
		[ -x /sbin/wpa_supplicant ] && [ ! -e /bin/ip ] && [ ! -L /bin/ip ] || fail 'OpenRC or /sbin/ip prerequisites changed'
	for level in sysinit boot default nonetwork shutdown; do
		path=/etc/runlevels/$level
		[ -d "$path" ] && [ ! -L "$path" ] || fail 'unsafe runlevel'
		for entry in "$path"/* "$path"/.[!.]* "$path"/..?*; do
			[ ! -e "$entry" ] && [ ! -L "$entry" ] || {
				[ "$entry" = /etc/runlevels/default/local ] && [ "$($BB readlink "$entry")" = /etc/init.d/local ] || fail 'another OpenRC service enabled'
			}
		done
	done
	/sbin/rc-service local status >/dev/null 2>&1 &&
		! /sbin/rc-service networking status >/dev/null 2>&1 &&
		! /sbin/rc-service wpa_supplicant status >/dev/null 2>&1 || fail 'unexpected OpenRC service state'
	for path in /etc/network /etc/wpa_supplicant /etc/conf.d /etc/runlevels/default; do
		[ -d "$path" ] && [ ! -L "$path" ] && [ "$($BB stat -c %u "$path")" = 0 ] || fail 'unsafe guest config directory'
	done
	for path in /etc/network/interfaces /etc/wpa_supplicant/wpa_supplicant.conf /etc/conf.d/networking /bin/run-parts /sbin/udhcpc "$STATE/ifquery-wlan" "$STATE/lease-wrapper.sh" "$STATE/services.attempted"; do
		[ ! -e "$path" ] && [ ! -L "$path" ] || fail 'service input already exists; no overwrite'
	done
	install_service_config
	$BB printf '%s\n' "$boot" > "$STATE/services.attempted"
	/sbin/rc-service -D wpa_supplicant start > "$STATE/wpa-service.log" 2>&1 || fail 'wpa_supplicant first service error (private guest RAM log)'
	$BB sleep 2
	/sbin/rc-service wpa_supplicant status >/dev/null 2>&1 || fail 'wpa_supplicant did not stay started (private guest RAM log)'
	/sbin/rc-service -D networking start > "$STATE/networking-service.log" 2>&1 || fail 'networking first service error (private guest RAM log)'
	/sbin/rc-service networking status >/dev/null 2>&1 || fail 'networking did not stay started (private guest RAM log)'
	report 'OpenRC wpa_supplicant then networking started; no dependency service started; private service logs remain in guest RAM'
}

case "$stage" in
	modem) modem;;
	wpss) wpss;;
	driver) driver;;
	scan) scan;;
	services) services;;
	all) modem; wpss; driver; scan;;
esac
