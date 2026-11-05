#!/usr/bin/env python3
import base64
import dataclasses
import functools
import hashlib
import importlib.util
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent

SCHEMA = "omnipha-sm7635-root-generation-v1"
RELEASE_NS = "omnipha-sm7635-root-release-v1@fixture.invalid"
ROLLBACK_NS = "omnipha-sm7635-root-rollback-v1@fixture.invalid"
RELEASE_PRINCIPAL = "fixture-release"
ROLLBACK_PRINCIPAL = "fixture-rollback"
RELEASE_DOMAIN = b"omnipha-sm7635-root-generation-v1/release\n"
ROLLBACK_DOMAIN = b"omnipha-sm7635-root-generation-v1/rollback\n"
MANIFEST_MAX = 4096
PAYLOAD_MAX = 1048576
SEQUENCE_MAX = 2**31 - 1
POST_BASELINE_SIZE = 846492
OPERATIONS = ("baseline", "forward", "rollback")
MANIFEST_KEYS = ["schema", "sequence", "operation", "previous", "files", "restores"]
ENTRY_KEYS = ["path", "size", "sha256", "uid", "gid", "mode"]
HEX64 = re.compile(r"[0-9a-f]{64}")

PINNED = (
    ("pmos-radio-bringup-fresh-boot.sh",
     "/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh", 29356,
     "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14"),
    ("pmos-self-post-fresh-boot.sh",
     "/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh", 846492,
     "113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3"),
    ("10-omnipha-self-stage.start",
     "/etc/local.d/10-omnipha-self-stage.start", 899,
     "3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67"),
)
PATHS = tuple(item[1] for item in PINNED)
ALTERED_RADIO = "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3"

counter = itertools.count()


class Reject(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Keys:
    work: pathlib.Path
    release_key: pathlib.Path
    rollback_key: pathlib.Path
    release_signers: pathlib.Path
    rollback_signers: pathlib.Path


@dataclasses.dataclass(frozen=True)
class Generation:
    manifest: bytes
    release_sig: bytes
    rollback_sig: bytes | None = None

    @property
    def ident(self) -> str:
        return hashlib.sha256(self.manifest).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_builder() -> Any:
    spec = importlib.util.spec_from_file_location(
        "persistent_builder", HERE / "build-init-boot-persistent-root.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.cache
def load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location(
        "verify_root_generation_bundle", HERE / "verify-root-generation-bundle.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def derive_baseline() -> dict[str, bytes]:
    builder = load_builder()
    assert builder.FRESH_RADIO == PINNED[0][0]
    assert builder.FRESH_POST == PINNED[1][0]
    assert builder.GATED_HOOK == PINNED[2][0]
    assert builder.FRESH_RADIO_SHA == PINNED[0][3]
    assert builder.GATED_POST_SHA == PINNED[1][3]
    assert builder.GATED_HOOK_SHA == PINNED[2][3]
    found = builder.runtime_scripts()
    payloads = {}
    for name, path, size, digest in PINNED:
        data = found[name]
        assert isinstance(data, bytes)
        assert len(data) == size, (name, len(data))
        assert sha256(data) == digest, name
        payloads[path] = data
    assert sha256(payloads[PATHS[0]]) != ALTERED_RADIO
    assert len({sha256(data) for data in payloads.values()}) == 3
    return payloads


def synthetic_payload(label: str, size: int) -> bytes:
    out = bytearray(b"#!/bin/sh\n")
    block = 0
    while len(out) < size:
        out += hashlib.sha256(f"synthetic:{label}:{block}".encode()).hexdigest().encode() + b"\n"
        block += 1
    return bytes(out[:size])


def candidate_payloads(label: str, post_size: int) -> dict[str, bytes]:
    assert POST_BASELINE_SIZE <= post_size
    return {
        PATHS[0]: synthetic_payload(label + "-radio", 30001),
        PATHS[1]: synthetic_payload(label + "-post", post_size),
        PATHS[2]: synthetic_payload(label + "-hook", 1024),
    }


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def files_object(payloads: dict[str, bytes]) -> list[dict[str, Any]]:
    return [{"path": path, "size": len(payloads[path]), "sha256": sha256(payloads[path]),
             "uid": 0, "gid": 0, "mode": "0700"} for path in PATHS]


def manifest_object(sequence: int, operation: str, previous: str | None, restores: str | None,
                    payloads: dict[str, bytes]) -> dict[str, Any]:
    return {"schema": SCHEMA, "sequence": sequence, "operation": operation, "previous": previous,
            "files": files_object(payloads), "restores": restores}


def hex_or_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and HEX64.fullmatch(value) is not None)


def parse_manifest(data: bytes) -> dict[str, Any]:
    if len(data) > MANIFEST_MAX:
        raise Reject("manifest size")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise Reject("manifest encoding") from None

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in items}) != len(items):
            raise Reject("manifest duplicate key")
        return dict(items)

    def constant(_name: str) -> Any:
        raise Reject("manifest number spelling")

    try:
        obj = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError:
        raise Reject("manifest json") from None
    if not isinstance(obj, dict) or list(obj) != MANIFEST_KEYS:
        raise Reject("manifest fields")
    if obj["schema"] != SCHEMA:
        raise Reject("manifest schema")
    if type(obj["sequence"]) is not int or not 0 <= obj["sequence"] <= SEQUENCE_MAX:
        raise Reject("manifest sequence type")
    if obj["operation"] not in OPERATIONS:
        raise Reject("manifest operation")
    if not hex_or_null(obj["previous"]) or not hex_or_null(obj["restores"]):
        raise Reject("manifest id")
    files = obj["files"]
    if not isinstance(files, list) or len(files) != len(PATHS):
        raise Reject("manifest files")
    for entry, path in zip(files, PATHS):
        if not isinstance(entry, dict) or list(entry) != ENTRY_KEYS:
            raise Reject("manifest entry fields")
        if entry["path"] != path:
            raise Reject("manifest entry path")
        if type(entry["size"]) is not int or not 0 < entry["size"] <= PAYLOAD_MAX:
            raise Reject("manifest entry size")
        if not isinstance(entry["sha256"], str) or HEX64.fullmatch(entry["sha256"]) is None:
            raise Reject("manifest entry digest")
        if entry["sha256"] == ALTERED_RADIO:
            raise Reject("manifest denylisted digest")
        if type(entry["uid"]) is not int or entry["uid"] != 0:
            raise Reject("manifest entry owner")
        if type(entry["gid"]) is not int or entry["gid"] != 0:
            raise Reject("manifest entry group")
        if entry["mode"] != "0700":
            raise Reject("manifest entry mode")
    operation = obj["operation"]
    if operation == "baseline":
        if obj["sequence"] != 0 or obj["previous"] is not None or obj["restores"] is not None:
            raise Reject("manifest baseline shape")
    else:
        if obj["sequence"] < 1 or obj["previous"] is None:
            raise Reject("manifest transition shape")
        if (operation == "rollback") != (obj["restores"] is not None):
            raise Reject("manifest restores shape")
    if canonical(obj) != data:
        raise Reject("manifest not canonical")
    return obj


def run(args: list[str], data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, input=data, capture_output=True, check=False)


def make_key(work: pathlib.Path, name: str, principal: str, namespace: str) -> tuple[pathlib.Path, pathlib.Path]:
    key = work / name
    done = run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(key)])
    assert done.returncode == 0
    assert key.stat().st_mode & 0o077 == 0
    fields = pathlib.Path(str(key) + ".pub").read_text().split()
    signers = work / (name + ".signers")
    signers.write_text(f'{principal} namespaces="{namespace}" {fields[0]} {fields[1]}\n')
    return key, signers


def make_keys(work: pathlib.Path) -> Keys:
    release_key, release_signers = make_key(work, "release", RELEASE_PRINCIPAL, RELEASE_NS)
    rollback_key, rollback_signers = make_key(work, "rollback", ROLLBACK_PRINCIPAL, ROLLBACK_NS)
    assert release_key.read_bytes() != rollback_key.read_bytes()
    assert release_signers.read_text().split()[-1] != rollback_signers.read_text().split()[-1]
    assert RELEASE_NS != ROLLBACK_NS and RELEASE_DOMAIN != ROLLBACK_DOMAIN
    return Keys(work, release_key, rollback_key, release_signers, rollback_signers)


def ssh_sign(keys: Keys, key: pathlib.Path, namespace: str, message: bytes) -> bytes:
    target = keys.work / f"message{next(counter)}"
    target.write_bytes(message)
    done = run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", namespace, str(target)])
    assert done.returncode == 0
    return pathlib.Path(str(target) + ".sig").read_bytes()


def pinned_verify(reason: str, signers: pathlib.Path, principal: str, namespace: str,
                  message: bytes, signature: bytes, key: bytes) -> None:
    verifier = load_verifier()
    try:
        accepted = verifier.ssh_verify(signers, principal, namespace, message, signature, key)
    except verifier.Reject as exc:
        raise Reject(f"{reason}: {exc}") from None
    if not accepted:
        raise Reject(reason)


def pin_signers(keys: Keys) -> tuple[bytes, bytes]:
    verifier = load_verifier()
    if (RELEASE_PRINCIPAL, RELEASE_NS, ROLLBACK_PRINCIPAL, ROLLBACK_NS) != (
        verifier.RELEASE_PRINCIPAL, verifier.RELEASE_NS, verifier.ROLLBACK_PRINCIPAL, verifier.ROLLBACK_NS
    ):
        raise Reject("signer policy mismatch")
    try:
        if keys.release_signers.resolve() == keys.rollback_signers.resolve():
            raise Reject("signer policy: keys not distinct")
        release_key = verifier.load_signers(keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS)[1]
        rollback_key = verifier.load_signers(keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS)[1]
    except verifier.Reject as exc:
        raise Reject(f"signer policy: {exc}") from None
    if release_key == rollback_key:
        raise Reject("signer policy: keys not distinct")
    return release_key, rollback_key


def release_message(manifest: bytes) -> bytes:
    return RELEASE_DOMAIN + manifest


def rollback_message(current: str, target: str, restores: str, sequence: int) -> bytes:
    if type(sequence) is not int or not 0 < sequence <= SEQUENCE_MAX:
        raise Reject("rollback statement")
    return ROLLBACK_DOMAIN + (f"current={current}\ntarget={target}\nrestores={restores}\n"
                              f"sequence={sequence}\n").encode("ascii")


def make_generation(keys: Keys, sequence: int, operation: str, previous: str | None,
                    restores: str | None, payloads: dict[str, bytes]) -> Generation:
    manifest = canonical(manifest_object(sequence, operation, previous, restores, payloads))
    release = ssh_sign(keys, keys.release_key, RELEASE_NS, release_message(manifest))
    rollback = None
    if operation == "rollback":
        assert previous is not None and restores is not None
        statement = rollback_message(previous, sha256(manifest), restores, sequence)
        rollback = ssh_sign(keys, keys.rollback_key, ROLLBACK_NS, statement)
    return Generation(manifest, release, rollback)


def verify_release(keys: Keys, release_key: bytes, gen: Generation, reason: str) -> dict[str, Any]:
    parsed = parse_manifest(gen.manifest)
    pinned_verify(reason, keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS,
                  release_message(gen.manifest), gen.release_sig, release_key)
    return parsed


def verify_generation(keys: Keys, gen: Generation, payloads: dict[str, bytes],
                      active: Generation | None, history: dict[str, Generation]) -> dict[str, Any]:
    release_key, rollback_key = pin_signers(keys)
    parsed = verify_release(keys, release_key, gen, "release signature")
    operation = parsed["operation"]
    if operation == "baseline":
        if active is not None:
            raise Reject("baseline after initialization")
        if gen.rollback_sig is not None:
            raise Reject("unexpected rollback signature")
        expected = [{"path": path, "size": size, "sha256": digest, "uid": 0, "gid": 0,
                     "mode": "0700"} for _name, path, size, digest in PINNED]
        if parsed["files"] != expected:
            raise Reject("baseline pin")
    else:
        if active is None:
            raise Reject("transition without active generation")
        active_parsed = verify_release(keys, release_key, active, "active release signature")
        if parsed["previous"] != active.ident:
            raise Reject("predecessor")
        if parsed["sequence"] != active_parsed["sequence"] + 1:
            raise Reject("sequence")
        if operation == "forward":
            if gen.rollback_sig is not None:
                raise Reject("unexpected rollback signature")
        else:
            restores = parsed["restores"]
            if restores == active.ident:
                raise Reject("restores active generation")
            source = history.get(restores)
            if source is None or source.ident != restores:
                raise Reject("restored generation unknown")
            source_parsed = verify_release(keys, release_key, source, "restored release signature")
            if source_parsed["sequence"] >= active_parsed["sequence"]:
                raise Reject("restored generation not older")
            if parsed["files"] != source_parsed["files"]:
                raise Reject("restored content")
            if gen.rollback_sig is None:
                raise Reject("rollback signature missing")
            statement = rollback_message(active.ident, gen.ident, restores, parsed["sequence"])
            pinned_verify("rollback signature", keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS,
                          statement, gen.rollback_sig, rollback_key)
    if set(payloads) != set(PATHS):
        raise Reject("payload set")
    for entry in parsed["files"]:
        data = payloads[entry["path"]]
        if len(data) > PAYLOAD_MAX:
            raise Reject("payload bound")
        if len(data) != entry["size"]:
            raise Reject("payload size")
        if sha256(data) != entry["sha256"]:
            raise Reject("payload digest")
    return parsed


def expect_reject(label: str, reason: str, call: Callable[[], Any]) -> None:
    try:
        call()
    except Reject as exc:
        assert reason in str(exc), (label, str(exc))
    else:
        raise AssertionError(f"accepted: {label}")
    print(f"rejected: {label}")


def flip(data: bytes, index: int) -> bytes:
    out = bytearray(data)
    out[index] ^= 1
    return bytes(out)


def ssh_keygen_verify(keys: Keys, signers: pathlib.Path, principal: str, namespace: str,
                      message: bytes, signature: bytes) -> bool:
    sig = keys.work / f"signature{next(counter)}"
    sig.write_bytes(signature)
    done = run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", principal,
                "-n", namespace, "-s", str(sig)], message)
    return done.returncode == 0


def pinned_load(signers: pathlib.Path, principal: str, namespace: str) -> bytes:
    verifier = load_verifier()
    try:
        return bytes(verifier.load_signers(signers, principal, namespace)[1])
    except verifier.Reject as exc:
        raise Reject(str(exc)) from None


def pinned_signature(signature: bytes, namespace: str | None = None) -> bytes:
    verifier = load_verifier()
    try:
        return bytes(verifier.canonical_signature(signature, namespace))
    except verifier.Reject as exc:
        raise Reject(str(exc)) from None


def role_line(principal: str, namespace: str, blob: str) -> str:
    return f'{principal} namespaces="{namespace}" ssh-ed25519 {blob}\n'


def rewrap(signature: bytes, width: int) -> bytes:
    body = signature.split(b"\n")[1:-2]
    data = b"".join(body)
    lines = [data[i:i + width] for i in range(0, len(data), width)]
    return b"-----BEGIN SSH SIGNATURE-----\n" + b"\n".join(lines) + b"\n-----END SSH SIGNATURE-----\n"


def check_signer_policy(keys: Keys, verify: Callable[[Keys], Any],
                        verify_baseline: Callable[[Keys], Any], verify_forward: Callable[[Keys], Any]) -> None:
    good = keys.release_signers.read_text()
    rollback_good = keys.rollback_signers.read_text()
    release_blob = good.split()[-1]
    rollback_blob = rollback_good.split()[-1]
    assert release_blob != rollback_blob
    assert verify(keys)["sequence"] == 2
    roles = "signer policy: signers file"
    for label, use, reason in (
        ("both signer sets swapped",
         dataclasses.replace(keys, release_signers=keys.rollback_signers,
                             rollback_signers=keys.release_signers),
         "signer policy: signers file"),
        ("rollback signer set is release signer set",
         dataclasses.replace(keys, rollback_signers=keys.release_signers),
         "signer policy: keys not distinct"),
        ("release signer set is rollback signer set",
         dataclasses.replace(keys, release_signers=keys.rollback_signers),
         "signer policy: keys not distinct"),
    ):
        expect_reject(label, reason, functools.partial(verify, use))
    expect_reject("signer files sharing one path", "signer policy: keys not distinct", functools.partial(
        verify, dataclasses.replace(keys, rollback_signers=keys.release_signers,
                                    release_signers=keys.release_signers)))

    same_rollback = keys.work / "rollback-with-release-key.signers"
    same_rollback.write_text(role_line(ROLLBACK_PRINCIPAL, ROLLBACK_NS, release_blob))
    for label, check in (("baseline", verify_baseline), ("forward", verify_forward), ("rollback", verify)):
        expect_reject(label + " with identical underlying role keys", "signer policy: keys not distinct",
                      functools.partial(check, dataclasses.replace(keys, rollback_signers=same_rollback)))
    same_release = keys.work / "release-with-rollback-key.signers"
    same_release.write_text(role_line(RELEASE_PRINCIPAL, RELEASE_NS, rollback_blob))
    expect_reject("release role holds the rollback underlying key", "signer policy: keys not distinct",
                  functools.partial(verify, dataclasses.replace(keys, release_signers=same_release)))

    malformed = (
        ("two key lines", good + good),
        ("option name", good.replace("namespaces", "namespace", 1)),
        ("key type", good.replace("ssh-ed25519", "ssh-rsa", 1)),
        ("extra option", good.replace(" ssh-ed25519", ",cert-authority ssh-ed25519", 1)),
        ("no trailing newline", good.rstrip("\n")),
        ("trailing field", good.rstrip("\n") + " note\n"),
        ("wrong principal", good.replace(RELEASE_PRINCIPAL, "fixture-other", 1)),
        ("wrong namespace", good.replace(RELEASE_NS, ROLLBACK_NS, 1)),
        ("short key blob", good.replace(release_blob, base64.b64encode(b"short").decode(), 1)),
        ("non-base64 key blob", good.replace(release_blob, "!" * len(release_blob), 1)),
        ("empty file", ""),
        ("oversized file", good + "#" * 1024 + "\n"),
    )
    for label, text in malformed:
        target = keys.work / f"malformed{next(counter)}.signers"
        target.write_bytes(text.encode())
        expect_reject("malformed signers: " + label, "signers file", functools.partial(
            pinned_load, target, RELEASE_PRINCIPAL, RELEASE_NS))
        expect_reject("generation under malformed signers: " + label, roles, functools.partial(
            verify, dataclasses.replace(keys, release_signers=target)))

    malformed_rollback = keys.work / "malformed-rollback.signers"
    malformed_rollback.write_text(rollback_good.replace(ROLLBACK_NS, RELEASE_NS, 1))
    for label, check in (("baseline", verify_baseline), ("forward", verify_forward), ("rollback", verify)):
        expect_reject(label + " with wrong rollback signer namespace", roles,
                      functools.partial(check, dataclasses.replace(keys, rollback_signers=malformed_rollback)))

    link = keys.work / "release-link.signers"
    link.symlink_to(keys.release_signers.name)
    expect_reject("symlinked signers", "signers file", functools.partial(
        pinned_load, link, RELEASE_PRINCIPAL, RELEASE_NS))
    expect_reject("generation under symlinked release signers", roles,
                  functools.partial(verify, dataclasses.replace(keys, release_signers=link)))
    rollback_link = keys.work / "rollback-link.signers"
    rollback_link.symlink_to(keys.rollback_signers.name)
    expect_reject("generation under symlinked rollback signers", roles,
                  functools.partial(verify, dataclasses.replace(keys, rollback_signers=rollback_link)))

    hard = keys.work / "release-hard.signers"
    os.link(keys.release_signers, hard)
    expect_reject("hardlinked signers", "signers file", functools.partial(
        pinned_load, hard, RELEASE_PRINCIPAL, RELEASE_NS))
    expect_reject("generation under hardlinked release signers", roles,
                  functools.partial(verify, dataclasses.replace(keys, release_signers=hard)))
    expect_reject("generation under signers with a second hardlink", roles, functools.partial(verify, keys))
    hard.unlink()
    rollback_hard = keys.work / "rollback-hard.signers"
    os.link(keys.rollback_signers, rollback_hard)
    expect_reject("generation under hardlinked rollback signers", roles,
                  functools.partial(verify, dataclasses.replace(keys, rollback_signers=rollback_hard)))
    expect_reject("generation under rollback signers with a second hardlink", roles, functools.partial(verify, keys))
    rollback_hard.unlink()

    folder = keys.work / "release-dir.signers"
    folder.mkdir()
    expect_reject("signers path is a directory", "signers file", functools.partial(
        pinned_load, folder, RELEASE_PRINCIPAL, RELEASE_NS))
    expect_reject("generation under missing release signers", roles, functools.partial(
        verify, dataclasses.replace(keys, release_signers=keys.work / "absent.signers")))
    assert verify(keys)["sequence"] == 2
    verifier = load_verifier()
    original_verify = verifier.ssh_verify
    for principal, signers, replacement in (
        (RELEASE_PRINCIPAL, keys.release_signers, role_line(RELEASE_PRINCIPAL, RELEASE_NS, rollback_blob)),
        (ROLLBACK_PRINCIPAL, keys.rollback_signers, role_line(ROLLBACK_PRINCIPAL, ROLLBACK_NS, release_blob)),
    ):
        original = signers.read_bytes()

        def replace_before_verify(path: pathlib.Path, role: str, namespace: str, message: bytes,
                                  signature: bytes, key: bytes | None = None, *, target: str = principal,
                                  signer_path: pathlib.Path = signers, new_line: str = replacement) -> bool:
            if role == target:
                signer_path.write_text(new_line)
            return bool(original_verify(path, role, namespace, message, signature, key))

        try:
            with mock.patch.object(verifier, "ssh_verify", side_effect=replace_before_verify):
                expect_reject("generation signer changes after pin: " + principal, "signers changed",
                              functools.partial(verify, keys))
        finally:
            signers.write_bytes(original)
    assert verify(keys)["sequence"] == 2
    print("ok: signer policy requires exact role, namespace, single-link regular files and distinct keys")



def check_signatures(keys: Keys, rolled: bytes, statement: bytes, release_sig: bytes,
                     release_text: bytes, verify: Callable[[bytes], Any]) -> None:
    assert pinned_signature(rolled, ROLLBACK_NS) == rolled
    assert pinned_signature(release_sig, RELEASE_NS) == release_sig
    crlf = rolled.replace(b"\n", b"\r\n")
    assert ssh_keygen_verify(keys, keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS, statement, crlf)
    wrapped = rewrap(rolled, 64)
    assert wrapped != rolled
    assert ssh_keygen_verify(keys, keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS, statement, wrapped)
    for label, signature in (("crlf armor", crlf), ("rewrapped at 64 columns", wrapped),
                             ("trailing newline", rolled + b"\n"), ("trailing junk", rolled + b"junk\n"),
                             ("leading junk", b"junk\n" + rolled), ("duplicated armor", rolled + rolled)):
        expect_reject("canonical signature: " + label, "signature encoding", functools.partial(
            pinned_signature, signature))
        expect_reject("generation with signature: " + label, "signature encoding",
                      functools.partial(verify, signature))
    expect_reject("canonical signature: namespace mismatch", "signature namespace", functools.partial(
        pinned_signature, rolled, RELEASE_NS))
    expect_reject("canonical signature: truncated structure", "signature", functools.partial(
        pinned_signature, rolled[:60] + b"\n-----END SSH SIGNATURE-----\n"))
    expect_reject("pinned key differs from signers file", "signers changed", functools.partial(
        pinned_verify, "rollback signature", keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS,
        statement, rolled, pinned_load(keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS)))
    assert not ssh_keygen_verify(keys, keys.release_signers, RELEASE_PRINCIPAL, ROLLBACK_NS,
                                 release_text, release_sig)
    assert not ssh_keygen_verify(keys, keys.release_signers, ROLLBACK_PRINCIPAL, RELEASE_NS,
                                 release_text, release_sig)
    print("ok: signatures must be canonical armor in the role namespace under the pinned key")


def check_tools() -> None:
    assert shutil.which("ssh-keygen") is not None
    version = run(["ssh", "-V"])
    print("ssh:", (version.stdout + version.stderr).decode().strip().splitlines()[0])
    compiler = shutil.which("aarch64-linux-gnu-gcc")
    assert compiler is not None
    first = run([compiler, "--version"]).stdout.decode().splitlines()[0]
    print("aarch64 compiler:", first)


def check_parser(baseline: dict[str, bytes]) -> None:
    good = canonical(manifest_object(0, "baseline", None, None, baseline))
    assert len(good) < MANIFEST_MAX
    parsed = parse_manifest(good)
    assert [entry["path"] for entry in parsed["files"]] == list(PATHS)
    assert all(path.startswith("/") for path in PATHS)
    assert [entry["size"] for entry in parsed["files"]] == [29356, 846492, 899]
    assert parsed["sequence"] == 0 and parsed["previous"] is None and parsed["restores"] is None
    text = good.decode()
    pretty = json.dumps(json.loads(text), indent=1).encode()
    object_ = manifest_object(0, "baseline", None, None, baseline)
    swapped = dict(object_)
    swapped["files"] = list(reversed(object_["files"]))
    relative = json.loads(text)
    relative["files"][0]["path"] = relative["files"][0]["path"].lstrip("/")
    cases: list[tuple[str, str, bytes]] = [
        ("whitespace", "not canonical", pretty),
        ("trailing newline", "not canonical", good + b"\n"),
        ("duplicate key", "duplicate key", text.replace('"sequence":0', '"sequence":0,"sequence":0').encode()),
        ("unknown field", "fields", canonical({**object_, "extra": 1})),
        ("reordered fields", "fields", canonical({key: object_[key] for key in reversed(MANIFEST_KEYS)})),
        ("alternate number", "sequence type", text.replace('"sequence":0', '"sequence":0.0').encode()),
        ("escaped text", "not canonical", text.replace("baseline", "\\u0062aseline").encode()),
        ("non-ascii", "encoding", good.replace(b"omnipha", "omnipha\u00e9".encode())),
        ("wrong schema", "schema", text.replace("generation-v1", "generation-v2").encode()),
        ("relative path", "entry path", canonical(relative)),
        ("reordered files", "entry path", canonical(swapped)),
        ("wrong mode", "entry mode", text.replace('"0700"', '"0755"', 1).encode()),
        ("wrong owner", "entry owner", text.replace('"uid":0', '"uid":1', 1).encode()),
        ("wrong group", "entry group", text.replace('"gid":0', '"gid":1', 1).encode()),
        ("uppercase digest", "entry digest", text.replace(PINNED[0][3], PINNED[0][3].upper()).encode()),
        *[(f"denylisted digest at {item[1]}", "denylisted digest",
           text.replace(item[3], ALTERED_RADIO, 1).encode()) for item in PINNED],
        ("zero size", "entry size", text.replace('"size":29356', '"size":0').encode()),
        ("oversized manifest", "manifest size", good + b" " * MANIFEST_MAX),
        ("baseline nonzero sequence", "baseline shape", text.replace('"sequence":0', '"sequence":1').encode()),
        ("baseline previous set", "baseline shape",
         text.replace('"previous":null', '"previous":"' + "0" * 64 + '"').encode()),
        ("forward with restores", "restores shape",
         canonical(manifest_object(1, "forward", "0" * 64, "1" * 64, baseline))),
        ("rollback without restores", "restores shape",
         canonical(manifest_object(1, "rollback", "0" * 64, None, baseline))),
        ("forward null predecessor", "transition shape",
         canonical(manifest_object(1, "forward", None, None, baseline))),
    ]
    for label, reason, data in cases:
        expect_reject("manifest " + label, reason, functools.partial(parse_manifest, data))
    over = dict(baseline)
    over[PATHS[1]] = synthetic_payload("over", PAYLOAD_MAX + 1)
    expect_reject("payload one byte above 1 MiB", "entry size",
                  lambda: parse_manifest(canonical(manifest_object(1, "forward", "0" * 64, None, over))))
    for size in (POST_BASELINE_SIZE, 900000, PAYLOAD_MAX):
        bounded = candidate_payloads("bound", size)
        assert POST_BASELINE_SIZE <= len(bounded[PATHS[1]]) <= PAYLOAD_MAX
        encoded = canonical(manifest_object(1, "forward", "0" * 64, None, bounded))
        assert len(encoded) < MANIFEST_MAX
        assert parse_manifest(encoded)["files"][1]["size"] == size
    predecessor = "0" * 64
    for sequence in (1, 2, SEQUENCE_MAX - 1, SEQUENCE_MAX):
        for operation, restores in (("forward", None), ("rollback", predecessor)):
            encoded = canonical(manifest_object(sequence, operation, predecessor, restores, baseline))
            assert parse_manifest(encoded)["sequence"] == sequence
    for sequence in (-1, SEQUENCE_MAX + 1, SEQUENCE_MAX + 2, 2**63, 2**64):
        for operation, restores in (("forward", None), ("rollback", predecessor)):
            expect_reject(f"manifest {operation} sequence {sequence}", "sequence type",
                          functools.partial(parse_manifest, canonical(
                              manifest_object(sequence, operation, predecessor, restores, baseline))))
    expect_reject("manifest forward sequence zero", "transition shape", functools.partial(
        parse_manifest, canonical(manifest_object(0, "forward", predecessor, None, baseline))))
    for sequence in (1, SEQUENCE_MAX):
        assert rollback_message(predecessor, predecessor, predecessor, sequence).endswith(
            f"sequence={sequence}\n".encode("ascii"))
    invalid_sequences: tuple[Any, ...] = (0, -1, True, 0.0, SEQUENCE_MAX + 1, 2**64)
    for invalid_sequence in invalid_sequences:
        expect_reject(f"rollback statement sequence {invalid_sequence}", "rollback statement",
                      functools.partial(rollback_message, predecessor, predecessor, predecessor, invalid_sequence))
    print("ok: canonical manifest parser bounds")


def main() -> None:
    check_tools()
    baseline = derive_baseline()
    print("ok: derived exactly three baseline payloads with pinned names, sizes and digests")
    check_parser(baseline)
    with tempfile.TemporaryDirectory(prefix="omnipha-baseline-provenance-") as name:
        work = pathlib.Path(name)
        work.chmod(0o700)
        keys = make_keys(work)
        base = make_generation(keys, 0, "baseline", None, None, baseline)
        assert verify_generation(keys, base, baseline, None, {})["operation"] == "baseline"
        print("ok: baseline sequence 0, null previous, release signature and pins verify")

        large = candidate_payloads("forward", PAYLOAD_MAX)
        forward = make_generation(keys, 1, "forward", base.ident, None, large)
        history = {base.ident: base, forward.ident: forward}
        assert verify_generation(keys, forward, large, base, history)["sequence"] == 1
        for size in (POST_BASELINE_SIZE, 900000):
            data = candidate_payloads(f"size{size}", size)
            other = make_generation(keys, 1, "forward", base.ident, None, data)
            verify_generation(keys, other, data, base, {base.ident: base, other.ident: other})
        print("ok: forward candidates at 846492, 900000 and 1048576 byte posts verify")

        rollback = make_generation(keys, 2, "rollback", forward.ident, base.ident, baseline)
        parsed = verify_generation(keys, rollback, baseline, forward, history)
        assert parsed["sequence"] == 2 and parsed["previous"] == forward.ident
        assert parsed["restores"] == base.ident
        assert rollback.ident not in (base.ident, forward.ident)
        assert rollback.manifest != base.manifest
        assert parse_manifest(rollback.manifest)["files"] == parse_manifest(base.manifest)["files"]
        assert rollback.rollback_sig is not None and rollback.rollback_sig != rollback.release_sig
        print("ok: rollback is a new higher sequence restoring baseline content with a separate signature")

        def roll(**changes: Any) -> Generation:
            return dataclasses.replace(rollback, **changes)

        def check_roll(gen: Generation, payloads: dict[str, bytes] = baseline,
                       use: Keys = keys, active: Generation | None = forward,
                       hist: dict[str, Generation] = history) -> dict[str, Any]:
            return verify_generation(use, gen, payloads, active, hist)

        statement = rollback_message(forward.ident, rollback.ident, base.ident, 2)
        wrong_target = rollback_message(forward.ident, "f" * 64, base.ident, 2)
        wrong_restore = rollback_message(forward.ident, rollback.ident, forward.ident, 2)
        wrong_sequence = rollback_message(forward.ident, rollback.ident, base.ident, 3)
        wrong_current = rollback_message(base.ident, rollback.ident, base.ident, 2)

        expect_reject("rollback signature missing", "rollback signature missing",
                      lambda: check_roll(roll(rollback_sig=None)))
        expect_reject("rollback signature empty", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=b"")))
        expect_reject("rollback signature garbage", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=b"not a signature\n")))
        assert rollback.rollback_sig is not None
        rolled_sig = rollback.rollback_sig
        expect_reject("rollback signature corrupted", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=flip(rolled_sig, len(rolled_sig) // 2))))
        for label, message in (("target", wrong_target), ("restored id", wrong_restore),
                               ("sequence", wrong_sequence), ("current id", wrong_current)):
            signature = ssh_sign(keys, keys.rollback_key, ROLLBACK_NS, message)
            expect_reject("rollback signature over wrong " + label, "rollback signature",
                          functools.partial(check_roll, roll(rollback_sig=signature)))
        expect_reject("rollback signature without domain separator", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=ssh_sign(
                          keys, keys.rollback_key, ROLLBACK_NS, statement[len(ROLLBACK_DOMAIN):]))))
        expect_reject("rollback signature with release domain", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=ssh_sign(
                          keys, keys.rollback_key, ROLLBACK_NS, RELEASE_DOMAIN + statement[len(ROLLBACK_DOMAIN):]))))
        expect_reject("release signature reused as rollback signature", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=rollback.release_sig)))
        expect_reject("release key signs rollback in rollback namespace", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=ssh_sign(
                          keys, keys.release_key, ROLLBACK_NS, statement))))
        expect_reject("release key signs rollback in release namespace", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=ssh_sign(
                          keys, keys.release_key, RELEASE_NS, statement))))
        expect_reject("rollback signature in release namespace", "rollback signature",
                      lambda: check_roll(roll(rollback_sig=ssh_sign(
                          keys, keys.rollback_key, RELEASE_NS, statement))))
        expect_reject("rollback key signs release", "release signature",
                      lambda: check_roll(roll(release_sig=ssh_sign(
                          keys, keys.rollback_key, ROLLBACK_NS, release_message(rollback.manifest)))))
        expect_reject("release signature in rollback namespace", "release signature",
                      lambda: check_roll(roll(release_sig=ssh_sign(
                          keys, keys.release_key, ROLLBACK_NS, release_message(rollback.manifest)))))
        expect_reject("release signature without domain separator", "release signature",
                      lambda: check_roll(roll(release_sig=ssh_sign(
                          keys, keys.release_key, RELEASE_NS, rollback.manifest))))
        expect_reject("release signature empty", "release signature",
                      lambda: check_roll(roll(release_sig=b"")))

        swapped_all = dataclasses.replace(keys, release_signers=keys.rollback_signers,
                                          rollback_signers=keys.release_signers)
        expect_reject("both signer sets swapped", "signer policy",
                      lambda: check_roll(rollback, use=swapped_all))
        swapped_rollback = dataclasses.replace(keys, rollback_signers=keys.release_signers)
        expect_reject("rollback signer set is release signer set", "signer policy",
                      lambda: check_roll(rollback, use=swapped_rollback))
        swapped_release = dataclasses.replace(keys, release_signers=keys.rollback_signers)
        expect_reject("release signer set is rollback signer set", "signer policy",
                      lambda: check_roll(rollback, use=swapped_release))

        check_signer_policy(keys, lambda use: check_roll(rollback, use=use),
                            lambda use: verify_generation(use, base, baseline, None, {}),
                            lambda use: verify_generation(use, forward, large, base, history))
        assert rollback.rollback_sig is not None
        check_signatures(keys, rollback.rollback_sig, statement, rollback.release_sig,
                         release_message(rollback.manifest),
                         lambda sig: check_roll(roll(rollback_sig=sig)))
        expect_reject("modified manifest", "release signature",
                      lambda: check_roll(roll(manifest=rollback.manifest.replace(b'"sequence":2', b'"sequence":3'))))
        expect_reject("modified manifest byte", "manifest",
                      lambda: check_roll(roll(manifest=flip(rollback.manifest, 40))))
        expect_reject("modified manifest digest", "release signature",
                      lambda: check_roll(roll(manifest=rollback.manifest.replace(
                          PINNED[2][3].encode(), ("0" * 64).encode()))))
        modified = dict(baseline)
        modified[PATHS[1]] = flip(baseline[PATHS[1]], 1000)
        expect_reject("modified post payload", "payload digest", lambda: check_roll(rollback, modified))
        modified = dict(baseline)
        modified[PATHS[2]] = baseline[PATHS[2]] + b"\n"
        expect_reject("modified hook payload size", "payload size", lambda: check_roll(rollback, modified))
        modified = dict(baseline)
        del modified[PATHS[0]]
        expect_reject("missing radio payload", "payload set", lambda: check_roll(rollback, modified))
        modified = dict(baseline)
        modified["/etc/local.d/extra"] = b"x"
        expect_reject("extra payload", "payload set", lambda: check_roll(rollback, modified))
        expect_reject("forward payloads for rollback manifest", "payload", lambda: check_roll(rollback, large))

        wrong_prev = make_generation(keys, 2, "rollback", base.ident, base.ident, baseline)
        expect_reject("rollback with wrong predecessor", "predecessor", lambda: check_roll(wrong_prev))
        unknown_prev = make_generation(keys, 2, "rollback", "a" * 64, base.ident, baseline)
        expect_reject("rollback with unknown predecessor", "predecessor", lambda: check_roll(unknown_prev))
        expect_reject("rollback against wrong active generation", "predecessor",
                      lambda: check_roll(rollback, active=base))
        expect_reject("rollback without active generation", "transition without active generation",
                      lambda: check_roll(rollback, active=None))
        stale = make_generation(keys, 1, "rollback", forward.ident, base.ident, baseline)
        expect_reject("rollback with non-increasing sequence", "sequence", lambda: check_roll(stale))
        skipped = make_generation(keys, 3, "rollback", forward.ident, base.ident, baseline)
        expect_reject("rollback skipping a sequence", "sequence", lambda: check_roll(skipped))
        unknown_source = make_generation(keys, 2, "rollback", forward.ident, "b" * 64, baseline)
        expect_reject("rollback restoring unknown generation", "restored generation unknown",
                      lambda: check_roll(unknown_source))
        expect_reject("rollback with source missing from history", "restored generation unknown",
                      lambda: check_roll(rollback, hist={forward.ident: forward}))
        impostor = dataclasses.replace(base, manifest=base.manifest.replace(b'"sequence":0', b'"sequence":0 '))
        expect_reject("history entry keyed under wrong id", "restored generation unknown",
                      lambda: check_roll(rollback, hist={base.ident: impostor, forward.ident: forward}))
        self_restore = make_generation(keys, 2, "rollback", forward.ident, forward.ident, large)
        expect_reject("rollback restoring the active generation", "restores active generation",
                      lambda: check_roll(self_restore, large))
        content_mismatch = make_generation(keys, 2, "rollback", forward.ident, base.ident, large)
        expect_reject("rollback content differs from restored generation", "restored content",
                      lambda: check_roll(content_mismatch, large))
        newer = make_generation(keys, 3, "forward", rollback.ident, None, candidate_payloads("n", 900000))
        later_history = {**history, rollback.ident: rollback, newer.ident: newer}
        forward_restore = make_generation(keys, 4, "rollback", newer.ident, newer.ident, candidate_payloads("n", 900000))
        expect_reject("rollback restoring newest generation", "restores active generation",
                      lambda: check_roll(forward_restore, candidate_payloads("n", 900000),
                                         active=newer, hist=later_history))
        expect_reject("replayed old rollback manifest", "predecessor",
                      lambda: check_roll(rollback, active=newer, hist=later_history))
        expect_reject("rollback manifest replaced by old baseline", "baseline after initialization",
                      lambda: check_roll(base))

        forward_bad_sig = dataclasses.replace(forward, rollback_sig=rollback.rollback_sig)
        expect_reject("forward carrying a rollback signature", "unexpected rollback signature",
                      lambda: verify_generation(keys, forward_bad_sig, large, base, history))
        wrong_forward_prev = make_generation(keys, 1, "forward", "c" * 64, None, large)
        expect_reject("forward with wrong predecessor", "predecessor",
                      lambda: verify_generation(keys, wrong_forward_prev, large, base, history))
        skipped_forward = make_generation(keys, 2, "forward", base.ident, None, large)
        expect_reject("forward skipping a sequence", "sequence",
                      lambda: verify_generation(keys, skipped_forward, large, base, history))
        expect_reject("forward replayed over its own successor", "predecessor",
                      lambda: verify_generation(keys, forward, large, forward, history))
        expect_reject("forward modified payload", "payload digest",
                      lambda: verify_generation(keys, forward, {**large, PATHS[1]: flip(large[PATHS[1]], 5)},
                                                base, history))
        expect_reject("forward release signature by rollback key", "release signature",
                      lambda: verify_generation(keys, dataclasses.replace(
                          forward, release_sig=ssh_sign(keys, keys.rollback_key, RELEASE_NS,
                                                       release_message(forward.manifest))),
                          large, base, history))
        expect_reject("forward under swapped signers", "signer policy",
                      lambda: verify_generation(swapped_all, forward, large, base, history))
        expect_reject("forward with missing release signature", "release signature",
                      lambda: verify_generation(keys, dataclasses.replace(forward, release_sig=b""),
                                                large, base, history))

        altered = dict(baseline)
        altered[PATHS[0]] = flip(baseline[PATHS[0]], 7)
        altered_base = make_generation(keys, 0, "baseline", None, None, altered)
        expect_reject("signed baseline not matching pins", "baseline pin",
                      lambda: verify_generation(keys, altered_base, altered, None, {}))
        expect_reject("baseline with modified payload", "payload digest",
                      lambda: verify_generation(keys, base, altered, None, {}))
        expect_reject("baseline signed by rollback key", "release signature",
                      lambda: verify_generation(keys, dataclasses.replace(base, release_sig=ssh_sign(
                          keys, keys.rollback_key, ROLLBACK_NS, release_message(base.manifest))),
                          baseline, None, {}))
        expect_reject("baseline with rollback signature", "unexpected rollback signature",
                      lambda: verify_generation(keys, dataclasses.replace(base, rollback_sig=b"x"),
                                                baseline, None, {}))
        oversize = dict(large)
        oversize[PATHS[1]] = large[PATHS[1]] + b"\n"
        expect_reject("forward post one byte above 1 MiB", "payload",
                      lambda: verify_generation(keys, forward, oversize, base, history))

        assert len(forward.manifest) < MANIFEST_MAX and len(rollback.manifest) < MANIFEST_MAX
        print(f"manifest sizes: baseline {len(base.manifest)} forward {len(forward.manifest)} "
              f"rollback {len(rollback.manifest)} (bound {MANIFEST_MAX})")

    assert not work.exists()
    print("PASS: host-only synthetic-key baseline, forward and rollback provenance fixture")
    print("NOTICE: this fixture uses throwaway synthetic keys generated in a temporary directory.")
    print("NOTICE: it does NOT provide an actual authorized device baseline signature.")
    print("NOTICE: it is NOT a reviewed schema implementation, updater or dependent pair.")
    print("NOTICE: it establishes no device behavior and authorizes no install, flash or boot.")


main()
