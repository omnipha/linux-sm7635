#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
STOCK_BOOT_SHA256=197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d
STOCK_BOOT_SIZE=100663296
PADDING_OFFSET=13954122

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum; do
	need "$tool"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -s "$STOCK_BOOT" ] || die "missing read-only stock boot_a reference: $STOCK_BOOT"
read -r stock_sha _ < <(sha256sum "$STOCK_BOOT")
[ "$stock_sha" = "$STOCK_BOOT_SHA256" ] ||
	die "stock boot_a is not the verified slot-A reference"
[ "$(stat -c '%s' "$STOCK_BOOT")" -eq "$STOCK_BOOT_SIZE" ] ||
	die "stock boot_a is not the verified slot-A size"

python3 - "$STOCK_BOOT" "$OUT/boot-hash-boundary.img" "$STOCK_BOOT_SHA256" \
	"$STOCK_BOOT_SIZE" "$PADDING_OFFSET" <<'PY'
import hashlib
import pathlib
import sys

source, output, expected_sha, expected_size, offset = sys.argv[1:]
expected_size = int(expected_size)
offset = int(offset)
image = bytearray(pathlib.Path(source).read_bytes())
if hashlib.sha256(image).hexdigest() != expected_sha or len(image) != expected_size:
    raise SystemExit("stock boot_a is not the verified slot-A reference")
if image[offset] != 0:
    raise SystemExit("selected padding byte is not zero")
image[offset] = 1
if len(image) != expected_size:
    raise SystemExit("control length is not the stock boot partition size")
changed = [index for index, (left, right) in enumerate(
    zip(image, pathlib.Path(source).read_bytes(), strict=True)) if left != right]
if changed != [offset]:
    raise SystemExit("control changes a byte other than the selected padding offset")
pathlib.Path(output).write_bytes(image)
print(f"control boot bytes: {len(image)}")
print(f"control changed offset: {offset}")
print(f"control boot SHA-256: {hashlib.sha256(image).hexdigest()}")
PY

(
	cd "$OUT"
	sha256sum boot-hash-boundary.img
) | tee "$OUT/boot-hash-boundary-sha256.txt"
