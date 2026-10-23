#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE=$ROOT/initramfs/restart2.c
IMAGE_SIZE=872
SOURCE_SHA256=6806922e9e5138df25ee13e5f11d4fad555479830436e283b040b6e666133f96
HELPER_SHA256=fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in sha256sum stat mktemp cmp file realpath mv tee grep cat; do
	need "$tool"
done
[ "$#" -eq 0 ] || die 'usage: build-restart2-helper.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "control artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
for tool in aarch64-linux-gnu-gcc aarch64-linux-gnu-strip; do
	need "$tool"
done
[ -f "$SOURCE" ] || die "missing input: $SOURCE"
read -r source_sha _ < <(sha256sum "$SOURCE")
[ "$source_sha" = "$SOURCE_SHA256" ] || die "RESTART2 helper source is not the committed file"

candidate=$(mktemp "$OUT/restart2.XXXXXXXX")
second=$(mktemp "$OUT/restart2.XXXXXXXX")
trap 'rm -f -- "$candidate" "$second"' EXIT
for helper in "$candidate" "$second"; do
	aarch64-linux-gnu-gcc -nostdlib -static -ffreestanding \
		-fno-asynchronous-unwind-tables -fno-stack-protector \
		-fno-pie -no-pie -Wl,--build-id=none \
		-Wall -Wextra -Werror -Os \
		-o "$helper" "$SOURCE" 2>"$helper.log" ||
		{ cat "$helper.log" >&2; die "cross compiler did not build the helper"; }
	aarch64-linux-gnu-strip --strip-all -R .comment "$helper"
	[ "$(stat -c '%s' "$helper")" -eq "$IMAGE_SIZE" ] || die "helper is not $IMAGE_SIZE bytes"
	file "$helper" | grep -q 'ARM aarch64' || die "helper is not arm64"
	file "$helper" | grep -q 'statically linked' || die "helper is not static"
	read -r helper_sha _ < <(sha256sum "$helper")
	[ "$helper_sha" = "$HELPER_SHA256" ] ||
		die "helper is not reproducible: $helper_sha != $HELPER_SHA256"
	rm -f -- "$helper.log"
done
cmp -s -- "$candidate" "$second" || die "repeated helper builds differ"
mv -f -- "$candidate" "$OUT/restart2"
sha256sum "$OUT/restart2" | tee "$OUT/restart2-sha256.txt"
