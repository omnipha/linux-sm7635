import hashlib
import importlib.util
import lzma
import os
import pathlib
import stat
import struct
import sys
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
BAD_RADIO = "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3"
INSTALLED_INIT = "d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c"
INSTALLED_CARRIER = "221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500"
RUN97_INIT = "2ebdf1db26193f7f0c3f4c6d42f722008bd1ee2718adf399dfe4927cc3eb9632"
VARIANT_MSG = "mb003 unpinned candidate is not the exact canonical transformation"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canonical = load("build-init-boot-persistent-root.py", "mb003_unpinned_canonical")
builder = load("build-init-boot-persistent-root.py", "mb003_unpinned_builder")
canonical_verifier = load("verify-init-boot-persistent-root.py", "mb003_unpinned_canonical_verifier")
canonical_verifier.builder = canonical
verifier = load("verify-init-boot-persistent-root.py", "mb003_unpinned_verifier")
verifier.builder = builder
require = builder.require
builder.INSTALLED_INIT = INSTALLED_INIT
builder.INSTALLED_CARRIER = INSTALLED_CARRIER
builder.REFUSED = builder.REFUSED | canonical_verifier.refused() | frozenset((INSTALLED_INIT, INSTALLED_CARRIER, RUN97_INIT))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_count(data, old, new, count=1):
    require(isinstance(data, bytes) and isinstance(old, bytes) and isinstance(new, bytes) and
            bool(old) and count > 0 and data.count(old) == count, VARIANT_MSG)
    return data.replace(old, new, count)


def unpinned_post(post):
    post = replace_count(post, b"RADIO_SHA=" + canonical.FRESH_RADIO_SHA.encode() + b"\n", b"")
    post = replace_count(post, b'''[ -f "$RADIO" ] && [ ! -L "$RADIO" ] &&
\t[ "$($BB stat -c '%u:%a' "$RADIO")" = 0:700 ] &&
\t[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || die 'pinned radio bring-up script missing'
''', b'')
    return replace_count(post,
        b'[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || gate_fail \'radio pin changed during stages\'\n', b'')


def unpinned_hook(hook):
    old = (b'for spec in "/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh ' +
           canonical.GATED_POST_SHA.encode() +
           b'" "/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh ' +
           canonical.FRESH_RADIO_SHA.encode() + b'"; do\n'
           b'\tset -- $spec\n'
           b'\t[ -f "$1" ] && [ ! -L "$1" ] &&\n'
           b'\t\t[ "$($BB stat -c \'%u:%a\' "$1")" = 0:700 ] &&\n'
           b'\t\t[ "$($BB sha256sum "$1" | $BB cut -d \' \' -f 1)" = "$2" ] || {\n'
           b'\t\t$BB printf \'pmos-self-post-fresh: pinned persistent script missing or changed\\n\' >/dev/kmsg 2>/dev/null || true\n'
           b'\t\texit 1\n\t}\ndone\n')
    return replace_count(hook, old, b"")


def unpinned_stage(stage):
    old = (b'\t\t\t[ -f "$hook" ] && [ ! -L "$hook" ] && [ "$($BB stat -c \'%u:%g:%a:%h\' "$hook")" = 0:0:700:1 ] &&\n'
           b'\t\t\t[ "$($BB sha256sum "$hook" | $BB cut -d \' \' -f 1)" = ' +
           canonical.GATED_HOOK_SHA.encode() + b' ] ||\n')
    return replace_count(stage, old, b'\t\t\ttrue ||\n')


def unpinned_self_stage(self_stage, old_stage, stage, post, hook):
    self_stage = replace_count(self_stage, b'''	if [ -e "$chain_target" ] || [ -L "$chain_target" ]; then
		chain_check "$chain_target" 700 "$3" || die 'untrusted persistent chain file'
	fi
	[ ! -e "$chain_target.omnipha-new" ] && [ ! -L "$chain_target.omnipha-new" ] ||
		die 'persistent chain staging path already exists'
''', b"")
    install_old = b'''	if [ ! -e "$chain_target" ] && [ ! -L "$chain_target" ]; then
		(umask 077; set -C; $BB cat "$chain_dir/$1" > "$chain_target.omnipha-new") || die 'cannot stage chain file'
		chain_check "$chain_target.omnipha-new" 600 "$3" || die 'staged chain file invalid'
		$BB chmod 700 "$chain_target.omnipha-new" || die 'cannot protect staged chain file'
		chain_check "$chain_target.omnipha-new" 700 "$3" || die 'protected chain file invalid'
		chain_inode=$($BB stat -c '%d:%i' "$chain_target.omnipha-new") || die 'staged chain inode unavailable'
		$BB ln -T "$chain_target.omnipha-new" "$chain_target" ||
			die 'cannot publish chain file without replacement'
		[ ! -L "$chain_target" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_target")" = "$chain_inode:0:0:700:2" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_target.omnipha-new")" = "$chain_inode:0:0:700:2" ] ||
			die 'published chain inode changed'
		$BB rm "$chain_target.omnipha-new" || die 'cannot complete chain publication'
	fi
	chain_check "$chain_target" 700 "$3" || die 'installed chain file invalid'
'''
    install_new = b'''	if [ ! -e "$chain_target" ] && [ ! -L "$chain_target" ]; then
		[ ! -e "$chain_target.omnipha-new" ] && [ ! -L "$chain_target.omnipha-new" ] ||
			die 'persistent chain staging path already exists'
		(umask 077; set -C; $BB cat "$chain_dir/$1" > "$chain_target.omnipha-new") || die 'cannot stage chain file'
		$BB chmod 700 "$chain_target.omnipha-new" || die 'cannot protect staged chain file'
		$BB ln -T "$chain_target.omnipha-new" "$chain_target" ||
			die 'cannot publish chain file without replacement'
		$BB rm "$chain_target.omnipha-new" || die 'cannot complete chain publication'
	fi
'''
    self_stage = replace_count(self_stage, install_old, install_new)
    final = (b'for chain_spec in \\\n'
             b'\t"/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh ' + canonical.FRESH_RADIO_SHA.encode() + b'" \\\n'
             b'\t"/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh ' + canonical.GATED_POST_SHA.encode() + b'" \\\n'
             b'\t"/etc/local.d/10-omnipha-self-stage.start ' + canonical.GATED_HOOK_SHA.encode() + b'"; do\n'
             b'\tset -- $chain_spec\n'
             b'''\tchain_check "$GUEST$1" 700 "$2" || die 'persistent chain changed after installation'\n'''
             b'done\n')
    self_stage = replace_count(self_stage, final, b"")
    self_stage = replace_count(self_stage, canonical.GATED_POST_SHA.encode(), sha(post).encode(), 2)
    self_stage = replace_count(self_stage, canonical.GATED_HOOK_SHA.encode(), sha(hook).encode(), 2)
    return replace_count(self_stage, b"STAGE_SHA=" + sha(old_stage).encode(),
                         b"STAGE_SHA=" + sha(stage).encode())


def runtime_scripts():
    original = canonical.runtime_scripts()
    canonical_verifier.check_runtime_scripts(original)
    require(canonical.FRESH_RADIO_SHA != BAD_RADIO and
            sha(original[canonical.FRESH_RADIO]) == canonical.FRESH_RADIO_SHA and
            original["pmos-radio-bringup.sh"] == original[canonical.FRESH_RADIO], VARIANT_MSG)
    result = dict(original)
    result[builder.FRESH_POST] = unpinned_post(original[canonical.FRESH_POST])
    result[builder.GATED_HOOK] = unpinned_hook(original[canonical.GATED_HOOK])
    result["pmos-session-stage.sh"] = unpinned_stage(original["pmos-session-stage.sh"])
    result["pmos-self-stage.sh"] = unpinned_self_stage(
        original["pmos-self-stage.sh"], original["pmos-session-stage.sh"],
        result["pmos-session-stage.sh"], result[builder.FRESH_POST], result[builder.GATED_HOOK])
    require(set(result) == set(original), VARIANT_MSG)
    for name in original:
        if name not in (builder.FRESH_POST, builder.GATED_HOOK,
                        "pmos-session-stage.sh", "pmos-self-stage.sh"):
            require(result[name] == original[name], VARIANT_MSG)
    require(result["pmos-radio-bringup.sh"] == original["pmos-radio-bringup.sh"] and
            result[canonical.FRESH_RADIO] == original[canonical.FRESH_RADIO] and
            result["pmos-self-post.sh"] == original["pmos-self-post.sh"], VARIANT_MSG)
    require(canonical.GATED_POST_SHA.encode() not in result["pmos-session-stage.sh"] and
            canonical.GATED_HOOK_SHA.encode() not in result["pmos-session-stage.sh"] and
            canonical.GATED_POST_SHA.encode() not in result[builder.GATED_HOOK] and
            canonical.FRESH_RADIO_SHA.encode() not in result[builder.GATED_HOOK] and
            canonical.GATED_POST_SHA.encode() not in result["pmos-self-stage.sh"] and
            canonical.GATED_HOOK_SHA.encode() not in result["pmos-self-stage.sh"] and
            result["pmos-self-stage.sh"].count(canonical.FRESH_RADIO_SHA.encode()) == 3 and
            b"RADIO_SHA=" not in result[builder.FRESH_POST] and
            b"radio_snapshot" not in result[builder.FRESH_POST] and
            result["pmos-self-stage.sh"].count(b"chain_check") == 2 and
            b"untrusted persistent chain file" not in result["pmos-self-stage.sh"] and
            b"installed chain file invalid" not in result["pmos-self-stage.sh"] and
            b"persistent chain changed after installation" not in result["pmos-self-stage.sh"] and
            b"chain_metadata" not in result["pmos-self-stage.sh"] and
            b"chain_digest" not in result["pmos-self-stage.sh"] and
            b"chain_trust" not in result["pmos-self-stage.sh"] and
            b"omnipha-legacy" not in result["pmos-self-stage.sh"], VARIANT_MSG)
    reconstructed = dict(result)
    reconstructed[builder.FRESH_POST] = original[canonical.FRESH_POST]
    reconstructed[builder.GATED_HOOK] = original[canonical.GATED_HOOK]
    reconstructed["pmos-session-stage.sh"] = original["pmos-session-stage.sh"]
    reconstructed["pmos-self-stage.sh"] = original["pmos-self-stage.sh"]
    require(reconstructed == original, VARIANT_MSG)
    canonical_verifier.check_runtime_scripts(reconstructed)
    builder.GATED_POST_SHA = sha(result[builder.FRESH_POST])
    builder.GATED_HOOK_SHA = sha(result[builder.GATED_HOOK])
    require(builder.GATED_POST_SHA != canonical.GATED_POST_SHA and
            builder.GATED_HOOK_SHA != canonical.GATED_HOOK_SHA and
            INSTALLED_INIT in verifier.refused() and INSTALLED_CARRIER in verifier.refused() and
            RUN97_INIT in verifier.refused() and verifier.builder is builder, VARIANT_MSG)
    return result


def build_candidate(stock, base, stock_carrier, library, decode):
    current = runtime_scripts()
    built = builder.build(stock, base, current, library, decode, stock_carrier)
    checked = verifier.check_pair(built[0], built[1], stock, base, stock_carrier, current, library, decode)
    require(checked == (built[2], built[3], built[4], built[5]), VARIANT_MSG)
    return built


def check_output_parent(fd, parent):
    actual = pathlib.Path(os.readlink(f"/proc/self/fd/{fd}"))
    held = os.fstat(fd)
    named = os.stat(parent, follow_symlinks=False)
    require(actual == parent and stat.S_ISDIR(held.st_mode) and stat.S_ISDIR(named.st_mode) and
            (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino) and
            not parent.is_relative_to(HERE.parent.resolve()), canonical.OUTPUT_MSG)
    for ancestor in (parent, *parent.parents):
        try:
            os.lstat(ancestor / ".git")
        except FileNotFoundError:
            continue
        raise ValueError(canonical.OUTPUT_MSG)


def check_output_file(fd, parent_fd, name, device, inode, size):
    held = os.fstat(fd)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    require(stat.S_ISREG(held.st_mode) and stat.S_ISREG(named.st_mode) and
            (held.st_dev, held.st_ino) == (device, inode) == (named.st_dev, named.st_ino) and
            held.st_uid == os.getuid() and held.st_nlink == 1 and held.st_size == size and
            stat.S_IMODE(held.st_mode) == 0o600 and
            (named.st_uid, named.st_nlink, named.st_size, stat.S_IMODE(named.st_mode)) ==
            (held.st_uid, held.st_nlink, held.st_size, 0o600),
            "candidate output changed or has unsafe metadata")


def write_candidate_pair(output, carrier_output, inputs, image, carrier):
    canonical.output_paths(output, carrier_output, (*inputs, canonical.PROFILE))
    parents = []
    files = []
    created = []
    pending = None
    try:
        for path in (output, carrier_output):
            require(path.name not in ("", ".", "..", ".git"), canonical.OUTPUT_MSG)
            parent = path.parent.resolve(strict=True)
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            parents.append((parent_fd, parent, path.name))
            check_output_parent(parent_fd, parent)
        first, second = (os.fstat(parent_fd) for parent_fd, _, _ in parents)
        require((first.st_dev, first.st_ino, parents[0][2]) !=
                (second.st_dev, second.st_ino, parents[1][2]), canonical.OUTPUT_MSG)
        for parent_fd, parent, name in parents:
            check_output_parent(parent_fd, parent)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=parent_fd)
            files.append(fd)
            pending = name
            info = os.fstat(fd)
            created.append((parent_fd, name, info.st_dev, info.st_ino))
            pending = None
            os.fchmod(fd, 0o600)
            check_output_file(fd, parent_fd, name, info.st_dev, info.st_ino, 0)
        for (parent_fd, parent, name), fd, (_, _, device, inode), data in zip(
                parents, files, created, (image, carrier)):
            check_output_parent(parent_fd, parent)
            check_output_file(fd, parent_fd, name, device, inode, 0)
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write on candidate output")
                view = view[written:]
            os.fsync(fd)
            check_output_file(fd, parent_fd, name, device, inode, len(data))
        for parent_fd, parent, _ in parents:
            check_output_parent(parent_fd, parent)
            os.fsync(parent_fd)
        for (parent_fd, parent, name), fd, (_, _, device, inode), data in zip(
                parents, files, created, (image, carrier)):
            check_output_parent(parent_fd, parent)
            check_output_file(fd, parent_fd, name, device, inode, len(data))
        while files:
            os.close(files.pop())
    except BaseException as exc:
        cleanup_errors = []
        if pending is not None:
            cleanup_errors.append(f"cannot identify created output {pending}")
        while files:
            try:
                os.close(files.pop())
            except OSError as error:
                cleanup_errors.append(str(error))
        for parent_fd, name, device, inode in created:
            try:
                info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (info.st_dev, info.st_ino) == (device, inode):
                    os.unlink(name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError as error:
                cleanup_errors.append(str(error))
        if cleanup_errors:
            raise OSError("candidate output cleanup incomplete: " + "; ".join(cleanup_errors)) from exc
        raise
    finally:
        for parent_fd, _, _ in parents:
            os.close(parent_fd)


def verify_candidate(init, carrier, stock, base, stock_carrier, library, decode):
    return verifier.check_pair(init, carrier, stock, base, stock_carrier, runtime_scripts(), library, decode)


def main():
    args = sys.argv[1:]
    require(len(args) == 6 and args[0] in ("--build", "--verify"),
            "usage: build-init-boot-mb003-unpinned.py --build STOCK_INIT BASE STOCK_VENDOR_B INIT_OUTPUT CARRIER_OUTPUT | --verify INIT CARRIER STOCK_INIT BASE STOCK_VENDOR_B")
    paths = tuple(map(pathlib.Path, args[1:]))
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "mb003_unpinned_decode")
    library = builder.base.lz4()
    decode = checker.hostkey_checker.decode_frame
    if args[0] == "--build":
        stock, base, stock_carrier, output, carrier_output = paths
        require(base.resolve() == builder.BASE_IMAGE.resolve(), builder.BASE_MSG)
        inputs = (stock, base, stock_carrier)
        canonical.output_paths(output, carrier_output, (*inputs, canonical.PROFILE))
        built = build_candidate(stock.read_bytes(), base.read_bytes(), stock_carrier.read_bytes(), library, decode)
        write_candidate_pair(output, carrier_output, inputs, built[0], built[1])
        digest, carrier_digest, cpio_size, frame_size = built[2:6]
    else:
        init_b, carrier_b, stock_b, base_b, stock_carrier_b = (path.read_bytes() for path in paths)
        digest, carrier_digest, cpio_size, frame_size = verify_candidate(
            init_b, carrier_b, stock_b, base_b, stock_carrier_b, library, decode)
    print(f"init_boot SHA-256 {digest}; vendor_boot_b SHA-256 {carrier_digest}")
    print(f"cpio {cpio_size} bytes; LZ4 HC-{builder.base.HC_LEVEL} frame {frame_size}/{builder.base.MAX_FRAME}")


runtime_scripts()

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error, lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
