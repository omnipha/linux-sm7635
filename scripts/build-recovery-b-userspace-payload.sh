#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_B=${STOCK_B:-$HOME/phone-second-life-data/mb003/parts/recovery_b.img}
ARCHIVE=${ARCHIVE:-$WORK/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
OUTPUT=${OUTPUT:-$OUT/recovery_b-userspace.img}
export PYTHONDONTWRITEBYTECODE=1
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die 'usage: build-recovery-b-userspace-payload.sh'
for tool in python3 sha256sum mktemp stat realpath cmp flock git; do command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"; done
[ -d "$WORK" ] && [ -d "$OUT" ] || die 'missing build or output directory'
for path in "$STOCK_B" "$ARCHIVE"; do [ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"; done
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
for path in "$STOCK_B" "$ARCHIVE"; do [ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$path")" ] || die 'output must not overwrite an input'; done
[ -d "$(dirname -- "$OUTPUT")" ] && [ ! -L "$OUTPUT" ] || die 'unsafe output path'
[ "$(stat -c %s "$STOCK_B")" -eq 104857600 ] || die 'stock recovery_b size mismatch'
[ "$(stat -c %s "$ARCHIVE")" -eq 23713302 ] || die 'archive size mismatch'
[ "$(sha256sum "$STOCK_B" | cut -d ' ' -f 1)" = 6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b ] || die 'unpinned stock recovery_b'
[ "$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)" = 7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26 ] || die 'unpinned userspace archive'
exec 9>"$WORK/i171-image.lock"
flock 9 || die 'another recovery_b build is in progress'
first=$(mktemp "$OUT/recovery_b-userspace.XXXXXXXX.img")
second=$(mktemp "$OUT/recovery_b-userspace.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second"' EXIT
for candidate in "$first" "$second"; do
    python3 -B "$ROOT/scripts/build-recovery-b-userspace-payload.py" --build "$STOCK_B" "$ARCHIVE" "$candidate"
done
cmp -s "$first" "$second" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 104857600 ] || die 'candidate size mismatch'
python3 -B "$ROOT/scripts/build-recovery-b-userspace-payload.py" --self-test "$STOCK_B" "$ARCHIVE" "$first"
mv -f -- "$first" "$OUTPUT"
python3 -B "$ROOT/scripts/build-recovery-b-userspace-payload.py" --verify "$STOCK_B" "$ARCHIVE" "$OUTPUT"
sha256sum "$OUTPUT"
