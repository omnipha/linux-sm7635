#!/usr/bin/env bash
# Reproducible baseline build for the Nothing Phone (3a) Pro (asteroids,
# SM7635 / volcano) vendor kernel.
#
# Pins:
#   VENDOR_COMMIT  d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7
#                   NothingOSS/android_kernel_msm-6.1_nothing_sm7635
#                   branch sm7635/v/mr (Nothing OS 3.x, kernel 6.1.78)
#   TOOLCHAIN       clang 17 + lld 17 (see README for the deviation from the
#                   on-device Android clang 17.0.2 build 10087095)
#
# Usage:
#   VENDOR_CACHE=~/github_repos/omnipha/linux-sm7635.git \
#   WORK=~/sm7635-build \
#   scripts/build-baseline.sh
#
# Produces, under $WORK/out:
#   Image
#   volcano.dtb, volcano6.dtb, volcano6i-fp{1,2,3,4}.dtb
#   volcano-qrd-pro-overlay.dtbo, volcano-qrd-overlay.dtbo
#   .config   (the merged configuration that was built)
#   build.log
#
# This script never flashes or boots a device. It never writes into the
# repository. Build artifacts stay in $WORK.

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
# The kernel build appends this suffix to clang, ld.lld and the llvm-* tools.
export LLVM=-17
# Host tools are built with the system gcc. The kernel itself stays on clang.
export HOSTCC=gcc
export HOSTCXX=g++

# tools/lib/bpf/libbpf.c builds with -Werror and assigns strchr()'s const char *
# result to a plain char *. Current GCC and clang both reject that; the Android
# clang 17.0.2 this tree was released against did not. The cast is applied only
# inside the build worktree. It is never committed.
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

# Fragment chain from build.config.msm.gki for the pineapple target. Volcano
# has no build.config of its own: target_variants.bzl maps it onto pineapple,
# and pineapple_GKI.config sets CONFIG_ARCH_VOLCANO. Flags match
# build.config.msm.common (merge_config.sh -m -r -y); olddefconfig then fills
# in every symbol the fragments leave unset.
#
# The on-device config matches neither variant outright. VARIANT=gki would
# additionally trim non-listed KMI symbols, which needs the prebuilt GKI kernel
# and the abi_gki_aarch64_qcom symbol list from a full kernel-platform
# workspace that this standalone tree does not contain. The consolidate
# fragments are therefore merged, and the remaining differences from the
# device config are reported by compare-baseline.sh rather than hidden.
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
	volcano-qrd-pro-overlay.dtbo; do
	cp -f "$DT/$f" "$OUT/$f"
done
# The tree's Makefile also pre-applies each board overlay onto every base SoC
# DTB. Those composite files are produced by Kbuild's fdtoverlay rule, but
# their root model/compatible remain the base SoC's, not the board's; the
# board identity is the separate overlay.
for f in volcano-volcano-qrd-pro-overlay.dtb \
	volcano6-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp1-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp2-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp3-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp4-volcano-qrd-pro-overlay.dtb; do
	cp -f "$DT/$f" "$OUT/$f"
done
for f in volcano-volcano-qrd-pro-overlay.dtb \
	volcano6-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp1-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp2-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp3-volcano-qrd-pro-overlay.dtb \
	volcano6i-fp4-volcano-qrd-pro-overlay.dtb; do
	cp -f "$DT/$f" "$OUT/$f"
done

echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUT/build.log"
( cd "$OUT" && sha256sum Image .config *.dtb *.dtbo ) | tee -a "$OUT/build.log"
