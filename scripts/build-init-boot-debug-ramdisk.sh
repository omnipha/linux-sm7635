#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
STOCK_SHA256=baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193
RAMDISK_SHA256=caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f
IMAGE_SIZE=8388608
RAMDISK_SIZE=1672600
RESULT_SHA256=f4a00ce3a1926f9b54eaa958158691efaabe90a9ea715d2bac3d424095f2f948

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp stat realpath cmp mv; do
	need "$tool"
done
[ "$#" -eq 0 ] || die 'usage: build-init-boot-debug-ramdisk.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -f "$STOCK_INIT" ] || die "missing stock init_boot_a reference: $STOCK_INIT"
[ -f "$OUT/initramfs.cpio.gz" ] || die "missing debug ramdisk: $OUT/initramfs.cpio.gz"
[ "$(stat -c '%s' "$STOCK_INIT")" -eq "$IMAGE_SIZE" ] ||
	die "stock init_boot is not $IMAGE_SIZE bytes"
[ "$(stat -c '%s' "$OUT/initramfs.cpio.gz")" -eq "$RAMDISK_SIZE" ] ||
	die "debug ramdisk is not $RAMDISK_SIZE bytes"
read -r stock_sha _ < <(sha256sum "$STOCK_INIT")
[ "$stock_sha" = "$STOCK_SHA256" ] ||
	die "stock init_boot is not the verified baa33fd4 slot-A reference"
read -r ramdisk_sha _ < <(sha256sum "$OUT/initramfs.cpio.gz")
[ "$ramdisk_sha" = "$RAMDISK_SHA256" ] ||
	die "debug ramdisk is not the verified caa3eb82 gzip cpio"
python3 "$ROOT/scripts/verify-init-boot-debug-ramdisk.py" --source \
	"$STOCK_INIT" "$OUT/initramfs.cpio.gz"

candidate=$(mktemp "$OUT/init_boot-debug-ramdisk.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-debug-ramdisk.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	python3 "$ROOT/scripts/build-init-boot-debug-ramdisk-payload.py" \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz" "$image"
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] ||
		die "candidate is not $IMAGE_SIZE bytes"
	read -r candidate_sha _ < <(sha256sum "$image")
	[ "$candidate_sha" = "$RESULT_SHA256" ] || die "candidate SHA-256 is not $RESULT_SHA256"
	python3 "$ROOT/scripts/verify-init-boot-debug-ramdisk.py" "$image" \
		"$STOCK_INIT" "$OUT/initramfs.cpio.gz"
	printf 'build SHA-256: %s\n' "$candidate_sha"
done
cmp -s -- "$candidate" "$second" || die "repeated builds differ"
mv -f -- "$candidate" "$OUT/init_boot-debug-ramdisk.img"
sha256sum "$OUT/init_boot-debug-ramdisk.img" | tee "$OUT/init-boot-debug-ramdisk-sha256.txt"
