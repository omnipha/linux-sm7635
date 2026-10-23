#!/usr/bin/env bash
set -euo pipefail

VENDOR_COMMIT=d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7
VENDOR_CACHE=${VENDOR_CACHE:-$HOME/github_repos/omnipha/linux-sm7635.git}
WORK=${WORK:-$HOME/sm7635-build}
JOBS=${JOBS:-$(nproc)}
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
DEVICE_CONFIG=${DEVICE_CONFIG:-$HOME/phone-second-life-data/mb003/config.gz}
STOCK_CONFIG_SHA256=90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478
STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
STOCK_BOOT_SHA256=197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d
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
[ -f "$OUT/.config-diagnostic-kallsyms-nls" ] ||
	die "missing $OUT/.config-diagnostic-kallsyms-nls; run scripts/build-diagnostic-kallsyms-nls.sh first"
[ -f "$STOCK_BOOT" ] || die "missing stock boot reference: $STOCK_BOOT"
read -r stock_boot_sha _ < <(sha256sum "$STOCK_BOOT")
[ "$stock_boot_sha" = "$STOCK_BOOT_SHA256" ] ||
	die "stock boot_a is not the verified slot-A reference"

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
	echo "baseline: stock-config (issue #55) + KALLSYMS_ALL=n + NLS=n (issue #60) + EXT4_FS=n (issue #59)"
} | tee "$OUT/build-diagnostic-ext4.log"

zcat "$DEVICE_CONFIG" >"$OUT/stock.config"

KCONFIG_CONFIG="$OUT/merged-diagnostic-ext4.config" scripts/kconfig/merge_config.sh -m -r -y \
	"$OUT/stock.config" \
	"$ROOT/configs/asteroids-stock-config-debug-off.fragment" \
	"$ROOT/configs/asteroids-stock-config-gunyah-closure.fragment" \
	"$ROOT/configs/asteroids-stock-config-ksyms.fragment" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment" \
	"$ROOT/configs/asteroids-debug-marker.fragment" \
	"$ROOT/configs/asteroids-diagnostic-kallsyms-nls-off.fragment" \
	"$ROOT/configs/asteroids-diagnostic-ext4-off.fragment" \
	2>&1 | tee -a "$OUT/build-diagnostic-ext4.log"
cp -f "$OUT/merged-diagnostic-ext4.config" .config
make olddefconfig 2>&1 | tee -a "$OUT/build-diagnostic-ext4.log"
cp -f .config "$OUT/.config-diagnostic-ext4"
python3 "$ROOT/scripts/verify-volcano-usb.py" config \
	"$OUT/.config-diagnostic-ext4" "$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
python3 - "$OUT/.config-diagnostic-ext4" "$OUT/.config-diagnostic-kallsyms-nls" <<'PY'
import sys

path, baseline = sys.argv[1], sys.argv[2]
EXPECTED = {
    "CONFIG_EXT4_FS": "y",
    "CONFIG_EXT4_USE_FOR_EXT2": "y",
    "CONFIG_EXT4_FS_POSIX_ACL": "y",
    "CONFIG_EXT4_FS_SECURITY": "y",
    "CONFIG_JBD2": "y",
    "CONFIG_FS_MBCACHE": "y",
}
KEPT_ON = ("CONFIG_KALLSYMS", "CONFIG_F2FS_FS", "CONFIG_ANDROID_BINDER_IPC",
           "CONFIG_USB_GADGET", "CONFIG_SCSI_UFSHCD", "CONFIG_NLS")


def pairs(text):
    result = {}
    for line in text.splitlines():
        if line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line.split()[1]] = "n"
        elif line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


with open(path) as handle:
    new = pairs(handle.read())
with open(baseline) as handle:
    old = pairs(handle.read())
if new.get("CONFIG_KALLSYMS_ALL", "n") != "n":
    raise SystemExit("CONFIG_KALLSYMS_ALL is not off")
for symbol in KEPT_ON:
    if new.get(symbol) != "y" or old.get(symbol) != "y":
        raise SystemExit(f"{symbol} is not on")
changed = {key: (old.get(key, "n"), new.get(key, "n"))
           for key in set(new) | set(old) if old.get(key, "n") != new.get(key, "n")}
if set(changed) != set(EXPECTED) or any(
        changed[key] != (EXPECTED[key], "n") for key in EXPECTED):
    raise SystemExit("config delta against #60 is not EXT4_FS and its solely-selected "
                     f"symbols: {sorted(changed.items())}")
print("diagnostic config: KALLSYMS_ALL and EXT4_FS off; kallsyms, f2fs, binder, USB closure, NLS unchanged")
for key in sorted(changed):
    print(f"  delta against #60: {key}: {changed[key][0]} -> {changed[key][1]}")
PY
host_tools_fixup

if [ "$CLEAN" = 1 ]; then
	make clean 2>&1 | tee -a "$OUT/build-diagnostic-ext4.log"
	cp -f "$OUT/merged-diagnostic-ext4.config" .config
	make olddefconfig 2>&1 | tee -a "$OUT/build-diagnostic-ext4.log"
	cmp -s .config "$OUT/.config-diagnostic-ext4" || die "olddefconfig is not stable after clean"
fi

make -j"$JOBS" Image 2>&1 | tee -a "$OUT/build-diagnostic-ext4.log"
cmp -s .config "$OUT/.config-diagnostic-ext4" || die "build changed .config"

cp -f arch/arm64/boot/Image "$OUT/Image-diagnostic-ext4"

python3 - "$OUT/Image-diagnostic-ext4" "$OUT/Image-diagnostic-ext4.gz" <<'PY'
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

payload_size=$(stat -c '%s' "$OUT/Image-diagnostic-ext4.gz")
{
	echo "payload bytes: $payload_size"
	echo "bound bytes: $PAYLOAD_BOUND"
} | tee -a "$OUT/build-diagnostic-ext4.log"
if [ "$payload_size" -gt "$PAYLOAD_BOUND" ]; then
	rm -f "$OUT/boot-diagnostic-ext4.img" "$OUT/boot-diagnostic-ext4-sha256.txt"
	die "payload $payload_size bytes misses the signed-tail bound $PAYLOAD_BOUND by $((payload_size - PAYLOAD_BOUND)) bytes; no boot image is assembled"
fi

python3 "$ROOT/scripts/build-diagnostic-signed-tail-payload.py" --build \
	"$STOCK_BOOT" "$OUT/Image-diagnostic-ext4.gz" "$OUT/.config-diagnostic-ext4" \
	"$OUT/boot-diagnostic-ext4.img"
python3 "$ROOT/scripts/verify-diagnostic-signed-tail.py" --self-test \
	"$OUT/boot-diagnostic-ext4.img" "$STOCK_BOOT" "$OUT/Image-diagnostic-ext4.gz" \
	"$OUT/Image-diagnostic-ext4" "$OUT/.config-diagnostic-ext4" \
	"$OUT/.config-diagnostic-kallsyms-nls" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
python3 "$ROOT/scripts/verify-diagnostic-signed-tail.py" \
	"$OUT/boot-diagnostic-ext4.img" "$STOCK_BOOT" "$OUT/Image-diagnostic-ext4.gz" \
	"$OUT/Image-diagnostic-ext4" "$OUT/.config-diagnostic-ext4" \
	"$OUT/.config-diagnostic-kallsyms-nls" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment"

( cd "$OUT" && sha256sum Image-diagnostic-ext4 Image-diagnostic-ext4.gz .config-diagnostic-ext4 ) \
	| tee "$OUT/sha256-diagnostic-ext4.txt" | tee -a "$OUT/build-diagnostic-ext4.log"
echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUT/build-diagnostic-ext4.log"
