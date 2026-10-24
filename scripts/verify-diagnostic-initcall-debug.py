import importlib.util
import pathlib
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


ext4 = load("verify-diagnostic-signed-tail.py", "signed_tail_checker")
base = ext4.base
usb = ext4.usb
BASELINE_CONFIG_SHA256 = "c6d8a4e86301d314adc8724b7b3d985d81b9cff2074e0e917ed976a46df3ebd9"
MEASURED_BOOT = "0ca048d554857b469aadf6a55e6fd70cc1cb51cd72eff8f6f98e451bb595f72b"
MEASURED_INIT = "cafcabb67a1d79f7877b59a1daff25d92fd8fc6ecb5d5128f44ab8cc17af541c"
MEASURED_IMAGE = "7be448b91b618cbe1dbda9659dfeeb2d554f702091c39453bfa44497c280377e"
MEASURED_PAYLOAD = "d259b744465eb48b2c42ddcedcf89f6d2608638c6b04f3c2c534fa27b66d7738"
PRIOR_IMAGES = frozenset((*ext4.PRIOR_IMAGES, MEASURED_BOOT, MEASURED_INIT, MEASURED_IMAGE,
                          MEASURED_PAYLOAD))
REQUIRED_PRIOR = (*ext4.REQUIRED_PRIOR, "0ca048d5", "cafcabb6", "7be448b9", "d259b744")
OLD_CMDLINE = (b'"console=ttynull stack_depot_disable=on cgroup_disable=pressure '
               b'kasan.page_alloc.sample=10 kasan.stacktrace=off kvm-arm.mode=protected '
               b'bootconfig ioremap_guard sm7635-boot-marker"')
NEW_CMDLINE = OLD_CMDLINE[:-1] + b' initcall_debug"'
SHA_MSG = ext4.SHA_MSG
CONFIG_MSG = "config differs from #59 outside exactly one CONFIG_CMDLINE initcall_debug token"
IMAGE_MSG = ext4.IMAGE_MSG
LAYOUT_MSG = ext4.LAYOUT_MSG
TAIL_MSG = ext4.TAIL_MSG
require = ext4.require


def reject_prior_sha(digest, prior_images=PRIOR_IMAGES):
    require(digest not in prior_images, SHA_MSG)


def config_lines(data):
    return data.decode().splitlines()


def check_config(config, baseline, fragment):
    require(base.sha256(baseline) == BASELINE_CONFIG_SHA256, "#59 config reference changed")
    old_lines, new_lines = config_lines(baseline), config_lines(config)
    old_cmdlines = [line for line in old_lines if line.startswith("CONFIG_CMDLINE=")]
    new_cmdlines = [line for line in new_lines if line.startswith("CONFIG_CMDLINE=")]
    require(old_cmdlines == ["CONFIG_CMDLINE=" + OLD_CMDLINE.decode()] and
            new_cmdlines == ["CONFIG_CMDLINE=" + NEW_CMDLINE.decode()], CONFIG_MSG)
    rest_old = [line for line in old_lines if not line.startswith("CONFIG_CMDLINE=")]
    rest_new = [line for line in new_lines if not line.startswith("CONFIG_CMDLINE=")]
    require(rest_old == rest_new, CONFIG_MSG)
    require(new_cmdlines[0].count("initcall_debug") == 1, CONFIG_MSG)
    values = ext4.config_values(config)
    for key in ("CONFIG_KALLSYMS", "CONFIG_F2FS_FS", "CONFIG_ANDROID_BINDER_IPC", "CONFIG_NLS",
                "CONFIG_TRACEPOINTS", "CONFIG_CMDLINE_EXTEND"):
        require(values.get(key) == "y", CONFIG_MSG)
    require(values.get("CONFIG_EXT4_FS", "n") == "n" and
            values.get("CONFIG_KALLSYMS_ALL", "n") == "n", CONFIG_MSG)
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
    require(NEW_CMDLINE[1:-1] + b"\x00" in unpacked and unpacked.count(b"initcall_debug") >= 2,
            IMAGE_MSG)
    require(len(candidate) == base.STOCK_BOOT_SIZE, LAYOUT_MSG)
    require(candidate[base.PREFIX_SIZE:] == stock[base.PREFIX_SIZE:], TAIL_MSG)
    require(candidate == base.assemble(stock, payload), LAYOUT_MSG)
    require(candidate[:8] == b"ANDROID!" and
            struct.unpack_from("<I", candidate, base.KERNEL_SIZE_OFFSET)[0] == len(payload) and
            struct.unpack_from("<I", candidate, 40)[0] == 4, LAYOUT_MSG)
    require(stock[base.PREFIX_SIZE:base.PREFIX_SIZE + 4] == b"AVB0" and
            stock[13971456:13971460] == b"AVB0" and stock[-64:-60] == b"AVBf" and
            struct.unpack_from(">QQQ", stock, len(stock) - 52) == (13971456, 13971456, 2496),
            base.STOCK_MSG)
    return base.sha256(candidate)


def expect(label, message, function, *args):
    try:
        function(*args)
    except ValueError as exc:
        require(str(exc) == message, f"{label}: unexpected failure: {exc}")
    else:
        raise ValueError(f"accepted {label}")


def self_test(args):
    candidate, stock, payload, image, config, baseline, fragment = args
    digest = check_candidate(*args)
    require(digest not in PRIOR_IMAGES, SHA_MSG)
    for prefix in REQUIRED_PRIOR:
        matches = [sha for sha in PRIOR_IMAGES if sha.startswith(prefix)]
        require(len(matches) == 1, f"missing or ambiguous prior SHA: {prefix}")
        expect(f"measured SHA {prefix}", SHA_MSG, reject_prior_sha, matches[0])
    expect("repeated candidate SHA", SHA_MSG, reject_prior_sha, digest, (digest,))
    expect("measured #59 gzip as payload", SHA_MSG, reject_prior_sha, MEASURED_PAYLOAD)
    expect("measured #59 boot image as candidate", SHA_MSG, reject_prior_sha, MEASURED_BOOT)
    expect("measured #59 Image as unpacked kernel", SHA_MSG, reject_prior_sha, MEASURED_IMAGE)
    for label, offset, msg in (("header", 8, LAYOUT_MSG),
                                ("payload", base.PAGE + 30, LAYOUT_MSG),
                                ("padding", base.PAGE + len(payload), LAYOUT_MSG),
                                ("first AVB0", base.PREFIX_SIZE, TAIL_MSG),
                                ("vbmeta", 13971456, TAIL_MSG),
                                ("AVBf", len(candidate) - 64, TAIL_MSG)):
        changed = bytearray(candidate)
        changed[offset] ^= 1
        expect(f"changed {label}", msg, check_candidate, bytes(changed), stock, payload,
               image, config, baseline, fragment)
    expect("config without initcall_debug", CONFIG_MSG, check_config,
           config.replace(b" initcall_debug", b"", 1), baseline, fragment)
    expect("config with doubled initcall_debug", CONFIG_MSG, check_config,
           config.replace(b" initcall_debug", b" initcall_debug initcall_debug", 1),
           baseline, fragment)
    expect("config with F2FS_FS off", CONFIG_MSG, check_config,
           config.replace(b"CONFIG_F2FS_FS=y", b"# CONFIG_F2FS_FS is not set"), baseline,
           fragment)
    expect("config with a second delta", CONFIG_MSG, check_config,
           config.replace(b"CONFIG_PANIC_TIMEOUT=-1", b"CONFIG_PANIC_TIMEOUT=0"), baseline,
           fragment)
    expect("config with initcall_blacklist", CONFIG_MSG, check_config,
           config.replace(b" initcall_debug", b" initcall_debug initcall_blacklist=init_u32", 1),
           baseline, fragment)
    expect("baseline #59 config as candidate", CONFIG_MSG, check_config, baseline, baseline,
           fragment)
    try:
        check_candidate(candidate, stock, payload, image, config, baseline, fragment)
    except ValueError as exc:
        raise ValueError(f"valid fixture rejected: {exc}") from exc
    print(f"initcall-debug negative fixtures: OK; candidate {digest}")


def main():
    args = sys.argv[1:]
    self_testing = args[:1] == ["--self-test"]
    if self_testing:
        args = args[1:]
    require(len(args) == 7,
            "usage: verify-diagnostic-initcall-debug.py [--self-test] BOOT STOCK_BOOT GZIP IMAGE CONFIG BASELINE_CONFIG USB_FRAGMENT")
    inputs = tuple(pathlib.Path(path).read_bytes() for path in args)
    if self_testing:
        self_test(inputs)
    else:
        digest = check_candidate(*inputs)
        print(f"initcall-debug boot: {len(inputs[0])} bytes, SHA-256 {digest}")
        print(f"payload: {len(inputs[2])} bytes, {base.PAYLOAD_BOUND - len(inputs[2])} below bound")
        print("config differs from #59 only by CONFIG_CMDLINE +initcall_debug; "
              "stock prefix except kernel-size field, gzip and padding; AVB0/vbmeta/AVBf tail unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, zlib.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
