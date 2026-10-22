#!/usr/bin/env bash
set -euo pipefail

STOCK_BOOT=${STOCK_BOOT:-$HOME/phone-second-life-data/mb003/parts/boot_a.img}
STOCK_VENDOR=${STOCK_VENDOR:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_a.img}
STOCK_INIT=${STOCK_INIT:-$HOME/phone-second-life-data/mb003/parts/init_boot_a.img}
STOCK_DTBO=${STOCK_DTBO:-$HOME/phone-second-life-data/mb003/parts/dtbo_a.img}
STOCK_VBMETA=${STOCK_VBMETA:-$HOME/phone-second-life-data/mb003/parts/vbmeta_a.img}
STOCK_RECOVERY=${STOCK_RECOVERY:-$HOME/phone-second-life-data/mb003/parts/recovery_a.img}
STOCK_RECOVERY_B=${STOCK_RECOVERY_B:-$HOME/phone-second-life-data/mb003/parts/recovery_b.img}
STOCK_CONFIG=${STOCK_CONFIG:-$HOME/phone-second-life-data/mb003/config.gz}
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in unpack_bootimg python3 cpio gzip sha256sum file mktemp fdtget dtc \
	fdtoverlay qemu-aarch64; do
	need "$tool"
done
for reference in "$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_INIT" "$STOCK_DTBO" "$STOCK_VBMETA" \
	"$STOCK_RECOVERY" "$STOCK_RECOVERY_B"; do
	[ -f "$reference" ] || die "missing stock reference: $reference"
done
printf '%s\n' \
	'197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d  '"$STOCK_BOOT" \
	'baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193  '"$STOCK_INIT" \
	'237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253  '"$STOCK_VENDOR" \
	'759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992  '"$STOCK_DTBO" \
	'cc1926d2aa8e9c12df6a469111bf87f1e61e70022b84626fabcd014ae33cdffe  '"$STOCK_VBMETA" \
	'0c6767698ebb069064b450b109cde6a1172b478e30000fe852e7d9bc19dbae9e  '"$STOCK_RECOVERY" \
	'6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b  '"$STOCK_RECOVERY_B" | sha256sum -c - ||
	die 'stock references differ from verified slot-A/B backups'
for artifact in "$OUT/boot.img" "$OUT/boot-stock-kernel.img" "$OUT/boot-full-footer.img" \
	"$OUT/boot-stock-full-footer.img" \
	"$OUT/boot-blank-tail.img" \
	"$OUT/boot-hash-boundary.img" \
	"$OUT/boot-image-size.img" \
	"$OUT/init_boot.img" "$OUT/vendor_boot.img" \
	"$OUT/dtb.img" "$OUT/Image.gz" "$OUT/initramfs.cpio.gz" \
	"$OUT/.config" "$OUT/merged.config" \
	"$OUT/volcano-qrd-pro-overlay.dtbo" "$STOCK_CONFIG" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment" \
	"$ROOT/configs/asteroids-debug-marker.fragment" \
	"$WORK/src/fs/pstore/Kconfig"; do
	[ -f "$artifact" ] || die "missing artifact: $artifact"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "verification artifacts must stay outside this repository" ;;
esac
printf '%s\n' \
	'caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f  '"$OUT/initramfs.cpio.gz" \
	'e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9  '"$OUT/dtb.img" \
	'f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89  '"$OUT/init_boot.img" \
	'6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d  '"$OUT/vendor_boot.img" | sha256sum -c - ||
	die 'init_boot/vendor_boot/DTB/ramdisk differ from the verified #16 chain'
for old_boot in \
	'5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb' \
	'84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a' \
	'1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7' \
	'116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce'; do
	[ "$(sha256sum "$OUT/boot.img" | cut -d ' ' -f 1)" != "$old_boot" ] ||
		die "boot.img repeats old baseline $old_boot instead of changing the kernel"
done
python3 "$ROOT/scripts/verify-volcano-usb.py" --self-test
python3 "$ROOT/scripts/verify-volcano-usb.py" config \
	"$OUT/.config" "$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
for old_image in \
	'cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386' \
	'a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29'; do
	[ "$(sha256sum "$OUT/Image" | cut -d ' ' -f 1)" != "$old_image" ] ||
		die "Image repeats old baseline $old_image instead of changing the kernel"
done
python3 "$ROOT/scripts/verify-generic-ramdisk.py" --self-test
python3 "$ROOT/scripts/verify-recovery-boundary.py" --self-test
python3 "$ROOT/scripts/verify-recovery-boundary.py" "$STOCK_BOOT" "$STOCK_INIT" \
	"$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_RECOVERY_B" "$STOCK_VBMETA"
python3 "$ROOT/scripts/verify-generic-ramdisk.py" "$STOCK_BOOT" "$OUT/boot.img" \
	"$OUT/init_boot.img" "$OUT/Image.gz" "$OUT/initramfs.cpio.gz"
python3 "$ROOT/scripts/verify-stock-kernel-control.py" --self-test
python3 "$ROOT/scripts/verify-stock-kernel-control.py" \
	"$OUT/boot-stock-kernel.img" "$OUT/boot.img" "$STOCK_BOOT"
python3 "$ROOT/scripts/verify-hash-boundary-control.py" --self-test
python3 "$ROOT/scripts/verify-hash-boundary-control.py" \
	"$OUT/boot-hash-boundary.img" "$STOCK_BOOT"
python3 "$ROOT/scripts/verify-image-size-control.py" --self-test
python3 "$ROOT/scripts/verify-image-size-control.py" \
	"$OUT/boot-image-size.img" "$STOCK_BOOT"
python3 "$ROOT/scripts/verify-stock-full-footer.py" --self-test \
	"$OUT/boot-stock-full-footer.img" "$OUT/boot-stock-kernel.img" \
	"$OUT/boot.img" "$OUT/boot-full-footer.img"
python3 "$ROOT/scripts/verify-stock-full-footer.py" \
	"$OUT/boot-stock-full-footer.img" "$OUT/boot-stock-kernel.img" \
	"$OUT/boot.img" "$OUT/boot-full-footer.img"
python3 "$ROOT/scripts/verify-blank-tail-control.py" --self-test \
	"$OUT/boot-blank-tail.img" "$OUT/boot-stock-kernel.img" \
	"$OUT/boot-stock-full-footer.img"
python3 "$ROOT/scripts/verify-blank-tail-control.py" \
	"$OUT/boot-blank-tail.img" "$OUT/boot-stock-kernel.img" \
	"$OUT/boot-stock-full-footer.img"
python3 "$ROOT/scripts/verify-post-flash-avb.py" --self-test
python3 "$ROOT/scripts/verify-post-flash-avb.py" \
	"$STOCK_BOOT" "$STOCK_INIT" "$STOCK_VENDOR" \
	"$HOME/phone-second-life-data/mb003/pstore/attempt-20261021-1536/boot.img" \
	"$OUT/initramfs.cpio.gz" "$OUT/boot.img" "$OUT/boot-stock-kernel.img" \
	"$OUT/init_boot.img" "$OUT/vendor_boot.img" "$OUT/boot-full-footer.img"

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
	"$scratch/stock-vendor/dtb" \
	"$scratch/built-vendor/dtb" "$scratch/built-vendor/vendor_ramdisk00" \
	"$scratch/built-init/ramdisk" "$OUT/volcano-qrd-pro-overlay.dtbo" \
	"$STOCK_VBMETA" "$OUT/.config" "$STOCK_CONFIG" \
	"$ROOT/configs/asteroids-stock-cmdline.fragment" "$OUT/merged.config" \
	"$ROOT/configs/asteroids-debug-marker.fragment" "$WORK/src/fs/pstore/Kconfig" <<'PY'
import gzip
import hashlib
import pathlib
import struct
import sys

(stock_boot, stock_vendor, stock_init, stock_dtbo, built_boot, built_vendor,
 built_init, kernel, ramdisk, dtb, stock_kernel, unpacked_kernel,
 stock_dtbs, built_dtbs, built_vendor_ramdisk,
 built_init_ramdisk, overlay, stock_vbmeta, config, stock_config,
  fragment, merged_config, marker_fragment, pstore_kconfig) = (
    pathlib.Path(p).read_bytes() for p in sys.argv[1:])


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def check(name, condition):
    print(f"{name}: {'OK' if condition else 'FAIL'}")
    if not condition:
        raise SystemExit(1)


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def avb_descriptors(vbmeta):
    require(len(vbmeta) >= 256 and vbmeta[:4] == b"AVB0", "invalid AVB0 header")
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    offset, length = struct.unpack_from(">QQ", vbmeta, 96)
    start = 256 + auth + offset
    end = start + length
    require(256 + auth + aux <= len(vbmeta) and offset + length <= aux,
            "AVB metadata out of bounds")
    pos = start
    while pos < end:
        require(pos + 16 <= end, "AVB descriptor header out of bounds")
        tag, size = struct.unpack_from(">QQ", vbmeta, pos)
        require(size > 0 and pos + 16 + size <= end, "AVB descriptor out of bounds")
        yield tag, vbmeta[pos + 16:pos + 16 + size]
        pos += 16 + size


def avb_policy(vbmeta):
    require(len(vbmeta) >= 256 and vbmeta[:4] == b"AVB0", "invalid AVB0 header")
    return struct.unpack_from(">QII", vbmeta, 112)


def avb_hashes(vbmeta):
    hashes = {}
    for tag, body in avb_descriptors(vbmeta):
        if tag != 2:
            continue
        require(len(body) >= 116, "AVB hash descriptor too short")
        image_size = struct.unpack_from(">Q", body)[0]
        algorithm = body[8:40].split(b"\0", 1)[0]
        name_len, salt_len, digest_len, flags = struct.unpack_from(">IIII", body, 40)
        total = 116 + name_len + salt_len + digest_len
        require(total <= len(body), "AVB hash data out of bounds")
        name = body[116:116 + name_len]
        salt = body[116 + name_len:116 + name_len + salt_len]
        digest = body[116 + name_len + salt_len:total]
        require(algorithm == b"sha256" and digest_len == 32 and flags == 0 and
                name not in hashes, "unexpected stock AVB hash format")
        hashes[name] = (image_size, salt, digest)
    return hashes


def avb_footer(image):
    footer = image[-64:]
    require(len(footer) == 64 and footer[:4] == b"AVBf", "stock AVB footer missing")
    original, offset, size = struct.unpack_from(">QQQ", footer, 12)
    require(original == offset and offset + size <= len(image) - 64,
            "stock AVB footer out of bounds")
    return original, image[offset:offset + size]


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
check("stock kernel gzip", stock_kernel[:2] == b"\x1f\x8b")
check("built kernel gzip", kernel[:2] == b"\x1f\x8b")
check("stock boot ramdisk empty", u32(stock_boot, 12) == 0)
check("built boot ramdisk empty", u32(built_boot, 12) == 0)
check("boot kernel size", u32(built_boot, 8) == len(kernel))
check("built boot has no separate AVB0 region",
       len(built_boot) == 4096 + (len(kernel) + 4095) // 4096 * 4096)
built_cmdline = built_boot[44:1580].split(b"\x00", 1)[0]
check("boot cmdline diagnosis prefix",
      built_cmdline.startswith(b"console=ttynull ") and b"bootconfig" in built_cmdline)
check("boot image header cmdline is unchanged #18 value without the marker",
      built_cmdline == b"console=ttynull stack_depot_disable=on cgroup_disable=pressure "
      b"kasan.page_alloc.sample=10 kasan.stacktrace=off kvm-arm.mode=protected "
      b"bootconfig ioremap_guard loglevel=6")


def config_value(data, symbol):
    matches = [line for line in data.splitlines() if line.startswith(symbol + b"=")]
    require(len(matches) == 1, f"expected exactly one {symbol.decode()} setting")
    return matches[0].split(b"=", 1)[1]


check("measured stock config.gz SHA-256",
      hashlib.sha256(stock_config).hexdigest() ==
      "90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478")
stock_config = gzip.decompress(stock_config)
stock_cmdline = config_value(stock_config, b"CONFIG_CMDLINE")
check("stock CONFIG_CMDLINE_EXTEND", config_value(stock_config, b"CONFIG_CMDLINE_EXTEND") == b"y")
check("override fragment matches measured stock CONFIG_CMDLINE",
      fragment.strip() == b"CONFIG_CMDLINE=" + stock_cmdline)
MARKER = b"sm7635-boot-marker"
marked_cmdline = stock_cmdline[:-1] + b" " + MARKER + b'"'
marker_lines = marker_fragment.strip().splitlines()
check("debug marker fragment is exactly the marked stock cmdline and panic timeout",
      marker_lines == [b"CONFIG_CMDLINE=" + marked_cmdline, b"CONFIG_PANIC_TIMEOUT=-1"])
check("marker token appears once and is unmistakable",
      stock_cmdline.count(MARKER) == 0 and marked_cmdline.count(MARKER) == 1 and
      marked_cmdline.endswith(b" " + MARKER + b'"'))
check("merged CONFIG_CMDLINE is measured stock plus marker",
      config_value(merged_config, b"CONFIG_CMDLINE") == marked_cmdline)
check("merged CONFIG_PANIC_TIMEOUT=-1",
      config_value(merged_config, b"CONFIG_PANIC_TIMEOUT") == b"-1")
check("built CONFIG_CMDLINE is measured stock plus marker", config_value(config, b"CONFIG_CMDLINE") ==
      marked_cmdline)
check("built CONFIG_PANIC_TIMEOUT=-1", config_value(config, b"CONFIG_PANIC_TIMEOUT") == b"-1")
check("stock config already has CONFIG_PANIC_TIMEOUT=-1",
      config_value(stock_config, b"CONFIG_PANIC_TIMEOUT") == b"-1")
check("built .config has no panic_on_taint", b"panic_on_taint" not in config)
check("built CONFIG_CMDLINE_EXTEND", config_value(config, b"CONFIG_CMDLINE_EXTEND") == b"y")
for symbol in (b"CONFIG_PSTORE", b"CONFIG_PSTORE_CONSOLE", b"CONFIG_PSTORE_RAM"):
    check(f"built {symbol.decode()}=y", config_value(config, symbol) == b"y")
console_size_defined = any(
    line.split()[:2] == [b"config", b"PSTORE_CONSOLE_SIZE"]
    for line in pstore_kconfig.splitlines() if line.strip())
if console_size_defined:
    check("fragment requests 2 MiB CONFIG_PSTORE_CONSOLE_SIZE",
          b"CONFIG_PSTORE_CONSOLE_SIZE=2097152" in marker_lines)
    check("built CONFIG_PSTORE_CONSOLE_SIZE is 2 MiB",
          config_value(config, b"CONFIG_PSTORE_CONSOLE_SIZE") == b"2097152")
    pstore_mode = "CONFIG_PSTORE_CONSOLE_SIZE=2097152"
else:
    check("issue exception: CONFIG_PSTORE_CONSOLE_SIZE absent from pinned fs/pstore/Kconfig",
          b"PSTORE_CONSOLE_SIZE" not in pstore_kconfig.replace(b"PSTORE_BLK_CONSOLE_SIZE", b""))
    check("issue exception: no synthesized CONFIG_PSTORE_CONSOLE_SIZE in fragment or .config",
          b"CONFIG_PSTORE_CONSOLE_SIZE" not in marker_fragment and
          b"CONFIG_PSTORE_CONSOLE_SIZE" not in config and
          b"CONFIG_PSTORE_CONSOLE_SIZE" not in stock_config)
    pstore_mode = "issue exception (stock DT console-size 0x200000)"
print(f"pstore console size handling: {pstore_mode}")
image = gzip.decompress(unpacked_kernel)
start = image.find(b"IKCFG_ST")
end = image.find(b"IKCFG_ED", start + 8)
require(start >= 0 and end > start, "unpacked kernel has no embedded IKCONFIG")
embedded_config = gzip.decompress(image[start + 8:end])
check("unpacked kernel embedded config matches .config", embedded_config == config)
kernel_cmdline = config_value(embedded_config, b"CONFIG_CMDLINE")
check("unpacked kernel config has no panic_on_taint", b"panic_on_taint" not in embedded_config)
check("unpacked kernel CONFIG_CMDLINE is measured stock plus marker", kernel_cmdline == marked_cmdline)
check("unpacked kernel embedded config has CONFIG_PANIC_TIMEOUT=-1",
      config_value(embedded_config, b"CONFIG_PANIC_TIMEOUT") == b"-1")
check("unpacked kernel embedded config has no synthesized CONFIG_PSTORE_CONSOLE_SIZE"
      if not console_size_defined else "unpacked kernel embedded config has 2 MiB console size",
      (b"CONFIG_PSTORE_CONSOLE_SIZE" not in embedded_config) if not console_size_defined
      else config_value(embedded_config, b"CONFIG_PSTORE_CONSOLE_SIZE") == b"2097152")
check("unpacked kernel image carries the marked built-in command line string",
      marked_cmdline[1:-1] + b"\x00" in image and image.count(MARKER) >= 2)
check("unpacked kernel effective built-in command line begins with measured stock tokens "
      "and ends with the marker",
      marked_cmdline[1:-1].startswith(stock_cmdline[1:-1]) and
      marked_cmdline[1:-1].endswith(b" " + MARKER))
for name, cmdline in ((".config", config_value(config, b"CONFIG_CMDLINE")),
                      ("unpacked kernel", kernel_cmdline),
                      ("boot image", built_cmdline),
                      ("init_boot image", built_init[44:1580].split(b"\x00", 1)[0]),
                      ("vendor_boot image", built_vendor[28:2076].split(b"\x00", 1)[0])):
    check(f"{name} has no panic_on_taint or removed debug flags",
          not any(flag in cmdline for flag in (
              b"panic_on_taint", b"stack_depot_disable=off", b"page_owner=on",
              b"page_pinner=on", b"no_hash_pointers", b"slub_debug=")))

stock_boot_end = 4096 + (u32(stock_boot, 8) + 4095) // 4096 * 4096
check("stock boot has separate 16KiB AVB0 region",
      stock_boot[stock_boot_end:stock_boot_end + 4] == b"AVB0" and
      stock_boot[stock_boot_end + 16384:stock_boot_end + 16388] == b"AVB0")
check("stock vbmeta_a verification flags and rollback",
      avb_policy(stock_vbmeta) == (0, 0, 0))

check("stock init header v4", stock_init[:8] == b"ANDROID!" and
      u32(stock_init, 20) == 1584 and u32(stock_init, 40) == 4 and
      u32(stock_init, 1580) == 0)
check("stock init kernel empty", u32(stock_init, 8) == 0)
check("stock init generic ramdisk nonempty", u32(stock_init, 12) > 0)
check("built init kernel empty", u32(built_init, 8) == 0)
check("built init ramdisk size", u32(built_init, 12) == len(ramdisk) > 0)
check("built init ramdisk", built_init_ramdisk == ramdisk)

root_hashes = avb_hashes(stock_vbmeta)
for name, stock, built in ((b"boot", stock_boot, built_boot),
                           (b"init_boot", stock_init, built_init),
                           (b"vendor_boot", stock_vendor, built_vendor)):
    label = name.decode()
    original, embedded = avb_footer(stock)
    embedded_hashes = avb_hashes(embedded)
    check(f"stock {label} embedded verification flags", avb_policy(embedded)[1] == 0)
    check(f"stock {label} embedded hash descriptor", name in embedded_hashes)
    size, salt, digest = embedded_hashes[name]
    if name == b"boot":
        check("stock boot AVB0 region ends at embedded vbmeta",
              stock_boot_end + 16384 == original)
        boot_record = stock_boot[stock_boot_end:original]
        boot_record_hashes = avb_hashes(boot_record)
        check("stock boot separate AVB0 verification flags", avb_policy(boot_record)[1] == 0)
        check("stock boot separate AVB0 hashes payload", b"boot" in boot_record_hashes and
              boot_record_hashes[b"boot"][0] == stock_boot_end and
              hashlib.sha256(boot_record_hashes[b"boot"][1] +
                             stock_boot[:stock_boot_end]).digest() ==
              boot_record_hashes[b"boot"][2])
        check("stock boot AVB0 records have distinct hashed prefixes",
              boot_record_hashes[b"boot"][0] != size)
    check(f"stock {label} hash matches footer", size == original and
          hashlib.sha256(salt + stock[:size]).digest() == digest)
    if name in (b"init_boot", b"vendor_boot"):
        check(f"stock vbmeta_a {label} hash matches embedded metadata",
              root_hashes.get(name) == embedded_hashes[name])
        check(f"stock vbmeta_a {label} hashed prefix",
              hashlib.sha256(root_hashes[name][1] +
                             stock[:root_hashes[name][0]]).digest() == root_hashes[name][2])
    check(f"built {label} differs from stock AVB hash",
          len(built) < size or hashlib.sha256(salt + built[:size]).digest() != digest)
    check(f"built {label} has no stock AVB footer", built[-64:-60] != b"AVBf")
    print(f"{label} AVB: stock footer/embedded hash valid; built stock hash invalid; "
          "built footer absent")
check("stock vbmeta_a has dtbo hash", b"dtbo" in root_hashes)
dtbo_size, dtbo_salt, dtbo_digest = root_hashes[b"dtbo"]
check("stock dtbo matches vbmeta_a hash", dtbo_size <= len(stock_dtbo) and
      hashlib.sha256(dtbo_salt + stock_dtbo[:dtbo_size]).digest() == dtbo_digest)
check("stock vbmeta_a chains boot", any(
    tag == 4 and len(body) >= 84 and struct.unpack_from(">I", body, 4)[0] == 4
    and body[76:80] == b"boot" and struct.unpack_from(">I", body)[0] == 3
    for tag, body in avb_descriptors(stock_vbmeta)))

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
    ramdisk_size, dtb_size = u32(image, 24), u32(image, 2100)
    table_offset = 4096 + ((ramdisk_size + 4095) // 4096 +
                           (dtb_size + 4095) // 4096) * 4096
    check(f"{label} vendor ramdisk table size", u32(image, 2112) == 108)
    check(f"{label} vendor ramdisk table bounds", table_offset + 108 <= len(image))
    size, offset, ramdisk_type = struct.unpack_from("<III", image, table_offset)
    check(f"{label} vendor ramdisk table PLATFORM fragment",
          (size, offset, ramdisk_type) == (ramdisk_size, 0, 1) and
          not any(image[table_offset + 12:table_offset + 108]))
    bootconfig_offset = table_offset + 4096
    bootconfig_size = u32(image, 2124)
    check(f"{label} bootconfig bounds", bootconfig_offset + bootconfig_size <= len(image))
    if label == "stock":
        stock_bootconfig = image[bootconfig_offset:bootconfig_offset + bootconfig_size]
    else:
        check("built bootconfig matches stock", bootconfig_size == len(stock_bootconfig) and
              image[bootconfig_offset:bootconfig_offset + bootconfig_size] == stock_bootconfig)
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
check("built vendor preserves stock DTBs", built_models == stock_models)
check("built vendor selects Volcano at index 9", b"Volcano SoC" in built_models[9])

if stock_dtbo[:4] != b"\xd7\xb7\xab\x1e":
    raise SystemExit("stock dtbo table has incorrect magic")
entries = struct.unpack_from(">I", stock_dtbo, 16)[0]
entry_size = struct.unpack_from(">I", stock_dtbo, 12)[0]
table_offset = struct.unpack_from(">I", stock_dtbo, 20)[0]
check("stock DTBO entry size", entry_size >= 8 and entries > 65)
check("stock DTBO table bounds", table_offset + entries * entry_size <= len(stock_dtbo))
entry = table_offset + 65 * entry_size
size, offset = struct.unpack_from(">II", stock_dtbo, entry)
check("stock DTBO entry 65 bounds", size >= 40 and offset + size <= len(stock_dtbo))
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
if size < 40 or offset + size > len(image):
    raise SystemExit("stock DTBO entry 65 is out of bounds")
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
dtc -I dtb -O dts "$scratch/volcano.dtb" >"$scratch/volcano.dts" 2>"$scratch/dtc-warnings.txt"
fdtoverlay -i "$scratch/volcano.dtb" -o "$scratch/stock-board.dtb" "$stock_overlay" ||
	die 'stock DTBO entry 65 does not apply to built vendor DTB index 9'
ramoops=$(fdtget -t x "$scratch/stock-board.dtb" /reserved-memory/ramoops_region reg)
console_size=$(fdtget -t x "$scratch/stock-board.dtb" /reserved-memory/ramoops_region console-size)
pmsg_size=$(fdtget -t x "$scratch/stock-board.dtb" /reserved-memory/ramoops_region pmsg-size)
[ "$ramoops" = '0 81f20000 0 400000' ] &&
	[ "$console_size" = '200000' ] && [ "$pmsg_size" = '200000' ] ||
	die 'stock DTBO overlay did not provide the stock ramoops reservation'
python3 "$ROOT/scripts/verify-volcano-usb.py" board "$OUT/.config" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment" \
	"$scratch/built-boot/kernel" "$scratch/stock-board.dtb" \
	"$scratch/built-init/ramdisk"

mkdir -p "$scratch/ramdisk"
gzip -dc "$scratch/built-init/ramdisk" | cpio -itv --quiet >"$scratch/ramdisk-list.txt"
for device in 'dev/console' 'dev/null' 'dev/kmsg' 'dev/ptmx'; do
	grep -q "^c.* $device$" "$scratch/ramdisk-list.txt" || die "missing device node: $device"
done
grep -q 'bin/busybox' "$scratch/ramdisk-list.txt" || die "initramfs has no busybox"
gzip -dc "$scratch/built-init/ramdisk" | \
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
cmp -s "$scratch/built-init/ramdisk" "$scratch/built-vendor/vendor_ramdisk00" ||
	die "init and vendor ramdisks differ"

report=$OUT/bootimg-verify.txt
{
	echo 'boot header v4 / vendor page size 4096; stock offsets match; stock and built boot generic ramdisk size zero; debug generic ramdisk only in init_boot'
	echo 'control: verified #21 header page except kernel-size field; stock slot-A gzip kernel payload byte-identical; 4096-aligned image length without AVB; shared arm64 Image header fields; unique SHA'
	echo 'image_size control: stock slot-A image with only decompressed bytes 16..23 changed from 35913728 to 55508992; decompressed length 35224064; gzip payload 13949926; stock header, padding window, AVB record and footer unchanged; salted 13971456-byte prefix differs from the stock digest'
	echo 'stock unsigned footer control: 13955072-byte 13a48ff9 prefix byte-identical; 100663296-byte image; 448-byte AVB0 at offset 13955072; algorithm NONE; salt d41d8cd98f00b204e9800998ecf8427e; differs from d966172c only in the stock kernel payload and resulting hash descriptor; host-only, not a boot result'
	echo 'blank-tail control: 13955072-byte 13a48ff9 prefix byte-identical; 86708224 zero bytes; 100663296-byte image; no AVB0 block and no AVBf footer; differs from 6891dc51 only in the tail; host-only, not a boot result'
	echo 'stock AVB footers and hashed image prefixes match embedded metadata; vbmeta_a init_boot/vendor_boot/dtbo hashes match stock; boot is chained'
	echo 'stock boot separate 16KiB AVB0 record hashes the shorter kernel-only prefix; stock verification flags and vbmeta_a rollback index are zero'
	echo 'built images are not authenticated by stock vbmeta_a: no AVB footer, stock hashes do not match; bootloader policy during attempt unknown'
	echo 'post-flash model: libavb model, not an observed ABL verdict; see BOOT.md for the per-SHA metadata table'
	echo "stock DTBO entry 65: $model; board-id <$board>; oem-id <$oem>"
	echo "built DTBO: $built_model; board-id <$built_board>; oem-id <$built_oem>"
	echo "built vendor DTBs: all 20 byte-identical to stock; DTBO 65 applies to index 9; ramoops reg <$ramoops>; console-size 0x$console_size"
	echo 'kernel CONFIG_CMDLINE: stock override + asteroids-debug-marker.fragment appends sm7635-boot-marker; merged config, built config, embedded IKCONFIG and Image carry the marker; no panic_on_taint or removed debug flags in boot chain cmdlines'
	echo 'pstore / panic: CONFIG_PSTORE=y, CONFIG_PSTORE_CONSOLE=y, CONFIG_PSTORE_RAM=y, CONFIG_PANIC_TIMEOUT=-1; CONFIG_PSTORE_CONSOLE_SIZE absent from pinned 6.1.78 Kconfig (issue exception: 2 MiB console-size 0x200000 verified from stock DTBO 65 ramoops_region)'
	echo 'recovery boundary: recovery_a and recovery_b are header-v4 kernel_size=0 LZ4 ramdisks chained in vbmeta_a at rollback location 1; recovery also consumes boot_a, init_boot_a and vendor_boot_a'
	echo 'Volcano USB reachability: /soc/ssusb@a600000 (qcom,dwc-usb3-msm), child dwc3@a600000 and all 22 DT phandle suppliers resolve to built-in (=y) drivers'
	echo 'vendor cmdline: earlycon keep_bootcon panic=-1 log_buf_len=1M'
	echo 'initramfs: gzip newc; static arm64 busybox + dropbear 2026.94 sshd; NCM+ECM; authorized_keys; console shell'
	echo 'unpack verification: passed'
	(cd "$OUT" && sha256sum boot.img boot-stock-kernel.img boot-full-footer.img \
		boot-stock-full-footer.img boot-blank-tail.img boot-hash-boundary.img boot-image-size.img init_boot.img \
		vendor_boot.img dtb.img \
		Image.gz initramfs.cpio.gz Image)
	sha256sum "$STOCK_BOOT" "$STOCK_INIT" "$STOCK_VENDOR" "$STOCK_DTBO" \
		"$STOCK_VBMETA" "$STOCK_RECOVERY" "$STOCK_RECOVERY_B"
} | tee "$report"
