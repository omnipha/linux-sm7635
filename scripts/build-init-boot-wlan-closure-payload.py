import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


icd = load("build-init-boot-initcall-debug-payload.py", "initcall_debug_builder")
static = icd.static
eud = icd.eud
base = icd.base
modules = icd.modules
super = load("super-wlan-closure.py", "super_wlan_closure")
require = static.require
MEASURED_SHAS = (
    "be946562cfaa83efd1e573a019e1f88541f9618b0a3d675ba534677e2adb9403",
    "86402ac671b6bbc1f2e7c42b2e163c4804abe6349c577d319d182009b5046c65",
)
PRIOR_IMAGES = (*icd.PRIOR_IMAGES, *MEASURED_SHAS)
FROZEN_SOURCE = icd.FROZEN_SOURCE
FROZEN_SHA256 = icd.FROZEN_SHA256
STARTING = icd.STARTING
ANCHOR = b"log 'console ready'\n"
WLAN_BEGIN = b"log 'wlan-init: begin'\n"
WLAN_END = b"log 'wlan-init: end'\n"
DELTA_MSG = "init is not frozen #53 plus the single wlan-init phase"
FROZEN_MSG = "frozen #53 init is missing or already carries a wlan-init phase"
WLAN_MARKER_MSG = "the wlan-init phase markers are missing, duplicated or moved"
MOUNT_MSG = "the bounded read-only super logical-partition mounts are wrong"
MODULE_MSG = "the WLAN module loop or its 21-entry dependency-ordered closure list is wrong"
LOG_MSG = "the capped read-only wlan0/iw/dmesg/firmware-name logging is wrong"
SHA_MSG = static.SHA_MSG
TIMER_MSG = static.TIMER_MSG
LIST_MSG = static.LIST_MSG
KO_MSG = static.KO_MSG
ENVELOPE_MSG = static.ENVELOPE_MSG
WLAN_MODULES_LIST = (
    "qmi_helpers.ko", "qcom_ramdump.ko", "qcom_pil_info.ko", "qcom_glink.ko",
    "qcom_glink_smem.ko", "qcom_smd.ko", "rproc_qcom_common.ko", "pdr_interface.ko",
    "qcom_sysmon.ko", "qcom_q6v5.ko", "qcom_q6v5_pas.ko", "rfkill.ko", "cfg80211.ko",
    "qrtr-smd.ko", "cnss_plat_ipc_qmi_svc.ko", "wlan_firmware_service.ko",
    "cnss_nl.ko", "cnss_prealloc.ko", "icnss2.ko", "cnss_utils.ko",
    "qca_cld3_qca6750.ko",
)
WLAN_MODULES = "WLAN_MODULES='\n" + "".join(name + "\n" for name in WLAN_MODULES_LIST) + "'\n"
WLAN_BLOCK = """wlog() { printf 'wlan-init: %s\\n' "$*" >/dev/kmsg 2>/dev/null || true; }
wlan_hash() {
	HASH=$(/bin/busybox timeout -k 1 2 /bin/busybox dd if=/dev/block/sda6 bs=4096 skip="$1" count=1 status=none 2>/dev/null | /bin/busybox sha256sum)
	[ "${HASH%% *}" = "$2" ]
}
wlan_loop() {
	LOOPMAJOR=""
	if [ -r /sys/block/loop0/dev ]; then
		LOOPMAJOR=$(/bin/busybox cat /sys/block/loop0/dev)
		LOOPMAJOR=${LOOPMAJOR%%:*}
	fi
	[ -n "$LOOPMAJOR" ] || return 1
	[ -b "/dev/loop$2" ] || /bin/busybox mknod "/dev/loop$2" b "$LOOPMAJOR" "$2"
	/bin/busybox timeout -k 1 2 /bin/busybox losetup -r -o "$3" "/dev/loop$2" /dev/block/sda6 || return 1
	if /bin/busybox timeout -k 1 3 mount -t erofs -o ro,nosuid,nodev,noexec "/dev/loop$2" "$4"; then
		return 0
	fi
	if /bin/busybox timeout -k 1 3 mount -t ext4 -o ro,noload,nosuid,nodev,noexec "/dev/loop$2" "$4"; then
		return 0
	fi
	/bin/busybox losetup -d "/dev/loop$2"
	return 1
}
mkdir -p /dev/block /mnt/vendor_dlkm /mnt/vendor /mnt/system_dlkm
if [ ! -b /dev/block/sda6 ] && [ -r /sys/class/block/sda6/dev ]; then
	DEVNUM=$(/bin/busybox cat /sys/class/block/sda6/dev)
	/bin/busybox mknod /dev/block/sda6 b "${DEVNUM%%:*}" "${DEVNUM##*:}"
fi
if [ -b /dev/block/sda6 ] && SIZE=$(/bin/busybox timeout -k 1 2 /bin/busybox blockdev --getsize64 /dev/block/sda6 2>&1) && [ "$SIZE" = "9663676416" ]; then
	wlog "super size: $SIZE"
	if wlan_hash 1 a797e50acc7aed7027d6de98620698281edbe05974b2b81f58504a608a410bf8 && wlan_hash 3 a70e6c7a22115732c69f43b52284c7d4838a8ba0a03ca39158c69adef1143e95 && wlan_hash 1696256 76e2d1c59b70b3c6d914fcd65d5e1d8ee8dfb320ccee1cacd30a652e479edc66 && wlan_hash 1386240 5f728e99ec4375e552d51228cfe78087f9109388871a93925e92274307e984d5 && wlan_hash 1171200 e26c9d5abd6e8c60dc0475e4fc732970a5b379b5274fd48cf7320a563143e3ce; then
		wlog "super geometry and erofs first pages verified"
		if wlan_loop vendor_dlkm 8 6947864576 /mnt/vendor_dlkm; then
			wlog "mount vendor_dlkm_a read-only: ok"
		else
			wlog "mount vendor_dlkm_a read-only: failed"
		fi
		if wlan_loop vendor 9 5678039040 /mnt/vendor; then
			wlog "mount vendor_a read-only: ok"
		else
			wlog "mount vendor_a read-only: failed"
		fi
		if wlan_loop system_dlkm 10 4797235200 /mnt/system_dlkm; then
			wlog "mount system_dlkm_a read-only: ok"
		else
			wlog "mount system_dlkm_a read-only: failed"
		fi
	else
		wlog "super geometry or erofs first page mismatch; mounts skipped"
	fi
else
	wlog "super device /dev/block/sda6 unavailable or wrong size: ${SIZE:-absent}"
fi
wlog "module load begin"
wn=0
for module in $WLAN_MODULES; do
	NAME=${module%.ko}
	NAME=${NAME//-/_}
	if [ -d "/sys/module/$NAME" ]; then
		wlog "module $module loaded (already present)"
		wn=$((wn + 1))
		continue
	fi
	case "$module" in
	rfkill.ko)
		KOPATH=/mnt/system_dlkm/lib/modules/6.1.84-android14-11-gf4b0d69fdf34-ab12786779/kernel/net/rfkill/rfkill.ko ;;
	*)
		KOPATH=/mnt/vendor_dlkm/lib/modules/$module ;;
	esac
	if [ ! -r "$KOPATH" ]; then
		wlog "module $module failed: missing $KOPATH"
		wn=$((wn + 1))
		continue
	fi
	if err=$(/bin/busybox timeout -k 1 2 /bin/busybox insmod "$KOPATH" 2>&1); then
		wlog "module $module loaded"
	else
		err=$(/bin/busybox printf %s "$err" | /bin/busybox head -c 160)
		wlog "module $module failed: $err"
	fi
	wn=$((wn + 1))
	[ "$wn" -lt 64 ] || break
done
wlog "module load end (modules logged: $wn, cap 64)"
if [ -d /sys/class/net/wlan0 ]; then
	wlog "wlan0 present"
	IW=""
	if /bin/busybox --list 2>/dev/null | /bin/busybox grep -qx iw; then
		IW="/bin/busybox iw"
	elif command -v iw >/dev/null 2>&1; then
		IW=iw
	fi
	if [ -n "$IW" ]; then
		wlog "iw dev available: $IW"
		$IW dev 2>&1 | {
			iwn=0
			while IFS= read -r line; do
				if [ "$iwn" -lt 16 ]; then
					line=$(/bin/busybox printf %s "$line" | /bin/busybox head -c 160)
					wlog "iw dev: $line"
					iwn=$((iwn + 1))
				fi
			done
			wlog "iw dev lines logged: $iwn (cap 16)"
		}
	else
		wlog "iw dev not available"
	fi
else
	wlog "wlan0 absent"
fi
QUOTE="'"
/bin/busybox timeout -k 1 3 /bin/busybox dmesg 2>&1 | {
	dn=0
	fn=0
	while IFS= read -r line; do
		case "$line" in
		*icnss2*|*cnss_plat*|*qca_cld3*|*bdwlan*)
			if [ "$dn" -lt 64 ]; then
				snippet=$(/bin/busybox printf %s "$line" | /bin/busybox head -c 240)
				wlog "wlan dmesg: $snippet"
				dn=$((dn + 1))
			fi ;;
		esac
		case "$line" in
		*"firmware: loading "*|*"Direct firmware load for "*|*"Falling back to sysfs fallback for: "*|*"failed to load "*)
			name=
			case "$line" in
			*"firmware: loading "*)
				name=${line#*firmware: loading }
				name=${name#"$QUOTE"}
				name=${name%%"$QUOTE"*} ;;
			*"Direct firmware load for "*)
				name=${line#*Direct firmware load for }
				name=${name%% *} ;;
			*"failed to load "*)
				name=${line#*failed to load }
				name=${name%% *} ;;
			*)
				name=${line#*Falling back to sysfs fallback for: }
				name=${name%% *} ;;
			esac
			case "$name" in
			""|/*|*[!A-Za-z0-9_./-]*) ;;
			*)
				if [ "$fn" -lt 64 ]; then
					wlog "firmware name: $name"
					fn=$((fn + 1))
				fi ;;
			esac ;;
		esac
	done
	wlog "wlan dmesg lines logged: $dn (cap 64)"
	wlog "firmware names logged: $fn (cap 64)"
}
"""
DELTA = WLAN_BEGIN + WLAN_MODULES.encode() + WLAN_BLOCK.encode() + WLAN_END


def require_frozen(frozen, order):
    require(modules.sha256(frozen) == FROZEN_SHA256, FROZEN_MSG)
    require(b"wlan-init" not in frozen and b"vendor_dlkm" not in frozen and
            b"qca_cld3" not in frozen and b"insmod \"$KOPATH\"" not in frozen, FROZEN_MSG)
    static.check_init(frozen, order)
    return frozen


def frozen_init(order):
    return require_frozen((HERE.parent / "initramfs" / FROZEN_SOURCE).read_bytes(), order)


def expected_init(frozen):
    require(frozen.count(ANCHOR) == 1 and frozen.count(DELTA) == 0, DELTA_MSG)
    return frozen.replace(ANCHOR, DELTA + ANCHOR, 1)


def check_wlan(init):
    require(init.count(WLAN_BEGIN) == 1 and init.count(WLAN_END) == 1, WLAN_MARKER_MSG)
    begin = init.index(WLAN_BEGIN)
    require(init.index(WLAN_END) > begin and init.index(WLAN_END) < init.index(ANCHOR) and
            begin < init.index(ANCHOR), WLAN_MARKER_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 3 mount -t erofs -o ro,nosuid,nodev,noexec") == 1, MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 3 mount -t ext4 -o ro,noload,nosuid,nodev,noexec") == 1, MOUNT_MSG)
    for bad in (b"mount -o rw", b",rw", b"remount", b"mount -w"):
        require(bad not in init, MOUNT_MSG)
    for offset in (b"6947864576", b"5678039040", b"4797235200"):
        require(init.count(offset) == 1, MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox losetup -r -o \"$3\"") == 1, MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox blockdev --getsize64 /dev/block/sda6") == 1 and
            init.count(b'[ "$SIZE" = "9663676416" ]') == 1, MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox dd if=/dev/block/sda6 bs=4096 skip=") == 1, MOUNT_MSG)
    for digest in (super.GEOMETRY_PAGE_SHA256.encode(), super.METADATA_PAGE_SHA256.encode(),
                   super.ERAFS_PAGE_SHA256[super.VENDOR_DLKM].encode(),
                   super.ERAFS_PAGE_SHA256[super.VENDOR].encode(),
                   super.ERAFS_PAGE_SHA256[super.SYSTEM_DLKM].encode()):
        require(init.count(digest) == 1, MOUNT_MSG)
    require(init.count(WLAN_MODULES.encode()) == 1, MODULE_MSG)
    require(len(WLAN_MODULES_LIST) == super.CLOSURE_SIZE + 1 and
            tuple(name for name in WLAN_MODULES_LIST if name != "rfkill.ko") == super.WLAN_ORDER,
            MODULE_MSG)
    require(init.count(b'wlog "module $module loaded"') == 1 and
            init.count(b'wlog "module $module failed: $err"') == 1 and
            init.count(b'wlog "module $module failed: missing $KOPATH"') == 1 and
            init.count(b'wlog "module $module loaded (already present)"') == 1, MODULE_MSG)
    require(init.count(b'/bin/busybox insmod "$KOPATH"') == 1 and
            init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox insmod") == 1, MODULE_MSG)
    require(init.index(b"rfkill.ko)") < init.index(b"*)\n\t\tKOPATH=/mnt/vendor_dlkm/lib/modules/$module"),
            MODULE_MSG)
    position = {name: index for index, name in enumerate(WLAN_MODULES_LIST)}
    require(position["qca_cld3_qca6750.ko"] == 20 and position["icnss2.ko"] == 18 and
            position["qcom_q6v5_pas.ko"] < position["icnss2.ko"] and
            position["icnss2.ko"] < position["qca_cld3_qca6750.ko"] and
            position["cfg80211.ko"] < position["qca_cld3_qca6750.ko"] and
            position["rfkill.ko"] < position["cfg80211.ko"], MODULE_MSG)
    require(init.count(b'[ -d /sys/class/net/wlan0 ]') == 1 and
            init.count(b"iw dev not available") == 1 and
            init.count(b'wlog "iw dev available: $IW"') == 1 and
            init.count(b'wlog "iw dev lines logged: $iwn (cap 16)"') == 1, LOG_MSG)
    require(init.count(b'wlog "wlan dmesg lines logged: $dn (cap 64)"') == 1 and
            init.count(b'wlog "firmware names logged: $fn (cap 64)"') == 1, LOG_MSG)
    require(init.count(b"*icnss2*|*cnss_plat*|*qca_cld3*|*bdwlan*") == 1 and
            init.count(b'wlog "firmware name: $name"') == 1, LOG_MSG)
    return begin


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    offset = check_wlan(init)
    frozen = frozen_init(order)
    stripped = init.replace(DELTA, b"", 1)
    static.check_timer(stripped)
    require(stripped.count(static.SSHD) == 1, static.SSHD_MSG)
    static.check_init(stripped, order)
    require(stripped == frozen and init == expected_init(frozen), DELTA_MSG)
    return offset


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order):
    return eud.candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                              init_check=check_init)


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, ENVELOPE_MSG)
    image, digest = static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 10, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER")
    stock, source, boot, vendor_boot, recovery, config, kernel, decompressor, pstore, helper = (
        pathlib.Path(path).read_bytes() for path in paths)
    library = base.lz4()
    vendor_files, recovery_entries = eud.vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, LIST_MSG)
    eud.vendor.check_stock(stock, library)
    init = expected_init(frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-wlan-closure-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print(f"wlan-init phase: verified sda6 geometry, 3 read-only erofs mounts "
          f"(vendor_dlkm_a {super.VENDOR_DLKM_OFFSET}, vendor_a {super.VENDOR_OFFSET}, "
          f"system_dlkm_a {super.SYSTEM_DLKM_OFFSET}), {len(WLAN_MODULES_LIST)}-module "
          f"dependency-ordered insmod loop, capped wlan0/iw/dmesg/firmware-name logging")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper {eud.HELPER_SIZE} "
          f"bytes, SHA-256 {eud.HELPER_SHA256[:8]}")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
