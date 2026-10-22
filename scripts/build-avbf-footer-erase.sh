#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE_SHA256=e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f
STOCK_SHA256=197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d
IMAGE_SIZE=100663296
FOOTER_OFFSET=100663232
FOOTER_SIZE=64
RESULT_SHA256=7c409cdefe9e0f24cbe53e44d5bbab8ff50adadb9fbfb26d64917fe1a6fc4ddf

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp cp mv stat dd realpath cmp; do
	need "$tool"
done
[ "$#" -eq 0 ] || die 'usage: build-avbf-footer-erase.sh (no arguments)'
[ $((FOOTER_OFFSET + FOOTER_SIZE)) -eq "$IMAGE_SIZE" ] ||
	die "footer window does not end at $IMAGE_SIZE"
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -f "$OUT/boot-avb0-window-erase.img" ] || die "missing verified #36 control"
[ -f "$STOCK_BOOT" ] || die "missing stock boot_a reference: $STOCK_BOOT"
[ "$(stat -c '%s' "$OUT/boot-avb0-window-erase.img")" -eq "$IMAGE_SIZE" ] ||
	die "#36 control is not $IMAGE_SIZE bytes"
[ "$(stat -c '%s' "$STOCK_BOOT")" -eq "$IMAGE_SIZE" ] ||
	die "stock boot_a is not $IMAGE_SIZE bytes"
read -r source_sha _ < <(sha256sum "$OUT/boot-avb0-window-erase.img")
[ "$source_sha" = "$SOURCE_SHA256" ] || die "source is not the verified #36 control"
read -r stock_sha _ < <(sha256sum "$STOCK_BOOT")
[ "$stock_sha" = "$STOCK_SHA256" ] || die "stock boot_a is not the verified 197aff11 reference"
python3 "$ROOT/scripts/verify-avbf-footer-erase.py" --source \
	"$OUT/boot-avb0-window-erase.img" "$STOCK_BOOT"

candidate=$(mktemp "$OUT/boot-avbf-footer-erase.XXXXXXXX.img")
second=$(mktemp "$OUT/boot-avbf-footer-erase.XXXXXXXX.img")
trap 'rm -f -- "$candidate" "$second"' EXIT
for image in "$candidate" "$second"; do
	cp -- "$OUT/boot-avb0-window-erase.img" "$image"
	dd if=/dev/zero of="$image" bs=1 seek="$FOOTER_OFFSET" count="$FOOTER_SIZE" \
		conv=notrunc status=none
	[ "$(stat -c '%s' "$image")" -eq "$IMAGE_SIZE" ] ||
		die "candidate is not $IMAGE_SIZE bytes"
	read -r candidate_sha _ < <(sha256sum "$image")
	[ "$candidate_sha" = "$RESULT_SHA256" ] || die "candidate SHA-256 is not $RESULT_SHA256"
	python3 "$ROOT/scripts/verify-avbf-footer-erase.py" "$image" \
		"$OUT/boot-avb0-window-erase.img" "$STOCK_BOOT"
	printf 'build SHA-256: %s\n' "$candidate_sha"
done
cmp -s -- "$candidate" "$second" || die "repeated builds differ"
mv -f -- "$candidate" "$OUT/boot-avbf-footer-erase.img"
sha256sum "$OUT/boot-avbf-footer-erase.img" | tee "$OUT/boot-avbf-footer-erase-sha256.txt"
