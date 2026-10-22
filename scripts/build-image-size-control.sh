#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
DEBUG_KERNEL=${DEBUG_KERNEL:-$OUT/Image.gz}
STOCK_BOOT_SHA256=197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d
STOCK_PAYLOAD_SHA256=dcbd8ae71b7e6341c3604c35360213b1d40a69ac38672e247772d4af399c3651
DEBUG_KERNEL_SHA256=b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277
STOCK_BOOT_SIZE=100663296
STOCK_PAYLOAD_SIZE=13949926
STOCK_IMAGE_LENGTH=35224064
STOCK_IMAGE_SIZE=35913728
DEBUG_IMAGE_SIZE=55508992

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum; do
	need "$tool"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -s "$STOCK_BOOT" ] || die "missing read-only stock boot_a reference: $STOCK_BOOT"
[ -s "$DEBUG_KERNEL" ] || die "missing verified debug Image.gz: $DEBUG_KERNEL"
read -r stock_sha _ < <(sha256sum "$STOCK_BOOT")
[ "$stock_sha" = "$STOCK_BOOT_SHA256" ] ||
	die "stock boot_a is not the verified slot-A reference"
[ "$(stat -c '%s' "$STOCK_BOOT")" -eq "$STOCK_BOOT_SIZE" ] ||
	die "stock boot_a is not the verified slot-A size"
read -r debug_sha _ < <(sha256sum "$DEBUG_KERNEL")
[ "$debug_sha" = "$DEBUG_KERNEL_SHA256" ] ||
	die "Image.gz is not the verified debug payload"

python3 - "$STOCK_BOOT" "$DEBUG_KERNEL" "$OUT/boot-image-size.img" \
	"$STOCK_BOOT_SHA256" "$STOCK_PAYLOAD_SHA256" "$DEBUG_KERNEL_SHA256" \
	"$STOCK_BOOT_SIZE" "$STOCK_PAYLOAD_SIZE" "$STOCK_IMAGE_LENGTH" \
	"$STOCK_IMAGE_SIZE" "$DEBUG_IMAGE_SIZE" <<'PY'
import gzip
import hashlib
import pathlib
import struct
import sys
import zlib

(source, debug, output, expected_boot, expected_payload, expected_debug,
 expected_size, expected_payload_size, expected_length, stock_image_size,
 debug_image_size) = sys.argv[1:]
expected_size = int(expected_size)
expected_payload_size = int(expected_payload_size)
expected_length = int(expected_length)
stock_image_size = int(stock_image_size)
debug_image_size = int(debug_image_size)
page = 4096
header_fields = "<IIQQQQQQ4sI"
stock = pathlib.Path(source).read_bytes()
debug_bytes = pathlib.Path(debug).read_bytes()
if hashlib.sha256(stock).hexdigest() != expected_boot or len(stock) != expected_size:
    raise SystemExit("stock boot_a is not the verified slot-A reference")
if hashlib.sha256(debug_bytes).hexdigest() != expected_debug:
    raise SystemExit("Image.gz is not the verified debug payload")
if stock[:8] != b"ANDROID!":
    raise SystemExit("stock boot header is not ANDROID!")
kernel_size = struct.unpack_from("<I", stock, 8)[0]
if kernel_size != expected_payload_size:
    raise SystemExit("stock kernel-size field is not the verified payload size")
payload = stock[page:page + kernel_size]
if payload[:10] != b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03":
    raise SystemExit("stock payload gzip framing is not the verified envelope")
if hashlib.sha256(payload).hexdigest() != expected_payload:
    raise SystemExit("stock slot-A gzip payload is not the verified reference")
image = bytearray(gzip.decompress(payload))
if len(image) != expected_length:
    raise SystemExit("stock Image length is not the verified decompressed length")
code0, _, text_offset, image_size, flags, reserved2, reserved3, reserved4, magic, pe = (
    struct.unpack_from(header_fields, image, 0))
if (text_offset, flags, reserved2, reserved3, reserved4, magic, pe) != (
        0, 0xA, 0, 0, 0, b"ARMd", 0x40):
    raise SystemExit("stock arm64 Image header is not the verified contract")
if image_size != stock_image_size:
    raise SystemExit("stock image_size is not the verified reservation")
debug_image = gzip.decompress(debug_bytes)
if struct.unpack_from("<Q", debug_image, 16)[0] != debug_image_size:
    raise SystemExit("debug Image.gz image_size is not the verified reservation")
image[16:24] = struct.pack("<Q", debug_image_size)
if len(image) != expected_length or bytes(image[16:24]) != struct.pack("<Q", debug_image_size):
    raise SystemExit("image_size change altered the decompressed length")
compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, 8, zlib.Z_DEFAULT_STRATEGY)
body = compressor.compress(bytes(image)) + compressor.flush()
packed = (b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03" + body +
          struct.pack("<II", zlib.crc32(bytes(image)) & 0xFFFFFFFF, len(image) & 0xFFFFFFFF))
if len(packed) != expected_payload_size:
    raise SystemExit(
        f"level 9 payload is {len(packed)} bytes, not {expected_payload_size}")
if packed[:10] != payload[:10] or packed[3] != 0 or packed[8] != payload[8] or packed[9] != 3:
    raise SystemExit("recompressed payload does not keep the stock gzip framing")
control = bytearray(stock)
control[page:page + kernel_size] = packed
if len(control) != expected_size or struct.unpack_from("<I", control, 8)[0] != kernel_size:
    raise SystemExit("control length or kernel-size field differs from stock")
if control[:page] != stock[:page] or control[page + kernel_size:] != stock[page + kernel_size:]:
    raise SystemExit("control changes a byte outside the stock gzip payload")
decompressed = gzip.decompress(bytes(control[page:page + kernel_size]))
if len(decompressed) != expected_length:
    raise SystemExit("control decompressed length differs from stock")
stock_image_bytes = gzip.decompress(payload)
if (decompressed[:16] != stock_image_bytes[:16] or decompressed[24:] != stock_image_bytes[24:] or
        decompressed[16:24] != struct.pack("<Q", debug_image_size)):
    raise SystemExit("control changes a decompressed byte outside image_size")
pathlib.Path(output).write_bytes(control)
print(f"control boot bytes: {len(control)}")
print(f"control gzip bytes: {len(packed)}")
print(f"control image_size: {struct.unpack_from('<Q', decompressed, 16)[0]}")
print(f"control boot SHA-256: {hashlib.sha256(control).hexdigest()}")
PY

(
	cd "$OUT"
	sha256sum boot-image-size.img
) | tee "$OUT/boot-image-size-sha256.txt"
