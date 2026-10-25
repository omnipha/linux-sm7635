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


builder = load("build-init-boot-wpss-boot-payload.py", "wpss_boot_builder")
rmtfs = load("verify-init-boot-rmtfs-sharedmem.py", "rmtfs_sharedmem_checker")
prior = rmtfs
base = builder.base
modules = builder.modules
eud = builder.eud
vendor = eud.vendor
static = builder.prior.prior.prior.static
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (*rmtfs.REQUIRED_PRIOR, "bf2089c4")
require = rmtfs.require
expect_rejection = rmtfs.expect_rejection
decode_frame = rmtfs.decode_frame
SIZE_MSG = rmtfs.SIZE_MSG
KERNEL_MSG = rmtfs.KERNEL_MSG
HEADER_MSG = rmtfs.HEADER_MSG
FRAME_MSG = rmtfs.FRAME_MSG
BLOCK_MSG = rmtfs.BLOCK_MSG
GAP_MSG = rmtfs.GAP_MSG
TAIL_MSG = rmtfs.TAIL_MSG
VENDOR_MSG = rmtfs.VENDOR_MSG
SHA_MSG = builder.SHA_MSG
KO_MSG = rmtfs.KO_MSG
ENVELOPE_MSG = rmtfs.ENVELOPE_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
TRIGGER_MSG = builder.TRIGGER_MSG


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def check_candidate(candidate, run36, stock, source, boot, vendor_boot, recovery, config,
                    kernel, decompressor, pstore, helper_input, pdmapper, tqftpserv,
                    rmtfs_binary, sharedmem, maps, library):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(modules.sha256(run36) == builder.MEASURED_RUN36 and len(run36) == IMAGE_SIZE,
            "run-36 reference is not the measured bf2089c4 image")
    vendor.check_stock(stock, library)
    vendor_files, recovery_entries = vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, rmtfs.LIST_MSG)
    frozen = builder.prior.prior.prior.wpss.frozen_init(order)

    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = decode_frame(candidate[PAGE:PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    by_name = {}
    for entry in entries:
        require(entry["name"] not in by_name, CPIO_MSG)
        by_name[entry["name"]] = entry

    # Byte-exact #96 half: identical init and identical entries except the trigger.
    init = by_name["init"]["data"]
    require(by_name["init"]["mode"] & 0o170777 == 0o100755, INIT_MSG)
    require(init == builder.prior.expected_init(frozen), INIT_MSG)
    trigger_entry = by_name.get("bin/wpss-once")
    require(trigger_entry is not None and trigger_entry["mode"] & 0o170777 == 0o100755 and
            trigger_entry["data"] == builder.TRIGGER, TRIGGER_MSG)
    builder.check_trigger(trigger_entry["data"])
    run36_frame_size = struct.unpack_from("<I", run36, RAMDISK_SIZE_OFFSET)[0]
    run36_decoded = decode_frame(run36[PAGE:PAGE + run36_frame_size], library)
    run36_entries, _ = modules.parse_newc(run36_decoded, "run-36 debug cpio")
    run36_by_name = {entry["name"]: entry for entry in run36_entries}
    require(set(by_name) - set(run36_by_name) == {"bin/wpss-once"}, CPIO_MSG)
    for name, entry in run36_by_name.items():
        mine = by_name[name]
        require(mine["mode"] == entry["mode"] and mine["data"] == entry["data"], CPIO_MSG)
    require([entry["name"] for entry in entries] ==
            [entry["name"] for entry in run36_entries] + ["bin/wpss-once"], CPIO_MSG)

    # Structural envelope: stock prefix, single LZ4 block, zero gap, stock signed tail.
    expected = vendor.encode_frame(decoded, library)
    require(expected == candidate[PAGE:PAGE + frame_size], BLOCK_MSG)
    require(len(expected) <= base.MAX_FRAME, ENVELOPE_MSG)
    require(candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET] and
            candidate[RAMDISK_SIZE_OFFSET + 4:PAGE] == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            HEADER_MSG)
    require(not any(candidate[PAGE + frame_size:TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)

    digest = modules.sha256(candidate)
    reject_prior_sha(digest)
    run36_cpio = modules.encode_newc(
        [entry for entry in entries if entry["name"] != "bin/wpss-once"],
        modules.parse_newc(decoded, "candidate")[1])
    rebuilt = builder.candidate_cpio(run36_cpio, builder.TRIGGER)
    require(vendor.encode_frame(rebuilt, library) == expected and
            builder.assemble(stock, expected)[0] == candidate,
            "candidate differs from the reproducible builder output")
    return digest, order, outside, decoded, expected


def self_test(candidate, run36, stock, source, boot, vendor_boot, recovery, config, kernel,
              decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs_binary,
              sharedmem, maps):
    library = base.lz4()
    digest, order, outside, cpio, frame = check_candidate(
        candidate, run36, stock, source, boot, vendor_boot, recovery, config, kernel,
        decompressor, pstore, helper_input, pdmapper, tqftpserv, rmtfs_binary, sharedmem,
        maps, library)
    print(f"init_boot wpss-boot fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")

    def rebuild(changed_entries):
        payload = modules.encode_newc(changed_entries, trailer)
        return static.peripheral.assemble(stock, vendor.encode_frame(payload, library))[0]

    def with_trigger(data=None, mode=None, drop=False):
        changed = []
        for entry in entries:
            if entry["name"] == "bin/wpss-once" and drop:
                continue
            item = dict(entry)
            if entry["name"] == "bin/wpss-once":
                if data is not None:
                    item = {**item, "data": data}
                if mode is not None:
                    item = {**item, "fields": item["fields"][:1] +
                            [mode] + item["fields"][2:], "mode": mode}
            changed.append(item)
        return changed

    def case(label, message, mutated):
        expect_rejection(label, message, check_candidate, mutated, run36, stock, source,
                         boot, vendor_boot, recovery, config, kernel, decompressor, pstore,
                         helper_input, pdmapper, tqftpserv, rmtfs_binary, sharedmem, maps,
                         library)

    case("changed signed tail", TAIL_MSG, rmtfs.flipped(candidate, TAIL_OFFSET + 100))
    case("nonzero kernel size", KERNEL_MSG,
         candidate[:8] + struct.pack("<I", 1) + candidate[12:])
    case("changed compressed block", BLOCK_MSG, rmtfs.flipped(candidate, PAGE + 64))
    case("wrong ramdisk-size field", FRAME_MSG, candidate[:RAMDISK_SIZE_OFFSET] +
         struct.pack("<I", len(frame) - 8) + candidate[RAMDISK_SIZE_OFFSET + 4:])
    case("nonzero gap", GAP_MSG, candidate[:PAGE + len(frame)] + b"\x01" +
         candidate[PAGE + len(frame) + 1:])
    case("short image", SIZE_MSG, candidate[:-PAGE])

    case("trigger removed", TRIGGER_MSG, rebuild(with_trigger(drop=True)))
    case("trigger mode not executable", TRIGGER_MSG,
         rebuild(with_trigger(mode=0o100444)))
    case("trigger bytes altered", TRIGGER_MSG,
         rebuild(with_trigger(data=builder.TRIGGER[:-40] + b"x" * 40)))
    case("trigger replaced by measured run-36 layout", TRIGGER_MSG, run36)
    case("trigger rewritten to write remoteproc state", TRIGGER_MSG,
         rebuild(with_trigger(data=builder.TRIGGER.replace(
             b">/sys/kernel/icnss/wpss_boot", b">/sys/class/remoteproc/remoteproc3/state"))))
    case("trigger one-shot marker removed", TRIGGER_MSG,
         rebuild(with_trigger(data=builder.TRIGGER.replace(
             b"/run/wpss-once.attempted", b"/tmp/wpss.marker"))))
    case("trigger precondition check weakened", TRIGGER_MSG,
         rebuild(with_trigger(data=builder.TRIGGER.replace(
             b'"$MODEM_STATE" != running', b'"$MODEM_STATE" != stopped'))))
    case("trigger timeout removed", TRIGGER_MSG,
         rebuild(with_trigger(data=builder.TRIGGER.replace(b"timeout -k 1 3 ", b""))))
    init_entries = [dict(entry) for entry in entries]
    init_entries = [{**entry, "data": builder.TRIGGER} if entry["name"] == "init"
                    else entry for entry in init_entries]
    case("init itself became the trigger", INIT_MSG, rebuild(init_entries))
    reworded = []
    for entry in entries:
        if entry["name"] == "init":
            entry = {**entry, "data": entry["data"].replace(
                b"session #96:", b"session #101:", 1)}
        reworded.append(entry)
    case("init marker reworded in place", INIT_MSG, rebuild(reworded))

    expect_rejection("reused measured run-36 image", SHA_MSG, reject_prior_sha,
                     builder.MEASURED_RUN36)
    expect_rejection("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    for prefix in REQUIRED_PRIOR:
        item = next((p for p in PRIOR_IMAGES if p.startswith(prefix)), None)
        require(item is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, item)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("wpss-boot negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(len(args) in (18, 19) and (len(args) == 18 or args[0] == "--self-test"),
            "usage: verify-init-boot-wpss-boot.py [--self-test] CANDIDATE RUN36 "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER TQFTPSERV RMTFS SHAREDMEM_KO "
            "BY_NAME MAPS_DIR")
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    blobs = [pathlib.Path(path).read_bytes() for path in args[:-2]]
    builder.prior.check_by_name(args[-2])
    maps = builder.prior.old_checker.builder.check_map_source(pathlib.Path(args[-1]))
    blobs.append(maps)
    if self_test_mode:
        self_test(*blobs)
        return
    digest, order, outside, cpio, frame = check_candidate(*blobs, base.lz4())
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
          f"list SHA-256 {modules.EUD_ORDER_SHA256}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"WPSS trigger: dormant one-shot helper bin/wpss-once, stock wpss_boot=1 write "
          f"only, {len(builder.TRIGGER)} B, SHA-256 {builder.TRIGGER_SHA256}")
    print("session init: byte-exact #96 run-36 init (bf2089c4); no WPSS or remoteproc "
          "write from init; the coordinator invokes the trigger once after the guarded "
          "modem start holds and DMS connects")
    print(f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} "
          f"/ {base.MAX_FRAME} bytes")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged")
    print(f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged")
    print("candidate SHA-256 differs from run-36 bf2089c4, 8dddb8c7, 35866d56, ae2ccff7, "
          "4216af26 and every other prior measured SHA")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
