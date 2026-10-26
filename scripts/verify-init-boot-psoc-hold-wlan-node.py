#!/usr/bin/env python3
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


builder = load(
    "build-init-boot-psoc-hold-wlan-node-payload.py", "psoc_hold_wlan_node_builder"
)
hostkey_checker = load(
    "verify-init-boot-psoc-hold-capture-hostkey.py", "psoc_hold_capture_hostkey_checker"
)
hostkey = builder.hostkey
capture = builder.capture
psoc = builder.psoc
prior = builder.prior
base = builder.base
modules = builder.modules
eud = builder.eud
vendor = eud.vendor
PAGE = base.PAGE
IMAGE_SIZE = base.IMAGE_SIZE
TAIL_OFFSET = base.TAIL_OFFSET
RAMDISK_SIZE_OFFSET = base.RAMDISK_SIZE_OFFSET
PRIOR_IMAGES = builder.PRIOR_IMAGES
REQUIRED_PRIOR = (*hostkey_checker.REQUIRED_PRIOR, "8b62520f")
require = hostkey_checker.require
expect_rejection = hostkey_checker.expect_rejection
SIZE_MSG = hostkey_checker.SIZE_MSG
KERNEL_MSG = hostkey_checker.KERNEL_MSG
HEADER_MSG = hostkey_checker.HEADER_MSG
FRAME_MSG = hostkey_checker.FRAME_MSG
BLOCK_MSG = hostkey_checker.BLOCK_MSG
GAP_MSG = hostkey_checker.GAP_MSG
TAIL_MSG = hostkey_checker.TAIL_MSG
SHA_MSG = builder.SHA_MSG
KO_MSG = hostkey_checker.KO_MSG
ENVELOPE_MSG = hostkey_checker.ENVELOPE_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
TRIGGER_MSG = builder.TRIGGER_MSG
KEY_MSG = builder.KEY_MSG
NODE_MSG = builder.NODE_MSG
NODE_ANCHOR = builder.NODE_ANCHOR
NODE_PHASE = builder.NODE_PHASE
ON_WRITE = hostkey_checker.ON_WRITE
HOLD_CAP = hostkey_checker.HOLD_CAP
WPSS_PATH = hostkey_checker.WPSS_PATH
HOST_KEY_DIR = builder.HOST_KEY_DIR
HOST_KEY_PATH = builder.HOST_KEY_PATH


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def check_candidate(
    candidate,
    run42,
    run41,
    run39,
    run38,
    run37,
    stock,
    source,
    boot,
    vendor_boot,
    recovery,
    config,
    kernel,
    decompressor,
    pstore,
    helper_input,
    pdmapper,
    tqftpserv,
    rmtfs_binary,
    sharedmem,
    maps,
    library,
    blob,
):
    require(len(candidate) == IMAGE_SIZE, SIZE_MSG)
    require(struct.unpack_from("<I", candidate, 8)[0] == 0, KERNEL_MSG)
    require(
        modules.sha256(run42) == builder.MEASURED_RUN42 and len(run42) == IMAGE_SIZE,
        "run-42 reference is not the measured 8b62520f image",
    )
    digest42, order, outside, run42_cpio, _, _ = hostkey_checker.check_candidate(
        run42,
        run41,
        run39,
        run38,
        run37,
        stock,
        source,
        boot,
        vendor_boot,
        recovery,
        config,
        kernel,
        decompressor,
        pstore,
        helper_input,
        pdmapper,
        tqftpserv,
        rmtfs_binary,
        sharedmem,
        maps,
        library,
        blob,
    )

    frame_size = struct.unpack_from("<I", candidate, RAMDISK_SIZE_OFFSET)[0]
    require(0 < frame_size <= base.MAX_FRAME, FRAME_MSG)
    decoded = hostkey_checker.decode_frame(candidate[PAGE : PAGE + frame_size], library)
    entries, _ = modules.parse_newc(decoded, "candidate debug cpio")
    require(not any(entry["name"].endswith(".ko") for entry in entries), KO_MSG)
    by_name = {}
    for entry in entries:
        require(entry["name"] not in by_name, CPIO_MSG)
        by_name[entry["name"]] = entry

    run42_entries, _ = modules.parse_newc(run42_cpio, "run-42 debug cpio")
    run42_by_name = {entry["name"]: entry for entry in run42_entries}
    run42_init = run42_by_name["init"]["data"]
    run42_trigger = run42_by_name["bin/wpss-once"]["data"]

    init = by_name["init"]["data"]
    trigger = by_name["bin/wpss-once"]["data"]
    require(by_name["init"]["mode"] & 0o170777 == 0o100755, INIT_MSG)
    require(by_name["bin/wpss-once"]["mode"] & 0o170777 == 0o100755, TRIGGER_MSG)
    require(trigger == run42_trigger, TRIGGER_MSG)
    builder.check_init(init, run42_init)
    builder.check_trigger(trigger)
    require(trigger.count(ON_WRITE) == 1 and trigger.count(HOLD_CAP) == 1, TRIGGER_MSG)
    require(
        trigger.count(WPSS_PATH) == psoc.OLD_TRIGGER.count(WPSS_PATH)
        and trigger.count(b'printf "1\\n" >/sys/kernel/icnss/wpss_boot') == 1,
        TRIGGER_MSG,
    )
    require(
        init.count(eud.TIMER) == 1
        and init.count(b"sleep 150") == 1
        and init.count(b"/run/keep") == 1
        and b"/run/keep" not in init[: init.index(eud.TIMER)],
        INIT_MSG,
    )
    require(
        init.count(hostkey.DROPBEAR_CMD) == 1
        and init.count(hostkey.GENERATED_CMD) == 0
        and init.count(b"/bin/dropbear -R") == 0,
        INIT_MSG,
    )
    require(set(by_name) == set(run42_by_name), CPIO_MSG)
    for name, entry in run42_by_name.items():
        mine = by_name[name]
        require(
            mine["mode"] == entry["mode"]
            and (mine["data"] == entry["data"] or name == "init"),
            CPIO_MSG,
        )
    require(
        [entry["name"] for entry in entries]
        == [entry["name"] for entry in run42_entries],
        CPIO_MSG,
    )
    require(
        init.index(NODE_PHASE) < init.index(b"log 'console ready'\n")
        and init.index(NODE_PHASE) > init.index(NODE_ANCHOR)
        and init.index(NODE_PHASE) > init.index(b"qca_cld3_qca6750.ko\n"),
        NODE_MSG,
    )
    require(
        init.replace(NODE_PHASE, b"", 1) == run42_init
        and b"wpss-once" not in init
        and b"/sys/kernel/icnss/wpss_boot" not in init,
        INIT_MSG,
    )

    expected = vendor.encode_frame(decoded, library)
    require(expected == candidate[PAGE : PAGE + frame_size], BLOCK_MSG)
    require(len(expected) <= base.MAX_FRAME, ENVELOPE_MSG)
    require(
        candidate[:RAMDISK_SIZE_OFFSET] == stock[:RAMDISK_SIZE_OFFSET]
        and candidate[RAMDISK_SIZE_OFFSET + 4 : PAGE]
        == stock[RAMDISK_SIZE_OFFSET + 4 : PAGE],
        HEADER_MSG,
    )
    require(not any(candidate[PAGE + frame_size : TAIL_OFFSET]), GAP_MSG)
    require(candidate[TAIL_OFFSET:] == stock[TAIL_OFFSET:], TAIL_MSG)

    digest = modules.sha256(candidate)
    reject_prior_sha(digest)
    rebuilt = builder.candidate_cpio(
        run42_cpio, blob, hostkey_checker.pinned_public(blob)
    )
    require(
        vendor.encode_frame(rebuilt, library) == expected
        and builder.assemble(stock, expected)[0] == candidate,
        "candidate differs from the reproducible builder output",
    )
    del digest42
    return digest, order, outside, decoded, expected


def self_test(
    candidate,
    run42,
    run41,
    run39,
    run38,
    run37,
    stock,
    source,
    boot,
    vendor_boot,
    recovery,
    config,
    kernel,
    decompressor,
    pstore,
    helper_input,
    pdmapper,
    tqftpserv,
    rmtfs_binary,
    sharedmem,
    maps,
    library,
    blob,
):
    digest, order, outside, cpio, frame = check_candidate(
        candidate,
        run42,
        run41,
        run39,
        run38,
        run37,
        stock,
        source,
        boot,
        vendor_boot,
        recovery,
        config,
        kernel,
        decompressor,
        pstore,
        helper_input,
        pdmapper,
        tqftpserv,
        rmtfs_binary,
        sharedmem,
        maps,
        library,
        blob,
    )
    print(f"init_boot psoc-hold-wlan-node fixture: OK ({digest})")
    print(f"closure: {len(order)} modules, {len(outside)} outside modules.load")

    entries, trailer = modules.parse_newc(cpio, "candidate debug cpio")

    def rebuild(changed_entries):
        payload = modules.encode_newc(changed_entries, trailer)
        return psoc.prior.prior.prior.prior.prior.static.peripheral.assemble(
            stock, vendor.encode_frame(payload, library)
        )[0]

    def with_entry(name, data):
        return [
            {**entry, "data": data} if entry["name"] == name else entry
            for entry in entries
        ]

    def case(label, message, mutated):
        expect_rejection(
            label,
            message,
            check_candidate,
            mutated,
            run42,
            run41,
            run39,
            run38,
            run37,
            stock,
            source,
            boot,
            vendor_boot,
            recovery,
            config,
            kernel,
            decompressor,
            pstore,
            helper_input,
            pdmapper,
            tqftpserv,
            rmtfs_binary,
            sharedmem,
            maps,
            library,
            blob,
        )

    case(
        "changed signed tail",
        TAIL_MSG,
        hostkey_checker.capture_checker.wpss.rmtfs.flipped(
            candidate, TAIL_OFFSET + 100
        ),
    )
    case(
        "nonzero kernel size",
        KERNEL_MSG,
        candidate[:8] + struct.pack("<I", 1) + candidate[12:],
    )
    case(
        "changed compressed block",
        BLOCK_MSG,
        hostkey_checker.capture_checker.wpss.rmtfs.flipped(candidate, PAGE + 64),
    )
    case(
        "wrong ramdisk-size field",
        FRAME_MSG,
        candidate[:RAMDISK_SIZE_OFFSET]
        + struct.pack("<I", len(frame) - 8)
        + candidate[RAMDISK_SIZE_OFFSET + 4 :],
    )
    case(
        "nonzero gap",
        GAP_MSG,
        candidate[: PAGE + len(frame)] + b"\x01" + candidate[PAGE + len(frame) + 1 :],
    )
    case("short image", SIZE_MSG, candidate[:-PAGE])

    init = next(entry["data"] for entry in entries if entry["name"] == "init")
    trigger = next(
        entry["data"] for entry in entries if entry["name"] == "bin/wpss-once"
    )

    case(
        "wlan-node phase removed",
        NODE_MSG,
        rebuild(with_entry("init", init.replace(NODE_PHASE, b"", 1))),
    )
    case(
        "wlan-node phase duplicated",
        NODE_MSG,
        rebuild(
            with_entry("init", init.replace(NODE_PHASE, NODE_PHASE + NODE_PHASE, 1))
        ),
    )
    case(
        "wlan-node phase moved after console ready",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(NODE_PHASE, b"", 1).replace(
                    b"log 'console ready'\n", b"log 'console ready'\n" + NODE_PHASE, 1
                ),
            )
        ),
    )
    case(
        "wlan-node phase moved before the WLAN closure",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(NODE_PHASE, b"", 1).replace(
                    b"log 'wlan-init: begin'\n",
                    b"log 'wlan-init: begin'\n" + NODE_PHASE,
                    1,
                ),
            )
        ),
    )
    case(
        "wlan-node major hardcoded to 495",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b'mknod -m 0600 /dev/wlan c "$WLAN_MAJOR" "$WLAN_MINOR"',
                    b"mknod -m 0600 /dev/wlan c 495 0",
                    1,
                ),
            )
        ),
    )
    case(
        "wlan-node minor hardcoded to 0",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b'mknod -m 0600 /dev/wlan c "$WLAN_MAJOR" "$WLAN_MINOR"',
                    b'mknod -m 0600 /dev/wlan c "$WLAN_MAJOR" 0',
                    1,
                ),
            )
        ),
    )
    case(
        "wlan-node /proc/devices cross-check removed",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b"WLAN_COUNT=0", b"WLAN_COUNT=1\nWLAN_REG_FIRST=$WLAN_MAJOR", 1
                ).replace(
                    b'if [ "$WLAN_COUNT" -ne 1 ] || [ -z "$WLAN_REG_FIRST" ] || '
                    b'[ "$WLAN_REG_FIRST" != "$WLAN_MAJOR" ]; then',
                    b'if [ "$WLAN_COUNT" -ne 1 ]; then',
                    1,
                ),
            )
        ),
    )
    case(
        "wlan-node class-absent guard removed",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b"if [ ! -e /sys/class/wlan/wlan ]; then", b"if false; then", 1
                ),
            )
        ),
    )
    case(
        "wlan-node verify step removed",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b"elif ! [ -c /dev/wlan ]; then", b"elif false; then", 1
                ).replace(b"elif ! WLAN_GOT=", b"elif WLAN_GOT=", 1),
            )
        ),
    )
    case(
        "wlan-node mode loosened to 0666",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(b"mknod -m 0600 /dev/wlan", b"mknod -m 0666 /dev/wlan", 1),
            )
        ),
    )
    case(
        "wlan-node mknod retry injected",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b'log "wlan-node: rejected: mknod /dev/wlan c $WLAN_MAJOR '
                    b'$WLAN_MINOR failed or timed out; no node, no WPSS helper"',
                    b'/bin/busybox mknod -m 0600 /dev/wlan c "$WLAN_MAJOR" '
                    b'"$WLAN_MINOR"\nlog "wlan-node: rejected: mknod /dev/wlan c '
                    b"$WLAN_MAJOR $WLAN_MINOR failed or timed out; no node, "
                    b'no WPSS helper"',
                    1,
                ),
            )
        ),
    )
    case(
        "wlan-node second mknod attempt injected",
        NODE_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b"log 'wlan-node phase end'",
                    b"NODE_PHASE_REDO=1\nlog 'wlan-node phase end'",
                    1,
                ),
            )
        ),
    )
    case(
        "WPSS helper started from init",
        INIT_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b"log 'console ready'\n",
                    b"/bin/wpss-once\nlog 'console ready'\n",
                    1,
                ),
            )
        ),
    )
    case(
        "wpss_boot write injected into init",
        INIT_MSG,
        rebuild(
            with_entry("init", init + b"printf '1\\n' >/sys/kernel/icnss/wpss_boot\n")
        ),
    )
    case(
        "/dev/wlan ON write injected into init",
        INIT_MSG,
        rebuild(with_entry("init", init + b"printf 'ON             ' >/dev/wlan\n")),
    )
    case(
        "helper trigger changed",
        TRIGGER_MSG,
        rebuild(with_entry("bin/wpss-once", trigger.replace(psoc.HOLD_START, b"", 1))),
    )
    case(
        "second WPSS write injected into the helper",
        TRIGGER_MSG,
        rebuild(
            with_entry(
                "bin/wpss-once",
                trigger.replace(
                    psoc.WPSS_RESULT,
                    psoc.WPSS_RESULT + b"printf '1\\n' >/sys/kernel/icnss/wpss_boot\n",
                    1,
                ),
            )
        ),
    )
    case(
        "150 s timer lengthened",
        INIT_MSG,
        rebuild(
            with_entry("init", init.replace(b"\tsleep 150\n", b"\tsleep 180\n", 1))
        ),
    )
    case(
        "/run/keep escape disabled",
        INIT_MSG,
        rebuild(
            with_entry(
                "init",
                init.replace(
                    b"\tif [ ! -e /run/keep ]; then\n", b"\tif false; then\n", 1
                ),
            )
        ),
    )
    case(
        "host key invocation removed",
        INIT_MSG,
        rebuild(with_entry("init", init.replace(hostkey.DROPBEAR_CMD, b"", 1))),
    )
    case(
        "#116 session marker altered",
        INIT_MSG,
        rebuild(with_entry("init", init.replace(capture.MARKER, b"", 1))),
    )
    case("reused measured run-42 image", NODE_MSG, run42)
    case("reused unflashed run-41 image", NODE_MSG, run41)

    expect_rejection(
        "reused measured run-42 image",
        SHA_MSG,
        reject_prior_sha,
        builder.MEASURED_RUN42,
    )
    expect_rejection(
        "reused unflashed run-41 image",
        SHA_MSG,
        reject_prior_sha,
        builder.hostkey_builder.MEASURED_RUN41,
    )
    expect_rejection(
        "repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,)
    )
    for prefix in REQUIRED_PRIOR:
        item = next((p for p in PRIOR_IMAGES if p.startswith(prefix)), None)
        require(item is not None, f"missing prior SHA {prefix}")
        expect_rejection(f"repeated {prefix} SHA", SHA_MSG, reject_prior_sha, item)
    require(len(set(PRIOR_IMAGES)) == len(PRIOR_IMAGES), "duplicate prior SHA")
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    print("psoc-hold-wlan-node negative fixtures: OK")


def main():
    args = sys.argv[1:]
    require(
        len(args) in (23, 24) and (len(args) == 23 or args[0] == "--self-test"),
        "usage: verify-init-boot-psoc-hold-wlan-node.py [--self-test] CANDIDATE "
        "RUN42 RUN41 RUN39 RUN38 RUN37 STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR "
        "RECOVERY CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER PDMAPPER "
        "TQFTPSERV RMTFS SHAREDMEM_KO BY_NAME MAPS_DIR HOSTKEY",
    )
    self_test_mode = args[:1] == ["--self-test"]
    if self_test_mode:
        args = args[1:]
    hostkey_checker.check_input(args[-1])
    blob = pathlib.Path(args[-1]).read_bytes()
    hostkey_checker.pinned_public(blob)
    blobs = [pathlib.Path(path).read_bytes() for path in args[:-3]]
    psoc.prior.prior.prior.check_by_name(args[-3])
    maps = psoc.prior.prior.prior.old_checker.builder.check_map_source(
        pathlib.Path(args[-2])
    )
    blobs.append(maps)
    blobs.append(blob)
    library = base.lz4()
    if self_test_mode:
        self_test(*blobs[:-1], library, blobs[-1])
        return
    digest, order, outside, cpio, frame = check_candidate(
        *blobs[:-1], library, blobs[-1]
    )
    print(f"candidate: {IMAGE_SIZE} bytes, SHA-256 {digest}")
    print(
        f"pinned Dropbear host fingerprint: "
        f"{hostkey.public_fingerprint(hostkey_checker.pinned_public(blob))}"
    )
    print(
        f"closure: {len(order)} modules, {len(outside)} outside modules.load, "
        f"list SHA-256 {modules.EUD_ORDER_SHA256}"
    )
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(
        "session delta: from the measured run-42 #120 image (8b62520f), only the "
        "fail-closed wlan-node phase differs; it is placed after the qca_cld3 load "
        "and before console ready, reads the live /sys/class/wlan/wlan/dev, "
        "cross-checks the qcwlanstate major against /proc/devices, mknods /dev/wlan "
        "mode 0600 only on an exact one-pair match, verifies the character device "
        "and its exact major:minor, removes a mismatched node and never retries; "
        "bin/wpss-once, the 25 s ON hold, the 150 s timer, /run/keep, the pinned "
        "host key, the modem-holding stack and the 21-module WLAN closure are "
        "byte-exact #120"
    )
    print(
        f"ramdisk: one Android LZ4 legacy block, HC level {base.HC_LEVEL}, {len(frame)} "
        f"/ {base.MAX_FRAME} bytes"
    )
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged")
    print(
        f"signed tail: {IMAGE_SIZE - TAIL_OFFSET} bytes from {TAIL_OFFSET}, unchanged"
    )
    print(
        "candidate SHA-256 differs from the measured run-42 8b62520f, unflashed "
        "run-41 7c3d915f, run-39 0b40ac34, run-38 e75c5bd2, run-37 d9d8d2b8, "
        "run-36 bf2089c4 and every other prior measured SHA"
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
