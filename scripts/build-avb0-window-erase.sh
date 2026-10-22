#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE_SHA256=13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450
SOURCE_SIZE=13955072
STOCK_SHA256=197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d
STOCK_SIZE=100663296
WINDOW_SIZE=16384
TAIL_OFFSET=13971456
PARTITION_SIZE=100663296
RESULT_SHA256=e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp head cp mv stat tail tee realpath; do
	need "$tool"
done
[ "$#" -eq 0 ] || die 'usage: build-avb0-window-erase.sh (no arguments)'
[ $((SOURCE_SIZE + WINDOW_SIZE)) -eq "$TAIL_OFFSET" ] ||
	die "prefix and erased window do not end at offset $TAIL_OFFSET"
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -f "$OUT/boot-stock-kernel.img" ] || die "missing verified #23 control"
[ -f "$STOCK_BOOT" ] || die "missing stock boot_a reference: $STOCK_BOOT"
[ "$(stat -c '%s' "$OUT/boot-stock-kernel.img")" -eq "$SOURCE_SIZE" ] ||
	die "#23 control is not $SOURCE_SIZE bytes"
[ "$(stat -c '%s' "$STOCK_BOOT")" -eq "$STOCK_SIZE" ] ||
	die "stock boot_a is not $STOCK_SIZE bytes"
read -r source_sha _ < <(sha256sum "$OUT/boot-stock-kernel.img")
[ "$source_sha" = "$SOURCE_SHA256" ] || die "source is not the verified #23 control"
read -r stock_sha _ < <(sha256sum "$STOCK_BOOT")
[ "$stock_sha" = "$STOCK_SHA256" ] || die "stock boot_a is not the verified 197aff11 reference"

candidate=$(mktemp "$OUT/boot-avb0-window-erase.XXXXXXXX.img")
trap 'rm -f -- "$candidate"' EXIT
cp -- "$OUT/boot-stock-kernel.img" "$candidate"
head -c "$WINDOW_SIZE" /dev/zero >>"$candidate"
tail -c "+$((TAIL_OFFSET + 1))" -- "$STOCK_BOOT" >>"$candidate"
[ "$(stat -c '%s' "$candidate")" -eq "$PARTITION_SIZE" ] ||
	die "candidate is not $PARTITION_SIZE bytes"
read -r candidate_sha _ < <(sha256sum "$candidate")
[ "$candidate_sha" = "$RESULT_SHA256" ] || die "candidate SHA-256 is not $RESULT_SHA256"
python3 "$ROOT/scripts/verify-avb0-window-erase.py" "$candidate" \
	"$OUT/boot-stock-kernel.img" "$STOCK_BOOT"
mv -f -- "$candidate" "$OUT/boot-avb0-window-erase.img"
sha256sum "$OUT/boot-avb0-window-erase.img" | tee "$OUT/boot-avb0-window-erase-sha256.txt"
