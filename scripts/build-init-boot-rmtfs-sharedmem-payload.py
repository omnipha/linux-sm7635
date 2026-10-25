import importlib.util
import lzma
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


prior = load("build-init-boot-pdmapper-tqftpserv-payload.py", "pdmapper_tqftpserv_builder")
base = prior.base
modules = prior.modules
eud = prior.eud
require = prior.require
old_checker = load("verify-init-boot-pdmapper-tqftpserv.py", "pdmapper_checker")
super_closure = load("super-wlan-closure.py", "super_wlan_closure")

MEASURED_RUN35 = "8dddb8c714dce40c2795c95103236d8af9cfdc8ef00aaa6b6723055e41de09d1"
PRIOR_IMAGES = (*prior.PRIOR_IMAGES, MEASURED_RUN35)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
BIN_MSG = "rmtfs is missing, non-static, non-aarch64 or not the pinned reproducible binary"
INIT_MSG = ("session init is not run-35 plus the single #96 rmtfs/sharedmem phase, or the "
            "#86 phase was not preserved with pd-mapper reconstructed before it")
CPIO_MSG = "candidate cpio does not contain exactly the pinned rmtfs binary"
RMTFS_SHA256 = "d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd"
RMTFS_SIZE = 134088
SHAREDMEM_SHA256 = "e9216dcba1295498bc8e1d17405f971d3dadd587f7c453df53512f0a7c96ac76"
SHAREDMEM_SIZE = 19568
BY_NAME_DEVICES = {"modemst1": "sdf2", "modemst2": "sdf3"}
STORAGE_LINKS = b"\tln -s /dev/block/sdf2 /boot/modemst1\n\tln -s /dev/block/sdf3 /boot/modemst2\n"

MARKER = (b"log 'session #96: stock msm_sharedmem plus pinned rmtfs, single-variable "
          b"successor of the #86 run'\n")
# The LZ4 envelope forces all three static services to be stored xz-compressed.
# The reconstruction runs before the byte-identical #86 phase, which needs the
# executable pd-mapper/tqftpserv; reconstructed binaries are hash-checked
# against the pins so the #86 phase still runs the exact #95 binaries.
RECON_PHASE = b"""\
log 'recon phase begin: unpack the three pinned static services'
RECON_OK=1
unpack_service() {
	PACKED=$1
	PLAIN=${PACKED%.xz}
	WANT_SHA=$2
	if /bin/busybox xz -dc "$PACKED" >"$PLAIN" && /bin/busybox chmod 755 "$PLAIN"; then
		GOT_SHA=$(/bin/busybox sha256sum "$PLAIN" 2>/dev/null)
		if [ "${GOT_SHA%% *}" = "$WANT_SHA" ]; then
			log "recon: reconstructed $PLAIN (sha ok)"
			return 0
		fi
	fi
	log "recon: failed to reconstruct $PLAIN"
	rm -f "$PLAIN"
	RECON_OK=0
	return 1
}
unpack_service /bin/pd-mapper.xz 40acf0b06856205cb6cb9d53084afe5f6619fd1330c13242be1464b1dede3f43
unpack_service /bin/tqftpserv.xz 4eacb4ae30fe9c1ee3078bf140bd391c0179c2e8599461c67636d26006313965
unpack_service /bin/rmtfs.xz d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd
if [ "$RECON_OK" -ne 1 ]; then
	log 'recon: a service failed to reconstruct; its phase will fail closed'
fi
log 'recon phase end'
"""
PHASE = b"""\
log 'rmtfs phase begin; modem start stays coordinator-guarded'
RMTFS_READY=1
if [ ! -x /bin/rmtfs ]; then
	log 'rmtfs: reconstructed binary missing or not executable; no rmtfs start'
	RMTFS_READY=0
fi
mkdir -p /boot
RMTFS_MODULE=/mnt/vendor_dlkm/lib/modules/msm_sharedmem.ko
if [ ! -r "$RMTFS_MODULE" ] || [ ! -r /lib/modules/msm_sharedmem.ko ] || ! /bin/busybox cmp -s "$RMTFS_MODULE" /lib/modules/msm_sharedmem.ko; then
	log 'rmtfs: stock vendor_dlkm_a msm_sharedmem.ko absent or differs from the vendor_boot copy; no load'
	RMTFS_READY=0
elif [ -d /sys/module/msm_sharedmem ]; then
	log 'rmtfs: msm_sharedmem already present'
elif err=$(/bin/busybox timeout -k 1 2 /bin/busybox insmod "$RMTFS_MODULE" 2>&1); then
	log 'rmtfs: stock msm_sharedmem.ko loaded from read-only vendor_dlkm_a'
else
	err=$(/bin/busybox printf %s "$err" | /bin/busybox head -c 200)
	log "rmtfs: stock msm_sharedmem.ko failed to load: $err"
	RMTFS_READY=0
fi
WAIT_N=0
RMTFS_UIONAME=""
while [ "$WAIT_N" -lt 10 ]; do
	for uio in /sys/class/uio/*; do
		[ -r "$uio/name" ] || continue
		if [ "$(/bin/busybox cat "$uio/name" 2>/dev/null)" = rmtfs ]; then
			RMTFS_UIONAME=${uio##*/}
		fi
	done
	if [ -n "$RMTFS_UIONAME" ] && [ ! -c "/dev/$RMTFS_UIONAME" ] && [ -r "/sys/class/uio/$RMTFS_UIONAME/dev" ]; then
		UIO_DEVNUM=$(/bin/busybox cat "/sys/class/uio/$RMTFS_UIONAME/dev")
		/bin/busybox mknod "/dev/$RMTFS_UIONAME" c "${UIO_DEVNUM%%:*}" "${UIO_DEVNUM##*:}"
	fi
	if [ -n "$RMTFS_UIONAME" ] && [ -c "/dev/$RMTFS_UIONAME" ]; then
		break
	fi
	/bin/busybox sleep 0.1
	WAIT_N=$((WAIT_N + 1))
done
if [ -n "$RMTFS_UIONAME" ] && [ -c "/dev/$RMTFS_UIONAME" ]; then
	log "rmtfs: stock sharedmem client device ready: /dev/$RMTFS_UIONAME"
	if /bin/busybox dmesg 2>/dev/null | /bin/busybox grep -m1 "Device created for client 'rmtfs'" >/dev/null; then
		log "rmtfs: kernel log carries Device created for client 'rmtfs'"
	fi
else
	log "rmtfs: sharedmem client device absent (uio name: ${RMTFS_UIONAME:-none})"
	RMTFS_READY=0
fi
BLOCK_ERROR=0
for part in modemst1 sdf2 modemst2 sdf3; do
	if [ -r /sys/class/block/$part/dev ]; then
		DEVNUM=$(/bin/busybox cat /sys/class/block/$part/dev)
		if [ ! -b "/dev/block/$part" ]; then
			/bin/busybox mknod "/dev/block/$part" b "${DEVNUM%%:*}" "${DEVNUM##*:}"
		fi
	fi
done
if [ ! -b /dev/block/sdf2 ] || [ ! -b /dev/block/sdf3 ]; then
	log 'rmtfs: backing partitions modemst1/sdf2 or modemst2/sdf3 absent'
	BLOCK_ERROR=1
elif [ "$(/bin/busybox cat /sys/class/block/sdf2/uevent 2>/dev/null | /bin/busybox sed -n 's/^PARTNAME=//p')" != modemst1 ] ||
	[ "$(/bin/busybox cat /sys/class/block/sdf3/uevent 2>/dev/null | /bin/busybox sed -n 's/^PARTNAME=//p')" != modemst2 ]; then
	log 'rmtfs: sdf2/sdf3 PARTNAME is not modemst1/modemst2; no backing link'
	BLOCK_ERROR=1
fi
if [ "$BLOCK_ERROR" -eq 0 ]; then
	ln -s /dev/block/sdf2 /boot/modemst1
	ln -s /dev/block/sdf3 /boot/modemst2
	log 'rmtfs: backing storage ready: /boot/modemst1 -> sdf2, /boot/modemst2 -> sdf3 (read-only shadow)'
else
	RMTFS_READY=0
fi
if [ "$RMTFS_READY" -eq 1 ]; then
	printf 'launching rmtfs\n' >/run/rmtfs.log
	/bin/rmtfs -r -P -o /boot >>/run/rmtfs.log 2>&1 &
	RMTFS_PID=$!
	log "rmtfs: launched pid $RMTFS_PID log /run/rmtfs.log"
	RMTFS_WAIT=0
	while [ "$RMTFS_WAIT" -lt 5 ]; do
		/bin/busybox sleep 1
		RMTFS_WAIT=$((RMTFS_WAIT + 1))
		if /bin/busybox kill -0 "$RMTFS_PID" 2>/dev/null &&
			/bin/busybox grep -q 'rmtfs: published QRTR service' /run/rmtfs.log; then
			break
		fi
	done
	if /bin/busybox kill -0 "$RMTFS_PID" 2>/dev/null &&
		/bin/busybox grep -q 'rmtfs: published QRTR service' /run/rmtfs.log; then
		log 'rmtfs: process alive and published QRTR service'
		printf 'rmtfs-published\n' >/run/rmtfs.status
	else
		log 'rmtfs: process exited or QRTR publish line missing'
		printf 'failed\n' >/run/rmtfs.status
	fi
else
	log 'rmtfs: prerequisites missing; no rmtfs start'
	printf 'failed\n' >/run/rmtfs.status
fi
log 'rmtfs phase end; inspect /run/rmtfs.log and /run/rmtfs.status over SSH'
"""
ANCHOR = b"log 'console ready'\n"
QRTR_PHASE_BEGIN = b"log 'qrtr-service phase begin; modem start stays coordinator-guarded'\n"
QRTR_PHASE_END = (b"log 'qrtr-service phase end; inspect /run/*.log and "
                  b"/run/qrtr-services.status over SSH'\n")


def expected_init(frozen):
    run35 = prior.expected_init(frozen)
    require(run35.count(QRTR_PHASE_BEGIN) == 1 and run35.count(QRTR_PHASE_END) == 1 and
            run35.count(ANCHOR) == 1, INIT_MSG)
    run35 = (run35.replace(prior.MARKER, MARKER, 1)
             .replace(QRTR_PHASE_BEGIN, RECON_PHASE + QRTR_PHASE_BEGIN, 1)
             .replace(QRTR_PHASE_END, QRTR_PHASE_END + PHASE, 1))
    return run35


def check_init(init, order):
    require(init.count(PHASE) == 1 and init.count(RECON_PHASE) == 1 and
            init.count(MARKER) == 1 and init.count(ANCHOR) == 1, INIT_MSG)
    require(init.index(b"log 'sshd listening at 172.16.42.2:22 (public key only)'") <
            init.index(RECON_PHASE) < init.index(QRTR_PHASE_BEGIN) <
            init.index(QRTR_PHASE_END) < init.index(PHASE) < init.index(ANCHOR), INIT_MSG)
    run35 = (init.replace(PHASE, b"", 1).replace(RECON_PHASE, b"", 1)
             .replace(MARKER, prior.MARKER, 1))
    old_checker.builder.check_init(run35, order)
    require(run35 == prior.expected_init(prior.prior.wpss.frozen_init(order)) and
            init == expected_init(prior.prior.wpss.frozen_init(order)), INIT_MSG)
    require(init.count(STORAGE_LINKS) == 1, INIT_MSG)
    require(b"/sys/class/remoteproc" not in init and b"wpss_boot" not in init, INIT_MSG)
    return init.index(PHASE)



def check_binary(data, sha, size):
    require(len(data) == size and modules.sha256(data) == sha and
            data[:6] == b"\x7fELF\x02\x01", BIN_MSG)
    require(struct.unpack_from("<HH", data, 16) == (2, 183), BIN_MSG)
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    types = [struct.unpack_from("<I", data, phoff + phsize * i)[0] for i in range(phnum)]
    require(1 in types and 2 not in types and 3 not in types, BIN_MSG)


def verify_sharedmem_host(path):
    data = pathlib.Path(path).read_bytes()
    verify_sharedmem_bytes(data)
    return data


def verify_sharedmem_bytes(data):
    require(len(data) == SHAREDMEM_SIZE and modules.sha256(data) == SHAREDMEM_SHA256,
            "stock msm_sharedmem.ko is not the pinned vendor_dlkm_a module")


def pack_binary(data):
    return lzma.compress(data, format=lzma.FORMAT_XZ,
                         preset=9 | lzma.PRESET_EXTREME, check=lzma.CHECK_NONE)


def check_by_name(path):
    found = super_closure.verify_by_name(path)
    for name, device in BY_NAME_DEVICES.items():
        require(found.get(name) == device,
                "the measured by-name table does not place %s on %s" % (name, device))
    return found


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order, rmtfs,
                   pdmapper, tqftpserv, maps):
    run35 = prior.candidate_cpio(source, prior.expected_init(prior.prior.wpss.frozen_init(order)),
                                 helper, vendor_files, recovery_entries, order,
                                 pdmapper, tqftpserv, maps)
    entries, trailer = modules.parse_newc(run35, "run-35 cpio")
    check_init(init, order)
    check_binary(rmtfs, RMTFS_SHA256, RMTFS_SIZE)
    names = {entry["name"] for entry in entries}
    require(not names & {"bin/rmtfs.xz", "bin/pd-mapper.xz", "bin/tqftpserv.xz"}, CPIO_MSG)
    result = []
    for entry in entries:
        if entry["name"] == "init":
            entry = {**entry, "data": init}
        if entry["name"] not in {"bin/pd-mapper", "bin/tqftpserv"}:
            result.append(entry)
    for name, binary in (("pd-mapper", pdmapper), ("tqftpserv", tqftpserv),
                         ("rmtfs", rmtfs)):
        result.append(prior.archive_entry("bin/" + name + ".xz", pack_binary(binary),
                                          0o100444))
    require(len(result) == len(entries) + 1, CPIO_MSG)
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#96 cpio")
    require([entry["name"] for entry in decoded] == [entry["name"] for entry in result] and
            all(a["mode"] == b["mode"] and a["data"] == b["data"]
                for a, b in zip(decoded, result)), CPIO_MSG)
    require(not any(e["name"].endswith(".ko") for e in decoded), CPIO_MSG)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, prior.prior.ENVELOPE_MSG)
    image, digest = prior.prior.static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 16, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME")
    blobs = [pathlib.Path(path).read_bytes() for path in paths[:10]]
    stock, source, boot, vendor, recovery, config, kernel, decompressor, pstore, helper = blobs
    pdmapper_path, tqftpserv_path, maps_dir, rmtfs_path, sharedmem_path, by_name_path = \
        paths[10:]
    maps = old_checker.builder.check_map_source(pathlib.Path(maps_dir))
    check_by_name(by_name_path)
    sharedmem = verify_sharedmem_host(sharedmem_path)
    rmtfs = pathlib.Path(rmtfs_path).read_bytes()
    check_binary(rmtfs, RMTFS_SHA256, RMTFS_SIZE)
    pdmapper = pathlib.Path(pdmapper_path).read_bytes()
    tqftpserv = pathlib.Path(tqftpserv_path).read_bytes()
    prior.check_binary(pdmapper, prior.PDMAPPER_SHA256, prior.PDMAPPER_SIZE)
    prior.check_binary(tqftpserv, prior.TQFTPSERV_SHA256, prior.TQFTPSERV_SIZE)
    library = base.lz4()
    vendor_files, recovery_entries = eud.vendor.verify_host_path(
        boot, vendor, stock, recovery, config, kernel, decompressor, pstore, library)
    entry = vendor_files.get("lib/modules/msm_sharedmem.ko")
    require(entry is not None and entry["data"] == sharedmem and
            modules.sha256(entry["data"]) == SHAREDMEM_SHA256 and
            len(entry["data"]) == SHAREDMEM_SIZE,
            "stock vendor_boot msm_sharedmem.ko is not the pinned module")
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, prior.prior.LIST_MSG)
    eud.vendor.check_stock(stock, library)
    init = expected_init(prior.prior.wpss.frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                          rmtfs, pdmapper, tqftpserv, maps)
    frame = eud.vendor.encode_frame(cpio, library)
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 18 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-rmtfs-sharedmem-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR RMTFS "
            "SHAREDMEM_KO BY_NAME OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"rmtfs: pinned upstream {RMTFS_SHA256[:8]} ({RMTFS_SIZE} B), static aarch64, "
          f"publish-line observability patch")
    print(f"msm_sharedmem.ko: stock module {SHAREDMEM_SHA256[:8]} "
          f"({SHAREDMEM_SIZE} B), vendor_boot copy already present in the combined image "
          f"at /lib/modules, identical to the vendor_dlkm_a provider; loaded as-is "
          f"from the read-only vendor_dlkm_a mount, never rebuilt")
    print(f"backing storage: /boot/modemst1 -> sdf2, /boot/modemst2 -> sdf3 (by-name "
          f"measured table); -r keeps the partitions unwritten")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} / {base.MAX_FRAME} bytes")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
