#!/usr/bin/env bash
set -euo pipefail
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
DEVICE=${DEVICE:-$HOME/phone-second-life-data/mb003}
STOCK_INIT=$DEVICE/parts/init_boot_a.img
STOCK_BOOT=$DEVICE/parts/boot_a.img
STOCK_VENDOR=$DEVICE/parts/vendor_boot_a.img
STOCK_RECOVERY=$DEVICE/parts/recovery_a.img
STOCK_CONFIG=$DEVICE/config.gz
KERNEL_SOURCE=$WORK/src/init/initramfs.c
DECOMPRESSOR_SOURCE=$WORK/src/lib/decompress_unlz4.c
PSTORE=$DEVICE/pstore/attempt-20261022-2004-initboot-lz4debug/pstore/console-ramoops-0
MAPS=$DEVICE/acquire/attempt-20261025-0632-modem-a/issue-86-maps
BY_NAME=$DEVICE/by-name.txt
IMAGE_SIZE=8388608
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp bash tee flock; do need "$tool"; done
[ "$#" -eq 0 ] || die 'usage: build-init-boot-wpss-boot.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
for reference in "$STOCK_INIT" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
	"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" \
	"$OUT/initramfs.cpio.gz" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" \
	"$OUT/rmtfs" "$OUT/msm_sharedmem.ko" "$BY_NAME" "$MAPS/extraction-manifest.txt"; do
	[ -f "$reference" ] || die "missing input: $reference"
done
[ "$(stat -c '%s' "$STOCK_INIT")" -eq "$IMAGE_SIZE" ] ||
	die "stock init_boot is not $IMAGE_SIZE bytes"

# The #96 run-36 image is an input only for the verifier; no measured SHA is reused.
[ -f "$OUT/init_boot-rmtfs-sharedmem.img" ] || die "missing run-36 reference image"
read -r run36_sha _ < <(sha256sum "$OUT/init_boot-rmtfs-sharedmem.img")
[ "$run36_sha" = bf2089c4f8a72591b45385829f287d24296fc88918a2b40a226ff4b1fcaede55 ] ||
	die "run-36 reference image does not match the measured bf2089c4 SHA"

exec 9>"$WORK/i101-image.lock"
flock 9 || die 'another #101 image build is in progress'

candidate=$(mktemp "$OUT/init_boot-wpss-boot.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-wpss-boot.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-wpss-boot-payload.py" --build \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$MAPS" \
		"$OUT/rmtfs" "$OUT/msm_sharedmem.ko" "$BY_NAME" "$image"
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] || die "candidate is not $IMAGE_SIZE bytes"
	python3 -B "$ROOT/scripts/verify-init-boot-wpss-boot.py" --self-test \
		"$image" "$OUT/init_boot-rmtfs-sharedmem.img" "$STOCK_INIT" \
		"$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" \
		"$OUT/msm_sharedmem.ko" "$BY_NAME" "$MAPS" >/dev/null
	python3 -B "$ROOT/scripts/verify-init-boot-wpss-boot.py" \
		"$image" "$OUT/init_boot-rmtfs-sharedmem.img" "$STOCK_INIT" \
		"$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" \
		"$OUT/msm_sharedmem.ko" "$BY_NAME" "$MAPS"
done
cmp -s "$candidate" "$second" || die 'repeated image builds differ'
mv -f -- "$candidate" "$OUT/init_boot-wpss-boot.img"
sha256sum "$OUT/init_boot-wpss-boot.img" | tee "$OUT/init-boot-wpss-boot-sha256.txt"
