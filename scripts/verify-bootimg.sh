#!/usr/bin/env bash
set -euo pipefail

STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
STOCK_VENDOR=${STOCK_VENDOR:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_a.img}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
STOCK_DTBO=${STOCK_DTBO:-$HOME/phone-second-life-data/mb003/parts/dtbo_a.img}
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in unpack_bootimg python3 cpio gzip sha256sum file mktemp fdtget dtc \
	qemu-aarch64; do
	need "$tool"
done
for reference in "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_INIT" "$STOCK_DTBO"; do
	[ -f "$reference" ] || die "missing stock reference: $reference"
done
for artifact in "$OUT/boot.img" "$OUT/init_boot.img" "$OUT/vendor_boot.img" \
	"$OUT/dtb.img" "$OUT/Image.gz" "$OUT/initramfs.cpio.gz" \
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
unpack_bootimg --boot_img "$STOCK_INIT" --out "$scratch/stock-init" >/dev/null
unpack_bootimg --boot_img "$OUT/boot.img" --out "$scratch/built-boot" >/dev/null
unpack_bootimg --boot_img "$OUT/vendor_boot.img" --out "$scratch/built-vendor" >/dev/null
unpack_bootimg --boot_img "$OUT/init_boot.img" --out "$scratch/built-init" >/dev/null

python3 - "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_INIT" "$STOCK_DTBO" \
	"$OUT/boot.img" "$OUT/vendor_boot.img" "$OUT/init_boot.img" \
	"$OUT/Image.gz" "$OUT/initramfs.cpio.gz" "$OUT/dtb.img" \
	"$scratch/stock-boot/kernel" "$scratch/built-boot/kernel" \
	"$scratch/built-boot/ramdisk" "$scratch/stock-vendor/dtb" \
	"$scratch/built-vendor/dtb" "$scratch/built-vendor/vendor_ramdisk00" \
	"$scratch/built-init/ramdisk" "$OUT/volcano-qrd-pro-overlay.dtbo" <<'PY'
import pathlib
import struct
import sys

(stock_boot, stock_vendor, stock_init, stock_dtbo, built_boot, built_vendor,
 built_init, kernel, ramdisk, dtb, stock_kernel, unpacked_kernel,
 unpacked_ramdisk, stock_dtbs, built_dtbs, built_vendor_ramdisk,
 built_init_ramdisk, overlay) = (
    pathlib.Path(p).read_bytes() for p in sys.argv[1:])


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def check(name, condition):
    print(f"{name}: {'OK' if condition else 'FAIL'}")
    if not condition:
        raise SystemExit(1)


def dtbs(blob, expected, count):
    found = []
    pos = 0
    while pos < len(blob):
        if blob[pos:pos + 4] != b"\xd0\x0d\xfe\xed":
            raise SystemExit(f"invalid DTB at {pos}")
        size = struct.unpack_from(">I", blob, pos + 4)[0]
        if size <= 0 or pos + size > len(blob):
            raise SystemExit(f"invalid DTB size at {pos}")
        found.append(blob[pos:pos + size])
        pos += size
    check(expected, len(found) == count)
    return found


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
check("unpacked kernel", unpacked_kernel == kernel)
check("unpacked ramdisk", unpacked_ramdisk == ramdisk)
check("stock kernel gzip", stock_kernel[:2] == b"\x1f\x8b")
check("built kernel gzip", kernel[:2] == b"\x1f\x8b")
check("stock boot ramdisk empty", u32(stock_boot, 12) == 0)
check("built boot ramdisk present", u32(built_boot, 12) == len(ramdisk) > 0)
check("boot kernel size", u32(built_boot, 8) == len(kernel))
built_cmdline = built_boot[44:1580].split(b"\x00", 1)[0]
check("boot cmdline diagnosis prefix",
      built_cmdline.startswith(b"console=ttynull ") and b"bootconfig" in built_cmdline)
check("stock init kernel empty", u32(stock_init, 8) == 0)
check("built init kernel empty", u32(built_init, 8) == 0)
check("built init ramdisk", built_init_ramdisk == ramdisk)

for image, label in ((stock_vendor, "stock"), (built_vendor, "built")):
    check(f"{label} vendor magic", image[:8] == b"VNDRBOOT")
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
        actual = u32(image, offset)
        print(f"{label} {name}: {actual:#x}")
        check(f"{label} {name}", actual == value)
    check(f"{label} dtb address", u64(image, 2104) == 0x1F00000)
check("stock bootconfig size", u32(stock_vendor, 2124) == 175)
check("built vendor ramdisk", built_vendor_ramdisk == ramdisk)
built_vendor_cmdline = built_vendor[28:2076].split(b"\x00", 1)[0]
for token in (b"earlycon", b"keep_bootcon", b"panic=-1", b"log_buf_len=1M"):
    check(f"vendor cmdline has {token.decode()}", token in built_vendor_cmdline)

page = 4096
stock_ramdisk_size = u32(stock_vendor, 24)
stock_dtb_size = u32(stock_vendor, 2100)
stock_dtb_offset = page + (stock_ramdisk_size + page - 1) // page * page
check("stock vendor DTB unpack",
      stock_vendor[stock_dtb_offset:stock_dtb_offset + stock_dtb_size] == stock_dtbs)
stock_models = dtbs(stock_dtbs, "stock vendor DTB count", 20)
check("stock vendor contains Volcano", b"Volcano SoC" in stock_models[9])
built_models = dtbs(built_dtbs, "built vendor DTB count", 20)
check("built vendor DTB payload", built_dtbs == dtb)
check("built vendor preserves stock prefix", built_models[:9] == stock_models[:9])
check("built vendor selects Volcano at index 9", b"Volcano SoC" in built_models[9])

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
print(f"stock DTB count: {len(stock_models)}, built DTB count: {len(built_models)}")
print(f"DTBO entries: {entries}, selected entry: 65")
print(f"stock kernel bytes: {u32(stock_boot, 8)}, built kernel bytes: {len(kernel)}")
print(f"stock vendor DTB bytes: {stock_dtb_size}, built vendor DTB bytes: {len(dtb)}")
print(f"stock bootconfig bytes: {u32(stock_vendor, 2124)}")
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

python3 - "$scratch/built-vendor/dtb" "$scratch/volcano.dtb" <<'PY'
import pathlib
import struct
import sys

blob = pathlib.Path(sys.argv[1]).read_bytes()
pos = 0
for index in range(9):
    pos += struct.unpack_from(">I", blob, pos + 4)[0]
size = struct.unpack_from(">I", blob, pos + 4)[0]
pathlib.Path(sys.argv[2]).write_bytes(blob[pos:pos + size])
PY
dtc -I dtb -O dts "$scratch/volcano.dtb" >/dev/null
ramoops=$(fdtget -t x "$scratch/volcano.dtb" /reserved-memory/ramoops_region reg)
console_size=$(fdtget -t x "$scratch/volcano.dtb" /reserved-memory/ramoops_region console-size)
pmsg_size=$(fdtget -t x "$scratch/volcano.dtb" /reserved-memory/ramoops_region pmsg-size)
[ "$ramoops" = '0 81f20000 0 400000' ] || die "ramoops reservation is not 0x81f20000/4MiB"
[ "$console_size" = '200000' ] || die "ramoops console size is not 2MiB"
[ "$pmsg_size" = '200000' ] || die "ramoops pmsg size is not 2MiB"

mkdir -p "$scratch/ramdisk"
gzip -dc "$scratch/built-boot/ramdisk" | cpio -itv --quiet >"$scratch/ramdisk-list.txt"
for device in 'dev/console' 'dev/null' 'dev/kmsg' 'dev/ptmx'; do
	grep -q "^c.* $device$" "$scratch/ramdisk-list.txt" || die "missing device node: $device"
done
grep -q 'bin/busybox' "$scratch/ramdisk-list.txt" || die "initramfs has no busybox"
gzip -dc "$scratch/built-boot/ramdisk" | \
	(cd "$scratch/ramdisk" && cpio -id --quiet --no-absolute-filenames \
		init bin/busybox bin/dropbear root/.ssh/authorized_keys \
		usr/share/doc/dropbear/LICENSE \
		usr/share/doc/dropbear/LibTomCrypt-LICENSE \
		usr/share/doc/dropbear/LibTomMath-LICENSE)
[ -x "$scratch/ramdisk/init" ] || die "initramfs has no init"
[ -f "$scratch/ramdisk/bin/busybox" ] || die "initramfs has no busybox"
file "$scratch/ramdisk/bin/busybox" | grep -q 'ARM aarch64' || die "busybox is not arm64"
grep -q 'ncm.usb0' "$scratch/ramdisk/init" || die "init has no NCM gadget"
grep -q 'ecm.usb0' "$scratch/ramdisk/init" || die "init has no ECM gadget"
[ -x "$scratch/ramdisk/bin/dropbear" ] || die "initramfs has no sshd"
file "$scratch/ramdisk/bin/dropbear" | grep -q 'ARM aarch64' ||
	die "dropbear is not arm64"
file "$scratch/ramdisk/bin/dropbear" | grep -q 'statically linked' ||
	die "dropbear is not static"
qemu-aarch64 "$scratch/ramdisk/bin/dropbear" -V 2>&1 | grep -q 'v2026.94' ||
	die "dropbear does not run under qemu-aarch64 or reports the wrong version"
[ -s "$scratch/ramdisk/root/.ssh/authorized_keys" ] ||
	die "initramfs has no authorized_keys"
grep -q '^ssh-ed25519 ' "$scratch/ramdisk/root/.ssh/authorized_keys" ||
	die "authorized_keys does not hold an ed25519 public key"
[ "$(wc -l <"$scratch/ramdisk/root/.ssh/authorized_keys")" -eq 1 ] ||
	die "authorized_keys is not a single key"
grep -q '172.16.42.2:22' "$scratch/ramdisk/init" ||
	die "init does not start sshd bound to 172.16.42.2:22"
grep -q 'Copyright (c) 2002' "$scratch/ramdisk/usr/share/doc/dropbear/LICENSE" ||
	die "dropbear LICENSE is missing"
grep -q 'LibTomCrypt is public domain' \
	"$scratch/ramdisk/usr/share/doc/dropbear/LibTomCrypt-LICENSE" ||
	die "LibTomCrypt license is missing"
grep -q 'public domain' "$scratch/ramdisk/usr/share/doc/dropbear/LibTomMath-LICENSE" ||
	die "LibTomMath license is missing"
cmp -s "$scratch/built-boot/ramdisk" "$scratch/built-vendor/vendor_ramdisk00" ||
	die "boot and vendor ramdisks differ"
cmp -s "$scratch/built-boot/ramdisk" "$scratch/built-init/ramdisk" ||
	die "boot and init ramdisks differ"

report=$OUT/bootimg-verify.txt
{
	echo 'boot header v4 / vendor page size 4096; stock offsets match'
	echo "stock DTBO entry 65: $model; board-id <$board>; oem-id <$oem>"
	echo "built DTBO: $built_model; board-id <$built_board>; oem-id <$built_oem>"
	echo "built vendor DTB: 20 entries, Volcano at index 9; ramoops reg <$ramoops>; console-size 0x$console_size"
	echo 'vendor cmdline: earlycon keep_bootcon panic=-1 log_buf_len=1M'
	echo 'initramfs: gzip newc; static arm64 busybox + dropbear 2026.94 sshd; NCM+ECM; authorized_keys; console shell'
	echo 'unpack verification: passed'
	(cd "$OUT" && sha256sum boot.img init_boot.img vendor_boot.img dtb.img \
		Image.gz initramfs.cpio.gz Image)
	sha256sum "$STOCK_BOOT" "$STOCK_INIT" "$STOCK_VENDOR" "$STOCK_DTBO"
} | tee "$report"
