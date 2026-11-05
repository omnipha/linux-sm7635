#!/usr/bin/env python3
import dataclasses
import functools
import hashlib
import importlib.util
import itertools
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any

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


def ssh_verify(keys: Keys, signers: pathlib.Path, principal: str, namespace: str,
               message: bytes, signature: bytes) -> bool:
    sig = keys.work / f"signature{next(counter)}"
    sig.write_bytes(signature)
    done = run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", principal,
                "-n", namespace, "-s", str(sig)], message)
    return done.returncode == 0


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


def verify_release(keys: Keys, gen: Generation, reason: str) -> dict[str, Any]:
    parsed = parse_manifest(gen.manifest)
    if not ssh_verify(keys, keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS,
                      release_message(gen.manifest), gen.release_sig):
        raise Reject(reason)
    return parsed


def verify_generation(keys: Keys, gen: Generation, payloads: dict[str, bytes],
                      active: Generation | None, history: dict[str, Generation]) -> dict[str, Any]:
    parsed = verify_release(keys, gen, "release signature")
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
        active_parsed = verify_release(keys, active, "active release signature")
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
            source_parsed = verify_release(keys, source, "restored release signature")
            if source_parsed["sequence"] >= active_parsed["sequence"]:
                raise Reject("restored generation not older")
            if parsed["files"] != source_parsed["files"]:
                raise Reject("restored content")
            if gen.rollback_sig is None:
                raise Reject("rollback signature missing")
            statement = rollback_message(active.ident, gen.ident, restores, parsed["sequence"])
            if not ssh_verify(keys, keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS,
                              statement, gen.rollback_sig):
                raise Reject("rollback signature")
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
        expect_reject("both signer sets swapped", "release signature",
                      lambda: check_roll(rollback, use=swapped_all))
        swapped_rollback = dataclasses.replace(keys, rollback_signers=keys.release_signers)
        expect_reject("rollback signer set is release signer set", "rollback signature",
                      lambda: check_roll(rollback, use=swapped_rollback))
        swapped_release = dataclasses.replace(keys, release_signers=keys.rollback_signers)
        expect_reject("release signer set is rollback signer set", "release signature",
                      lambda: check_roll(rollback, use=swapped_release))
        assert not ssh_verify(keys, keys.release_signers, RELEASE_PRINCIPAL, ROLLBACK_NS,
                              release_message(rollback.manifest), rollback.release_sig)
        assert not ssh_verify(keys, keys.release_signers, ROLLBACK_PRINCIPAL, RELEASE_NS,
                              release_message(rollback.manifest), rollback.release_sig)
        print("rejected: wrong namespace and wrong principal at ssh-keygen level")

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
        expect_reject("forward under swapped signers", "release signature",
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
