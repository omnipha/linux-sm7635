#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("vendor_payload", HERE / "build-vendor-boot-b-userspace-payload.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)

SIZE = 104857600
STOCK_SHA = "6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b"
PREFIX = 15616192
VBMETA_OFFSET = 15613952
VBMETA_SIZE = 2240
FOOTER = 64
REFUSED = frozenset((STOCK_SHA, source.STOCK_SHA256,
                     "1bdb7c2252b3192127aed0a2f8953d928be0f36a00a259582e7a75a98a029f5f"))
STOCK_MSG = "stock recovery_b geometry, hash or empty payload window differs from the verified backup"
ARCHIVE_MSG = source.ARCHIVE_MSG
BOUND_MSG = source.BOUND_MSG
PREFIX_MSG = "recovery_b signed prefix was modified"
FOOTER_MSG = "recovery_b stock footer was modified"
HEADER_MSG = source.HEADER_MSG
GAP_MSG = source.GAP_MSG
SIZE_MSG = "recovery_b payload image size differs from the by-name backup"
IMAGE_MSG = "recovery_b payload does not reproduce from pinned stock and archive"
SHA_MSG = "payload repeats a stock or measured image SHA-256"
require = source.require
sha256 = source.sha256


def check_stock(stock):
    require(len(stock) == SIZE and sha256(stock) == STOCK_SHA and
            stock[:8] == b"ANDROID!" and
            struct.unpack_from("<I", stock, 8)[0] == 0 and
            struct.unpack_from("<I", stock, 12)[0] == 15609526 and
            struct.unpack_from("<I", stock, 20)[0] == 1584 and
            struct.unpack_from("<I", stock, 40)[0] == 4 and
            struct.unpack_from("<I", stock, 1580)[0] == 0 and
            stock[VBMETA_OFFSET:VBMETA_OFFSET + 4] == b"AVB0" and
            any(stock[VBMETA_OFFSET:PREFIX]) and
            stock[-FOOTER:-FOOTER + 4] == b"AVBf" and
            struct.unpack_from(">QQQ", stock, SIZE - FOOTER + 12) ==
            (VBMETA_OFFSET, VBMETA_OFFSET, VBMETA_SIZE) and
            not any(stock[PREFIX:-FOOTER]), STOCK_MSG)


def check_archive(archive):
    require(len(archive) == source.ARCHIVE_SIZE and
            sha256(archive) == source.ARCHIVE_SHA256, ARCHIVE_MSG)
    end = source.ARCHIVE_OFFSET + len(archive)
    require(source.HEADER_OFFSET == source.ARCHIVE_OFFSET - source.PAGE and
            source.HEADER_OFFSET % source.PAGE == 0 and
            PREFIX <= source.HEADER_OFFSET and end <= SIZE - FOOTER, BOUND_MSG)
    return end


def assemble(stock, archive):
    check_stock(stock)
    end = check_archive(archive)
    image = bytearray(stock)
    image[source.HEADER_OFFSET:source.ARCHIVE_OFFSET] = source.header_bytes(archive)
    image[source.ARCHIVE_OFFSET:end] = archive
    return bytes(image)


def check_image(image, stock, archive):
    check_stock(stock)
    end = check_archive(archive)
    require(len(image) == SIZE, SIZE_MSG)
    require(sha256(image) not in REFUSED, SHA_MSG)
    require(image[:PREFIX] == stock[:PREFIX], PREFIX_MSG)
    require(image[-FOOTER:] == stock[-FOOTER:], FOOTER_MSG)
    require(image[source.HEADER_OFFSET:source.ARCHIVE_OFFSET] ==
            source.header_bytes(archive), HEADER_MSG)
    require(image[source.ARCHIVE_OFFSET:end] == archive, ARCHIVE_MSG)
    require(not any(image[PREFIX:source.HEADER_OFFSET]) and
            not any(image[end:-FOOTER]), GAP_MSG)
    require(image == assemble(stock, archive), IMAGE_MSG)
    return end


def flipped(data, index):
    out = bytearray(data)
    out[index] ^= 1
    return bytes(out)


def self_test(image, stock, archive):
    end = check_image(image, stock, archive)
    source.check_git_absent()

    def bad(label, message, candidate, baseline=stock, payload=archive):
        try:
            check_image(candidate, baseline, payload)
        except ValueError as exc:
            require(str(exc) == message, f"{label}: unexpected failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture accepted")

    bad("stock image", SHA_MSG, stock)
    bad("short image", SIZE_MSG, image[:-1])
    bad("old carrier", SIZE_MSG, bytes(source.STOCK_SIZE))
    bad("stock corruption", STOCK_MSG, image, flipped(stock, 0))
    bad("stock AVB0 corruption", STOCK_MSG, image, flipped(stock, VBMETA_OFFSET))
    bad("stock footer corruption", STOCK_MSG, image, flipped(stock, SIZE - FOOTER))
    bad("dirty stock window", STOCK_MSG, image, flipped(stock, PREFIX))
    bad("archive input corruption", ARCHIVE_MSG, image, stock, flipped(archive, 0))
    bad("archive input truncation", ARCHIVE_MSG, image, stock, archive[:-1])
    bad("prefix corruption", PREFIX_MSG, flipped(image, VBMETA_OFFSET))
    bad("prefix end corruption", PREFIX_MSG, flipped(image, PREFIX - 1))
    bad("footer corruption", FOOTER_MSG, flipped(image, SIZE - FOOTER))
    bad("header corruption", HEADER_MSG, flipped(image, source.HEADER_OFFSET))
    bad("header padding", HEADER_MSG, flipped(image, source.ARCHIVE_OFFSET - 1))
    bad("archive first byte", ARCHIVE_MSG, flipped(image, source.ARCHIVE_OFFSET))
    bad("archive last byte", ARCHIVE_MSG, flipped(image, end - 1))
    bad("gap before header", GAP_MSG, flipped(image, PREFIX))
    bad("gap after archive", GAP_MSG, flipped(image, end))
    bad("gap before footer", GAP_MSG, flipped(image, SIZE - FOOTER - 1))
    try:
        source.check_output_path(HERE.parent / "recovery_b.img", [])
    except ValueError as exc:
        require(str(exc) == source.PATH_MSG, "repo output check changed")
    else:
        raise ValueError("repo output path accepted")


def main():
    args = sys.argv[1:]
    require(len(args) == 4 and args[0] in ("--build", "--verify", "--self-test"),
            "usage: build-recovery-b-userspace-payload.py --build|--verify|--self-test STOCK_B ARCHIVE CANDIDATE")
    mode, stock_path, archive_path, candidate_path = args
    for item in (stock_path, archive_path):
        path = pathlib.Path(item)
        require(path.is_file() and not path.is_symlink(), f"missing or symlinked input: {path.name}")
    stock, archive = pathlib.Path(stock_path).read_bytes(), pathlib.Path(archive_path).read_bytes()
    check_stock(stock)
    check_archive(archive)
    output = source.check_output_path(candidate_path, (stock_path, archive_path))
    source.check_git_absent(output)
    if mode == "--build":
        image = assemble(stock, archive)
        check_image(image, stock, archive)
        fd, tmp = tempfile.mkstemp(prefix=".recovery_b.", suffix=".tmp", dir=str(output.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(image)
            os.replace(tmp, output)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    require(output.is_file() and not output.is_symlink(), "missing candidate image")
    image = output.read_bytes()
    if mode == "--self-test":
        self_test(image, stock, archive)
    end = check_image(image, stock, archive)
    source.check_git_absent(output)
    print(f"recovery_b payload: {len(image)} bytes, SHA-256 {sha256(image)}")
    print(f"stock prefix [0, {PREFIX}) and terminal {FOOTER}-byte AVBf unchanged; "
          f"header [{source.HEADER_OFFSET}, {source.ARCHIVE_OFFSET}), archive end {end}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
