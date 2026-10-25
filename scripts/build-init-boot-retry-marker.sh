#!/usr/bin/env bash
set -euo pipefail
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
DEVICE=${DEVICE:-$HOME/phone-second-life-data/mb003}
STOCK_INIT=${STOCK_INIT:-$DEVICE/parts/init_boot_a.img}
STOCK_BOOT=${STOCK_BOOT:-$DEVICE/parts/boot_a.img}
STOCK_VENDOR=${STOCK_VENDOR:-$DEVICE/parts/vendor_boot_a.img}
STOCK_RECOVERY=${STOCK_RECOVERY:-$DEVICE/parts/recovery_a.img}
STOCK_CONFIG=${STOCK_CONFIG:-$DEVICE/config.gz}
KERNEL_SOURCE=${KERNEL_SOURCE:-$WORK/src/init/initramfs.c}
DECOMPRESSOR_SOURCE=${DECOMPRESSOR_SOURCE:-$WORK/src/lib/decompress_unlz4.c}
PSTORE=${PSTORE:-$DEVICE/pstore/attempt-20261022-2004-initboot-lz4debug/pstore/console-ramoops-0}
SUPER=${SUPER:-$DEVICE/super-dump/super.img}
IMAGE_SIZE=8388608
SUPER_SIZE=9663676416
GZIP_SIZE=1672600
GZIP_SHA256=caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f
SUPER_SHA256=7307e9ff22fa4d9d0bfbf3dd0b1cf7d97c4c5de6eda3d44ff8c740e340462d8c
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp mv bash tee sudo; do
	need "$tool"
done
[ -x /sbin/losetup ] || [ -x /usr/sbin/losetup ] || die "missing tool: losetup"
[ "$#" -eq 0 ] || die 'usage: build-init-boot-retry-marker.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ "$OUT" != "$WORK" ] || die "output directory must not be the work directory"
for reference in "$STOCK_INIT" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
	"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" "$SUPER" \
	"$DEVICE/by-name.txt" \
	"$ROOT/initramfs/init" "$ROOT/initramfs/init-51-peripheral-mode" \
	"$ROOT/initramfs/restart2.c" "$OUT/initramfs.cpio.gz"; do
	[ -f "$reference" ] || die "missing input: $reference"
done
[ "$(stat -c '%s' "$STOCK_INIT")" -eq "$IMAGE_SIZE" ] ||
	die "stock init_boot is not $IMAGE_SIZE bytes"
[ "$(stat -c '%s' "$SUPER")" -eq "$SUPER_SIZE" ] ||
	die "super dump is not $SUPER_SIZE bytes"
read -r super_sha _ < <(sha256sum "$SUPER")
[ "$super_sha" = "$SUPER_SHA256" ] ||
	die "super dump is not the verified 7307e9ff image"
[ "$(stat -c '%s' "$OUT/initramfs.cpio.gz")" -eq "$GZIP_SIZE" ] ||
	die "debug gzip is not $GZIP_SIZE bytes"
read -r gzip_sha _ < <(sha256sum "$OUT/initramfs.cpio.gz")
[ "$gzip_sha" = "$GZIP_SHA256" ] || die "debug gzip is not the verified caa3eb82 archive"
bash -n "$ROOT/initramfs/init" || die "initramfs/init is not valid shell"
bash -n "$ROOT/initramfs/init-51-peripheral-mode" ||
	die "initramfs/init-51-peripheral-mode is not valid shell"
python3 -B "$ROOT/scripts/vendor-module-closure.py" "$STOCK_VENDOR"
python3 -B "$ROOT/scripts/super-wlan-closure.py" "$SUPER"

old_list=
super_mount=
super_loops=
derived=
candidate=
second=
cleanup() {
	local status=$?
	set +e
	for d in system_dlkm vendor vendor_dlkm; do
		[ -n "${super_mount:-}" ] && sudo -n umount "$super_mount/$d" >/dev/null 2>&1
	done
	for loop in $super_loops; do
		sudo -n /sbin/losetup -d "$loop" >/dev/null 2>&1
	done
	rm -f -- "$old_list" "$derived" "$candidate" "$second"
	rm -rf -- "$super_mount"
	return "$status"
}
trap cleanup EXIT
old_list=$(mktemp "$OUT/retry-marker-old-order.XXXXXXXX")
super_mount=$(mktemp -d "$OUT/retry-marker-super-mount.XXXXXXXX")
mkdir -p "$super_mount/vendor_dlkm" "$super_mount/vendor" "$super_mount/system_dlkm"
mount_lp() {
	local offset=$1 size=$2 dest=$3 loop
	loop=$(sudo -n /sbin/losetup -f --show -r -o "$offset" --sizelimit "$size" "$SUPER") ||
		return 1
	if ! sudo -n mount -t erofs -o ro,nodev,nosuid,noexec "$loop" "$super_mount/$dest"; then
		sudo -n /sbin/losetup -d "$loop"
		return 1
	fi
	super_loops="$super_loops $loop"
}
mount_lp 4797235200 11804672 system_dlkm ||
	die "could not mount system_dlkm_a read-only from super"
mount_lp 5678039040 1269284864 vendor ||
	die "could not mount vendor_a read-only from super"
mount_lp 6947864576 32669696 vendor_dlkm ||
	die "could not mount vendor_dlkm_a read-only from super"
python3 - "$ROOT/initramfs/init" >"$old_list" <<'PYEOF'
import pathlib, re, sys
text = pathlib.Path(sys.argv[1]).read_text()
match = re.search(r"^VENDOR_MODULES='\n((?:[A-Za-z0-9_.-]+\n)+)'$", text, re.MULTILINE)
sys.stdout.write("VENDOR_MODULES='\n" + match.group(1) + "'\n")
PYEOF
python3 -B "$ROOT/scripts/super-wlan-closure.py" --verify-mounted "$SUPER" \
	"$super_mount/vendor_dlkm" "$super_mount/vendor" "$super_mount/system_dlkm" "$old_list"
python3 -B "$ROOT/scripts/super-wlan-closure.py" --verify-by-name "$DEVICE/by-name.txt"
for d in system_dlkm vendor vendor_dlkm; do
	sudo -n umount "$super_mount/$d" || die "could not unmount $d"
done
for loop in $super_loops; do
	sudo -n /sbin/losetup -d "$loop" || die "could not detach loop $loop"
done
super_loops=

bash "$ROOT/scripts/build-restart2-helper.sh"

derived=$(mktemp "$OUT/init-retry-marker.XXXXXXXX")
candidate=$(mktemp "$OUT/init_boot-retry-marker.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-retry-marker.XXXXXXXX.img")
python3 -B -c '
import importlib.util, pathlib, sys
root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "retry_marker_builder", root / "scripts/build-init-boot-retry-marker-payload.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
frozen = (root / "initramfs" / builder.FROZEN_SOURCE).read_bytes()
builder.require(builder.modules.sha256(frozen) == builder.FROZEN_SHA256, builder.FROZEN_MSG)
sys.stdout.buffer.write(builder.expected_init(frozen))
' "$ROOT" >"$derived"
bash -n "$derived" || die "derived retry-marker init is not valid shell"
for image in "$candidate" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-retry-marker-payload.py" --build \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$image"
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] || die "candidate is not $IMAGE_SIZE bytes"
	python3 -B "$ROOT/scripts/verify-init-boot-retry-marker.py" --self-test "$image" \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" >/dev/null
	python3 -B "$ROOT/scripts/verify-init-boot-retry-marker.py" "$image" \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2"
done
cmp -s -- "$candidate" "$second" || die "repeated builds differ"
mv -f -- "$candidate" "$OUT/init_boot-retry-marker.img"
sha256sum "$OUT/init_boot-retry-marker.img" |
	tee "$OUT/init-boot-retry-marker-sha256.txt"
