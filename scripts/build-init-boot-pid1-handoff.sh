#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
RUN43=${RUN43:-$WORK/out/init_boot-psoc-hold-wlan-node.img}
OUTPUT=${OUTPUT:-$OUT/init_boot-pid1-handoff.img}
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 2 ] && [ "$1" = --script ] || die 'usage: build-init-boot-pid1-handoff.sh --script TRANSITION'
SCRIPT=$2
for tool in python3 sha256sum mktemp stat realpath cmp flock; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -d "$WORK" ] || die "missing build directory: $WORK"
for path in "$STOCK_INIT" "$RUN43" "$SCRIPT"; do
	[ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"
done
[ -x "$SCRIPT" ] || die 'transition script must be executable'
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$STOCK_INIT")" ] &&
	[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$RUN43")" ] &&
	[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$SCRIPT")" ] ||
	die 'output must not overwrite an input'
[ -d "$(dirname -- "$OUTPUT")" ] && [ ! -L "$OUTPUT" ] || die 'unsafe output path'
[ "$(stat -c %s "$STOCK_INIT")" -eq 8388608 ] || die 'stock image size mismatch'
[ "$(stat -c %s "$RUN43")" -eq 8388608 ] || die 'run-43 image size mismatch'
[ "$(sha256sum "$STOCK_INIT" | cut -d ' ' -f 1)" = baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193 ] || die 'unpinned stock image'
[ "$(sha256sum "$RUN43" | cut -d ' ' -f 1)" = 0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa ] || die 'unpinned run-43 image'
SCRIPT_SHA=$(sha256sum "$SCRIPT" | cut -d ' ' -f 1)
exec 9>"$WORK/i124-image.lock"
flock 9 || die 'another init_boot build is in progress'
first=$(mktemp "$OUT/init_boot-pid1-handoff.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-pid1-handoff.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second"' EXIT
for candidate in "$first" "$second"; do
	[ "$(sha256sum "$SCRIPT" | cut -d ' ' -f 1)" = "$SCRIPT_SHA" ] || die 'transition script changed during build'
	python3 -B "$ROOT/scripts/build-init-boot-pid1-handoff.py" --build \
		"$STOCK_INIT" "$RUN43" --script "$SCRIPT" "$candidate"
	python3 -B "$ROOT/scripts/verify-init-boot-pid1-handoff.py" --self-test \
		"$candidate" "$STOCK_INIT" "$RUN43" --script "$SCRIPT"
done
[ "$(sha256sum "$SCRIPT" | cut -d ' ' -f 1)" = "$SCRIPT_SHA" ] || die 'transition script changed during build'
cmp -s "$first" "$second" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 8388608 ] || die 'candidate size mismatch'
mv -f -- "$first" "$OUTPUT"
sha256sum "$OUTPUT"
