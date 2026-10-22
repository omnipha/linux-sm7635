#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE_SHA256=13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450
SOURCE_SIZE=13955072
PARTITION_SIZE=100663296
TAIL_SIZE=86708224
RESULT_SHA256=db2c635d5c51aed47cf6a626244bba5be6e6eeb240f0dd2d0ed0e72d85fdff00

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp head cp mv stat; do
	need "$tool"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -f "$OUT/boot-stock-kernel.img" ] || die "missing verified #23 control"
[ -f "$OUT/boot-stock-full-footer.img" ] || die "missing verified #32 comparison image"
[ "$(stat -c '%s' "$OUT/boot-stock-kernel.img")" -eq "$SOURCE_SIZE" ] ||
	die "#23 control is not $SOURCE_SIZE bytes"
read -r source_sha _ < <(sha256sum "$OUT/boot-stock-kernel.img")
[ "$source_sha" = "$SOURCE_SHA256" ] || die "source is not the verified #23 control"

candidate=$(mktemp "$OUT/boot-blank-tail.XXXXXXXX.img")
trap 'rm -f -- "$candidate"' EXIT
cp -- "$OUT/boot-stock-kernel.img" "$candidate"
head -c "$TAIL_SIZE" /dev/zero >>"$candidate"
[ "$(stat -c '%s' "$candidate")" -eq "$PARTITION_SIZE" ] ||
	die "candidate is not $PARTITION_SIZE bytes"
read -r candidate_sha _ < <(sha256sum "$candidate")
[ "$candidate_sha" = "$RESULT_SHA256" ] || die "candidate SHA-256 is not $RESULT_SHA256"
python3 "$ROOT/scripts/verify-blank-tail-control.py" "$candidate" \
	"$OUT/boot-stock-kernel.img" "$OUT/boot-stock-full-footer.img"
mv -f -- "$candidate" "$OUT/boot-blank-tail.img"
sha256sum "$OUT/boot-blank-tail.img" | tee "$OUT/boot-blank-tail-sha256.txt"
