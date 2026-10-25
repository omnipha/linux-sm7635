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


prior = load("build-init-boot-wpss-boot-payload.py", "wpss_boot_builder")
checker = load("verify-init-boot-vendor-modules.py", "wlan_ini_vendor_checker")
base = prior.base
modules = prior.modules
eud = prior.eud
require = prior.require
decode_frame = checker.decode_frame

MEASURED_RUN37 = "d9d8d2b8268f1fcc8e3212b7943bf62c5a5b4b7e20f258acf80cbc76d5508076"
PRIOR_IMAGES = (*prior.PRIOR_IMAGES, MEASURED_RUN37)
SHA_MSG = "candidate repeats a measured init_boot SHA-256"
INIT_MSG = ("session init differs from the byte-exact #101 session init beyond the "
            "single WLAN INI reachability phase and the session marker")
CPIO_MSG = "candidate cpio differs from the #101 cpio beyond the session init"
PHASE_MSG = "the single WLAN INI reachability phase is missing, altered or misplaced"

INI_REL = "wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini"
INI_SHA256 = "57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4"
INI_SIZE = 2095
INI_FILE = "/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini"
FW_PATH = "/vendor/firmware"

MARKER = (b"log 'session #106: stock WLAN INI reachable on /vendor/firmware, "
          b"single-variable successor of the #101 run'\n")
PHASE = b"""\
wlog "wlan-ini: exposing the stock INI before the WLAN closure loads"
if [ -d /mnt/vendor/etc/wifi/qca6750 ] && [ -r /mnt/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini ]; then
	mkdir -p /vendor
	if /bin/busybox mount --bind /mnt/vendor /vendor; then
		if /bin/busybox mount -o remount,bind,ro /vendor; then
			wlog "wlan-ini: stock vendor_a bound read-only at /vendor"
		else
			/bin/busybox umount /vendor
			wlog "wlan-ini: /vendor remount read-only failed; bind removed"
		fi
	else
		wlog "wlan-ini: /vendor bind failed; INI unreachable"
	fi
else
	wlog "wlan-ini: stock vendor_a INI absent; INI unreachable"
fi
if [ -r /vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini ]; then
	INI_SHA=$(/bin/busybox sha256sum /vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini 2>/dev/null)
	if [ "${INI_SHA%% *}" = 57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4 ]; then
		wlog "wlan-ini: stock WCNSS_qcom_cfg.ini reachable (sha ok, 2095 B)"
	else
		wlog "wlan-ini: INI reachable but sha differs from the pinned stock file"
	fi
else
	wlog "wlan-ini: stock WCNSS_qcom_cfg.ini unreachable through /vendor/firmware"
fi
"""
ANCHOR = b'mkdir -p /vendor/firmware_mnt\n'


def expected_init(run37_init):
    require(run37_init.count(prior.prior.MARKER) == 1 and run37_init.count(ANCHOR) == 1 and
            PHASE not in run37_init, INIT_MSG)
    return (run37_init.replace(prior.prior.MARKER, MARKER, 1)
            .replace(ANCHOR, PHASE + ANCHOR, 1))


def check_init(init, run37_init):
    require(init.count(PHASE) == 1 and init.count(MARKER) == 1 and
            init.count(ANCHOR) == 1, PHASE_MSG)
    require(init.index(b"log 'wlan-init: begin'\n") <
            init.index(b"wlan_loop vendor_a 9 5678039040 /mnt/vendor") <
            init.index(PHASE) < init.index(ANCHOR) <
            init.index(b'wlog "module load begin"') <
            init.index(b"log 'wlan-init: end'\n"), PHASE_MSG)
    restored = (init.replace(PHASE, b"", 1).replace(MARKER, prior.prior.MARKER, 1))
    require(restored == run37_init and init == expected_init(run37_init), INIT_MSG)
    require(init.count(b"mount --bind /mnt/vendor /vendor") == 1 and
            init.count(b"remount,bind,ro /vendor") == 1, PHASE_MSG)
    return init.index(PHASE)


def candidate_cpio(run37_cpio, init, run37_init):
    entries, trailer = modules.parse_newc(run37_cpio, "run-37 cpio")
    check_init(init, run37_init)
    result = [{**entry, "data": init} if entry["name"] == "init" else entry
              for entry in entries]
    cpio = modules.encode_newc(result, trailer)
    decoded, _ = modules.parse_newc(cpio, "#106 cpio")
    require([entry["name"] for entry in decoded] == [entry["name"] for entry in entries] and
            all(a["mode"] == b["mode"] and
                (a["data"] == b["data"] or a["name"] == "init")
                for a, b in zip(decoded, entries)) and
            next(entry["data"] for entry in decoded if entry["name"] == "init") == init and
            not any(entry["name"].endswith(".ko") for entry in decoded), CPIO_MSG)
    return cpio


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, prior.prior.prior.prior.ENVELOPE_MSG)
    image, digest = prior.prior.prior.prior.static.peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    return image, digest


def run37_init_of(run37_cpio, order):
    init = next(entry["data"] for entry in modules.parse_newc(run37_cpio, "run-37 cpio")[0]
                if entry["name"] == "init")
    require(init == prior.prior.expected_init(prior.prior.prior.prior.wpss.frozen_init(order)),
            INIT_MSG)
    return init


def prepare(paths):
    require(len(paths) == 17, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV "
            "MAPS_DIR RMTFS SHAREDMEM_KO BY_NAME RUN37")
    stock, cpio, _frame, order, outside = prior.prepare(paths[:-1])
    run37 = pathlib.Path(paths[-1]).read_bytes()
    require(len(run37) == base.IMAGE_SIZE and modules.sha256(run37) == MEASURED_RUN37,
            "run-37 reference is not the measured d9d8d2b8 image")
    run37_frame_size = struct.unpack_from("<I", run37, base.RAMDISK_SIZE_OFFSET)[0]
    run37_cpio = decode_frame(run37[base.PAGE:base.PAGE + run37_frame_size], base.lz4())
    run37_init = run37_init_of(run37_cpio, order)
    init = expected_init(run37_init)
    cpio = candidate_cpio(run37_cpio, init, run37_init)
    frame = eud.vendor.encode_frame(cpio, base.lz4())
    return stock, cpio, frame, order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 19 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-wlan-ini-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR RMTFS "
            "SHAREDMEM_KO BY_NAME RUN37 OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"WLAN INI: stock {INI_REL} exposed read-only at {FW_PATH} before the "
          f"WLAN closure (target {INI_FILE}, {INI_SIZE} B, SHA-256 {INI_SHA256})")
    print("session init: byte-exact #101 run-37 init plus the single INI phase and "
          "the #106 marker; bin/wpss-once and every service unchanged")
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
