#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
AVBTOOL=${AVBTOOL:-$HOME/.local/var/pmbootstrap/chroot_native/usr/bin/avbtool}
AVBTOOL_SHA256=1aa6f2b462aa67aa3fdf488bee83ab517de8ad9d8228c7b45c35267ab2cf6781
SOURCE_SHA256=13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450
PARTITION_SIZE=100663296
SOURCE_SIZE=13955072

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in python3 sha256sum mktemp; do
	need "$tool"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -f "$OUT/boot-stock-kernel.img" ] || die "missing verified #23 control"
[ -f "$OUT/boot.img" ] || die "missing verified #21 boot image"
[ -f "$OUT/boot-full-footer.img" ] || die "missing verified #25 footer image"
[ -f "$AVBTOOL" ] || die "missing pinned avbtool: $AVBTOOL"
[ "$(stat -c '%s' "$OUT/boot-stock-kernel.img")" -eq "$SOURCE_SIZE" ] ||
	die "#23 control is not $SOURCE_SIZE bytes"
read -r source_sha _ < <(sha256sum "$OUT/boot-stock-kernel.img")
[ "$source_sha" = "$SOURCE_SHA256" ] || die "source is not the verified #23 control"
read -r avbtool_sha _ < <(sha256sum "$AVBTOOL")
[ "$avbtool_sha" = "$AVBTOOL_SHA256" ] || die "avbtool is not the pinned 1.4.0 script"
[ "$(python3 "$AVBTOOL" version)" = 'avbtool 1.4.0' ] ||
	die "avbtool does not report 1.4.0"

candidate=$(mktemp "$OUT/boot-stock-full-footer.XXXXXXXX.img")
trap 'rm -f -- "$candidate"' EXIT
cp -- "$OUT/boot-stock-kernel.img" "$candidate"
python3 "$AVBTOOL" add_hash_footer \
	--image "$candidate" \
	--partition_name boot \
	--partition_size "$PARTITION_SIZE" \
	--hash_algorithm sha256 \
	--algorithm NONE \
	--salt d41d8cd98f00b204e9800998ecf8427e
python3 "$ROOT/scripts/verify-stock-full-footer.py" "$candidate" \
	"$OUT/boot-stock-kernel.img" "$OUT/boot.img" "$OUT/boot-full-footer.img"
mv -f -- "$candidate" "$OUT/boot-stock-full-footer.img"
python3 "$AVBTOOL" info_image --image "$OUT/boot-stock-full-footer.img" |
	tee "$OUT/boot-stock-full-footer-avb.txt"
sha256sum "$OUT/boot-stock-full-footer.img" | tee "$OUT/boot-stock-full-footer-sha256.txt"
