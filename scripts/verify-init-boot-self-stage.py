#!/usr/bin/env python3
import importlib.util
import io
import lzma
import pathlib
import struct
import sys
import tarfile

HERE = pathlib.Path(__file__).parent


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build-init-boot-self-stage.py", "self_stage_builder")
modules = builder.modules
base = builder.base
vendor = builder.vendor
prior = builder.prior
require = builder.require
SIZE_MSG = "candidate is not 8388608 bytes"
HEADER_MSG = "candidate header differs from pinned stock header v4"
TAIL_MSG = "candidate signed tail differs from pinned stock init_boot_a"
GAP_MSG = "candidate gap before signed tail is not zero"
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
FRAME_MSG = builder.FRAME_MSG
SHA_MSG = builder.SHA_MSG
BUNDLE_MSG = builder.BUNDLE_MSG
GIT_MSG = "self-stage archive or private profile is present in Git"


def reject_sha(digest):
    require(digest not in builder.REFUSED, SHA_MSG)


def check_candidate(candidate, stock, previous, found, private, library, decode_frame):
    require(len(candidate) == base.IMAGE_SIZE, SIZE_MSG)
    original, trailer = builder.source_entries(stock, previous, library, decode_frame)
    digest = modules.sha256(candidate)
    reject_sha(digest)
    require(candidate[:8] == b"ANDROID!" and struct.unpack_from("<I", candidate, 40)[0] == 4 and
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
    entries, new_trailer = modules.parse_newc(decoded, "self-stage generic cpio")
    require(len(entries) == len(original) + 1 and new_trailer == trailer and
            entries[-1]["name"] == builder.BUNDLE and
            len({entry["name"] for entry in entries}) == len(entries), CPIO_MSG)
    for left, right in zip(entries, original):
        require(left["name"] == right["name"] and left["mode"] == right["mode"] and
                left["fields"][:6] == right["fields"][:6] and
                left["fields"][7:] == right["fields"][7:] and
                (left["data"] == right["data"] or left["name"] == "init"), CPIO_MSG)
    require(entries[-1]["mode"] & 0o170777 == 0o100600 and
            entries[-1]["data"] == builder.checked_bundle(
                builder.bundle_bytes(found, private), found, private), BUNDLE_MSG)
    original_init = next(entry["data"] for entry in original if entry["name"] == "init")
    init = next(entry["data"] for entry in entries if entry["name"] == "init")
    require(init == builder.expected_init(original_init, found, private) and
            init.count(prior.SETTLE) == 1 and init.count(prior.previous.eud.TIMER) == 1 and
            init.count(builder.hook(found, private)) == 1, INIT_MSG)
    require(decoded == builder.candidate_cpio(original, trailer, found, private), CPIO_MSG)
    require(candidate == vendor.assemble(stock, frame)[0], FRAME_MSG)
    return digest, len(decoded), size


def git_clean():
    import subprocess
    proc = subprocess.run(["git", "-C", str(HERE.parent), "status", "--porcelain", "--ignored"],
                          check=True, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        path = line[3:].split(" -> ")[-1]
        require(not path.endswith((".img", ".tar", ".tar.xz", ".tar.gz")) and
                "wpa_supplicant.conf" not in path, GIT_MSG)


def self_test(candidate, stock, previous, found, private, library, decode_frame):
    digest, _, size = check_candidate(candidate, stock, previous, found, private,
                                      library, decode_frame)
    original, _ = builder.source_entries(stock, previous, library, decode_frame)
    init = next(entry["data"] for entry in original if entry["name"] == "init")
    git_clean()

    def bad(label, message, image, source=found, secret=private):
        try:
            check_candidate(image, stock, previous, source, secret, library, decode_frame)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture was accepted")

    def flipped(image, index):
        result = bytearray(image)
        result[index] ^= 1
        return bytes(result)

    def reframe(entries):
        decoded = decode_frame(candidate[base.PAGE:base.PAGE + size], library)
        _, trailer = modules.parse_newc(decoded, "candidate generic cpio")
        frame = vendor.encode_frame(modules.encode_newc(entries, trailer), library)
        header = bytearray(stock[:base.PAGE])
        struct.pack_into("<I", header, base.RAMDISK_SIZE_OFFSET, len(frame))
        return bytes(header) + frame + bytes(base.MAX_FRAME - len(frame)) + stock[base.TAIL_OFFSET:]

    def entries():
        decoded = decode_frame(candidate[base.PAGE:base.PAGE + size], library)
        parsed, _ = modules.parse_newc(decoded, "candidate generic cpio")
        return parsed

    def with_init(data):
        return reframe([{**entry, "data": data} if entry["name"] == "init" else entry
                        for entry in entries()])

    bad("short image", SIZE_MSG, candidate[:-base.PAGE])
    bad("header change", HEADER_MSG, flipped(candidate, 16))
    bad("tail change", TAIL_MSG, flipped(candidate, base.TAIL_OFFSET + 100))
    bad("gap change", GAP_MSG, flipped(candidate, base.PAGE + size))
    bad("frame bound", FRAME_MSG, candidate[:12] + struct.pack("<I", base.MAX_FRAME + 1) +
        candidate[16:])
    bad("compressed block", FRAME_MSG, flipped(candidate, base.PAGE + 16))
    bad("previous image", SHA_MSG, previous)
    bad("stock init_boot", SHA_MSG, stock)
    built = builder.expected_init(init, found, private)
    timer = prior.previous.eud.TIMER
    bad("timer duplicated", INIT_MSG, with_init(built.replace(timer, timer + timer, 1)))
    bad("timer removed", INIT_MSG, with_init(built.replace(timer, b"", 1)))
    bad("settle hold removed", INIT_MSG, with_init(built.replace(prior.SETTLE, b"", 1)))
    handoff = prior.HANDOFF.replace(
        b"@SHA256@", modules.sha256(found["pmos-pid1-transition.sh"]).encode())
    require(built.endswith(handoff[len(b"setsid cttyhack /bin/sh &\n"):]) and
            built.count(b"pid1_request_valid() {") == 1, INIT_MSG)
    bad("handoff removed", INIT_MSG, with_init(built.replace(
        b"pid1_request_valid() {", b"pid1_request_missing() {", 1)))
    bad("handoff duplicated", INIT_MSG, with_init(built + handoff))
    changed = dict(found)
    changed["pmos-self-stage.sh"] += b"\n"
    bad("bundle mismatch", BUNDLE_MSG, candidate, changed)
    leaked = dict(found)
    leaked["pmos-self-post.sh"] = b"#!/bin/busybox sh\n# " + private[:16] + b"\n"
    bad("profile bytes inside bundle", BUNDLE_MSG, candidate, leaked)
    require(modules.sha256(private).encode() not in init and
            modules.sha256(private).encode() not in
            next(entry["data"] for entry in entries() if entry["name"] == "init") and
            private not in candidate, GIT_MSG)
    present = [entry for entry in entries() if entry["name"] == builder.BUNDLE]
    bad("bundle removed", CPIO_MSG, reframe(entry for entry in entries()
                                            if entry["name"] != builder.BUNDLE))
    bad("bundle duplicated", CPIO_MSG, reframe([*entries(), present[0]]))
    for sha in builder.REFUSED:
        try:
            reject_sha(sha)
        except ValueError as exc:
            require(str(exc) == SHA_MSG, "refused SHA rejection changed")
        else:
            raise ValueError(f"refused SHA accepted: {sha}")
    require(builder.BUNDLE not in git_paths() and "wpa_supplicant.conf" not in git_paths(), GIT_MSG)
    print(f"negative mutations: OK; {len(builder.REFUSED)} refused image hashes; candidate {digest}")


def git_paths():
    import subprocess
    proc = subprocess.run(["git", "-C", str(HERE.parent), "ls-files"],
                          check=True, capture_output=True, text=True)
    return proc.stdout.splitlines()


def main():
    args = sys.argv[1:]
    testing = args[:1] == ["--self-test"]
    if testing:
        args = args[1:]
    require(len(args) == 3,
            "usage: verify-init-boot-self-stage.py [--self-test] CANDIDATE STOCK_INIT PREVIOUS")
    candidate, stock, previous = (pathlib.Path(path).read_bytes() for path in args)
    found, private, ready = builder.members(False)
    require(ready, builder.DEFER_MSG)
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "self_stage_checker")
    library = base.lz4()
    if testing:
        self_test(candidate, stock, previous, found, private, library,
                  checker.hostkey_checker.decode_frame)
    digest, cpio_size, frame_size = check_candidate(
        candidate, stock, previous, found, private, library,
        checker.hostkey_checker.decode_frame)
    print(f"verified: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"cpio {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame {frame_size}/{base.MAX_FRAME}; "
          f"gap {base.MAX_FRAME - frame_size}; signed tail unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError,
            tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
