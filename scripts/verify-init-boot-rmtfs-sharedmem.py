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


builder = load("build-init-boot-rmtfs-sharedmem-payload.py", "rmtfs_sharedmem_builder")
prior = builder.prior
retry_checker = prior.old_checker
base_checker = load("verify-init-boot-vendor-modules.py", "vendor_checker")
base = builder.base
modules = builder.modules
eud = builder.eud
vendor = eud.vendor
static = prior.prior.static
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (*retry_checker.REQUIRED_PRIOR, "35866d56", "8dddb8c7")
require = base_checker.require
flipped = base_checker.flipped
expect_rejection = base_checker.expect_rejection
decode_frame = base_checker.decode_frame
SIZE_MSG = base_checker.SIZE_MSG
KERNEL_MSG = base_checker.KERNEL_MSG
HEADER_MSG = base_checker.HEADER_MSG
FRAME_MSG = base_checker.FRAME_MSG
BLOCK_MSG = base_checker.BLOCK_MSG
GAP_MSG = base_checker.GAP_MSG
TAIL_MSG = base_checker.TAIL_MSG
VENDOR_MSG = base_checker.VENDOR_MSG
SHA_MSG = builder.SHA_MSG
KO_MSG = prior.prior.KO_MSG
TIMER_MSG = prior.prior.TIMER_MSG
LIST_MSG = prior.prior.LIST_MSG
ENVELOPE_MSG = prior.prior.ENVELOPE_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
BIN_MSG = builder.BIN_MSG
INPUT_MSG = prior.INPUT_MSG
MARKER = builder.MARKER
PHASE = builder.PHASE
RECON_PHASE = builder.RECON_PHASE
ANCHOR = builder.ANCHOR
QRTR_PHASE_BEGIN = builder.QRTR_PHASE_BEGIN
QRTR_PHASE_END = builder.QRTR_PHASE_END

RUN35_MARKER = prior.MARKER
MAPS = prior.MAPS
PDMAPPER = prior.PDMAPPER_SHA256
TQFTPSERV = prior.TQFTPSERV_SHA256
RMTFS = builder.RMTFS_SHA256


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def check_candidate(candidate, run35, stock, source, boot, vendor_boot, recovery, config,
                    kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv,
                    rmtfs, sharedmem, maps, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(modules.sha256(run35) == builder.MEASURED_RUN35 and len(run35) == IMAGE_SIZE,
            "run-35 reference is not the measured 8dddb8c7 image")
    vendor.check_stock(stock, library)
    vendor_files, recovery_entries = vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, LIST_MSG)
    frozen = prior.prior.wpss.frozen_init(order)
    builder.check_binary(rmtfs, RMTFS, builder.RMTFS_SIZE)
    prior.check_binary(pdmapper, PDMAPPER, prior.PDMAPPER_SIZE)
    prior.check_binary(tqftpserv, TQFTPSERV, prior.TQFTPSERV_SIZE)
    require(len(sharedmem) == builder.SHAREDMEM_SIZE and
            modules.sha256(sharedmem) == builder.SHAREDMEM_SHA256,
            "stock msm_sharedmem.ko is not the pinned vendor_dlkm_a module")
    vendor_module = vendor_files.get("lib/modules/msm_sharedmem.ko")
    require(vendor_module is not None and vendor_module["data"] == sharedmem,
            "the vendor_boot ramdisk copy of msm_sharedmem.ko is not the pinned module")
    prior.check_maps(maps)

    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)

    by_name = {}
    for entry in entries:
        require(entry["name"] not in by_name, CPIO_MSG)
        by_name[entry["name"]] = entry
    init_entry = by_name.get("init")
    require(init_entry is not None and init_entry["mode"] & 0o170777 == 0o100755, INIT_MSG)
    init = init_entry["data"]
    builder.check_init(init, order)
    require(init == builder.expected_init(frozen), INIT_MSG)

    for name, sha in (("bin/pd-mapper.xz", PDMAPPER), ("bin/tqftpserv.xz", TQFTPSERV),
                      ("bin/rmtfs.xz", RMTFS)):
        entry = by_name.get(name)
        plain_name = name[:-3]
        require(entry is not None and entry["mode"] & 0o170777 == 0o100444, BIN_MSG)
        import lzma
        try:
            plain = lzma.decompress(entry["data"])
        except lzma.LZMAError as exc:
            raise ValueError(BIN_MSG) from exc
        expected_size = {"bin/pd-mapper": prior.PDMAPPER_SIZE, "bin/tqftpserv": prior.TQFTPSERV_SIZE,
                         "bin/rmtfs": builder.RMTFS_SIZE}[plain_name]
        require(len(plain) == expected_size and modules.sha256(plain) == sha, BIN_MSG)
    require("bin/pd-mapper" not in by_name and "bin/tqftpserv" not in by_name and
            "bin/rmtfs" not in by_name, CPIO_MSG)

    require(by_name.get("etc/pd-mapper") is not None and
            by_name["etc/pd-mapper"]["mode"] & 0o170000 == 0o40000, CPIO_MSG)
    for name, sha in MAPS.items():
        entry = by_name.get("etc/pd-mapper/" + name)
        require(entry is not None and entry["mode"] & 0o170777 == 0o100444 and
                modules.sha256(entry["data"]) == sha and entry["data"] == maps[name],
                CPIO_MSG)

    helper_entry = by_name.get(eud.HELPER_NAME)
    eud.check_helper(helper_input)
    require(helper_entry is not None and helper_entry["data"] == helper_input and
            helper_entry["mode"] & 0o170777 == 0o100755, eud.HELPER_MSG)

    try:
        modules.prove_vendor_modules(vendor_files, entries, recovery_entries)
    except ValueError as exc:
        raise ValueError(VENDOR_MSG) from exc

    expected = vendor.encode_frame(decoded, library)
    require(expected == candidate[PAGE:PAGE + frame_size], BLOCK_MSG)
    require(len(expected) <= base.MAX_FRAME, ENVELOPE_MSG)
    require(candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET] and
            candidate[RAMDISK_SIZE_OFFSET + 4:PAGE] == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            HEADER_MSG)
    require(not any(candidate[PAGE + frame_size:TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)

    run35_init = (init.replace(PHASE, b"", 1).replace(RECON_PHASE, b"", 1)
                  .replace(MARKER, RUN35_MARKER, 1))
    run35_frame_size = struct.unpack_from("<I", run35, RAMDISK_SIZE_OFFSET)[0]
    run35_decoded = decode_frame(run35[PAGE:PAGE + run35_frame_size], library)
    run35_entries, _ = modules.parse_newc(run35_decoded, "run-35 debug cpio")
    run35_init_entry = next(e for e in run35_entries if e["name"] == "init")
    require(run35_init == run35_init_entry["data"], INIT_MSG)
    added = [e["name"] for e in entries if e["name"] not in {x["name"] for x in run35_entries}]
    require(added == ["bin/pd-mapper.xz", "bin/tqftpserv.xz", "bin/rmtfs.xz"], CPIO_MSG)
    removed = [e["name"] for e in run35_entries if e["name"] not in {x["name"] for x in entries}]
    require(removed == ["bin/pd-mapper", "bin/tqftpserv"], CPIO_MSG)

    digest = modules.sha256(candidate)
    reject_prior_sha(digest)
    rebuilt = builder.candidate_cpio(source, init, helper_input, vendor_files,
                                     recovery_entries, order, rmtfs, pdmapper, tqftpserv, maps)
    require(vendor.encode_frame(rebuilt, library) == expected and
            builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected


def self_test(candidate, run35, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs, sharedmem, maps):
    library = base.lz4()
    digest, order, outside, cpio, frame = check_candidate(
        candidate, run35, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs, sharedmem, maps,
        library)
    print(f"init_boot rmtfs-sharedmem fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")
    retry_checker.previous.test_timer(next(e["data"] for e in
                                  modules.parse_newc(cpio, "candidate")[0]
                                  if e["name"] == "init"))

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")

    def rebuild(changed_entries):
        payload = modules.encode_newc(changed_entries, trailer)
        return static.peripheral.assemble(stock, vendor.encode_frame(payload, library))[0]

    def with_init(new_init=None, drop=(), replace=None, mode=None):
        changed = []
        for entry in entries:
            if entry["name"] in drop:
                continue
            item = dict(entry)
            if entry["name"] == "init" and new_init is not None:
                item = {**item, "data": new_init}
            if replace and entry["name"] in replace:
                item = {**item, "data": replace[entry["name"]]}
            if mode and entry["name"] in mode:
                item = {**item, "fields": item["fields"][:1] +
                        [mode[entry["name"]]] + item["fields"][2:], "mode": mode[entry["name"]]}
            changed.append(item)
        return changed

    good_init = next(e["data"] for e in entries if e["name"] == "init")

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, run35, stock, source,
                         boot, vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, pdmapper, tqftpserv, rmtfs, sharedmem, maps, library)

    def edited(old, new, count=1):
        require(good_init.count(old) == count, f"fixture anchor missing: {old!r}")
        return good_init.replace(old, new)

    case("changed signed tail", TAIL_MSG, flipped(candidate, TAIL_OFFSET + 100))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, flipped(candidate, PAGE + 64))
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    case("rmtfs removed", BIN_MSG, rebuild(with_init(drop={"bin/rmtfs.xz"})))
    case("pd-mapper archive removed", BIN_MSG, rebuild(with_init(drop={"bin/pd-mapper.xz"})))
    case("tqftpserv archive removed", BIN_MSG, rebuild(with_init(drop={"bin/tqftpserv.xz"})))
    case("rmtfs not readable", BIN_MSG,
         rebuild(with_init(mode={"bin/rmtfs.xz": 0o100000})))
    case("rmtfs archive bytes differ from host pin", BIN_MSG,
         rebuild(with_init(replace={"bin/rmtfs.xz": b"\xfd7zXZ\x00" + b"\x00" * 8})))
    expect_rejection("host rmtfs binary altered", BIN_MSG, check_candidate,
                     candidate, run35, stock, source, boot, vendor_boot, recovery, config,
                     kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv,
                     bytearray(rmtfs) + b"\x00", sharedmem, maps, library)
    expect_rejection("host msm_sharedmem.ko altered", "stock msm_sharedmem.ko is not the "
                     "pinned vendor_dlkm_a module", check_candidate, candidate, run35, stock,
                     source, boot, vendor_boot, recovery, config, kernel, decompressor, pstore,
                     helper_input, pdmapper, tqftpserv, rmtfs, bytearray(sharedmem) + b"\x00",
                     maps, library)
    case("stock map altered", CPIO_MSG,
         rebuild(with_init(replace={"etc/pd-mapper/modemr.jsn":
                                    maps["modemr.jsn"].replace(b"modem", b"xodem", 1)})))
    case("stock map removed", CPIO_MSG,
         rebuild(with_init(drop={"etc/pd-mapper/cdspr.jsn"})))

    case("marker reworded", INIT_MSG, rebuild(with_init(
        edited(MARKER, b"log 'session #96: reworded'\n"))))
    case("marker replaced by run-35", INIT_MSG, rebuild(with_init(edited(MARKER, RUN35_MARKER))))
    case("recon phase removed", INIT_MSG, rebuild(with_init(edited(RECON_PHASE, b""))))
    case("recon phase duplicated", INIT_MSG, rebuild(with_init(
        edited(RECON_PHASE, RECON_PHASE + RECON_PHASE))))
    case("recon phase moved after the #86 phase", INIT_MSG, rebuild(with_init(
        good_init.replace(RECON_PHASE, b"", 1).replace(QRTR_PHASE_END,
                                                       QRTR_PHASE_END + RECON_PHASE, 1))))
    case("phase removed", INIT_MSG, rebuild(with_init(edited(PHASE, b""))))
    case("phase duplicated", INIT_MSG, rebuild(with_init(edited(PHASE, PHASE + PHASE))))
    case("phase moved before the #86 phase", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, b"", 1).replace(QRTR_PHASE_BEGIN, PHASE + QRTR_PHASE_BEGIN, 1))))
    case("phase moved after console ready", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, b"", 1).replace(ANCHOR, ANCHOR + PHASE, 1))))
    case("init-time remoteproc start added", prior.prior.REMOTE_MSG, rebuild(with_init(edited(
        PHASE, PHASE + b"printf start >/sys/class/remoteproc/remoteproc2/state\n"))))
    case("sharedmem load removed from phase", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(
            b"/bin/busybox insmod \"$RMTFS_MODULE\"", b"true", 1), 1))))
    case("no /run log for rmtfs", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(b"/run/rmtfs.log", b"/dev/null", 1), 1))))
    case("QRTR publication not required", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(
            b"/bin/busybox grep -q 'rmtfs: published QRTR service' /run/rmtfs.log",
            b"/bin/busybox true", 1), 1))))
    case("backing partition link removed", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(builder.STORAGE_LINKS, b"", 1), 1))))
    case("reconstruction hash check removed", INIT_MSG, rebuild(with_init(
        good_init.replace(RECON_PHASE, RECON_PHASE.replace(
            b'[ "${GOT_SHA%% *}" = "$WANT_SHA" ]', b"true", 1), 1))))

    run35_frame_size = struct.unpack_from("<I", run35, RAMDISK_SIZE_OFFSET)[0]
    run35_decoded = decode_frame(run35[PAGE:PAGE + run35_frame_size], library)
    run35_entries, _ = modules.parse_newc(run35_decoded, "run-35 debug cpio")
    expect_rejection("reused measured run-35 init", INIT_MSG, builder.check_init,
                     next(e["data"] for e in run35_entries if e["name"] == "init"), order)
    expect_rejection("reused measured run-35 image", SHA_MSG, reject_prior_sha,
                     builder.MEASURED_RUN35)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        item = next((p for p in PRIOR_IMAGES if p.startswith(prefix)), None)
        require(item is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, item)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("rmtfs-sharedmem negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (18, 19) and (len(args) == 18 or args[0] == "--self-test"),
            "usage: verify-init-boot-rmtfs-sharedmem.py [--self-test] CANDIDATE RUN35 "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV RMTFS SHAREDMEM_KO "
            "BY_NAME MAPS_DIR")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    blobs = [pathlib.Path(path).read_bytes() for path in args[:-2]]
    builder.check_by_name(args[-2])
    maps = builder.old_checker.builder.check_map_source(pathlib.Path(args[-1]))
    if self_test_mode:
        self_test(*blobs, maps)
        return
    digest, order, outside, cpio, frame = check_candidate(*blobs, maps, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"static services: pd-mapper {PDMAPPER[:8]} ({prior.PDMAPPER_SIZE} B), "
          f"tqftpserv {TQFTPSERV[:8]} ({prior.TQFTPSERV_SIZE} B), "
          f"rmtfs {RMTFS[:8]} ({builder.RMTFS_SIZE} B); pd-mapper, tqftpserv and rmtfs "
          f"stored xz and reconstructed byte-exact before the #86 phase")
    print(f"stock msm_sharedmem.ko: {builder.SHAREDMEM_SHA256[:8]} "
          f"({builder.SHAREDMEM_SIZE} B), loaded as-is from read-only vendor_dlkm_a, "
          f"not shipped in the cpio")
    print(f"backing storage: /boot/modemst1 -> sdf2, /boot/modemst2 -> sdf3, read-only "
          f"shadow; fsc/fsg not exposed")
    print(f"stock domain maps: {len(MAPS)} files hash-pinned from the #89 "
          f"{prior.DUMP_SHA256[:8]} dump; no upstream example maps")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} "
          f"/ {base.MAX_FRAME} bytes")
    print("session init: run-35 (8dddb8c7) with the marker reworded and one bounded "
          "rmtfs/sharedmem phase after the #86 QRTR phase and before console ready; "
          "no remoteproc start in init")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from run-35 8dddb8c7, 35866d56, ae2ccff7, 4216af26 "
          "and every other prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
