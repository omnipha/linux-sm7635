#!/usr/bin/env bash
set -euo pipefail

VENDOR_COMMIT=d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7
VENDOR_CACHE=${VENDOR_CACHE:-$HOME/github_repos/omnipha/linux-sm7635.git}
WORK=${WORK:-$HOME/sm7635-build}
JOBS=${JOBS:-$(nproc)}

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }

for t in git make clang-17 ld.lld-17 llvm-nm-17 llvm-ar-17 llvm-objcopy-17 \
	llvm-objdump-17 llvm-strip-17 llvm-readelf-17 dtc flex bison python3 bc \
	rsync cpio openssl pahole gcc g++; do
	need "$t"
done

case "$(clang-17 --version | head -1)" in
	'Ubuntu clang version 17.0.6 (23ubuntu7)') ;;
	*) die "requires Ubuntu clang 17.0.6-23ubuntu7" ;;
esac
case "$(ld.lld-17 --version)" in
	'Ubuntu LLD 17.0.6 (compatible with GNU linkers)') ;;
	*) die "requires Ubuntu LLD 17.0.6" ;;
esac

[ -d "$VENDOR_CACHE" ] || die "vendor cache not found: $VENDOR_CACHE"
git --git-dir="$VENDOR_CACHE" cat-file -e "$VENDOR_COMMIT^{commit}" \
	|| die "commit $VENDOR_COMMIT not in $VENDOR_CACHE"

SRC=$WORK/src
OUT=$WORK/out
mkdir -p "$SRC" "$OUT"

if [ ! -d "$SRC/.git" ]; then
	git clone --shared --no-checkout --single-branch --branch sm7635/v/mr \
		"$VENDOR_CACHE" "$SRC"
fi
git -C "$SRC" checkout --detach "$VENDOR_COMMIT"
[ "$(git -C "$SRC" rev-parse HEAD)" = "$VENDOR_COMMIT" ] \
	|| die "checkout is not $VENDOR_COMMIT"

export ARCH=arm64
export LLVM_IAS=1
export LLVM=-17
export HOSTCC=gcc
export HOSTCXX=g++

host_tools_fixup() {
	python3 - "$SRC/tools/lib/bpf/libbpf.c" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
source = path.read_text()
before = "next_path = strchr(s, ':');"
after = "next_path = (char *)strchr(s, ':');"
if after not in source:
    if source.count(before) != 1:
        raise SystemExit('libbpf.c pattern not found or ambiguous')
    path.write_text(source.replace(before, after))
PY
}

cd "$SRC"
{
	echo "commit: $(git rev-parse HEAD)"
	echo "compiler: $(clang-17 --version | head -1)"
	echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} | tee "$OUT/build.log"

KCONFIG_CONFIG="$OUT/merged.config" scripts/kconfig/merge_config.sh -m -r -y \
	arch/arm64/configs/gki_defconfig \
	arch/arm64/configs/vendor/pineapple_GKI.config \
	arch/arm64/configs/consolidate.fragment \
	arch/arm64/configs/vendor/pineapple_consolidate.config \
	2>&1 | tee -a "$OUT/build.log"
cp -f "$OUT/merged.config" .config
make olddefconfig 2>&1 | tee -a "$OUT/build.log"
cp -f .config "$OUT/.config"
host_tools_fixup

make -j"$JOBS" Image dtbs 2>&1 | tee -a "$OUT/build.log"

cp -f arch/arm64/boot/Image "$OUT/Image"
DT=arch/arm64/boot/dts/vendor/qcom
for f in volcano.dtb volcano6.dtb volcano6i-fp1.dtb volcano6i-fp2.dtb \
	volcano6i-fp3.dtb volcano6i-fp4.dtb volcano-qrd-overlay.dtbo \
	volcano-qrd-pro-overlay.dtbo volcano-volcano-qrd-pro-overlay.dtb \
	volcano6-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp1-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp2-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp3-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp4-volcano-qrd-pro-overlay.dtb; do
	cp -f "$DT/$f" "$OUT/$f"
done

( cd "$OUT" && sha256sum Image .config *.dtb *.dtbo ) > "$OUT/sha256.txt"
echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUT/build.log"
tee -a "$OUT/build.log" < "$OUT/sha256.txt"
