#!/usr/bin/env python3
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
SCHEMA = "omnipha-sm7635-mb003-no-guard-pair-v1"
MANIFEST_NAME = "mb003-no-guard-pair-v3.manifest.json"
IMAGES = (("init_boot_a", "init_boot-mb003-no-guard-v3.img", 8388608),
          ("vendor_boot_b", "vendor_boot_b-mb003-no-guard-v3.img", 100663296))
USAGE = ("usage: verify-mb003-no-guard-pair-manifest.py "
         "write|verify INIT CARRIER MANIFEST STOCK_INIT BASE STOCK_VENDOR_B LOCK [--lock-fd N]")
UNPINNED_SCHEMA = "omnipha-sm7635-mb003-unpinned-pair-v1"
UNPINNED_NAMES = frozenset(("mb003-unpinned-pair-v2.manifest.json",
                            "init_boot-mb003-unpinned-v2.img",
                            "vendor_boot_b-mb003-unpinned-v2.img"))
ROUTE_CACHE_SCHEMA = "omnipha-sm7635-route-cache-pair-v1"
ROUTE_CACHE_NAMES = frozenset(("root-contract-route-cache-pair.manifest.json",
                               "init_boot-route-cache-candidate.img",
                               "vendor_boot_b-route-cache-candidate.img"))


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest = load("verify-dependent-pair-manifest.py", "mb003_no_guard_pair_manifest")
CANONICAL_SCHEMA = manifest.SCHEMA
CANONICAL_NAMES = frozenset((manifest.MANIFEST_NAME, *(item[1] for item in manifest.IMAGES)))
canonical_paths = manifest.paths
manifest.SCHEMA = SCHEMA
manifest.MANIFEST_NAME = MANIFEST_NAME
manifest.IMAGES = IMAGES
manifest.USAGE = USAGE


def paths(init_path, carrier_path, manifest_path):
    result = canonical_paths(init_path, carrier_path, manifest_path)
    parent = result[2].parent
    private = (pathlib.Path.home() / "phone-second-life-data" / "mb003").resolve()
    manifest.require(not parent.is_relative_to(private), "output must not be in device reference data")
    for ancestor in (parent, *parent.parents):
        try:
            (ancestor / ".git").lstat()
        except FileNotFoundError:
            continue
        raise ValueError("output must not be in a Git worktree")
    return result


def verified_pair(init_path, carrier_path, refs):
    init, init_identity = manifest.snapshot(init_path, IMAGES[0][2])
    carrier, carrier_identity = manifest.snapshot(carrier_path, IMAGES[1][2])
    stock_init, base_image, stock_carrier = (manifest.read_reference(path) for path in refs)
    variant = load("build-init-boot-mb003-no-guard.py", "mb003_no_guard_pair_variant")
    checker = manifest.load("verify-init-boot-psoc-hold-wlan-node.py", "mb003_no_guard_pair_decode")
    digest, carrier_digest, _cpio_size, _frame_size = variant.verify_candidate(
        init, carrier, stock_init, base_image, stock_carrier,
        variant.unpinned.builder.base.lz4(), checker.hostkey_checker.decode_frame)
    variant.check_content(init, carrier, variant.unpinned.builder.base.lz4(),
                          checker.hostkey_checker.decode_frame)
    manifest.require(digest == hashlib.sha256(init).hexdigest() and
                     carrier_digest == hashlib.sha256(carrier).hexdigest())
    manifest.unchanged(init_path, IMAGES[0][2], digest, init_identity)
    manifest.unchanged(carrier_path, IMAGES[1][2], carrier_digest, carrier_identity)
    return (digest, carrier_digest), (init_identity, carrier_identity)


def require_absent(path):
    manifest.require(not path.exists() and not path.is_symlink(), "candidate manifest already exists")


def remove_own(parent_fd, name, identity):
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) == identity:
            os.unlink(name, dir_fd=parent_fd)
    except FileNotFoundError:
        pass


def publish(manifest_path, digests, identities, init_path, carrier_path):
    require_absent(manifest_path)
    data = (json.dumps(manifest.declaration(digests), indent=1, sort_keys=True) + "\n").encode()
    parent = manifest_path.parent
    staging = manifest_path.name + ".omnipha-new"
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    identity = None
    linked = False
    try:
        parent_info = os.fstat(parent_fd)
        named_parent = parent.stat()
        manifest.require(stat.S_ISDIR(parent_info.st_mode) and
                         (parent_info.st_dev, parent_info.st_ino) ==
                         (named_parent.st_dev, named_parent.st_ino), "output directory changed")
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            identity = (info.st_dev, info.st_ino)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
            staged = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
            manifest.require(manifest.regular(staged, 0o600) and staged.st_size == len(data) and
                             (staged.st_dev, staged.st_ino) == identity, "manifest staging changed")
        finally:
            os.close(fd)
        manifest.unchanged(init_path, IMAGES[0][2], digests[0], identities[0])
        manifest.unchanged(carrier_path, IMAGES[1][2], digests[1], identities[1])
        named_parent = parent.stat()
        manifest.require((parent_info.st_dev, parent_info.st_ino) ==
                         (named_parent.st_dev, named_parent.st_ino), "output directory changed")
        os.link(staging, manifest_path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False)
        linked = True
        named = os.stat(manifest_path.name, dir_fd=parent_fd, follow_symlinks=False)
        manifest.require((named.st_dev, named.st_ino) == identity and named.st_nlink == 2,
                         "manifest publication changed")
        remove_own(parent_fd, staging, identity)
        os.fsync(parent_fd)
        named = os.stat(manifest_path.name, dir_fd=parent_fd, follow_symlinks=False)
        manifest.require((named.st_dev, named.st_ino) == identity and named.st_nlink == 1,
                         "manifest staging link remains")
        manifest.check_manifest(manifest.read_manifest(manifest_path), digests)
        manifest.unchanged(init_path, IMAGES[0][2], digests[0], identities[0])
        manifest.unchanged(carrier_path, IMAGES[1][2], digests[1], identities[1])
    except BaseException:
        if identity is not None:
            if linked:
                remove_own(parent_fd, manifest_path.name, identity)
            remove_own(parent_fd, staging, identity)
            os.fsync(parent_fd)
        raise
    finally:
        os.close(parent_fd)


manifest.paths = paths
manifest.verified_pair = verified_pair
manifest.invalidate = require_absent
manifest.publish = publish


def check_wrapper():
    names = (MANIFEST_NAME, *(item[1] for item in IMAGES))
    manifest.require(SCHEMA != CANONICAL_SCHEMA and SCHEMA != ROUTE_CACHE_SCHEMA and
                     SCHEMA != UNPINNED_SCHEMA and len(set(names)) == 3 and
                     set(names).isdisjoint(CANONICAL_NAMES) and
                     set(names).isdisjoint(ROUTE_CACHE_NAMES) and
                     set(names).isdisjoint(UNPINNED_NAMES) and
                     manifest.SCHEMA == SCHEMA and manifest.MANIFEST_NAME == MANIFEST_NAME and
                     manifest.IMAGES == IMAGES and manifest.USAGE == USAGE and
                     manifest.paths is paths and manifest.verified_pair is verified_pair and
                     manifest.invalidate is require_absent and manifest.publish is publish and
                     manifest.main.__globals__ is manifest.__dict__,
                     "unsafe mb003 no-guard candidate manifest wrapper")


def main():
    check_wrapper()
    args = sys.argv[1:]
    if len(args) >= 2 and args[-2] == "--lock-fd":
        args = args[:-2]
    manifest.require(len(args) == 8 and args[0] in ("write", "verify"), USAGE)
    lock = pathlib.Path(args[-1])
    expected_lock = pathlib.Path.home() / "sm7635-build" / "i204-root-contract.lock"
    manifest.require(lock.parent.resolve(strict=True) == expected_lock.parent.resolve(strict=True) and
                     lock.name == expected_lock.name, "wrong build lock")
    manifest.main()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error,
            lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
