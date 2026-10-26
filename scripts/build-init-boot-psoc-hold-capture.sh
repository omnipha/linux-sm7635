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
RUN39_SHA=0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7
RUN38_SHA=e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c
RUN37_SHA=d9d8d2b8268f1fcc8e3212b7943bf62c5a5b4b7e20f258acf80cbc76d5508076
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp bash tee flock; do need "$tool"; done
[ "$#" -eq 0 ] || die 'usage: build-init-boot-psoc-hold-capture.sh (no arguments)'
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

[ -f "$OUT/init_boot-wpss-boot.img" ] || die "missing run-37 reference image"
read -r run37_sha _ < <(sha256sum "$OUT/init_boot-wpss-boot.img")
[ "$run37_sha" = "$RUN37_SHA" ] ||
	die "run-37 reference image does not match the measured $RUN37_SHA SHA"
[ -f "$OUT/init_boot-wlan-ini.img" ] || die "missing run-38 reference image"
read -r run38_sha _ < <(sha256sum "$OUT/init_boot-wlan-ini.img")
[ "$run38_sha" = "$RUN38_SHA" ] ||
	die "run-38 reference image does not match the measured $RUN38_SHA SHA"
[ -f "$OUT/init_boot-psoc-hold.img" ] || die "missing run-39 reference image"
read -r run39_sha _ < <(sha256sum "$OUT/init_boot-psoc-hold.img")
[ "$run39_sha" = "$RUN39_SHA" ] ||
	die "run-39 reference image does not match the measured $RUN39_SHA SHA"

exec 9>"$WORK/i116-image.lock"
flock 9 || die 'another #116 image build is in progress'

candidate=$(mktemp "$OUT/init_boot-psoc-hold-capture.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-psoc-hold-capture.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-psoc-hold-capture-payload.py" --build \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$MAPS" \
		"$OUT/rmtfs" "$OUT/msm_sharedmem.ko" "$BY_NAME" \
		"$OUT/init_boot-wpss-boot.img" "$OUT/init_boot-wlan-ini.img" \
		"$OUT/init_boot-psoc-hold.img" "$image"
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] || die "candidate is not $IMAGE_SIZE bytes"
	python3 -B "$ROOT/scripts/verify-init-boot-psoc-hold-capture.py" --self-test \
		"$image" "$OUT/init_boot-psoc-hold.img" "$OUT/init_boot-wlan-ini.img" \
		"$OUT/init_boot-wpss-boot.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
		"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
		"$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" "$OUT/restart2" \
		"$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" "$OUT/msm_sharedmem.ko" \
		"$BY_NAME" "$MAPS" >/dev/null
	python3 -B "$ROOT/scripts/verify-init-boot-psoc-hold-capture.py" \
		"$image" "$OUT/init_boot-psoc-hold.img" "$OUT/init_boot-wlan-ini.img" \
		"$OUT/init_boot-wpss-boot.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
		"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
		"$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" "$OUT/restart2" \
		"$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" "$OUT/msm_sharedmem.ko" \
		"$BY_NAME" "$MAPS"
done
cmp -s "$candidate" "$second" || die 'repeated image builds differ'
mv -f -- "$candidate" "$OUT/init_boot-psoc-hold-capture.img"
sha256sum "$OUT/init_boot-psoc-hold-capture.img" |
	tee "$OUT/init-boot-psoc-hold-capture-sha256.txt"
