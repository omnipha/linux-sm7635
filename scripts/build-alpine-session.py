#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
LOCK = HERE / "alpine-session-packages.lock"
SOURCES = {
    "main": ("https://dl-cdn.alpinelinux.org/alpine/v3.21/main/aarch64/", "c3bde2900501803e2ef1a843550b1996c02073f2c81dd43d3c4edf81b1cf5fda"),
    "community": ("https://dl-cdn.alpinelinux.org/alpine/v3.21/community/aarch64/", "9864a888c3a73a9468e39805298690e195f53a2c496a9bf31ed2dd27e3f6b669"),
    "postmarketos": ("https://mirror.postmarketos.org/postmarketos/v24.12/aarch64/", "acd75f7de339358c68340a0ad957cc22ce0685603747f3322c0a6ca81f57eb1c"),
}
APK_STATIC = ("https://dl-cdn.alpinelinux.org/alpine/v3.21/main/x86_64/apk-tools-static-2.14.6-r3.apk", "f0e0d34d6a8f1f9d8704bae6612b4627b96f13cd20db759e9b43085135cd234f")
APPLETS = ("cat", "chmod", "chown", "cp", "cut", "date", "df", "dmesg", "echo", "env", "free", "grep", "head", "hostname", "id", "kill", "ln", "ls", "mkdir", "mount", "nslookup", "ping", "ps", "rm", "sed", "sha256sum", "sleep", "sort", "tail", "tar", "timeout", "touch", "tr", "udhcpc", "umount", "uname", "wc")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_lock(text):
    packages = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        repo, name, version, apk_size, installed_size, digest = line.split()
        require(repo in SOURCES and re.fullmatch("[0-9a-f]{64}", digest), f"bad lock entry: {name}")
        require(name not in packages and int(apk_size) > 0 and int(installed_size) >= 0, f"bad lock entry: {name}")
        packages[name] = (repo, version, int(apk_size), int(installed_size), digest)
    require(len(packages) == 134 and "postmarketos-base" in packages, "package closure is incomplete")
    return packages


def fetch(cache, filename, url, digest, offline):
    dest = cache / filename
    if not dest.exists():
        require(not offline, f"missing pinned input: {filename}")
        data = urlopen(url, timeout=90).read()
        require(sha256(data) == digest, f"download checksum mismatch: {filename}")
        dest.write_bytes(data)
    data = dest.read_bytes()
    require(sha256(data) == digest, f"input checksum mismatch: {filename}")
    return data


def member(data, name):
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        item = archive.getmember(name)
        require(item.isfile(), f"not a regular file: {name}")
        return archive.extractfile(item).read()


def parse_index(data):
    text = member(data, "APKINDEX").decode()
    records = {}
    for block in text.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if len(line) > 2 and line[1] == ":":
                fields[line[0]] = line[2:]
        if "P" in fields:
            records.setdefault(fields["P"], []).append(fields)
    return records


def index_record(indexes, name, version):
    for record in indexes.get(name, []):
        if record["V"] == version:
            return record
    return None


def verify_inputs(cache, packages, apk_binary, offline):
    indexes = {}
    raw_indexes = {}
    for repo, (url, digest) in SOURCES.items():
        data = fetch(cache, repo + "-APKINDEX.tar.gz", url + "APKINDEX.tar.gz", digest, offline)
        indexes[repo] = parse_index(data)
        raw_indexes[repo] = data
    raw_packages = {}
    for name, (repo, version, apk_size, installed_size, digest) in packages.items():
        filename = f"{name}-{version}.apk"
        data = fetch(cache, filename, SOURCES[repo][0] + filename, digest, offline)
        record = index_record(indexes[repo], name, version)
        require(record is not None and record["V"] == version and record["A"] in ("aarch64", "noarch"), f"index version/arch mismatch: {filename}")
        require(len(data) == apk_size and int(record["S"]) == apk_size and int(record["I"]) == installed_size, f"index size mismatch: {filename}")
        info = member(data, ".PKGINFO").decode()
        require(f"pkgname = {name}\n" in info and f"pkgver = {version}\n" in info, f"package metadata mismatch: {filename}")
        raw_packages[name] = data
    with tempfile.TemporaryDirectory(prefix="issue139-trust-") as temp:
        root = Path(temp)
        keys = root / "keys"
        keys.mkdir()
        for pkg, name in (("alpine-keys", "alpine-devel@lists.alpinelinux.org-616ae350.rsa.pub"), ("postmarketos-keys", "build.postmarketos.org.rsa.pub")):
            (keys / name).write_bytes(member(raw_packages[pkg], "etc/apk/keys/" + name))
        for repo, data in raw_indexes.items():
            path = root / (repo + ".tar.gz")
            path.write_bytes(data)
            result = subprocess.run([apk_binary, "verify", "--keys-dir", keys, path], capture_output=True, text=True, check=False)
            require(result.returncode == 0 and " - OK" in result.stdout, f"untrusted index: {repo}")
        for name, (repo, version, _, _, _) in packages.items():
            if repo != "postmarketos":
                result = subprocess.run([apk_binary, "verify", "--keys-dir", keys, cache / (name + "-" + version + ".apk")], capture_output=True, text=True, check=False)
                require(result.returncode == 0 and " - OK" in result.stdout, f"untrusted Alpine package: {name}")


def pack_rootfs(stage, destination):
    with destination.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(stage.rglob("*")):
            relative = path.relative_to(stage)
            info = archive.gettarinfo(str(path), arcname="./" + str(relative))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 1700000000
            if path.is_file() and not path.is_symlink():
                mode = stat.S_IMODE(path.stat().st_mode)
                try:
                    path.chmod(mode | stat.S_IRUSR)
                    with path.open("rb") as file:
                        archive.addfile(info, file)
                finally:
                    path.chmod(mode)
            else:
                archive.addfile(info)


def check_runtime(stage):
    libraries = {p.name for base in (stage / "lib", stage / "usr/lib") for p in base.rglob("*") if p.is_file() or p.is_symlink()}
    count = 0
    for path in stage.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        try:
            path.chmod(mode | stat.S_IRUSR)
            with path.open("rb") as file:
                header = file.read(20)
            if not header.startswith(b"\x7fELF"):
                continue
            require(header[4:6] == b"\x02\x01" and struct.unpack_from("<H", header, 18)[0] == 183, f"wrong ELF architecture: {path}")
            result = subprocess.run(["readelf", "-l", "-d", str(path)], capture_output=True, text=True, check=True).stdout
            for needed in re.findall(r"\(NEEDED\).*?\[(.*?)\]", result):
                require(needed in libraries, f"missing ELF library {needed} for {path}")
            for interpreter in re.findall(r"Requesting program interpreter: (.*?)\]", result):
                require(interpreter == "/lib/ld-musl-aarch64.so.1" and (stage / interpreter.lstrip("/")).exists(), f"wrong ELF interpreter: {path}")
            count += 1
        finally:
            path.chmod(mode)
    require(count == 390, "ELF inventory incomplete")
    require('ID="postmarketos"' in (stage / "usr/lib/os-release").read_text(), "postmarketOS identity absent")
    require((stage / "bin/sh").is_symlink() and (stage / "usr/sbin/dropbear").is_file(), "shell or SSH service absent")
    require((stage / "sbin/wpa_supplicant").is_file() and (stage / "usr/sbin/iw").is_file(), "WLAN clients absent")
    require(not (stage / "root/.ssh/authorized_keys").exists(), "unexpected credential in stage")
    return count


def assemble(cache, output, offline=False):
    require(not cache.is_relative_to(REPO_ROOT) and not output.is_relative_to(REPO_ROOT), "artifacts must remain outside Git")
    require(cache != output, "cache and output must differ")
    packages = parse_lock(LOCK.read_text())
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    static_data = fetch(cache, "apk-tools-static-2.14.6-r3-x86_64.apk", *APK_STATIC, offline)
    with tempfile.TemporaryDirectory(prefix="issue139-", dir=output) as temp:
        work = Path(temp)
        apk_binary = work / "apk.static"
        apk_binary.write_bytes(member(static_data, "sbin/apk.static"))
        apk_binary.chmod(0o700)
        verify_inputs(cache, packages, apk_binary, offline)
        stage = work / "rootfs"
        stage.mkdir(mode=0o700)
        (stage / "etc/apk").mkdir(parents=True)
        (stage / "etc/apk/arch").write_text("aarch64\n")
        (stage / "etc/apk/world").touch()
        (stage / "etc/apk/repositories").write_text("".join(SOURCES[repo][0].removesuffix("aarch64/") + "\n" for repo in SOURCES))
        cmd = [apk_binary, "--root", stage, "--arch", "aarch64", "--initdb", "--no-scripts", "--no-commit-hooks", "--no-network", "--allow-untrusted", "add"]
        cmd.extend(str(cache / f"{name}-{version}.apk") for name, (_, version, _, _, _) in sorted(packages.items()))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        require(result.returncode == 0 and "134 packages" in result.stdout, "apk failed to install frozen closure")
        installed = subprocess.run([apk_binary, "--root", stage, "--arch", "aarch64", "list", "--installed"], check=True, capture_output=True, text=True).stdout
        actual = {line.split(" ", 1)[0] for line in installed.splitlines()}
        expected = {name + "-" + version for name, (_, version, _, _, _) in packages.items()}
        require(actual == expected, "installed package set differs from frozen closure")
        for link in APPLETS:
            dest = stage / "bin" / link
            if not dest.exists() and not dest.is_symlink():
                dest.symlink_to("busybox")
        for path in ("root/.ssh", "etc/dropbear", "dev/pts", "proc", "sys", "run"):
            (stage / path).mkdir(parents=True, exist_ok=True)
        (stage / "root").chmod(0o700)
        (stage / "root/.ssh").chmod(0o700)
        (stage / "etc/shadow").write_text("root:!:0:0:99999:7:::\n")
        (stage / "etc/shadow").chmod(0o600)
        count = check_runtime(stage)
        archive = work / "rootfs.tar.gz"
        pack_rootfs(stage, archive)
        size = archive.stat().st_size
        require(size < 32 * 1024 * 1024, "RAM transport exceeds 32 MiB cap")
        dest = output / "postmarketos-session-aarch64.tar.gz"
        shutil.copyfile(archive, dest)
        summary = {"packages": len(packages), "apk_bytes": sum(v[2] for v in packages.values()), "index_sha256": {repo: sha for repo, (_, sha) in SOURCES.items()}, "transport_bytes": size, "transport_sha256": sha256(dest.read_bytes()), "aarch64_elfs": count, "uncompressed_bytes": sum(p.stat().st_size for p in stage.rglob("*") if p.is_file() and not p.is_symlink())}
        (output / "postmarketos-session-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path.home() / "sm7635-build/i139-userspace/cache")
    parser.add_argument("--output", type=Path, default=Path.home() / "sm7635-build/i139-userspace/out")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    assemble(args.cache.resolve(), args.output.resolve(), args.offline)


if __name__ == "__main__":
    main()
