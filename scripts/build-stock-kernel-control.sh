#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
VERIFIED_BOOT_SHA256=55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af
VERIFIED_KERNEL_SHA256=b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277
STOCK_PAYLOAD_SHA256=dcbd8ae71b7e6341c3604c35360213b1d40a69ac38672e247772d4af399c3651
STOCK_BOOT_SHA256=197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum; do
	need "$tool"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -s "$OUT/boot.img" ] || die "missing verified #21 boot.img: $OUT/boot.img"
[ -s "$OUT/Image.gz" ] || die "missing verified #21 Image.gz: $OUT/Image.gz"
[ -s "$STOCK_BOOT" ] || die "missing read-only stock boot_a reference: $STOCK_BOOT"
read -r boot_sha _ < <(sha256sum "$OUT/boot.img")
[ "$boot_sha" = "$VERIFIED_BOOT_SHA256" ] ||
	die "boot.img is not the verified #21 image"
read -r kernel_sha _ < <(sha256sum "$OUT/Image.gz")
[ "$kernel_sha" = "$VERIFIED_KERNEL_SHA256" ] ||
	die "Image.gz is not the verified #21 payload"
read -r stock_sha _ < <(sha256sum "$STOCK_BOOT")
[ "$stock_sha" = "$STOCK_BOOT_SHA256" ] ||
	die "stock boot_a is not the verified slot-A reference"

python3 - "$OUT/boot.img" "$STOCK_BOOT" "$OUT/boot-stock-kernel.img" \
	"$VERIFIED_BOOT_SHA256" "$STOCK_PAYLOAD_SHA256" <<'PY'
import hashlib
import pathlib
import struct
import sys

page = 4096
source, stock, output, expected_source, expected_payload = sys.argv[1:]
source_bytes = pathlib.Path(source).read_bytes()
stock_bytes = pathlib.Path(stock).read_bytes()
if hashlib.sha256(source_bytes).hexdigest() != expected_source:
    raise SystemExit("verified #21 boot image changed while reading")
if source_bytes[:8] != b"ANDROID!" or stock_bytes[:8] != b"ANDROID!":
    raise SystemExit("boot header is not ANDROID!")
if struct.unpack_from("<I", source_bytes, 40)[0] != 4:
    raise SystemExit("verified #21 header is not v4")
kernel_size = struct.unpack_from("<I", source_bytes, 8)[0]
stock_kernel_size = struct.unpack_from("<I", stock_bytes, 8)[0]
if struct.unpack_from("<I", source_bytes, 12)[0] != 0:
    raise SystemExit("verified #21 generic ramdisk is not empty")
payload_end = page + kernel_size
aligned_end = page + (kernel_size + page - 1) // page * page
if len(source_bytes) != aligned_end or any(source_bytes[payload_end:aligned_end]):
    raise SystemExit("verified #21 image has data after the kernel")
payload = stock_bytes[page:page + stock_kernel_size]
if payload[:2] != b"\x1f\x8b":
    raise SystemExit("stock slot-A boot payload is not gzip")
if hashlib.sha256(payload).hexdigest() != expected_payload:
    raise SystemExit("stock slot-A boot payload is not the verified gzip bytes")
header = bytearray(source_bytes[:page])
struct.pack_into("<I", header, 8, len(payload))
if bytes(header[:8]) != source_bytes[:8] or bytes(header[12:]) != source_bytes[12:page]:
    raise SystemExit("control header changes more than the kernel-size field")
control = bytes(header) + payload + bytes(-len(payload) % page)
pathlib.Path(output).write_bytes(control)
print(f"control boot bytes: {len(control)}")
print(f"control kernel bytes: {len(payload)}")
print(f"control boot SHA-256: {hashlib.sha256(control).hexdigest()}")
PY

(
	cd "$OUT"
	sha256sum boot-stock-kernel.img boot.img init_boot.img vendor_boot.img
) | tee "$OUT/boot-stock-kernel-sha256.txt"
