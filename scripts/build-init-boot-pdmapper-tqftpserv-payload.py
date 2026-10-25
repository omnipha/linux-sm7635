import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


prior = load("build-init-boot-retry-marker-payload.py", "retry_marker_builder")
base = prior.base
modules = prior.modules
eud = prior.eud
require = prior.require
old_checker = load("verify-init-boot-retry-marker.py", "retry_marker_checker")
extractor = load("extract-modem-domain-maps.py", "domain_map_extractor")

MEASURED_RUN34 = "35866d569e3aabe62698bad924ab0cd649f0bf89cafdf41e520af7964b10f466"
PRIOR_IMAGES = (*prior.PRIOR_IMAGES, MEASURED_RUN34)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INPUT_MSG = "missing, altered or synthetic #89 stock domain maps"
BIN_MSG = "pd-mapper or tqftpserv is missing, non-static, non-aarch64 or not reproducible"
INIT_MSG = "session init is not run-34 plus the single #86 QRTR-service phase"
CPIO_MSG = "candidate cpio does not contain exactly the pinned binaries and stock maps"
MAPS = {
    "adspr.jsn": "66ce8531efb7979d234e0f0eabbe18d038ac97da771a8a194f613df8f0724e81",
    "adsps.jsn": "12ac2f3ae8ced12aa4b06b3ab3a01bc4d8efe1c92ebea503c002f209a6ec176f",
    "adspua.jsn": "982a99853495e34726b8e44697fdfad303334de0a67cbf6cde306c8f1731000b",
    "battmgr.jsn": "be8c6fba330908e4683fb6282761cb08485a302d6a66e09721e102e342f27236",
    "cdspr.jsn": "6d01cd7dce745204d5de20efe57e2511149ca2a5b48ee562fbedefda573ca465",
    "modemr.jsn": "07138bd0e249fa43db4eeb1a4516037db3bfe4bb88285e8c36f594be2b2a4b43",
}
DUMP_SHA256 = "08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a"
PDMAPPER_SHA256 = "40acf0b06856205cb6cb9d53084afe5f6619fd1330c13242be1464b1dede3f43"
TQFTPSERV_SHA256 = "4eacb4ae30fe9c1ee3078bf140bd391c0179c2e8599461c67636d26006313965"
PDMAPPER_SIZE = 199008
TQFTPSERV_SIZE = 132592

MARKER = b"log 'session #86: stock-map pd-mapper and tqftpserv, capture-gated single modem start'\n"
PHASE = b"""\
log 'qrtr-service phase begin; modem start stays coordinator-guarded'
QRTR_READY=1
if [ ! -d /vendor/firmware_mnt/image ] || [ ! -r /vendor/firmware_mnt/image/modemr.jsn ]; then
	log 'qrtr-service: stock modem_a firmware mount absent; no service start'
	QRTR_READY=0
fi
for jsn in adspr.jsn adsps.jsn adspua.jsn battmgr.jsn cdspr.jsn modemr.jsn; do
	case "$jsn" in
	adspr.jsn) JSN_SHA=66ce8531efb7979d234e0f0eabbe18d038ac97da771a8a194f613df8f0724e81 ;;
	adsps.jsn) JSN_SHA=12ac2f3ae8ced12aa4b06b3ab3a01bc4d8efe1c92ebea503c002f209a6ec176f ;;
	adspua.jsn) JSN_SHA=982a99853495e34726b8e44697fdfad303334de0a67cbf6cde306c8f1731000b ;;
	battmgr.jsn) JSN_SHA=be8c6fba330908e4683fb6282761cb08485a302d6a66e09721e102e342f27236 ;;
	cdspr.jsn) JSN_SHA=6d01cd7dce745204d5de20efe57e2511149ca2a5b48ee562fbedefda573ca465 ;;
	modemr.jsn) JSN_SHA=07138bd0e249fa43db4eeb1a4516037db3bfe4bb88285e8c36f594be2b2a4b43 ;;
	esac
	JSN_PATH=/vendor/firmware_mnt/image/$jsn
	JSN_CONFIG=/etc/pd-mapper/$jsn
	if [ ! -r "$JSN_PATH" ] || [ ! -r "$JSN_CONFIG" ] || ! /bin/busybox cmp -s "$JSN_PATH" "$JSN_CONFIG" || ! /bin/busybox sha256sum "$JSN_CONFIG" | /bin/busybox grep -q "^$JSN_SHA  $JSN_CONFIG$"; then
		log "qrtr-service: invalid stock map $jsn; no service start"
		QRTR_READY=0
	else
		log "qrtr-service: stock map $jsn verified"
	fi
done
if [ ! -x /bin/pd-mapper ] || [ ! -x /bin/tqftpserv ]; then
	log 'qrtr-service: missing executable binary; no service start'
	QRTR_READY=0
fi
if [ "$QRTR_READY" -eq 1 ]; then
	mkdir -p /lib/firmware /var/lib/tqftpserv
	if /bin/busybox mount --bind /vendor/firmware_mnt/image /lib/firmware; then
		if /bin/busybox mount -o remount,bind,ro /lib/firmware; then
			log 'qrtr-service: stock firmware maps bound read-only at /lib/firmware'
		else
			log 'qrtr-service: firmware bind remount ro failed; no service start'
			QRTR_READY=0
		fi
	else
		log 'qrtr-service: firmware bind failed; no service start'
		QRTR_READY=0
	fi
fi
if [ "$QRTR_READY" -eq 1 ]; then
	printf 'launching pd-mapper\n' >/run/pd-mapper.log
	/bin/pd-mapper >>/run/pd-mapper.log 2>&1 &
	PD_PID=$!
	log "qrtr-service: pd-mapper launched pid $PD_PID log /run/pd-mapper.log"
	printf 'launching tqftpserv\n' >/run/tqftpserv.log
	/bin/tqftpserv -d >>/run/tqftpserv.log 2>&1 &
	TQ_PID=$!
	log "qrtr-service: tqftpserv launched pid $TQ_PID log /run/tqftpserv.log"
	QRTR_WAIT=0
	while [ "$QRTR_WAIT" -lt 5 ]; do
		/bin/busybox sleep 1
		QRTR_WAIT=$((QRTR_WAIT + 1))
		if /bin/busybox grep -q 'pd-mapper: published QRTR service' /run/pd-mapper.log &&
			/bin/busybox grep -q 'tqftpserv: published QRTR service' /run/tqftpserv.log &&
			/bin/busybox kill -0 "$PD_PID" 2>/dev/null &&
			/bin/busybox kill -0 "$TQ_PID" 2>/dev/null; then
			break
		fi
	done
	if /bin/busybox kill -0 "$PD_PID" 2>/dev/null &&
		/bin/busybox kill -0 "$TQ_PID" 2>/dev/null &&
		/bin/busybox grep -q 'pd-mapper: published QRTR service' /run/pd-mapper.log &&
		/bin/busybox grep -q 'tqftpserv: published QRTR service' /run/tqftpserv.log; then
		log 'qrtr-service: both processes alive and published QRTR services'
		printf 'qrtr-published\n' >/run/qrtr-services.status
	else
		log 'qrtr-service: process exited or QRTR publish line missing; no guarded start'
		printf 'failed\n' >/run/qrtr-services.status
	fi
else
	printf 'failed\n' >/run/qrtr-services.status
fi
log 'qrtr-service phase end; inspect /run/*.log and /run/qrtr-services.status over SSH'
"""
ANCHOR = b"log 'console ready'\n"


def expected_init(frozen):
    run34 = prior.expected_init(frozen)
    require(run34.count(prior.SESSION_MARKER) == 1 and run34.count(ANCHOR) == 1,
            INIT_MSG)
    return run34.replace(prior.SESSION_MARKER, MARKER, 1).replace(ANCHOR, PHASE + ANCHOR, 1)


def check_init(init, order):
    require(init.count(PHASE) == 1 and init.count(MARKER) == 1 and
            init.count(ANCHOR) == 1, INIT_MSG)
    require(init.index(b"log 'sshd listening at 172.16.42.2:22 (public key only)'") <
            init.index(PHASE) < init.index(ANCHOR) and
            init.index(eud.TIMER) < init.index(MARKER), INIT_MSG)
    run34 = init.replace(PHASE, b"", 1).replace(MARKER, prior.SESSION_MARKER, 1)
    old_checker.builder.check_init(run34, order)
    require(run34 == prior.expected_init(prior.wpss.frozen_init(order)) and
            init == expected_init(prior.wpss.frozen_init(order)), INIT_MSG)
    return init.index(PHASE)


def check_binary(data, sha, size):
    require(len(data) == size and modules.sha256(data) == sha and
            data[:6] == b"\x7fELF\x02\x01" and
            struct.unpack_from("<HH", data, 16) == (2, 183), BIN_MSG)
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    require(phsize == 56 and phnum > 0 and phoff + phsize * phnum <= len(data), BIN_MSG)
    types = [struct.unpack_from("<I", data, phoff + phsize * i)[0] for i in range(phnum)]
    require(1 in types and 2 not in types and 3 not in types, BIN_MSG)


def check_maps(maps):
    require(set(maps) == set(MAPS), INPUT_MSG)
    files = []
    for name in sorted(MAPS):
        data = maps[name]
        require(modules.sha256(data) == MAPS[name], INPUT_MSG)
        files.append({"path": "image/" + name, "entries": extractor.validate_jsn(
            "image/" + name, data)})
    providers = extractor.derive_config(files)
    require(len(providers) == 6 and
            [(p["soc"], p["domain"], p["subdomain"], p["qmi_instance_id"])
             for p in providers] == [
                 ("msm", "adsp", "audio_pd", 74),
                 ("msm", "adsp", "charger_pd", 74),
                 ("msm", "adsp", "root_pd", 74),
                 ("msm", "adsp", "sensor_pd", 74),
                 ("msm", "cdsp", "root_pd", 76),
                 ("msm", "modem", "root_pd", 180)], INPUT_MSG)
    return providers


def check_map_source(maps_dir):
    manifest = (maps_dir / "extraction-manifest.txt").read_text()
    required = ("dump_sha256=" + DUMP_SHA256, "dump_size=367001600", "fat_type=16",
                "synthetic=false", "jsn_under_image=6", "jsn_outside_image=0",
                "providers=6", "verdict=PASS")
    require(all(manifest.splitlines().count(line) == 1 for line in required), INPUT_MSG)
    maps = {}
    for name, sha in MAPS.items():
        needle = f"jsn_file=image/{name} size="
        lines = [line for line in manifest.splitlines() if line.startswith(needle)]
        require(len(lines) == 1 and f"sha256={sha} under_image=yes" in lines[0], INPUT_MSG)
        maps[name] = (maps_dir / "maps" / "image" / name).read_bytes()
    require(sum(line.startswith("jsn_file=") for line in manifest.splitlines()) == 6,
            INPUT_MSG)
    check_maps(maps)
    return maps


def archive_entry(name, data, mode):
    return {"name": name, "fields": [0, mode, 0, 0, 1, 0, 0, 0, 0, 0, 0,
                                     len(name) + 1, 0], "mode": mode, "data": data}


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                   pdmapper, tqftpserv, maps):
    old = prior.candidate_cpio(source, prior.expected_init(prior.wpss.frozen_init(order)),
                               helper, vendor_files, recovery_entries, order)
    entries, trailer = modules.parse_newc(old, "run-34 cpio")
    check_init(init, order)
    check_binary(pdmapper, PDMAPPER_SHA256, PDMAPPER_SIZE)
    check_binary(tqftpserv, TQFTPSERV_SHA256, TQFTPSERV_SIZE)
    check_maps(maps)
    names = {entry["name"] for entry in entries}
    forbidden = ({"bin/pd-mapper", "bin/tqftpserv", "etc/pd-mapper"} |
                 {f"etc/pd-mapper/{name}" for name in MAPS})
    require(not names & forbidden, CPIO_MSG)
    result = []
    for entry in entries:
        if entry["name"] == "init":
            entry = {**entry, "data": init}
        result.append(entry)
    result.append(archive_entry("bin/pd-mapper", pdmapper, 0o100755))
    result.append(archive_entry("bin/tqftpserv", tqftpserv, 0o100755))
    result.append(archive_entry("etc/pd-mapper", b"", 0o40755))
    for name in sorted(MAPS):
        result.append(archive_entry(f"etc/pd-mapper/{name}", maps[name], 0o100444))
    require(len(result) == len(entries) + 9, CPIO_MSG)
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#86 cpio")
    require([entry["name"] for entry in decoded] == [entry["name"] for entry in result] and
            all(a["mode"] == b["mode"] and a["data"] == b["data"]
                for a, b in zip(decoded, result)) and
            not any(e["name"].endswith(".ko") for e in decoded), CPIO_MSG)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, prior.ENVELOPE_MSG)
    image, digest = prior.static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 13, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR")
    stock, source, boot, vendor, recovery, config, kernel, decompressor, pstore, helper, \
        pdmapper, tqftpserv = (pathlib.Path(path).read_bytes() for path in paths[:-1])
    maps = check_map_source(pathlib.Path(paths[-1]))
    library = base.lz4()
    vendor_files, recovery_entries = eud.vendor.verify_host_path(
        boot, vendor, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, prior.LIST_MSG)
    eud.vendor.check_stock(stock, library)
    init = expected_init(prior.wpss.frozen_init(order))
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                          pdmapper, tqftpserv, maps)
    frame = eud.vendor.encode_frame(cpio, library)
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 15 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-pdmapper-tqftpserv-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"stock domain maps: {len(MAPS)} files from #89 {DUMP_SHA256}; no example maps")
    print(f"static aarch64 services: pd-mapper {PDMAPPER_SHA256}, tqftpserv {TQFTPSERV_SHA256}")
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
