#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).parent
IMAGE_SIZE = 100663296
BLOCKS = 24576
TIMESTAMP = 1767225600
UUID = "6f6d6e69-7068-4170-6d6f-732d726f6f74"
HASH_SEED = "6f6d6e69-7068-4173-6565-642d726f6f74"
LABEL = "omnipha-root"
ARCHIVE_MSG = "userspace archive size or SHA-256 differs from the pinned measurement"
SIZE_MSG = "persistent userdata ext4 image is not 100663296 bytes"
SHA_MSG = "persistent userdata image repeats a stock, measured or refused SHA-256"
IMAGE_MSG = "persistent userdata image is not the deterministic unpacked postmarketOS root"
PATH_MSG = "output must be outside Git, different from the archive and not a symlink"
GIT_MSG = "persistent userdata image or private profile is present in Git"
REFUSED = frozenset((
    "ea09444c0ddde87e970d0b27cb8c067a28424da6501eed88bca749729855d4ed",
    "1bdb7c2252b3192127aed0a2f8953d928be0f36a00a259582e7a75a98a029f5f",
    "41cab142203b4ccf894f7bea24398d21ff959ab72d3473e88379d2780bdc9afd",
))
MKE2FS_CONFIG = """[fs_types]
	omnipha = {
		features = extent,huge_file,flex_bg,metadata_csum,64bit,dir_nlink,extra_isize,large_file,sparse_super,filetype,ext_attr
		blocksize = 4096
		inode_size = 256
		inode_ratio = 16384
	}
"""


def load():
    spec = importlib.util.spec_from_file_location("userdata_payload", HERE / "build-userdata-userspace-payload.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


payload = load()
require = payload.require
run = payload.run
tool = payload.tool


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def clean_name(name):
    while name.startswith("./"):
        name = name[2:]
    require(name and name != "." and not name.startswith("/") and
            all(part not in ("", ".", "..") for part in name.split("/")), IMAGE_MSG)
    return name.rstrip("/")


def root_tar(archive):
    payload.check_archive(archive)
    raw = io.BytesIO()
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source, \
            tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as target:
        for item in source.getmembers():
            name = clean_name(item.name)
            require(name not in seen and (item.isdir() or item.isfile() or item.issym()), IMAGE_MSG)
            seen.add(name)
            info = tarfile.TarInfo(name)
            info.mtime = TIMESTAMP
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = item.mode
            if item.isdir():
                info.type = tarfile.DIRTYPE
                target.addfile(info)
            elif item.issym():
                info.type = tarfile.SYMTYPE
                info.linkname = item.linkname
                require(info.linkname and "\0" not in info.linkname, IMAGE_MSG)
                target.addfile(info)
            else:
                data = source.extractfile(item).read()
                require(len(data) == item.size, IMAGE_MSG)
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
    for name in ("bin/busybox", "sbin/openrc", "usr/lib/os-release", "etc/local.d",
                 "etc/runlevels/default", "root/.ssh"):
        require(name in seen, IMAGE_MSG)
    return raw.getvalue()


def makefs_tar(tar, target):
    target = pathlib.Path(target)
    with tempfile.TemporaryDirectory(prefix="persistent-root-mke2fs.") as scratch:
        scratch = pathlib.Path(scratch)
        (scratch / "mke2fs.conf").write_text(MKE2FS_CONFIG)
        (scratch / "root.tar").write_bytes(tar)
        env = dict(os.environ)
        env.update(MKE2FS_CONFIG=str(scratch / "mke2fs.conf"),
                   E2FSPROGS_FAKE_TIME=str(TIMESTAMP), SOURCE_DATE_EPOCH=str(TIMESTAMP),
                   LC_ALL="C", TZ="UTC")
        run([tool("mke2fs"), "-q", "-F", "-t", "ext4", "-T", "omnipha", "-b", "4096",
             "-m", "0", "-L", LABEL, "-U", UUID,
             "-E", f"hash_seed={HASH_SEED},root_owner=0:0,lazy_itable_init=0,"
                   "lazy_journal_init=0,offset=0",
             "-O", "^has_journal,^resize_inode", "-d", str(scratch / "root.tar"),
             str(target), str(BLOCKS)], env=env)
    return target.read_bytes()


def makefs(archive, target):
    return makefs_tar(root_tar(archive), target)


def filesystem_ok(path):
    run([tool("e2fsck"), "-f", "-n", str(path)])
    listing = run([tool("debugfs"), "-R", "ls -l /", str(path)]).decode()
    names = [line.split()[-1] for line in listing.splitlines() if line.strip()[:1].isdigit()]
    require(names[:2] == [".", ".."] and "lost+found" in names and
            all(name in names for name in ("bin", "etc", "sbin", "usr")) and
            "omnipha-userspace" not in names, IMAGE_MSG)
    for name, kind in (("bin/busybox", "regular"), ("sbin/openrc", "regular"),
                       ("usr/lib/os-release", "regular")):
        stat = run([tool("debugfs"), "-R", f"stat /{name}", str(path)]).decode()
        require(f"Type: {kind}" in stat and "Fast link dest:" not in stat, IMAGE_MSG)
    require("ID=\"postmarketos\"" in run(
        [tool("debugfs"), "-R", "cat /usr/lib/os-release", str(path)]).decode(), IMAGE_MSG)


def check_image(image, archive):
    payload.check_archive(archive)
    require(len(image) == IMAGE_SIZE, SIZE_MSG)
    require(sha256(image) not in REFUSED, SHA_MSG)
    with tempfile.TemporaryDirectory(prefix="persistent-root-verify.") as scratch:
        scratch = pathlib.Path(scratch)
        path = scratch / "image"
        path.write_bytes(image)
        filesystem_ok(path)
        require(makefs(archive, scratch / "repro") == image, IMAGE_MSG)
    return sha256(image)


def self_test(image, archive):
    check_image(image, archive)
    payload.check_git_absent()

    def bad(label, message, candidate, source=archive):
        try:
            check_image(candidate, source)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture accepted")

    bad("short image", SIZE_MSG, image[:-4096])
    bad("archive input", ARCHIVE_MSG, image, archive[:-1])
    with tempfile.TemporaryDirectory(prefix="persistent-root-neg.") as scratch:
        scratch = pathlib.Path(scratch)
        raw = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source, \
                tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as target:
            for item in source.getmembers():
                target.addfile(item, source.extractfile(item) if item.isfile() else None)
            info = tarfile.TarInfo("extra")
            info.size = 1
            info.mtime = TIMESTAMP
            target.addfile(info, io.BytesIO(b"x"))
        bad("extra root entry", IMAGE_MSG, makefs_tar(raw.getvalue(), scratch / "extra.img"))
        changed = bytearray(archive)
        changed[-1] ^= 1
        bad("changed archive byte", ARCHIVE_MSG, image, bytes(changed))
    for digest in REFUSED:
        require(digest != sha256(image), SHA_MSG)
    try:
        payload.check_output_path(HERE.parent / "userdata-root.img", "/nonexistent-archive")
    except ValueError as exc:
        require(str(exc) == payload.PATH_MSG, "repo output check changed")
    else:
        raise ValueError("repo output path accepted")
    print("persistent userdata negative mutations: OK")


def main():
    args = sys.argv[1:]
    require(len(args) == 3 and args[0] in ("--build", "--verify", "--self-test"),
            "usage: build-userdata-persistent-root.py --build|--verify|--self-test ARCHIVE CANDIDATE")
    mode, archive_path, candidate_path = args
    archive_file = pathlib.Path(archive_path)
    require(archive_file.is_file() and not archive_file.is_symlink(),
            "missing or symlinked userspace archive")
    archive = archive_file.read_bytes()
    payload.check_archive(archive)
    output = payload.check_output_path(candidate_path, archive_path)
    payload.check_git_absent()
    if mode == "--build":
        image = makefs(archive, output)
        require(len(image) == IMAGE_SIZE, SIZE_MSG)
        check_image(image, archive)
    else:
        require(output.is_file() and not output.is_symlink(), "missing candidate image")
        image = output.read_bytes()
        if mode == "--self-test":
            self_test(image, archive)
        check_image(image, archive)
    payload.check_git_absent()
    print(f"persistent userdata ext4 root: {len(image)} bytes, SHA-256 {sha256(image)}")
    print(f"fixed UUID {UUID}, hash seed {HASH_SEED}, timestamps {TIMESTAMP}; "
          "no journal, unpacked pinned postmarketOS userspace")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, tarfile.TarError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
