#!/usr/bin/env bash
set -euo pipefail

WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
STOCK_VENDOR=${STOCK_VENDOR:-$HOME/phone-second-life-data/mb003/parts/vendor_boot_a.img}
BUSYBOX_DEB=${BUSYBOX_DEB:-$WORK/busybox-static_1.37.0-7ubuntu1_arm64.deb}
BUSYBOX_URL=https://ports.ubuntu.com/ubuntu-ports/pool/main/b/busybox/busybox-static_1.37.0-7ubuntu1_arm64.deb
BUSYBOX_SHA256=fcf50794faf920455895d7ef103d1c54b9ebf7f18d2e52982dbf3903b7769592
DROPBEAR_TARBALL=${DROPBEAR_TARBALL:-$WORK/dropbear-2026.94.tar.bz2}
DROPBEAR_URL=https://matt.ucc.asn.au/dropbear/releases/dropbear-2026.94.tar.bz2
DROPBEAR_SHA256=e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81
PUBKEY=${PUBKEY:-$HOME/.ssh/id_ed25519.pub}

umask 077

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }

for tool in mkbootimg python3 cpio gzip sha256sum dpkg-deb curl file fakeroot dtc \
	tar make aarch64-linux-gnu-gcc; do
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
	CONFIG_USB_DWC3_MSM CONFIG_USB_MSM_EUSB2_PHY CONFIG_USB_MSM_SSPHY_QMP \
	CONFIG_USB_REPEATER CONFIG_QTI_PMIC_EUSB2_REPEATER CONFIG_QCOM_EUD \
	CONFIG_COMMON_CLK_QCOM CONFIG_SM_GCC_VOLCANO CONFIG_QCOM_CLK_RPMH \
	CONFIG_QCOM_GDSC_REGULATOR CONFIG_QCOM_COMMAND_DB CONFIG_QCOM_RPMH \
	CONFIG_REGULATOR_RPMH CONFIG_INTERCONNECT_QCOM_VOLCANO \
	CONFIG_SPMI_MSM_PMIC_ARB CONFIG_MFD_SPMI_PMIC CONFIG_PINCTRL_VOLCANO \
	CONFIG_QCOM_PDC CONFIG_ARM_SMMU CONFIG_ARM_SMMU_QCOM \
	CONFIG_QTI_PMIC_GLINK CONFIG_UCSI_QTI_GLINK \
	CONFIG_BLK_DEV_INITRD CONFIG_RD_GZIP CONFIG_PSTORE CONFIG_PSTORE_RAM \
	CONFIG_PSTORE_CONSOLE CONFIG_SERIAL_EARLYCON CONFIG_SERIAL_QCOM_GENI; do
	grep -qx "$option=y" "$OUT/.config" || die "baseline kernel requires $option=y"
done
python3 "$ROOT/scripts/verify-volcano-usb.py" config \
	"$OUT/.config" "$ROOT/configs/asteroids-volcano-usb-builtin.fragment"
[ -f "$ROOT/initramfs/init" ] || die "missing initramfs/init"
for base in volcano volcano6 volcano6i-fp1 volcano6i-fp2 volcano6i-fp3 \
	volcano6i-fp4 volcano6p volcano6ip-fp1 volcano6ip-fp2 volcano6ip-fp3 \
	volcano6ip-fp4; do
	[ -s "$OUT/$base.dtb" ] || die "missing $OUT/$base.dtb; rebuild the baseline"
done
[ -f "$STOCK_VENDOR" ] ||
	die "missing stock vendor_boot reference: $STOCK_VENDOR"
read -r vendor_sha _ < <(sha256sum "$STOCK_VENDOR")
[ "$vendor_sha" = 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253 ] ||
	die 'stock vendor_boot is not the verified slot-A baseline'

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
	"$stage/root/etc" "$stage/root/root" "$stage/root/tmp" \
	"$stage/root/usr/share/doc/dropbear"
chmod 0755 "$stage/root" "$stage/root"/* "$stage/root/dev/pts" \
	"$stage/root/sys/kernel" "$stage/root/sys/kernel/config" \
	"$stage/root/usr" "$stage/root/usr/share" \
	"$stage/root/usr/share/doc" "$stage/root/usr/share/doc/dropbear"
chmod 0700 "$stage/root/root"
chmod 1777 "$stage/root/tmp"
dpkg-deb -x "$BUSYBOX_DEB" "$stage/package"
busybox=$stage/package/usr/bin/busybox
[ -f "$busybox" ] || die "busybox binary missing from package"
file "$busybox" | grep -q 'ARM aarch64' || die "busybox is not arm64"
file "$busybox" | grep -q 'statically linked' || die "busybox is not static"
install -m 0755 "$busybox" "$stage/root/bin/busybox"

[ -s "$PUBKEY" ] || die "missing public key file: $PUBKEY (set PUBKEY=<path>)"
python3 - "$PUBKEY" "$stage/root/root/.ssh/authorized_keys" <<'PY'
import base64
import pathlib
import sys

key = pathlib.Path(sys.argv[1]).read_text()
fields = key.strip().split()
if len(fields) not in (2, 3) or fields[0] != "ssh-ed25519":
    raise SystemExit("expected exactly one ssh-ed25519 public key")
try:
    data = base64.b64decode(fields[1], validate=True)
except ValueError as exc:
    raise SystemExit("invalid public key encoding") from exc
if not data.startswith(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20") or len(data) != 51:
    raise SystemExit("invalid ed25519 public key data")
path = pathlib.Path(sys.argv[2])
path.parent.mkdir(mode=0o700)
path.write_text(" ".join(fields[:2]) + "\n")
path.chmod(0o600)
PY

if [ ! -f "$DROPBEAR_TARBALL" ]; then
	curl -fL --retry 3 --retry-delay 2 -o "$DROPBEAR_TARBALL" "$DROPBEAR_URL"
fi
printf '%s  %s\n' "$DROPBEAR_SHA256" "$DROPBEAR_TARBALL" | sha256sum -c -
dropbear_build=$(mktemp -d "$WORK/dropbear-build.XXXXXXXX")
trap 'rm -rf "$stage" "$dropbear_build"' EXIT
(
	cd "$dropbear_build"
	tar -xjf "$DROPBEAR_TARBALL" --strip-components=1
	cat >localoptions.h <<'OPTIONS'
#define DROPBEAR_SVR_PASSWORD_AUTH 0
#define DROPBEAR_SVR_PAM_AUTH 0
#define DROPBEAR_SVR_LOCALTCPFWD 0
#define DROPBEAR_SVR_REMOTETCPFWD 0
#define DROPBEAR_DSS 0
#define DO_MOTD 0
OPTIONS
	CC=aarch64-linux-gnu-gcc ./configure --host=aarch64-linux-gnu \
		--enable-static --disable-zlib --disable-syslog \
		--disable-lastlog --disable-wtmp --disable-utmp \
		--disable-pututline --disable-pututxline >/dev/null
	make -j "${JOBS:-2}" PROGRAMS=dropbear >/dev/null
)
dropbear_bin=$dropbear_build/dropbear
[ -x "$dropbear_bin" ] || die "dropbear build produced no binary"
file "$dropbear_bin" | grep -q 'ARM aarch64' || die "dropbear is not arm64"
file "$dropbear_bin" | grep -q 'statically linked' || die "dropbear is not static"
if command -v qemu-aarch64 >/dev/null 2>&1; then
	qemu-aarch64 "$dropbear_bin" -V 2>&1 | grep -q 'v2026.94' ||
		die "built dropbear does not report v2026.94 under qemu-aarch64"
else
	echo 'note: qemu-aarch64 not found; skipping dropbear version smoke test' >&2
fi
install -m 0755 "$dropbear_bin" "$stage/root/bin/dropbear"
install -m 0644 "$dropbear_build/LICENSE" "$stage/root/usr/share/doc/dropbear/LICENSE"
install -m 0644 "$dropbear_build/libtomcrypt/LICENSE" \
	"$stage/root/usr/share/doc/dropbear/LibTomCrypt-LICENSE"
install -m 0644 "$dropbear_build/libtommath/LICENSE" \
	"$stage/root/usr/share/doc/dropbear/LibTomMath-LICENSE"

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

python3 - "$STOCK_VENDOR" "$OUT/dtb.img" <<'PY'
import pathlib
import struct
import sys

stock_vendor = pathlib.Path(sys.argv[1]).read_bytes()


def split_dtbs(blob):
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
    return found


page = 4096
stock_ramdisk_size = struct.unpack_from("<I", stock_vendor, 24)[0]
stock_dtb_size = struct.unpack_from("<I", stock_vendor, 2100)[0]
stock_dtb_offset = page + (stock_ramdisk_size + page - 1) // page * page
stock_blob = stock_vendor[stock_dtb_offset:stock_dtb_offset + stock_dtb_size]
if len(stock_blob) != stock_dtb_size:
    raise SystemExit("stock vendor DTB blob is truncated")
stock_list = split_dtbs(stock_blob)
if len(stock_list) != 20 or b"Volcano SoC" not in stock_list[9]:
    raise SystemExit("stock vendor DTB layout is unexpected")
pathlib.Path(sys.argv[2]).write_bytes(stock_blob)
PY

printf '%s\n' \
	'androidboot.hardware=qcom' \
	'androidboot.memcg=1' \
	'androidboot.usbcontroller=a600000.dwc3' \
	'androidboot.load_modules_parallel=true' \
	'androidboot.vendor.qspa=true' \
	'androidboot.console=0' >"$stage/bootconfig"

BOOT_CMDLINE='console=ttynull stack_depot_disable=on cgroup_disable=pressure kasan.page_alloc.sample=10 kasan.stacktrace=off kvm-arm.mode=protected bootconfig ioremap_guard loglevel=6'
VENDOR_CMDLINE='earlycon keep_bootcon loglevel=8 log_buf_len=1M ignore_loglevel printk.devkmsg=on panic=-1 bootconfig'

mkbootimg --header_version 4 --pagesize 4096 \
	--base 0x00000000 --kernel_offset 0x00008000 \
	--ramdisk_offset 0x01000000 --tags_offset 0x00000100 \
	--dtb_offset 0x0000000001f00000 \
	--os_version 0.0.0 --os_patch_level 0 \
	--kernel "$OUT/Image.gz" \
	--cmdline "$BOOT_CMDLINE" \
	--dtb "$OUT/dtb.img" \
	--vendor_cmdline "$VENDOR_CMDLINE" \
	--vendor_ramdisk "$OUT/initramfs.cpio.gz" \
	--vendor_bootconfig "$stage/bootconfig" \
	--output "$OUT/boot.img" --vendor_boot "$OUT/vendor_boot.img"

: >"$stage/empty-kernel"
mkbootimg --header_version 4 --pagesize 4096 \
	--base 0x00000000 --kernel_offset 0x00008000 \
	--ramdisk_offset 0x01000000 --tags_offset 0x00000100 \
	--dtb_offset 0x0000000001f00000 \
	--os_version 0.0.0 --os_patch_level 0 \
	--kernel "$stage/empty-kernel" --ramdisk "$OUT/initramfs.cpio.gz" \
	--cmdline '' --output "$OUT/init_boot.img"

python3 - "$OUT/boot.img" "$OUT/vendor_boot.img" "$OUT/init_boot.img" \
	"$OUT/Image.gz" "$OUT/initramfs.cpio.gz" "$OUT/dtb.img" <<'PY'
import pathlib
import struct
import sys

boot, vendor, init_boot, kernel, ramdisk, dtb = (
    pathlib.Path(path).read_bytes() for path in sys.argv[1:])
if boot[:8] != b"ANDROID!" or struct.unpack_from("<I", boot, 40)[0] != 4:
    raise SystemExit("boot header is not v4")
if struct.unpack_from("<I", boot, 20)[0] != 1584:
    raise SystemExit("boot header size is not 1584")
if struct.unpack_from("<II", boot, 8) != (len(kernel), 0):
    raise SystemExit("boot kernel size or empty generic ramdisk mismatch")
page = 4096
start = page
if boot[start:start + len(kernel)] != kernel:
    raise SystemExit("kernel payload does not match")
start += (len(kernel) + page - 1) // page * page
if len(boot) != start or any(boot[page + len(kernel):start]):
    raise SystemExit("boot has data after the kernel")
if vendor[:8] != b"VNDRBOOT" or struct.unpack_from("<I", vendor, 8)[0] != 4:
    raise SystemExit("vendor boot header is not v4")
if struct.unpack_from("<III", vendor, 12) != (page, 0x8000, 0x1000000):
    raise SystemExit("vendor boot geometry does not match stock")
if struct.unpack_from("<I", vendor, 24)[0] != len(ramdisk):
    raise SystemExit("vendor ramdisk size does not match")
if struct.unpack_from("<Q", vendor, 2104)[0] != 0x1F00000:
    raise SystemExit("vendor DTB load address is not 0x1f00000")
if struct.unpack_from("<I", vendor, 2100)[0] != len(dtb):
    raise SystemExit("vendor DTB size does not match")
dtb_offset = page + (len(ramdisk) + page - 1) // page * page
if vendor[dtb_offset:dtb_offset + len(dtb)] != dtb:
    raise SystemExit("vendor DTB payload does not match")
cmdline = vendor[28:2076].split(b"\x00", 1)[0]
if b"earlycon" not in cmdline or b"panic=-1" not in cmdline:
    raise SystemExit("vendor command line is missing diagnosis options")
if init_boot[:8] != b"ANDROID!" or struct.unpack_from("<I", init_boot, 40)[0] != 4:
    raise SystemExit("init_boot header is not v4")
if struct.unpack_from("<I", init_boot, 8)[0] != 0:
    raise SystemExit("init_boot kernel is not empty")
if struct.unpack_from("<I", init_boot, 12)[0] != len(ramdisk):
    raise SystemExit("init_boot ramdisk size does not match")
PY

(
	cd "$OUT"
	sha256sum boot.img init_boot.img vendor_boot.img dtb.img Image.gz \
		initramfs.cpio.gz Image
) | tee "$OUT/bootimg-sha256.txt"
