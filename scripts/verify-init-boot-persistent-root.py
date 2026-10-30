#!/usr/bin/env python3
import importlib.util
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


builder = load("build-init-boot-persistent-root.py", "persistent_builder")
base = builder.base
vendor = builder.vendor
require = builder.require
SIZE_MSG = "candidate is not 8388608 bytes"
HEADER_MSG = "candidate header differs from pinned stock header v4"
TAIL_MSG = "candidate signed tail differs from pinned stock init_boot_a"
GAP_MSG = "candidate gap before signed tail is not zero"
BASE_MSG = builder.BASE_MSG
DELTA_MSG = builder.DELTA_MSG
INIT_MSG = builder.INIT_MSG
CPIO_MSG = builder.CPIO_MSG
FRAME_MSG = builder.FRAME_MSG
SHA_MSG = builder.SHA_MSG
BUNDLE_MSG = builder.builder.BUNDLE_MSG
GIT_MSG = "persistent-root archive or private profile is present in Git"


def check_candidate(candidate, stock, base_image, current, library, decode_frame):
    require(len(candidate) == base.IMAGE_SIZE, SIZE_MSG)
    require(base_image[:8] == b"ANDROID!" and base_image[:base.RAMDISK_SIZE_OFFSET] ==
            stock[:base.RAMDISK_SIZE_OFFSET] and
            base_image[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
            base_image[base.TAIL_OFFSET:] == stock[base.TAIL_OFFSET:], BASE_MSG)
    entries, trailer, _frame = builder.unpack_image(base_image, library, decode_frame)
    digest = builder.modules.sha256(candidate)
    require(digest not in builder.REFUSED, SHA_MSG)
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
    decoded = decode_frame(frame, library)
    require(vendor.encode_frame(decoded, library) == frame, FRAME_MSG)
    changed, new_trailer = builder.modules.parse_newc(decoded, "persistent-root generic cpio")
    require(len(changed) == len(entries) and new_trailer == trailer and
            [item["name"] for item in changed] == [item["name"] for item in entries], CPIO_MSG)
    for old, new in zip(entries, changed):
        require(old["name"] == new["name"] and old["mode"] == new["mode"] and
                old["fields"][:6] == new["fields"][:6] and old["fields"][7:] == new["fields"][7:] and
                (old["data"] == new["data"] or old["name"] in ("init", builder.builder.BUNDLE)), CPIO_MSG)
    base_entries, base_trailer, base_found, private = builder.base_state(base_image, library, decode_frame)
    require(base_trailer == trailer and base_entries == entries, BASE_MSG)
    found = builder.expected_found(base_found, current)
    original = next(item["data"] for item in entries if item["name"] == "init")
    init = next(item["data"] for item in changed if item["name"] == "init")
    blob = next(item["data"] for item in changed if item["name"] == builder.builder.BUNDLE)
    public = {name: found[name] for name in (*builder.builder.PUBLIC, "pmos-root-contract.sh")}
    require(blob == builder.builder.checked_bundle(
        builder.builder.bundle_bytes(public, private), public, private), BUNDLE_MSG)
    require(init == builder.expected_init(original, found), INIT_MSG)
    require(decoded == builder.candidate_cpio(entries, trailer, found, private), CPIO_MSG)
    require(candidate == vendor.assemble(stock, frame)[0], FRAME_MSG)
    return digest, len(decoded), size


def self_test(candidate, stock, base_image, current, library, decode_frame):
    digest, _decoded_size, size = check_candidate(candidate, stock, base_image, current, library, decode_frame)
    import subprocess
    proc = subprocess.run(["git", "-C", str(HERE.parent), "status", "--porcelain", "--ignored"],
                          check=True, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        name = line[3:].split(" -> ")[-1]
        require(not name.endswith((".img", ".tar", ".tar.xz", ".tar.gz")) and
                "wpa_supplicant.conf" not in name, GIT_MSG)

    def bad(label, message, image, source=current):
        try:
            check_candidate(image, stock, base_image, source, library, decode_frame)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture accepted")

    def flipped(image, index):
        result = bytearray(image)
        result[index] ^= 1
        return bytes(result)

    bad("short image", SIZE_MSG, candidate[:-base.PAGE])
    bad("header change", HEADER_MSG, flipped(candidate, 16))
    bad("tail change", TAIL_MSG, flipped(candidate, base.TAIL_OFFSET + 100))
    bad("gap change", GAP_MSG, flipped(candidate, base.PAGE + size))
    bad("stock init_boot", SHA_MSG, stock)
    bad("run-66 init_boot", SHA_MSG, base_image)
    changed = dict(current)
    changed["pmos-self-stage.sh"] += b"\n"
    bad("bundle mismatch", BUNDLE_MSG, candidate, changed)
    changed = dict(current)
    changed["pmos-root-contract.sh"] = changed["pmos-root-contract.sh"].replace(b"userdata", b"super")
    bad("super substitution", INIT_MSG, candidate, changed)
    changed = dict(current)
    changed["pmos-self-stage.sh"] = changed["pmos-self-stage.sh"].replace(b'"$wait_n" -lt 145', b'"$wait_n" -lt 146')
    bad("weakened hold", BUNDLE_MSG, candidate, changed)
    changed = dict(current)
    changed["pmos-pid1-guard.sh"] = changed["pmos-pid1-guard.sh"].replace(b"root_contract_switched_root", b"true")
    bad("weakened guard", BUNDLE_MSG, candidate, changed)
    changed = dict(current)
    changed["pmos-self-stage.sh"] = changed["pmos-self-stage.sh"].replace(b"PMOS_ROOT_KIND=ext4 ", b"")
    bad("root delta removed", BUNDLE_MSG, candidate, changed)
    for digest in builder.REFUSED:
        require(digest not in builder.REFUSED or digest != builder.modules.sha256(candidate), SHA_MSG)
    print(f"persistent-root negative mutations: OK; {len(builder.REFUSED)} refused image hashes; candidate {digest}")


def main():
    args = sys.argv[1:]
    testing = args[:1] == ["--self-test"]
    if testing:
        args = args[1:]
    require(len(args) == 3, "usage: verify-init-boot-persistent-root.py [--self-test] CANDIDATE STOCK_INIT BASE")
    candidate, stock, base_image = (pathlib.Path(path).read_bytes() for path in args)
    current = builder.current_scripts()
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "persistent_checker")
    library = base.lz4()
    if testing:
        self_test(candidate, stock, base_image, current, library, checker.hostkey_checker.decode_frame)
    digest, cpio_size, frame_size = check_candidate(
        candidate, stock, base_image, current, library, checker.hostkey_checker.decode_frame)
    print(f"verified persistent-root init_boot: {len(candidate)} bytes, SHA-256 {digest}")
    print(f"cpio {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame {frame_size}/{base.MAX_FRAME}; "
          f"gap {base.MAX_FRAME - frame_size}; signed tail unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
