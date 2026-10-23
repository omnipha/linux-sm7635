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
IMAGE_SIZE=8388608
GZIP_SIZE=1672600
GZIP_SHA256=caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp mv bash; do
	need "$tool"
done
[ "$#" -eq 0 ] || die 'usage: build-init-boot-self-recovering.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ "$OUT" != "$WORK" ] || die "output directory must not be the work directory"
for reference in "$STOCK_INIT" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
	"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" \
	"$ROOT/initramfs/init" "$ROOT/initramfs/init-44-vendor-modules" \
	"$ROOT/initramfs/restart2.c" "$OUT/initramfs.cpio.gz"; do
	[ -f "$reference" ] || die "missing input: $reference"
done
[ "$(stat -c '%s' "$STOCK_INIT")" -eq "$IMAGE_SIZE" ] ||
	die "stock init_boot is not $IMAGE_SIZE bytes"
[ "$(stat -c '%s' "$OUT/initramfs.cpio.gz")" -eq "$GZIP_SIZE" ] ||
	die "debug gzip is not $GZIP_SIZE bytes"
read -r gzip_sha _ < <(sha256sum "$OUT/initramfs.cpio.gz")
[ "$gzip_sha" = "$GZIP_SHA256" ] || die "debug gzip is not the verified caa3eb82 archive"
bash -n "$ROOT/initramfs/init" || die "initramfs/init is not valid shell"
python3 "$ROOT/scripts/vendor-module-closure.py" "$STOCK_VENDOR"
bash "$ROOT/scripts/build-restart2-helper.sh"

candidate=$(mktemp "$OUT/init_boot-self-recovering.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-self-recovering.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	python3 "$ROOT/scripts/build-init-boot-self-recovering-payload.py" --build \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$image"
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] || die "candidate is not $IMAGE_SIZE bytes"
	python3 "$ROOT/scripts/verify-init-boot-self-recovering.py" --self-test "$image" \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" >/dev/null
	python3 "$ROOT/scripts/verify-init-boot-self-recovering.py" "$image" \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2"
done
cmp -s -- "$candidate" "$second" || die "repeated builds differ"
mv -f -- "$candidate" "$OUT/init_boot-self-recovering.img"
sha256sum "$OUT/init_boot-self-recovering.img" |
	tee "$OUT/init-boot-self-recovering-sha256.txt"
