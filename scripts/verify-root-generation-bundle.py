#!/usr/bin/env python3
import base64
import binascii
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import runpy
import stat
import subprocess
import sys
import tempfile
from typing import Any, NoReturn

SCHEMA = "omnipha-sm7635-root-generation-v1"
RELEASE_DOMAIN = b"omnipha-sm7635-root-generation-v1/release\n"
ROLLBACK_DOMAIN = b"omnipha-sm7635-root-generation-v1/rollback\n"
RELEASE_PRINCIPAL = "fixture-release"
ROLLBACK_PRINCIPAL = "fixture-rollback"
RELEASE_NS = "omnipha-sm7635-root-release-v1@fixture.invalid"
ROLLBACK_NS = "omnipha-sm7635-root-rollback-v1@fixture.invalid"
MAGIC = b"ORGB"
HEADER = MAGIC + bytes((1, 0, 0, 0))
HEADER_LEN = 12
MANIFEST_MAX = 4096
PAYLOAD_MAX = 1048576
SIGNATURE_MAX = 2048
BUNDLE_MAX = 3 * 1048576 + 8192
SEQUENCE_MAX = 2**31 - 1
SIGNERS_MAX = 1024
CHAIN_MAX = 64
ED25519_PREFIX = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
KIND_MANIFEST = 1
KIND_RELEASE_SIG = 2
KIND_PAYLOADS = (3, 4, 5)
KIND_ROLLBACK_SIG = 6
ORDER_FORWARD = (KIND_MANIFEST, KIND_RELEASE_SIG, *KIND_PAYLOADS)
ORDER_ROLLBACK = (KIND_MANIFEST, KIND_RELEASE_SIG, KIND_ROLLBACK_SIG, *KIND_PAYLOADS)
PATHS = (
    "/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh",
    "/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh",
    "/etc/local.d/10-omnipha-self-stage.start",
)
BASELINE_DIGESTS = (
    "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14",
    "113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3",
    "3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67",
)
BASELINE_SIZES = (29356, 846492, 899)
BAD_RADIO = "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3"
OPERATIONS = ("baseline", "forward", "rollback")
MANIFEST_KEYS = ["schema", "sequence", "operation", "previous", "files", "restores"]
ENTRY_KEYS = ["path", "size", "sha256", "uid", "gid", "mode"]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
Payloads = tuple[bytes, bytes, bytes]


class Reject(Exception):
    pass


def refuse(reason: str) -> NoReturn:
    raise Reject(reason)


def require(condition: bool, reason: str) -> None:
    if not condition:
        refuse(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_id(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def canonical(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def parse_manifest(raw: bytes) -> dict[str, Any]:
    require(bool(raw) and len(raw) <= MANIFEST_MAX, "manifest size")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        require(len({key for key, _ in items}) == len(items), "duplicate key")
        return dict(items)

    def constant(_: str) -> NoReturn:
        refuse("number spelling")

    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError):
        refuse("manifest encoding or JSON")
    require(isinstance(obj, dict) and list(obj) == MANIFEST_KEYS, "manifest fields")
    require(obj["schema"] == SCHEMA, "schema")
    require(type(obj["sequence"]) is int and 0 <= obj["sequence"] <= SEQUENCE_MAX, "sequence type")
    require(obj["operation"] in OPERATIONS, "operation")
    require(all(value is None or is_id(value) for value in (obj["previous"], obj["restores"])), "manifest id")
    if obj["operation"] == "baseline":
        require(obj["sequence"] == 0 and obj["previous"] is None and obj["restores"] is None, "baseline shape")
    else:
        require(obj["sequence"] > 0 and obj["previous"] is not None and
                (obj["operation"] == "rollback") == (obj["restores"] is not None), "transition shape")
    files = obj["files"]
    require(isinstance(files, list) and len(files) == len(PATHS), "file count")
    for entry, path in zip(files, PATHS):
        require(isinstance(entry, dict) and list(entry) == ENTRY_KEYS, "file fields")
        require(entry["path"] == path, "file path or order")
        require(type(entry["size"]) is int and 0 < entry["size"] <= PAYLOAD_MAX, "file size")
        require(is_id(entry["sha256"]) and entry["sha256"] != BAD_RADIO, "file digest")
        require(type(entry["uid"]) is int and entry["uid"] == 0, "file uid")
        require(type(entry["gid"]) is int and entry["gid"] == 0, "file gid")
        require(entry["mode"] == "0700", "file mode")
    require(canonical(obj) == raw, "not canonical")
    return obj


def frame_member(kind: int, data: bytes) -> bytes:
    return bytes((kind,)) + len(data).to_bytes(4, "big") + data


def encode_bundle(manifest: bytes, release_sig: bytes, payloads: Payloads,
                  rollback_sig: bytes | None = None) -> bytes:
    require(0 < len(manifest) <= MANIFEST_MAX and 0 < len(release_sig) <= SIGNATURE_MAX, "bundle input")
    require(isinstance(payloads, tuple) and len(payloads) == len(PATHS) and
            all(isinstance(item, bytes) and 0 < len(item) <= PAYLOAD_MAX for item in payloads),
            "bundle input")
    members = [(KIND_MANIFEST, manifest), (KIND_RELEASE_SIG, release_sig)]
    if rollback_sig is not None:
        require(isinstance(rollback_sig, bytes) and 0 < len(rollback_sig) <= SIGNATURE_MAX, "bundle input")
        members.append((KIND_ROLLBACK_SIG, rollback_sig))
    members.extend(zip(KIND_PAYLOADS, payloads))
    encoded = HEADER + len(members).to_bytes(4, "big") + b"".join(frame_member(k, d) for k, d in members)
    require(len(encoded) <= BUNDLE_MAX, "bundle size")
    return encoded


def parse_bundle(blob: bytes) -> tuple[bytes, bytes, Payloads, bytes | None]:
    require(HEADER_LEN <= len(blob) <= BUNDLE_MAX, "bundle size")
    require(blob[:8] == HEADER, "bundle header")
    count = int.from_bytes(blob[8:12], "big")
    require(count in (len(ORDER_FORWARD), len(ORDER_ROLLBACK)), "bundle count")
    order = ORDER_ROLLBACK if count == len(ORDER_ROLLBACK) else ORDER_FORWARD
    offset = HEADER_LEN
    members: list[bytes] = []
    for expected_kind in order:
        require(offset + 5 <= len(blob), "truncated member")
        require(blob[offset] == expected_kind, "member order or kind")
        length = int.from_bytes(blob[offset + 1:offset + 5], "big")
        offset += 5
        if expected_kind == KIND_MANIFEST:
            limit = MANIFEST_MAX
        elif expected_kind in (KIND_RELEASE_SIG, KIND_ROLLBACK_SIG):
            limit = SIGNATURE_MAX
        else:
            limit = PAYLOAD_MAX
        require(0 < length <= limit and offset + length <= len(blob), "member bounds")
        members.append(blob[offset:offset + length])
        offset += length
    require(offset == len(blob), "trailing bytes")
    rollback_sig = members[2] if count == len(ORDER_ROLLBACK) else None
    payloads = members[-3:]
    return members[0], members[1], (payloads[0], payloads[1], payloads[2]), rollback_sig


def load_signers(signers: pathlib.Path, principal: str, namespace: str) -> tuple[bytes, bytes]:
    try:
        fd = os.open(signers, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= SIGNERS_MAX,
                    "signers file")
            raw = handle.read(SIGNERS_MAX + 1)
    except OSError:
        refuse("signers file")
    require(0 < len(raw) <= SIGNERS_MAX and raw.endswith(b"\n") and raw.count(b"\n") == 1, "signers file")
    try:
        fields = raw[:-1].decode("ascii").split(" ")
    except UnicodeDecodeError:
        refuse("signers file")
    require(len(fields) == 4 and fields[0] == principal and fields[1] == f'namespaces="{namespace}"' and
            fields[2] == "ssh-ed25519", "signers file")
    try:
        blob = base64.b64decode(fields[3], validate=True)
    except binascii.Error:
        refuse("signers file")
    require(len(blob) == 51 and blob.startswith(ED25519_PREFIX) and
            base64.b64encode(blob).decode("ascii") == fields[3], "signers file")
    return raw, blob


def write_private(path: pathlib.Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


SSHSIG_BEGIN = b"-----BEGIN SSH SIGNATURE-----\n"
SSHSIG_END = b"-----END SSH SIGNATURE-----\n"
SSHSIG_WRAP = 70
SSHSIG_ALPHABET = re.compile(rb"[A-Za-z0-9+/=]+\Z")
SSHSIG_HASHES = (b"sha256", b"sha512")


def sshsig_string(blob: bytes, offset: int) -> tuple[bytes, int]:
    require(offset + 4 <= len(blob), "signature structure")
    length = int.from_bytes(blob[offset:offset + 4], "big")
    offset += 4
    require(offset + length <= len(blob), "signature structure")
    return blob[offset:offset + length], offset + length


def canonical_signature(signature: bytes, namespace: str | None = None) -> bytes:
    require(isinstance(signature, bytes) and 0 < len(signature) <= SIGNATURE_MAX, "signature bounds")
    require(signature.startswith(SSHSIG_BEGIN) and signature.endswith(SSHSIG_END), "signature encoding")
    require(signature.count(SSHSIG_BEGIN) == 1 and signature.count(SSHSIG_END) == 1,
            "signature encoding")
    body = signature[len(SSHSIG_BEGIN):-len(SSHSIG_END)]
    require(body.endswith(b"\n") and not body.endswith(b"\n\n"), "signature encoding")
    lines = body[:-1].split(b"\n")
    require(bool(lines) and all(0 < len(line) <= SSHSIG_WRAP for line in lines), "signature encoding")
    require(all(len(line) == SSHSIG_WRAP for line in lines[:-1]), "signature encoding")
    require(all(SSHSIG_ALPHABET.fullmatch(line) is not None for line in lines), "signature encoding")
    data = b"".join(lines)
    try:
        blob = base64.b64decode(data, validate=True)
    except binascii.Error:
        refuse("signature encoding")
    require(base64.b64encode(blob) == data, "signature encoding")
    require(blob.startswith(b"SSHSIG") and int.from_bytes(blob[6:10], "big") == 1, "signature structure")
    offset = 10
    public, offset = sshsig_string(blob, offset)
    found, offset = sshsig_string(blob, offset)
    reserved, offset = sshsig_string(blob, offset)
    algorithm, offset = sshsig_string(blob, offset)
    inner, offset = sshsig_string(blob, offset)
    require(offset == len(blob) and public.startswith(ED25519_PREFIX) and len(public) == 51 and
            not reserved and algorithm in SSHSIG_HASHES, "signature structure")
    require(namespace is None or found == namespace.encode("ascii"), "signature namespace")
    kind, inner_offset = sshsig_string(inner, 0)
    raw, inner_offset = sshsig_string(inner, inner_offset)
    require(kind == b"ssh-ed25519" and len(raw) == 64 and inner_offset == len(inner), "signature structure")
    return signature


def ssh_verify(signers: pathlib.Path, principal: str, namespace: str, message: bytes,
               signature: bytes, key: bytes | None = None) -> bool:
    raw, blob = load_signers(signers, principal, namespace)
    require(key is None or blob == key, "signers changed")
    signature = canonical_signature(signature, namespace)
    with tempfile.TemporaryDirectory(prefix="root-generation-verify-") as scratch:
        pinned = pathlib.Path(scratch) / "signers"
        target = pathlib.Path(scratch) / "signature"
        write_private(pinned, raw)
        write_private(target, signature)
        try:
            done = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(pinned), "-I", principal,
                                   "-n", namespace, "-s", str(target)], input=message,
                                  capture_output=True, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError):
            refuse("ssh-keygen failed")
    return done.returncode == 0


def rollback_message(current: str, target: str, restores: str, sequence: int) -> bytes:
    require(all(is_id(value) for value in (current, target, restores)) and type(sequence) is int and
            0 < sequence <= SEQUENCE_MAX, "rollback statement")
    return ROLLBACK_DOMAIN + (
        f"current={current}\ntarget={target}\nrestores={restores}\nsequence={sequence}\n"
    ).encode("ascii")


@dataclasses.dataclass(frozen=True)
class VerifiedBundle:
    manifest: bytes
    parsed: dict[str, Any]
    ident: str
    payloads: Payloads
    rollback: bool


def verify_chain(blobs: list[bytes], release_signers: pathlib.Path, rollback_signers: pathlib.Path,
                  baseline_id: str) -> list[VerifiedBundle]:
    require(0 < len(blobs) <= CHAIN_MAX and is_id(baseline_id), "chain input")
    require(release_signers.resolve() != rollback_signers.resolve(), "keys not distinct")
    rel_key = load_signers(release_signers, RELEASE_PRINCIPAL, RELEASE_NS)[1]
    rb_key = load_signers(rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS)[1]
    require(rel_key != rb_key, "keys not distinct")
    chain: list[VerifiedBundle] = []
    for position, blob in enumerate(blobs):
        require(isinstance(blob, bytes) and 0 < len(blob) <= BUNDLE_MAX, "bundle size")
        manifest, release_sig, payloads, rollback_sig = parse_bundle(blob)
        parsed = parse_manifest(manifest)
        ident = digest(manifest)
        require(ssh_verify(release_signers, RELEASE_PRINCIPAL, RELEASE_NS, RELEASE_DOMAIN + manifest,
                           release_sig, rel_key), "release signature")
        for entry, data in zip(parsed["files"], payloads):
            require(len(data) == entry["size"] and digest(data) == entry["sha256"], "payload mismatch")
        if position == 0:
            require(parsed["operation"] == "baseline" and rollback_sig is None, "baseline context")
            require(ident == baseline_id, "baseline pin")
            require(tuple(entry["sha256"] for entry in parsed["files"]) == BASELINE_DIGESTS and
                    tuple(entry["size"] for entry in parsed["files"]) == BASELINE_SIZES, "baseline bytes")
            chain.append(VerifiedBundle(manifest, parsed, ident, payloads, False))
            continue
        previous = chain[-1]
        require(parsed["operation"] != "baseline", "baseline after initialization")
        require(all(item.ident != ident for item in chain), "generation replay")
        require(parsed["previous"] == previous.ident, "predecessor")
        require(parsed["sequence"] == previous.parsed["sequence"] + 1, "sequence")
        if parsed["operation"] == "forward":
            require(rollback_sig is None, "forward authorization")
            require(all(item.payloads != payloads for item in chain), "forward reissues earlier bytes")
        else:
            require(rollback_sig is not None, "rollback evidence")
            assert rollback_sig is not None
            sources = [item for item in chain if item.ident == parsed["restores"]]
            require(len(sources) == 1, "restored id")
            source = sources[0]
            require(source.parsed["sequence"] < previous.parsed["sequence"], "source not older")
            require(source.payloads == payloads and source.parsed["files"] == parsed["files"],
                    "restored bytes")
            statement = rollback_message(previous.ident, ident, parsed["restores"], parsed["sequence"])
            require(ssh_verify(rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS, statement, rollback_sig,
                               rb_key), "rollback signature")
        chain.append(VerifiedBundle(manifest, parsed, ident, payloads, parsed["operation"] == "rollback"))
    return chain


def main(argv: list[str]) -> int:
    require(argv == ["--self-test"], "production use refused")
    test = pathlib.Path(__file__).with_name("test-root-generation-bundle.py")
    require(test.is_file(), "self-test missing")
    runpy.run_path(str(test), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Reject as exc:
        print(f"refused: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
