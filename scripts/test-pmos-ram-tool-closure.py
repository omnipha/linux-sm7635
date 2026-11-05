#!/usr/bin/env python3
import hashlib
import pathlib
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from typing import NoReturn

HERE = pathlib.Path(__file__).resolve().parent
BUILD = HERE / "build-bootimg.sh"
CACHE = pathlib.Path.home() / "sm7635-build" / "busybox-static_1.37.0-7ubuntu1_arm64.deb"
DEB_SHA256 = "fcf50794faf920455895d7ef103d1c54b9ebf7f18d2e52982dbf3903b7769592"
BUSYBOX_SHA256 = "c2f279d1d5640a0f327890d41cad594c0f059f3fed3f96dd72fdcc4f5e18ec02"
BUSYBOX_SIZE = 1981032
APPLET_COUNT = 276
MEMBER = "./usr/bin/busybox"
QEMU = "qemu-aarch64"
PIN = re.compile(r"^BUSYBOX_(DEB|SHA256)=(\S+)$", re.MULTILINE)
DEB_PIN = "${BUSYBOX_DEB:-$WORK/busybox-static_1.37.0-7ubuntu1_arm64.deb}"
ELF64_LE = b"\x7fELF\x02\x01\x01"
ET_EXEC = 2
EM_AARCH64 = 183
EM_X86_64 = 62
PT_DYNAMIC = 2
PT_INTERP = 3
ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
SELECTED = (
    "[", "awk", "base64", "blockdev", "cat", "chmod", "chroot", "cmp", "cp",
    "cttyhack", "cut", "dd", "dmesg", "grep", "hostname", "id", "insmod", "ip",
    "kill", "ln", "mkdir", "mknod", "mount", "mv", "pidof", "ping", "printf",
    "ps", "readlink", "rm", "rmdir", "rmmod", "sed", "setsid", "sh",
    "sha256sum", "sleep", "sort", "stat", "switch_root", "sync", "tar", "tee",
    "timeout", "touch", "tr", "true", "umount", "uname", "wc",
)
SYMLINK_APPLETS = ("init", "run-parts", "udhcpc")
EXTERNAL = (
    "dropbear", "dropbearkey", "ifquery", "iw", "openrc", "rc-service",
    "rc-status", "restart2", "rmtfs", "wpa_supplicant", "wpss-once",
)


def fail(message: str) -> NoReturn:
    raise SystemExit(f"FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        fail(f"required host tool missing: {name}")
    return path


def run(args: list[str], data: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, input=data, capture_output=True, check=False, env={})


def build_pin() -> None:
    text = BUILD.read_text(encoding="ascii")
    found = dict(PIN.findall(text))
    require(found.get("DEB") == DEB_PIN, "build script BusyBox path pin differs")
    require(found.get("SHA256") == DEB_SHA256, "build script BusyBox deb pin differs")
    require(text.count(DEB_SHA256) == 1, "build script BusyBox deb pin is not unique")
    require(CACHE.name in found["DEB"], "cached deb name differs from build pin")


def elf_static(data: bytes) -> None:
    require(data.startswith(ELF64_LE) and len(data) >= 64, "BusyBox is not ELF64 little-endian")
    elf_type, machine, version, entry, phoff, _shoff, _flags, ehsize, phentsize, phnum, shentsize, shnum, _strndx = (
        struct.unpack_from("<HHIQQQIHHHHHH", data, 16))
    require(elf_type == ET_EXEC and machine == EM_AARCH64 and version == 1 and entry != 0,
            "BusyBox is not a static-position AArch64 executable")
    require(ehsize == 64 and phentsize == 56 and 0 < phnum <= 64, "malformed ELF program headers")
    require(shentsize in (0, 64) and shnum <= 512, "malformed ELF section headers")
    require(phoff >= 64 and phoff + phnum * phentsize <= len(data), "program headers extend past file")
    kinds = {struct.unpack_from("<I", data, phoff + index * phentsize)[0] for index in range(phnum)}
    require(PT_INTERP not in kinds, "BusyBox has a PT_INTERP program header")
    require(PT_DYNAMIC not in kinds, "BusyBox has a PT_DYNAMIC program header")


def member(archive: tarfile.TarFile, name: str) -> bytes:
    require(name in archive.getnames(), f"missing package member {name}")
    info = archive.getmember(name)
    require(info.isreg() and not info.issym() and not info.islnk(), f"{name} is not one regular file")
    require(stat.S_IMODE(info.mode) == 0o755, f"{name} mode is not 0755")
    handle = archive.extractfile(info)
    if handle is None:
        fail(f"cannot read {name}")
    data = handle.read()
    require(len(data) == info.size, f"{name} size differs from tar header")
    return data


def extract(deb: bytes, private: pathlib.Path, dpkg_deb: str) -> bytes:
    require_deb(deb)
    raw = private / "package.deb"
    raw.write_bytes(deb)
    listing = run([dpkg_deb, "--fsys-tarfile", str(raw)])
    require(listing.returncode == 0 and listing.stdout[257:262] == b"ustar",
            "package filesystem archive is not a tar stream")
    archive_path = private / "filesystem.tar"
    archive_path.write_bytes(listing.stdout)
    try:
        with tarfile.open(archive_path, "r:") as archive:
            binary = member(archive, MEMBER)
    except tarfile.TarError:
        fail("cannot parse package filesystem archive")
    require_binary(binary)
    elf_static(binary)
    return binary


def applets(binary: pathlib.Path, qemu: str) -> tuple[str, ...]:
    listed = run([qemu, str(binary), "--list"])
    require(listed.returncode == 0 and listed.stderr == b"", "qemu applet listing failed")
    names = tuple(listed.stdout.decode("ascii").splitlines())
    require(len(names) == APPLET_COUNT, "applet count differs from pinned package")
    require(names == tuple(sorted(set(names))), "applet listing is not sorted and unique")
    require(all(re.fullmatch(r"[a-z0-9][a-z0-9._-]*|\[\[?", name) for name in names),
            "applet listing contains an unexpected name")
    require(len(set(SELECTED)) == len(SELECTED), "selected applet list has duplicates")
    missing = sorted(set(SELECTED) - set(names))
    require(not missing, "selected production applets missing: " + " ".join(missing))
    missing = sorted(set(SYMLINK_APPLETS) - set(names))
    require(not missing, "symlink-invoked applets missing: " + " ".join(missing))
    require(set(EXTERNAL).isdisjoint(names), "external command unexpectedly listed as an applet")
    return names


def smoke(binary: pathlib.Path, qemu: str) -> None:
    done = run([qemu, str(binary), "true"])
    require(done.returncode == 0 and done.stdout == b"", "true applet failed")
    done = run([qemu, str(binary), "false"])
    require(done.returncode == 1 and done.stdout == b"", "false applet did not exit 1")
    done = run([qemu, str(binary), "sh", "-c", "exit 7"])
    require(done.returncode == 7, "sh applet did not propagate exit status")
    done = run([qemu, str(binary), "sha256sum"], b"abc")
    require(done.returncode == 0 and done.stdout.split() == [ABC_SHA256.encode(), b"-"],
            "sha256sum applet known-answer test failed")
    done = run([qemu, str(binary), "omnipha-not-an-applet"])
    require(done.returncode != 0, "unknown applet was accepted")


def rejects(label: str, call: Callable[[], object]) -> None:
    try:
        call()
    except SystemExit as exc:
        require(str(exc).startswith("FAIL: "), f"{label}: unexpected exit")
    else:
        fail(f"accepted: {label}")
    print(f"rejected: {label}")


def require_deb(deb: bytes) -> None:
    require(digest(deb) == DEB_SHA256, "BusyBox deb SHA differs")


def require_binary(binary: bytes) -> None:
    require(len(binary) == BUSYBOX_SIZE, "BusyBox binary size differs")
    require(digest(binary) == BUSYBOX_SHA256, "BusyBox binary SHA differs")


def negatives(binary: bytes, deb: bytes, private: pathlib.Path, dpkg_deb: str) -> None:
    phoff = struct.unpack_from("<Q", binary, 32)[0]
    phnum = struct.unpack_from("<H", binary, 56)[0]
    require(phnum > 0, "BusyBox has no program headers")

    def patched(offset: int, value: bytes) -> bytes:
        out = bytearray(binary)
        out[offset:offset + len(value)] = value
        return bytes(out)

    rejects("PT_INTERP program header", lambda: elf_static(patched(phoff, struct.pack("<I", PT_INTERP))))
    rejects("PT_DYNAMIC program header", lambda: elf_static(patched(phoff, struct.pack("<I", PT_DYNAMIC))))
    rejects("x86-64 machine", lambda: elf_static(patched(18, struct.pack("<H", EM_X86_64))))
    rejects("ELF32 class", lambda: elf_static(patched(4, b"\x01")))
    rejects("truncated ELF", lambda: elf_static(binary[:63]))
    flipped = patched(len(binary) // 2, b"\x00" if binary[len(binary) // 2] else b"\x01")
    rejects("altered BusyBox byte", lambda: require_binary(flipped))
    rejects("truncated deb", lambda: require_deb(deb[:-1]))
    rejects("extended deb", lambda: require_deb(deb + b"\x00"))
    rejects("altered deb", lambda: extract(deb[:-1] + bytes([deb[-1] ^ 1]), private, dpkg_deb))


def main() -> None:
    dpkg_deb = tool("dpkg-deb")
    qemu = tool(QEMU)
    require(CACHE.is_file() and not CACHE.is_symlink(), "cached BusyBox deb unavailable; not downloading")
    deb = CACHE.read_bytes()
    require_deb(deb)
    build_pin()
    print("build-bootimg.sh BUSYBOX_SHA256 equals cached deb SHA-256 " + DEB_SHA256)
    with tempfile.TemporaryDirectory(prefix="pmos-ram-tool-closure.") as private:
        root = pathlib.Path(private)
        root.chmod(0o700)
        binary = extract(deb, root, dpkg_deb)
        path = root / "busybox"
        path.write_bytes(binary)
        path.chmod(0o700)
        names = applets(path, qemu)
        smoke(path, qemu)
        negatives(binary, deb, root, dpkg_deb)
    print("pass: pinned deb, BusyBox " + BUSYBOX_SHA256 + ", static AArch64, no PT_INTERP, no PT_DYNAMIC")
    print(f"selected applets present: {len(SELECTED)} of {len(names)} listed under qemu")
    print("symlink-invoked applets listed only: " + " ".join(SYMLINK_APPLETS))
    print("not busybox, uncovered: " + " ".join(EXTERNAL))
    print("not proven: applet behavior beyond smoke, scripts outside the audited set, variants")
    print("not proven: target guest BusyBox f35a45f7, verifier or guard across switch_root")


if __name__ == "__main__":
    main()
