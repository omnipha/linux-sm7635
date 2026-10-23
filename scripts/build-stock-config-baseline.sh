#!/usr/bin/env bash
set -euo pipefail

VENDOR_COMMIT=d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7
VENDOR_CACHE=${VENDOR_CACHE:-$HOME/github_repos/omnipha/linux-sm7635.git}
WORK=${WORK:-$HOME/sm7635-build}
JOBS=${JOBS:-$(nproc)}
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
DEVICE_CONFIG=${DEVICE_CONFIG:-$HOME/phone-second-life-data/mb003/config.gz}
STOCK_CONFIG_SHA256=90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478
PAYLOAD_BOUND=13967360
CLEAN=${CLEAN:-0}

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }

for t in git make clang-17 ld.lld-17 llvm-nm-17 llvm-ar-17 llvm-objcopy-17 \
	llvm-objdump-17 llvm-strip-17 llvm-readelf-17 dtc flex bison python3 bc \
	rsync cpio openssl pahole gcc g++ sha256sum; do
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
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "build artifacts must stay outside this repository" ;;
esac
mkdir -p "$SRC" "$OUT"

[ -f "$DEVICE_CONFIG" ] || die "missing stock config reference: $DEVICE_CONFIG"
read -r stock_config_sha _ < <(sha256sum "$DEVICE_CONFIG")
[ "$stock_config_sha" = "$STOCK_CONFIG_SHA256" ] ||
	die "stock config is not the verified device capture"
[ -f "$OUT/.config" ] || die "missing $OUT/.config; run scripts/build-baseline.sh first"

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
export KBUILD_BUILD_USER=omnipha
export KBUILD_BUILD_HOST=linux-sm7635
export KBUILD_BUILD_TIMESTAMP='Thu Jan  1 00:00:00 UTC 1970'
export KBUILD_BUILD_VERSION=1
export LC_ALL=C

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
common = pathlib.Path(sys.argv[1]).parents[3] / "drivers/remoteproc/qcom_common.h"
text = common.read_text()
stub_before = "\nint qcom_sysmon_get_reason(struct qcom_sysmon *sysmon, char *buf, size_t len)\n{\n\treturn -ENODEV;\n}\n"
stub_after = "\nstatic inline int qcom_sysmon_get_reason(struct qcom_sysmon *sysmon, char *buf,\n\t\t\t\t\t size_t len)\n{\n\treturn -ENODEV;\n}\n"
if stub_after not in text:
    if text.count(stub_before) != 1:
        raise SystemExit("qcom_common.h sysmon stub pattern not found or ambiguous")
    common.write_text(text.replace(stub_before, stub_after))
for directory, name in (("drivers/clk/qcom", "trace.h"),
                        ("drivers/clk/qcom", "trace-gdsc.h"),
                        ("drivers/interconnect/qcom", "trace.h"),
                        ("drivers/soc/qcom", "trace-crm.h"),
                        ("drivers/soc/qcom", "trace-rpmh.h"),
                        ("drivers/soc/qcom", "trace_secure_buffer.h"),
                        ("drivers/soc/qcom/mem_buf", "trace-mem-buf.h"),
                        ("drivers/virt/gunyah", "gh_proxy_sched_trace.h")):
    path = pathlib.Path(sys.argv[1]).parents[3] / directory / name
    lines = path.read_text().splitlines()
    target = f"#define TRACE_INCLUDE_PATH ../../{directory}"
    matches = [index for index, line in enumerate(lines)
               if line.startswith("#define TRACE_INCLUDE_PATH ")]
    if len(matches) != 1:
        raise SystemExit(f"{directory}/{name} trace include pattern not found or ambiguous")
    if lines[matches[0]] != target:
        lines[matches[0]] = target
        path.write_text("\n".join(lines) + "\n")
PY
}

cd "$SRC"
{
	echo "commit: $(git rev-parse HEAD)"
	echo "compiler: $(clang-17 --version | head -1)"
	echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
	echo "baseline: stock-config (issue #55)"
} | tee "$OUT/build-stock-config.log"

zcat "$DEVICE_CONFIG" >"$OUT/stock.config"

KCONFIG_CONFIG="$OUT/merged-stock-config.config" scripts/kconfig/merge_config.sh -m -r -y \
	"$OUT/stock.config" \
	"$ROOT/configs/asteroids-stock-config-debug-off.fragment" \
	"$ROOT/configs/asteroids-stock-config-gunyah-closure.fragment" \
	"$ROOT/configs/asteroids-stock-config-ksyms.fragment" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment" \
	"$ROOT/configs/asteroids-debug-marker.fragment" \
	2>&1 | tee -a "$OUT/build-stock-config.log"
cp -f "$OUT/merged-stock-config.config" .config
make olddefconfig 2>&1 | tee -a "$OUT/build-stock-config.log"
cp -f .config "$OUT/.config-stock-config"
python3 "$ROOT/scripts/verify-volcano-usb.py" config \
	"$OUT/.config-stock-config" "$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
host_tools_fixup

if [ "$CLEAN" = 1 ]; then
	make clean 2>&1 | tee -a "$OUT/build-stock-config.log"
	cp -f "$OUT/merged-stock-config.config" .config
	make olddefconfig 2>&1 | tee -a "$OUT/build-stock-config.log"
	cmp -s .config "$OUT/.config-stock-config" || die "olddefconfig is not stable after clean"
fi

make -j"$JOBS" Image 2>&1 | tee -a "$OUT/build-stock-config.log"
cmp -s .config "$OUT/.config-stock-config" || die "build changed .config"

cp -f arch/arm64/boot/Image "$OUT/Image-stock-config"

python3 - "$OUT/Image-stock-config" "$OUT/Image-stock-config.gz" <<'PY'
import pathlib
import struct
import sys
import zlib

image = pathlib.Path(sys.argv[1]).read_bytes()
compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, 8, zlib.Z_DEFAULT_STRATEGY)
body = compressor.compress(image) + compressor.flush()
packed = (b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03" + body +
          struct.pack("<II", zlib.crc32(image) & 0xFFFFFFFF, len(image) & 0xFFFFFFFF))
pathlib.Path(sys.argv[2]).write_bytes(packed)
print(f"decompressed {len(image)} bytes, gzip {len(packed)} bytes")
PY

payload_size=$(stat -c '%s' "$OUT/Image-stock-config.gz")
{
	echo "payload bytes: $payload_size"
	echo "bound bytes: $PAYLOAD_BOUND"
} | tee -a "$OUT/build-stock-config.log"
if [ "$payload_size" -gt "$PAYLOAD_BOUND" ]; then
	rm -f "$OUT/boot-signed-tail.img"
	die "payload $payload_size bytes misses the signed-tail bound $PAYLOAD_BOUND by $((payload_size - PAYLOAD_BOUND)) bytes"
fi

( cd "$OUT" && sha256sum Image-stock-config Image-stock-config.gz .config-stock-config ) \
	| tee "$OUT/sha256-stock-config.txt" | tee -a "$OUT/build-stock-config.log"
echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUT/build-stock-config.log"
