#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
BASE=${BASE:-$WORK/out/init_boot-mindstorms-wlan.img}
OUTPUT=${OUTPUT:-$OUT/init_boot-persistent-root.img}
export PYTHONDONTWRITEBYTECODE=1
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die 'usage: build-init-boot-persistent-root.sh'
for tool in python3 sha256sum mktemp stat realpath cmp flock git; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$OUT" ] && [ -d "$WORK" ] || die 'missing build or output directory'
for path in "$STOCK_INIT" "$BASE"; do
	[ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"
done
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$STOCK_INIT")" ] &&
	[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$BASE")" ] || die 'output must not overwrite an input'
[ -d "$(dirname -- "$OUTPUT")" ] && [ ! -L "$OUTPUT" ] || die 'unsafe output path'
[ "$(stat -c %s "$STOCK_INIT")" -eq 8388608 ] || die 'stock image size mismatch'
[ "$(stat -c %s "$BASE")" -eq 8388608 ] || die 'base image size mismatch'
[ "$(sha256sum "$STOCK_INIT" | cut -d ' ' -f 1)" = baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193 ] || die 'unpinned stock image'
[ "$(sha256sum "$BASE" | cut -d ' ' -f 1)" = 5b5a60d4ceaf1551217874136c0de9a26f6b3ec29f9f586e2b7cdf0d728466d6 ] || die 'base is not the installed run-66 init_boot'
exec 9>"$WORK/i197-init-boot.lock"
flock 9 || die 'another persistent init_boot build is in progress'
first=$(mktemp "$OUT/init_boot-persistent-root.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-persistent-root.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second"' EXIT
for candidate in "$first" "$second"; do
	python3 -B "$ROOT/scripts/build-init-boot-persistent-root.py" --build "$STOCK_INIT" "$BASE" "$candidate"
	python3 -B "$ROOT/scripts/verify-init-boot-persistent-root.py" --self-test "$candidate" "$STOCK_INIT" "$BASE"
done
cmp -s "$first" "$second" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 8388608 ] || die 'candidate size mismatch'
mv -f -- "$first" "$OUTPUT"
python3 -B "$ROOT/scripts/verify-init-boot-persistent-root.py" "$OUTPUT" "$STOCK_INIT" "$BASE"
sha256sum "$OUTPUT"
