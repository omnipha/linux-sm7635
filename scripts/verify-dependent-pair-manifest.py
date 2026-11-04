#!/usr/bin/env python3
import fcntl
import hashlib
import importlib.util
import json
import lzma
import os
import pathlib
import stat
import struct
import sys
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = "omnipha-sm7635-dependent-pair-v1"
MANIFEST_NAME = "root-contract-pair.manifest.json"
IMAGES = (("init_boot_a", "init_boot-root-contract-carrier.img", 8388608),
          ("vendor_boot_b", "vendor_boot_b-root-contract.img", 100663296))
ERROR = "invalid or unverified dependent-pair declaration"
USAGE = ("usage: verify-dependent-pair-manifest.py "
         "write|verify INIT CARRIER MANIFEST STOCK_INIT BASE STOCK_VENDOR_B LOCK "
         "[--lock-fd N] | invalidate INIT CARRIER MANIFEST LOCK [--lock-fd N]")


def require(condition, message=ERROR):
    if not condition:
        raise ValueError(message)


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def regular(info, mode=None):
    return (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
            info.st_nlink == 1 and (mode is None or stat.S_IMODE(info.st_mode) == mode))


def paths(init_path, carrier_path, manifest_path):
    require(init_path.name == IMAGES[0][1] and carrier_path.name == IMAGES[1][1] and
            manifest_path.name == MANIFEST_NAME)
    parent = manifest_path.parent.resolve(strict=True)
    require(parent.is_dir() and not parent.is_relative_to(HERE.parent))
    require(init_path.parent.resolve(strict=True) == parent and
            carrier_path.parent.resolve(strict=True) == parent)
    return parent / init_path.name, parent / carrier_path.name, parent / manifest_path.name


def lock_file(path, inherited):
    if inherited is None:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        owned = True
        close = True
    else:
        fd = inherited
        owned = False
        close = False
    info = os.fstat(fd)
    require(regular(info) and identity(info) == identity(path.lstat()), "unsafe build lock")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        require(identity(os.fstat(fd)) == identity(path.lstat()), "changed build lock")
    except BaseException:
        if close:
            os.close(fd)
        raise
    return fd, owned


def unlock_file(fd, owned, path):
    if owned:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    else:
        require(identity(os.fstat(fd)) == identity(path.lstat()), "changed build lock")


def sync_directory(parent):
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def invalidate(manifest_path):
    try:
        info = manifest_path.lstat()
    except FileNotFoundError:
        return
    require(regular(info, 0o600), "unsafe existing manifest")
    manifest_path.unlink()
    sync_directory(manifest_path.parent)


def snapshot(path, size):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(regular(before, 0o600) and before.st_size == size)
        require(identity(before) == identity(path.lstat()), "image path changed")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(size + 1)
        require(len(data) == size and identity(before) == identity(os.fstat(fd)) and
                identity(before) == identity(path.lstat()), "image changed while reading")
        return data, identity(before)
    finally:
        os.close(fd)


def unchanged(path, size, expected, original):
    data, info = snapshot(path, size)
    require(info == original and hashlib.sha256(data).hexdigest() == expected,
            "image changed after verification")


def read_reference(path):
    require(path.is_file() and not path.is_symlink(), "unsafe verification input")
    return path.read_bytes()


def verified_pair(init_path, carrier_path, refs):
    init, init_identity = snapshot(init_path, IMAGES[0][2])
    carrier, carrier_identity = snapshot(carrier_path, IMAGES[1][2])
    stock_init, base_image, stock_carrier = (read_reference(path) for path in refs)
    verifier = load("verify-init-boot-persistent-root.py", "persistent_pair_verifier")
    checker = load("verify-init-boot-psoc-hold-wlan-node.py", "persistent_pair_decode")
    digest, carrier_digest, _cpio_size, _frame_size = verifier.check_pair(
        init, carrier, stock_init, base_image, stock_carrier, verifier.builder.runtime_scripts(),
        verifier.base.lz4(), checker.hostkey_checker.decode_frame)
    require(digest == hashlib.sha256(init).hexdigest() and
            carrier_digest == hashlib.sha256(carrier).hexdigest())
    unchanged(init_path, IMAGES[0][2], digest, init_identity)
    unchanged(carrier_path, IMAGES[1][2], carrier_digest, carrier_identity)
    return (digest, carrier_digest), (init_identity, carrier_identity)


def declaration(digests):
    return {"schema": SCHEMA, "images": [
        {"partition": partition, "filename": filename, "size": size, "sha256": digest}
        for (partition, filename, size), digest in zip(IMAGES, digests)
    ]}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_manifest(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(regular(info, 0o600) and 0 < info.st_size <= 4096 and
                identity(info) == identity(path.lstat()))
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(4097)
        require(len(data) == info.st_size and identity(info) == identity(os.fstat(fd)) and
                identity(info) == identity(path.lstat()))
    finally:
        os.close(fd)
    return json.loads(data, object_pairs_hook=unique_object)


def check_manifest(value, digests):
    require(isinstance(value, dict) and set(value) == {"schema", "images"} and
            value["schema"] == SCHEMA and isinstance(value["images"], list) and
            len(value["images"]) == len(IMAGES))
    entries = {}
    for entry in value["images"]:
        require(isinstance(entry, dict) and set(entry) == {"partition", "filename", "size", "sha256"})
        partition = entry["partition"]
        require(isinstance(partition, str) and partition not in entries and
                type(entry["size"]) is int and isinstance(entry["sha256"], str))
        entries[partition] = entry
    require(entries == {entry["partition"]: entry for entry in declaration(digests)["images"]})


def remove_own(path, device, inode):
    try:
        info = path.lstat()
        if (info.st_dev, info.st_ino) == (device, inode):
            path.unlink()
    except FileNotFoundError:
        pass


def publish(manifest_path, digests, identities, init_path, carrier_path):
    staging = manifest_path.with_name(manifest_path.name + ".omnipha-new")
    require(not staging.exists() and not staging.is_symlink(), "manifest staging path exists")
    data = (json.dumps(declaration(digests), indent=1, sort_keys=True) + "\n").encode()
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    info = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        staged = staging.lstat()
        require(regular(staged, 0o600) and
                (staged.st_dev, staged.st_ino) == (info.st_dev, info.st_ino))
        unchanged(init_path, IMAGES[0][2], digests[0], identities[0])
        unchanged(carrier_path, IMAGES[1][2], digests[1], identities[1])
        os.link(staging, manifest_path, follow_symlinks=False)
        require((manifest_path.lstat().st_dev, manifest_path.lstat().st_ino) ==
                (info.st_dev, info.st_ino))
        staging.unlink()
        sync_directory(manifest_path.parent)
        check_manifest(read_manifest(manifest_path), digests)
        unchanged(init_path, IMAGES[0][2], digests[0], identities[0])
        unchanged(carrier_path, IMAGES[1][2], digests[1], identities[1])
    except BaseException:
        remove_own(manifest_path, info.st_dev, info.st_ino)
        remove_own(staging, info.st_dev, info.st_ino)
        raise


def main():
    args = sys.argv[1:]
    inherited = None
    if len(args) >= 2 and args[-2] == "--lock-fd":
        inherited = int(args[-1])
        args = args[:-2]
    require(args and args[0] in ("write", "verify", "invalidate"), USAGE)
    action = args[0]
    require(len(args) == (5 if action == "invalidate" else 8), USAGE)
    init_path, carrier_path, manifest_path = (pathlib.Path(item) for item in args[1:4])
    init_path, carrier_path, manifest_path = paths(init_path, carrier_path, manifest_path)
    lock_path = pathlib.Path(args[-1])
    fd, owned = lock_file(lock_path, inherited)
    try:
        if action in ("write", "invalidate"):
            invalidate(manifest_path)
        if action == "invalidate":
            return
        refs = tuple(pathlib.Path(item) for item in args[4:7])
        if action == "verify":
            value = read_manifest(manifest_path)
        digests, identities = verified_pair(init_path, carrier_path, refs)
        if action == "write":
            publish(manifest_path, digests, identities, init_path, carrier_path)
        else:
            check_manifest(value, digests)
            require(read_manifest(manifest_path) == value, "manifest changed during verification")
        print(f"{action}: {manifest_path.name}; init_boot_a {digests[0]}; vendor_boot_b {digests[1]}")
    finally:
        unlock_file(fd, owned, lock_path)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error,
            lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
