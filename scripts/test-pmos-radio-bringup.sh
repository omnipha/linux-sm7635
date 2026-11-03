#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=${SCRIPT:-"$HERE/pmos-radio-bringup.sh"}
if [ "${1:-}" != --inner ] && [ "${1:-}" != --inner-291 ]; then
	[ -f "$SCRIPT" ] || exit 1
	for variant in "$HERE/pmos-radio-bringup.sh" "$HERE/pmos-radio-bringup-persistent.sh"; do
		sudo -n unshare --mount --pid --fork --mount-proc env HERE="$HERE" SCRIPT="$variant" /bin/busybox sh "$0" --inner
	done
	work=$(mktemp -d "${TMPDIR:-/tmp}/radio-fresh.XXXXXXXX")
	chmod 755 "$work"
	trap 'rm -rf "$work"' EXIT
	HERE="$HERE" OUTPUT="$work/pmos-radio-bringup-fresh.sh" python3 -B - <<'PY'
import importlib.util, os, pathlib
here = pathlib.Path(os.environ['HERE'])
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
radio = load('fresh', 'derive-radio-fresh-boot.py').derive(
    load('persistent', 'derive-radio-persistent.py').derive((here / 'pmos-radio-bringup.sh').read_text()))
pathlib.Path(os.environ['OUTPUT']).write_text(radio)
PY
	sudo -n unshare --mount --pid --fork --mount-proc env HERE="$HERE" SCRIPT="$work/pmos-radio-bringup-fresh.sh" /bin/busybox sh "$0" --inner
	HERE="$HERE" OUTPUT="$work/pmos-radio-bringup-291.sh" python3 -B - <<'PY'
import hashlib, importlib.util, os, pathlib
here = pathlib.Path(os.environ['HERE'])
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
staged = load('builder', 'build-init-boot-persistent-root.py').current_scripts()['pmos-radio-bringup.sh']
assert hashlib.sha256(staged).hexdigest() == 'f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f'
radio = load('fresh', 'derive-radio-fresh-boot.py').derive(
    load('persistent', 'derive-radio-persistent.py').derive(staged.decode()))
assert hashlib.sha256(radio.encode()).hexdigest() == 'a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21'
pathlib.Path(os.environ['OUTPUT']).write_text(radio)
PY
	mkdir "$work/radio-291-root"
	sudo -n unshare --mount --pid --fork --mount-proc env SCRIPT="$work/pmos-radio-bringup-291.sh" /bin/busybox sh "$0" --inner-291
	exit 0
fi

if [ "${1:-}" = --inner-291 ]; then
	[ "$$" -eq 1 ] && [ -f "$SCRIPT" ] || exit 1
	BB=/bin/busybox
	BOOT=11111111-2222-3333-4444-555555555555
	R=${SCRIPT%/*}/radio-291-root
	fail() { $BB printf 'FAIL: #291 %s\n' "$*" >&2; exit 1; }
	[ -d "$R" ] && [ ! -L "$R" ] || fail 'fixture root absent or unsafe'
	$BB mount --make-rprivate /
	$BB mount -t tmpfs -o mode=0755,size=32m tmpfs "$R"
	for d in bin sbin etc/init.d etc/conf.d etc/network etc/wpa_supplicant etc/runlevels/sysinit etc/runlevels/boot etc/runlevels/default etc/runlevels/nonetwork etc/runlevels/shutdown dev run/radio-bringup run/openrc run/pid1-guard proc/sys/kernel/random proc/1 proc/452 proc/net sys/class/remoteproc/remoteproc2 sys/class/remoteproc/remoteproc3 sys/class/net/wlan0 sys/class/ieee80211/phy0 vendor/firmware/wlan/qca_cld/qca6750 tmp; do
		$BB mkdir -p "$R/$d"
	done
	$BB cp /bin/busybox "$R/bin/busybox.real"
	$BB cp "$SCRIPT" "$R/radio.sh"
	[ "$( $BB sha256sum "$R/radio.sh" | $BB cut -d ' ' -f 1)" = a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21 ] || fail 'radio pin differs'
	$BB mknod -m 666 "$R/dev/null" c 1 3
	$BB ln -s /bin/busybox "$R/proc/1/exe"
	$BB printf 'tmpfs / tmpfs rw 0 0\n' > "$R/proc/1/mounts"
	$BB printf 'ID="postmarketos"\n' > "$R/etc/os-release"
	$BB printf '4080000.remoteproc-mss\n' > "$R/sys/class/remoteproc/remoteproc2/name"
	$BB printf '9bb00000.remoteproc-wpss\n' > "$R/sys/class/remoteproc/remoteproc3/name"
	$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc2/state"
	$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc3/state"
	$BB printf 'synthetic INI\n' > "$R/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini"
	$BB printf 'synthetic networking service\n' > "$R/etc/init.d/networking"
	$BB printf 'synthetic wpa service\n' > "$R/etc/init.d/wpa_supplicant"
	$BB printf 'wpa_supplicant_args=""\n' > "$R/etc/conf.d/wpa_supplicant"
	$BB chmod 644 "$R/etc/conf.d/wpa_supplicant"
	$BB touch "$R/sbin/ip" "$R/sbin/ifup" "$R/sbin/wpa_supplicant"
	$BB chmod 755 "$R/sbin/ip" "$R/sbin/ifup" "$R/sbin/wpa_supplicant"
	$BB ln -s /etc/init.d/local "$R/etc/runlevels/default/local"
	$BB printf '%s\0' dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid > "$R/proc/452/cmdline"
	$BB ln -s / "$R/proc/452/root"
	$BB printf '  0: 022A10AC:08AE 00000000:0000 0A 0 0 0 0 0 0 0\n' > "$R/proc/net/tcp"
	stage_291_run() {
		$BB mkdir -p "$R/run/radio-bringup" "$R/run/openrc" "$R/run/pid1-guard"
		$BB chmod 700 "$R/run/radio-bringup"
		$BB printf '%s\n' "$BOOT" > "$R/proc/sys/kernel/random/boot_id"
		$BB touch "$R/run/keep"
		$BB printf 'default\n' > "$R/run/openrc/softlevel"
		$BB printf '%s\n' "$BOOT" > "$R/run/pid1-guard/armed"
		$BB printf '%s\n' "$nonce" > "$R/run/pid1-guard/nonce"
		$BB printf '452\n' > "$R/run/dropbear-session.pid"
		$BB printf 'synthetic lease helper\n' > "$R/run/radio-bringup/wlan-udhcpc-lease.sh"
		$BB chmod 700 "$R/run/radio-bringup/wlan-udhcpc-lease.sh"
		token="guest-radio-services-$( $BB printf '%s' "$BOOT:$nonce:services" | $BB sha256sum | $BB cut -c 1-16)"
		$BB printf '%s\n' "$token" > "$R/run/radio-bringup/services.marker"
		$BB chmod 600 "$R/run/radio-bringup/services.marker"
		$BB printf 'pmos-self-post: guest radio marker %s\n' "$token" > "$R/tmp/dmesg.txt"
	}
	nonce=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
	stage_291_run
	$BB cat > "$R/bin/busybox" <<'MOCK'
#!/bin/busybox.real sh
BB=/bin/busybox.real
case "${1:-}" in
	sha256sum)
		case "${2:-}" in
			/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini) digest=57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4;;
			/run/radio-bringup/wlan-udhcpc-lease.sh) digest=1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56;;
			/etc/init.d/networking) digest=334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c;;
			/etc/init.d/wpa_supplicant) digest=a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f;;
			/etc/conf.d/wpa_supplicant)
				if [ "$( $BB cat "$2")" = 'wpa_supplicant_args=""' ]; then digest=1600be060d3cdebb0663363f791fc1927ca1463f7a09e1f1f26b6e3ce390d1a1; else exec "$BB" "$@"; fi;;
			*) exec "$BB" "$@";;
		esac
		printf '%s  %s\n' "$digest" "$2"
		exit 0;;
	dmesg) exec "$BB" cat /tmp/dmesg.txt;;
	sleep) exit 0;;
esac
exec "$BB" "$@"
MOCK
	$BB cat > "$R/sbin/rc-service" <<'RC'
#!/bin/busybox.real sh
BB=/bin/busybox.real
case "$1 $2 $3" in
	'local status ') exit 0;;
	'networking status '|'wpa_supplicant status ')
		[ ! -f "/run/radio-bringup/$1.failed" ] || exit 1
		[ -f "/run/radio-bringup/$1.started" ];;
	'-D wpa_supplicant start')
		[ -f /run/radio-bringup/ifquery-wlan ] && [ -f /run/radio-bringup/lease-wrapper.sh ] || exit 1
		$BB printf 'wpa\n' >> /run/radio-bringup/order
		$BB rm -f /run/radio-bringup/wpa_supplicant.failed
		$BB touch /run/radio-bringup/wpa_supplicant.started;;
	'-D networking start')
		[ -f /run/radio-bringup/wpa_supplicant.started ] && [ -f /run/radio-bringup/ifquery-wlan ] && [ -f /run/radio-bringup/lease-wrapper.sh ] || exit 1
		$BB printf 'net\n' >> /run/radio-bringup/order
		$BB rm -f /run/radio-bringup/networking.failed
		$BB touch /run/radio-bringup/networking.started;;
	*) exit 1;;
esac
RC
	$BB cat > "$R/sbin/ifquery" <<'IFQUERY'
#!/bin/busybox.real sh
[ "$*" = '-i /etc/network/interfaces --list -a' ] || exit 1
/bin/busybox.real printf 'lo\nwlan0\n'
IFQUERY
	$BB chmod 755 "$R/bin/busybox" "$R/sbin/rc-service" "$R/sbin/ifquery"
	run_291_services() {
		$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="synthetic"\npsk="synthetic-only"\n}\n' |
			$BB chroot "$R" /bin/busybox.real sh /radio.sh "$BOOT" services "$token" > "$R/tmp/$1.out" 2>&1
	}
	check_291_starts() {
		[ "$( $BB cat "$R/run/radio-bringup/order")" = 'wpa
net' ] || fail "$1: starts not ordered"
		[ "$( $BB cat "$R/run/radio-bringup/services.attempted")" = "$BOOT" ] || fail "$1: attempt not recorded"
		[ -f "$R/run/radio-bringup/wpa_supplicant.started" ] && [ -f "$R/run/radio-bringup/networking.started" ] &&
			[ ! -e "$R/run/radio-bringup/wpa_supplicant.failed" ] && [ ! -e "$R/run/radio-bringup/networking.failed" ] || fail "$1: services not started"
		for helper in ifquery-wlan lease-wrapper.sh; do
			[ -f "$R/run/radio-bringup/$helper" ] && [ ! -L "$R/run/radio-bringup/$helper" ] &&
				[ "$( $BB stat -c '%u:%a:%h' "$R/run/radio-bringup/$helper")" = 0:700:1 ] || fail "$1: $helper not recreated root-only"
		done
	}
	$BB printf 'ffffffff-ffff-ffff-ffff-ffffffffffff\n' > "$R/run/pid1-guard/armed"
	if run_291_services invalid_guard; then fail 'unarmed guard accepted'; fi
	$BB grep -qF 'PID 1 guard is not armed and unacknowledged' "$R/tmp/invalid_guard.out" || fail 'guard refusal missing'
	$BB printf '%s\n' "$BOOT" > "$R/run/pid1-guard/armed"
	$BB printf 'invalid\n' > "$R/run/radio-bringup/services.marker"
	if run_291_services invalid_marker; then fail 'invalid capture marker accepted'; fi
	$BB grep -qF 'guest radio marker missing or unsafe' "$R/tmp/invalid_marker.out" || fail 'capture refusal missing'
	$BB printf '%s\n' "$token" > "$R/run/radio-bringup/services.marker"
	run_291_services initial || { $BB cat "$R/tmp/initial.out" >&2; fail 'initial services refused'; }
	check_291_starts initial
	for path in etc/network/interfaces etc/wpa_supplicant/wpa_supplicant.conf etc/conf.d/networking etc/conf.d/wpa_supplicant run/radio-bringup/ifquery-wlan run/radio-bringup/lease-wrapper.sh; do
		$BB cp "$R/$path" "$R/tmp/${path##*/}.own"
	done
	next_291_boot() {
		BOOT=$1
		nonce=$2
		$BB rm -rf "$R/run"
		stage_291_run
		for service in local wpa_supplicant networking; do
			[ -L "$R/etc/runlevels/default/$service" ] && [ "$( $BB readlink "$R/etc/runlevels/default/$service")" = "/etc/init.d/$service" ] || fail "next boot: $service link lost"
		done
		for path in etc/network/interfaces etc/wpa_supplicant/wpa_supplicant.conf etc/conf.d/networking etc/conf.d/wpa_supplicant; do
			$BB cmp -s "$R/$path" "$R/tmp/${path##*/}.own" || fail "next boot: $path changed"
			mode=600
			[ "$path" != etc/conf.d/wpa_supplicant ] || mode=644
			[ "$( $BB stat -c '%u:%a:%h' "$R/$path")" = "0:$mode:1" ] || fail "next boot: $path metadata changed"
		done
		[ -L "$R/bin/run-parts" ] && [ "$( $BB readlink "$R/bin/run-parts")" = busybox ] &&
			[ -L "$R/sbin/udhcpc" ] && [ "$( $BB readlink "$R/sbin/udhcpc")" = ../bin/busybox ] || fail 'next boot: persistent utility links changed'
		for path in ifquery-wlan lease-wrapper.sh services.attempted services-stdin order wpa_supplicant.started networking.started; do
			[ ! -e "$R/run/radio-bringup/$path" ] && [ ! -L "$R/run/radio-bringup/$path" ] || fail "next boot: volatile $path survived"
		done
	}
	next_291_boot 22222222-2222-3333-4444-555555555555 abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789
	run_291_services stopped || { $BB cat "$R/tmp/stopped.out" >&2; fail 'stopped services refused'; }
	$BB grep -qF 'OpenRC wpa_supplicant then networking started' "$R/tmp/stopped.out" || fail 'stopped: service summary missing'
	check_291_starts stopped
	for path in etc/network/interfaces etc/wpa_supplicant/wpa_supplicant.conf etc/conf.d/networking etc/conf.d/wpa_supplicant run/radio-bringup/ifquery-wlan run/radio-bringup/lease-wrapper.sh; do
		$BB cmp -s "$R/$path" "$R/tmp/${path##*/}.own" || fail "stopped: $path differs from own output"
	done
	next_291_boot 33333333-2222-3333-4444-555555555555 123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0
	$BB touch "$R/run/radio-bringup/wpa_supplicant.failed" "$R/run/radio-bringup/networking.failed"
	run_291_services failed || { $BB cat "$R/tmp/failed.out" >&2; fail 'failed services refused'; }
	$BB grep -qF 'OpenRC wpa_supplicant then networking started' "$R/tmp/failed.out" || fail 'failed: service summary missing'
	check_291_starts failed
	for path in run/radio-bringup/ifquery-wlan run/radio-bringup/lease-wrapper.sh; do
		$BB cmp -s "$R/$path" "$R/tmp/${path##*/}.own" || fail "failed: $path differs from own output"
	done
	next_291_boot 44444444-2222-3333-4444-555555555555 fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210
	$BB touch "$R/run/radio-bringup/wpa_supplicant.started" "$R/run/radio-bringup/networking.started"
	run_291_services started || { $BB cat "$R/tmp/started.out" >&2; fail 'already-started services refused'; }
	$BB grep -qF 'persistent OpenRC WLAN services already running; no reinstall' "$R/tmp/started.out" || fail 'already-started early return missing'
	[ -f "$R/run/radio-bringup/wpa_supplicant.started" ] && [ -f "$R/run/radio-bringup/networking.started" ] || fail 'already-started status changed'
	for path in ifquery-wlan lease-wrapper.sh services.attempted services-stdin order; do
		[ ! -e "$R/run/radio-bringup/$path" ] && [ ! -L "$R/run/radio-bringup/$path" ] || fail "already-started unexpectedly created $path"
	done
	$BB printf 'invalid\n' > "$R/run/radio-bringup/services.marker"
	if run_291_services started_invalid_marker; then fail 'already-started bypassed capture marker'; fi
	$BB grep -qF 'guest radio marker missing or unsafe' "$R/tmp/started_invalid_marker.out" || fail 'already-started capture refusal missing'
	[ ! -e "$R/run/radio-bringup/order" ] && [ ! -e "$R/run/radio-bringup/ifquery-wlan" ] && [ ! -e "$R/run/radio-bringup/lease-wrapper.sh" ] || fail 'already-started capture refusal changed services'
	$BB printf 'pass: exact #291 radio; synthetic failed/stopped services recreate helpers and start wpa then networking; already-started early return leaves both helpers absent (limitation)\n'
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
$BB printf '%s\n' "$BOOT" > "$R/run/pid1-guard/armed"
$BB printf '%s\n' 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef > "$R/run/pid1-guard/nonce"
$BB chmod 600 "$R/run/pid1-guard/nonce"
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
$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
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
for stage in modem wpss driver scan services; do
	token="guest-radio-$stage-$($BB printf '%s' "$BOOT:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:$stage" | $BB sha256sum | $BB cut -c 1-16)"
	eval "${stage}_token=\$token"
	$BB printf '%s\n' "$token" > "$R/run/radio-bringup/$stage.marker"
	$BB chmod 600 "$R/run/radio-bringup/$stage.marker"
	$BB printf 'pmos-self-post: guest radio marker %s\n' "$token" >> "$R/tmp/dmesg.txt"
done

reject_stage modem "$BOOT" modem
$BB printf '%s\n' ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff > "$R/run/pid1-guard/nonce"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'guest radio marker does not match this guard nonce' 'nonce substitution accepted'
$BB printf '%s\n' 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef > "$R/run/pid1-guard/nonce"
$BB printf '%s\n' "$BOOT" > "$R/run/pid1-guard/accepted"
$BB rm "$R/run/pid1-guard/nonce"
reject_stage modem "$BOOT" modem
expect "$R/tmp/modem.out" 'guard is not armed and unacknowledged' 'consumed-nonce acknowledged guard accepted'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed after guard acknowledgement'
$BB printf '%s\n' 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef > "$R/run/pid1-guard/nonce"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'guard is not armed and unacknowledged' 'already-acknowledged guard accepted'
$BB rm "$R/run/pid1-guard/accepted"
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc2/state"
reject_stage modem "$BOOT" modem missing-marker
$BB mv "$R/sys/class/uio/uio0/name" "$R/tmp/uio-name.hidden"
$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB printf 'pmos-self-post: guest radio marker %s\n' "$modem_token" >> "$R/tmp/dmesg.txt"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'kernel sharedmem UIO is not the rmtfs client' 'missing UIO reason'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed with the sharedmem UIO absent'
$BB mv "$R/tmp/uio-name.hidden" "$R/sys/class/uio/uio0/name"
$BB mv "$R/run/radio-bringup/rmtfs.pid" "$R/tmp/rmtfs.pid.hidden"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'expected exactly one pinned rmtfs process' 'copied status marker accepted without prepared rmtfs'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed without the prepared rmtfs process identity'
$BB mv "$R/tmp/rmtfs.pid.hidden" "$R/run/radio-bringup/rmtfs.pid"
$BB mv "$R/run/radio-bringup/rmtfs.log" "$R/tmp/rmtfs.log.hidden"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'rmtfs did not log the UIO map and QRTR publish' 'missing rmtfs publish log reason'
$BB mv "$R/tmp/rmtfs.log.hidden" "$R/run/radio-bringup/rmtfs.log"
$BB mv "$R/proc/628/maps" "$R/tmp/rmtfs.maps.hidden"
$BB printf '' > "$R/proc/628/maps"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'rmtfs does not hold the mapped sharedmem UIO' 'missing UIO mapping reason'
$BB mv "$R/tmp/rmtfs.maps.hidden" "$R/proc/628/maps"
$BB printf 'PARTNAME=other\n' > "$R/sys/class/block/sdf3/uevent"
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'modemst2 PARTNAME changed' 'wrong backing partition reason'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed with the wrong modemst backing'
$BB printf 'PARTNAME=modemst2\n' > "$R/sys/class/block/sdf3/uevent"
$BB rm "$R/tmp/modemst.img"
reject_stage modem "$BOOT" modem "$modem_token"
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
reject_stage modem "$BOOT" modem "$modem_token"
expect "$R/tmp/modem.out" 'expected exactly one pinned rmtfs process' 'non-pinned rmtfs reason'
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed against a non-pinned rmtfs process'
$BB rm "$R/proc/628/exe"
$BB mv "$R/tmp/rmtfs.exe.hidden" "$R/proc/628/exe"
$BB mv "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt" "$R/tmp/modem.mdt.hidden"
reject_stage modem "$BOOT" modem "$modem_token"
[ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'modem start armed before firmware was reachable'
$BB mv "$R/tmp/modem.mdt.hidden" "$R/proc/358/root/vendor/firmware_mnt/image/modem.mdt"
if [ "${SCRIPT##*/}" = pmos-radio-bringup-fresh.sh ]; then
	$BB touch "$R/vendor/firmware_mnt"
	reject_stage modem "$BOOT" modem "$modem_token"
	[ -f "$R/vendor/firmware_mnt" ] && [ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'regular file repair not refused'
	$BB rm "$R/vendor/firmware_mnt"
	$BB ln -s /tmp "$R/vendor/firmware_mnt"
	reject_stage modem "$BOOT" modem "$modem_token"
	[ -L "$R/vendor/firmware_mnt" ] && [ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'symlink repair not refused'
	$BB rm "$R/vendor/firmware_mnt"
	$BB mkdir -m 700 "$R/vendor/firmware_mnt"
	$BB touch "$R/vendor/firmware_mnt/.hidden"
	reject_stage modem "$BOOT" modem "$modem_token"
	[ -f "$R/vendor/firmware_mnt/.hidden" ] && [ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'nonempty repair not refused'
	$BB rm "$R/vendor/firmware_mnt/.hidden"
	$BB chmod 755 "$R/vendor/firmware_mnt"
	reject_stage modem "$BOOT" modem "$modem_token"
	[ -d "$R/vendor/firmware_mnt" ] && [ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'wrong-mode repair not refused'
	$BB chmod 700 "$R/vendor/firmware_mnt"
	$BB printf 'tmpfs /vendor/firmware_mnt tmpfs rw 0 0\n' >> "$R/proc/mounts"
	reject_stage modem "$BOOT" modem "$modem_token"
	[ -d "$R/vendor/firmware_mnt" ] && [ ! -e "$R/run/radio-bringup/modem.attempted" ] || fail 'mounted repair not refused'
	$BB sed -i '\|^tmpfs /vendor/firmware_mnt tmpfs |d' "$R/proc/mounts"
fi
$BB rm "$R/proc/628/root/boot/modemst1" "$R/proc/628/root/boot/modemst2" "$R/proc/628/root/dev/uio0" "$R/proc/628/root/dev/block/sdf2"
run_stage modem "$modem_token"
if [ "${SCRIPT##*/}" = pmos-radio-bringup-fresh.sh ]; then
	expect "$R/tmp/modem.out" 'removed the measured empty unmounted persistent firmware_mnt directory' 'empty repair not applied'
fi
expect "$R/tmp/modem.out" 'restored backing links: uio0 sdf2 modemst1 modemst2' 'cutover-deleted rmtfs paths not restored'
[ -c "$R/proc/628/root/dev/uio0" ] && [ -b "$R/proc/628/root/dev/block/sdf2" ] && [ -b "$R/proc/628/root/dev/block/sdf3" ] &&
	[ "$($BB readlink "$R/proc/628/root/boot/modemst1")" = /dev/block/sdf2 ] &&
	[ "$($BB readlink "$R/proc/628/root/boot/modemst2")" = /dev/block/sdf3 ] || fail 'rmtfs backing links not restored before start'
[ -r "$R/vendor/firmware_mnt/image/modem.mdt" ] || fail 'modem firmware not bound before start'
[ "$($BB cat "$R/sys/class/remoteproc/remoteproc2/state")" = running ] || fail 'modem not running'
run_stage modem "$modem_token"
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc2/state"
reject_stage modem "$BOOT" modem "$modem_token"
$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc2/state"

$BB rm "$R/dev/wlan"
$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB printf 'pmos-self-post: guest radio marker %s\n' "$wpss_token" >> "$R/tmp/dmesg.txt"
reject_stage wpss "$BOOT" wpss "$wpss_token"
expect "$R/tmp/wpss.out" 'no /dev/wlan and no valid live wlan class device' 'missing wlan class device accepted'
$BB printf '495:0\n' > "$R/sys/class/wlan/wlan/dev"
$BB printf 'Character devices:\n 496 qcwlanstate\nBlock devices:\n 495 qcwlanstate\n' > "$R/proc/devices"
reject_stage wpss "$BOOT" wpss "$wpss_token"
expect "$R/tmp/wpss.out" 'wlan class major does not match one character qcwlanstate' 'block or mismatched qcwlanstate major accepted'
[ ! -e "$R/dev/wlan" ] && [ ! -e "$R/run/radio-bringup/wpss.attempted" ] || fail 'wpss armed or left node on qcwlanstate major mismatch'
$BB printf 'Character devices:\n 495 qcwlanstate\nBlock devices:\n' > "$R/proc/devices"
$BB touch "$R/dev/wlan"
reject_stage wpss "$BOOT" wpss "$wpss_token"
expect "$R/tmp/wpss.out" '/dev/wlan is not a character node' 'non-character /dev/wlan accepted'
[ ! -e "$R/run/radio-bringup/wpss.attempted" ] || fail 'wpss armed with non-character /dev/wlan'
$BB rm "$R/dev/wlan"
$BB mknod -m 0600 "$R/dev/wlan" c 494 0
reject_stage wpss "$BOOT" wpss "$wpss_token"
expect "$R/tmp/wpss.out" 'existing /dev/wlan differs from live wlan class device or is not root-only' 'mismatched copied /dev/wlan accepted'
[ ! -e "$R/run/radio-bringup/wpss.attempted" ] || fail 'wpss armed with a mismatched /dev/wlan node'
$BB rm "$R/dev/wlan"
run_stage wpss "$wpss_token"
expect "$R/tmp/wpss.out" 'derived /dev/wlan character 495:0' 'wpss did not derive /dev/wlan from class device'
expect "$R/tmp/wpss.out" 'helper exit 10' 'wpss did not accept helper exit 10'
[ -c "$R/dev/wlan" ] && [ "$($BB stat -c '%t:%T:%a' "$R/dev/wlan")" = '1ef:0:600' ] || fail 'derived /dev/wlan node invalid'
[ "$($BB cat "$R/sys/class/remoteproc/remoteproc3/state")" = running ] || fail 'wpss not running'
$BB printf 'offline\n' > "$R/sys/class/remoteproc/remoteproc3/state"
reject_stage wpss "$BOOT" wpss "$wpss_token"
$BB printf 'running\n' > "$R/sys/class/remoteproc/remoteproc3/state"

$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB printf 'pmos-self-post: guest radio marker %s\n' "$driver_token" >> "$R/tmp/dmesg.txt"
run_stage driver "$driver_token"
[ "$($BB wc -l < "$R/tmp/mod.log")" -eq 3 ] || fail 'driver did not run insmod -> rmmod -> insmod'
[ -d "$R/sys/class/net/wlan0" ] && [ -d "$R/sys/class/ieee80211/phy0" ] || fail 'wlan0/phy0 not registered'
$BB rm -rf "$R/sys/class/net/wlan0"
reject_stage driver "$BOOT" driver "$driver_token"
$BB mkdir -p "$R/sys/class/net/wlan0"
$BB printf '0x1002\n' > "$R/sys/class/net/wlan0/flags"
$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB printf 'pmos-self-post: guest radio marker %s\n' "$scan_token" >> "$R/tmp/dmesg.txt"

run_stage scan "$scan_token"
expect "$R/tmp/scan.out" 'BSS count 2' 'scan count not reported'
[ "$($BB stat -c '%a' "$R/run/radio-bringup/scan.raw")" = 600 ] || fail 'scan output not root-only'
reject_stage scan "$BOOT" scan "$scan_token"

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
$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
$BB printf 'pmos-self-post: guest radio marker %s\n' "$services_token" >> "$R/tmp/dmesg.txt"
reject_stage services "$BOOT" services "$services_token"
expect "$R/tmp/services.out" 'OpenRC or /sbin/ip prerequisites changed' 'missing service prerequisites reason'
$BB rm "$R/bin/ip-bad"
$BB touch "$R/sbin/wpa_supplicant" "$R/sbin/ifup"
$BB chmod 755 "$R/sbin/wpa_supplicant" "$R/sbin/ifup"
for service in sshd udev tmpfs; do
	$BB ln -s "/etc/init.d/$service" "$R/etc/runlevels/default/$service"
	reject_stage services "$BOOT" services "$services_token"
	expect "$R/tmp/services.out" 'another OpenRC service enabled' "pre-enabled $service accepted"
	$BB rm "$R/etc/runlevels/default/$service"
done
$BB printf 'wpa_supplicant_args="-f /run/log"\n' > "$R/etc/conf.d/wpa_supplicant"
reject_stage services "$BOOT" services "$services_token"
expect "$R/tmp/services.out" 'unexpected supplicant arguments; no -f supported' 'supplicant -f accepted'
$BB printf 'wpa_supplicant_args=""\n' > "$R/etc/conf.d/wpa_supplicant"
$BB ln -s /sbin/ip "$R/bin/ip"
reject_stage services "$BOOT" services "$services_token"
expect "$R/tmp/services.out" 'OpenRC or /sbin/ip prerequisites changed' 'bin/ip not refused'
$BB rm "$R/bin/ip"
$BB mv "$R/run/dropbear-session.pid" "$R/tmp/ssh-pid.hidden"
reject_stage services "$BOOT" services "$services_token"
expect "$R/tmp/services.out" 'guest :2222 pidfile absent' 'missing guest SSH accepted'
$BB mv "$R/tmp/ssh-pid.hidden" "$R/run/dropbear-session.pid"
$BB printf 'fatal error received: mock\n' >> "$R/tmp/dmesg.txt"
reject_stage services "$BOOT" services "$services_token"
expect "$R/tmp/services.out" 'radio fatal in this boot' 'modem fatal accepted'
$BB printf 'icnss2_qmi: QMI DMS service connected\nicnss2: WLAN FW is ready\n' > "$R/tmp/dmesg.txt"
for stage in modem wpss driver services; do
	eval "token=\${${stage}_token}"
	$BB printf 'pmos-self-post: guest radio marker %s\n' "$token" >> "$R/tmp/dmesg.txt"
done
$BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services "$services_token" </dev/null > "$R/tmp/missing-profile.out" 2>&1 && fail 'missing profile accepted'
expect "$R/tmp/missing-profile.out" 'profile missing or not root-only' 'missing profile reason'
[ ! -e "$R/etc/wpa_supplicant/wpa_supplicant.conf" ] && [ ! -e "$R/etc/runlevels/default/networking" ] || fail 'missing profile enabled services'
$BB touch "$R/run/radio-bringup/wpa-fail"
$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="synthetic"\npsk="synthetic-only"\n}\n' | $BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services "$services_token" > "$R/tmp/wpa-fail.out" 2>&1 && fail 'failed wpa service accepted'
expect "$R/tmp/wpa-fail.out" 'wpa_supplicant first service error' 'first failed service not reported'
[ "$($BB cat "$R/run/radio-bringup/order")" = wpa ] && [ ! -e "$R/run/radio-bringup/networking.started" ] || fail 'networking attempted after wpa failure'
$BB rm "$R/run/radio-bringup/wpa-fail" "$R/run/radio-bringup/order" "$R/run/radio-bringup/services.attempted" "$R/etc/network/interfaces" "$R/etc/wpa_supplicant/wpa_supplicant.conf" "$R/etc/conf.d/networking" "$R/bin/run-parts" "$R/sbin/udhcpc" "$R/run/radio-bringup/ifquery-wlan" "$R/run/radio-bringup/lease-wrapper.sh" "$R/etc/runlevels/default/wpa_supplicant" "$R/etc/runlevels/default/networking"
$BB printf 'wpa_supplicant_args=""\n' > "$R/etc/conf.d/wpa_supplicant"
$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="synthetic"\npsk="synthetic-only"\n}\n' | $BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services "$services_token" > "$R/tmp/services-ok.out" 2>&1 || { $BB cat "$R/tmp/services-ok.out" >&2; fail 'services stage failed'; }
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
reject_stage services "$BOOT" services "$services_token"

if [ "${SCRIPT##*/}" = pmos-radio-bringup-persistent.sh ] || [ "${SCRIPT##*/}" = pmos-radio-bringup-fresh.sh ]; then
persistent_reboot() {
	$BB rm -f "$R/run/radio-bringup/services.attempted" "$R/run/radio-bringup/services-stdin" \
		"$R/run/radio-bringup/order" "$R/run/radio-bringup/wpa_supplicant.started" \
		"$R/run/radio-bringup/networking.started" "$R/run/radio-bringup/ifquery-wlan" \
		"$R/run/radio-bringup/lease-wrapper.sh"
}
run_persistent_services() {
	$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="synthetic"\npsk="synthetic-only"\n}\n' |
		$BB chroot "$R" /bin/busybox sh /radio.sh "$BOOT" services "$services_token" > "$R/tmp/$1.out" 2>&1
}
$BB cp "$R/etc/network/interfaces" "$R/tmp/interfaces.own"
$BB cp "$R/etc/wpa_supplicant/wpa_supplicant.conf" "$R/tmp/profile.own"

persistent_reboot
run_persistent_services services-persistent-ok || { $BB cat "$R/tmp/services-persistent-ok.out" >&2; fail 'persistent own-output services refused'; }
expect "$R/tmp/services-persistent-ok.out" 'OpenRC wpa_supplicant then networking started' 'persistent services summary missing'
[ "$($BB cat "$R/run/radio-bringup/order")" = 'wpa
net' ] || fail 'persistent services did not start wpa_supplicant then networking'
[ "$($BB cat "$R/run/radio-bringup/services.attempted")" = "$BOOT" ] || fail 'persistent services attempt not recorded'
$BB grep -q '^wpa_supplicant_if="wlan0"$' "$R/etc/conf.d/wpa_supplicant" || fail 'persistent own supplicant config changed'
[ "$($BB stat -c '%u:%a' "$R/run/radio-bringup/ifquery-wlan")" = 0:700 ] &&
	[ "$($BB stat -c '%u:%a' "$R/run/radio-bringup/lease-wrapper.sh")" = 0:700 ] || fail 'fresh-boot helpers not recreated root-only'
$BB cmp -s "$R/etc/network/interfaces" "$R/tmp/interfaces.own" || fail 'persistent interfaces not idempotent'
$BB cmp -s "$R/etc/wpa_supplicant/wpa_supplicant.conf" "$R/tmp/profile.own" || fail 'persistent profile not idempotent'

persistent_reboot
$BB touch "$R/run/radio-bringup/wpa_supplicant.started" "$R/run/radio-bringup/networking.started"
run_persistent_services services-persistent-started || { $BB cat "$R/tmp/services-persistent-started.out" >&2; fail 'already-started own services refused'; }

persistent_reboot
$BB printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan1"\n' > "$R/etc/conf.d/wpa_supplicant"
run_persistent_services services-foreign-conf && fail 'foreign supplicant interface accepted'
expect "$R/tmp/services-foreign-conf.out" 'unexpected supplicant arguments; no -f supported' 'foreign supplicant conf.d reason'
$BB printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan0"\n' > "$R/etc/conf.d/wpa_supplicant"

persistent_reboot
$BB chmod 666 "$R/etc/conf.d/wpa_supplicant"
run_persistent_services services-conf-mode && fail 'world-writable own supplicant conf.d accepted'
expect "$R/tmp/services-conf-mode.out" 'service input already exists' 'supplicant conf.d mode reason'
$BB chmod 600 "$R/etc/conf.d/wpa_supplicant"

persistent_reboot
$BB ln -s /etc/init.d/sshd "$R/etc/runlevels/default/sshd"
run_persistent_services services-foreign-runlevel && fail 'foreign enabled service accepted on persistent root'
expect "$R/tmp/services-foreign-runlevel.out" 'another OpenRC service enabled' 'foreign runlevel reason'
$BB rm "$R/etc/runlevels/default/sshd"

persistent_reboot
$BB rm "$R/etc/runlevels/default/wpa_supplicant"
$BB ln -s /etc/init.d/sshd "$R/etc/runlevels/default/wpa_supplicant"
run_persistent_services services-runlevel-target && fail 'modified own runlevel target accepted'
expect "$R/tmp/services-runlevel-target.out" 'another OpenRC service enabled' 'modified runlevel target reason'
$BB rm "$R/etc/runlevels/default/wpa_supplicant"
$BB ln -s /etc/init.d/wpa_supplicant "$R/etc/runlevels/default/wpa_supplicant"

persistent_reboot
$BB rm "$R/etc/runlevels/default/wpa_supplicant"
$BB touch "$R/run/radio-bringup/wpa_supplicant.started"
run_persistent_services services-started-foreign && fail 'started but not enabled service accepted'
expect "$R/tmp/services-started-foreign.out" 'unexpected OpenRC service state' 'started foreign service reason'
$BB ln -s /etc/init.d/wpa_supplicant "$R/etc/runlevels/default/wpa_supplicant"

persistent_reboot
$BB printf '# foreign lease change\n' >> "$R/run/radio-bringup/wlan-udhcpc-lease.sh"
run_persistent_services services-lease-modified && fail 'modified lease helper accepted'
expect "$R/tmp/services-lease-modified.out" 'pinned lease helper absent' 'modified lease helper reason'
$BB cp "$HERE/wlan-udhcpc-lease.sh" "$R/run/radio-bringup/wlan-udhcpc-lease.sh"
$BB chmod 700 "$R/run/radio-bringup/wlan-udhcpc-lease.sh"

persistent_reboot
$BB printf 'auto wlan1\n' > "$R/etc/network/interfaces"
run_persistent_services services-interfaces-modified && fail 'modified interfaces accepted'
expect "$R/tmp/services-interfaces-modified.out" 'service input already exists' 'modified interfaces reason'
$BB cp "$R/tmp/interfaces.own" "$R/etc/network/interfaces"
$BB chmod 600 "$R/etc/network/interfaces"

persistent_reboot
$BB rm "$R/bin/run-parts"
$BB ln -s /sbin/ip "$R/bin/run-parts"
run_persistent_services services-run-parts-foreign && fail 'foreign run-parts link accepted'
expect "$R/tmp/services-run-parts-foreign.out" 'service input already exists' 'foreign run-parts reason'
$BB rm "$R/bin/run-parts"
$BB ln -s busybox "$R/bin/run-parts"

persistent_reboot
$BB printf 'ctrl_interface=/run/wpa_supplicant\nnetwork={\nssid="other"\npsk="other-only"\n}\n' > "$R/etc/wpa_supplicant/wpa_supplicant.conf"
$BB chmod 600 "$R/etc/wpa_supplicant/wpa_supplicant.conf"
run_persistent_services services-profile-foreign && fail 'different persisted profile silently overwritten'
expect "$R/tmp/services-profile-foreign.out" 'persisted WLAN profile differs' 'foreign profile reason'
$BB cmp -s "$R/etc/wpa_supplicant/wpa_supplicant.conf" "$R/tmp/profile.own" && fail 'foreign profile was overwritten'
$BB cp "$R/tmp/profile.own" "$R/etc/wpa_supplicant/wpa_supplicant.conf"
$BB chmod 600 "$R/etc/wpa_supplicant/wpa_supplicant.conf"

persistent_reboot
run_persistent_services services-persistent-final || { $BB cat "$R/tmp/services-persistent-final.out" >&2; fail 'restored own-output state refused'; }
reject_stage services "$BOOT" services "$services_token"
expect "$R/tmp/services.out" 'services already attempted this boot; no retry' 'same-boot services retry reason'
else
	$BB printf 'pass (pinned installed variant, pristine archive only): host-only radio bring-up stages verified\n'
	exit 0
fi
$BB printf 'pass: host-only radio bring-up stages, one-shot guards, fail-closed /dev/wlan derivation, helper exit 10, single reload, root-only scan, pinned lease-helper staging, OpenRC wpa_supplicant/networking stage, pristine archive, persistent-root own-output replay (including already-started services) and foreign conf.d, runlevel, lease-helper, interfaces, run-parts and profile refusals verified\n'
