#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import lzma
import os
import pathlib
import re
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
TRACE_MSG = "self-post instrumentation is not trace-line-only"
INSTALLED_INIT = "f9449ba5590fd5955a85a6b97a0e21775aa34534197981b213bc380fe8378b0f"
INSTALLED_CARRIER = "a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3"
SELF_POST_BUNDLE_SHA = "5e118ffc4073752afc06eb6f0f2e603f28c2a50f44356ec842039321db5bd81f"
TRACE_MEMBER = "run/omnipha-self-post-trace.sh"
TRACE_PATH = "/" + TRACE_MEMBER
TRACE_BLOCK = re.compile(rb"# trace-begin\n.*?# trace-end\n", re.DOTALL)
TRACE_LINE = re.compile(rb"^[ \t]*trace(?:_state|_refusal)? ")
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
STAGED_RADIO_SHA = "f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f"
FRESH_RADIO_SHA = "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14"
GATED_POST_SHA = "113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3"
GATED_HOOK_SHA = "3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67"
FRESH_POST = "pmos-self-post-fresh-boot.sh"
FRESH_RADIO = "pmos-radio-bringup-fresh-boot.sh"
GATED_HOOK = "10-omnipha-self-stage.start"
GATED_NAMES = (FRESH_RADIO, FRESH_POST, GATED_HOOK)


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build-init-boot-self-stage.py", "persistent_self_stage")
CARRIER_PUBLIC = tuple(name for name in builder.PUBLIC if name != "pmos-self-post.sh")
CARRIER_NAMES = (*CARRIER_PUBLIC, "pmos-root-contract.sh", *GATED_NAMES)
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
                       "1765381ce0f2753aea208896342424ab5db7489c426d457a259f3398827cb587",
                       INSTALLED_INIT,
                       "27a78a225a840040f5e88b36f0ff75367caef3412ea26ac17ac83e24b4c23ce0",
                       "17531039e2c1bb36eac7c5fb2d4c343d53977950cbd2ade0d9dea6f3dd794bdd"))
REFUSED = REFUSED | frozenset((
    "ef476d8cbf3cba31fc143680d53b9aaf687cadd0409ad6dcf93c018bd97a233b",
    "2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28",
    "f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095",
    "3c97c918ed085d6d72530f00bba81c053130c184d351f372a10ac11b616bc71a",
    INSTALLED_CARRIER,
))
OUTPUT_MSG = "outputs must be separate, outside Git and different from every input"


def deinstrument(data):
    require(len(TRACE_BLOCK.findall(data)) == 1, TRACE_MSG)
    plain = TRACE_BLOCK.sub(b"", data, count=1)
    require(b"# trace-begin\n" not in plain and b"self-post-trace" not in plain, TRACE_MSG)
    kept = [line for line in plain.splitlines(keepends=True) if not TRACE_LINE.match(line)]
    plain = b"".join(kept)
    require(plain != data and plain.endswith(b"\n") and b"\0" not in plain, TRACE_MSG)
    require(not any(TRACE_LINE.match(line) for line in plain.splitlines()) and
            b"trace_refusal" not in plain, TRACE_MSG)
    return plain


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


PANEL_RECORD_RESTORE = b'''trace 'pre check panel record'
panel=/run/pmos-pre-ssh-panel.record
if [ ! -e "$panel" ] && [ ! -L "$panel" ] && [ -f /.omnipha-boot-record ] && [ ! -L /.omnipha-boot-record ]; then
\tpanel_hits=$($BB dmesg 2>/dev/null | $BB grep -E "^(\\[[ 0-9.]*\\] )?usb-init: usb-init: pre-SSH panel node=(boe|vxn|none) card0=[ -~]* boot $boot\\$" | $BB sed 's/^\\(\\[[ 0-9.]*\\] \\)\\{0,1\\}usb-init: //')
\tpanel_line=
\tif [ -n "$panel_hits" ] && [ "$($BB printf '%s\\n' "$panel_hits" | $BB sort -u | $BB wc -l)" = 1 ]; then
\t\tpanel_line=$($BB printf '%s\\n' "$panel_hits" | $BB sed -n 1p)
\tfi
\tif [ -n "$panel_line" ] && [ "${#panel_line}" -le 400 ] &&
\t\t[ "${panel_line% boot $boot}" != "$panel_line" ] &&
\t\t[ "$($BB sed -n 3p /.omnipha-boot-record 2>/dev/null)" = "$panel_line" ]; then
\t\t( umask 077; set -C; $BB printf '%s\\n' "$panel_line" > "$panel" ) || die 'cannot restore the pre-SSH panel record'
\t\t[ -f "$panel" ] && [ ! -L "$panel" ] && [ "$($BB stat -c '%u:%a:%h' "$panel")" = 0:600:1 ] ||
\t\t\tdie 'restored pre-SSH panel record is unsafe'
\t\ttrace 'panel record restored from the boot kernel log'
\tfi
fi
trace 'post check panel record'
'''


def without_nonce_wait(data):
    wait = b'''i=0
while [ ! -f "$GUARD/nonce" ] || [ -L "$GUARD/nonce" ]; do
\t[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] &&
\t\t[ ! -e "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
\t\t[ ! -e "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] ||
\t\tdie 'independent recovery guard is not armed and unacknowledged'
\t[ "$i" -lt 20 ] || die 'independent recovery guard is not armed and unacknowledged'
\t$BB sleep 1
\ti=$((i + 1))
done
'''
    fallback = b'[ -f "$contract" ] && [ ! -L "$contract" ] || contract="$GUARD/root-contract.sh"\n'
    restore_plain = b"".join(line for line in PANEL_RECORD_RESTORE.splitlines(keepends=True)
                             if not TRACE_LINE.match(line))
    return replace_once(replace_once(replace_once(data, wait, b""), fallback, b""), restore_plain, b"")


def persistent_installer():
    body = b'''chain_dir=/run/omnipha-self-stage
( [ -f /run/pmos-root-contract.sh ] && [ ! -L /run/pmos-root-contract.sh ] &&
	. /run/pmos-root-contract.sh && root_contract_pinned_userdata "$GUEST" &&
	case ",$ROOT_CONTRACT_OPTS," in *,rw,*) true;; *) false;; esac ) || die 'persistent chain root is not pinned read-write userdata'
chain_root_dev=$($BB stat -c '%d' "$GUEST") || die 'cannot inspect chain root'
for chain_parent in "$GUEST" "$GUEST/usr" "$GUEST/etc" "$GUEST/etc/local.d"; do
	[ -d "$chain_parent" ] && [ ! -L "$chain_parent" ] || die 'unsafe persistent chain parent'
	case "$($BB stat -c '%u:%g:%a:%d' "$chain_parent")" in
		"0:0:700:$chain_root_dev"|"0:0:755:$chain_root_dev") :;;
		"0:0:775:$chain_root_dev") [ "$chain_parent" = "$GUEST/etc" ] || die 'unsafe persistent chain parent metadata';;
		*) die 'unsafe persistent chain parent metadata';;
	esac
done
$BB awk -v r="$GUEST" '
	$5 != r && (index($5, r "/usr/") == 1 || $5 == r "/usr" ||
		index($5, r "/etc/") == 1 || $5 == r "/etc") {bad++}
	END {exit(bad != 0)}
' /proc/self/mountinfo || die 'nested mount in persistent chain parents'
for chain_parent in "$GUEST/usr/libexec" "$GUEST/usr/libexec/omnipha"; do
	if [ ! -e "$chain_parent" ] && [ ! -L "$chain_parent" ]; then
		$BB mkdir -m 700 "$chain_parent" || die 'cannot create persistent chain directory'
	fi
	[ -d "$chain_parent" ] && [ ! -L "$chain_parent" ] || die 'unsafe persistent chain directory'
	case "$($BB stat -c '%u:%g:%a:%d' "$chain_parent")" in
		"0:0:700:$chain_root_dev"|"0:0:755:$chain_root_dev") :;;
		*) die 'unsafe persistent chain directory metadata';;
	esac
done
[ -d "$chain_dir" ] && [ ! -L "$chain_dir" ] &&
	[ "$($BB stat -c '%u:%g:%a' "$chain_dir")" = 0:0:700 ] || die 'unsafe carrier payload directory'
chain_check() {
	[ -f "$1" ] && [ ! -L "$1" ] &&
		[ "$($BB stat -c '%u:%g:%a:%h' "$1")" = "0:0:$2:1" ] &&
		[ "$($BB sha256sum "$1" 2>/dev/null | $BB cut -d ' ' -f 1)" = "$3" ]
}
for chain_spec in \\
	"pmos-radio-bringup-fresh-boot.sh /usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh @RADIO@" \\
	"pmos-self-post-fresh-boot.sh /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh @POST@" \\
	"10-omnipha-self-stage.start /etc/local.d/10-omnipha-self-stage.start @HOOK@"; do
	set -- $chain_spec
	chain_check "$chain_dir/$1" 700 "$3" || die 'unpinned carrier payload'
	chain_target="$GUEST$2"
	if [ -e "$chain_target" ] || [ -L "$chain_target" ]; then
		chain_check "$chain_target" 700 "$3" || die 'untrusted persistent chain file'
	fi
	[ ! -e "$chain_target.omnipha-new" ] && [ ! -L "$chain_target.omnipha-new" ] ||
		die 'persistent chain staging path already exists'
done
for chain_hook in "$GUEST"/etc/local.d/*.start; do
	[ ! -e "$chain_hook" ] && [ ! -L "$chain_hook" ] && continue
	[ "$chain_hook" = "$GUEST/etc/local.d/10-omnipha-self-stage.start" ] || die 'unexpected local startup hook'
done
for chain_spec in \\
	"pmos-radio-bringup-fresh-boot.sh /usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh @RADIO@" \\
	"pmos-self-post-fresh-boot.sh /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh @POST@" \\
	"10-omnipha-self-stage.start /etc/local.d/10-omnipha-self-stage.start @HOOK@"; do
	set -- $chain_spec
	chain_target="$GUEST$2"
	if [ ! -e "$chain_target" ] && [ ! -L "$chain_target" ]; then
		(umask 077; set -C; $BB cat "$chain_dir/$1" > "$chain_target.omnipha-new") || die 'cannot stage chain file'
		chain_check "$chain_target.omnipha-new" 600 "$3" || die 'staged chain file invalid'
		$BB chmod 700 "$chain_target.omnipha-new" || die 'cannot protect staged chain file'
		chain_check "$chain_target.omnipha-new" 700 "$3" || die 'protected chain file invalid'
		chain_inode=$($BB stat -c '%d:%i' "$chain_target.omnipha-new") || die 'staged chain inode unavailable'
		$BB ln -T "$chain_target.omnipha-new" "$chain_target" ||
			die 'cannot publish chain file without replacement'
		[ ! -L "$chain_target" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_target")" = "$chain_inode:0:0:700:2" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_target.omnipha-new")" = "$chain_inode:0:0:700:2" ] ||
			die 'published chain inode changed'
		$BB rm "$chain_target.omnipha-new" || die 'cannot complete chain publication'
	fi
	chain_check "$chain_target" 700 "$3" || die 'installed chain file invalid'
done
for chain_spec in \\
	"/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh @RADIO@" \\
	"/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh @POST@" \\
	"/etc/local.d/10-omnipha-self-stage.start @HOOK@"; do
	set -- $chain_spec
	chain_check "$GUEST$1" 700 "$2" || die 'persistent chain changed after installation'
done
'''
    for token, digest in ((b"@RADIO@", FRESH_RADIO_SHA), (b"@POST@", GATED_POST_SHA),
                          (b"@HOOK@", GATED_HOOK_SHA)):
        body = body.replace(token, digest.encode())
    return body


def current_scripts():
    original = {name: script_bytes(name) for name in ROOT_NAMES}
    plain_post = deinstrument(original["pmos-self-post.sh"])
    carrier_post = without_nonce_wait(plain_post)
    require(hashlib.sha256(carrier_post).hexdigest() ==
            "fe98c0d284906cd2e4fa843153f15a844a8ca8b9f3d301f772bab6233e410bab", DELTA_MSG)
    expected = {
        "pmos-root-contract.sh": "c76c31ff148ab19ff5b2de6f1e40a036ee6ec275d54b0b5d1eaab0bbf0f06cc6",
        "pmos-session-stage.sh": "be70a27305145cabc15b70469ae7a0434fab352fb9c3d681943f73d22b92938a",
        "pmos-pid1-transition.sh": "af42a763d6a84a4cae3dddfa576a9affa5b84f57b6e64e2b41636cc690883be7",
        "pmos-pid1-guard.sh": "dcc4124dd404823f891e683d455177613d91afc2bd91582835cc1d6bbe118243",
        "pmos-self-post.sh": "eb3c2cb6509246c14142bebe4bf4318b159057faff43b03be7588557fcf7323f",
        "pmos-radio-bringup.sh": "7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812",
        "pmos-self-stage.sh": "ae9a0d98c9c7d75f56333c24f1b4b4267ca1ad612efd007698c017d5a9218c90",
    }
    require(hashlib.sha256(plain_post).hexdigest() == expected["pmos-self-post.sh"] and
            {name: hashlib.sha256(data).hexdigest() for name, data in original.items()
             if name != "pmos-self-post.sh"} ==
            {name: digest for name, digest in expected.items() if name != "pmos-self-post.sh"}, DELTA_MSG)
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
        b'\t\t\t[ -f "$hook" ] && [ ! -L "$hook" ] && [ "$($BB stat -c \'%u:%g:%a:%h\' "$hook")" = 0:0:700:1 ] &&\n'
        b'\t\t\t[ "$($BB sha256sum "$hook" | $BB cut -d \' \' -f 1)" = ' + GATED_HOOK_SHA.encode() + b' ] ||\n'
        b'\t\t\tdie "unexpected local startup hook"\n'
        b'\t}')

    stage = replace_once(stage, b'$BB ln -s /etc/init.d/local "$PMOS_ROOT/etc/runlevels/default/local" || die "cannot enable RAM-only local service"',
        b'if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then\n'
        b'\tfor service in wpa_supplicant networking; do\n'
        b'\t\tentry="$PMOS_ROOT/etc/runlevels/default/$service"\n'
        b'\t\tif [ -e "$entry" ] || [ -L "$entry" ]; then\n'
        b'\t\t\t[ -L "$entry" ] && [ "$($BB readlink "$entry")" = "/etc/init.d/$service" ] ||\n'
        b'\t\t\t\tdie "unexpected enabled OpenRC service"\n'
        b'\t\t\t$BB rm "$entry" || die "cannot defer OpenRC service"\n'
        b'\t\t\t[ ! -e "$entry" ] && [ ! -L "$entry" ] || die "OpenRC service still enabled"\n'
        b'\t\tfi\n'
        b'\tdone\n'
        b'fi\n'
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
    require(hashlib.sha256(radio).hexdigest() == STAGED_RADIO_SHA, DELTA_MSG)
    found["pmos-radio-bringup.sh"] = radio
    radio_pin = b"RADIO_SHA=" + hashlib.sha256(radio).hexdigest().encode()
    traced_post = replace_once(original["pmos-self-post.sh"],
        b"RADIO_SHA=7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812", radio_pin)
    found["pmos-self-post.sh"] = replace_once(carrier_post,
        b"RADIO_SHA=7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812", radio_pin)
    require(without_nonce_wait(deinstrument(traced_post)) == found["pmos-self-post.sh"] and
            hashlib.sha256(found["pmos-self-post.sh"]).hexdigest() == SELF_POST_BUNDLE_SHA and
            hashlib.sha256(traced_post).hexdigest() != SELF_POST_BUNDLE_SHA and
            sum(1 for line in traced_post.splitlines() if TRACE_LINE.match(line)) >= 25 and
            traced_post.count(b"self-post-trace") >= 5 and
            traced_post.count(b"boot_record_append /") == 2 and
            traced_post.count(b"boot_record_verify /") == 1, DELTA_MSG)
    found["pmos-self-post-trace"] = traced_post
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
    self_stage = replace_once(self_stage,
        b'''post_sha=$(hash /run/pmos-self-post.sh)
$BB cp /run/pmos-radio-bringup.sh /run/pmos/run/radio-bringup/pmos-radio-bringup.sh
$BB chmod 700 /run/pmos/run/radio-bringup/pmos-radio-bringup.sh
[ "$(hash /run/pmos/run/radio-bringup/pmos-radio-bringup.sh)" = "$RADIO_SHA" ] ||
	die 'guest radio script digest mismatch'
$BB cp /run/pmos-self-post.sh /run/pmos/run/radio-bringup/pmos-self-post.sh
$BB chmod 700 /run/pmos/run/radio-bringup/pmos-self-post.sh
[ "$(hash /run/pmos/run/radio-bringup/pmos-self-post.sh)" = "$post_sha" ] ||
	die 'guest post-cutover helper digest mismatch'
''', b'')
    self_stage = replace_once(self_stage, b'''hook=/run/pmos/etc/local.d/10-omnipha-self-stage.start
[ ! -e "$hook" ] && [ ! -L "$hook" ] || die 'local.d startup hook already exists'
$BB printf '%s\\n' '#!/bin/busybox sh' '( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )' > "$hook"
$BB chmod 700 "$hook"
[ "$($BB stat -c '%u:%a' "$hook")" = 0:700 ] || die 'local.d startup hook mode invalid'
''', b'')
    self_stage = replace_once(self_stage,
        b'''$BB sh /run/pmos-radio-bringup.sh "$boot" prepare || die 'pmos-radio-bringup prepare failed'
''', persistent_installer() + b'''$BB sh /run/pmos-radio-bringup.sh "$boot" prepare || die 'pmos-radio-bringup prepare failed'
''')
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
            self_stage.index(b"record_line \"pmos-self-stage: staged postmarketOS root") and
            self_stage.index(b"pin_session_hostkey\n") <
            self_stage.index(b"chain_dir=/run/omnipha-self-stage") <
            self_stage.index(b"pmos-radio-bringup prepare failed") <
            self_stage.index(b"PID 1 request already exists") and
            b"/run/wpa_supplicant.conf /run/pmos/run/radio-bringup/wpa_supplicant.conf" in self_stage and
            b"local.d startup hook already exists" not in self_stage,
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
            stream = archive.extractfile(item)
            if stream is None:
                raise ValueError(builder.BUNDLE_MSG)
            data = stream.read()
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
    for name, digest in ((FRESH_RADIO, FRESH_RADIO_SHA), (FRESH_POST, GATED_POST_SHA),
                         (GATED_HOOK, GATED_HOOK_SHA), ("pmos-radio-bringup.sh", FRESH_RADIO_SHA)):
        require(name in found and hashlib.sha256(found[name]).hexdigest() == digest, DELTA_MSG)
    for name in PRESERVED:
        require(found[name] == base_found[name], DELTA_MSG)
    for name in builder.PUBLIC:
        if name not in ROOT_NAMES and name not in PRESERVED:
            require(found[name] == base_found[name], DELTA_MSG)
    return found


def pins(found):
    lines = [f"stage {name} {hashlib.sha256(found[name]).hexdigest()} 700" for name in CARRIER_PUBLIC]
    lines.append(f'stage pmos-root-contract.sh {hashlib.sha256(found["pmos-root-contract.sh"]).hexdigest()} 700')
    for name in GATED_NAMES:
        lines.append(f"stage {name} {hashlib.sha256(found[name]).hexdigest()} 700")
    lines.append(f'$BB chmod 600 "$D/{builder.PRIVATE}" || exit 0')
    return "\n".join(lines).encode()


def hook(found, blob):
    body = builder.HOOK.replace(b"@PINS@", pins(found), 1)
    body = replace_once(body,
        b'$BB mv "$D/pmos-self-post.sh" /run/pmos-self-post.sh || exit 0\n', b'')
    body = body.replace(b'$BB mkdir -m 700 "$D" || exit 0\n',
                        b'$BB mkdir -m 700 "$D" || exit 0\n' + carrier_reader(blob), 1)
    body = body.replace(
        b'$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0\n',
        b'$BB mv "$D/pmos-root-contract.sh" /run/pmos-root-contract.sh || exit 0\n'
        b'$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0\n', 1)
    body = body.replace(
        b'setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n',
        b'T=' + TRACE_PATH.encode() + b'\n'
        b'got=$($BB sha256sum "$T" 2>/dev/null | $BB cut -d " " -f 1)\n'
        b'[ "$got" = ' + hashlib.sha256(found["pmos-self-post-trace"]).hexdigest().encode() + b' ] || exit 0\n'
        b'$BB chmod 700 "$T" || exit 0\n'
        b'$BB mv "$T" /run/pmos-self-post.sh || exit 0\n'
        b'[ ! -e /run/keep ] && [ ! -L /run/keep ] || exit 0\n'
        b'$BB touch /run/keep || exit 0\n'
        b'$BB chmod 600 /run/keep || exit 0\n'
        b'[ -f /run/keep ] && [ ! -L /run/keep ] &&\n'
        b'\t[ "$($BB stat -c "%u:%a:%h" /run/keep)" = 0:600:1 ] || exit 0\n'
        b'setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n', 1)
    require(body.count(b"@PINS@") == 0 and body.count(b"pmos-root-contract.sh") == 3 and
            body.count(b"/run/keep") == 7 and body.count(b"sleep 150") == 0 and
            body.count(b"151.01") == 0 and body.count(carrier_reader(blob)) == 1 and
            body.index(b'touch /run/keep') < body.index(b'setsid /bin/busybox sh /run/pmos-self-stage.sh') and
            body.count(b'mv "$T" /run/pmos-self-post.sh') == 1 and
            body.index(b'mv "$T" /run/pmos-self-post.sh') < body.index(b'touch /run/keep') and
            body.count(b'mv "$D/pmos-self-post.sh"') == 0,
            INIT_MSG)
    return body


def gated_artifacts(staged_radio, source_post, probe):
    require(hashlib.sha256(staged_radio).hexdigest() == STAGED_RADIO_SHA, DELTA_MSG)
    persist = load("derive-radio-persistent.py", "persistent_radio_derive")
    fresh = load("derive-radio-fresh-boot.py", "fresh_radio_derive")
    selfpost = load("derive-self-post-fresh-boot.py", "fresh_post_derive")
    gate = load("derive-success-gated-ack.py", "gate_derive")
    radio = fresh.derive(persist.derive(staged_radio.decode())).encode()
    require(hashlib.sha256(radio).hexdigest() == FRESH_RADIO_SHA, DELTA_MSG)
    prefix, _ = selfpost.derive(source_post.decode(), radio)
    post, hook = (value.encode() for value in gate.derive(prefix, radio, probe))
    require(hashlib.sha256(post).hexdigest() == GATED_POST_SHA and
            hashlib.sha256(hook).hexdigest() == GATED_HOOK_SHA, DELTA_MSG)
    return {FRESH_RADIO: radio, FRESH_POST: post, GATED_HOOK: hook}


def runtime_scripts():
    current = current_scripts()
    gate = load("derive-success-gated-ack.py", "runtime_gate_derive")
    artifacts = gated_artifacts(current["pmos-radio-bringup.sh"],
                                script_bytes("pmos-self-post.sh"), gate.build_dns_probe())
    current["pmos-radio-bringup.sh"] = artifacts[FRESH_RADIO]
    current["pmos-self-stage.sh"] = replace_once(
        current["pmos-self-stage.sh"], b"RADIO_SHA=" + STAGED_RADIO_SHA.encode(),
        b"RADIO_SHA=" + FRESH_RADIO_SHA.encode())
    current.update(artifacts)
    return current


def carrier_bundle(found, private):
    names = CARRIER_NAMES
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
    template = next(entry for entry in entries if entry["name"] == builder.BUNDLE)
    fields = list(template["fields"])
    fields[1] = 0o100700
    changed.append({"name": TRACE_MEMBER, "mode": 0o100700, "fields": fields,
                    "data": found["pmos-self-post-trace"]})
    cpio = modules.encode_newc(changed, trailer)
    decoded, new_trailer = modules.parse_newc(cpio, "persistent-root generic cpio")
    require(new_trailer == trailer and [item["name"] for item in decoded] ==
            [item["name"] for item in changed] and
            decoded[-1]["name"] == TRACE_MEMBER and
            decoded[-1]["data"] == found["pmos-self-post-trace"], CPIO_MSG)
    return cpio


def frame_for(cpio, library):
    block = base.compress_hc(library, cpio, base.HC_LEVEL)
    frame = base.LZ4_MAGIC + struct.pack("<I", len(block)) + block
    require(base.decompress(library, block, len(cpio)) == cpio and len(frame) <= base.MAX_FRAME, FRAME_MSG)
    return frame


def check_digests(init_digest, carrier_digest):
    require(init_digest not in REFUSED and carrier_digest not in REFUSED and
            init_digest != carrier_digest and init_digest != CARRIER_SHA and
            carrier_digest != CARRIER_SHA, SHA_MSG)


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
    check_digests(digest, carrier_digest)
    return image, carrier, digest, carrier_digest, len(cpio), len(frame), entries, trailer, found, private


def output_paths(output, carrier_output, inputs):
    targets = (output.resolve(), carrier_output.resolve())
    inputs = tuple(path.resolve() for path in inputs)
    require(len(set(targets)) == 2 and not any(target.is_relative_to(HERE.parent.resolve()) or
            target in inputs for target in targets) and
            all(not path.is_symlink() and path.parent.is_dir() and not path.is_dir()
                for path in (output, carrier_output)), OUTPUT_MSG)


def write_pair(output, carrier_output, inputs, image, carrier):
    output_paths(output, carrier_output, (*inputs, PROFILE))
    streams = []
    created = []
    try:
        for path in (output, carrier_output):
            new_file = False
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                new_file = True
            except FileExistsError:
                fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            stream = os.fdopen(fd, "wb")
            streams.append(stream)
            if new_file:
                info = os.fstat(fd)
                created.append((path, info.st_dev, info.st_ino))
                os.fchmod(fd, 0o600)
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                    info.st_nlink == 1 and info.st_size == 0 and
                    stat.S_IMODE(info.st_mode) == 0o600,
                    "output must be an empty owner-only regular file with one link")
        for stream, data in zip(streams, (image, carrier)):
            stream.write(data)
            stream.flush()
    except BaseException:
        for stream in streams:
            stream.close()
        for path, device, inode in created:
            try:
                info = path.lstat()
                if info.st_dev == device and info.st_ino == inode:
                    path.unlink()
            except FileNotFoundError:
                pass
        raise
    else:
        for stream in streams:
            stream.close()


def main():
    args = sys.argv[1:]
    require(len(args) == 6 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-persistent-root.py --preflight|--build STOCK_INIT BASE STOCK_VENDOR_B INIT_OUTPUT CARRIER_OUTPUT")
    stock_path, base_path, carrier_path, output, carrier_output = map(pathlib.Path, args[1:])
    require(base_path.resolve() == BASE_IMAGE.resolve(), BASE_MSG)
    inputs = (stock_path, base_path, carrier_path)
    if args[0] == "--build":
        output_paths(output, carrier_output, (*inputs, PROFILE))
    current = runtime_scripts()
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "persistent_decode")
    image, carrier, digest, carrier_digest, cpio_size, frame_size, *_rest = build(
        stock_path.read_bytes(), base_path.read_bytes(), current, base.lz4(),
        checker.hostkey_checker.decode_frame, carrier_path.read_bytes())
    print(f"cpio: {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame: {frame_size}/{base.MAX_FRAME}")
    print(f"init_boot: {len(image)} bytes, SHA-256 {digest}")
    print(f"{CARRIER}: {len(carrier)} bytes, SHA-256 {carrier_digest}")
    if args[0] == "--build":
        write_pair(output, carrier_output, inputs, image, carrier)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
