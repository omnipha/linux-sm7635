#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
ATTR_OUT=${ATTR_OUT:-${TMPDIR:-/tmp}/sm7635-diagnostic-shortfall}
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SRC=$WORK/src
BUILD_OUT=$WORK/out

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }

for t in ld.lld-17 llvm-objcopy-17 python3 sha256sum; do
	need "$t"
done

case "$(realpath -m "$ATTR_OUT")/" in
	"$ROOT"/* | "$SRC"/* | "$BUILD_OUT"/*)
		die "report scratch must stay outside the repository and the build tree" ;;
esac

IMAGE=$BUILD_OUT/Image-diagnostic-kallsyms-nls
GZIP=$BUILD_OUT/Image-diagnostic-kallsyms-nls.gz
CONFIG=$BUILD_OUT/.config-diagnostic-kallsyms-nls
for f in "$IMAGE" "$GZIP" "$CONFIG" "$SRC/vmlinux.a" "$SRC/.vmlinux.export.o" \
	"$SRC/init/version-timestamp.o" "$SRC/.tmp_vmlinux.kallsyms2.o" \
	"$SRC/.btf.vmlinux.bin.o" "$SRC/drivers/firmware/efi/libstub/lib.a" \
	"$SRC/arch/arm64/kernel/vmlinux.lds" \
	"$SRC/tools/bpf/resolve_btfids/resolve_btfids" "$SRC/scripts/sorttable"; do
	[ -f "$f" ] || die "missing diagnostic build input: $f"
done
cmp -s "$SRC/.config" "$CONFIG" || die "source tree .config is not the diagnostic build config"
cmp -s "$SRC/arch/arm64/boot/Image" "$IMAGE" || die "source tree Image is not the diagnostic Image"

mkdir -p "$ATTR_OUT"
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

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/scripts/report-diagnostic-shortfall.py" \
	--image "$IMAGE" --gz "$GZIP" --config "$CONFIG" \
	--replay-elf "$ATTR_OUT/vmlinux.replay" --replay-image "$ATTR_OUT/Image.replay" \
	--map "$ATTR_OUT/vmlinux.map"
