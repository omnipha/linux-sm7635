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
MAPS=${MAPS:-$DEVICE/acquire/attempt-20261025-0632-modem-a/issue-86-maps}
SHAREDMEM=${SHAREDMEM:-$OUT/msm_sharedmem.ko}
BY_NAME=${BY_NAME:-$DEVICE/by-name.txt}
IMAGE_SIZE=8388608
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp mv bash tee flock; do need "$tool"; done
[ "$#" -eq 0 ] || die 'usage: build-init-boot-rmtfs-sharedmem.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
for reference in "$STOCK_INIT" "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" \
	"$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" "$PSTORE" \
	"$OUT/initramfs.cpio.gz" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" \
	"$OUT/rmtfs" "$SHAREDMEM" "$BY_NAME" "$MAPS/extraction-manifest.txt" \
	"$ROOT/initramfs/init"; do
	[ -f "$reference" ] || die "missing input: $reference"
done
[ "$(stat -c '%s' "$STOCK_INIT")" -eq "$IMAGE_SIZE" ] ||
	die "stock init_boot is not $IMAGE_SIZE bytes"
bash -n "$ROOT/initramfs/init" || die "base init is not valid shell"

# The #86 image is an input only for the verifier; no measured SHA is reused.
[ -f "$OUT/init_boot-pdmapper-tqftpserv.img" ] || die "missing run-35 reference image"
read -r run35_sha _ < <(sha256sum "$OUT/init_boot-pdmapper-tqftpserv.img")
[ "$run35_sha" = 8dddb8c714dce40c2795c95103236d8af9cfdc8ef00aaa6b6723055e41de09d1 ] ||
	die "run-35 reference image does not match the measured 8dddb8c7 SHA"

exec 9>"$WORK/i96-image.lock"
flock 9 || die 'another #96 image build is in progress'

candidate=$(mktemp "$OUT/init_boot-rmtfs-sharedmem.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-rmtfs-sharedmem.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-rmtfs-sharedmem-payload.py" --build \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$MAPS" \
		"$OUT/rmtfs" "$SHAREDMEM" "$BY_NAME" "$image"
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] || die "candidate is not $IMAGE_SIZE bytes"
	python3 -B "$ROOT/scripts/verify-init-boot-rmtfs-sharedmem.py" --self-test \
		"$image" "$OUT/init_boot-pdmapper-tqftpserv.img" "$STOCK_INIT" \
		"$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" \
		"$SHAREDMEM" "$BY_NAME" "$MAPS" >/dev/null
	python3 -B "$ROOT/scripts/verify-init-boot-rmtfs-sharedmem.py" \
		"$image" "$OUT/init_boot-pdmapper-tqftpserv.img" "$STOCK_INIT" \
		"$OUT/initramfs.cpio.gz" "$STOCK_BOOT" "$STOCK_VENDOR" \
		"$STOCK_RECOVERY" "$STOCK_CONFIG" "$KERNEL_SOURCE" "$DECOMPRESSOR_SOURCE" \
		"$PSTORE" "$OUT/restart2" "$OUT/pd-mapper" "$OUT/tqftpserv" "$OUT/rmtfs" \
		"$SHAREDMEM" "$BY_NAME" "$MAPS"
done
cmp -s "$candidate" "$second" || die 'repeated image builds differ'
mv -f -- "$candidate" "$OUT/init_boot-rmtfs-sharedmem.img"
sha256sum "$OUT/init_boot-rmtfs-sharedmem.img" |
	tee "$OUT/init-boot-rmtfs-sharedmem-sha256.txt"
