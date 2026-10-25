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


builder = load("build-init-boot-pdmapper-tqftpserv-payload.py", "pdmapper_tqftpserv_builder")
prior = builder.prior
retry_checker = builder.old_checker
base_checker = load("verify-init-boot-vendor-modules.py", "vendor_checker")
base = builder.base
modules = builder.modules
eud = builder.eud
vendor = eud.vendor
static = prior.static
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (*retry_checker.REQUIRED_PRIOR, "35866d56")
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
KO_MSG = prior.KO_MSG
TIMER_MSG = prior.TIMER_MSG
LIST_MSG = prior.LIST_MSG
ENVELOPE_MSG = prior.ENVELOPE_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
BIN_MSG = builder.BIN_MSG
INPUT_MSG = builder.INPUT_MSG
MARKER = builder.MARKER
PHASE = builder.PHASE
ANCHOR = builder.ANCHOR
RUN34_MARKER = prior.SESSION_MARKER
MAPS = builder.MAPS
PDMAPPER = builder.PDMAPPER_SHA256
TQFTPSERV = builder.TQFTPSERV_SHA256


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def check_candidate(candidate, run34, stock, source, boot, vendor_boot, recovery, config,
                    kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv,
                    maps, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(modules.sha256(run34) == builder.MEASURED_RUN34 and len(run34) == IMAGE_SIZE,
            "run-34 reference is not the measured 35866d56 image")
    vendor.check_stock(stock, library)
    vendor_files, recovery_entries = vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, LIST_MSG)
    frozen = prior.wpss.frozen_init(order)
    builder.check_binary(pdmapper, PDMAPPER, builder.PDMAPPER_SIZE)
    builder.check_binary(tqftpserv, TQFTPSERV, builder.TQFTPSERV_SIZE)
    builder.check_maps(maps)

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

    for name, sha, size in (("bin/pd-mapper", PDMAPPER, builder.PDMAPPER_SIZE),
                            ("bin/tqftpserv", TQFTPSERV, builder.TQFTPSERV_SIZE)):
        entry = by_name.get(name)
        require(entry is not None and entry["mode"] & 0o170777 == 0o100755 and
                len(entry["data"]) == size and modules.sha256(entry["data"]) == sha, BIN_MSG)
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

    # The #86 init is run-34 with only the marker reworded and one phase inserted.
    run34_init = init.replace(PHASE, b"", 1).replace(MARKER, RUN34_MARKER, 1)
    run34_frame_size = struct.unpack_from("<I", run34, RAMDISK_SIZE_OFFSET)[0]
    run34_decoded = decode_frame(run34[PAGE:PAGE + run34_frame_size], library)
    run34_entries, _ = modules.parse_newc(run34_decoded, "run-34 debug cpio")
    run34_init_entry = next(e for e in run34_entries if e["name"] == "init")
    require(run34_init == run34_init_entry["data"], INIT_MSG)
    added = [e["name"] for e in entries if e["name"] not in {x["name"] for x in run34_entries}]
    require(added == ["bin/pd-mapper", "bin/tqftpserv", "etc/pd-mapper"] +
            ["etc/pd-mapper/" + n for n in sorted(MAPS)], CPIO_MSG)
    require([e["name"] for e in entries if e["name"] in
             {x["name"] for x in run34_entries}] ==
            [x["name"] for x in run34_entries], CPIO_MSG)

    digest = modules.sha256(candidate)
    reject_prior_sha(digest)
    rebuilt = builder.candidate_cpio(source, init, helper_input, vendor_files,
                                     recovery_entries, order, pdmapper, tqftpserv, maps)
    require(vendor.encode_frame(rebuilt, library) == expected and
            builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected


def self_test(candidate, run34, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input, pdmapper, tqftpserv, maps):
    library = base.lz4()
    digest, order, outside, cpio, frame = check_candidate(
        candidate, run34, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, pdmapper, tqftpserv, maps, library)
    print(f"init_boot pdmapper-tqftpserv fixture: OK ({digest})")
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
        expect_rejection(label, message, check_candidate, mutated, run34, stock, source,
                         boot, vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, pdmapper, tqftpserv, maps, library)

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

    # Binary/config presence and executability.
    case("pd-mapper removed", BIN_MSG, rebuild(with_init(drop={"bin/pd-mapper"})))
    case("tqftpserv removed", BIN_MSG, rebuild(with_init(drop={"bin/tqftpserv"})))
    case("pd-mapper not executable", BIN_MSG,
         rebuild(with_init(mode={"bin/pd-mapper": 0o100644})))
    case("tqftpserv not executable", BIN_MSG,
         rebuild(with_init(mode={"bin/tqftpserv": 0o100644})))
    case("cpio pd-mapper bytes differ from host pin", BIN_MSG,
         rebuild(with_init(replace={"bin/pd-mapper": bytearray(pdmapper) + b"\x00"})))
    case("cpio tqftpserv bytes differ from host pin", BIN_MSG,
         rebuild(with_init(replace={"bin/tqftpserv": bytearray(tqftpserv) + b"\x00"})))
    expect_rejection("host pd-mapper binary altered", BIN_MSG, check_candidate,
                     candidate, run34, stock, source, boot, vendor_boot, recovery, config,
                     kernel, decompressor, pstore, helper_input, bytearray(pdmapper) + b"\x00",
                     tqftpserv, maps, library)
    expect_rejection("host tqftpserv binary altered", BIN_MSG, check_candidate,
                     candidate, run34, stock, source, boot, vendor_boot, recovery, config,
                     kernel, decompressor, pstore, helper_input, pdmapper,
                     bytearray(tqftpserv) + b"\x00", maps, library)
    case("stock map altered", CPIO_MSG,
         rebuild(with_init(replace={"etc/pd-mapper/modemr.jsn":
                                    maps["modemr.jsn"].replace(b"modem", b"xodem", 1)})))
    case("stock map removed", CPIO_MSG,
         rebuild(with_init(drop={"etc/pd-mapper/cdspr.jsn"})))
    case("map parent dir removed", CPIO_MSG, rebuild(with_init(drop={"etc/pd-mapper"})))
    expect_rejection("host stock maps altered", INPUT_MSG, check_candidate, candidate,
                     run34, stock, source, boot, vendor_boot, recovery, config, kernel,
                     decompressor, pstore, helper_input, pdmapper, tqftpserv,
                     {**maps, "modemr.jsn": maps["modemr.jsn"].replace(b"modem", b"xodem", 1)},
                     library)

    # Startup ordering: phase after SSH/listener and before console ready.
    case("marker reworded", INIT_MSG, rebuild(with_init(
        edited(MARKER, b"log 'session #86: reworded'\n"))))
    case("marker replaced by run-34", INIT_MSG, rebuild(with_init(edited(MARKER, RUN34_MARKER))))
    case("phase removed", INIT_MSG, rebuild(with_init(edited(PHASE, b""))))
    case("phase duplicated", INIT_MSG, rebuild(with_init(edited(PHASE, PHASE + PHASE))))
    case("phase moved before SSH", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, b"", 1).replace(
            eud.TIMER, PHASE + eud.TIMER, 1))))
    case("phase moved after console ready", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, b"", 1).replace(
            ANCHOR, ANCHOR + PHASE, 1))))
    case("init-time remoteproc start added", prior.REMOTE_MSG, rebuild(with_init(edited(
        PHASE, PHASE + b"printf start >/sys/class/remoteproc/remoteproc2/state\n"))))
    case("service launch removed from phase", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(
            b"/bin/pd-mapper >>/run/pd-mapper.log 2>&1 &", b"true", 1), 1))))
    case("no /run log for pd-mapper", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(b"/run/pd-mapper.log", b"/dev/null", 1), 1))))
    case("QRTR publication not required before guarded start", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(
            b"/bin/busybox grep -q 'pd-mapper: published QRTR service' /run/pd-mapper.log",
            b"/bin/busybox true", 1), 1))))
    case("QRTR status log removed", INIT_MSG, rebuild(with_init(
        good_init.replace(PHASE, PHASE.replace(b"/run/qrtr-services.status", b"/dev/null", 1), 1))))

    run34_frame_size = struct.unpack_from("<I", run34, RAMDISK_SIZE_OFFSET)[0]
    run34_decoded = decode_frame(run34[PAGE:PAGE + run34_frame_size], library)
    run34_entries, _ = modules.parse_newc(run34_decoded, "run-34 debug cpio")
    expect_rejection("reused measured run-34 init", INIT_MSG, builder.check_init,
                     next(e["data"] for e in run34_entries if e["name"] == "init"), order)
    expect_rejection("reused measured run-34 image", SHA_MSG, reject_prior_sha,
                     builder.MEASURED_RUN34)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        item = next((p for p in PRIOR_IMAGES if p.startswith(prefix)), None)
        require(item is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, item)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("pdmapper-tqftpserv negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (15, 16) and (len(args) == 15 or args[0] == "--self-test"),
            "usage: verify-init-boot-pdmapper-tqftpserv.py [--self-test] CANDIDATE RUN34 "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV MAPS_DIR")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    blobs = [pathlib.Path(path).read_bytes() for path in args[:-1]]
    maps = builder.check_map_source(pathlib.Path(args[-1]))
    if self_test_mode:
        self_test(*blobs, maps)
        return
    digest, order, outside, cpio, frame = check_candidate(*blobs, maps, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"static services: pd-mapper {PDMAPPER[:8]} ({builder.PDMAPPER_SIZE} B), "
          f"tqftpserv {TQFTPSERV[:8]} ({builder.TQFTPSERV_SIZE} B)")
    print(f"stock domain maps: {len(MAPS)} files hash-pinned from the #89 "
          f"{builder.DUMP_SHA256[:8]} dump; no upstream example maps")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} "
          f"/ {base.MAX_FRAME} bytes")
    print("session init: run-34 (35866d56) with only the marker reworded and one bounded "
          "QRTR-service phase after verified SSH and before console ready; no remoteproc "
          "start in init")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from run-34 35866d56, ae2ccff7, 4216af26 and every "
          "other prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
