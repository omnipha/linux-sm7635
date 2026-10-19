#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
BUSYBOX_DEB=${BUSYBOX_DEB:-$WORK/busybox-static_1.37.0-7ubuntu1_arm64.deb}
BUSYBOX_URL=https://ports.ubuntu.com/ubuntu-ports/pool/main/b/busybox/busybox-static_1.37.0-7ubuntu1_arm64.deb
BUSYBOX_SHA256=fcf50794faf920455895d7ef103d1c54b9ebf7f18d2e52982dbf3903b7769592

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }

for tool in mkbootimg python3 cpio gzip sha256sum dpkg-deb curl file fakeroot; do
	need "$tool"
done
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "build artifacts must stay outside this repository" ;;
esac
[ -s "$OUT/Image" ] || die "missing $OUT/Image; run scripts/build-baseline.sh"
[ -f "$OUT/.config" ] || die "missing $OUT/.config"
for option in CONFIG_USB_GADGET CONFIG_CONFIGFS_FS CONFIG_USB_CONFIGFS \
	CONFIG_USB_CONFIGFS_NCM CONFIG_USB_F_NCM CONFIG_USB_CONFIGFS_ECM \
	CONFIG_USB_F_ECM CONFIG_USB_CONFIGFS_ACM CONFIG_USB_DWC3_QCOM \
	CONFIG_BLK_DEV_INITRD CONFIG_RD_GZIP; do
	grep -qx "$option=y" "$OUT/.config" || die "baseline kernel requires $option=y"
done
[ -f "$ROOT/initramfs/init" ] || die "missing initramfs/init"

mkdir -p "$WORK"
if [ ! -f "$BUSYBOX_DEB" ]; then
	curl -fL --retry 3 --retry-delay 2 -o "$BUSYBOX_DEB" "$BUSYBOX_URL"
fi
printf '%s  %s\n' "$BUSYBOX_SHA256" "$BUSYBOX_DEB" | sha256sum -c -

stage=$(mktemp -d "$WORK/bootimg-stage.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/package" "$stage/root/bin" "$stage/root/sbin" \
	"$stage/root/dev/pts" "$stage/root/proc" \
	"$stage/root/sys/kernel/config" "$stage/root/run" \
	"$stage/root/etc" "$stage/root/root" "$stage/root/tmp"
chmod 0755 "$stage/root" "$stage/root"/* "$stage/root/dev/pts" \
	"$stage/root/sys/kernel" "$stage/root/sys/kernel/config"
chmod 1777 "$stage/root/tmp"
dpkg-deb -x "$BUSYBOX_DEB" "$stage/package"
busybox=$stage/package/usr/bin/busybox
[ -f "$busybox" ] || die "busybox binary missing from package"
file "$busybox" | grep -q 'ARM aarch64' || die "busybox is not arm64"
file "$busybox" | grep -q 'statically linked' || die "busybox is not static"
install -m 0755 "$busybox" "$stage/root/bin/busybox"
install -m 0755 "$ROOT/initramfs/init" "$stage/root/init"
for applet in sh ip sleep mount mkdir mknod ln hostname setsid cttyhack; do
	ln -s busybox "$stage/root/bin/$applet"
done
ln -s ../bin/busybox "$stage/root/sbin/init"

cat >"$stage/archive.sh" <<'SCRIPT'
set -eu
root=$1
mknod "$root/dev/console" c 5 1
mknod "$root/dev/null" c 1 3
mknod "$root/dev/kmsg" c 1 11
mknod "$root/dev/ptmx" c 5 2
cd "$root"
find . -exec touch -h -d '@0' {} +
find . -print0 | LC_ALL=C sort -z | cpio --null -o -H newc --reproducible --owner=0:0 --quiet
SCRIPT
chmod 0755 "$stage/archive.sh"
fakeroot -- bash "$stage/archive.sh" "$stage/root" >"$stage/initramfs.cpio"
gzip -n -9 -c "$stage/initramfs.cpio" >"$OUT/initramfs.cpio.gz"
gzip -n -9 -c "$OUT/Image" >"$OUT/Image.gz"

mkbootimg --header_version 4 --pagesize 4096 \
	--base 0x00000000 --kernel_offset 0x00008000 \
	--ramdisk_offset 0x01000000 --tags_offset 0x00000100 \
	--dtb_offset 0x0000000001f00000 \
	--os_version 0.0.0 --os_patch_level 0 \
	--kernel "$OUT/Image.gz" --ramdisk "$OUT/initramfs.cpio.gz" \
	--cmdline '' --output "$OUT/boot.img"

python3 - "$OUT/boot.img" "$OUT/Image.gz" "$OUT/initramfs.cpio.gz" <<'PY'
import pathlib
import struct
import sys

boot, kernel, ramdisk = (pathlib.Path(p).read_bytes() for p in sys.argv[1:])
if boot[:8] != b"ANDROID!" or struct.unpack_from("<I", boot, 40)[0] != 4:
    raise SystemExit("boot header is not v4")
if struct.unpack_from("<I", boot, 20)[0] != 1584:
    raise SystemExit("boot header size is not 1584")
if struct.unpack_from("<II", boot, 8) != (len(kernel), len(ramdisk)):
    raise SystemExit("kernel/ramdisk sizes do not match")
page = 4096
start = page
if boot[start:start + len(kernel)] != kernel:
    raise SystemExit("kernel payload does not match")
start += (len(kernel) + page - 1) // page * page
if boot[start:start + len(ramdisk)] != ramdisk:
    raise SystemExit("ramdisk payload does not match")
PY

(
	cd "$OUT"
	sha256sum boot.img Image.gz initramfs.cpio.gz Image
) | tee "$OUT/bootimg-sha256.txt"
