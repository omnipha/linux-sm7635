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
	"$OUT/boot-avb0-window-erase.img" \
	"$OUT/boot-avbf-footer-erase.img" \
	"$OUT/init_boot-debug-ramdisk.img" \
	"$OUT/init_boot-lz4-debug-ramdisk.img" \
	"$OUT/init_boot-vendor-modules.img" \
	"$OUT/init_boot-self-recovering.img" \
	"$OUT/init_boot-eud-softdep.img" \
	"$OUT/init_boot-peripheral-mode.img" \
	"$OUT/init_boot-static-address.img" \
	"$OUT/init_boot-kernel-banner.img" \
	"$OUT/init_boot-initcall-debug.img" \
	"$OUT/init_boot-wlan-closure.img" \
	"$OUT/init_boot-wlan-rfkill.img" \
	"$OUT/boot-diagnostic-ext4.img" \
	"$OUT/boot-diagnostic-initcall-debug.img" \
	"$OUT/Image-diagnostic-ext4.gz" \
	"$OUT/Image-diagnostic-ext4" \
	"$OUT/Image-diagnostic-initcall-debug.gz" \
	"$OUT/Image-diagnostic-initcall-debug" \
	"$OUT/.config-diagnostic-ext4" \
	"$OUT/.config-diagnostic-initcall-debug" \
	"$OUT/.config-diagnostic-kallsyms-nls" \
	"$OUT/restart2" \
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
python3 "$ROOT/scripts/verify-avb0-window-erase.py" --self-test \
	"$OUT/boot-avb0-window-erase.img" "$OUT/boot-stock-kernel.img" \
	"$STOCK_BOOT"
python3 "$ROOT/scripts/verify-avb0-window-erase.py" \
	"$OUT/boot-avb0-window-erase.img" "$OUT/boot-stock-kernel.img" \
	"$STOCK_BOOT"
python3 "$ROOT/scripts/verify-avbf-footer-erase.py" --self-test \
	"$OUT/boot-avbf-footer-erase.img" "$OUT/boot-avb0-window-erase.img" \
	"$STOCK_BOOT"
python3 "$ROOT/scripts/verify-avbf-footer-erase.py" \
	"$OUT/boot-avbf-footer-erase.img" "$OUT/boot-avb0-window-erase.img" \
	"$STOCK_BOOT"
python3 "$ROOT/scripts/verify-init-boot-debug-ramdisk.py" --self-test \
	"$OUT/init_boot-debug-ramdisk.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz"
python3 "$ROOT/scripts/verify-init-boot-debug-ramdisk.py" \
	"$OUT/init_boot-debug-ramdisk.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz"
python3 "$ROOT/scripts/verify-init-boot-lz4-debug-ramdisk.py" --self-test \
	"$OUT/init_boot-lz4-debug-ramdisk.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz"
python3 "$ROOT/scripts/verify-init-boot-lz4-debug-ramdisk.py" \
	"$OUT/init_boot-lz4-debug-ramdisk.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz"
PSTORE_CONSOLE=$HOME/phone-second-life-data/mb003/pstore/attempt-20261022-2004-initboot-lz4debug/pstore/console-ramoops-0
for source in "$PSTORE_CONSOLE" "$WORK/src/init/initramfs.c" \
	"$WORK/src/lib/decompress_unlz4.c"; do
	[ -f "$source" ] || die "missing vendor-module proof source: $source"
done
python3 "$ROOT/scripts/vendor-module-closure.py" "$STOCK_VENDOR"
python3 "$ROOT/scripts/verify-init-boot-vendor-modules.py" --self-test \
	"$OUT/init_boot-vendor-modules.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE"
python3 "$ROOT/scripts/verify-init-boot-vendor-modules.py" \
	"$OUT/init_boot-vendor-modules.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE"
python3 "$ROOT/scripts/verify-init-boot-self-recovering.py" --self-test \
	"$OUT/init_boot-self-recovering.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-self-recovering.py" \
	"$OUT/init_boot-self-recovering.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-eud-softdep.py" --self-test \
	"$OUT/init_boot-eud-softdep.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-eud-softdep.py" \
	"$OUT/init_boot-eud-softdep.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-peripheral-mode.py" --self-test \
	"$OUT/init_boot-peripheral-mode.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-peripheral-mode.py" \
	"$OUT/init_boot-peripheral-mode.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-static-address.py" --self-test \
	"$OUT/init_boot-static-address.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-static-address.py" \
	"$OUT/init_boot-static-address.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
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
python3 "$ROOT/scripts/verify-diagnostic-initcall-debug.py" --self-test \
	"$OUT/boot-diagnostic-initcall-debug.img" "$STOCK_BOOT" \
	"$OUT/Image-diagnostic-initcall-debug.gz" "$OUT/Image-diagnostic-initcall-debug" \
	"$OUT/.config-diagnostic-initcall-debug" "$OUT/.config-diagnostic-ext4" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
python3 "$ROOT/scripts/verify-diagnostic-initcall-debug.py" \
	"$OUT/boot-diagnostic-initcall-debug.img" "$STOCK_BOOT" \
	"$OUT/Image-diagnostic-initcall-debug.gz" "$OUT/Image-diagnostic-initcall-debug" \
	"$OUT/.config-diagnostic-initcall-debug" "$OUT/.config-diagnostic-ext4" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
python3 "$ROOT/scripts/verify-init-boot-kernel-banner.py" --self-test \
	"$OUT/init_boot-kernel-banner.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-kernel-banner.py" \
	"$OUT/init_boot-kernel-banner.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-initcall-debug.py" --self-test \
	"$OUT/init_boot-initcall-debug.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-initcall-debug.py" \
	"$OUT/init_boot-initcall-debug.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-wlan-closure.py" --self-test \
	"$OUT/init_boot-wlan-closure.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-wlan-closure.py" \
	"$OUT/init_boot-wlan-closure.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-wlan-rfkill.py" --self-test \
	"$OUT/init_boot-wlan-rfkill.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
python3 "$ROOT/scripts/verify-init-boot-wlan-rfkill.py" \
	"$OUT/init_boot-wlan-rfkill.img" "$STOCK_INIT" "$OUT/initramfs.cpio.gz" \
	"$STOCK_BOOT" "$STOCK_VENDOR" "$STOCK_RECOVERY" "$STOCK_CONFIG" \
	"$WORK/src/init/initramfs.c" "$WORK/src/lib/decompress_unlz4.c" \
	"$PSTORE_CONSOLE" "$OUT/restart2"
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
unpack_bootimg --boot_img "$OUT/boot-diagnostic-ext4.img" --out "$scratch/diagnostic-boot" >/dev/null
unpack_bootimg --boot_img "$OUT/init_boot-kernel-banner.img" --out "$scratch/diagnostic-init" >/dev/null
unpack_bootimg --boot_img "$OUT/init_boot-initcall-debug.img" --out "$scratch/diagnostic-init63" >/dev/null
unpack_bootimg --boot_img "$OUT/boot-diagnostic-initcall-debug.img" --out "$scratch/diagnostic-boot63" >/dev/null
python3 -B - "$ROOT/scripts" "$scratch/diagnostic-init/ramdisk" \
	"$scratch/diagnostic-init/ramdisk.cpio.gz" <<'PY'
import gzip
import importlib.util
import pathlib
import sys

root, source, output = sys.argv[1:]
spec = importlib.util.spec_from_file_location(
    "vendor_checker", pathlib.Path(root) / "verify-init-boot-vendor-modules.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
frame = pathlib.Path(source).read_bytes()
cpio = checker.decode_frame(frame, checker.base.lz4())
pathlib.Path(output).write_bytes(gzip.compress(cpio, mtime=0))
PY
python3 "$ROOT/scripts/verify-volcano-usb.py" board "$OUT/.config-diagnostic-ext4" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment" \
	"$scratch/diagnostic-boot/kernel" "$scratch/stock-board.dtb" \
	"$scratch/diagnostic-init/ramdisk.cpio.gz"
python3 -B - "$ROOT/scripts" "$scratch/diagnostic-init63/ramdisk" \
	"$scratch/diagnostic-init63/ramdisk.cpio.gz" <<'PY'
import gzip
import importlib.util
import pathlib
import sys

root, source, output = sys.argv[1:]
spec = importlib.util.spec_from_file_location(
    "vendor_checker", pathlib.Path(root) / "verify-init-boot-vendor-modules.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
frame = pathlib.Path(source).read_bytes()
cpio = checker.decode_frame(frame, checker.base.lz4())
pathlib.Path(output).write_bytes(gzip.compress(cpio, mtime=0))
PY
python3 "$ROOT/scripts/verify-volcano-usb.py" board "$OUT/.config-diagnostic-initcall-debug" \
	"$ROOT/configs/asteroids-volcano-usb-builtin.fragment" \
	"$scratch/diagnostic-boot63/kernel" "$scratch/stock-board.dtb" \
	"$scratch/diagnostic-init63/ramdisk.cpio.gz"

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
	echo 'avb0-window-erase control: 13955072-byte 13a48ff9 prefix byte-identical; bytes [13955072, 13971456) zero; signed vbmeta and footer from offset 13971456 byte-identical to stock boot_a; 100663296-byte image; host-only, not a boot result'
	echo 'avbf-footer-erase control: bytes before offset 100663232 byte-identical to e7fd2022; final 64 AVBf bytes zero; signed vbmeta block and erased AVB0 window unchanged; 100663296-byte image; host-only, not a boot result'
	echo 'init_boot debug-ramdisk control: stock baa33fd4 prefix except ramdisk-size field 2113581 -> 1672600; gzip newc cpio caa3eb82 at offset 4096; 445032-byte zero gap; signed tail from offset 2121728 through terminal AVBf unchanged; 8388608-byte image; host-only, not a boot result'
	echo 'init_boot lz4-debug-ramdisk control: stock baa33fd4 prefix except ramdisk-size field 2113581 -> 1927750; one Android LZ4 legacy frame (02214c18, one 1927742-byte block, LZ4 HC level 12) of the cpio inside caa3eb82 at offset 4096; 189882-byte zero gap; signed tail from offset 2121728 through terminal AVBf unchanged; 8388608-byte image; host-only, not a boot result'
	echo 'init_boot vendor-modules control: same stock baa33fd4 prefix and signed tail; ramdisk is one LZ4 HC-12 block of the caa3eb82 cpio whose init is replaced with the 126-module vendor closure loader; debug cpio carries zero .ko; unchanged stock vendor_boot_a contributes lib/modules in the concatenated initrd; negative fixtures reject a tail change, a header change, a kernel size, a block change, modern LZ4 magic, a wrong ramdisk size, a nonzero gap, a short image, a removed load path, a planted .ko and every repeated prior SHA; host-only, not a boot result'
	echo 'init_boot self-recovering control: same stock baa33fd4 prefix and signed tail; ramdisk is one LZ4 HC-12 block of the caa3eb82 cpio whose init is the 126-module vendor closure loader plus a pre-insmod loading marker, a qcom-reboot-reason bind check and an independent 150 s self-recovery timer; the only added file is the static arm64 RESTART2 helper bin/restart2; debug cpio carries zero .ko; negative fixtures reject a missing or loop-nested timer, a marker that does not precede insmod, a removed bind check, a changed module list, a missing, dynamic or altered helper, a planted .ko, a modified tail and every repeated prior SHA including cdb9458f, 3932504a, f4a00ce3 and baa33fd4; host-only, not a boot result'
	echo 'init_boot eud-softdep control: same stock baa33fd4 prefix and signed tail as the self-recovering control; ramdisk is one LZ4 HC-12 block of the caa3eb82 cpio whose init is the #47 init with exactly one added insmod of the stock eud.ko after its modules.dep prerequisites and immediately before dwc3-msm.ko, the other 126 modules in their old order, the unchanged 150 s timer, /run/keep escape and bin/restart2 helper, and read-only logging of EUD bind, a600000.ssusb bind or deferred state and UDC names; debug cpio carries zero .ko; negative fixtures reject missing, duplicated or misordered eud.ko, an unresolved softdep target, a changed dwc3 softdep edge, an out-of-closure or non-arm64 eud.ko, a changed old module order, a removed timer, bad envelope or tail, a planted .ko and every repeated prior SHA including 8f8b7331; host-only, not a boot result'
	echo 'init_boot peripheral-mode control: same stock baa33fd4 prefix and signed tail as the eud-softdep control; ramdisk is one LZ4 HC-12 block of the caa3eb82 cpio whose init is the frozen #49 init plus exactly one step after the module phase and before the UDC wait: it discovers the msm-dwc3 device a600000.ssusb under /sys/bus/platform/devices/ without a hardcoded SoC path, logs that the mode attribute exists with its current value, writes peripheral once and logs the write result and readback, keeps the unchanged 40x0.25s UDC wait, and moves the EUD/glue bind checks after it with capped read-only logging of the a600000.dwc3 child, udc names, a600000.* devices_deferred entries and dmesg msm-dwc3/dwc3/phy/repeater lines (64-line caps); the 127-module list and order, 150 s /run/keep timer, bin/restart2 helper, key-only sshd and NCM/ECM path are unchanged and the debug cpio carries zero .ko; negative fixtures reject a missing or duplicated write, a write before the module phase or before eud.ko/dwc3-msm.ko, a value other than peripheral, a hardcoded SoC path, a removed or moved timer, a changed module order, a planted .ko, a bad envelope or tail and every repeated prior SHA including 88c93077; host-only, not a boot result'
	echo 'init_boot static-address control: same stock baa33fd4 prefix and signed tail as the peripheral-mode control; ramdisk is one LZ4 HC-12 block of the caa3eb82 cpio whose init is the frozen #51 init (initramfs/init-51-peripheral-mode, so 9f89fe8d still rebuilds) with the four discarded usb0/usb1 link and address commands replaced by commands that log their result, read-only ip addr show dev usb0, dev usb1 and ip route output capped at 32 lines, and one bounded read-only listener check (ss or netstat, else dropbear process and /proc/net/tcp) for 172.16.42.2:22 capped at 64 lines; the 127-module order, single peripheral write, 40x0.25s UDC wait, 150 s /run/keep timer, bin/restart2 helper, NCM+ECM functions and key-only sshd are unchanged and the debug cpio carries zero .ko; negative fixtures reject a missing or duplicated address log, a discarded address or link result, missing or lengthened network and listener diagnostics, a removed, moved or lengthened timer, a changed module order, a second role write, a changed gadget function, a planted .ko, a bad envelope or tail and every repeated prior SHA including 9f89fe8d; host-only, not a boot result'
echo 'init_boot kernel-banner control: same stock baa33fd4 prefix and signed tail as the static-address control; ramdisk is one LZ4 HC-12 block of the caa3eb82 cpio whose init is the frozen #53 init plus exactly one log line after starting reporting uname -r and /proc/version; the 127-module order, single peripheral write, 40x0.25s UDC wait, 150 s /run/keep timer, bin/restart2 helper, NCM+ECM functions and key-only sshd are unchanged and the debug cpio carries zero .ko; negative fixtures reject a removed, duplicated, moved or reworded banner line, a second diagnostic line, a changed module order, a second role write, a changed gadget function, a removed address log, a removed or lengthened timer, a planted .ko, a bad envelope or tail and every repeated prior SHA including 995aaca3, 9f89fe8d and 37535dd1; host-only, not a boot result'
echo 'diagnostic signed-tail boot control: stock boot_a 197aff11 with only the kernel-size field 13949926 -> 13806454 and the gzip payload replaced by the EXT4_FS-off own 6.1.78 kernel; zero padding fills to offset 13955072; stock AVB0 at 13955072, vbmeta at 13971456 and terminal AVBf unchanged; 100663296-byte image; negative fixtures reject a header, payload, padding, AVB0, vbmeta or footer byte change, an F2FS_FS config change and every repeated prior SHA including 37535dd1, 55fa78ca, 5a513998, dc990b95 and 13a48ff9; host-only, not a boot result'
echo 'initcall-debug boot control: stock boot_a 197aff11 with only the kernel-size field and the gzip payload replaced by the EXT4_FS-off own 6.1.78 kernel whose CONFIG_CMDLINE differs from the #59 config by exactly the token initcall_debug; zero padding fills to offset 13955072; stock AVB0, vbmeta and terminal AVBf unchanged; negative fixtures reject a header, payload, padding, AVB0, vbmeta or footer byte change, a config missing, doubled or blacklisted initcall_debug, a second config delta and every repeated prior SHA including 0ca048d5, cafcabb6, 7be448b9, d259b744, 37535dd1 and 13a48ff9; host-only, not a boot result'
echo 'init_boot initcall-debug control: same stock prefix and signed tail as the kernel-banner control; ramdisk is one LZ4 HC-12 block of the debug cpio whose init is the frozen #53 init plus exactly one log line after starting, identical to the #59 banner line except the literal kernel banner #63; the 127-module order, single peripheral write, UDC wait, 150 s timer, helper, NCM+ECM and key-only sshd are unchanged and the debug cpio carries zero .ko; negative fixtures reject a removed, duplicated, moved or reworded banner, the measured #59 banner text, a second diagnostic line, a changed module order, a second role write, a planted .ko, a bad envelope or tail and every repeated prior SHA including cafcabb6 and 995aaca3; host-only, not a boot result'
echo 'init_boot wlan-rfkill control: same stock baa33fd4 prefix and signed tail as the wlan-closure control; ramdisk is one LZ4 HC-12 block of the debug cpio whose init is the frozen run-24 #53 init plus the corrected wlan-init phase before console ready: the run-27 measurement showed vendor_a and system_dlkm_a failing because loop nodes were created with minor equal to the loop index while the stock cmdline sets loop.max_part=7, so loop9 and loop10 aliased loop1 partitions; this image derives each loop node major:minor from /sys/block/loopN/dev, probes the extent fstype (erofs magic at byte 1024, else ext4 magic at byte 1080, else skip) instead of assuming it, mounts system_dlkm_a, vendor_a and vendor_dlkm_a read-only from their verified super extents on the single by-name super device /dev/block/sda6 (no second super loop), probes and mounts the by-name modem_a partition (/dev/block/sde6, the measured stock source of /vendor/firmware_mnt/image/qca6750/bdwlan.elf) read-only vfat only after its FAT signature matches and logs the firmware file presence, then insmods the same 21-module closure with rfkill.ko (the measured system_dlkm provider, SHA-256 773ddddb) before cfg80211.ko and logs per-module results, the fstype, the mount results, a wlan0 interface check and capped wlan dmesg; the 127-module order, single peripheral write, 40x0.25s UDC wait, 150 s /run/keep timer, bin/restart2 helper, NCM+ECM functions and key-only sshd are unchanged and the debug cpio carries zero .ko; negative fixtures reject the run-27 loop-minor regression, an assumed fstype, a removed system_dlkm mount, a second guessed super loop, rfkill loaded from vendor_dlkm, rfkill absent from the verified system_dlkm, a false vendor_a by-name claim, cfg80211 before rfkill, rfkill removed from the closure, a removed or unprobed modem_a firmware mount, a moved firmware path, a planted .ko, a removed or lengthened timer, removed or duplicated wlan-init markers, a bad envelope or tail and every repeated prior SHA including 2faab7e2, 995aaca3, be946562 and 86402ac6; host-only, not a boot result'
echo 'init_boot wlan-closure control: same stock baa33fd4 prefix and signed tail as the static-address control; ramdisk is one LZ4 HC-12 block of the debug cpio whose init is the frozen run-24 #53 init plus one wlan-init phase before console ready: it verifies /dev/block/sda6 (9,663,676,416 bytes) and the pinned super LP metadata and erofs first pages by SHA-256, mounts vendor_dlkm_a, vendor_a and system_dlkm_a read-only (erofs, ext4 ro,noload fallback) through read-only loop devices, then insmods the 21-module dependency-ordered stock WLAN closure (the 20-module vendor_dlkm closure of qcom_q6v5_pas, icnss2, qca_cld3_qca6750, cnss_plat_ipc_qmi_svc and qrtr-smd, plus rfkill.ko from system_dlkm) with a 2 s per-module timeout and per-module wlan-init result lines capped at 64, and logs wlan0 presence, an iw-dev availability check, dmesg lines matching icnss2/cnss_plat/qca_cld3/bdwlan capped at 64 and firmware load names capped at 64; the 127-module order, single peripheral write, 40x0.25s UDC wait, 150 s /run/keep timer, bin/restart2 helper, NCM+ECM functions and key-only sshd are unchanged and the debug cpio carries zero .ko; negative fixtures reject a wrong WLAN module order, a planted .ko, a removed mount, a writable mount flag, a removed or lengthened timer, a changed sshd, a changed address, a changed gadget function, a second role write, a changed old module order, removed or duplicated wlan-init markers, a bad envelope or tail and every repeated prior SHA including 995aaca3, be946562 and 86402ac6; host-only, not a boot result'
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
		boot-stock-full-footer.img boot-blank-tail.img boot-avb0-window-erase.img \
		boot-avbf-footer-erase.img init_boot-debug-ramdisk.img \
		init_boot-lz4-debug-ramdisk.img init_boot-vendor-modules.img \
		init_boot-self-recovering.img init_boot-eud-softdep.img \
		init_boot-peripheral-mode.img init_boot-static-address.img \
		init_boot-kernel-banner.img init_boot-initcall-debug.img \
		init_boot-wlan-closure.img init_boot-wlan-rfkill.img \
		boot-diagnostic-ext4.img boot-diagnostic-initcall-debug.img \
		Image-diagnostic-ext4.gz Image-diagnostic-initcall-debug.gz restart2 \
		boot-hash-boundary.img boot-image-size.img init_boot.img \
		vendor_boot.img dtb.img \
		Image.gz initramfs.cpio.gz Image)
	sha256sum "$STOCK_BOOT" "$STOCK_INIT" "$STOCK_VENDOR" "$STOCK_DTBO" \
		"$STOCK_VBMETA" "$STOCK_RECOVERY" "$STOCK_RECOVERY_B"
} | tee "$report"
