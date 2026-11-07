import hashlib
import importlib.util
import lzma
import pathlib
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
BAD_RADIO = "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3"
V2_INIT = "f08a71aedb549147c092c1dea4d0289b1108a607d8839b889e6851868fd91637"
V2_CARRIER = "cb7f3a9eb3033e22ad17116a7d5adf10aa0091eb0c512a628e6319e7aa2cd666"
MIGRATE = "pmos-migrate-no-guard.sh"
VARIANT_MSG = "mb003 no-guard candidate is not the exact transformation of the unpinned pair"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


unpinned = load("build-init-boot-mb003-unpinned.py", "mb003_no_guard_unpinned_ref")
canonical = unpinned.canonical
require = unpinned.builder.require
sha = unpinned.sha
replace_count = unpinned.replace_count
FRESH_RADIO = canonical.FRESH_RADIO
FRESH_POST = canonical.FRESH_POST
GATED_HOOK = canonical.GATED_HOOK
GUARD_SCRIPT_SHA = hashlib.sha256((HERE / "pmos-pid1-guard.sh").read_bytes()).hexdigest().encode()

GUARD_ARM = b'''if ! $BB sh "$GUARD" arm "$ROOT" 160; then
	if [ -e "$ROOT/run/pid1-guard/armed" ] || [ -L "$ROOT/run/pid1-guard/armed" ]; then
		log 'pid1 transition guard arm failed after arming; independent guard remains armed'
		while :; do $BB sleep 60; done
	fi
	fail 'independent recovery guard not armed'
	return 1
fi
[ -f "$ROOT/run/pid1-guard/armed" ] && [ ! -L "$ROOT/run/pid1-guard/armed" ] &&
	[ "$($BB cat "$ROOT/run/pid1-guard/armed")" = "$($BB cat /proc/sys/kernel/random/boot_id)" ] &&
	[ ! -e "$ROOT/run/pid1-guard/nonce" ] && [ ! -L "$ROOT/run/pid1-guard/nonce" ] || {
	log 'pid1 transition guard not awaiting transition; independent guard remains armed'
	while :; do $BB sleep 60; done
}
'''
CONTRACT_COPY = b'''GUEST_CONTRACT="$ROOT/run/pmos-root-contract.sh"
[ ! -e "$GUEST_CONTRACT" ] && [ ! -L "$GUEST_CONTRACT" ] || { fail 'guest root contract path exists'; return 1; }
$BB cp "$CONTRACT" "$GUEST_CONTRACT" && $BB chmod 600 "$GUEST_CONTRACT" || { fail 'cannot stage root contract'; return 1; }
[ -f "$GUEST_CONTRACT" ] && [ ! -L "$GUEST_CONTRACT" ] &&
	[ "$($BB sha256sum "$GUEST_CONTRACT" | $BB cut -d ' ' -f 1)" = "$($BB sha256sum "$CONTRACT" | $BB cut -d ' ' -f 1)" ] || { fail 'staged root contract differs'; return 1; }
'''
GUARD_INPUT = b'''[ -f "$GUARD" ] && [ ! -L "$GUARD" ] &&
	[ "$($BB stat -c '%u:%a:%h' "$GUARD")" = 0:700:1 ] || { fail 'guard input missing'; return 1; }
[ "$($BB sha256sum "$GUARD" | $BB cut -d ' ' -f 1)" = "$GUARD_SHA256" ] || { fail 'guard digest mismatch'; return 1; }
'''
INIT_TIMER = (b"{\n"
              b"\tsleep 150\n"
              b"\tif [ ! -e /run/keep ]; then\n"
              b"\t\tlog 'self-recovery -> bootloader'\n"
              b"\t\t/bin/restart2 bootloader\n"
              b"\t\tlog 'self-recovery RESTART2 failed; falling back to reboot -f'\n"
              b"\t\treboot -f\n"
              b"\tfi\n"
              b"} &\n")
SETTLE_START = b"PID1_TIMER_SETTLED=0\n"
SETTLE_END = b"pid1_request_valid() {\n"
SETTLE_GATE = (b'\t\tif [ "$PID1_TIMER_SETTLED" != failed ] && pid1_request_valid &&\n'
               b'\t\t\tpid1_settle_timer && pid1_request_valid; then\n')
INIT_FORBIDDEN = (b"sleep 150", b"restart2", b"reboot -f", b"pid1-guard", b"pmos-pid1-guard",
                  b"PID1_SETTLE", b"PID1_TIMER_SETTLED", b"151.01", b"self-recovery")


def no_guard_init(init):
    init = replace_count(init, INIT_TIMER, b"")
    start = init.index(SETTLE_START)
    end = init.index(SETTLE_END, start)
    require(init.count(SETTLE_START) == 1 and init.count(SETTLE_END) == 1 and start < end, VARIANT_MSG)
    init = init[:start] + init[end:]
    init = replace_count(init, SETTLE_GATE, b"\t\tif pid1_request_valid; then\n")
    init = replace_count(init, b"\t\t\t[ -f /run/keep ] && [ ! -L /run/keep ] &&\n", b"\t\t\ttrue &&\n")
    require(not any(token in init for token in INIT_FORBIDDEN), VARIANT_MSG)
    return init


def no_guard_transition(transition):
    transition = replace_count(transition, b"GUARD=/run/pmos-pid1-guard.sh\n", b"")
    transition = replace_count(transition, b"GUARD_SHA256=" + GUARD_SCRIPT_SHA + b"\n", b"")
    transition = replace_count(transition, GUARD_INPUT, b"")
    transition = replace_count(transition, GUARD_ARM, CONTRACT_COPY)
    transition = replace_count(transition, b"pid1 transition guard armed; exec switch_root to postmarketOS init",
                               b"pid1 transition ready; exec switch_root to postmarketOS init", 3)
    require(b"GUARD" not in transition.replace(b"GUEST_CONTRACT", b"") and
            b"pid1-guard" not in transition and b'arm "$ROOT"' not in transition and
            b"restart2" not in transition and transition.count(b"exec /bin/busybox switch_root") == 1 and
            transition.index(b"GUEST_CONTRACT=") < transition.index(b"boot_record_append") <
            transition.index(b"exec /bin/busybox switch_root"), VARIANT_MSG)
    return transition


def migrated(files):
    busybox = shutil.which("busybox")
    require(busybox is not None, "host busybox is required for the no-guard migration")
    assert busybox is not None
    with tempfile.TemporaryDirectory(prefix="mb003-no-guard.") as tmp:
        root = pathlib.Path(tmp)
        (root / "usr/libexec/omnipha").mkdir(parents=True)
        (root / "etc/local.d").mkdir(parents=True)
        (root / "run").mkdir()
        targets = {
            FRESH_RADIO: root / "usr/libexec/omnipha" / FRESH_RADIO,
            FRESH_POST: root / "usr/libexec/omnipha" / FRESH_POST,
            GATED_HOOK: root / "etc/local.d" / GATED_HOOK,
        }
        for name, path in targets.items():
            path.write_bytes(files[name])
        script = HERE / MIGRATE
        env = {"PATH": "/usr/bin:/bin", "BB": busybox}
        result = subprocess.run([busybox, "sh", str(script), str(root)], env=env,
                                capture_output=True, check=False)
        require(result.returncode == 0 and (root / "etc/.omnipha-no-guard-migrated").is_file(), VARIANT_MSG)
        out = {name: path.read_bytes() for name, path in targets.items()}
        require(not (root / "run/no-guard-work").exists(), VARIANT_MSG)
        (root / "etc/.omnipha-no-guard-migrated").unlink()
        again = subprocess.run([busybox, "sh", str(script), str(root)], env=env,
                               capture_output=True, check=False)
        require(again.returncode == 0 and
                {name: path.read_bytes() for name, path in targets.items()} == out, VARIANT_MSG)
        return out


def no_guard_self_stage(self_stage, old_post, new_post, old_radio, new_radio, old_transition, new_transition):
    self_stage = replace_count(self_stage, b"GUARD_SHA=" + GUARD_SCRIPT_SHA + b"\n", b"")
    self_stage = replace_count(self_stage, b'\t"/run/pmos-pid1-guard.sh $GUARD_SHA" \\\n', b"")
    self_stage = replace_count(self_stage, old_radio.encode(), new_radio.encode(), 3)
    self_stage = replace_count(self_stage, old_post.encode(), new_post.encode(), 2)
    self_stage = replace_count(self_stage, old_transition.encode(), new_transition.encode(), 1)
    call = (b'''$BB sh "$chain_dir/''' + MIGRATE.encode() + b'''" "$GUEST" || {
	migrate_rc=$?
\t[ "$migrate_rc" != 3 ] || die 'known bad radio script on persistent root'
\tdie 'no-guard migration of persistent scripts failed'
}
''')
    anchor = b'''$BB sh /run/pmos-radio-bringup.sh "$boot" prepare || die 'pmos-radio-bringup prepare failed'
'''
    self_stage = replace_count(self_stage, anchor, call + anchor)
    require(b"GUARD" not in self_stage and b"pid1-guard" not in self_stage and
            GUARD_SCRIPT_SHA not in self_stage, VARIANT_MSG)
    return self_stage


def runtime_scripts():
    base = unpinned.runtime_scripts()
    old_post = sha(base[FRESH_POST])
    old_radio = sha(base[FRESH_RADIO])
    old_transition = sha(base["pmos-pid1-transition.sh"])
    files = migrated({name: base[name] for name in (FRESH_RADIO, FRESH_POST, GATED_HOOK)})
    radio = files[FRESH_RADIO]
    post = files[FRESH_POST]
    hook = files[GATED_HOOK]
    require(hook == base[GATED_HOOK] and sha(radio) != BAD_RADIO and
            sha(radio) != old_radio and sha(post) != old_post, VARIANT_MSG)
    for forbidden in (b"pid1-guard", b"$GUARD", b"guard.sh", b"nonce", b"/ack", b"accepted"):
        require(forbidden not in radio and forbidden not in post and forbidden not in hook, VARIANT_MSG)
    result = dict(base)
    contract = replace_count(base["pmos-root-contract.sh"],
                             b"pid1 transition guard armed; exec switch_root to postmarketOS init",
                             b"pid1 transition ready; exec switch_root to postmarketOS init", 3)
    result["pmos-root-contract.sh"] = replace_count(
        contract, b"guard identity check passed; ", b"", 3)
    result[FRESH_RADIO] = radio
    result["pmos-radio-bringup.sh"] = radio
    result[FRESH_POST] = post
    result[GATED_HOOK] = hook
    result["pmos-pid1-transition.sh"] = no_guard_transition(base["pmos-pid1-transition.sh"])
    result[MIGRATE] = (HERE / MIGRATE).read_bytes()
    require(result[MIGRATE].startswith(b"#!/bin/busybox sh\n") and b"\0" not in result[MIGRATE], VARIANT_MSG)
    result["pmos-self-stage.sh"] = no_guard_self_stage(
        base["pmos-self-stage.sh"], old_post, sha(post), old_radio, sha(radio),
        old_transition, sha(result["pmos-pid1-transition.sh"]))
    require(set(result) == set(base) | {MIGRATE}, VARIANT_MSG)
    return result


def context(scripts):
    mod = load("build-init-boot-persistent-root.py", "mb003_no_guard_builder")
    mod.INSTALLED_INIT = unpinned.INSTALLED_INIT
    mod.INSTALLED_CARRIER = unpinned.INSTALLED_CARRIER
    mod.REFUSED = (mod.REFUSED | unpinned.canonical_verifier.refused() |
                   frozenset((unpinned.INSTALLED_INIT, unpinned.INSTALLED_CARRIER,
                              unpinned.RUN97_INIT, V2_INIT, V2_CARRIER)))
    mod.FRESH_RADIO_SHA = sha(scripts[FRESH_RADIO])
    mod.GATED_POST_SHA = sha(scripts[FRESH_POST])
    mod.GATED_HOOK_SHA = sha(scripts[GATED_HOOK])
    mod.builder.HOOK = replace_count(
        mod.builder.HOOK, b'$BB mv "$D/pmos-pid1-guard.sh" /run/pmos-pid1-guard.sh || exit 0\n', b"")
    mod.CARRIER_PUBLIC = tuple(name for name in mod.CARRIER_PUBLIC if name != "pmos-pid1-guard.sh") + (MIGRATE,)
    mod.CARRIER_NAMES = (*mod.CARRIER_PUBLIC, "pmos-root-contract.sh", *mod.GATED_NAMES)
    base_expected_init = mod.expected_init

    def expected_init(original, found, blob):
        return no_guard_init(base_expected_init(original, found, blob))

    mod.expected_init = expected_init
    verifier = load("verify-init-boot-persistent-root.py", "mb003_no_guard_verifier")
    verifier.builder = mod
    require("pmos-pid1-guard.sh" not in mod.CARRIER_NAMES and MIGRATE in mod.CARRIER_NAMES and
            mod.FRESH_RADIO_SHA != BAD_RADIO, VARIANT_MSG)
    return mod, verifier


def build_candidate(stock, base, stock_carrier, library, decode):
    current = runtime_scripts()
    mod, verifier = context(current)
    built = mod.build(stock, base, current, library, decode, stock_carrier)
    checked = verifier.check_pair(built[0], built[1], stock, base, stock_carrier, current, library, decode)
    require(checked == (built[2], built[3], built[4], built[5]), VARIANT_MSG)
    return built


def verify_candidate(init, carrier, stock, base, stock_carrier, library, decode):
    current = runtime_scripts()
    _mod, verifier = context(current)
    return verifier.check_pair(init, carrier, stock, base, stock_carrier, current, library, decode)


def check_content(init, carrier, library, decode):
    current = runtime_scripts()
    mod, _verifier = context(current)
    entries, _trailer, _frame = mod.unpack_image(init, library, decode)
    data = {entry["name"]: entry["data"] for entry in entries}
    require(not any(token in data["init"] for token in INIT_FORBIDDEN), VARIANT_MSG)
    require(BAD_RADIO.encode() not in init and BAD_RADIO.encode() not in carrier, VARIANT_MSG)
    return entries


def main():
    args = sys.argv[1:]
    require(len(args) == 6 and args[0] in ("--build", "--verify"),
            "usage: build-init-boot-mb003-no-guard.py --build STOCK_INIT BASE STOCK_VENDOR_B INIT_OUTPUT CARRIER_OUTPUT | --verify INIT CARRIER STOCK_INIT BASE STOCK_VENDOR_B")
    paths = tuple(map(pathlib.Path, args[1:]))
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "mb003_no_guard_decode")
    library = unpinned.builder.base.lz4()
    decode = checker.hostkey_checker.decode_frame
    if args[0] == "--build":
        stock, base, stock_carrier, output, carrier_output = paths
        require(base.resolve() == unpinned.builder.BASE_IMAGE.resolve(), unpinned.builder.BASE_MSG)
        inputs = (stock, base, stock_carrier)
        canonical.output_paths(output, carrier_output, (*inputs, canonical.PROFILE))
        built = build_candidate(stock.read_bytes(), base.read_bytes(), stock_carrier.read_bytes(), library, decode)
        check_content(built[0], built[1], library, decode)
        unpinned.write_candidate_pair(output, carrier_output, inputs, built[0], built[1])
        digest, carrier_digest, cpio_size, frame_size = built[2:6]
    else:
        init_b, carrier_b, stock_b, base_b, stock_carrier_b = (path.read_bytes() for path in paths)
        digest, carrier_digest, cpio_size, frame_size = verify_candidate(
            init_b, carrier_b, stock_b, base_b, stock_carrier_b, library, decode)
        check_content(init_b, carrier_b, library, decode)
    print(f"init_boot SHA-256 {digest}; vendor_boot_b SHA-256 {carrier_digest}")
    print(f"cpio {cpio_size} bytes; LZ4 HC-{unpinned.builder.base.HC_LEVEL} frame {frame_size}/{unpinned.builder.base.MAX_FRAME}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
