import importlib.util
import pathlib
import re
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


base = load("build-diagnostic-signed-tail-payload.py", "signed_tail_builder")
usb = load("verify-volcano-usb.py", "volcano_usb")
init_builder = load("build-init-boot-kernel-banner-payload.py", "init_banner_builder")
BASELINE_CONFIG_SHA256 = "05c70f1a766c7f2d265dc538363445ae581d158a1e60d93313e0c35a0aa2dfd0"
OLD_PAYLOAD = "37535dd13312e2d2078c344cbf11db32260f0d35c4d3e0b2bf95a214b27b9bb8"
PRIOR_IMAGES = frozenset((*init_builder.PRIOR_IMAGES, OLD_PAYLOAD,
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450",
    "5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b",
    "dc990b9517d53431fcaeebb2b0498e6e64d3e7cbbc7e469d3e0bfc73abe00075"))
REQUIRED_PRIOR = ("9f89fe8d", "995aaca3", "88c93077", "8f8b7331", "55fa78ca",
                  "5a513998", "dc990b95", "13a48ff9", "37535dd1", "bde3a3b3",
                  "6078269d")
EXPECTED_DELTAS = {"CONFIG_EXT4_FS", "CONFIG_EXT4_USE_FOR_EXT2", "CONFIG_EXT4_FS_POSIX_ACL",
                   "CONFIG_EXT4_FS_SECURITY", "CONFIG_JBD2", "CONFIG_FS_MBCACHE"}
SHA_MSG = "candidate repeats a previously measured SHA-256"
CONFIG_MSG = "config differs from #60 outside EXT4_FS and its solely-selected symbols"
IMAGE_MSG = "gzip does not contain the diagnostic Image and IKCONFIG"
LAYOUT_MSG = "boot differs from stock outside kernel-size field, gzip payload and zero padding"
TAIL_MSG = "stock AVB0/vbmeta/AVBf tail was modified"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reject_prior_sha(digest):
    require(digest not in PRIOR_IMAGES, SHA_MSG)


def config_values(data):
    values = {}
    for line in data.decode().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name, value = line.split("=", 1)
            values[name] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            values[line.split()[1]] = "n"
    return values


def check_config(config, baseline, fragment):
    require(base.sha256(baseline) == BASELINE_CONFIG_SHA256, "#60 config reference changed")
    old, new = config_values(baseline), config_values(config)
    changed = {key for key in set(old) | set(new)
               if old.get(key, "n") != new.get(key, "n")}
    require(changed == EXPECTED_DELTAS and
            all(old.get(key) == "y" and new.get(key, "n") == "n" for key in changed), CONFIG_MSG)
    for key in ("CONFIG_KALLSYMS", "CONFIG_F2FS_FS", "CONFIG_ANDROID_BINDER_IPC", "CONFIG_NLS"):
        require(old.get(key) == new.get(key) == "y", CONFIG_MSG)
    require(old.get("CONFIG_KALLSYMS_ALL", "n") == new.get("CONFIG_KALLSYMS_ALL", "n") == "n",
            CONFIG_MSG)
    usb.check_config(config, fragment)


def check_candidate(candidate, stock, payload, image, config, baseline, fragment):
    reject_prior_sha(base.sha256(candidate))
    reject_prior_sha(base.sha256(payload))
    require(len(stock) == base.STOCK_BOOT_SIZE and base.sha256(stock) == base.STOCK_BOOT_SHA256,
            base.STOCK_MSG)
    check_config(config, baseline, fragment)
    unpacked = base.check_payload(payload)
    require(unpacked == image and base.sha256(image) not in PRIOR_IMAGES, IMAGE_MSG)
    start = unpacked.find(b"IKCFG_ST")
    end = unpacked.find(b"IKCFG_ED", start + 8)
    require(start >= 0 and end > start and zlib.decompress(unpacked[start + 8:end],
            16 + zlib.MAX_WBITS) == config, IMAGE_MSG)
    require(len(candidate) == base.STOCK_BOOT_SIZE, LAYOUT_MSG)
    require(candidate[base.PREFIX_SIZE:] == stock[base.PREFIX_SIZE:], TAIL_MSG)
    expected = base.assemble(stock, payload)
    require(candidate == expected, LAYOUT_MSG)
    require(candidate[:8] == b"ANDROID!" and
            struct.unpack_from("<I", candidate, base.KERNEL_SIZE_OFFSET)[0] == len(payload) and
            struct.unpack_from("<I", candidate, 40)[0] == 4, LAYOUT_MSG)
    require(stock[base.PREFIX_SIZE:base.PREFIX_SIZE + 4] == b"AVB0" and
            stock[13971456:13971460] == b"AVB0" and stock[-64:-60] == b"AVBf" and
            struct.unpack_from(">QQQ", stock, len(stock) - 52) == (13971456, 13971456, 2496),
            base.STOCK_MSG)
    return base.sha256(candidate)


def self_test(args):
    candidate, stock, payload, image, config, baseline, fragment = args
    digest = check_candidate(*args)
    for prefix in REQUIRED_PRIOR:
        matches = [sha for sha in PRIOR_IMAGES if sha.startswith(prefix)]
        require(len(matches) == 1, f"missing or ambiguous prior SHA: {prefix}")
        try:
            reject_prior_sha(matches[0])
        except ValueError as exc:
            require(str(exc) == SHA_MSG, f"wrong rejection for {prefix}")
        else:
            raise ValueError(f"accepted measured SHA {prefix}")
    for label, offset, msg in (("header", 8, LAYOUT_MSG),
                                ("payload", base.PAGE + 30, LAYOUT_MSG),
                                ("padding", base.PAGE + len(payload), LAYOUT_MSG),
                                ("first AVB0", base.PREFIX_SIZE, TAIL_MSG),
                                ("vbmeta", 13971456, TAIL_MSG),
                                ("AVBf", len(candidate) - 64, TAIL_MSG)):
        changed = bytearray(candidate)
        changed[offset] ^= 1
        try:
            check_candidate(bytes(changed), stock, payload, image, config, baseline, fragment)
        except ValueError as exc:
            require(str(exc) == msg, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"accepted changed {label}")
    bad_config = config.replace(b"CONFIG_F2FS_FS=y", b"# CONFIG_F2FS_FS is not set")
    try:
        check_config(bad_config, baseline, fragment)
    except ValueError as exc:
        require(str(exc) == CONFIG_MSG, f"unexpected config failure: {exc}")
    else:
        raise ValueError("accepted F2FS_FS change")
    try:
        check_candidate(candidate, stock, payload, image, config, baseline, fragment)
    except ValueError as exc:
        raise ValueError(f"valid fixture rejected: {exc}") from exc
    print(f"signed-tail negative fixtures: OK; candidate {digest}")


def main():
    args = sys.argv[1:]
    self_testing = args[:1] == ["--self-test"]
    if self_testing:
        args = args[1:]
    require(len(args) == 7,
            "usage: verify-diagnostic-signed-tail.py [--self-test] BOOT STOCK_BOOT GZIP IMAGE CONFIG BASELINE_CONFIG USB_FRAGMENT")
    inputs = tuple(pathlib.Path(path).read_bytes() for path in args)
    if self_testing:
        self_test(inputs)
    else:
        digest = check_candidate(*inputs)
        print(f"diagnostic boot: {len(inputs[0])} bytes, SHA-256 {digest}")
        print(f"payload: {len(inputs[2])} bytes, {base.PAYLOAD_BOUND - len(inputs[2])} below bound")
        print("stock prefix except kernel-size field, gzip and padding; AVB0/vbmeta/AVBf tail unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, zlib.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
