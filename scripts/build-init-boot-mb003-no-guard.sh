#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${WORK:-$HOME/sm7635-build}
OUT=${OUT:-$WORK/out}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
BASE=${BASE:-$WORK/out/init_boot-mindstorms-wlan.img}
STOCK_VENDOR_B=${STOCK_VENDOR_B:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_b.img}
OUTPUT=${OUTPUT:-$OUT/init_boot-mb003-no-guard-v3.img}
CARRIER=${CARRIER:-$OUT/vendor_boot_b-mb003-no-guard-v3.img}
MANIFEST=${MANIFEST:-$OUT/mb003-no-guard-pair-v3.manifest.json}
LOCK=$WORK/i204-root-contract.lock
export PYTHONDONTWRITEBYTECODE=1
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || { [ "$#" -eq 1 ] && [ "$1" = --locked ]; } || die 'usage: build-init-boot-mb003-no-guard.sh'
for tool in python3 sha256sum mktemp stat realpath cmp ln dd; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ -d "$OUT" ] && [ -d "$WORK" ] || die 'missing build or output directory'
[ "$(realpath -e "$WORK")" = "$(realpath -e "$HOME/sm7635-build")" ] || die 'wrong build lock directory'
if [ "$#" -eq 0 ]; then
	umask 077
	exec python3 -B -c '
import fcntl, os, stat, sys
lock, script = sys.argv[1:]
fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
info = os.fstat(fd)
named = os.lstat(lock)
if not (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and
        (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino)):
    raise SystemExit("unsafe build lock")
fcntl.flock(fd, fcntl.LOCK_EX)
named = os.lstat(lock)
if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
    raise SystemExit("changed build lock")
if fd != 9:
    os.dup2(fd, 9, inheritable=True)
    os.close(fd)
else:
    os.set_inheritable(9, True)
os.execvp("bash", ("bash", script, "--locked"))
' "$LOCK" "$0"
fi
python3 -B -c '
import fcntl, os, stat, sys
info = os.fstat(9)
named = os.lstat(sys.argv[1])
if not (stat.S_ISREG(info.st_mode) and stat.S_ISREG(named.st_mode) and
        info.st_uid == os.getuid() and info.st_nlink == 1 and
        (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino)):
    raise SystemExit("unsafe inherited build lock")
fcntl.flock(9, fcntl.LOCK_EX)
named = os.lstat(sys.argv[1])
if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
    raise SystemExit("changed build lock")
' "$LOCK"
for path in "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"; do
	[ -f "$path" ] && [ ! -L "$path" ] || die "missing or symlinked input: $path"
done
private=$(realpath -m "$HOME/phone-second-life-data/mb003")
for path in "$OUT" "$OUTPUT" "$CARRIER" "$MANIFEST"; do
	resolved=$(realpath -m "$path")
	case "$resolved/" in
		"$ROOT"/*) die 'output must be outside Git';;
		"$private"/*) die 'output must not be in device reference data';;
	esac
done
[ "$(realpath -m "$OUTPUT")" != "$(realpath -m "$CARRIER")" ] || die 'outputs must differ'
[ "$(realpath -m "$MANIFEST")" != "$(realpath -m "$OUTPUT")" ] &&
	[ "$(realpath -m "$MANIFEST")" != "$(realpath -m "$CARRIER")" ] || die 'manifest must differ from outputs'
for output in "$OUTPUT" "$CARRIER" "$MANIFEST"; do
	for input in "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"; do
		[ "$(realpath -m "$output")" != "$(realpath -m "$input")" ] || die 'output must not overwrite an input'
	done
	[ -d "$(dirname -- "$output")" ] && [ ! -L "$output" ] || die 'unsafe output path'
	[ ! -e "$output" ] || die "output already exists: $output"
done
[ "$(stat -c %s "$STOCK_INIT")" -eq 8388608 ] || die 'stock image size mismatch'
[ "$(stat -c %s "$BASE")" -eq 8388608 ] || die 'base image size mismatch'
[ "$(sha256sum "$STOCK_INIT" | cut -d ' ' -f 1)" = baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193 ] || die 'unpinned stock image'
[ "$(stat -c %s "$STOCK_VENDOR_B")" -eq 100663296 ] || die 'stock carrier size mismatch'
[ "$(sha256sum "$BASE" | cut -d ' ' -f 1)" = 5b5a60d4ceaf1551217874136c0de9a26f6b3ec29f9f586e2b7cdf0d728466d6 ] || die 'base is not the installed run-66 init_boot'
[ "$(sha256sum "$STOCK_VENDOR_B" | cut -d ' ' -f 1)" = 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253 ] || die 'stock carrier is not vendor_boot_b'
[ ! -e "$OUTPUT" ] && [ ! -L "$OUTPUT" ] && [ ! -e "$CARRIER" ] && [ ! -L "$CARRIER" ] &&
	[ ! -e "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || die 'output appeared after locking'
private_dir=$(mktemp -d "$OUT/mb003-no-guard.XXXXXXXX")
first=$private_dir/first-init.img
second=$private_dir/second-init.img
first_carrier=$private_dir/first-carrier.img
second_carrier=$private_dir/second-carrier.img
published_output=
published_carrier=
published_manifest=
complete=0
remove_own() {
	[ -n "$2" ] && [ -f "$1" ] && [ ! -L "$1" ] &&
		[ "$(stat -c %d:%i -- "$1")" = "$2" ] && rm -f -- "$1"
	return 0
}
cleanup() {
	status=$?
	trap - EXIT HUP INT TERM
	if [ "$complete" -ne 1 ]; then
		remove_own "$MANIFEST" "$published_manifest"
		remove_own "$OUTPUT" "$published_output"
		remove_own "$CARRIER" "$published_carrier"
	fi
	for path in "$first" "$second" "$first_carrier" "$second_carrier"; do
		[ -f "$path" ] && [ ! -L "$path" ] || continue
		[ "$(stat -c %h -- "$path" 2>/dev/null || echo 2)" = 1 ] || continue
		size=$(stat -c %s -- "$path" 2>/dev/null || true)
		case "$size" in ''|*[!0-9]*) continue;; esac
		dd if=/dev/zero of="$path" bs=1048576 count=$(((size + 1048575) / 1048576)) conv=notrunc status=none 2>/dev/null || true
	done
	rm -rf -- "$private_dir"
	exit "$status"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
for pair in "$first:$first_carrier" "$second:$second_carrier"; do
	candidate=${pair%%:*}
	carrier=${pair##*:}
	python3 -B "$ROOT/scripts/build-init-boot-mb003-no-guard.py" --build \
		"$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B" "$candidate" "$carrier"
	python3 -B "$ROOT/scripts/build-init-boot-mb003-no-guard.py" --verify \
		"$candidate" "$carrier" "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B"
done
cmp -s "$first" "$second" || die 'two serial builds differ'
cmp -s "$first_carrier" "$second_carrier" || die 'two serial builds differ'
[ "$(stat -c %s "$first")" -eq 8388608 ] || die 'candidate size mismatch'
[ "$(stat -c %s "$first_carrier")" -eq 100663296 ] || die 'carrier size mismatch'
[ "$(stat -c %a "$first")" = 600 ] && [ "$(stat -c %a "$first_carrier")" = 600 ] || die 'candidate mode mismatch'
published_output=$(stat -c %d:%i -- "$first")
published_carrier=$(stat -c %d:%i -- "$first_carrier")
ln -- "$first" "$OUTPUT"
rm -f -- "$first"
ln -- "$first_carrier" "$CARRIER"
rm -f -- "$first_carrier"
[ "$(stat -c %h -- "$OUTPUT")" -eq 1 ] && [ "$(stat -c %h -- "$CARRIER")" -eq 1 ] || die 'candidate publication left extra links'
python3 -B "$ROOT/scripts/verify-mb003-no-guard-pair-manifest.py" write \
	"$OUTPUT" "$CARRIER" "$MANIFEST" "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B" "$LOCK" --lock-fd 9
published_manifest=$(stat -c %d:%i -- "$MANIFEST")
python3 -B "$ROOT/scripts/verify-mb003-no-guard-pair-manifest.py" verify \
	"$OUTPUT" "$CARRIER" "$MANIFEST" "$STOCK_INIT" "$BASE" "$STOCK_VENDOR_B" "$LOCK" --lock-fd 9
complete=1
sha256sum "$OUTPUT" "$CARRIER" "$MANIFEST"
