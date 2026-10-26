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
HOSTKEY=${HOSTKEY:-$HOME/.omnipha/sm7635/dropbear_ed25519_host_key}
IMAGE_SIZE=8388608
RUN41_SHA=7c3d915f3c8554d8a551b33f1b1caf162d410c0f629fae75425f29112c2fedf0
RUN39_SHA=0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp tee flock; do need "$tool"; done
[ "$#" -eq 0 ] || die 'usage: build-init-boot-psoc-hold-capture-hostkey.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "artifacts must stay outside this repository" ;;
esac
case "$(realpath -m "$HOSTKEY")/" in
	"$ROOT"/*) die "the Dropbear host key must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -f "$HOSTKEY" ] || die "missing protected host key input: $HOSTKEY (set HOSTKEY=<path>)"
[ "$(stat -c '%a' "$HOSTKEY")" -le 600 ] ||
	die "protected host key input must not be group- or world-readable"
for reference in "$STOCK_INIT" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
	"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" \
	"$OUT/initramfs.cpio.gz" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" \
	"$OUT/rmtfs" "$OUT/msm_sharedmem.ko" "$BY_NAME" "$MAPS/extraction-manifest.txt" \
	"$HOSTKEY"; do
	[ -f "$reference" ] || die "missing input: $reference"
done
[ "$(stat -c '%s' "$STOCK_INIT")" -eq "$IMAGE_SIZE" ] ||
	die "stock init_boot is not $IMAGE_SIZE bytes"

[ -f "$OUT/init_boot-psoc-hold-capture.img" ] || die "missing run-41 reference image"
read -r run41_sha _ < <(sha256sum "$OUT/init_boot-psoc-hold-capture.img")
[ "$run41_sha" = "$RUN41_SHA" ] ||
	die "run-41 reference image does not match the unflashed $RUN41_SHA SHA"
[ -f "$OUT/init_boot-psoc-hold.img" ] || die "missing run-39 reference image"
read -r run39_sha _ < <(sha256sum "$OUT/init_boot-psoc-hold.img")
[ "$run39_sha" = "$RUN39_SHA" ] ||
	die "run-39 reference image does not match the measured $RUN39_SHA SHA"

python3 -B "$ROOT/scripts/verify-init-boot-psoc-hold-capture-hostkey.py" --check-input \
	"$HOSTKEY" || die 'unprotected, unpinned or committed Dropbear host key input'

exec 9>"$WORK/i120-image.lock"
flock 9 || die 'another #120 image build is in progress'

candidate=$(mktemp "$OUT/init_boot-psoc-hold-capture-hostkey.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-psoc-hold-capture-hostkey.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-psoc-hold-capture-hostkey-payload.py" --build \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$MAPS" \
		"$OUT/rmtfs" "$OUT/msm_sharedmem.ko" "$BY_NAME" \
		"$OUT/init_boot-wpss-boot.img" "$OUT/init_boot-wlan-ini.img" \
		"$OUT/init_boot-psoc-hold.img" "$OUT/init_boot-psoc-hold-capture.img" \
		"$HOSTKEY" "$image" >/dev/null
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] || die "candidate is not $IMAGE_SIZE bytes"
	python3 -B "$ROOT/scripts/verify-init-boot-psoc-hold-capture-hostkey.py" --self-test \
		"$image" "$OUT/init_boot-psoc-hold-capture.img" "$OUT/init_boot-psoc-hold.img" \
		"$OUT/init_boot-wlan-ini.img" "$OUT/init_boot-wpss-boot.img" "$STOCK_INIT" \
		"$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
		"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" \
		"$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" \
		"$OUT/msm_sharedmem.ko" "$BY_NAME" "$MAPS" "$HOSTKEY" >/dev/null
	python3 -B "$ROOT/scripts/verify-init-boot-psoc-hold-capture-hostkey.py" \
		"$image" "$OUT/init_boot-psoc-hold-capture.img" "$OUT/init_boot-psoc-hold.img" \
		"$OUT/init_boot-wlan-ini.img" "$OUT/init_boot-wpss-boot.img" "$STOCK_INIT" \
		"$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
		"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" \
		"$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" \
		"$OUT/msm_sharedmem.ko" "$BY_NAME" "$MAPS" "$HOSTKEY"
done
cmp -s "$candidate" "$second" || die 'repeated image builds differ'
mv -f -- "$candidate" "$OUT/init_boot-psoc-hold-capture-hostkey.img"
sha256sum "$OUT/init_boot-psoc-hold-capture-hostkey.img" |
	tee "$OUT/init-boot-psoc-hold-capture-hostkey-sha256.txt"