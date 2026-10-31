#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import lzma
import pathlib
import struct
import sys
import tarfile

HERE = pathlib.Path(__file__).parent
OLD_IMAGE = pathlib.Path.home() / "sm7635-build" / "out" / "init_boot-persistent-root.img"
OLD_SHA = "ef476d8cbf3cba31fc143680d53b9aaf687cadd0409ad6dcf93c018bd97a233b"
RUN69_INIT = "2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28"
RUN69_CARRIER = "f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095"
RUN72_INIT = "3c97c918ed085d6d72530f00bba81c053130c184d351f372a10ac11b616bc71a"


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
CARRIER_MSG = builder.CARRIER_MSG
GIT_MSG = "persistent-root archive or private profile is present in Git"
OLD_MSG = "reconstructed ef476d8c bundle or launch was accepted"
OVERFLOW_MSG = "raw pinned root contract exceeds the fixed LZ4 envelope"


def refused():
    values = set(builder.REFUSED)
    values.update((OLD_SHA, RUN69_INIT, RUN69_CARRIER, RUN72_INIT))
    return frozenset(values)


def changed_cpio(image, library, decode_frame):
    size = struct.unpack_from("<I", image, base.RAMDISK_SIZE_OFFSET)[0]
    require(8 < size <= base.MAX_FRAME, FRAME_MSG)
    frame = image[base.PAGE:base.PAGE + size]
    decoded = decode_frame(frame, library)
    require(vendor.encode_frame(decoded, library) == frame, FRAME_MSG)
    entries, trailer = builder.modules.parse_newc(decoded, "persistent-root generic cpio")
    return decoded, entries, trailer, frame, size


def member_map(blob):
    require(blob.startswith(b"\xfd7zXZ\x00"), BUNDLE_MSG)
    raw = lzma.decompress(blob, format=lzma.FORMAT_XZ)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        infos = archive.getmembers()
        require([item.name for item in infos] == sorted(item.name for item in infos), BUNDLE_MSG)
        found = {}
        for item in infos:
            mode = 0o600 if item.name == builder.builder.PRIVATE else 0o700
            require(item.isfile() and not item.issym() and item.name not in found and
                    item.mode == mode and item.uid == 0 and item.gid == 0 and item.mtime == 0 and
                    item.uname == "" and item.gname == "", BUNDLE_MSG)
            found[item.name] = archive.extractfile(item).read()
    return found


def check_carrier(carrier, stock_carrier, blob):
    require(len(stock_carrier) == builder.CARRIER_SIZE and
            hashlib.sha256(stock_carrier).hexdigest() == builder.CARRIER_SHA and
            stock_carrier[:8] == b"VNDRBOOT" and
            stock_carrier[18255872:18255876] == b"AVB0" and
            stock_carrier[-64:-60] == b"AVBf" and
            not any(stock_carrier[builder.CARRIER_PREFIX:-64]), CARRIER_MSG)
    image = builder.carrier_image(stock_carrier, blob)
    header = builder.carrier_header(blob)
    require(len(carrier) == builder.CARRIER_SIZE and carrier == image, CARRIER_MSG)
    text = header.rstrip(b"\x00")
    require(len(header) == 4096 and text.startswith(builder.CARRIER_MARKER) and
            text.isascii() and b"\0" not in text and not any(header[len(text):]), CARRIER_MSG)
    require(str(len(blob)).encode() in text and
            hashlib.sha256(blob).hexdigest().encode() in text and
            b"wpa_supplicant" not in text, CARRIER_MSG)
    end = builder.CARRIER_OFFSET + len(blob)
    require(builder.CARRIER_PREFIX <= builder.CARRIER_HEADER and
            builder.CARRIER_HEADER + 4096 == builder.CARRIER_OFFSET and
            end <= builder.CARRIER_SIZE - 64, CARRIER_MSG)
    require(carrier[:builder.CARRIER_PREFIX] == stock_carrier[:builder.CARRIER_PREFIX] and
            carrier[-64:] == stock_carrier[-64:] and
            not any(carrier[builder.CARRIER_PREFIX:builder.CARRIER_HEADER]) and
            carrier[builder.CARRIER_HEADER:builder.CARRIER_OFFSET] == header and
            carrier[builder.CARRIER_OFFSET:end] == blob and
            not any(carrier[end:-64]), CARRIER_MSG)
    digest = hashlib.sha256(carrier).hexdigest()
    require(digest != builder.CARRIER_SHA and digest not in refused(), SHA_MSG)
    return digest


def check_pair(init_image, carrier, stock_init, base_image, stock_carrier, current,
               library, decode_frame):
    require(len(init_image) == base.IMAGE_SIZE, SIZE_MSG)
    require(base_image[:8] == b"ANDROID!" and base_image[:base.RAMDISK_SIZE_OFFSET] ==
            stock_init[:base.RAMDISK_SIZE_OFFSET] and
            base_image[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock_init[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] and
            base_image[base.TAIL_OFFSET:] == stock_init[base.TAIL_OFFSET:], BASE_MSG)
    entries, trailer, _frame = builder.unpack_image(base_image, library, decode_frame)
    digest = builder.modules.sha256(init_image)
    require(digest not in refused() and digest != OLD_SHA, SHA_MSG)
    require(init_image[:8] == b"ANDROID!" and struct.unpack_from("<I", init_image, 40)[0] == 4 and
            struct.unpack_from("<I", init_image, 8)[0] == 0 and
            init_image[:base.RAMDISK_SIZE_OFFSET] == stock_init[:base.RAMDISK_SIZE_OFFSET] and
            init_image[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE] ==
            stock_init[base.RAMDISK_SIZE_OFFSET + 4:base.PAGE], HEADER_MSG)
    require(init_image[base.TAIL_OFFSET:] == stock_init[base.TAIL_OFFSET:], TAIL_MSG)
    decoded, changed, new_trailer, frame, size = changed_cpio(init_image, library, decode_frame)
    require(not any(init_image[base.PAGE + size:base.TAIL_OFFSET]), GAP_MSG)
    preserved = [item for item in entries if item["name"] != builder.builder.BUNDLE]
    require(len(changed) == len(preserved) and new_trailer == trailer and
            [item["name"] for item in changed] == [item["name"] for item in preserved] and
            len({item["name"] for item in changed}) == len(changed), CPIO_MSG)
    for old, new in zip(preserved, changed):
        require(old["name"] == new["name"] and old["mode"] == new["mode"] and
                old["fields"][:6] == new["fields"][:6] and old["fields"][7:] == new["fields"][7:] and
                (old["data"] == new["data"] or old["name"] == "init"), CPIO_MSG)
    base_entries, base_trailer, base_found, private = builder.base_state(
        base_image, library, decode_frame)
    require(base_trailer == trailer and base_entries == entries, BASE_MSG)
    found = builder.expected_found(base_found, current)
    original = next(item["data"] for item in entries if item["name"] == "init")
    init = next(item["data"] for item in changed if item["name"] == "init")
    blob = builder.carrier_bundle(found, private)
    members = member_map(blob)
    names = (*builder.builder.PUBLIC, "pmos-root-contract.sh", builder.builder.PRIVATE)
    require(set(members) == set(names) and
            members["pmos-root-contract.sh"] == found["pmos-root-contract.sh"] and
            members[builder.builder.PRIVATE] == private and
            all(members[name] == found[name] for name in builder.builder.PUBLIC), BUNDLE_MSG)
    public = {name: found[name] for name in names if name != builder.builder.PRIVATE}
    require(builder.builder.checked_bundle(blob, public, private, tuple(public)) == blob, BUNDLE_MSG)
    require(init == builder.expected_init(original, found, blob) and
            builder.carrier_reader(blob) in init and
            init.count(b"/run/pmos-root-contract.sh") >= 1 and
             init.count(b"vendor_boot_b") >= 1, INIT_MSG)
    require(decoded == builder.candidate_cpio(entries, trailer, found, private) and
            not any(item["name"] == builder.builder.BUNDLE for item in changed), CPIO_MSG)
    require(init_image == vendor.assemble(stock_init, frame)[0], FRAME_MSG)
    carrier_digest = check_carrier(carrier, stock_carrier, blob)
    require(digest != carrier_digest and digest != builder.CARRIER_SHA, SHA_MSG)
    built = builder.build(stock_init, base_image, current, library, decode_frame, stock_carrier)
    require(built[0] == init_image and built[1] == carrier and built[2] == digest and
            built[3] == carrier_digest and built[4] == len(decoded) and built[5] == size and
            built[6] == entries and built[7] == trailer and built[8] == found and
            built[9] == private, CPIO_MSG)
    return digest, carrier_digest, len(decoded), size


def git_clean():
    import subprocess
    proc = subprocess.run(["git", "-C", str(HERE.parent), "status", "--porcelain", "--ignored"],
                          check=True, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        name = line[3:].split(" -> ")[-1]
        require(not name.endswith((".img", ".tar", ".tar.xz", ".tar.gz")) and
                "wpa_supplicant.conf" not in name, GIT_MSG)


def omission_fixture(base_image, library, decode_frame):
    image = base_image
    replayed = False
    if OLD_IMAGE.is_file() and not OLD_IMAGE.is_symlink():
        saved = OLD_IMAGE.read_bytes()
        if hashlib.sha256(saved).hexdigest() == OLD_SHA:
            image = saved
            replayed = True
    decoded, entries, _trailer, _frame, size = changed_cpio(image, library, decode_frame)
    blob = next(item["data"] for item in entries if item["name"] == builder.builder.BUNDLE)
    members = member_map(blob)
    require("pmos-root-contract.sh" not in members, OLD_MSG)
    if replayed:
        require(len(decoded) == 3698688 and size == 2116944, OLD_MSG)
    return image, blob, members, replayed


def overflow_frame(image, library, decode_frame, found, private, replayed):
    _decoded, entries, trailer, _frame, _size = changed_cpio(image, library, decode_frame)
    names = (*builder.builder.PUBLIC, "pmos-root-contract.sh")
    public = {name: found[name] for name in names}
    raw = lzma.decompress(builder.builder.bundle_bytes(public, private, names), format=lzma.FORMAT_XZ)
    blob = lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=9)
    original = next(item["data"] for item in entries if item["name"] == "init")
    changed = [{**entry, "data": blob} if entry["name"] == builder.builder.BUNDLE else entry
               for entry in entries]
    require(any(item["data"] == blob for item in changed) and
            original == next(item["data"] for item in changed if item["name"] == "init"),
            OVERFLOW_MSG)
    cpio = builder.modules.encode_newc(changed, trailer)
    block = base.compress_hc(library, cpio, base.HC_LEVEL)
    framed = len(block) + 8
    require(framed > base.MAX_FRAME, OVERFLOW_MSG)


def self_test(init_image, carrier, stock_init, base_image, stock_carrier, current,
              library, decode_frame):
    digest, carrier_digest, _cpio_size, size = check_pair(
        init_image, carrier, stock_init, base_image, stock_carrier, current, library, decode_frame)
    require(digest not in (RUN69_INIT, RUN72_INIT) and carrier_digest != RUN69_CARRIER,
            "delta must change both carriers and repeat neither measured image")
    git_clean()
    old_image, old_blob, old_members, replayed = omission_fixture(
        base_image, library, decode_frame)
    _entries, _trailer, found, private = builder.base_state(base_image, library, decode_frame)
    found = builder.expected_found(found, current)
    previous = dict(found)
    guard = previous["pmos-pid1-guard.sh"]
    start = guard.index(b'[ ! -e "$root$STATE" ]')
    end = guard.index(b'[ -f "$0" ]', start)
    guard = guard[:start] + (b'[ ! -e "$root$STATE" ] && [ ! -L "$root$STATE" ] &&\n'
                            b'\t[ ! -e "$root/bin/restart2" ] && [ ! -L "$root/bin/restart2" ] || '
                            b"fail 'guard or RESTART2 already exists'\n\t") + guard[end:]
    start = guard.index(b'\tif [ "$mode" = real ]; then\n\t\tif [ ! -e')
    end = guard.index(b'\telse\n\t\t$BB cp "$mock_source"', start)
    guard = guard[:start] + (b'\tif [ "$mode" = real ]; then\n'
                            b'\t\t$BB cp /bin/restart2 "$root/bin/restart2" || fail '\
                            b"'cannot copy RESTART2'\n"
                            b'\t\t$BB chmod 755 "$root/bin/restart2"\n'
                            b'\t\t[ "$(hash "$root/bin/restart2")" = "$HELPER_SHA" ] || '
                            b"fail 'RESTART2 copy changed'\n") + guard[end:]
    require(hashlib.sha256(guard).hexdigest() ==
            "2a92fbcfe029ec3be1af8b73d4cd8d0ac317ecd267a9dc9ba9637932207d5da3", OVERFLOW_MSG)
    previous["pmos-pid1-guard.sh"] = guard
    overflow_frame(old_image, library, decode_frame, previous, private, replayed)
    require(set(old_members) == set(builder.builder.PUBLIC) | {builder.builder.PRIVATE} and
            "pmos-root-contract.sh" not in old_members and
            b"pmos-root-contract.sh" not in old_blob, OLD_MSG)
    if not replayed:
        print("ef476d8c image unavailable or hash differs; overflow replay uses original base init")

    def bad(label, message, init=init_image, boot=carrier, source=current, stock=stock_carrier):
        try:
            check_pair(init, boot, stock_init, base_image, stock, source, library, decode_frame)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture accepted")

    def flipped(image, index):
        result = bytearray(image)
        result[index] ^= 1
        return bytes(result)

    def reframe(parsed):
        decoded = decode_frame(init_image[base.PAGE:base.PAGE + size], library)
        _, new_trailer = builder.modules.parse_newc(decoded, "candidate generic cpio")
        frame = vendor.encode_frame(builder.modules.encode_newc(parsed, new_trailer), library)
        header = bytearray(stock_init[:base.PAGE])
        struct.pack_into("<I", header, base.RAMDISK_SIZE_OFFSET, len(frame))
        return (bytes(header) + frame + bytes(base.MAX_FRAME - len(frame)) +
                stock_init[base.TAIL_OFFSET:])

    def parsed():
        decoded = decode_frame(init_image[base.PAGE:base.PAGE + size], library)
        entries, _trailer = builder.modules.parse_newc(decoded, "candidate generic cpio")
        return entries

    def with_init(data):
        return reframe([{**entry, "data": data} if entry["name"] == "init" else entry
                        for entry in parsed()])

    bad("short image", SIZE_MSG, init_image[:-base.PAGE])
    bad("header change", HEADER_MSG, flipped(init_image, 16))
    bad("tail change", TAIL_MSG, flipped(init_image, base.TAIL_OFFSET + 100))
    bad("gap change", GAP_MSG, flipped(init_image, base.PAGE + size))
    bad("stock init_boot", SHA_MSG, stock_init, stock_carrier)
    bad("run-66 init_boot", SHA_MSG, base_image, stock_carrier)
    bad("ef476d8c omission", SHA_MSG, old_image, stock_carrier)
    bad("stock carrier", CARRIER_MSG, init_image, stock_carrier)
    bad("carrier prefix", CARRIER_MSG, init_image, flipped(carrier, 16))
    bad("carrier tail", CARRIER_MSG, init_image, flipped(carrier, builder.CARRIER_SIZE - 1))
    bad("carrier header", CARRIER_MSG, init_image, flipped(carrier, builder.CARRIER_HEADER))
    bad("carrier payload", CARRIER_MSG, init_image, flipped(carrier, builder.CARRIER_OFFSET))
    changed = dict(current)
    changed["pmos-self-stage.sh"] += b"\n"
    bad("bundle mismatch", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-root-contract.sh"] = changed["pmos-root-contract.sh"].replace(
        b"userdata", b"super")
    bad("super substitution", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-self-stage.sh"] = changed["pmos-self-stage.sh"].replace(
        b'"$wait_n" -lt 145', b'"$wait_n" -lt 146')
    bad("weakened hold", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-pid1-guard.sh"] = changed["pmos-pid1-guard.sh"].replace(
        b"root_contract_switched_root", b"true")
    bad("weakened guard", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-self-stage.sh"] = changed["pmos-self-stage.sh"].replace(
        b"PMOS_ROOT_KIND=ext4 ", b"")
    bad("root delta removed", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-pid1-guard.sh"] = changed["pmos-pid1-guard.sh"].replace(
        b"if [ ! -e \"$root/bin/restart2\" ] && [ ! -L \"$root/bin/restart2\" ]; then",
        b"if true; then", 1)
    bad("helper reuse missing", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-pid1-guard.sh"] = changed["pmos-pid1-guard.sh"].replace(
        b"[ \"$(hash \"$root/bin/restart2\")\" = \"$HELPER_SHA\" ]",
        b"true")
    bad("helper hash weakened", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-pid1-transition.sh"] = changed["pmos-pid1-transition.sh"].replace(
        b"arm \"$ROOT\" 160", b"arm \"$ROOT\" 161", 1)
    bad("deadline weakened", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-pid1-guard.sh"] = changed["pmos-pid1-guard.sh"].replace(
        b"guard state already exists", b"guard state accepted", 1)
    bad("foreign-state refusal changed", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-root-contract.sh"] = b"#!/bin/busybox sh\nexit 0\n"
    bad("missing contract body", INIT_MSG, source=changed)
    changed = dict(current)
    changed["pmos-root-contract.sh"] = changed["pmos-root-contract.sh"].replace(
        b"root_contract_pinned_userdata", b"root_contract_unpinned", 1)
    bad("weakened contract", INIT_MSG, source=changed)
    launch = next(item["data"] for item in parsed() if item["name"] == "init")
    keep = (b"[ ! -e /run/keep ] && [ ! -L /run/keep ] || exit 0\n"
            b"$BB touch /run/keep || exit 0\n"
            b"$BB chmod 600 /run/keep || exit 0\n"
            b"[ -f /run/keep ] && [ ! -L /run/keep ] &&\n"
            b"\t[ \"$($BB stat -c \"%u:%a:%h\" /run/keep)\" = 0:600:1 ] || exit 0\n")
    installed = with_init(launch.replace(keep, b"", 1))
    bad("guest keep removed", INIT_MSG, installed)
    require(RUN69_INIT in refused() and RUN72_INIT in refused() and
            RUN69_CARRIER in refused(), SHA_MSG)
    reader = builder.carrier_reader(builder.carrier_bundle(found, private))
    bad("reader removed", INIT_MSG, with_init(launch.replace(reader, b"", 1)))
    bad("wrong carrier name", INIT_MSG, with_init(launch.replace(b"vendor_boot_b", b"recovery_b", 1)))
    bad("malformed init", INIT_MSG, with_init(b"#!/bin/busybox sh\nexit 0\n"))
    bad("guest keep creation missing", INIT_MSG, with_init(launch.replace(
        b"$BB touch /run/keep || exit 0\n", b"", 1)))
    bad("guest keep mode weakened", INIT_MSG, with_init(launch.replace(
        b"$BB chmod 600 /run/keep || exit 0\n", b"$BB chmod 644 /run/keep || exit 0\n", 1)))
    bad("pre-existing keep accepted", INIT_MSG, with_init(launch.replace(
        b"[ ! -e /run/keep ] && [ ! -L /run/keep ] || exit 0\n", b"", 1)))
    bad("guest keep after self-stage", INIT_MSG, with_init(launch.replace(
        b"$BB touch /run/keep || exit 0\n", b"", 1).replace(
        b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n",
        b"setsid /bin/busybox sh /run/pmos-self-stage.sh >/dev/null 2>&1 &\n$BB touch /run/keep || exit 0\n", 1)))
    bad("malformed carrier", CARRIER_MSG, init_image, b"")
    header = bytearray(builder.carrier_header(builder.carrier_bundle(found, private)))
    header[len(builder.CARRIER_MARKER)] ^= 1
    mutated = bytearray(carrier)
    mutated[builder.CARRIER_HEADER:builder.CARRIER_OFFSET] = header
    bad("malformed carrier header", CARRIER_MSG, init_image, bytes(mutated))
    bad("malformed carrier bundle", INIT_MSG, source={
        **current, "pmos-root-contract.sh": current["pmos-root-contract.sh"] + b"\n#\n"})
    for value in refused():
        require(value != digest and value != carrier_digest, SHA_MSG)
    print(f"persistent-root negative mutations: OK; {len(refused())} refused image hashes; "
          f"init {digest}; carrier {carrier_digest}")


def main():
    args = sys.argv[1:]
    testing = args[:1] == ["--self-test"]
    if testing:
        args = args[1:]
    require(len(args) == 5,
            "usage: verify-init-boot-persistent-root.py [--self-test] "
            "INIT CARRIER STOCK_INIT BASE STOCK_VENDOR_B")
    init_image, carrier, stock_init, base_image, stock_carrier = (
        pathlib.Path(path).read_bytes() for path in args)
    current = builder.current_scripts()
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "persistent_checker")
    library = base.lz4()
    decode = checker.hostkey_checker.decode_frame
    if testing:
        self_test(init_image, carrier, stock_init, base_image, stock_carrier, current,
                  library, decode)
    digest, carrier_digest, cpio_size, frame_size = check_pair(
        init_image, carrier, stock_init, base_image, stock_carrier, current, library, decode)
    print(f"verified persistent-root init_boot: {len(init_image)} bytes, SHA-256 {digest}")
    print(f"verified vendor_boot_b carrier: {len(carrier)} bytes, SHA-256 {carrier_digest}")
    print(f"cpio {cpio_size} bytes; LZ4 HC-{base.HC_LEVEL} frame {frame_size}/{base.MAX_FRAME}; "
          f"gap {base.MAX_FRAME - frame_size}; signed tail unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError,
            tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
