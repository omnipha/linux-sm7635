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
REFUSED = frozenset((*builder.REFUSED, RUN66, "fcb0ed91c83461be1f22df859c2f9b331e72d31a576fcf33876de6c3136c2e0d"))


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
        "pmos-root-contract.sh": "2e95e9d3bef9b38dc71bd132f7054f0a558208800b8e918a34e7b0ec20a5c94c",
        "pmos-session-stage.sh": "be70a27305145cabc15b70469ae7a0434fab352fb9c3d681943f73d22b92938a",
        "pmos-pid1-transition.sh": "176422c5536025749d9ffdd306df7ff2dfdd213be0674b24bb4fff4775f8b415",
        "pmos-pid1-guard.sh": "2a92fbcfe029ec3be1af8b73d4cd8d0ac317ecd267a9dc9ba9637932207d5da3",
        "pmos-self-post.sh": "2d5847f38d6c58e4ac048cfb628dbe8e8b530df8522316d6ce0f1129758ce17a",
        "pmos-radio-bringup.sh": "04fe93d76c5048122f1a413457c0e0f1b1abd13f78f3518d8bb12abb18762dd1",
        "pmos-self-stage.sh": "fec98717681aba52e64344a4dba43f6bdf8907c3f11aaab10e9bfd46530afa92",
    }
    require({name: hashlib.sha256(data).hexdigest() for name, data in original.items()} == expected, DELTA_MSG)
    found = dict(original)
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
    stage = replace_once(stage, b'$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"',
        b'if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then\n'
        b'\tlog "using unpacked persistent postmarketOS root"\n'
        b'else\n'
        b'\t$BB tar -xzf "$PMOS_TARBALL" -C "$PMOS_ROOT" || die "extraction failed"\n'
        b'fi')
    stage = replace_once(stage, b'[ ! -e "$PMOS_ROOT/sbin/init" ] && [ ! -L "$PMOS_ROOT/sbin/init" ] || die "guest init already exists"',
        b'[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] ||\n'
        b'\t{ [ ! -e "$PMOS_ROOT/sbin/init" ] && [ ! -L "$PMOS_ROOT/sbin/init" ] || die "guest init already exists"; }')
    stage = replace_once(stage, b'\t\t[ ! -e "$entry" ] && [ ! -L "$entry" ] || die "unexpected enabled OpenRC service"',
        b'\t\t[ ! -e "$entry" ] && [ ! -L "$entry" ] || {\n'
        b'\t\t\t[ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ] && [ "$entry" = "$PMOS_ROOT/etc/runlevels/default/local" ] &&\n'
        b'\t\t\t\t[ "$($BB readlink "$entry")" = /etc/init.d/local ] || die "unexpected enabled OpenRC service"\n'
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
    found["pmos-radio-bringup.sh"] = radio
    found["pmos-self-post.sh"] = replace_once(found["pmos-self-post.sh"],
        b"RADIO_SHA=04fe93d76c5048122f1a413457c0e0f1b1abd13f78f3518d8bb12abb18762dd1",
        b"RADIO_SHA=" + hashlib.sha256(radio).hexdigest().encode())
    self_stage = found["pmos-self-stage.sh"]
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
log "mounted pinned persistent root from read-only $node ($part_dev) and verified its root contract"'''
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
            b"PMOS_ROOT_KIND=ext4 " in self_stage and b'"$wait_n" -lt 145' in self_stage, DELTA_MSG)
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


def hook(found):
    body = builder.HOOK.replace(b"@PINS@", pins(found), 1)
    body = body.replace(
        b'$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0\n',
        b'$BB mv "$D/pmos-root-contract.sh" /run/pmos-root-contract.sh || exit 0\n'
        b'$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0\n', 1)
    require(body.count(b"@PINS@") == 0 and body.count(b"pmos-root-contract.sh") == 3 and
            body.count(b"/run/keep") == 0 and body.count(b"sleep 150") == 0 and
            body.count(b"151.01") == 0, INIT_MSG)
    return body


def expected_init(original, found):
    marker = b"setsid cttyhack /bin/sh &\n"
    start = original.index(marker) + len(marker)
    end = original.index(b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n' >/dev/null 2>&1 &\n", start)
    end += len(b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n' >/dev/null 2>&1 &\n")
    require(original.count(marker) == 1 and original.count(b"@PINS@") == 0, INIT_MSG)
    old_sha = b"0b85d1dc3c05b58f703618994363a9d0dbd09ecf8139573d2db15628d2497549"
    new_sha = hashlib.sha256(found["pmos-pid1-transition.sh"]).hexdigest().encode()
    require(original.count(old_sha) == 2, INIT_MSG)
    return replace_once(original[:start] + hook(found) + original[end:], old_sha, new_sha)


def candidate_cpio(entries, trailer, found, private):
    original = next(entry["data"] for entry in entries if entry["name"] == "init")
    init = expected_init(original, found)
    public = {name: found[name] for name in (*builder.PUBLIC, "pmos-root-contract.sh")}
    blob = builder.checked_bundle(builder.bundle_bytes(public, private), public, private)
    changed = [{**entry, "data": init} if entry["name"] == "init" else entry for entry in entries]
    for index, entry in enumerate(changed):
        if entry["name"] == builder.BUNDLE:
            changed[index] = {**entry, "data": blob}
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


def build(stock, base_image, current, library, decode_frame):
    vendor.check_stock(stock, library)
    require(base_image[:base.RAMDISK_SIZE_OFFSET] == stock[:base.RAMDISK_SIZE_OFFSET] and
            base_image[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
            base_image[base.TAIL_OFFSET:] == stock[base.TAIL_OFFSET:], BASE_MSG)
    entries, trailer, base_found, private = base_state(base_image, library, decode_frame)
    found = expected_found(base_found, current)
    cpio = candidate_cpio(entries, trailer, found, private)
    frame = frame_for(cpio, library)
    image, digest = vendor.assemble(stock, frame)
    require(digest not in REFUSED, SHA_MSG)
    return image, digest, len(cpio), len(frame), entries, trailer, found, private


def main():
    args = sys.argv[1:]
    require(len(args) == 4 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-persistent-root.py --preflight|--build STOCK_INIT BASE OUTPUT")
    stock_path, base_path, output = map(pathlib.Path, args[1:])
    require(base_path.resolve() == BASE_IMAGE.resolve(), BASE_MSG)
    if args[0] == "--build":
        target = output.resolve()
        require(not target.is_relative_to(HERE.parent.resolve()) and target not in
                (stock_path.resolve(), base_path.resolve()) and not output.is_symlink() and
                output.parent.is_dir() and not output.is_dir(), "output must be outside Git and different from every input")
    current = current_scripts()
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "persistent_decode")
    image, digest, cpio_size, frame_size, *_rest = build(
        stock_path.read_bytes(), base_path.read_bytes(), current, base.lz4(),
        checker.hostkey_checker.decode_frame)
    print(f"cpio: {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame: {frame_size}/{base.MAX_FRAME}")
    print(f"candidate: {len(image)} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        output.write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
