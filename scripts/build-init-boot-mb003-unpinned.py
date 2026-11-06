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
    old = b'''[ -f "$RADIO" ] && [ ! -L "$RADIO" ] &&
\t[ "$($BB stat -c '%u:%a' "$RADIO")" = 0:700 ] &&
\t[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || die 'pinned radio bring-up script missing'
'''
    new = b'''[ -d /run ] && [ ! -L /run ] &&
\t[ "$($BB stat -c '%u:%g:%a' /run 2>/dev/null)" = 0:0:700 ] &&
\t[ -d "$STATE" ] && [ ! -L "$STATE" ] &&
\t[ "$($BB stat -c '%u:%g:%a' "$STATE" 2>/dev/null)" = 0:0:700 ] || die 'unsafe radio snapshot parent'
[ -f "$RADIO" ] && [ ! -L "$RADIO" ] &&
\t[ "$($BB stat -c '%u:%a' "$RADIO")" = 0:700 ] &&
\t[ "$($BB stat -c '%g:%h' "$RADIO" 2>/dev/null)" = 0:1 ] || die 'unsafe persistent radio script'
radio_dir="$STATE/omnipha-radio-snapshot"
[ ! -e "$radio_dir" ] && [ ! -L "$radio_dir" ] || die 'radio snapshot directory already exists'
$BB mkdir -m 700 "$radio_dir" || die 'cannot create radio snapshot directory'
[ -d "$radio_dir" ] && [ ! -L "$radio_dir" ] &&
\t[ "$($BB stat -c '%u:%g:%a' "$radio_dir" 2>/dev/null)" = 0:0:700 ] || die 'unsafe radio snapshot directory'
radio_snapshot="$radio_dir/radio.sh"
(umask 077; set -C; $BB cat "$RADIO" > "$radio_snapshot") || die 'cannot copy radio snapshot'
RADIO="$radio_snapshot"
radio_snapshot_check() {
\t[ -d /run ] && [ ! -L /run ] &&
\t\t[ "$($BB stat -c '%u:%g:%a' /run 2>/dev/null)" = 0:0:700 ] &&
\t\t[ -d "$STATE" ] && [ ! -L "$STATE" ] &&
\t\t[ "$($BB stat -c '%u:%g:%a' "$STATE" 2>/dev/null)" = 0:0:700 ] &&
\t\t[ -d "$radio_dir" ] && [ ! -L "$radio_dir" ] &&
\t\t[ "$($BB stat -c '%u:%g:%a' "$radio_dir" 2>/dev/null)" = 0:0:700 ] &&
\t\t[ -f "$RADIO" ] && [ ! -L "$RADIO" ] && [ -s "$RADIO" ] &&
\t\t[ "$($BB stat -c '%u:%g:%a:%h' "$RADIO" 2>/dev/null)" = 0:0:600:1 ] || return 1
\tradio_sum=$($BB sha256sum "$RADIO" 2>/dev/null) || return 1
\tradio_sum=${radio_sum%% *}
\t[ "${#radio_sum}" = 64 ] || return 1
\tcase "$radio_sum" in *[!0-9a-f]*) return 1;; esac
\t[ "$radio_sum" != @BAD_RADIO@ ]
}
radio_snapshot_check || die 'unsafe, unreadable or refused radio snapshot'
'''.replace(b"@BAD_RADIO@", BAD_RADIO.encode())
    post = replace_count(post, old, new)
    post = replace_count(post,
        b'\t$BB sh "$RADIO" "$boot" "$stage" "$marker" || die "radio bring-up $stage failed"\n',
        b'\tradio_snapshot_check || die "unsafe, unreadable or refused radio snapshot before $stage"\n'
        b'\t$BB sh "$RADIO" "$boot" "$stage" "$marker" || die "radio bring-up $stage failed"\n')
    post = replace_count(post,
        b'$BB sh "$RADIO" "$boot" services "$marker" < "$PROFILE" || die \'radio bring-up services failed\'\n',
        b'radio_snapshot_check || die \'unsafe, unreadable or refused radio snapshot before services\'\n'
        b'$BB sh "$RADIO" "$boot" services "$marker" < "$PROFILE" || die \'radio bring-up services failed\'\n')
    return replace_count(post,
        b'[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || gate_fail \'radio pin changed during stages\'\n',
        b'radio_snapshot_check || gate_fail \'unsafe, unreadable or refused radio snapshot\'\n')


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
    new = b'''for spec in "/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"; do
\tset -- $spec
\t[ -f "$1" ] && [ ! -L "$1" ] &&
\t\t[ "$($BB stat -c '%u:%a' "$1")" = 0:700 ] &&
\t\t[ "$($BB stat -c '%g:%h' "$1" 2>/dev/null)" = 0:1 ] || {
\t\t$BB printf 'pmos-self-post-fresh: persistent script missing or unsafe\\n' >/dev/kmsg 2>/dev/null || true
\t\texit 1
\t}
done
'''
    return replace_count(hook, old, new)


def unpinned_stage(stage):
    old = (b'\t\t\t[ -f "$hook" ] && [ ! -L "$hook" ] && [ "$($BB stat -c \'%u:%g:%a:%h\' "$hook")" = 0:0:700:1 ] &&\n'
           b'\t\t\t[ "$($BB sha256sum "$hook" | $BB cut -d \' \' -f 1)" = ' +
           canonical.GATED_HOOK_SHA.encode() + b' ] ||\n')
    new = b'\t\t\t[ -f "$hook" ] && [ ! -L "$hook" ] && [ "$($BB stat -c \'%u:%g:%a:%h\' "$hook")" = 0:0:700:1 ] ||\n'
    return replace_count(stage, old, new)


def unpinned_self_stage(self_stage, old_stage, stage, post, hook):
    self_stage = replace_count(self_stage, canonical.GATED_POST_SHA.encode(), sha(post).encode(), 3)
    self_stage = replace_count(self_stage, canonical.GATED_HOOK_SHA.encode(), sha(hook).encode(), 3)
    self_stage = replace_count(self_stage, b"STAGE_SHA=" + sha(old_stage).encode(),
                               b"STAGE_SHA=" + sha(stage).encode())
    old = b'''chain_check() {
	[ -f "$1" ] && [ ! -L "$1" ] &&
		[ "$($BB stat -c '%u:%g:%a:%h' "$1")" = "0:0:$2:1" ] &&
		[ "$($BB sha256sum "$1" 2>/dev/null | $BB cut -d ' ' -f 1)" = "$3" ]
}
'''
    new = b'''chain_metadata() {
	[ -f "$1" ] && [ ! -L "$1" ] &&
		[ "$($BB stat -c '%u:%g:%a:%h' "$1")" = "0:0:$2:1" ]
}
chain_digest() {
	chain_sum=
	chain_out=$($BB sha256sum "$1" 2>/dev/null) || return 1
	[ -n "$chain_out" ] || return 1
	chain_sum=${chain_out%% *}
	[ "$chain_sum  $1" = "$chain_out" ] && [ "${#chain_sum}" = 64 ] || return 1
	case "$chain_sum" in *[!0-9a-f]*) return 1;; esac
	[ "$chain_sum" != @BAD_RADIO@ ] || return 2
	return 0
}
chain_check() {
	chain_metadata "$1" "$2" && chain_digest "$1" && [ "$chain_sum" = "$3" ]
}
chain_trust() {
	if chain_digest "$1"; then return 0; else chain_rc=$?; fi
	[ "$chain_rc" -ne 2 ] || die 'refused persistent chain file'
	die "$2"
}
chain_legacy_for() {
	case "$1" in
		pmos-self-post-fresh-boot.sh) chain_legacy=@LEGACY_POST@;;
		10-omnipha-self-stage.start) chain_legacy=@LEGACY_HOOK@;;
		*) chain_legacy=;;
	esac
}
'''.replace(b"@BAD_RADIO@", BAD_RADIO.encode()).replace(
        b"@LEGACY_POST@", canonical.GATED_POST_SHA.encode()).replace(
        b"@LEGACY_HOOK@", canonical.GATED_HOOK_SHA.encode())
    self_stage = replace_count(self_stage, old, new)
    inspect_old = b'''	if [ -e "$chain_target" ] || [ -L "$chain_target" ]; then
		chain_check "$chain_target" 700 "$3" || die 'untrusted persistent chain file'
	fi
	[ ! -e "$chain_target.omnipha-new" ] && [ ! -L "$chain_target.omnipha-new" ] ||
		die 'persistent chain staging path already exists'
'''
    inspect_new = b'''	chain_legacy_for "$1"
	chain_backup="$chain_target.omnipha-legacy"
	[ ! -e "$chain_target.omnipha-new" ] && [ ! -L "$chain_target.omnipha-new" ] ||
		die 'persistent chain staging path already exists'
	if [ -e "$chain_backup" ] || [ -L "$chain_backup" ]; then
		[ -n "$chain_legacy" ] || die 'unexpected persistent chain legacy backup'
		chain_metadata "$chain_backup" 700 || die 'unsafe persistent chain legacy backup'
		chain_trust "$chain_backup" 'unsafe persistent chain legacy backup'
		[ "$chain_sum" = "$chain_legacy" ] || die 'stale persistent chain legacy backup'
		[ "$($BB stat -c '%d' "$chain_backup")" = "$chain_root_dev" ] ||
			die 'persistent chain legacy backup left persistent filesystem'
		chain_metadata "$chain_target" 700 || die 'partial persistent chain migration'
		chain_trust "$chain_target" 'untrusted persistent chain file'
		[ "$chain_sum" != "$chain_legacy" ] || die 'partial persistent chain migration'
	elif [ -e "$chain_target" ] || [ -L "$chain_target" ]; then
		chain_metadata "$chain_target" 700 || die 'untrusted persistent chain file'
		chain_trust "$chain_target" 'untrusted persistent chain file'
		if [ -n "$chain_legacy" ] && [ "$chain_sum" = "$chain_legacy" ]; then
			[ "$($BB stat -c '%d' "$chain_target")" = "$chain_root_dev" ] ||
				die 'legacy chain file left persistent filesystem'
		fi
	fi
'''
    self_stage = replace_count(self_stage, inspect_old, inspect_new)
    migrate_old = b'''	chain_target="$GUEST$2"
	if [ ! -e "$chain_target" ] && [ ! -L "$chain_target" ]; then
'''
    migrate_new = b'''	chain_target="$GUEST$2"
	chain_legacy_for "$1"
	chain_backup="$chain_target.omnipha-legacy"
	if [ -n "$chain_legacy" ] && [ -e "$chain_target" ] && [ ! -e "$chain_backup" ] && [ ! -L "$chain_backup" ] &&
		chain_check "$chain_target" 700 "$chain_legacy"; then
		chain_identity='%d:%i:%u:%g:%a:%s:%Y'
		chain_before=$($BB stat -c "$chain_identity" "$chain_target") || die 'legacy chain identity unavailable'
		chain_old=$($BB stat -c '%d:%i' "$chain_target") || die 'legacy chain inode unavailable'
		(umask 077; set -C; $BB cat "$chain_dir/$1" > "$chain_target.omnipha-new") || die 'cannot stage chain file'
		chain_check "$chain_target.omnipha-new" 600 "$3" || die 'staged chain file invalid'
		$BB chmod 700 "$chain_target.omnipha-new" || die 'cannot protect staged chain file'
		chain_check "$chain_target.omnipha-new" 700 "$3" || die 'protected chain file invalid'
		chain_inode=$($BB stat -c '%d:%i' "$chain_target.omnipha-new") || die 'staged chain inode unavailable'
		[ "${chain_inode%%:*}" = "$chain_root_dev" ] && [ "$chain_inode" != "$chain_old" ] ||
			die 'staged chain file is not separate on the persistent filesystem'
		$BB sync -f "$chain_target.omnipha-new" || die 'cannot make staged chain file durable'
		chain_check "$chain_target" 700 "$chain_legacy" &&
			[ "$($BB stat -c "$chain_identity" "$chain_target")" = "$chain_before" ] ||
			die 'persistent chain file changed before backup'
		$BB ln -T "$chain_target" "$chain_backup" || die 'cannot create persistent chain legacy backup'
		[ ! -L "$chain_backup" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_target")" = "$chain_old:0:0:700:2" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_backup")" = "$chain_old:0:0:700:2" ] &&
			[ "$($BB stat -c "$chain_identity" "$chain_backup")" = "$chain_before" ] &&
			chain_digest "$chain_backup" && [ "$chain_sum" = "$chain_legacy" ] ||
			die 'persistent chain legacy backup changed'
		$BB sync -f "$chain_backup" || die 'cannot make persistent chain legacy backup durable'
		chain_digest "$chain_target" && [ "$chain_sum" = "$chain_legacy" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_target")" = "$chain_old:0:0:700:2" ] &&
			[ "$($BB stat -c '%d:%i:%u:%g:%a:%h' "$chain_backup")" = "$chain_old:0:0:700:2" ] &&
			chain_check "$chain_target.omnipha-new" 700 "$3" &&
			[ "$($BB stat -c '%d:%i' "$chain_target.omnipha-new")" = "$chain_inode" ] ||
			die 'persistent chain file changed before replacement'
		$BB mv -fT "$chain_target.omnipha-new" "$chain_target" || die 'cannot replace legacy chain file'
		chain_check "$chain_target" 700 "$3" && [ "$($BB stat -c '%d:%i' "$chain_target")" = "$chain_inode" ] &&
			chain_check "$chain_backup" 700 "$chain_legacy" &&
			[ "$($BB stat -c "$chain_identity" "$chain_backup")" = "$chain_before" ] ||
			die 'migrated chain file invalid'
		$BB sync -f "$chain_target" || die 'cannot make migrated chain file durable'
	fi
	if [ ! -e "$chain_target" ] && [ ! -L "$chain_target" ]; then
'''
    self_stage = replace_count(self_stage, migrate_old, migrate_new)
    self_stage = replace_count(self_stage,
        b'chain_check "$chain_target" 700 "$3" || die \'installed chain file invalid\'',
        b'chain_metadata "$chain_target" 700 || die \'installed chain file invalid\'\n'
        b'\tchain_trust "$chain_target" \'installed chain file invalid\'')
    return replace_count(self_stage,
        b'chain_check "$GUEST$1" 700 "$2" || die \'persistent chain changed after installation\'',
        b'chain_metadata "$GUEST$1" 700 || die \'persistent chain changed after installation\'\n'
        b'\tchain_trust "$GUEST$1" \'persistent chain changed after installation\'\n'
        b'\tchain_legacy_for "${1##*/}"\n'
        b'\tif [ -n "$chain_legacy" ] && { [ -e "$GUEST$1.omnipha-legacy" ] || [ -L "$GUEST$1.omnipha-legacy" ]; }; then\n'
        b'\t\tchain_check "$GUEST$1.omnipha-legacy" 700 "$chain_legacy" ||\n'
        b'\t\t\tdie \'persistent chain legacy backup changed after installation\'\n'
        b'\tfi')


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
            result["pmos-self-stage.sh"].count(canonical.GATED_POST_SHA.encode()) == 1 and
            result["pmos-self-stage.sh"].count(canonical.GATED_HOOK_SHA.encode()) == 1 and
            b"RADIO_SHA=" not in result[builder.FRESH_POST], VARIANT_MSG)
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
