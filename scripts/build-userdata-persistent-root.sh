#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
ARCHIVE=${ARCHIVE:-$WORK/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
OUTPUT=${OUTPUT:-$OUT/userdata-persistent-root.img}
export PYTHONDONTWRITEBYTECODE=1
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || die 'usage: build-userdata-persistent-root.sh'
for tool in python3 sha256sum mktemp stat realpath cmp flock git; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$WORK" ] && [ -d "$OUT" ] || die 'missing build or output directory'
[ -f "$ARCHIVE" ] && [ ! -L "$ARCHIVE" ] || die 'missing or symlinked archive'
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'output directory must be outside Git';; esac
case "$(realpath -m "$OUTPUT")/" in "$ROOT"/*) die 'output must be outside Git';; esac
[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$ARCHIVE")" ] || die 'output must not overwrite the archive'
[ -d "$(dirname -- "$OUTPUT")" ] && [ ! -L "$OUTPUT" ] || die 'unsafe output path'
[ "$(stat -c %s "$ARCHIVE")" -eq 23713302 ] || die 'archive size mismatch'
[ "$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)" = 7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26 ] || die 'unpinned userspace archive'
exec 9>"$WORK/i197-userdata.lock"
flock 9 || die 'another persistent userdata build is in progress'
first=$(mktemp "$OUT/userdata-persistent-root.XXXXXXXX.img")
second=$(mktemp "$OUT/userdata-persistent-root.XXXXXXXX.img")
trap 'rm -f -- "$first" "$second"' EXIT
for candidate in "$first" "$second"; do
	python3 -B "$ROOT/scripts/build-userdata-persistent-root.py" --build "$ARCHIVE" "$candidate"
done
cmp -s "$first" "$second" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 100663296 ] || die 'candidate size mismatch'
python3 -B "$ROOT/scripts/build-userdata-persistent-root.py" --self-test "$ARCHIVE" "$first"
mv -f -- "$first" "$OUTPUT"
python3 -B "$ROOT/scripts/build-userdata-persistent-root.py" --verify "$ARCHIVE" "$OUTPUT"
sha256sum "$OUTPUT"
