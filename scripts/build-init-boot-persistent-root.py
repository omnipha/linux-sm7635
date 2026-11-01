#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import lzma
import os
import pathlib
import stat
import struct
import sys
import tarfile

HERE = pathlib.Path(__file__).parent
PROFILE = pathlib.Path.home() / ".omnipha" / "sm7635" / "wpa_supplicant.conf"
BASE_IMAGE = pathlib.Path.home() / "sm7635-build" / "out" / "init_boot-mindstorms-wlan.img"
CARRIER = "vendor_boot_b"
CARRIER_SIZE = 100663296
CARRIER_SHA = "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253"
CARRIER_PREFIX = 18256512
CARRIER_HEADER = 18870272
CARRIER_OFFSET = 18874368
CARRIER_MARKER = b"OMNIPHA_VENDOR_BOOT_B_ROOT_CONTRACT_V1"
CARRIER_MSG = "carrier is not the pinned vendor_boot_b root-contract image"
RUN66 = "5b5a60d4ceaf1551217874136c0de9a26f6b3ec29f9f586e2b7cdf0d728466d6"
RUN66_LEASE = "1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56"
BASE_MSG = "base is not the installed run-66 init_boot"
DELTA_MSG = "functional delta is not the pinned userdata ext4 root"
FRAME_MSG = "ramdisk is not one reproducible LZ4 HC-12 block inside the stock envelope"
CPIO_MSG = "cpio must change only /init and one root-only self-stage bundle"
INIT_MSG = "init must keep the measured run-66 handoff and change only the root-contract pin"
SHA_MSG = "candidate repeats a stock, measured or refused image SHA-256"
ROOT_NAMES = (
    "pmos-root-contract.sh",
    "pmos-session-stage.sh",
    "pmos-pid1-transition.sh",
    "pmos-pid1-guard.sh",
    "pmos-self-post.sh",
    "pmos-radio-bringup.sh",
    "pmos-self-stage.sh",
)
PRESERVED = ("wlan-udhcpc-lease.sh",)


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build-init-boot-self-stage.py", "persistent_self_stage")
modules = builder.modules
base = builder.base
vendor = builder.vendor
require = builder.require
REFUSED = frozenset((*builder.REFUSED, RUN66,
                      "3192278b93812ff14cf7d71d4f8bae60a7e00d178c194155fc336817a6c4bcdf",
                      "ab3a0e6360269d1e56d14626e6849b8249634810895f5270283ed30ebdb4a5a9",
                      "becd37846fedd0d4298cf562667fd498f76a5c99e2e68810ca5cacf8c1ee72b4",
                      "adb47dc0228cdbb1ba57dd245ecec49386d53bf24c3ab8f72493e709b78aeae8",
                      "fcb0ed91c83461be1f22df859c2f9b331e72d31a576fcf33876de6c3136c2e0d",
                      "3eeddb35eb32b29323f50bab673c7acc36b029373e911eb4d74a3aa180236522",
                      "762566b758494c53b0265ce7eee13155c6d06b9cca44f8c5eb75ce7cb8fc4e5d",
                      "a4ee7def41e645301f59bdc4dc043c97253a4002d8774016ee3557633b0cb6e3",
                      "6e7c5a2e26981fc19c9eba97356d1a52f80e768cb6b9536bc9cb4fd906a8c59e",
                       "dd6ce74e47827814c3c0010d6c71f0b9d0874a370cb147bb455e05f018ed6f41",
                       "e7d5558037b903de3ab817619ce527319f6b54fb4ec97782e729078c666268fc",
                       "27c4d8959ffdb5154aaa11bdf508ec7a1d81fe3cffbaaeb66bfe52b31365b21c",
                       "da4651d827cad181e55baf1bd9ddb9876fcc271b791c5046362ef056ea69c9c6",
                       "fed40c3073663b9bc5ff29e35e09ae1afdb8568cadf27e09c7e956f284c33c2d",
                       "1765381ce0f2753aea208896342424ab5db7489c426d457a259f3398827cb587"))


def regular(path):
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600


def profile_bytes():
    require(PROFILE.is_file() and not PROFILE.is_symlink() and PROFILE.stat().st_uid == os.getuid() and
            regular(PROFILE) and PROFILE.stat().st_size > 0, builder.PROFILE_MSG)
    return PROFILE.read_bytes()


def script_bytes(name):
    path = HERE / name
    require(path.is_file() and not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode) and
            path.stat().st_size > 0 and not path.stat().st_mode & 0o002, builder.SCRIPT_MSG)
    data = path.read_bytes()
    require(data.startswith(b"#!/bin/busybox sh\n") and b"\0" not in data, builder.SCRIPT_MSG)
    return data


def replace_once(data, old, new):
    require(data.count(old) == 1, DELTA_MSG)
    return data.replace(old, new, 1)


def current_scripts():
    original = {name: script_bytes(name) for name in ROOT_NAMES}
    expected = {
        "pmos-root-contract.sh": "c76c31ff148ab19ff5b2de6f1e40a036ee6ec275d54b0b5d1eaab0bbf0f06cc6",
        "pmos-session-stage.sh": "be70a27305145cabc15b70469ae7a0434fab352fb9c3d681943f73d22b92938a",
        "pmos-pid1-transition.sh": "e1dba7135e2335c22aee0a5c0f4edb247fad5acd8100377cba3771abe5044e36",
        "pmos-pid1-guard.sh": "f72a68a4c3a0e9bb7e72aa88883dcc9087a684985f5af688e34ea13c0226d3ad",
        "pmos-self-post.sh": "fe98c0d284906cd2e4fa843153f15a844a8ca8b9f3d301f772bab6233e410bab",
        "pmos-radio-bringup.sh": "7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812",
        "pmos-self-stage.sh": "92e9045894df3da3db2b093aebc03840a63d8e2b4b89c6cffc835b62d10614c6",
    }
    require({name: hashlib.sha256(data).hexdigest() for name, data in original.items()} == expected, DELTA_MSG)
    found = dict(original)
    transition = replace_once(found["pmos-pid1-transition.sh"],
        b"log 'pid1 transition guard armed; exec switch_root to postmarketOS init'\n",
        b'''boot_record_append "$ROOT" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || { fail 'boot record append refused'; return 1; }
boot_record_verify "$ROOT" 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || { fail 'boot record verify refused'; return 1; }
log 'pid1 transition guard armed; exec switch_root to postmarketOS init'
''')
    require(transition.count(b"boot_record_verify") == 1 and
            transition.index(b"boot_record_verify") < transition.index(b"exec /bin/busybox switch_root"),
            DELTA_MSG)
    found["pmos-pid1-transition.sh"] = transition
    stage = found["pmos-session-stage.sh"]
    stage = replace_once(stage, b'''[ -f "$PMOS_TARBALL" ] && [ ! -L "$PMOS_TARBALL" ] || die "missing or symlinked staged tarball $PMOS_TARBALL"
[ "$($BB stat -c %a "$PMOS_TARBALL")" = 600 ] || die "staged tarball not root-only"
$BB printf '%s  %s\\n' "$PMOS_SHA256" "$PMOS_TARBALL" | $BB sha256sum -c - ||
	die "tarball SHA-256 mismatch"
log "tarball SHA-256 verified"''',
        b'''if [ "${PMOS_ROOT_KIND:-tmpfs}" != ext4 ]; then
	[ -f "$PMOS_TARBALL" ] && [ ! -L "$PMOS_TARBALL" ] || die "missing or symlinked staged tarball $PMOS_TARBALL"
	[ "$($BB stat -c %a "$PMOS_TARBALL")" = 600 ] || die "staged tarball not root-only"
	$BB printf '%s  %s\\n' "$PMOS_SHA256" "$PMOS_TARBALL" | $BB sha256sum -c - ||
		die "tarball SHA-256 mismatch"
	log "tarball SHA-256 verified"
fi''')
    stage = replace_once(stage, b'die() { log "FAIL: $*"; exit 1; }\n',
        b'''die() { log "FAIL: $*"; exit 1; }
record_stage() {
	[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] || return 0
	boot_record_append "$PMOS_ROOT" "pmos-stage: $*" || die 'boot record append refused'
}
''')
    stage = replace_once(stage,
        b'root_contract_stage_root "$PMOS_ROOT" || die "guest root is not a separate 256m tmpfs"\n',
        b'''root_contract_stage_root "$PMOS_ROOT" || die "guest root is not a separate 256m tmpfs"
if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then
	boot_record_open "$PMOS_ROOT" || die 'boot record open refused'
	boot_record_id || die 'boot record boot ID invalid'
	boot_record_append "$PMOS_ROOT" "pmos-self-stage: diagnostic hold and :22 verified on boot $br_boot" || die 'boot record hold append refused'
fi
''')
    stage = replace_once(stage, b'$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"',
        b'if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then\n'
        b'\tlog "using unpacked persistent postmarketOS root"\n'
        b'\trecord_stage "using unpacked persistent postmarketOS root"\n'
        b'else\n'
        b'\t$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"\n'
        b'fi')
    stage = replace_once(stage, b'[ ! -e "$PMOS_ROOT/sbin/init" ] && [ ! -L "$PMOS_ROOT/sbin/init" ] || die "guest init already exists"',
        b'[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] ||\n'
        b'\t{ [ ! -e "$PMOS_ROOT/sbin/init" ] && [ ! -L "$PMOS_ROOT/sbin/init" ] || die "guest init already exists"; }')
    stage = replace_once(stage, b'\t\t[ ! -e "$entry" ] && [ ! -L "$entry" ] || die "unexpected enabled OpenRC service"',
        b'\t\t[ ! -e "$entry" ] && [ ! -L "$entry" ] || {\n'
        b'\t\t\t[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] && {\n'
        b'\t\t\t\tcase "$entry" in\n'
        b'\t\t\t\t\t"$PMOS_ROOT/etc/runlevels/default/local")\n'
        b'\t\t\t\t\t\t[ "$($BB readlink "$entry")" = /etc/init.d/local ] || die "unexpected enabled OpenRC service" ;;\n'
        b'\t\t\t\t\t"$PMOS_ROOT/etc/runlevels/default/wpa_supplicant")\n'
        b'\t\t\t\t\t\t[ "$($BB readlink "$entry")" = /etc/init.d/wpa_supplicant ] || die "unexpected enabled OpenRC service" ;;\n'
        b'\t\t\t\t\t"$PMOS_ROOT/etc/runlevels/default/networking")\n'
        b'\t\t\t\t\t\t[ "$($BB readlink "$entry")" = /etc/init.d/networking ] || die "unexpected enabled OpenRC service" ;;\n'
        b'\t\t\t\t\t*) die "unexpected enabled OpenRC service" ;;\n'
        b'\t\t\t\tesac\n'
        b'\t\t\t} || die "unexpected enabled OpenRC service"\n'
        b'\t\t}')
    stage = replace_once(stage, b'\t[ ! -e "$hook" ] && [ ! -L "$hook" ] || die "unexpected local startup hook"',
        b'\t[ ! -e "$hook" ] && [ ! -L "$hook" ] || {\n'
        b'\t\t[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] &&\n'
        b'\t\t\t[ "$hook" = "$PMOS_ROOT/etc/local.d/10-omnipha-self-stage.start" ] &&\n'
        b'\t\t\t[ -f "$hook" ] && [ ! -L "$hook" ] && [ "$($BB stat -c \'%u:%a\' "$hook")" = 0:700 ] ||\n'
        b'\t\t\tdie "unexpected local startup hook"\n'
        b'\t}')
    stage = replace_once(stage, b'$BB ln -s /etc/init.d/local "$PMOS_ROOT/etc/runlevels/default/local" || die "cannot enable RAM-only local service"',
        b'if [ ! -e "$PMOS_ROOT/etc/runlevels/default/local" ] &&\n'
        b'\t[ ! -L "$PMOS_ROOT/etc/runlevels/default/local" ]; then\n'
        b'\t$BB ln -s /etc/init.d/local "$PMOS_ROOT/etc/runlevels/default/local" || die "cannot enable RAM-only local service"\n'
        b'fi')
    stage = replace_once(stage, b'$BB ln -s ../bin/busybox "$PMOS_ROOT/sbin/init" || die "cannot link guest init"',
        b'if [ ! -e "$PMOS_ROOT/sbin/init" ] && [ ! -L "$PMOS_ROOT/sbin/init" ]; then\n'
        b'\t$BB ln -s ../bin/busybox "$PMOS_ROOT/sbin/init" || die "cannot link guest init"\n'
        b'fi')
    stage = replace_once(stage, b'$BB chroot "$PMOS_ROOT" /usr/bin/dropbearkey -t ed25519 -f /etc/dropbear/session_host_key \\',
        b'if [ -e "$PMOS_ROOT/etc/dropbear/session_host_key" ] || [ -L "$PMOS_ROOT/etc/dropbear/session_host_key" ]; then\n'
        b'\t[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] && [ -f "$PMOS_ROOT/etc/dropbear/session_host_key" ] &&\n'
        b'\t\t[ ! -L "$PMOS_ROOT/etc/dropbear/session_host_key" ] &&\n'
        b'\t\t[ "$($BB stat -c \'%u:%a\' "$PMOS_ROOT/etc/dropbear/session_host_key")" = 0:600 ] ||\n'
        b'\t\tdie "persistent guest host key is unsafe"\n'
        b'\t$BB rm -f "$PMOS_ROOT/etc/dropbear/session_host_key"\n'
        b'fi\n'
        b'$BB chroot "$PMOS_ROOT" /usr/bin/dropbearkey -t ed25519 -f /etc/dropbear/session_host_key \\')
    stage = replace_once(stage,
        b'log "mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts"\n',
        b'log "mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts"\nrecord_stage "mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts"\n')
    stage = replace_once(stage,
        b'log "second key-only SSH listening on 172.16.42.2:$PMOS_SSH_PORT (diagnostic :22 untouched)"\n',
        b'log "second key-only SSH listening on 172.16.42.2:$PMOS_SSH_PORT (diagnostic :22 untouched)"\nrecord_stage "second key-only SSH listening on 172.16.42.2:$PMOS_SSH_PORT (diagnostic :22 untouched)"\n')
    stage = replace_once(stage,
        b'log "STAGED ok; enter with: ssh -p $PMOS_SSH_PORT root@172.16.42.2 (accept the printed key)"\n',
        b'log "STAGED ok; enter with: ssh -p $PMOS_SSH_PORT root@172.16.42.2 (accept the printed key)"\nrecord_stage "STAGED ok; enter with: ssh -p $PMOS_SSH_PORT root@172.16.42.2 (accept the printed key)"\n')
    stage = replace_once(stage,
        b'''if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then
	boot_record_open "$PMOS_ROOT" || die 'boot record open refused'
	boot_record_id || die 'boot record boot ID invalid'
	boot_record_append "$PMOS_ROOT" "pmos-self-stage: diagnostic hold and :22 verified on boot $br_boot" || die 'boot record hold append refused'
fi''',
        b'''if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then
	boot_record_open "$PMOS_ROOT" || die 'boot record open refused'
	boot_record_id || die 'boot record boot ID invalid'
	boot_record_append "$PMOS_ROOT" "pmos-self-stage: diagnostic hold and :22 verified on boot $br_boot" || die 'boot record hold append refused'
	[ -f /run/pre-ssh-panel.record ] && [ ! -L /run/pre-ssh-panel.record ] &&
		[ "$($BB stat -c '%u:%a:%h' /run/pre-ssh-panel.record)" = 0:600:1 ] ||
		die 'pre-SSH panel record missing or unsafe'
	$BB cp /run/pre-ssh-panel.record /run/pmos-pre-ssh-panel.record ||
		die 'cannot preserve pre-SSH panel record'
	$BB chmod 600 /run/pmos-pre-ssh-panel.record || die 'cannot protect pre-SSH panel record'
	panel_line=$($BB cat /run/pmos-pre-ssh-panel.record) || die 'pre-SSH panel record unreadable'
	boot_record_append "$PMOS_ROOT" "$panel_line" || die 'pre-SSH panel record append refused'
fi''')
    require(stage.count(b"record_stage") == 5 and stage.count(b"boot_record_open") == 1 and
            stage.count(b"/run/pre-ssh-panel.record") == 4 and
            stage.count(b"/run/pmos-pre-ssh-panel.record") == 3, DELTA_MSG)
    found["pmos-session-stage.sh"] = stage
    radio = replace_once(found["pmos-radio-bringup.sh"],
        b"LEASE_SHA=86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896",
        b"LEASE_SHA=" + RUN66_LEASE.encode())
    radio = replace_once(radio, b'\t[ ! -e /run/pmos/vendor ] && [ ! -L /run/pmos/vendor ] || fail \'guest vendor path already exists\'',
        b'\t[ -d /run/pmos/vendor ] && [ ! -L /run/pmos/vendor ] || fail \'guest vendor path invalid\'')
    radio = replace_once(radio, b'\t$BB ln -s /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini /run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini',
        b'\tif [ ! -L /run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini ]; then\n'
        b'\t\t[ ! -e /run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini ] ||\n'
        b'\t\t\tfail \'persistent INI firmware link invalid\'\n'
        b'\t\t$BB ln -s /vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini /run/pmos/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini\n'
        b'\tfi')
    radio = replace_once(radio, b'services() {\n\tstage=services\n\tcapture_gate',
        b'services() {\n\tstage=services\n\tcapture_gate\n'
        b'\tif [ -f /etc/network/interfaces ] && [ -f /etc/wpa_supplicant/wpa_supplicant.conf ] &&\n'
        b'\t\t/sbin/rc-service networking status >/dev/null 2>&1 &&\n'
        b'\t\t/sbin/rc-service wpa_supplicant status >/dev/null 2>&1; then\n'
        b'\t\treport \'persistent OpenRC WLAN services already running; no reinstall\'\n'
        b'\t\treturn 0\n'
        b'\tfi')
    radio = replace_once(radio,
        b"\treport 'stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover'\n\texit 0",
        b'''\treport 'stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover'
	if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then
		[ -f /run/pmos-root-contract.sh ] && [ ! -L /run/pmos-root-contract.sh ] ||
			fail 'boot record contract unavailable'
		. /run/pmos-root-contract.sh
		boot_record_append /run/pmos 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' || fail 'boot record append refused'
	fi
	exit 0''')
    require(radio.count(b"boot_record_append") == 1, DELTA_MSG)
    found["pmos-radio-bringup.sh"] = radio
    found["pmos-self-post.sh"] = replace_once(found["pmos-self-post.sh"],
        b"RADIO_SHA=7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812",
        b"RADIO_SHA=" + hashlib.sha256(radio).hexdigest().encode())
    self_stage = replace_once(found["pmos-self-stage.sh"],
        b'die() { log "FAIL: $*"; exit 1; }\n',
        b'''die() { log "FAIL: $*"; exit 1; }
record_line() {
	[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] || return 0
	CONTRACT=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
	[ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] && . "$CONTRACT" || die 'boot record contract unavailable'
	case "$1" in
		open) boot_record_open "$GUEST" || die 'boot record open refused';;
		*) boot_record_append "$GUEST" "$1" || die "boot record append refused: $1";;
	esac
}
''')

    self_stage = replace_once(self_stage,
        b"\tlog 'guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request'\n}",
        b"\tlog 'guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request'\n\trecord_line 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request'\n}")
    self_stage = replace_once(self_stage,
        b'log "staged postmarketOS root and armed PID 1 request for boot $boot"\n',
        b'log "staged postmarketOS root and armed PID 1 request for boot $boot"\nrecord_line "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot"\n')
    start = self_stage.index(b"part_dev=\npart_count=0\n")
    end_marker = b"$BB sh /run/pmos-session-stage.sh || die 'pmos-session-stage failed'"
    end = self_stage.index(end_marker, start) + len(end_marker)
    direct = b'''part_dev=
part_count=0
for uevent in /sys/class/block/*/uevent; do
	[ -r "$uevent" ] || continue
	if [ "$($BB sed -n 's/^PARTNAME=//p' "$uevent" 2>/dev/null)" = userdata ]; then
		dir=${uevent%/uevent}
		part_dev=${dir##*/}
		part_count=$((part_count + 1))
	fi
done
[ "$part_count" = 1 ] && [ -n "$part_dev" ] ||
	die "expected one userdata PARTNAME in sysfs, found $part_count"
devnum=$($BB cat "/sys/class/block/$part_dev/dev" 2>/dev/null) || devnum=
case "$devnum" in [0-9]*:[0-9]*) :;; *) die 'userdata device numbers invalid';; esac
major=${devnum%%:*}
minor=${devnum##*:}
$BB mkdir -p /dev/block
node="/dev/block/$part_dev"
if [ -b "$node" ]; then
	[ ! -L "$node" ] || die 'userdata block path is a symlink'
	[ "$($BB stat -c '%t:%T' "$node")" = "$($BB printf '%x:%x' "$major" "$minor")" ] ||
		die 'userdata block node numbers differ from sysfs'
else
	[ ! -e "$node" ] && [ ! -L "$node" ] || die 'userdata path is not a block node'
	$BB mknod -m 0400 "$node" b "$major" "$minor" || die 'cannot create userdata block node'
fi
[ "$($BB stat -c '%t:%T' "$node")" = "$($BB printf '%x:%x' "$major" "$minor")" ] ||
	die 'userdata node verification failed'
size=$($BB timeout -k 1 2 $BB blockdev --getsize64 "$node" 2>/dev/null) || size=
[ "$size" -ge "$PART_SIZE" ] 2>/dev/null || die "userdata size below image (${size:-unknown})"
[ ! -e "$GUEST" ] && [ ! -L "$GUEST" ] || die 'persistent root path already exists'
$BB mkdir -m 700 "$GUEST" || die 'cannot create persistent root path'
$BB timeout -k 1 5 $BB mount -t ext4 -o ro,noload "$node" "$GUEST" 2>/dev/null ||
	{ $BB rmdir "$GUEST" 2>/dev/null || true; die 'cannot mount userdata read-only without journal replay'; }
[ "$($BB awk -v m="$GUEST" '$2 == m && $3 == "ext4" && $4 ~ /(^|,)ro(,|$)/ && $4 ~ /(^|,)(noload|norecovery)(,|$)/ {n++} END {print n+0}' /proc/mounts)" = 1 ] ||
	{ $BB umount "$GUEST" 2>/dev/null || true; $BB rmdir "$GUEST" 2>/dev/null || true; die 'userdata mount is not read-only ext4 with noload'; }
PMOS_ROOT_KIND=ext4 $BB sh /run/pmos-session-stage.sh || die 'pmos-session-stage failed'
log "mounted pinned persistent root from read-only $node ($part_dev) and verified its root contract"
PMOS_ROOT_KIND=ext4
export PMOS_ROOT_KIND
record_line "pmos-self-stage: mounted pinned persistent root from read-only $node ($part_dev) and verified its root contract"
'''
    self_stage = self_stage[:start] + direct + self_stage[end:]
    self_stage = replace_once(self_stage, b'$BB rm -f "$TARBALL"\n', b'')
    self_stage = replace_once(self_stage, b'''[ ! -e "$hook" ] && [ ! -L "$hook" ] || die 'local.d startup hook already exists'
$BB printf '%s\\n' '#!/bin/busybox sh' '( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )' > "$hook"
$BB chmod 700 "$hook"''',
        b'''if [ -e "$hook" ] || [ -L "$hook" ]; then
	[ -f "$hook" ] && [ ! -L "$hook" ] && [ "$($BB stat -c '%u:%a' "$hook")" = 0:700 ] || die 'persistent local.d startup hook invalid'
else
	$BB printf '%s\\n' '#!/bin/busybox sh' '( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )' > "$hook"
	$BB chmod 700 "$hook"
fi''')
    pins_by_name = {
        "STAGE_SHA": found["pmos-session-stage.sh"],
        "TRANSITION_SHA": found["pmos-pid1-transition.sh"],
        "GUARD_SHA": found["pmos-pid1-guard.sh"],
        "RADIO_SHA": found["pmos-radio-bringup.sh"],
        "LEASE_SHA": b"lease",
    }
    for pin, data in pins_by_name.items():
        digest = RUN66_LEASE if pin == "LEASE_SHA" else hashlib.sha256(data).hexdigest()
        self_stage = __import__("re").sub(
            pin.encode() + b"=[0-9a-f]{64}", pin.encode() + b"=" + digest.encode(), self_stage, count=1)
    require(b"STAGE_SHA=be70a273" not in self_stage and b"LEASE_SHA=86ebff" not in self_stage and
            b"PMOS_ROOT_KIND=ext4 " in self_stage and b'"$wait_n" -lt 145' in self_stage and
            self_stage.count(b"record_line") == 4 and
            self_stage.index(b"record_line \"pmos-self-stage: mounted pinned persistent root") <
            self_stage.index(b"record_line \"pmos-self-stage: staged postmarketOS root"),
            DELTA_MSG)
    found["pmos-self-stage.sh"] = self_stage
    return found


def unpack_image(image, library, decode_frame):
    require(len(image) == base.IMAGE_SIZE and image[:8] == b"ANDROID!" and
            struct.unpack_from("<I", image, 40)[0] == 4 and
            struct.unpack_from("<I", image, 8)[0] == 0, BASE_MSG)
    size = struct.unpack_from("<I", image, base.RAMDISK_SIZE_OFFSET)[0]
    require(8 < size <= base.MAX_FRAME and not any(image[base.PAGE + size:base.TAIL_OFFSET]), FRAME_MSG)
    frame = image[base.PAGE:base.PAGE + size]
    decoded = decode_frame(frame, library)
    require(vendor.encode_frame(decoded, library) == frame, FRAME_MSG)
    entries, trailer = modules.parse_newc(decoded, "persistent-root generic cpio")
    return entries, trailer, frame


def bundle_map(blob, names):
    require(blob.startswith(b"\xfd7zXZ\x00"), builder.BUNDLE_MSG)
    raw = lzma.decompress(blob, format=lzma.FORMAT_XZ)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        infos = archive.getmembers()
        require([item.name for item in infos] == sorted(names), builder.BUNDLE_MSG)
        found = {}
        private = b""
        for item in infos:
            data = archive.extractfile(item).read()
            mode = 0o600 if item.name == builder.PRIVATE else 0o700
            require(item.isfile() and not item.issym() and item.mode == mode and item.uid == 0 and
                    item.gid == 0 and item.mtime == 0 and item.uname == "" and item.gname == "" and
                    data.startswith(b"#!/bin/busybox sh\n" if item.name != builder.PRIVATE else b""),
                    builder.BUNDLE_MSG)
            if item.name == builder.PRIVATE:
                private = data
            else:
                found[item.name] = data
    require(private and set(found) == set(builder.PUBLIC), builder.BUNDLE_MSG)
    return found, private


def base_state(base_image, library, decode_frame):
    require(modules.sha256(base_image) == RUN66, BASE_MSG)
    entries, trailer, _frame = unpack_image(base_image, library, decode_frame)
    names = [entry["name"] for entry in entries]
    require(len(set(names)) == len(names) and names.count("init") == 1 and
            names.count(builder.BUNDLE) == 1, BASE_MSG)
    found, private = bundle_map(next(entry["data"] for entry in entries if entry["name"] == builder.BUNDLE),
                                (*builder.PUBLIC, builder.PRIVATE))
    require(hashlib.sha256(found["wlan-udhcpc-lease.sh"]).hexdigest() == RUN66_LEASE and
            private == profile_bytes() and
            b"root_contract_" not in b"".join(found.values()), BASE_MSG)
    return entries, trailer, found, private


def expected_found(base_found, current):
    found = dict(base_found)
    found.update(current)
    for name in PRESERVED:
        require(found[name] == base_found[name], DELTA_MSG)
    for name in builder.PUBLIC:
        if name not in ROOT_NAMES and name not in PRESERVED:
            require(found[name] == base_found[name], DELTA_MSG)
    return found


def pins(found):
    lines = [f"stage {name} {hashlib.sha256(found[name]).hexdigest()} 700" for name in builder.PUBLIC]
    lines.append(f'stage pmos-root-contract.sh {hashlib.sha256(found["pmos-root-contract.sh"]).hexdigest()} 700')
    lines.append(f'$BB chmod 600 "$D/{builder.PRIVATE}" || exit 0')
    return "\n".join(lines).encode()


def hook(found, blob):
    body = builder.HOOK.replace(b"@PINS@", pins(found), 1)
    body = body.replace(b'$BB mkdir -m 700 "$D" || exit 0\n',
                        b'$BB mkdir -m 700 "$D" || exit 0\n' + carrier_reader(blob), 1)
    body = body.replace(
        b'$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0\n',
        b'$BB mv "$D/pmos-root-contract.sh" /run/pmos-root-contract.sh || exit 0\n'
        b'$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0\n', 1)
    body = body.replace(
        b'setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n',
        b'[ ! -e /run/keep ] && [ ! -L /run/keep ] || exit 0\n'
        b'$BB touch /run/keep || exit 0\n'
        b'$BB chmod 600 /run/keep || exit 0\n'
        b'[ -f /run/keep ] && [ ! -L /run/keep ] &&\n'
        b'\t[ "$($BB stat -c "%u:%a:%h" /run/keep)" = 0:600:1 ] || exit 0\n'
        b'setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n', 1)
    require(body.count(b"@PINS@") == 0 and body.count(b"pmos-root-contract.sh") == 3 and
            body.count(b"/run/keep") == 7 and body.count(b"sleep 150") == 0 and
            body.count(b"151.01") == 0 and body.count(carrier_reader(blob)) == 1 and
            body.index(b'touch /run/keep') < body.index(b'setsid /bin/busybox sh /run/pmos-self-stage.sh'),
            INIT_MSG)
    return body


def carrier_bundle(found, private):
    names = (*builder.PUBLIC, "pmos-root-contract.sh")
    public = {name: found[name] for name in names}
    return builder.checked_bundle(builder.bundle_bytes(public, private, names), public, private, names)


def carrier_header(blob):
    text = (CARRIER_MARKER + b"\nsize=" + str(len(blob)).encode() + b"\nsha256=" +
            hashlib.sha256(blob).hexdigest().encode() + b"\n")
    require(len(text) <= 4096, CARRIER_MSG)
    return text + bytes(4096 - len(text))


def carrier_image(stock, blob):
    require(len(stock) == CARRIER_SIZE and hashlib.sha256(stock).hexdigest() == CARRIER_SHA and
            stock[:8] == b"VNDRBOOT" and stock[18255872:18255876] == b"AVB0" and
            stock[-64:-60] == b"AVBf" and not any(stock[CARRIER_PREFIX:-64]) and
            CARRIER_PREFIX <= CARRIER_HEADER and CARRIER_HEADER + 4096 == CARRIER_OFFSET and
            CARRIER_OFFSET + len(blob) <= CARRIER_SIZE - 64, CARRIER_MSG)
    result = bytearray(stock)
    result[CARRIER_HEADER:CARRIER_OFFSET] = carrier_header(blob)
    result[CARRIER_OFFSET:CARRIER_OFFSET + len(blob)] = blob
    return bytes(result)


def carrier_reader(blob):
    size = len(blob)
    header_sha = hashlib.sha256(carrier_header(blob)).hexdigest()
    bundle_sha = hashlib.sha256(blob).hexdigest()
    return f'''part=
part_count=0
for uevent in /sys/class/block/*/uevent; do
    [ -r "$uevent" ] || continue
    [ "$($BB sed -n "s/^PARTNAME=//p" "$uevent" 2>/dev/null)" = {CARRIER} ] || continue
    part=${{uevent%/uevent}}
    part=${{part##*/}}
    part_count=$((part_count + 1))
done
[ "$part_count" = 1 ] && [ -n "$part" ] || exit 0
    case "$part" in *[!A-Za-z0-9_-]*) exit 0 ;; esac
devnum=$($BB cat "/sys/class/block/$part/dev" 2>/dev/null) || exit 0
    case "$devnum" in [0-9]*:[0-9]*) : ;; *) exit 0 ;; esac
major=${{devnum%%:*}}
minor=${{devnum##*:}}
    case "$major:$minor" in *[!0-9:]*|0:*|*:|:*) exit 0 ;; esac
$BB mkdir -p /dev/block || exit 0
node=/dev/block/$part
if [ ! -b "$node" ]; then
    [ ! -e "$node" ] && [ ! -L "$node" ] || exit 0
    $BB mknod -m 0400 "$node" b "$major" "$minor" || exit 0
fi
    [ ! -L "$node" ] && [ "$($BB stat -c "%t:%T" "$node")" = "$($BB printf "%x:%x" "$major" "$minor")" ] || exit 0
[ "$($BB timeout -k 1 2 $BB blockdev --getsize64 "$node" 2>/dev/null)" = {CARRIER_SIZE} ] || exit 0
hdr=/run/{CARRIER}.header
[ ! -e "$hdr" ] && [ ! -L "$hdr" ] || exit 0
$BB timeout -k 1 5 $BB dd if="$node" of="$hdr" bs=4096 skip={CARRIER_HEADER // 4096} count=1 2>/dev/null || exit 0
    [ "$($BB stat -c "%u:%a:%s" "$hdr")" = 0:600:4096 ] &&
    [ "$($BB sha256sum "$hdr" | $BB cut -d " " -f 1)" = {header_sha} ] || exit 0
$BB rm -f "$hdr" || exit 0
[ ! -e "$B" ] && [ ! -L "$B" ] || exit 0
$BB timeout -k 1 5 $BB dd if="$node" of="$B" bs=4096 skip={CARRIER_OFFSET // 4096} count={size // 4096} 2>/dev/null || exit 0
page=/run/{CARRIER}.page
[ ! -e "$page" ] && [ ! -L "$page" ] || exit 0
$BB timeout -k 1 5 $BB dd if="$node" of="$page" bs=4096 skip={(CARRIER_OFFSET + (size // 4096) * 4096) // 4096} count=1 2>/dev/null || exit 0
$BB dd if="$page" of="$B" bs=1 seek={(size // 4096) * 4096} count={size % 4096} conv=notrunc 2>/dev/null || exit 0
$BB rm -f "$page" || exit 0
    [ "$($BB stat -c "%u:%a:%s" "$B")" = 0:600:{size} ] &&
    [ "$($BB sha256sum "$B" | $BB cut -d " " -f 1)" = {bundle_sha} ] || exit 0
'''.encode()


def display_phase():
    return b'''DISPLAY_MODULES='
qti_battery_charger.ko
panel_event_notifier.ko
hwmon.ko
qti_amoled_ecm.ko
qseecom_proxy.ko
smcinvoke_dlkm.ko
hdcp_qseecom_dlkm.ko
sync_fence.ko
nt_display_notifier.ko
llcc-qcom.ko
msm_ext_display.ko
drm_display_helper.ko
gh_mem_notifier.ko
gh_irq_lend.ko
altmode-glink.ko
fsa4480-i2c.ko
qpnp-amoled-regulator.ko
qcom-spmi-wled.ko
msm_drm.ko
'
log 'display module load begin'
for module in $DISPLAY_MODULES; do
	panel_opt=
	[ "$module" = msm_drm.ko ] &&
		panel_opt='dsi_display0=qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe:'
	if err=$(insmod "/lib/modules/$module" $panel_opt 2>&1); then
		log "display module $module loaded"
	else
		log "display module $module failed: $err"
	fi
done
log 'display module load end'
dp_card0=0
dp_dsi1=0
dp_bl=none
dp_suspend=clear
dp_dcs=none
dp_reset=none
dp_node=none
[ -d /sys/class/drm/card0 ] && dp_card0=1
[ -d /sys/class/drm/card0-DSI-1 ] && dp_dsi1=1
for bl in /sys/class/backlight/*; do
	[ -e "$bl/actual_brightness" ] || continue
	case "$bl" in *panel0-backlight*)
		dp_bl=$(cat "$bl/actual_brightness" 2>/dev/null) || dp_bl=none
		case "$dp_bl" in ''|*[!0-9]*) dp_bl=none;; esac;;
	esac
done
/bin/busybox dmesg >/run/display-init.dmesg 2>/dev/null || true
if /bin/busybox grep -q 'suspend state' /run/display-init.dmesg 2>/dev/null; then
	dp_suspend=suspend-state
fi
if /bin/busybox grep -qE 'DSI_CMD_SET|dsi_panel_tx_cmd_set|failed to send DSI_CMD' /run/display-init.dmesg 2>/dev/null; then
	dp_dcs=init-ran
fi
if /bin/busybox grep -qE 'dsi_panel.*reset|reset_gpio' /run/display-init.dmesg 2>/dev/null; then
	dp_reset=seen
fi
if /bin/busybox grep -q "Successfully bind display panel 'qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe " /run/display-init.dmesg 2>/dev/null; then
	dp_node=boe
elif /bin/busybox grep -q "Successfully bind display panel 'qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_vxn " /run/display-init.dmesg 2>/dev/null; then
	dp_node=vxn
fi
panel_line="usb-init: pre-SSH panel node=$dp_node card0=$dp_card0 dsi1=$dp_dsi1 dcs=$dp_dcs reset=$dp_reset suspend=$dp_suspend brightness=$dp_bl boot $(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
log "$panel_line"
(umask 077; printf '%s\\n' "$panel_line" >/run/pre-ssh-panel.record)
chmod 600 /run/pre-ssh-panel.record

'''


def expected_init(original, found, blob):
    anchor = b"mkdir -p /etc/dropbear /var/run\n"
    original = replace_once(original, anchor, display_phase() + anchor)
    require(display_phase() in original, INIT_MSG)
    marker = b"setsid cttyhack /bin/sh &\n"
    start = original.index(marker) + len(marker)
    end = original.index(b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n' >/dev/null 2>&1 &\n", start)
    end += len(b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n' >/dev/null 2>&1 &\n")
    require(original.count(marker) == 1 and original.count(b"@PINS@") == 0, INIT_MSG)
    old_sha = b"0b85d1dc3c05b58f703618994363a9d0dbd09ecf8139573d2db15628d2497549"
    new_sha = hashlib.sha256(found["pmos-pid1-transition.sh"]).hexdigest().encode()
    require(original.count(old_sha) == 2, INIT_MSG)
    handoff = original[end:]
    require(handoff.count(old_sha) == 1, INIT_MSG)
    preserved = replace_once(handoff, old_sha, new_sha)
    return original[:start] + hook(found, blob) + preserved


def candidate_cpio(entries, trailer, found, private):
    original = next(entry["data"] for entry in entries if entry["name"] == "init")
    blob = carrier_bundle(found, private)
    init = expected_init(original, found, blob)
    changed = [{**entry, "data": init} if entry["name"] == "init" else entry
               for entry in entries if entry["name"] != builder.BUNDLE]
    cpio = modules.encode_newc(changed, trailer)
    decoded, new_trailer = modules.parse_newc(cpio, "persistent-root generic cpio")
    require(new_trailer == trailer and [item["name"] for item in decoded] ==
            [item["name"] for item in changed], CPIO_MSG)
    return cpio


def frame_for(cpio, library):
    block = base.compress_hc(library, cpio, base.HC_LEVEL)
    frame = base.LZ4_MAGIC + struct.pack("<I", len(block)) + block
    require(base.decompress(library, block, len(cpio)) == cpio and len(frame) <= base.MAX_FRAME, FRAME_MSG)
    return frame


def build(stock, base_image, current, library, decode_frame, stock_carrier):
    vendor.check_stock(stock, library)
    require(base_image[:base.RAMDISK_SIZE_OFFSET] == stock[:base.RAMDISK_SIZE_OFFSET] and
            base_image[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
            base_image[base.TAIL_OFFSET:] == stock[base.TAIL_OFFSET:], BASE_MSG)
    entries, trailer, base_found, private = base_state(base_image, library, decode_frame)
    found = expected_found(base_found, current)
    blob = carrier_bundle(found, private)
    carrier = carrier_image(stock_carrier, blob)
    cpio = candidate_cpio(entries, trailer, found, private)
    frame = frame_for(cpio, library)
    image, digest = vendor.assemble(stock, frame)
    carrier_digest = hashlib.sha256(carrier).hexdigest()
    require(digest not in REFUSED and carrier_digest not in REFUSED and
            digest != carrier_digest and carrier_digest != CARRIER_SHA, SHA_MSG)
    return image, carrier, digest, carrier_digest, len(cpio), len(frame), entries, trailer, found, private


def main():
    args = sys.argv[1:]
    require(len(args) == 6 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-persistent-root.py --preflight|--build STOCK_INIT BASE STOCK_VENDOR_B INIT_OUTPUT CARRIER_OUTPUT")
    stock_path, base_path, carrier_path, output, carrier_output = map(pathlib.Path, args[1:])
    require(base_path.resolve() == BASE_IMAGE.resolve(), BASE_MSG)
    if args[0] == "--build":
        targets = (output.resolve(), carrier_output.resolve())
        inputs = (stock_path.resolve(), base_path.resolve(), carrier_path.resolve())
        require(len(set(targets)) == 2 and not any(target.is_relative_to(HERE.parent.resolve()) or
                target in inputs for target in targets) and not output.is_symlink() and
                not carrier_output.is_symlink() and output.parent.is_dir() and
                carrier_output.parent.is_dir() and not output.is_dir() and
                not carrier_output.is_dir(), "outputs must be outside Git and different from every input")
    current = current_scripts()
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "persistent_decode")
    image, carrier, digest, carrier_digest, cpio_size, frame_size, *_rest = build(
        stock_path.read_bytes(), base_path.read_bytes(), current, base.lz4(),
        checker.hostkey_checker.decode_frame, carrier_path.read_bytes())
    print(f"cpio: {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame: {frame_size}/{base.MAX_FRAME}")
    print(f"init_boot: {len(image)} bytes, SHA-256 {digest}")
    print(f"{CARRIER}: {len(carrier)} bytes, SHA-256 {carrier_digest}")
    if args[0] == "--build":
        output.write_bytes(image)
        carrier_output.write_bytes(carrier)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
