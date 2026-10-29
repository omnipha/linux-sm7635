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
BUNDLE = "run/omnipha-self-stage.tar.xz"
BUNDLE_DIR = "/run/omnipha-self-stage"
STAGE = "/run/pmos-self-stage.sh"
POST = "/run/pmos-self-post.sh"
PUBLIC = (
    "pmos-session-stage.sh",
    "pmos-pid1-transition.sh",
    "pmos-pid1-guard.sh",
    "pmos-radio-bringup.sh",
    "wlan-udhcpc-lease.sh",
    "pmos-self-stage.sh",
    "pmos-self-post.sh",
)
PRIVATE = "wpa_supplicant.conf"
STUBS = {
    "pmos-self-stage.sh": b"#!/bin/busybox sh\nexit 0\n",
    "pmos-self-post.sh": b"#!/bin/busybox sh\nexit 0\n",
}
PARENT = ("pmos-self-stage.sh", "pmos-self-post.sh")
DEFER_MSG = "parent self-stage scripts are absent; frame sized, image deferred"
FRAME_MSG = "ramdisk is not one reproducible LZ4 HC-12 block inside the stock envelope"
CPIO_MSG = "cpio must change only /init and add one root-only self-stage bundle"
INIT_MSG = "init must keep the measured handoff and append one distinct self-stage hook"
SHA_MSG = "candidate repeats a stock, measured or refused image SHA-256"
RUN58_INIT = "4b83ea24c305d731b168c2e2f12bd0ebd5d4a18de9039eaf8b0e0ca452b464f7"
RUN58_PAYLOAD = "1bdb7c2252b3192127aed0a2f8953d928be0f36a00a259582e7a75a98a029f5f"
RUN61_INIT = "bee02ce1f31d628fd95879fb519d4b131f3d8a3298530d1fc31c390db528f412"
RUN61_PAYLOAD = "41cab142203b4ccf894f7bea24398d21ff959ab72d3473e88379d2780bdc9afd"
RECOVERY_SCRIPT_SHA = "af5e4c53872267504e36fe5863735fdf534f834673a2c9bce0a5c802a0d18f13"
CARRIER_MSG = "self-stage script differs from the measured recovery_b script by more than the userdata staging block"
OLD_STAGING = b'''PART_SIZE=104857600
HEADER_OFFSET=18870272
ARCHIVE_OFFSET=18874368
HEADER_SHA=2d09f260bab4b77c51f0639d034c662d01e7e13e821507278cbd571ac038b578
'''
NEW_START = b'''PART_SIZE=33554432
ARCHIVE_PATH=/omnipha-userspace/postmarketos-session-aarch64.tar.gz
MOUNT=/run/omnipha-userspace
'''
OLD_BODY = b'''part_dev=
part_count=0
for uevent in /sys/class/block/*/uevent; do
	[ -r "$uevent" ] || continue
	if [ "$($BB sed -n 's/^PARTNAME=//p' "$uevent" 2>/dev/null)" = recovery_b ]; then
		dir=${uevent%/uevent}
		part_dev=${dir##*/}
		part_count=$((part_count + 1))
	fi
done
[ "$part_count" = 1 ] && [ -n "$part_dev" ] ||
	die "expected one recovery_b PARTNAME in sysfs, found $part_count"
devnum=$($BB cat "/sys/class/block/$part_dev/dev" 2>/dev/null) || devnum=
case "$devnum" in [0-9]*:[0-9]*) :;; *) die 'recovery_b device numbers invalid';; esac
major=${devnum%%:*}
minor=${devnum##*:}
$BB mkdir -p /dev/block
node="/dev/block/$part_dev"
if [ -b "$node" ]; then
	[ ! -L "$node" ] || die 'recovery_b block path is a symlink'
	[ "$($BB stat -c '%t:%T' "$node")" = "$($BB printf '%x:%x' "$major" "$minor")" ] ||
		die 'recovery_b block node numbers differ from sysfs'
else
	[ ! -e "$node" ] && [ ! -L "$node" ] || die 'recovery_b path is not a block node'
	$BB mknod -m 0400 "$node" b "$major" "$minor" || die 'cannot create recovery_b block node'
fi
[ "$($BB stat -c '%t:%T' "$node")" = "$($BB printf '%x:%x' "$major" "$minor")" ] ||
	die 'recovery_b node verification failed'
size=$($BB timeout -k 1 2 $BB blockdev --getsize64 "$node" 2>/dev/null) || size=
[ "$size" = "$PART_SIZE" ] || die "recovery_b size mismatch (${size:-unknown})"

hdr=/run/recovery_b.header
$BB rm -f "$hdr"
$BB timeout -k 1 5 $BB dd if="$node" of="$hdr" bs=4096 skip=$((HEADER_OFFSET / 4096)) count=1 2>/dev/null ||
	{ $BB rm -f "$hdr"; die 'cannot read recovery_b payload header'; }
[ "$(hash "$hdr")" = "$HEADER_SHA" ] ||
	{ $BB rm -f "$hdr"; die 'recovery_b payload header digest mismatch'; }
$BB rm -f "$hdr"

[ ! -e "$TARBALL" ] && [ ! -L "$TARBALL" ] || die 'tarball path already exists'
full_blocks=$((ARCHIVE_SIZE / 4096))
rem_bytes=$((ARCHIVE_SIZE % 4096))
skip_blocks=$((ARCHIVE_OFFSET / 4096))
$BB timeout -k 2 30 $BB dd if="$node" of="$TARBALL" bs=4096 skip="$skip_blocks" count="$full_blocks" 2>/dev/null ||
	{ $BB rm -f "$TARBALL"; die 'recovery_b archive block copy failed'; }
if [ "$rem_bytes" -gt 0 ]; then
	page=/run/recovery_b.page
	$BB rm -f "$page"
	$BB timeout -k 1 5 $BB dd if="$node" of="$page" bs=4096 skip=$((skip_blocks + full_blocks)) count=1 2>/dev/null ||
		{ $BB rm -f "$TARBALL" "$page"; die 'recovery_b archive tail copy failed'; }
	$BB dd if="$page" of="$TARBALL" bs=1 seek="$((full_blocks * 4096))" count="$rem_bytes" conv=notrunc 2>/dev/null ||
		{ $BB rm -f "$TARBALL" "$page"; die 'recovery_b archive tail copy failed'; }
	$BB rm -f "$page"
fi
$BB chmod 600 "$TARBALL"
[ "$($BB stat -c '%u:%a:%s' "$TARBALL")" = "0:600:$ARCHIVE_SIZE" ] &&
	[ "$(hash "$TARBALL")" = "$ARCHIVE_SHA" ] ||
	{ $BB rm -f "$TARBALL"; die 'recovery_b archive digest or size mismatch'; }
log "copied userspace archive from read-only $node ($part_dev) and verified SHA-256"
'''
BODY_START = b"part_dev=\npart_count=0\n"
BODY_END = b'log "copied userspace archive from read-only $node ($part_dev) and verified SHA-256"\n'
PROFILE_MSG = "private profile must be a regular non-symlink file owned by the current uid with mode 0600"
BUNDLE_MSG = "self-stage bundle is not one reproducible root-only xz tar of the pinned scripts"
SCRIPT_MSG = "bundled script does not match its reviewed digest"
HOOK = b"""setsid /bin/busybox sh -c '
umask 077
BB=/bin/busybox
B=/run/omnipha-self-stage.tar.xz
D=/run/omnipha-self-stage
$BB mkdir -m 700 "$D" || exit 0
$BB tar -xJf "$B" -C "$D" || exit 0
stage() {
	got=$($BB sha256sum "$D/$1" 2>/dev/null | $BB cut -d " " -f 1)
	[ "$got" = "$2" ] || exit 0
	$BB chmod "$3" "$D/$1" || exit 0
}
@PINS@
$BB mv "$D/pmos-self-stage.sh" /run/pmos-self-stage.sh || exit 0
$BB mv "$D/pmos-self-post.sh" /run/pmos-self-post.sh || exit 0
$BB mv "$D/pmos-session-stage.sh" /run/pmos-session-stage.sh || exit 0
$BB mv "$D/pmos-pid1-transition.sh" /run/pmos-pid1-transition.sh || exit 0
$BB mv "$D/pmos-pid1-guard.sh" /run/pmos-pid1-guard.sh || exit 0
$BB mv "$D/pmos-radio-bringup.sh" /run/pmos-radio-bringup.sh || exit 0
$BB mv "$D/wlan-udhcpc-lease.sh" /run/wlan-udhcpc-lease.sh || exit 0
$BB mv "$D/wpa_supplicant.conf" /run/wpa_supplicant.conf || exit 0
setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &
' >/dev/null 2>&1 &
"""


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = load("build-init-boot-pid1-handoff.py", "self_stage_prior")
modules = prior.modules
base = prior.base
vendor = prior.vendor
REFUSED = frozenset((*prior.REFUSED, prior.EXPECTED_SHA256, RUN58_INIT, RUN58_PAYLOAD,
                      RUN61_INIT, RUN61_PAYLOAD))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path, mode_bits):
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == mode_bits


def profile_bytes():
    require(PROFILE.is_file() and not PROFILE.is_symlink() and
            PROFILE.stat().st_uid == os.getuid() and regular(PROFILE, 0o600) and
            PROFILE.stat().st_size > 0, PROFILE_MSG)
    return PROFILE.read_bytes()


def carrier_delta(data):
    original = (HERE / "pmos-self-stage.sh").read_bytes()
    require(data == original and data.count(NEW_START) == 1 and
            data.count(BODY_START) == 1 and data.count(BODY_END) == 1 and
            data.count(b"recovery_b") == 0 and data.count(b"vendor_boot_b") == 0,
            CARRIER_MSG)
    start = data.index(BODY_START)
    end = data.index(BODY_END, start) + len(BODY_END)
    require(start < end and data.count(b"PART_SIZE=33554432\n") == 1 and
            data.count(b"ARCHIVE_PATH=/omnipha-userspace/postmarketos-session-aarch64.tar.gz\n") == 1,
            CARRIER_MSG)
    old = data[:start] + OLD_BODY + data[end:]
    old = old.replace(NEW_START, OLD_STAGING, 1)
    require(hashlib.sha256(old).hexdigest() == RECOVERY_SCRIPT_SHA and
            old.count(b"recovery_b") == 17 and old.count(OLD_STAGING) == 1,
            CARRIER_MSG)
    return old


def script_bytes(name):
    path = HERE / name
    require(path.is_file() and not path.is_symlink() and
            stat.S_ISREG(path.lstat().st_mode) and path.stat().st_size > 0 and
            not path.stat().st_mode & 0o002, SCRIPT_MSG)
    data = path.read_bytes()
    require(data.startswith(b"#!/bin/busybox sh\n") and b"\0" not in data, SCRIPT_MSG)
    return data


def members(allow_stub):
    found = {}
    missing = []
    for name in PUBLIC:
        path = HERE / name
        if name in PARENT and not path.exists():
            missing.append(name)
            continue
        found[name] = script_bytes(name)
    private = profile_bytes()
    if missing:
        require(allow_stub and set(missing) <= set(PARENT), DEFER_MSG)
        for name in missing:
            found[name] = STUBS[name]
        return found, private, False
    return found, private, True


def bundle_bytes(found, private):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted((*PUBLIC, PRIVATE)):
            data = private if name == PRIVATE else found[name]
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600 if name == PRIVATE else 0o700
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            archive.addfile(info, io.BytesIO(data))
    packed = lzma.compress(raw.getvalue(), format=lzma.FORMAT_XZ,
                           check=lzma.CHECK_CRC64, preset=6)
    require(packed.startswith(b"\xfd7zXZ\x00") and PRIVATE.encode() not in packed and
            not any(value in packed for value in found.values()), BUNDLE_MSG)
    return packed


def checked_bundle(blob, found, private):
    require(blob.startswith(b"\xfd7zXZ\x00"), BUNDLE_MSG)
    raw = lzma.decompress(blob, format=lzma.FORMAT_XZ)
    require(bundle_bytes(found, private) == blob, BUNDLE_MSG)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        infos = archive.getmembers()
        require([item.name for item in infos] == sorted((*PUBLIC, PRIVATE)), BUNDLE_MSG)
        for item in infos:
            data = archive.extractfile(item).read()
            want = private if item.name == PRIVATE else found[item.name]
            mode = 0o600 if item.name == PRIVATE else 0o700
            require(item.isfile() and not item.issym() and item.mode == mode and
                    item.uid == 0 and item.gid == 0 and item.mtime == 0 and
                    item.uname == "" and item.gname == "" and data == want, BUNDLE_MSG)
    return blob


def pins(found, private):
    lines = [f"stage {name} {hashlib.sha256(found[name]).hexdigest()} 700" for name in PUBLIC]
    lines.append(f'$BB chmod 600 "$D/{PRIVATE}" || exit 0')
    return "\n".join(lines).encode()


def hook(found, private):
    body = HOOK.replace(b"@PINS@", pins(found, private), 1)
    require(body.count(b"@PINS@") == 0 and body.count(b"setsid /bin/busybox sh /run/pmos-self-stage.sh") == 1 and
            body.endswith(b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n' >/dev/null 2>&1 &\n") and
            body.count(b"/run/keep") == 0 and body.count(b"sleep 150") == 0 and
            body.count(b"151.01") == 0, INIT_MSG)
    return body


def source_entries(stock, previous, library, decode_frame):
    vendor.check_stock(stock, library)
    require(len(previous) == base.IMAGE_SIZE and modules.sha256(previous) == prior.EXPECTED_SHA256 and
            previous[:8] == b"ANDROID!" and struct.unpack_from("<I", previous, 40)[0] == 4 and
            struct.unpack_from("<I", previous, 8)[0] == 0 and
            previous[:base.RAMDISK_SIZE_OFFSET] == stock[:base.RAMDISK_SIZE_OFFSET] and
            previous[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
            previous[base.TAIL_OFFSET:] == stock[base.TAIL_OFFSET:],
            "previous image is not the measured fef03008 handoff image on the pinned stock header and tail")
    size = struct.unpack_from("<I", previous, base.RAMDISK_SIZE_OFFSET)[0]
    require(8 < size <= base.MAX_FRAME and not any(previous[base.PAGE + size:base.TAIL_OFFSET]),
            FRAME_MSG)
    frame = previous[base.PAGE:base.PAGE + size]
    decoded = decode_frame(frame, library)
    require(vendor.encode_frame(decoded, library) == frame, FRAME_MSG)
    entries, trailer = modules.parse_newc(decoded, "handoff generic cpio")
    names = [entry["name"] for entry in entries]
    require(modules.encode_newc(entries, trailer) == decoded and len(set(names)) == len(names) and
            names.count("init") == 1 and BUNDLE not in names and
            not any(name.endswith(".ko") for name in names), CPIO_MSG)
    init = next(entry["data"] for entry in entries if entry["name"] == "init")
    console = b"log 'console ready'\n"
    marker = b"setsid cttyhack /bin/sh &\n"
    require(init.startswith(b"#!/bin/busybox sh\n") and
            init.count(prior.SETTLE) == 1 and init.count(prior.previous.eud.TIMER) == 1 and
            init.count(console) == 1 and init.count(marker) == 1 and
            init.index(prior.previous.eud.TIMER) < init.index(console) + len(console) ==
            init.index(marker) < init.index(prior.SETTLE) and
            init.endswith(prior.HANDOFF.split(b"@SHA256@")[1]),
            INIT_MSG)
    return entries, trailer


def expected_init(original, found, private):
    marker = b"setsid cttyhack /bin/sh &\n"
    require(original.count(marker) == 1 and original.count(prior.SETTLE) == 1, INIT_MSG)
    return original.replace(marker, marker + hook(found, private), 1)


def candidate_cpio(entries, trailer, found, private):
    original = next(entry["data"] for entry in entries if entry["name"] == "init")
    init = expected_init(original, found, private)
    blob = checked_bundle(bundle_bytes(found, private), found, private)
    fields = list(next(entry["fields"] for entry in entries if entry["name"] == "init"))
    fields[1] = 0o100600
    added = {"name": BUNDLE, "mode": 0o100600, "fields": fields, "data": blob}
    changed = [{**entry, "data": init} if entry["name"] == "init" else entry
               for entry in entries]
    changed.append(added)
    cpio = modules.encode_newc(changed, trailer)
    decoded, new_trailer = modules.parse_newc(cpio, "self-stage generic cpio")
    require(len(decoded) == len(changed) and new_trailer == trailer and
            decoded[-1]["name"] == BUNDLE and decoded[-1]["data"] == blob and
            decoded[-1]["mode"] & 0o170777 == 0o100600, CPIO_MSG)
    return cpio


def frame_budget(cpio, library):
    block = base.compress_hc(library, cpio, base.HC_LEVEL)
    frame = base.LZ4_MAGIC + struct.pack("<I", len(block)) + block
    require(base.decompress(library, block, len(cpio)) == cpio, FRAME_MSG)
    require(len(frame) <= base.MAX_FRAME,
            f"LZ4 HC-{base.HC_LEVEL} frame {len(frame)}/{base.MAX_FRAME}; exceeds envelope")
    return frame


def measured_delta(stock, entries, trailer, found, private, library):
    old = dict(found)
    old["pmos-self-stage.sh"] = carrier_delta(found["pmos-self-stage.sh"])
    old_frame = frame_budget(candidate_cpio(entries, trailer, old, private), library)
    require(vendor.assemble(stock, old_frame)[1] == RUN61_INIT, CARRIER_MSG)
    run58 = dict(old)
    run58["pmos-self-stage.sh"] = old["pmos-self-stage.sh"].replace(
        b"recovery_b", b"vendor_boot_b").replace(
            b"PART_SIZE=104857600\n", b"PART_SIZE=100663296\n")
    run58_frame = frame_budget(candidate_cpio(entries, trailer, run58, private), library)
    require(vendor.assemble(stock, run58_frame)[1] == RUN58_INIT, CARRIER_MSG)


def build(stock, previous, found, private, library, decode_frame, ready):
    carrier_delta(found["pmos-self-stage.sh"])
    entries, trailer = source_entries(stock, previous, library, decode_frame)
    measured_delta(stock, entries, trailer, found, private, library)
    cpio = candidate_cpio(entries, trailer, found, private)
    frame = frame_budget(cpio, library)
    if not ready:
        raise ValueError(f"{DEFER_MSG}: frame {len(frame)}/{base.MAX_FRAME}")
    image, digest = vendor.assemble(stock, frame)
    require(digest not in REFUSED, SHA_MSG)
    return image, digest, len(cpio), len(frame)


def main():
    args = sys.argv[1:]
    require(len(args) == 4 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-self-stage.py --preflight|--build STOCK_INIT PREVIOUS OUTPUT")
    stock_path, previous_path, output = map(pathlib.Path, args[1:])
    if args[0] == "--build":
        target = output.resolve()
        require(not target.is_relative_to(HERE.parent.resolve()) and
                target not in (stock_path.resolve(), previous_path.resolve()) and
                not output.is_symlink() and output.parent.is_dir() and not output.is_dir(),
                "output must be outside Git and different from every input")
    found, private, ready = members(True)
    stock, previous_image = stock_path.read_bytes(), previous_path.read_bytes()
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "self_stage_decode")
    image, digest, cpio_size, frame_size = build(
        stock, previous_image, found, private, base.lz4(),
        checker.hostkey_checker.decode_frame, ready)
    print(f"cpio: {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame: {frame_size}/{base.MAX_FRAME}")
    print(f"candidate: {len(image)} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        require(ready and not output.is_symlink(), DEFER_MSG)
        output.write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError,
            tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
