#!/usr/bin/env python3
import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

PAGE = 4096
STOCK_SIZE = 100663296
STOCK_SHA256 = "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253"
ARCHIVE_SHA256 = "7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26"
ARCHIVE_SIZE = 23713302
SIGNED_PREFIX = 18256512
VBMETA_OFFSET = 18255872
HEADER_OFFSET = 18870272
ARCHIVE_OFFSET = 18874368
FOOTER_SIZE = 64
MARKER = b"OMNIPHA_VENDOR_BOOT_B_USERSPACE_V1"
REPO = pathlib.Path(__file__).resolve().parent.parent
STOCK_MSG = "stock vendor_boot_b is not the verified 100663296-byte 23725940 image"
PAIR_MSG = "stock vendor_boot_a and vendor_boot_b are not byte-identical"
ARCHIVE_MSG = "userspace archive is not the pinned 23713302-byte 7a76a110 archive"
HEADER_MSG = "payload header is not the pinned 4096-byte ASCII record"
BOUND_MSG = "payload does not fit at the 4096-aligned offset before the footer"
GAP_MSG = "image is not zero outside the signed prefix, header and archive"
PREFIX_MSG = "stock signed prefix through offset 18256512 was modified"
FOOTER_MSG = "stock terminal 64-byte footer was modified"
SIZE_MSG = "payload image is not 100663296 bytes"
IDEMPOTENT_MSG = "rebuilding over an existing or stock image is not byte-identical"
PATH_MSG = "output path must be outside the git repository and distinct from inputs"
GIT_MSG = "payload artifact is present inside the git repository"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def header_bytes(archive):
    text = (f"{MARKER.decode('ascii')}\n"
            f"size={len(archive)}\n"
            f"sha256={sha256(archive)}\n").encode("ascii")
    require(len(text) <= PAGE, HEADER_MSG)
    return text + bytes(PAGE - len(text))


def check_stock(stock, stock_a=None):
    require(len(stock) == STOCK_SIZE and sha256(stock) == STOCK_SHA256, STOCK_MSG)
    if stock_a is not None:
        require(stock == stock_a, PAIR_MSG)
    require(stock[:8] == b"VNDRBOOT", STOCK_MSG)
    require(stock[VBMETA_OFFSET:VBMETA_OFFSET + 4] == b"AVB0", STOCK_MSG)
    require(any(stock[VBMETA_OFFSET:SIGNED_PREFIX]), STOCK_MSG)
    require(stock[-FOOTER_SIZE:-FOOTER_SIZE + 4] == b"AVBf", STOCK_MSG)
    require(not any(stock[SIGNED_PREFIX:-FOOTER_SIZE]), STOCK_MSG)


def check_archive(archive, bound=STOCK_SIZE - FOOTER_SIZE):
    require(len(archive) == ARCHIVE_SIZE and sha256(archive) == ARCHIVE_SHA256, ARCHIVE_MSG)
    end = ARCHIVE_OFFSET + len(archive)
    require(HEADER_OFFSET == ARCHIVE_OFFSET - PAGE and
            HEADER_OFFSET % PAGE == 0 and
            ARCHIVE_OFFSET % PAGE == 0 and
            SIGNED_PREFIX <= HEADER_OFFSET and
            end <= bound, BOUND_MSG)
    return end


def assemble(stock, archive, stock_a=None, bound=STOCK_SIZE - FOOTER_SIZE):
    check_stock(stock, stock_a)
    end = check_archive(archive, bound)
    header = header_bytes(archive)
    image = bytearray(stock)
    image[SIGNED_PREFIX:-FOOTER_SIZE] = bytes(STOCK_SIZE - FOOTER_SIZE - SIGNED_PREFIX)
    image[HEADER_OFFSET:ARCHIVE_OFFSET] = header
    image[ARCHIVE_OFFSET:end] = archive
    return bytes(image), header, end


def reassemble(existing, stock, archive):
    check_stock(stock)
    end = check_archive(archive)
    header = header_bytes(archive)
    require(len(existing) == STOCK_SIZE and
            existing[:SIGNED_PREFIX] == stock[:SIGNED_PREFIX] and
            existing[-FOOTER_SIZE:] == stock[-FOOTER_SIZE:], IDEMPOTENT_MSG)
    image = bytearray(existing)
    image[SIGNED_PREFIX:-FOOTER_SIZE] = bytes(STOCK_SIZE - FOOTER_SIZE - SIGNED_PREFIX)
    image[HEADER_OFFSET:ARCHIVE_OFFSET] = header
    image[ARCHIVE_OFFSET:end] = archive
    return bytes(image)


def check_image(image, stock, archive, stock_a=None, bound=STOCK_SIZE - FOOTER_SIZE):
    check_stock(stock, stock_a)
    end = check_archive(archive, bound)
    require(len(image) == STOCK_SIZE, SIZE_MSG)
    require(image[:SIGNED_PREFIX] == stock[:SIGNED_PREFIX] and
            image[VBMETA_OFFSET:VBMETA_OFFSET + 4] == b"AVB0", PREFIX_MSG)
    require(image[-FOOTER_SIZE:] == stock[-FOOTER_SIZE:] and
            image[-FOOTER_SIZE:-FOOTER_SIZE + 4] == b"AVBf", FOOTER_MSG)
    header = header_bytes(archive)
    raw_header = image[HEADER_OFFSET:ARCHIVE_OFFSET]
    body_len = len(header.rstrip(b"\x00"))
    require(raw_header[:body_len] == header[:body_len] and
            not any(raw_header[body_len:]) and
            raw_header == header, HEADER_MSG)
    require(image[ARCHIVE_OFFSET:end] == archive and
            sha256(image[ARCHIVE_OFFSET:end]) == ARCHIVE_SHA256, ARCHIVE_MSG)
    require(not any(image[SIGNED_PREFIX:HEADER_OFFSET]) and
            not any(image[end:-FOOTER_SIZE]), GAP_MSG)
    rebuilt = assemble(stock, archive, stock_a, bound)[0]
    require(image == rebuilt and reassemble(image, stock, archive) == image, IDEMPOTENT_MSG)
    return header, end


def check_output_path(output, inputs, repo=REPO):
    out = pathlib.Path(output)
    require(not out.is_symlink() and out.parent.is_dir(), PATH_MSG)
    resolved = out.resolve(strict=False)
    repo_root = pathlib.Path(repo).resolve()
    require(resolved != repo_root and repo_root not in resolved.parents, PATH_MSG)
    for item in inputs:
        require(resolved != pathlib.Path(item).resolve(), PATH_MSG)
    return resolved


def check_git_absent(output=None, repo=REPO):
    repo_root = pathlib.Path(repo).resolve()
    if output is not None:
        resolved = pathlib.Path(output).resolve(strict=False)
        require(resolved != repo_root and repo_root not in resolved.parents, GIT_MSG)
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--ignored"],
        check=True, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        path = line[3:].split(" -> ")[-1]
        require(not path.endswith(".img") and not path.endswith(".tar.gz"), GIT_MSG)


def flipped(data, index):
    out = bytearray(data)
    out[index] ^= 1
    return bytes(out)


def self_test(candidate, stock_b, archive, stock_a=None):
    header, end = check_image(candidate, stock_b, archive, stock_a)
    check_git_absent()

    def bad(label, expected, fn):
        try:
            fn()
        except ValueError as exc:
            require(str(exc) == expected, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture was accepted")

    bad("corrupt stock byte", STOCK_MSG,
        lambda: check_image(candidate, flipped(stock_b, 0), archive, stock_a))
    bad("missing stock bytes", STOCK_MSG,
        lambda: check_image(candidate, b"", archive, stock_a))
    bad("corrupt stock AVB0", STOCK_MSG,
        lambda: check_stock(stock_b[:VBMETA_OFFSET] + b"XXXX" + stock_b[VBMETA_OFFSET + 4:]))
    bad("corrupt stock footer", STOCK_MSG,
        lambda: check_stock(stock_b[:-FOOTER_SIZE] + b"XXXX" + stock_b[-FOOTER_SIZE + 4:]))
    bad("dirty stock tail", STOCK_MSG,
        lambda: check_stock(flipped(stock_b, SIGNED_PREFIX)))
    if stock_a is not None:
        bad("mismatched slot A/B", PAIR_MSG,
            lambda: check_image(candidate, stock_b, archive, flipped(stock_a, 0)))
    bad("corrupt archive source", ARCHIVE_MSG,
        lambda: check_image(candidate, stock_b, flipped(archive, 0), stock_a))
    bad("missing archive source", ARCHIVE_MSG,
        lambda: check_image(candidate, stock_b, b"", stock_a))
    bad("truncated archive source", ARCHIVE_MSG,
        lambda: check_image(candidate, stock_b, archive[:-1], stock_a))
    bad("corrupt embedded archive first byte", ARCHIVE_MSG,
        lambda: check_image(flipped(candidate, ARCHIVE_OFFSET), stock_b, archive, stock_a))
    bad("corrupt embedded archive last byte", ARCHIVE_MSG,
        lambda: check_image(flipped(candidate, end - 1), stock_b, archive, stock_a))
    bad("missing embedded archive", ARCHIVE_MSG,
        lambda: check_image(stock_b[:HEADER_OFFSET] + header +
                            bytes(STOCK_SIZE - ARCHIVE_OFFSET - FOOTER_SIZE) +
                            stock_b[-FOOTER_SIZE:], stock_b, archive, stock_a))
    bad("corrupt header marker", HEADER_MSG,
        lambda: check_image(flipped(candidate, HEADER_OFFSET), stock_b, archive, stock_a))
    bad("corrupt header size", HEADER_MSG,
        lambda: check_image(flipped(candidate, HEADER_OFFSET + len(MARKER) + 6),
                            stock_b, archive, stock_a))
    bad("corrupt header sha256", HEADER_MSG,
        lambda: check_image(flipped(candidate, HEADER_OFFSET + len(MARKER) + 22),
                            stock_b, archive, stock_a))
    bad("missing header", HEADER_MSG,
        lambda: check_image(candidate[:HEADER_OFFSET] + bytes(PAGE) +
                            candidate[ARCHIVE_OFFSET:], stock_b, archive, stock_a))
    bad("nonzero header padding", HEADER_MSG,
        lambda: check_image(flipped(candidate, ARCHIVE_OFFSET - 1), stock_b, archive, stock_a))
    bad("payload exceeds bound", BOUND_MSG,
        lambda: check_image(candidate, stock_b, archive, stock_a, bound=end - 1))
    bad("changed signed prefix header", PREFIX_MSG,
        lambda: check_image(flipped(candidate, 16), stock_b, archive, stock_a))
    bad("changed signed prefix AVB0", PREFIX_MSG,
        lambda: check_image(flipped(candidate, VBMETA_OFFSET), stock_b, archive, stock_a))
    bad("changed signed prefix last byte", PREFIX_MSG,
        lambda: check_image(flipped(candidate, SIGNED_PREFIX - 1), stock_b, archive, stock_a))
    bad("changed footer magic", FOOTER_MSG,
        lambda: check_image(flipped(candidate, STOCK_SIZE - FOOTER_SIZE),
                            stock_b, archive, stock_a))
    bad("changed footer last byte", FOOTER_MSG,
        lambda: check_image(flipped(candidate, STOCK_SIZE - 1), stock_b, archive, stock_a))
    bad("nonzero gap before header", GAP_MSG,
        lambda: check_image(flipped(candidate, SIGNED_PREFIX), stock_b, archive, stock_a))
    bad("nonzero gap just before header", GAP_MSG,
        lambda: check_image(flipped(candidate, HEADER_OFFSET - 1), stock_b, archive, stock_a))
    bad("nonzero gap after archive", GAP_MSG,
        lambda: check_image(flipped(candidate, end), stock_b, archive, stock_a))
    bad("nonzero gap before footer", GAP_MSG,
        lambda: check_image(flipped(candidate, STOCK_SIZE - FOOTER_SIZE - 1),
                            stock_b, archive, stock_a))
    bad("short image", SIZE_MSG,
        lambda: check_image(candidate[:-PAGE], stock_b, archive, stock_a))
    bad("output inside repo", PATH_MSG,
        lambda: check_output_path(REPO / "vendor_boot_b.img", []))
    bad("git artifact path inside repo", GIT_MSG,
        lambda: check_git_absent(REPO / "out.img"))
    require(assemble(stock_b, archive, stock_a)[0] == candidate and
            reassemble(candidate, stock_b, archive) == candidate, IDEMPOTENT_MSG)
    return header, end


def main():
    args = sys.argv[1:]
    require(len(args) in (4, 5) and args[0] in ("--build", "--verify", "--self-test"),
            "usage: build-vendor-boot-b-userspace-payload.py "
            "(--build|--verify|--self-test) STOCK_B ARCHIVE CANDIDATE [STOCK_A]")
    mode, stock_b_path, archive_path, candidate_path = args[:4]
    stock_a_path = args[4] if len(args) == 5 else None
    inputs = [stock_b_path, archive_path] + ([stock_a_path] if stock_a_path else [])
    for item in inputs:
        p = pathlib.Path(item)
        require(p.is_file() and not p.is_symlink(), f"missing or symlinked input: {p.name}")
    stock_b = pathlib.Path(stock_b_path).read_bytes()
    archive = pathlib.Path(archive_path).read_bytes()
    stock_a = pathlib.Path(stock_a_path).read_bytes() if stock_a_path else None
    check_stock(stock_b, stock_a)
    check_archive(archive)
    if mode == "--build":
        out = check_output_path(candidate_path, inputs)
        check_git_absent(out)
        image, header, end = assemble(stock_b, archive, stock_a)
        check_image(image, stock_b, archive, stock_a)
        fd, tmp_name = tempfile.mkstemp(prefix=".vendor_boot_b.", suffix=".tmp",
                                        dir=str(out.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(image)
            os.replace(tmp_name, out)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        written = out.read_bytes()
        check_image(written, stock_b, archive, stock_a)
        check_git_absent(out)
        candidate = written
    else:
        cand = check_output_path(candidate_path, inputs)
        require(cand.is_file(), "missing candidate image")
        candidate = cand.read_bytes()
        if mode == "--self-test":
            header, end = self_test(candidate, stock_b, archive, stock_a)
        else:
            header, end = check_image(candidate, stock_b, archive, stock_a)
        check_git_absent(cand)
    print(f"vendor_boot_b payload image: {len(candidate)} bytes, SHA-256 {sha256(candidate)}")
    print(f"header: {PAGE} bytes at [{HEADER_OFFSET}, {ARCHIVE_OFFSET}), SHA-256 {sha256(header)}")
    print(f"archive: {len(archive)} bytes at [{ARCHIVE_OFFSET}, {end}), SHA-256 {sha256(archive)}")
    print(f"signed prefix: [0, {SIGNED_PREFIX}) unchanged (AVB0 at {VBMETA_OFFSET}); "
          f"terminal {FOOTER_SIZE}-byte AVBf footer unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
