#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
BASE=${BASE:-$WORK/out/init_boot-mindstorms-wlan.img}
STOCK_VENDOR_B=${STOCK_VENDOR_B:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_b.img}
OUTPUT=${OUTPUT:-$OUT/init_boot-root-contract-carrier.img}
CARRIER=${CARRIER:-$OUT/vendor_boot_b-root-contract.img}
export PYTHONDONTWRITEBYTECODE=1
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die 'usage: build-init-boot-persistent-root.sh'
for tool in python3 sha256sum mktemp stat realpath cmp flock git; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$OUT" ] && [ -d "$WORK" ] || die 'missing build or output directory'
for path in "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"; do
	[ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"
done
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
case "$(realpath -m "$CARRIER")/" in "$ROOT"/*) die 'carrier output must be outside Git';; esac
[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$CARRIER")" ] || die 'outputs must differ'
for output in "$OUTPUT" "$CARRIER"; do
	for input in "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"; do
		[ "$(realpath -m "$output")" != "$(realpath -m "$input")" ] || die 'output must not overwrite an input'
	done
	[ -d "$(dirname -- "$output")" ] && [ ! -L "$output" ] || die 'unsafe output path'
done
[ "$(stat -c %s "$STOCK_INIT")" -eq 8388608 ] || die 'stock image size mismatch'
[ "$(stat -c %s "$BASE")" -eq 8388608 ] || die 'base image size mismatch'
[ "$(sha256sum "$STOCK_INIT" | cut -d ' ' -f 1)" = baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193 ] || die 'unpinned stock image'
[ "$(sha256sum "$BASE" | cut -d ' ' -f 1)" = 5b5a60d4ceaf1551217874136c0de9a26f6b3ec29f9f586e2b7cdf0d728466d6 ] || die 'base is not the installed run-66 init_boot'
[ "$(stat -c %s "$STOCK_VENDOR_B")" -eq 100663296 ] || die 'stock carrier size mismatch'
[ "$(sha256sum "$STOCK_VENDOR_B" | cut -d ' ' -f 1)" = 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253 ] || die 'stock carrier is not vendor_boot_b'
exec 9>"$WORK/i204-root-contract.lock"
flock 9 || die 'another root-contract carrier build is in progress'
first=$(mktemp "$OUT/init_boot-root-contract.XXXXXXXX.img")
second=$(mktemp "$OUT/init_boot-root-contract.XXXXXXXX.img")
first_carrier=$(mktemp "$OUT/vendor_boot_b-root-contract.XXXXXXXX.img")
second_carrier=$(mktemp "$OUT/vendor_boot_b-root-contract.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second" "$first_carrier" "$second_carrier"' EXIT
for pair in "$first:$first_carrier" "$second:$second_carrier"; do
	candidate=${pair%%:*}
	carrier=${pair##*:}
	python3 -B "$ROOT/scripts/build-init-boot-persistent-root.py" --build "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B" "$candidate" "$carrier"
	python3 -B "$ROOT/scripts/verify-init-boot-persistent-root.py" --self-test "$candidate" "$carrier" "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"
done
cmp -s "$first" "$second" && cmp -s "$first_carrier" "$second_carrier" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 8388608 ] || die 'candidate size mismatch'
[ "$(stat -c %s "$first_carrier")" -eq 100663296 ] || die 'carrier size mismatch'
mv -f -- "$first" "$OUTPUT"
mv -f -- "$first_carrier" "$CARRIER"
python3 -B "$ROOT/scripts/verify-init-boot-persistent-root.py" "$OUTPUT" "$CARRIER" "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"
sha256sum "$OUTPUT" "$CARRIER"
