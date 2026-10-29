#!/usr/bin/env python3
import hashlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).parent
IMAGE_SIZE = 33554432
BLOCKS = 8192
ARCHIVE_SIZE = 23713302
ARCHIVE_SHA = "7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26"
ARCHIVE_PATH = "omnipha-userspace/postmarketos-session-aarch64.tar.gz"
DIRECTORY = "omnipha-userspace"
TIMESTAMP = 1767225600
UUID = "6f6d6e69-7068-4170-6d6f-732d7573726b"
HASH_SEED = "6f6d6e69-7068-4173-6565-642d75737264"
LABEL = "omnipha-pmos"
REFUSED = frozenset((
    "baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193",
    "fef030081e04d3a90451bb7d64dcfa7668c41dc4248e6e0b1959fdb40efce948",
    "4b83ea24c305d731b168c2e2f12bd0ebd5d4a18de9039eaf8b0e0ca452b464f7",
    "1bdb7c2252b3192127aed0a2f8953d928be0f36a00a259582e7a75a98a029f5f",
    "bee02ce1f31d628fd95879fb519d4b131f3d8a3298530d1fc31c390db528f412",
    "41cab142203b4ccf894f7bea24398d21ff959ab72d3473e88379d2780bdc9afd",
    "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253",
    "6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b",
))
ARCHIVE_MSG = "userspace archive size or SHA-256 differs from the pinned measurement"
SIZE_MSG = "userdata ext4 image is not 33554432 bytes"
SHA_MSG = "userdata image repeats a stock, measured or refused SHA-256"
IMAGE_MSG = "userdata ext4 image is not the deterministic single-archive filesystem"
PATH_MSG = "output must be outside Git, different from the archive and not a symlink"
GIT_MSG = "userdata ext4 image or private profile is present in Git"
TOOL_MSG = "required e2fsprogs tool is unavailable"
MKE2FS_CONFIG = """[fs_types]
	ext4 = {
		features = extent,huge_file,flex_bg,metadata_csum,64bit,dir_nlink,extra_isize,large_file,sparse_super,filetype,ext_attr
		blocksize = 4096
		inode_size = 256
		inode_ratio = 16384
	}
	omnipha = {
		features = extent,huge_file,flex_bg,metadata_csum,64bit,dir_nlink,extra_isize,large_file,sparse_super,filetype,ext_attr
		blocksize = 4096
		inode_size = 256
		inode_ratio = 16384
	}
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def tool(name):
    found = shutil.which(name) or ("/sbin/" + name if os.path.exists("/sbin/" + name) else None)
    require(found is not None, f"{TOOL_MSG}: {name}")
    return found


def run(args, env=None):
    merged = dict(os.environ if env is None else env)
    merged.setdefault("LC_ALL", "C")
    merged.setdefault("TZ", "UTC")
    proc = subprocess.run(args, capture_output=True, env=merged)
    require(proc.returncode == 0,
            f"{' '.join(os.path.basename(a) for a in args[:1])} failed: "
            f"{proc.stderr.decode(errors='replace')[-400:]}")
    return proc.stdout


def check_archive(archive):
    require(len(archive) == ARCHIVE_SIZE and sha256(archive) == ARCHIVE_SHA, ARCHIVE_MSG)


def tar_bytes(archive):
    check_archive(archive)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
        for name in (DIRECTORY, ARCHIVE_PATH):
            info = tarfile.TarInfo(name)
            info.mtime = TIMESTAMP
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if name == DIRECTORY:
                info.type = tarfile.DIRTYPE
                info.mode = 0o700
                bundle.addfile(info)
            else:
                info.size = len(archive)
                info.mode = 0o444
                bundle.addfile(info, io.BytesIO(archive))
    return raw.getvalue()


def makefs(archive, target):
    return makefs_tar(tar_bytes(archive), target)


def makefs_tar(tar, target):
    target = pathlib.Path(target)
    with tempfile.TemporaryDirectory(prefix="userdata-mke2fs.") as scratch:
        scratch = pathlib.Path(scratch)
        (scratch / "mke2fs.conf").write_text(MKE2FS_CONFIG)
        (scratch / "root.tar").write_bytes(tar)
        env = dict(os.environ)
        env.update(MKE2FS_CONFIG=str(scratch / "mke2fs.conf"),
                   E2FSPROGS_FAKE_TIME=str(TIMESTAMP), SOURCE_DATE_EPOCH=str(TIMESTAMP),
                   LC_ALL="C", TZ="UTC")
        run([tool("mke2fs"), "-q", "-F", "-t", "ext4", "-T", "omnipha", "-b", "4096",
             "-N", "32", "-m", "0", "-L", LABEL, "-U", UUID,
             "-E", f"hash_seed={HASH_SEED},root_owner=0:0,lazy_itable_init=0,"
                   "lazy_journal_init=0,offset=0",
             "-O", "^has_journal,^resize_inode", "-d", str(scratch / "root.tar"),
             str(target), str(BLOCKS)], env=env)
    return target.read_bytes()


def filesystem_ok(path):
    path = pathlib.Path(path)
    run([tool("e2fsck"), "-f", "-n", str(path)])
    listing = run([tool("debugfs"), "-R", "ls -l /", str(path)]).decode()
    entries = [line for line in listing.splitlines() if line.strip()[:1].isdigit()]
    names = [line.split()[-1] for line in entries]
    require(names == [".", "..", "lost+found", DIRECTORY], IMAGE_MSG)
    require(all(line.split()[1] == "40755" for line in entries[:2]) and
            entries[3].split()[1] == "40700", IMAGE_MSG)
    stat = run([tool("debugfs"), "-R", f"stat /{ARCHIVE_PATH}", str(path)]).decode()
    require("Type: regular" in stat and f"Size: {ARCHIVE_SIZE}" in stat and
            "Links: 1" in stat and "Fast link dest:" not in stat, IMAGE_MSG)
    return listing


def extract(path):
    with tempfile.TemporaryDirectory(prefix="userdata-extract.") as scratch:
        out = pathlib.Path(scratch) / "archive"
        run([tool("debugfs"), "-R", f"dump -p /{ARCHIVE_PATH} {out}", str(path)])
        return out.read_bytes()


def check_image(image, archive):
    check_archive(archive)
    require(len(image) == IMAGE_SIZE, SIZE_MSG)
    require(sha256(image) not in REFUSED, SHA_MSG)
    with tempfile.TemporaryDirectory(prefix="userdata-verify.") as scratch:
        scratch = pathlib.Path(scratch)
        path = scratch / "image"
        path.write_bytes(image)
        filesystem_ok(path)
        require(extract(path) == archive, ARCHIVE_MSG)
        require(makefs(archive, scratch / "repro") == image, IMAGE_MSG)
    return sha256(image)


def check_output_path(candidate, archive):
    output = pathlib.Path(candidate)
    require(output.parent.is_dir() and not output.is_symlink() and not output.is_dir(), PATH_MSG)
    resolved = output.resolve()
    require(not resolved.is_relative_to(HERE.parent.resolve()) and
            resolved != pathlib.Path(archive).resolve(), PATH_MSG)
    return output


def check_git_absent():
    proc = subprocess.run(["git", "-C", str(HERE.parent), "status", "--porcelain", "--ignored"],
                          check=True, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        name = line[3:].split(" -> ")[-1]
        require(not name.endswith((".img", ".tar", ".tar.xz", ".tar.gz")) and
                "wpa_supplicant.conf" not in name, GIT_MSG)


def self_test(image, archive):
    check_image(image, archive)
    check_git_absent()

    def bad(label, message, candidate, payload=archive):
        try:
            check_image(candidate, payload)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture accepted")

    bad("short image", SIZE_MSG, image[:-4096])
    bad("archive input", ARCHIVE_MSG, image, archive[:-1])
    with tempfile.TemporaryDirectory(prefix="userdata-neg.") as scratch:
        scratch = pathlib.Path(scratch)
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
            for name in (DIRECTORY, ARCHIVE_PATH, "extra"):
                info = tarfile.TarInfo(name)
                info.mtime = TIMESTAMP
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                if name == DIRECTORY:
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o700
                    bundle.addfile(info)
                elif name == "extra":
                    info.size = 1
                    info.mode = 0o444
                    bundle.addfile(info, io.BytesIO(b"x"))
                else:
                    info.size = len(archive)
                    info.mode = 0o444
                    bundle.addfile(info, io.BytesIO(archive))
        bad("extra root entry", IMAGE_MSG, makefs_tar(raw.getvalue(), scratch / "extra.img"))
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
            info = tarfile.TarInfo(DIRECTORY)
            info.type = tarfile.DIRTYPE
            info.mode = 0o700
            info.mtime = TIMESTAMP
            bundle.addfile(info)
            real = tarfile.TarInfo(f"{DIRECTORY}/real.tar.gz")
            real.size = len(archive)
            real.mode = 0o444
            real.mtime = TIMESTAMP
            bundle.addfile(real, io.BytesIO(archive))
            link = tarfile.TarInfo(ARCHIVE_PATH)
            link.type = tarfile.SYMTYPE
            link.linkname = "real.tar.gz"
            link.mtime = TIMESTAMP
            bundle.addfile(link)
        bad("symlinked archive", IMAGE_MSG, makefs_tar(raw.getvalue(), scratch / "symlink.img"))
        changed = bytearray(archive)
        changed[-1] ^= 1
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
            info = tarfile.TarInfo(DIRECTORY)
            info.type = tarfile.DIRTYPE
            info.mode = 0o700
            info.mtime = TIMESTAMP
            bundle.addfile(info)
            item = tarfile.TarInfo(ARCHIVE_PATH)
            item.size = len(changed)
            item.mode = 0o444
            item.mtime = TIMESTAMP
            bundle.addfile(item, io.BytesIO(bytes(changed)))
        bad("changed archive byte", ARCHIVE_MSG,
            makefs_tar(raw.getvalue(), scratch / "changed.img"))
    for sha in REFUSED:
        require(sha != sha256(image), SHA_MSG)
    try:
        check_output_path(HERE.parent / "userdata.img", "/nonexistent-archive")
    except ValueError as exc:
        require(str(exc) == PATH_MSG, "repo output check changed")
    else:
        raise ValueError("repo output path accepted")
    print("userdata payload negative mutations: OK")


def main():
    args = sys.argv[1:]
    require(len(args) == 3 and args[0] in ("--build", "--verify", "--self-test"),
            "usage: build-userdata-userspace-payload.py --build|--verify|--self-test ARCHIVE CANDIDATE")
    mode, archive_path, candidate_path = args
    archive_file = pathlib.Path(archive_path)
    require(archive_file.is_file() and not archive_file.is_symlink(),
            "missing or symlinked userspace archive")
    archive = archive_file.read_bytes()
    check_archive(archive)
    output = check_output_path(candidate_path, archive_path)
    check_git_absent()
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
    check_git_absent()
    print(f"userdata ext4 payload: {len(image)} bytes, SHA-256 {sha256(image)}")
    print(f"fixed UUID {UUID}, hash seed {HASH_SEED}, timestamps {TIMESTAMP}; "
          f"no journal, one regular file /{ARCHIVE_PATH}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
