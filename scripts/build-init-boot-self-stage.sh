#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
PREVIOUS=${PREVIOUS:-$WORK/out/init_boot-pid1-handoff.img}
OUTPUT=${OUTPUT:-$OUT/init_boot-self-stage-recovery-b.img}
export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die 'usage: build-init-boot-self-stage.sh'
for tool in python3 sha256sum mktemp stat realpath cmp flock git; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$OUT" ] || die "missing output directory: $OUT"
[ -d "$WORK" ] || die "missing build directory: $WORK"
for path in "$STOCK_INIT" "$PREVIOUS"; do
	[ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"
done
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$STOCK_INIT")" ] &&
	[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$PREVIOUS")" ] ||
	die 'output must not overwrite an input'
[ -d "$(dirname -- "$OUTPUT")" ] && [ ! -L "$OUTPUT" ] || die 'unsafe output path'
[ "$(stat -c %s "$STOCK_INIT")" -eq 8388608 ] || die 'stock image size mismatch'
[ "$(stat -c %s "$PREVIOUS")" -eq 8388608 ] || die 'previous image size mismatch'
[ "$(sha256sum "$STOCK_INIT" | cut -d ' ' -f 1)" = baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193 ] || die 'unpinned stock image'
[ "$(sha256sum "$PREVIOUS" | cut -d ' ' -f 1)" = fef030081e04d3a90451bb7d64dcfa7668c41dc4248e6e0b1959fdb40efce948 ] || die 'unpinned previous image'
exec 9>"$WORK/i164-init-boot.lock"
flock 9 || die 'another init_boot build is in progress'
first=$(mktemp "$OUT/init_boot-self-stage-recovery-b.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-self-stage-recovery-b.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second"' EXIT
for candidate in "$first" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-self-stage.py" --build \
		"$STOCK_INIT" "$PREVIOUS" "$candidate"
	python3 -B "$ROOT/scripts/verify-init-boot-self-stage.py" --self-test \
		"$candidate" "$STOCK_INIT" "$PREVIOUS"
done
cmp -s "$first" "$second" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 8388608 ] || die 'candidate size mismatch'
mv -f -- "$first" "$OUTPUT"
sha256sum "$OUTPUT"
