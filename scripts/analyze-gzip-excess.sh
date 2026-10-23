#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
ATTR_OUT=${ATTR_OUT:-${TMPDIR:-/tmp}/sm7635-gzip-excess}
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SRC=$WORK/src
BUILD_OUT=$WORK/out

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }

for t in ld.lld-17 llvm-objcopy-17 llvm-nm-17 llvm-readelf-17 clang-17 python3 find cmp; do
	need "$t"
done

case "$(realpath -m "$ATTR_OUT")/" in
	"$ROOT"/* | "$SRC"/* | "$BUILD_OUT"/*)
		die "analysis scratch must stay outside the repository and the build tree" ;;
esac

IMAGE=$BUILD_OUT/Image-stock-config
GZIP=$BUILD_OUT/Image-stock-config.gz
CONFIG=$BUILD_OUT/.config-stock-config
for f in "$IMAGE" "$GZIP" "$CONFIG" "$SRC/vmlinux.a" "$SRC/.vmlinux.objs" \
	"$SRC/.vmlinux.export.o" "$SRC/init/version-timestamp.o" \
	"$SRC/.tmp_vmlinux.kallsyms2.o" "$SRC/.btf.vmlinux.bin.o" \
	"$SRC/drivers/firmware/efi/libstub/lib.a" \
	"$SRC/arch/arm64/kernel/vmlinux.lds" \
	"$SRC/tools/bpf/resolve_btfids/resolve_btfids" "$SRC/scripts/sorttable" \
	"$SRC/scripts/kconfig/conf" "$SRC/scripts/kallsyms" \
	"$SRC/.tmp_vmlinux.kallsyms2.syms"; do
	[ -f "$f" ] || die "missing #55 build input: $f"
done

DEVICE=${DEVICE:-$HOME/phone-second-life-data/mb003}
VENDOR_BOOT=${VENDOR_BOOT:-$DEVICE/parts/vendor_boot_a.img}
[ -f "$VENDOR_BOOT" ] || die "missing stock vendor_boot for the module closure: $VENDOR_BOOT"

mkdir -p "$ATTR_OUT"
: >"$ATTR_OUT/.start"

(
	cd "$SRC"
	ld.lld-17 -EL -maarch64elf -z norelro -z noexecstack --no-undefined -X -shared \
		-Bsymbolic -z notext --no-apply-dynamic-relocs --fix-cortex-a53-843419 \
		--build-id=sha1 --pack-dyn-relocs=relr --use-android-relr-tags \
		--orphan-handling=warn --script=arch/arm64/kernel/vmlinux.lds \
		-Map="$ATTR_OUT/vmlinux.map" -o "$ATTR_OUT/vmlinux.replay" \
		--whole-archive vmlinux.a --no-whole-archive \
		--start-group drivers/firmware/efi/libstub/lib.a --end-group \
		.vmlinux.export.o init/version-timestamp.o \
		.tmp_vmlinux.kallsyms2.o .btf.vmlinux.bin.o
	tools/bpf/resolve_btfids/resolve_btfids "$ATTR_OUT/vmlinux.replay"
	scripts/sorttable "$ATTR_OUT/vmlinux.replay"
	llvm-objcopy-17 -O binary -R .note -R .note.gnu.build-id -R .comment -S \
		"$ATTR_OUT/vmlinux.replay" "$ATTR_OUT/Image.replay"
)

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/analyze-gzip-excess.py" \
	--src "$SRC" --scratch "$ATTR_OUT" --image "$IMAGE" --gz "$GZIP" \
	--config "$CONFIG" --replay-elf "$ATTR_OUT/vmlinux.replay" \
	--replay-image "$ATTR_OUT/Image.replay" --map "$ATTR_OUT/vmlinux.map" \
	--repo "$ROOT" --vendor-boot "$VENDOR_BOOT" "$@"

touched=$(find "$SRC" "$BUILD_OUT" -path "$SRC/.git" -prune -o -newer "$ATTR_OUT/.start" -print | head -5)
if [ -n "$touched" ]; then
	echo "build tree modified during analysis:" >&2
	echo "$touched" >&2
	exit 1
fi
echo "build tree read-only check: no file under $SRC or $BUILD_OUT changed"
