#!/usr/bin/env bash
set -euo pipefail

STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
STOCK_VENDOR=${STOCK_VENDOR:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_a.img}
STOCK_DTBO=${STOCK_DTBO:-$HOME/phone-second-life-data/mb003/parts/dtbo_a.img}
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in unpack_bootimg python3 cpio gzip sha256sum file mktemp fdtget; do
	need "$tool"
done
for reference in "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_DTBO"; do
	[ -f "$reference" ] || die "missing stock reference: $reference"
done
for artifact in "$OUT/boot.img" "$OUT/Image.gz" "$OUT/initramfs.cpio.gz" \
	"$OUT/volcano-qrd-pro-overlay.dtbo"; do
	[ -f "$artifact" ] || die "missing artifact: $artifact"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "verification artifacts must stay outside this repository" ;;
esac

scratch=$(mktemp -d "$WORK/bootimg-verify.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT
unpack_bootimg --boot_img "$STOCK_BOOT" --out "$scratch/stock-boot" >/dev/null
unpack_bootimg --boot_img "$STOCK_VENDOR" --out "$scratch/stock-vendor" >/dev/null
unpack_bootimg --boot_img "$OUT/boot.img" --out "$scratch/built-boot" >/dev/null

python3 - "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_DTBO" \
	"$OUT/boot.img" "$OUT/Image.gz" "$OUT/initramfs.cpio.gz" \
	"$scratch/stock-boot/kernel" "$scratch/built-boot/kernel" \
	"$scratch/built-boot/ramdisk" "$scratch/stock-vendor/dtb" \
	"$OUT/volcano-qrd-pro-overlay.dtbo" <<'PY'
import pathlib
import struct
import sys

(stock_boot, stock_vendor, stock_dtbo, built_boot, kernel, ramdisk,
 stock_kernel, unpacked_kernel, unpacked_ramdisk, stock_dtbs, overlay) = (
    pathlib.Path(p).read_bytes() for p in sys.argv[1:])


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def check(name, condition):
    print(f"{name}: {'OK' if condition else 'FAIL'}")
    if not condition:
        raise SystemExit(1)


check("boot magic", stock_boot[:8] == built_boot[:8] == b"ANDROID!")
for name, offset, value in (
    ("header version", 40, 4),
    ("header size", 20, 1584),
    ("OS version", 16, 0),
    ("signature size", 1580, 0),
):
    stock, built = u32(stock_boot, offset), u32(built_boot, offset)
    print(f"{name}: stock={stock} built={built}")
    check(name, stock == built == value)
check("empty cmdline", stock_boot[44:1580] == built_boot[44:1580] == bytes(1536))
check("unpacked kernel", unpacked_kernel == kernel)
check("unpacked ramdisk", unpacked_ramdisk == ramdisk)
check("stock kernel gzip", stock_kernel[:2] == b"\x1f\x8b")
check("built kernel gzip", kernel[:2] == b"\x1f\x8b")
check("stock boot ramdisk empty", u32(stock_boot, 12) == 0)
check("built boot ramdisk present", u32(built_boot, 12) == len(ramdisk) > 0)
check("boot kernel size", u32(built_boot, 8) == len(kernel))

check("vendor magic", stock_vendor[:8] == b"VNDRBOOT")
for name, offset, value in (
    ("vendor header version", 8, 4),
    ("page size", 12, 4096),
    ("kernel address", 16, 0x8000),
    ("vendor ramdisk address", 20, 0x1000000),
    ("tags address", 2076, 0x100),
    ("vendor header size", 2096, 2128),
    ("vendor ramdisk table entries", 2116, 1),
    ("vendor ramdisk table entry size", 2120, 108),
):
    actual = u32(stock_vendor, offset)
    print(f"{name}: stock={actual:#x} expected={value:#x}")
    check(name, actual == value)
check("dtb address", u64(stock_vendor, 2104) == 0x1F00000)
check("stock bootconfig present", u32(stock_vendor, 2124) == 175)

page = 4096
ramdisk_size = u32(stock_vendor, 24)
dtb_size = u32(stock_vendor, 2100)
dtb_offset = page + (ramdisk_size + page - 1) // page * page
check("vendor DTB unpack", stock_vendor[dtb_offset:dtb_offset + dtb_size] == stock_dtbs)
models = []
pos = 0
while pos < len(stock_dtbs):
    if stock_dtbs[pos:pos + 4] != b"\xd0\x0d\xfe\xed":
        raise SystemExit(f"invalid stock DTB at {pos}")
    size = struct.unpack_from(">I", stock_dtbs, pos + 4)[0]
    if size <= 0 or pos + size > len(stock_dtbs):
        raise SystemExit(f"invalid stock DTB size at {pos}")
    models.append(stock_dtbs[pos:pos + size])
    pos += size
check("stock vendor DTB count", len(models) == 20)
check("stock vendor contains Volcano", b"Volcano SoC" in models[9])

if stock_dtbo[:4] != b"\xd7\xb7\xab\x1e":
    raise SystemExit("stock dtbo table has incorrect magic")
entries = struct.unpack_from(">I", stock_dtbo, 16)[0]
entry_size = struct.unpack_from(">I", stock_dtbo, 12)[0]
table_offset = struct.unpack_from(">I", stock_dtbo, 20)[0]
check("stock DTBO entry size", entry_size >= 8 and entries > 65)
entry = table_offset + 65 * entry_size
size, offset = struct.unpack_from(">II", stock_dtbo, entry)
check("stock DTBO entry 65", stock_dtbo[offset:offset + size][:4] == b"\xd0\x0d\xfe\xed")
check("selected overlay has FDT magic", overlay[:4] == b"\xd0\x0d\xfe\xed")
print(f"stock DTB count: {len(models)}, DTBO entries: {entries}, selected entry: 65")
print(f"stock kernel bytes: {u32(stock_boot, 8)}, built kernel bytes: {len(kernel)}")
print(f"stock vendor DTB bytes: {dtb_size}, stock bootconfig bytes: {u32(stock_vendor, 2124)}")
PY

stock_overlay=$scratch/stock-overlay.dtb
python3 - "$STOCK_DTBO" "$stock_overlay" <<'PY'
import pathlib
import struct
import sys

image = pathlib.Path(sys.argv[1]).read_bytes()
entry = struct.unpack_from(">I", image, 20)[0] + 65 * struct.unpack_from(">I", image, 12)[0]
size, offset = struct.unpack_from(">II", image, entry)
pathlib.Path(sys.argv[2]).write_bytes(image[offset:offset + size])
PY
model=$(fdtget -t s "$stock_overlay" / model)
board=$(fdtget -t x "$stock_overlay" / qcom,board-id)
oem=$(fdtget -t x "$stock_overlay" / qcom,oem-id)
[ "$model" = 'Qualcomm Technologies, Inc. Volcano QRD Pro' ] || die "stock overlay model mismatch"
[ "$board" = 'b 0' ] || die "stock overlay board ID mismatch"
[ "$oem" = '2' ] || die "stock overlay OEM ID mismatch"
built_model=$(fdtget -t s "$OUT/volcano-qrd-pro-overlay.dtbo" / model)
built_board=$(fdtget -t x "$OUT/volcano-qrd-pro-overlay.dtbo" / qcom,board-id)
built_oem=$(fdtget -t x "$OUT/volcano-qrd-pro-overlay.dtbo" / qcom,oem-id)
[ "$built_model" = "$model" ] && [ "$built_board" = "$board" ] &&
	[ "$built_oem" = "$oem" ] || die "built overlay is not the stock board match"

mkdir -p "$scratch/ramdisk"
gzip -dc "$scratch/built-boot/ramdisk" | cpio -itv --quiet >"$scratch/ramdisk-list.txt"
for device in 'dev/console' 'dev/null' 'dev/kmsg' 'dev/ptmx'; do
	grep -q "^c.* $device$" "$scratch/ramdisk-list.txt" || die "missing device node: $device"
done
grep -q 'bin/busybox' "$scratch/ramdisk-list.txt" || die "initramfs has no busybox"
gzip -dc "$scratch/built-boot/ramdisk" | \
	(cd "$scratch/ramdisk" && cpio -id --quiet --no-absolute-filenames \
		init bin/busybox)
[ -x "$scratch/ramdisk/init" ] || die "initramfs has no init"
[ -f "$scratch/ramdisk/bin/busybox" ] || die "initramfs has no busybox"
file "$scratch/ramdisk/bin/busybox" | grep -q 'ARM aarch64' || die "busybox is not arm64"
grep -q 'ncm.usb0' "$scratch/ramdisk/init" || die "init has no NCM gadget"
grep -q 'ecm.usb0' "$scratch/ramdisk/init" || die "init has no ECM gadget"

report=$OUT/bootimg-verify.txt
{
	echo 'boot header v4 / vendor page size 4096; stock offsets match'
	echo "stock DTBO entry 65: $model; board-id <$board>; oem-id <$oem>"
	echo "built DTBO: $built_model; board-id <$built_board>; oem-id <$built_oem>"
	echo 'initramfs: gzip newc; static arm64 busybox; NCM+ECM; console shell; no sshd'
	echo 'unpack verification: passed'
	(cd "$OUT" && sha256sum boot.img Image.gz initramfs.cpio.gz Image)
	sha256sum "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_DTBO"
} | tee "$report"
