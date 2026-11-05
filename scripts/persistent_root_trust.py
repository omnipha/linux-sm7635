#!/usr/bin/env python3
import base64
import binascii
import hashlib
import hmac
import json
import os
import pathlib
import stat
import sys
from collections.abc import Mapping
from typing import Any, NoReturn

SCHEMA = "omnipha-sm7635-persistent-root-trust-anchors-v1"
SLOTS = ("release", "rollback")
SSH_TYPE = b"ssh-ed25519"
PUBLIC_BYTES = 32
ENCODED_BYTES = 68
MAX_LINE = len(SSH_TYPE) + 1 + ENCODED_BYTES + 1
MAX_CONFIG = 4096
OWNER_ANCHOR_COMMENTS = {
    "release": b"omnipha-sm7635-release-20261105",
    "rollback": b"omnipha-sm7635-rollback-20261105",
}
REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "configs" / "persistent-root-trust-anchors.json"
OWNER_ANCHOR_SHA256: dict[str, str | None] = {
    "release": "0becb7e18ea429eeb06bfe9fcdb84e7873f4cc9da18e1f625fbaaad92fdc6e55",
    "rollback": "9bae1576be7bdf20f14c75b735998e5a574736429186b7d7ec4f91a11e25cf9b",
}
BLOB_HEADER = (len(SSH_TYPE).to_bytes(4, "big") + SSH_TYPE +
               PUBLIC_BYTES.to_bytes(4, "big"))


class Reject(Exception):
    pass


def refuse(reason: str) -> NoReturn:
    raise Reject(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_public_line(line: bytes) -> bytes:
    if (not isinstance(line, bytes) or len(line) > MAX_LINE or
            not line.endswith(b"\n") or line.count(b"\n") != 1 or
            any(byte < 0x20 or byte > 0x7E for byte in line[:-1])):
        refuse("public key line is not one bounded ASCII record")
    prefix = SSH_TYPE + b" "
    if not line.startswith(prefix) or line.count(b" ") != 1:
        refuse("public key line is not exactly one ssh-ed25519 key")
    encoded = line[len(prefix):-1]
    if len(encoded) != ENCODED_BYTES:
        refuse("public key encoding length is not exact")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        refuse("public key encoding is malformed")
    if len(blob) != len(BLOB_HEADER) + PUBLIC_BYTES or not blob.startswith(BLOB_HEADER):
        refuse("public key blob is not one Ed25519 public key")
    if base64.b64encode(blob) != encoded:
        refuse("public key encoding is not canonical")
    return blob[len(BLOB_HEADER):]


def valid_pin(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64 and
            all(character in "0123456789abcdef" for character in value))


def validate_with_pins(lines: Mapping[str, bytes], pins: Mapping[str, object]) -> dict[str, bytes]:
    if tuple(lines) != SLOTS or tuple(pins) != SLOTS:
        refuse("release and rollback anchors are not both present")
    parsed = {slot: parse_public_line(lines[slot]) for slot in SLOTS}
    if parsed["release"] == parsed["rollback"]:
        refuse("release and rollback anchors are not distinct")
    if not all(valid_pin(pins[slot]) for slot in SLOTS):
        refuse("owner anchor authorization pins are absent or malformed")
    if pins["release"] == pins["rollback"]:
        refuse("owner anchor authorization pins are not distinct")
    for slot in SLOTS:
        if not hmac.compare_digest(digest(parsed[slot]).encode("ascii"),
                                   str(pins[slot]).encode("ascii")):
            refuse(f"{slot} anchor is not the owner-authorized value")
    return parsed


def read_fixed_config() -> bytes:
    try:
        fd = os.open(CONFIG_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC |
                     os.O_NONBLOCK)
    except OSError:
        refuse("trust anchor config cannot be opened safely")
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_size <= 0 or info.st_size > MAX_CONFIG):
            refuse("trust anchor config is not one bounded regular file")
        chunks = []
        remaining = info.st_size + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    if len(data) != info.st_size:
        refuse("trust anchor config changed while reading")
    return data


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            refuse("trust anchor config has a duplicate member")
        result[key] = value
    return result


def parse_config(data: bytes) -> dict[str, bytes]:
    if not isinstance(data, bytes) or len(data) == 0 or len(data) > MAX_CONFIG:
        refuse("trust anchor config is not bounded")
    def constant(_: str) -> NoReturn:
        refuse("trust anchor config is malformed")

    try:
        parsed = json.loads(data.decode("ascii"), object_pairs_hook=unique_object,
                            parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        refuse("trust anchor config is malformed")
    if (not isinstance(parsed, dict) or tuple(parsed) != ("schema", "keys") or
            parsed["schema"] != SCHEMA or not isinstance(parsed["keys"], dict) or
            tuple(parsed["keys"]) != SLOTS):
        refuse("trust anchor config schema is invalid")
    lines = {}
    for slot in SLOTS:
        value = parsed["keys"][slot]
        if value is None:
            refuse(f"{slot} owner anchor is absent")
        if not isinstance(value, str) or not value.isascii():
            refuse(f"{slot} owner anchor is malformed")
        encoded = value.encode("ascii")
        suffix = b" " + OWNER_ANCHOR_COMMENTS[slot]
        if not encoded.endswith(suffix) or encoded.count(b" ") != 2:
            refuse(f"{slot} owner anchor comment is not exact")
        lines[slot] = encoded[:-len(suffix)] + b"\n"
    return lines


def load_owner_anchors() -> dict[str, bytes]:
    return validate_with_pins(parse_config(read_fixed_config()), OWNER_ANCHOR_SHA256)


def check_owner_anchors() -> int:
    try:
        load_owner_anchors()
    except (Reject, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError,
            MemoryError):
        print("owner trust anchors: FAIL", file=sys.stderr)
        return 1
    print("owner trust anchors: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["--check-owner-anchors"]:
        print("usage: persistent_root_trust.py --check-owner-anchors", file=sys.stderr)
        return 2
    return check_owner_anchors()


if __name__ == "__main__":
    raise SystemExit(main())
