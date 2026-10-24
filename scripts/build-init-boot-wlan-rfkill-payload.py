import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


old = load("build-init-boot-wlan-closure-payload.py", "wlan_closure_builder")
super = old.super
base = old.base
eud = old.eud
modules = old.modules
static = old.static
require = old.require
MEASURED_WLAN = "2faab7e2d4069d5f908e292d0a5d17e0be86a09ce91efc9e6aececfb0c6872bf"
PRIOR_IMAGES = (*old.PRIOR_IMAGES, MEASURED_WLAN)
FROZEN_SOURCE = old.FROZEN_SOURCE
FROZEN_SHA256 = old.FROZEN_SHA256
WLAN_BEGIN = old.WLAN_BEGIN
WLAN_END = old.WLAN_END
ANCHOR = old.ANCHOR
DELTA_MSG = "init is not frozen #53 plus the single corrected wlan-init phase"
FROZEN_MSG = old.FROZEN_MSG
WLAN_MARKER_MSG = old.WLAN_MARKER_MSG
MOUNT_MSG = "the probed read-only super extent mounts and loop-node derivation are wrong"
MODULE_MSG = "the rfkill provider, its position before cfg80211 or the closure list is wrong"
FIRMWARE_MSG = "the probed read-only modem_a firmware mount or its stock path is wrong"
LOG_MSG = old.LOG_MSG
SHA_MSG = old.SHA_MSG
TIMER_MSG = old.TIMER_MSG
LIST_MSG = old.LIST_MSG
KO_MSG = old.KO_MSG
ENVELOPE_MSG = old.ENVELOPE_MSG

LOOP_OLD = '''\tLOOPMAJOR=""
\tif [ -r /sys/block/loop0/dev ]; then
\t\tLOOPMAJOR=$(/bin/busybox cat /sys/block/loop0/dev)
\t\tLOOPMAJOR=${LOOPMAJOR%%:*}
\tfi
\t[ -n "$LOOPMAJOR" ] || return 1
\t[ -b "/dev/loop$2" ] || /bin/busybox mknod "/dev/loop$2" b "$LOOPMAJOR" "$2"
\t/bin/busybox timeout -k 1 2 /bin/busybox losetup -r -o "$3" "/dev/loop$2" /dev/block/sda6 || return 1
\tif /bin/busybox timeout -k 1 3 mount -t erofs -o ro,nosuid,nodev,noexec "/dev/loop$2" "$4"; then
\t\treturn 0
\tfi
\tif /bin/busybox timeout -k 1 3 mount -t ext4 -o ro,noload,nosuid,nodev,noexec "/dev/loop$2" "$4"; then
\t\treturn 0
\tfi
\t/bin/busybox losetup -d "/dev/loop$2"
\treturn 1
'''
LOOP_NEW = '''\tLOOPNODE="/dev/wlan-loop$2"
\t[ -r "/sys/block/loop$2/dev" ] && [ ! -e "$LOOPNODE" ] || return 1
\tLOOPNUM=$(/bin/busybox cat "/sys/block/loop$2/dev")
\tcase "$LOOPNUM" in
\t[0-9]*:[0-9]*)
\t\t/bin/busybox mknod "$LOOPNODE" b "${LOOPNUM%%:*}" "${LOOPNUM##*:}" || return 1 ;;
\t*)
\t\treturn 1 ;;
\tesac
\t/bin/busybox timeout -k 1 2 /bin/busybox losetup -r -o "$3" "$LOOPNODE" /dev/block/sda6 || return 1
\tFS_MAGIC=$(/bin/busybox timeout -k 1 2 /bin/busybox hexdump -n 4 -s 1024 -e '4/1 "%02x"' "$LOOPNODE" 2>/dev/null)
\tcase "$FS_MAGIC" in
\te2e1f5e0)
\t\tFSTYPE=erofs
\t\tFSOPTS=ro,nosuid,nodev,noexec ;;
\t*)
\t\tFS_MAGIC=$(/bin/busybox timeout -k 1 2 /bin/busybox hexdump -n 2 -s 1080 -e '2/1 "%02x"' "$LOOPNODE" 2>/dev/null)
\t\tif [ "$FS_MAGIC" != "53ef" ]; then
\t\t\t/bin/busybox losetup -d "$LOOPNODE"
\t\t\treturn 1
\t\tfi
\t\tFSTYPE=ext4
\t\tFSOPTS=ro,noload,nosuid,nodev,noexec ;;
\tesac
\tif /bin/busybox timeout -k 1 3 mount -t "$FSTYPE" -o "$FSOPTS" "$LOOPNODE" "$4"; then
\t\twlog "mount $1 fstype: $FSTYPE"
\t\treturn 0
\tfi
\t/bin/busybox losetup -d "$LOOPNODE"
\treturn 1
'''
MOUNTS_OLD = '''\t\tif wlan_loop vendor_dlkm 8 6947864576 /mnt/vendor_dlkm; then
\t\t\twlog "mount vendor_dlkm_a read-only: ok"
\t\telse
\t\t\twlog "mount vendor_dlkm_a read-only: failed"
\t\tfi
\t\tif wlan_loop vendor 9 5678039040 /mnt/vendor; then
\t\t\twlog "mount vendor_a read-only: ok"
\t\telse
\t\t\twlog "mount vendor_a read-only: failed"
\t\tfi
\t\tif wlan_loop system_dlkm 10 4797235200 /mnt/system_dlkm; then
\t\t\twlog "mount system_dlkm_a read-only: ok"
\t\telse
\t\t\twlog "mount system_dlkm_a read-only: failed"
\t\tfi
'''
MOUNTS_NEW = '''\t\tif wlan_loop system_dlkm_a 10 4797235200 /mnt/system_dlkm; then
\t\t\twlog "mount system_dlkm_a read-only: ok"
\t\telse
\t\t\twlog "mount system_dlkm_a read-only: failed"
\t\tfi
\t\tif wlan_loop vendor_a 9 5678039040 /mnt/vendor; then
\t\t\twlog "mount vendor_a read-only: ok"
\t\telse
\t\t\twlog "mount vendor_a read-only: failed"
\t\tfi
\t\tif wlan_loop vendor_dlkm_a 8 6947864576 /mnt/vendor_dlkm; then
\t\t\twlog "mount vendor_dlkm_a read-only: ok"
\t\telse
\t\t\twlog "mount vendor_dlkm_a read-only: failed"
\t\tfi
'''
FIRMWARE_ANCHOR = 'wlog "module load begin"\n'
FIRMWARE_BLOCK = '''mkdir -p /vendor/firmware_mnt
if [ -r /sys/class/block/sde6/uevent ] && /bin/busybox grep -qx 'PARTNAME=modem_a' /sys/class/block/sde6/uevent && [ -r /sys/class/block/sde6/dev ]; then
\tif [ ! -b /dev/block/sde6 ]; then
\t\tDEVNUM=$(/bin/busybox cat /sys/class/block/sde6/dev)
\t\t/bin/busybox mknod /dev/block/sde6 b "${DEVNUM%%:*}" "${DEVNUM##*:}"
\tfi
\tFAT_OK=0
\tif [ -b /dev/block/sde6 ]; then
\t\tFAT_MAGIC=$(/bin/busybox timeout -k 1 2 /bin/busybox hexdump -n 8 -s 82 -e '8/1 "%02x"' /dev/block/sde6 2>/dev/null)
\t\tcase "$FAT_MAGIC" in
\t\t4641543332202020)
\t\t\tFAT_OK=1 ;;
\t\t*)
\t\t\tFAT_MAGIC=$(/bin/busybox timeout -k 1 2 /bin/busybox hexdump -n 5 -s 54 -e '5/1 "%02x"' /dev/block/sde6 2>/dev/null)
\t\t\tcase "$FAT_MAGIC" in
\t\t\t4641543132|4641543136)
\t\t\t\tFAT_OK=1 ;;
\t\t\tesac ;;
\t\tesac
\tfi
\tif [ "$FAT_OK" -eq 1 ] && /bin/busybox timeout -k 1 3 mount -t vfat -o ro,nosuid,nodev,noexec /dev/block/sde6 /vendor/firmware_mnt; then
\t\twlog "mount modem_a read-only vfat at /vendor/firmware_mnt: ok"
\telse
\t\twlog "mount modem_a read-only vfat at /vendor/firmware_mnt: failed"
\tfi
else
\twlog "mount modem_a read-only vfat at /vendor/firmware_mnt: failed"
fi
if [ -d /mnt/vendor/firmware_mnt ]; then
\twlog "vendor_a firmware_mnt mountpoint: present"
else
\twlog "vendor_a firmware_mnt mountpoint: absent"
fi
if [ -r /vendor/firmware_mnt/image/qca6750/bdwlan.elf ]; then
\twlog "firmware qca6750/bdwlan.elf: present"
else
\twlog "firmware qca6750/bdwlan.elf: absent"
fi
'''


def replace_one(text, before, after):
    require(text.count(before) == 1 and text.count(after) == 0, DELTA_MSG)
    return text.replace(before, after, 1)


WLAN_BLOCK = replace_one(old.WLAN_BLOCK, LOOP_OLD, LOOP_NEW)
WLAN_BLOCK = replace_one(WLAN_BLOCK, MOUNTS_OLD, MOUNTS_NEW)
WLAN_BLOCK = replace_one(WLAN_BLOCK, FIRMWARE_ANCHOR, FIRMWARE_BLOCK + FIRMWARE_ANCHOR)
DELTA = WLAN_BEGIN + old.WLAN_MODULES.encode() + WLAN_BLOCK.encode() + WLAN_END


def frozen_init(order):
    return old.frozen_init(order)


def expected_init(frozen):
    require(frozen.count(ANCHOR) == 1 and frozen.count(DELTA) == 0, DELTA_MSG)
    return frozen.replace(ANCHOR, DELTA + ANCHOR, 1)


def check_wlan(init):
    require(init.count(WLAN_BEGIN) == 1 and init.count(WLAN_END) == 1, WLAN_MARKER_MSG)
    begin = init.index(WLAN_BEGIN)
    require(init.index(WLAN_END) > begin and init.index(WLAN_END) < init.index(ANCHOR) and
            begin < init.index(ANCHOR), WLAN_MARKER_MSG)
    require(init.count(LOOP_NEW.encode()) == 1 and init.count(LOOP_OLD.encode()) == 0 and
            init.count(b"LOOPMAJOR") == 0, MOUNT_MSG)
    require(init.count(MOUNTS_NEW.encode()) == 1 and init.count(MOUNTS_OLD.encode()) == 0,
            MOUNT_MSG)
    require(init.count(b'/bin/busybox hexdump -n 4 -s 1024') == 1 and
            init.count(b'/bin/busybox hexdump -n 2 -s 1080') == 1 and
            init.count(b'[ "$FS_MAGIC" != "53ef" ]') == 1 and
            init.count(b'mount -t "$FSTYPE" -o "$FSOPTS"') == 1 and
            init.count(b"FSOPTS=ro,nosuid,nodev,noexec") == 1 and
            init.count(b"FSOPTS=ro,noload,nosuid,nodev,noexec") == 1, MOUNT_MSG)
    for bad in (b"mount -o rw", b",rw", b"remount", b"mount -w"):
        require(bad not in init, MOUNT_MSG)
    for offset in (b"6947864576", b"5678039040", b"4797235200"):
        require(init.count(offset) == 1, MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox losetup -r -o \"$3\"") == 1,
            MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox blockdev --getsize64 /dev/block/sda6") == 1 and
            init.count(b'[ "$SIZE" = "9663676416" ]') == 1, MOUNT_MSG)
    require(init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox dd if=/dev/block/sda6 bs=4096 skip=") == 1,
            MOUNT_MSG)
    for digest in (super.GEOMETRY_PAGE_SHA256.encode(), super.METADATA_PAGE_SHA256.encode(),
                   super.ERAFS_PAGE_SHA256[super.VENDOR_DLKM].encode(),
                   super.ERAFS_PAGE_SHA256[super.VENDOR].encode(),
                   super.ERAFS_PAGE_SHA256[super.SYSTEM_DLKM].encode()):
        require(init.count(digest) == 1, MOUNT_MSG)
    require(init.count(FIRMWARE_BLOCK.encode()) == 1 and
            init.count(b"PARTNAME=modem_a") == 1 and
            init.count(b"/vendor/firmware_mnt/image/qca6750/bdwlan.elf") == 1 and
            init.count(b"mount -t vfat -o ro,nosuid,nodev,noexec /dev/block/sde6 "
                       b"/vendor/firmware_mnt") == 1 and
            init.count(b'/bin/busybox hexdump -n 8 -s 82') == 1 and
            init.count(b'/bin/busybox hexdump -n 5 -s 54') == 1, FIRMWARE_MSG)
    require(init.count(old.WLAN_MODULES.encode()) == 1 and
            init.count(super.RFKILL_PATH.encode()) == 1 and
            init.index(b"rfkill.ko\n") < init.index(b"cfg80211.ko\n"), MODULE_MSG)
    require(len(old.WLAN_MODULES_LIST) == super.CLOSURE_SIZE + 1 and
            tuple(name for name in old.WLAN_MODULES_LIST if name != "rfkill.ko") ==
            super.WLAN_ORDER, MODULE_MSG)
    position = {name: index for index, name in enumerate(old.WLAN_MODULES_LIST)}
    require(position["rfkill.ko"] < position["cfg80211.ko"] and
            position["cfg80211.ko"] < position["qca_cld3_qca6750.ko"] and
            position["qca_cld3_qca6750.ko"] == 20, MODULE_MSG)
    require(init.count(b'wlog "module $module loaded"') == 1 and
            init.count(b'wlog "module $module failed: $err"') == 1 and
            init.count(b'wlog "module $module failed: missing $KOPATH"') == 1 and
            init.count(b'wlog "module $module loaded (already present)"') == 1 and
            init.count(b'/bin/busybox insmod "$KOPATH"') == 1 and
            init.count(b"/bin/busybox timeout -k 1 2 /bin/busybox insmod") == 1, MODULE_MSG)
    require(init.count(b'[ -d /sys/class/net/wlan0 ]') == 1 and
            init.count(b"iw dev not available") == 1 and
            init.count(b'wlog "iw dev available: $IW"') == 1 and
            init.count(b'wlog "iw dev lines logged: $iwn (cap 16)"') == 1 and
            init.count(b'wlog "wlan dmesg lines logged: $dn (cap 64)"') == 1 and
            init.count(b'wlog "firmware names logged: $fn (cap 64)"') == 1 and
            init.count(b"*icnss2*|*cnss_plat*|*qca_cld3*|*bdwlan*") == 1 and
            init.count(b'wlog "firmware name: $name"') == 1, LOG_MSG)
    return begin


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    offset = check_wlan(init)
    frozen = frozen_init(order)
    require(init.count(DELTA) == 1, DELTA_MSG)
    stripped = init.replace(DELTA, b"", 1)
    static.check_timer(stripped)
    require(stripped.count(static.SSHD) == 1, static.SSHD_MSG)
    static.check_init(stripped, order)
    require(stripped == frozen and init == expected_init(frozen), DELTA_MSG)
    old.check_init(old.expected_init(frozen), order)
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
            "usage: build-init-boot-wlan-rfkill-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print("wlan-init phase: verified sda6 geometry, sysfs-derived loop nodes "
          f"(loop.max_part={super.LOOP_MAX_PART} measured), fstype-probed read-only mounts of "
          f"system_dlkm_a ({super.SYSTEM_DLKM_OFFSET}), vendor_a ({super.VENDOR_OFFSET}) and "
          f"vendor_dlkm_a ({super.VENDOR_DLKM_OFFSET}), probed vfat modem_a firmware mount at "
          f"/vendor/firmware_mnt, rfkill.ko ({super.RFKILL_SHA256[:8]}) before cfg80211.ko, "
          f"{len(old.WLAN_MODULES_LIST)}-module closure order unchanged, capped logging")
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
