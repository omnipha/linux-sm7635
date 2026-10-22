#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
AVBTOOL=${AVBTOOL:-$HOME/.local/var/pmbootstrap/chroot_native/usr/bin/avbtool}
AVBTOOL_SHA256=1aa6f2b462aa67aa3fdf488bee83ab517de8ad9d8228c7b45c35267ab2cf6781
PARTITION_SIZE=100663296
VERIFIED_BOOT_SHA256=55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af
VERIFIED_KERNEL_SHA256=b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277
VERIFIED_INIT_SHA256=f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89
VERIFIED_VENDOR_SHA256=6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum; do
	need "$tool"
done
[ -f "$AVBTOOL" ] || die "missing pinned avbtool: $AVBTOOL"
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "candidate artifacts must stay outside this repository" ;;
esac
[ -s "$OUT/boot.img" ] || die "missing verified #21 boot.img: $OUT/boot.img"
[ -s "$OUT/Image.gz" ] || die "missing verified #21 Image.gz: $OUT/Image.gz"
[ -s "$OUT/init_boot.img" ] || die "missing verified #21 init_boot.img"
[ -s "$OUT/vendor_boot.img" ] || die "missing verified #21 vendor_boot.img"
read -r boot_sha _ < <(sha256sum "$OUT/boot.img")
[ "$boot_sha" = "$VERIFIED_BOOT_SHA256" ] || die "boot.img is not the verified #21 image"
read -r kernel_sha _ < <(sha256sum "$OUT/Image.gz")
[ "$kernel_sha" = "$VERIFIED_KERNEL_SHA256" ] || die "Image.gz is not the verified #21 payload"
read -r init_sha _ < <(sha256sum "$OUT/init_boot.img")
[ "$init_sha" = "$VERIFIED_INIT_SHA256" ] || die "init_boot.img is not the verified #21 image"
read -r vendor_sha _ < <(sha256sum "$OUT/vendor_boot.img")
[ "$vendor_sha" = "$VERIFIED_VENDOR_SHA256" ] || die "vendor_boot.img is not the verified #21 image"
read -r avbtool_sha _ < <(sha256sum "$AVBTOOL")
[ "$avbtool_sha" = "$AVBTOOL_SHA256" ] || die "avbtool is not the pinned 1.4.0 script"
[ "$(python3 "$AVBTOOL" version)" = 'avbtool 1.4.0' ] || die "avbtool does not report 1.4.0"

cp -f "$OUT/boot.img" "$OUT/boot-full-footer.img"
python3 "$AVBTOOL" add_hash_footer \
	--image "$OUT/boot-full-footer.img" \
	--partition_name boot \
	--partition_size "$PARTITION_SIZE" \
	--hash_algorithm sha256 \
	--algorithm NONE \
	--salt d41d8cd98f00b204e9800998ecf8427e
python3 "$AVBTOOL" info_image --image "$OUT/boot-full-footer.img" |
	tee "$OUT/boot-full-footer-avb.txt"
python3 - "$OUT/boot.img" "$OUT/boot-full-footer.img" "$PARTITION_SIZE" \
	"$VERIFIED_BOOT_SHA256" <<'PY'
import hashlib
import pathlib
import struct
import sys

base = pathlib.Path(sys.argv[1]).read_bytes()
image = pathlib.Path(sys.argv[2]).read_bytes()
partition_size = int(sys.argv[3])
if hashlib.sha256(base).hexdigest() != sys.argv[4]:
    raise SystemExit("verified #21 boot changed while building the candidate")
if len(image) != partition_size or not image.startswith(base):
    raise SystemExit("candidate changes the verified #21 boot bytes")
if image[-64:-60] != b"AVBf":
    raise SystemExit("candidate has no AVB footer")
original, offset, size = struct.unpack_from(">QQQ", image, len(image) - 52)
if (original, offset) != (len(base), len(base)) or image[offset:offset + 4] != b"AVB0":
    raise SystemExit("candidate footer does not cover exactly the verified #21 boot")
print(f"candidate boot bytes: {len(image)}")
print(f"candidate boot SHA-256: {hashlib.sha256(image).hexdigest()}")
print(f"candidate hashed prefix: {original}")
print(f"candidate vbmeta offset: {offset}")
print(f"candidate vbmeta size: {size}")
PY
(
	cd "$OUT"
	sha256sum boot-full-footer.img boot.img Image.gz init_boot.img vendor_boot.img
) | tee "$OUT/boot-full-footer-sha256.txt"
