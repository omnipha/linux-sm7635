#!/usr/bin/env python3
import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).parent


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build-init-boot-pid1-handoff.py", "pid1_handoff_builder")
modules = builder.modules
base = builder.base
vendor = builder.vendor
require = builder.require
SIZE_MSG = "candidate is not 8388608 bytes"
HEADER_MSG = "candidate header differs from pinned stock header v4"
TAIL_MSG = "candidate signed tail differs from pinned stock init_boot_a"
GAP_MSG = "candidate gap before signed tail is not zero"
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
FRAME_MSG = builder.FRAME_MSG
SHA_MSG = builder.SHA_MSG


def reject_sha(digest, refused=builder.REFUSED):
    require(digest not in refused, SHA_MSG)


def check_candidate(candidate, stock, run43, script, library, decode_frame):
    require(len(candidate) == base.IMAGE_SIZE, SIZE_MSG)
    original, trailer = builder.check_refs(stock, run43, library, decode_frame)
    digest = modules.sha256(candidate)
    reject_sha(digest)
    require(candidate[:8] == b"ANDROID!" and
            struct.unpack_from("<I", candidate, 40)[0] == 4 and
            struct.unpack_from("<I", candidate, 8)[0] == 0 and
            candidate[:base.RAMDISK_SIZE_OFFSET] == stock[:base.RAMDISK_SIZE_OFFSET] and
            candidate[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE], HEADER_MSG)
    require(candidate[base.TAIL_OFFSET:] == stock[base.TAIL_OFFSET:], TAIL_MSG)
    size = struct.unpack_from("<I", candidate, base.RAMDISK_SIZE_OFFSET)[0]
    require(8 < size <= base.MAX_FRAME, FRAME_MSG)
    require(not any(candidate[base.PAGE + size:base.TAIL_OFFSET]), GAP_MSG)
    frame = candidate[base.PAGE:base.PAGE + size]
    try:
        decoded = decode_frame(frame, library)
    except ValueError as exc:
        raise ValueError(FRAME_MSG) from exc
    require(vendor.encode_frame(decoded, library) == frame, FRAME_MSG)
    entries, new_trailer = modules.parse_newc(decoded, "handoff generic cpio")
    require(modules.encode_newc(entries, new_trailer) == decoded and
            len(entries) == len(original) and new_trailer == trailer and
            len({entry["name"] for entry in entries}) == len(entries) and
            not any(entry["name"].endswith(".ko") for entry in entries), CPIO_MSG)
    for left, right in zip(entries, original):
        require(left["name"] == right["name"] and
                left["mode"] == right["mode"] and
                left["fields"][:6] == right["fields"][:6] and
                left["fields"][7:] == right["fields"][7:] and
                (left["data"] == right["data"] or left["name"] == "init"), CPIO_MSG)
    original_init = next(entry["data"] for entry in original if entry["name"] == "init")
    init = next(entry["data"] for entry in entries if entry["name"] == "init")
    require(init == builder.expected_init(original_init, script), INIT_MSG)
    require(decoded == builder.candidate_cpio(original, trailer, script), CPIO_MSG)
    require(candidate == vendor.assemble(stock, frame)[0], FRAME_MSG)
    require(digest == builder.EXPECTED_SHA256, "candidate differs from reviewed PID1 image SHA-256")
    return digest, len(decoded), size


def self_test(candidate, stock, run43, script, library, decode_frame):
    digest, _, size = check_candidate(candidate, stock, run43, script, library, decode_frame)
    original, _ = builder.check_refs(stock, run43, library, decode_frame)
    init = next(entry["data"] for entry in original if entry["name"] == "init")
    require(init.count(builder.ANCHOR) == 1 and init.endswith(builder.ANCHOR), INIT_MSG)

    def bad(label, message, image, source=script):
        try:
            check_candidate(image, stock, run43, source, library, decode_frame)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture was accepted")

    def flipped(image, index):
        result = bytearray(image)
        result[index] ^= 1
        return bytes(result)

    def reframe(entries):
        _, trailer = modules.parse_newc(decode_frame(candidate[base.PAGE:base.PAGE + size], library),
                                         "candidate generic cpio")
        frame = vendor.encode_frame(modules.encode_newc(entries, trailer), library)
        header = bytearray(stock[:base.PAGE])
        struct.pack_into("<I", header, base.RAMDISK_SIZE_OFFSET, len(frame))
        return bytes(header) + frame + bytes(base.MAX_FRAME - len(frame)) + stock[base.TAIL_OFFSET:]

    def with_init(data):
        decoded = decode_frame(candidate[base.PAGE:base.PAGE + size], library)
        entries, _ = modules.parse_newc(decoded, "candidate generic cpio")
        return reframe([{**entry, "data": data} if entry["name"] == "init" else entry
                        for entry in entries])

    bad("short image", SIZE_MSG, candidate[:-base.PAGE])
    bad("header change", HEADER_MSG, flipped(candidate, 16))
    bad("kernel size", HEADER_MSG, flipped(candidate, 8))
    bad("tail change", TAIL_MSG, flipped(candidate, base.TAIL_OFFSET + 100))
    bad("footer change", TAIL_MSG, flipped(candidate, base.IMAGE_SIZE - 1))
    bad("gap change", GAP_MSG, flipped(candidate, base.PAGE + size))
    bad("frame bound", FRAME_MSG, candidate[:12] + struct.pack("<I", base.MAX_FRAME + 1) +
        candidate[16:])
    bad("frame length", FRAME_MSG, candidate[:12] + struct.pack("<I", size - 1) +
        candidate[16:])
    bad("compressed block", FRAME_MSG, flipped(candidate, base.PAGE + 16))
    bad("previous run-43", SHA_MSG, run43)
    bad("stock init_boot", SHA_MSG, stock)

    candidate_init = builder.expected_init(init, script)
    require(init.count(builder.previous.eud.TIMER) == 1 and
            init.index(builder.previous.eud.TIMER) <
            init.index(builder.ANCHOR) and
            candidate_init.count(builder.SETTLE) == 1 and
            candidate_init.count(builder.previous.eud.TIMER) == 1, INIT_MSG)
    bad("timer settle removed", INIT_MSG, with_init(candidate_init.replace(
        builder.SETTLE, b"", 1)))
    bad("timer settle shortened", INIT_MSG, with_init(candidate_init.replace(
        b"151.01", b"15.01", 1)))
    bad("timer settle hold bypassed", INIT_MSG, with_init(candidate_init.replace(
        b'[ -f /run/keep ] && [ ! -L /run/keep ]', b'[ -e /run ]', 1)))
    bad("timer settle uptime bypassed", INIT_MSG, with_init(candidate_init.replace(
        b"PID1_TIMER_SETTLED=failed", b"PID1_TIMER_SETTLED=1", 1)))
    bad("timer settle request bypassed", INIT_MSG, with_init(candidate_init.replace(
        b'pid1_request_valid; then', b'/bin/busybox true; then', 1)))
    bad("no background console", INIT_MSG, with_init(candidate_init.replace(
        b"setsid cttyhack /bin/sh &\n", builder.ANCHOR, 1)))
    bad("SSH child runs handoff", INIT_MSG, with_init(candidate_init.replace(
        b'. "$PID1_SCRIPT"', b'/bin/busybox sh "$PID1_SCRIPT"', 1)))
    bad("PID1 exec instead of sourced transition", INIT_MSG, with_init(candidate_init.replace(
        b'. "$PID1_SCRIPT"', b'exec /bin/busybox sh "$PID1_SCRIPT"', 1)))
    bad("missing PID1 identity", INIT_MSG, with_init(candidate_init.replace(
        b'[ "$$" = 1 ]', b'[ "$$" != 1 ]', 1)))
    bad("missing boot-id match", INIT_MSG, with_init(candidate_init.replace(
        b"/bin/busybox cmp -s - \"$PID1_REQUEST\"", b"/bin/busybox true", 1)))
    bad("request symlink allowed", INIT_MSG, with_init(candidate_init.replace(
        b'[ ! -L "$PID1_REQUEST" ]', b'[ -L "$PID1_REQUEST" ]', 1)))
    bad("run root-only guard removed", INIT_MSG, with_init(candidate_init.replace(
        b'" = 0:755 ]', b'" = 0:777 ]', 1)))
    bad("loose request mode", INIT_MSG, with_init(candidate_init.replace(
        b"0:600:1:37", b"0:644:1:37", 1)))
    bad("script symlink allowed", INIT_MSG, with_init(candidate_init.replace(
        b'[ ! -L "$PID1_SCRIPT" ]', b'[ -L "$PID1_SCRIPT" ]', 1)))
    bad("loose script mode", INIT_MSG, with_init(candidate_init.replace(
        b"0:700:1", b"0:755:1", 1)))
    bad("missing boot-id source", INIT_MSG, with_init(candidate_init.replace(
        b'/proc/sys/kernel/random/boot_id', b'/run/boot_id', 1)))
    bad("missing digest", INIT_MSG, with_init(candidate_init.replace(
        b"= \"$PID1_SHA256\"", b"= \"$PID1_BOOT_ID\"", 1)))
    bad("script executed in subshell", INIT_MSG, with_init(candidate_init.replace(
        b'if . "$PID1_SCRIPT"; then', b'if ( . "$PID1_SCRIPT" ); then', 1)))
    bad("no request cleanup", INIT_MSG, with_init(candidate_init.replace(
        b"/bin/busybox rm -f \"$PID1_REQUEST\"\n\t\t\tlog", b"/bin/busybox true\n\t\t\tlog", 1)))
    bad("marker only", INIT_MSG, with_init(init.replace(builder.ANCHOR,
        b"log 'pid1 handoff'\n" + builder.ANCHOR, 1)))
    bad("double handoff", INIT_MSG, with_init(candidate_init + builder.HANDOFF.replace(
        b"@SHA256@", modules.sha256(script).encode())))
    bad("wrong pinned script", INIT_MSG, candidate, script + b"\n")
    entries, _ = modules.parse_newc(decode_frame(candidate[base.PAGE:base.PAGE + size], library),
                                     "candidate generic cpio")
    altered = [{**entry, "mode": entry["mode"] ^ 1,
                "fields": [entry["fields"][0], entry["fields"][1] ^ 1, *entry["fields"][2:]]}
               if entry["name"] == "init" else entry for entry in entries]
    bad("init mode change", CPIO_MSG, reframe(altered))
    other = next(entry for entry in entries if entry["name"] not in ("init", "TRAILER!!!") and
                 entry["data"])
    bad("other entry change", CPIO_MSG, reframe([
        {**entry, "data": entry["data"] + b"x"} if entry["name"] == other["name"] else entry
        for entry in entries]))
    for sha in builder.REFUSED:
        try:
            reject_sha(sha)
        except ValueError as exc:
            require(str(exc) == SHA_MSG, "refused SHA rejection changed")
        else:
            raise ValueError(f"refused SHA accepted: {sha}")
    require(builder.RUN43_SHA256 in builder.REFUSED and base.STOCK_SHA256 in builder.REFUSED and
            len(builder.REFUSED) == len(previous_shas()), "refused SHA inventory incomplete")
    print(f"negative mutations: OK; {len(builder.REFUSED)} refused image hashes; candidate {digest}")


def previous_shas():
    return {*builder.previous.PRIOR_IMAGES, builder.RUN43_SHA256}


def main():
    args = sys.argv[1:]
    testing = args[:1] == ["--self-test"]
    if testing:
        args = args[1:]
    require(len(args) == 5 and args[3] == "--script",
            "usage: verify-init-boot-pid1-handoff.py [--self-test] CANDIDATE STOCK_INIT RUN43 --script TRANSITION")
    candidate, stock, run43 = (pathlib.Path(path).read_bytes() for path in args[:3])
    script = builder.script_bytes(args[4])
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "pid1_prior_checker")
    library = base.lz4()
    if testing:
        self_test(candidate, stock, run43, script, library,
                  checker.hostkey_checker.decode_frame)
    digest, cpio_size, frame_size = check_candidate(candidate, stock, run43, script,
                                                     library, checker.hostkey_checker.decode_frame)
    print(f"verified: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"transition script SHA-256 {modules.sha256(script)}; cpio {cpio_size} bytes; "
          f"LZ4 HC-{base.HC_LEVEL} frame {frame_size}/{base.MAX_FRAME}; "
          f"gap {base.MAX_FRAME - frame_size}; signed tail unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
