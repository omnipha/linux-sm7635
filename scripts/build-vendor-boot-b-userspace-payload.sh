#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_B=${STOCK_B:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_b.img}
STOCK_A=${STOCK_A:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_a.img}
ARCHIVE=${ARCHIVE:-$WORK/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
OUTPUT=${OUTPUT:-$OUT/vendor_boot_b-userspace.img}
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die 'usage: build-vendor-boot-b-userspace-payload.sh'
for tool in python3 sha256sum mktemp stat realpath cmp flock git; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$WORK" ] && [ -d "$OUT" ] || die 'missing build or output directory'
for path in "$STOCK_B" "$STOCK_A" "$ARCHIVE"; do
	[ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"
done
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
for path in "$STOCK_B" "$STOCK_A" "$ARCHIVE"; do
	[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$path")" ] || die 'output must not overwrite an input'
done
[ -d "$(dirname -- "$OUTPUT")" ] && [ ! -L "$OUTPUT" ] || die 'unsafe output path'
[ "$(stat -c %s "$STOCK_B")" -eq 100663296 ] || die 'stock vendor_boot_b size mismatch'
[ "$(stat -c %s "$STOCK_A")" -eq 100663296 ] || die 'stock vendor_boot_a size mismatch'
[ "$(stat -c %s "$ARCHIVE")" -eq 23713302 ] || die 'archive size mismatch'
[ "$(sha256sum "$STOCK_B" | cut -d ' ' -f 1)" = 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253 ] || die 'unpinned stock vendor_boot_b'
[ "$(sha256sum "$STOCK_A" | cut -d ' ' -f 1)" = 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253 ] || die 'unpinned stock vendor_boot_a'
[ "$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)" = 7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26 ] || die 'unpinned userspace archive'
cmp -s "$STOCK_A" "$STOCK_B" || die 'stock vendor_boot slots differ'
exec 9>"$WORK/i164-image.lock"
flock 9 || die 'another vendor_boot build is in progress'
first=$(mktemp "$OUT/vendor_boot_b-userspace.XXXXXXXX.img")
second=$(mktemp "$OUT/vendor_boot_b-userspace.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second"' EXIT
for candidate in "$first" "$second"; do
	[ "$(sha256sum "$STOCK_B" | cut -d ' ' -f 1)" = 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253 ] || die 'stock changed during build'
	[ "$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)" = 7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26 ] || die 'archive changed during build'
	python3 -B "$ROOT/scripts/build-vendor-boot-b-userspace-payload.py" --build \
		"$STOCK_B" "$ARCHIVE" "$candidate" "$STOCK_A"
done
cmp -s "$first" "$second" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 100663296 ] || die 'candidate size mismatch'
python3 -B "$ROOT/scripts/build-vendor-boot-b-userspace-payload.py" --self-test \
	"$STOCK_B" "$ARCHIVE" "$first" "$STOCK_A"
mv -f -- "$first" "$OUTPUT"
python3 -B "$ROOT/scripts/build-vendor-boot-b-userspace-payload.py" --verify \
	"$STOCK_B" "$ARCHIVE" "$OUTPUT" "$STOCK_A"
sha256sum "$OUTPUT"
