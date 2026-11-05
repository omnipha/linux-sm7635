#!/usr/bin/env python3
import ast
import base64
import copy
import dataclasses
import functools
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any, NoReturn, cast
from unittest import mock

SCHEMA = "omnipha-sm7635-root-generation-v1"
RELEASE_NS = "omnipha-sm7635-root-release-v1@fixture.invalid"
ROLLBACK_NS = "omnipha-sm7635-root-rollback-v1@fixture.invalid"
RELEASE_DOMAIN = b"omnipha-sm7635-root-generation-v1/release\n"
ROLLBACK_DOMAIN = b"omnipha-sm7635-root-generation-v1/rollback\n"
RELEASE_PRINCIPAL = "fixture-release"
ROLLBACK_PRINCIPAL = "fixture-rollback"
PATHS = (
    "/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh",
    "/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh",
    "/etc/local.d/10-omnipha-self-stage.start",
)
BAD_RADIO = "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3"
RUN113_PINS = {
    "init_boot_sha256": "d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c",
    "vendor_boot_b_sha256": "221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500",
}
RUN113_FILES = {
    PATHS[0]: "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14",
    PATHS[1]: "113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3",
    PATHS[2]: "3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67",
}
LEGACY_IMAGE_NS = "omnipha-legacy-image-attestation-v1@fixture.invalid"
LEGACY_IMAGE_PRINCIPAL = "fixture-legacy-image"
LEGACY_IMAGE_DOMAIN = b"omnipha-legacy-image-attestation-v1\n"
SEQUENCE_MAX = 2**31 - 1
MANIFEST_KEYS = ["schema", "sequence", "operation", "previous", "files", "restores"]
ENTRY_KEYS = ["path", "size", "sha256", "uid", "gid", "mode"]


class Reject(Exception):
    pass


def refuse(reason: str) -> NoReturn:
    raise Reject(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_id(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def canonical(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def parse_manifest(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 4096:
        refuse("manifest size")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in items}) != len(items):
            refuse("duplicate key")
        return dict(items)

    def constant(_: str) -> NoReturn:
        refuse("number spelling")

    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        refuse("manifest encoding or JSON")
    if not isinstance(obj, dict) or list(obj) != MANIFEST_KEYS:
        refuse("manifest fields")
    if obj["schema"] != SCHEMA:
        refuse("schema")
    if type(obj["sequence"]) is not int or not 0 <= obj["sequence"] <= SEQUENCE_MAX:
        refuse("sequence type")
    if obj["operation"] not in ("baseline", "forward", "rollback"):
        refuse("operation")
    if any(value is not None and not is_id(value) for value in (obj["previous"], obj["restores"])):
        refuse("manifest id")
    if obj["operation"] == "baseline":
        if obj["sequence"] != 0 or obj["previous"] is not None or obj["restores"] is not None:
            refuse("baseline shape")
    elif (obj["sequence"] == 0 or obj["previous"] is None or
          (obj["operation"] == "rollback") != (obj["restores"] is not None)):
        refuse("transition shape")
    files = obj["files"]
    if not isinstance(files, list) or len(files) != len(PATHS):
        refuse("file count")
    for entry, path in zip(files, PATHS):
        if not isinstance(entry, dict) or list(entry) != ENTRY_KEYS:
            refuse("file fields")
        if entry["path"] != path:
            refuse("file path or order")
        if type(entry["size"]) is not int or not 0 < entry["size"] <= 1048576:
            refuse("file size")
        if not is_id(entry["sha256"]) or entry["sha256"] == BAD_RADIO:
            refuse("file digest")
        if type(entry["uid"]) is not int or entry["uid"] != 0:
            refuse("file uid")
        if type(entry["gid"]) is not int or entry["gid"] != 0:
            refuse("file gid")
        if entry["mode"] != "0700":
            refuse("file mode")
    if canonical(obj) != raw:
        refuse("not canonical")
    return obj


def manifest(sequence: int, operation: str, previous: str | None, restores: str | None,
             payloads: tuple[bytes, ...]) -> bytes:
    entries = [{"path": path, "size": len(data), "sha256": digest(data),
                "uid": 0, "gid": 0, "mode": "0700"} for path, data in zip(PATHS, payloads)]
    return canonical({"schema": SCHEMA, "sequence": sequence, "operation": operation,
                      "previous": previous, "files": entries, "restores": restores})


def rollback_message(current: str, target: str, restores: str, sequence: int) -> bytes:
    if type(sequence) is not int or not 0 < sequence <= SEQUENCE_MAX:
        refuse("rollback statement")
    return ROLLBACK_DOMAIN + (
        f"current={current}\ntarget={target}\nrestores={restores}\nsequence={sequence}\n"
    ).encode("ascii")


def run(args: list[str], data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, input=data, capture_output=True, check=False)


def load_verifier() -> Any:
    path = pathlib.Path(__file__).resolve().with_name("verify-root-generation-bundle.py")
    spec = importlib.util.spec_from_file_location("verify_root_generation_bundle", path)
    if spec is None or spec.loader is None:
        raise ImportError("verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFIER = load_verifier()


def signer_key_material(signers: pathlib.Path, principal: str, namespace: str) -> bytes:
    try:
        blob = VERIFIER.load_signers(signers, principal, namespace)[1]
    except VERIFIER.Reject as exc:
        refuse(str(exc))
    return cast(bytes, blob)


def signer_pin(keys: "Keys") -> tuple[bytes, bytes]:
    require(keys.release_signers.resolve() != keys.rollback_signers.resolve(), "keys not distinct")
    release = signer_key_material(keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS)
    rollback = signer_key_material(keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS)
    require(release != rollback, "keys not distinct")
    return release, rollback


class Keys:
    def __init__(self, directory: pathlib.Path) -> None:
        self.directory = directory
        self.verified: set[tuple[bool, bytes, bytes, bytes]] = set()
        self.release, self.release_signers = self.make_key("release", RELEASE_PRINCIPAL, RELEASE_NS)
        self.rollback, self.rollback_signers = self.make_key("rollback", ROLLBACK_PRINCIPAL, ROLLBACK_NS)
        signer_pin(self)
        assert RELEASE_DOMAIN != ROLLBACK_DOMAIN and RELEASE_NS != ROLLBACK_NS

    def make_key(self, name: str, principal: str, namespace: str) -> tuple[pathlib.Path, pathlib.Path]:
        key = self.directory / name
        result = run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(key)])
        assert result.returncode == 0, result.stderr
        assert key.stat().st_mode & 0o077 == 0
        fields = pathlib.Path(str(key) + ".pub").read_text().split()
        signers = self.directory / (name + ".signers")
        signers.write_text(f'{principal} namespaces="{namespace}" {fields[0]} {fields[1]}\n')
        return key, signers

    def sign(self, key: pathlib.Path, namespace: str, message: bytes) -> bytes:
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            target = pathlib.Path(tmp) / "message"
            target.write_bytes(message)
            result = run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", namespace, str(target)])
            assert result.returncode == 0, result.stderr
            return pathlib.Path(str(target) + ".sig").read_bytes()

    def verify(self, rollback: bool, message: bytes, signature: bytes, key: bytes | None = None) -> bool:
        signers = self.rollback_signers if rollback else self.release_signers
        principal = ROLLBACK_PRINCIPAL if rollback else RELEASE_PRINCIPAL
        namespace = ROLLBACK_NS if rollback else RELEASE_NS
        current = signer_key_material(signers, principal, namespace)
        require(key is None or current == key, "signers changed")
        try:
            canonical_sig = VERIFIER.canonical_signature(signature, namespace)
        except VERIFIER.Reject:
            return False
        cache_key = (rollback, message, canonical_sig, current)
        if cache_key in self.verified:
            return True
        try:
            accepted = VERIFIER.ssh_verify(signers, principal, namespace, message, canonical_sig, current)
        except VERIFIER.Reject as exc:
            refuse(str(exc))
        if accepted:
            self.verified.add(cache_key)
        return bool(accepted)


@dataclasses.dataclass(frozen=True)
class Generation:
    raw: bytes
    release_sig: bytes
    rollback_sig: bytes | None
    payloads: tuple[bytes, ...]

    @property
    def ident(self) -> str:
        return digest(self.raw)


def make_generation(keys: Keys, sequence: int, operation: str, previous: str | None,
                    restores: str | None, payloads: tuple[bytes, ...]) -> Generation:
    raw = manifest(sequence, operation, previous, restores, payloads)
    signature = keys.sign(keys.release, RELEASE_NS, RELEASE_DOMAIN + raw)
    authorization = None
    if operation == "rollback":
        assert previous is not None and restores is not None
        authorization = keys.sign(keys.rollback, ROLLBACK_NS,
                                  rollback_message(previous, digest(raw), restores, sequence))
    return Generation(raw, signature, authorization, payloads)


def payloads(label: str) -> tuple[bytes, ...]:
    return tuple((f"synthetic {label} {path}\n" * 3).encode() for path in PATHS)


def verify_entry(keys: Keys, baseline_id: str, gen: Generation, previous: Generation | None,
                 ancestors: dict[str, Generation], pins: tuple[bytes, bytes] | None = None) -> None:
    current = signer_pin(keys)
    require(pins is None or current == pins, "signers changed")
    release_key, rollback_key = current if pins is None else pins
    obj = parse_manifest(gen.raw)
    if not keys.verify(False, RELEASE_DOMAIN + gen.raw, gen.release_sig, release_key):
        refuse("release signature")
    if len(gen.payloads) != len(PATHS):
        refuse("payload count")
    for entry, data in zip(obj["files"], gen.payloads):
        if len(data) != entry["size"] or digest(data) != entry["sha256"]:
            refuse("payload mismatch")
    if previous is None:
        if obj["operation"] != "baseline" or gen.ident != baseline_id:
            refuse("baseline pin")
        if gen.rollback_sig is not None:
            refuse("unexpected rollback signature")
        return
    prev_obj = parse_manifest(previous.raw)
    if obj["operation"] == "baseline":
        refuse("baseline after initialization")
    if obj["previous"] != previous.ident:
        refuse("predecessor")
    if obj["sequence"] != prev_obj["sequence"] + 1:
        refuse("sequence")
    if obj["operation"] == "forward":
        if gen.rollback_sig is not None:
            refuse("unexpected rollback signature")
        return
    source_id = obj["restores"]
    source = ancestors.get(source_id)
    if source is None:
        refuse("unverified source")
    if parse_manifest(source.raw)["sequence"] >= prev_obj["sequence"]:
        refuse("source not older")
    if obj["files"] != parse_manifest(source.raw)["files"] or gen.payloads != source.payloads:
        refuse("restored content")
    if gen.rollback_sig is None:
        refuse("missing rollback signature")
    statement = rollback_message(previous.ident, gen.ident, source_id, obj["sequence"])
    if not keys.verify(True, statement, gen.rollback_sig, rollback_key):
        refuse("rollback signature")


def verify_chain(keys: Keys, baseline_id: str, generations: dict[str, Generation], ident: str
                 ) -> dict[str, Generation]:
    chain: list[Generation] = []
    seen: set[str] = set()
    current = ident
    while True:
        if current in seen:
            refuse("chain cycle")
        seen.add(current)
        gen = generations.get(current)
        if gen is None or gen.ident != current:
            refuse("missing or substituted generation")
        chain.append(gen)
        obj = parse_manifest(gen.raw)
        if obj["operation"] == "baseline":
            break
        current = obj["previous"]
    pins = signer_pin(keys)
    ancestors: dict[str, Generation] = {}
    previous = None
    for gen in reversed(chain):
        verify_entry(keys, baseline_id, gen, previous, ancestors, pins)
        ancestors[gen.ident] = gen
        previous = gen
    return ancestors


@dataclasses.dataclass(frozen=True)
class Journal:
    previous: str
    target: str
    attempt: int = 0


@dataclasses.dataclass
class Stage:
    target: str
    members: dict[str, bytes] = dataclasses.field(default_factory=dict)
    synced: set[str] = dataclasses.field(default_factory=set)
    ready: bool = False
    recognized: bool = True
    isolated: bool = True
    safe_metadata: bool = True


@dataclasses.dataclass
class FixedTemp:
    generation: str
    index: int
    data: bytes
    synced: bool = False


@dataclasses.dataclass
class State:
    generations: dict[str, Generation]
    selector: str
    fixed: list[bytes | None]
    stage: Stage | None = None
    journal_temp: Journal | None = None
    journal_temp_synced: bool = False
    journal: Journal | None = None
    fixed_temps: dict[tuple[str, int, int], FixedTemp] = dataclasses.field(default_factory=dict)
    selector_temps: dict[tuple[str, int], tuple[str, bool]] = dataclasses.field(default_factory=dict)
    archived: dict[Journal, str] = dataclasses.field(default_factory=dict)
    unsynced_archive: Journal | None = None


Action = tuple[str, Callable[[], None]]


def members(gen: Generation) -> dict[str, bytes]:
    result = {"manifest": gen.raw, "release.sig": gen.release_sig}
    if gen.rollback_sig is not None:
        result["rollback.sig"] = gen.rollback_sig
    result.update({f"payload-{i}": data for i, data in enumerate(gen.payloads)})
    return result


def require(condition: bool, reason: str) -> None:
    if not condition:
        refuse(reason)


def sequence_of(gen: Generation) -> int:
    return int(parse_manifest(gen.raw)["sequence"])


@dataclasses.dataclass
class TrustedFloor:
    sequence: int
    ident: str

    def consult(self, state: State, keys: Keys, baseline_id: str) -> str:
        require(type(self.sequence) is int and self.sequence >= 0 and is_id(self.ident), "invalid trusted floor")
        validate_archive_history(state, keys, baseline_id, state.journal)
        ident = state.selector if state.journal is None else state.journal.previous
        chain = verify_chain(keys, baseline_id, state.generations, ident)
        require(sequence_of(chain[ident]) >= self.sequence, "below trusted floor")
        require(self.ident in chain, "trusted checkpoint not in chain")
        require(sequence_of(chain[self.ident]) == self.sequence, "trusted floor mismatch")
        return ident

    def check(self, state: State, keys: Keys, baseline_id: str) -> str:
        self.consult(state, keys, baseline_id)
        return boot_clean(state, keys, baseline_id)

    def advance(self, state: State, keys: Keys, baseline_id: str) -> None:
        self.consult(state, keys, baseline_id)
        require(state.unsynced_archive is None, "journal archive not durable")
        ident = self.check(state, keys, baseline_id)
        sequence = sequence_of(state.generations[ident])
        self.sequence, self.ident = sequence, ident


def guard_plan(plan: list[Action], floor: TrustedFloor | None, state: State, keys: Keys,
               baseline_id: str) -> list[Action]:
    if floor is None:
        return plan

    def guard(action: Callable[[], None]) -> Callable[[], None]:
        def guarded() -> None:
            floor.consult(state, keys, baseline_id)
            action()
        return guarded

    return [(name, guard(action)) for name, action in plan]


def committed(state: State, previous: str, target: str) -> bool:
    return any(journal.previous == previous and journal.target == target and kind == "committed"
               for journal, kind in state.archived.items())


def verify_recovered(state: State, keys: Keys, baseline_id: str, current_id: str,
                     journal: Journal, reason: str) -> None:
    require(journal.previous == current_id and is_id(journal.target) and
            type(journal.attempt) is int and journal.attempt >= 0 and
            state.archived.get(journal) == "recovered", reason)
    chain = verify_chain(keys, baseline_id, state.generations, journal.target)
    require(parse_manifest(chain[journal.target].raw)["previous"] == current_id, reason)


def verify_recovered_from(state: State, keys: Keys, baseline_id: str, current_id: str, reason: str) -> None:
    journals = [journal for journal, kind in state.archived.items()
                if journal.previous == current_id and kind == "recovered"]
    require(bool(journals), reason)
    for journal in journals:
        verify_recovered(state, keys, baseline_id, current_id, journal, reason)


def verify_staged_bytes(expected: bytes, data: bytes, synced: bool) -> None:
    require(isinstance(data, bytes) and type(synced) is bool and expected.startswith(data) and
            (not synced or data == expected), "unrecognized staged bytes")


def inspect_stage(stage: Stage, state: State, keys: Keys, baseline_id: str, current_id: str,
                  chain: dict[str, Generation], candidate: Generation | None) -> None:
    require(stage.recognized and stage.isolated and stage.safe_metadata, "unknown staging")
    require(stage.target != current_id and stage.target not in state.generations, "unknown staging")
    if candidate is None or candidate.ident != stage.target:
        refuse("unverified staging candidate")
    verify_entry(keys, baseline_id, candidate, chain[current_id], chain)
    expected = members(candidate)
    names = set(stage.members)
    require(names <= set(expected) and stage.synced <= names, "unknown staging")
    require(all(isinstance(v, bytes) for v in stage.members.values()), "unknown staging")
    order = list(expected)
    present = [name for name in order if name in names]
    require(present == order[:len(present)], "unknown staging")
    unsynced = [name for name in present if name not in stage.synced]
    require(len(unsynced) <= 1 and (not unsynced or unsynced[0] == present[-1]), "unrecognized staged bytes")
    for name in present:
        verify_staged_bytes(expected[name], stage.members[name], name in stage.synced)
    if stage.ready:
        require(present == order and not unsynced, "unrecognized staged bytes")


def is_plain_generation_target(target: str) -> bool:
    return isinstance(target, str) and is_id(target) and len(target) == 64


def inspect_leftovers(state: State, keys: Keys, baseline_id: str, current_id: str,
                      candidate: Generation | None = None) -> list[str]:
    chain = verify_chain(keys, baseline_id, state.generations, current_id)
    found: list[str] = []
    if state.stage is not None:
        require(state.journal_temp is None, "unknown staging")
        require(is_plain_generation_target(state.stage.target), "unknown staging")
        inspect_stage(state.stage, state, keys, baseline_id, current_id, chain, candidate)
        found.append("generation staging")
    temp = state.journal_temp
    if temp is not None:
        require(type(temp.attempt) is int and temp.attempt >= 0 and
                temp.previous == current_id and is_plain_generation_target(temp.target) and
                temp.target != current_id and temp.target in state.generations, "unknown journal staging")
        target_chain = verify_chain(keys, baseline_id, state.generations, temp.target)
        next_attempt = 1 + max((journal.attempt for journal in state.archived
                                if journal.previous == temp.previous and journal.target == temp.target), default=-1)
        require(parse_manifest(target_chain[temp.target].raw)["previous"] == current_id and
                temp not in state.archived and not committed(state, current_id, temp.target) and
                temp.attempt == next_attempt, "unknown journal staging")
        found.append("journal staging")
    for (kind, attempt, index), fixed in state.fixed_temps.items():
        require(is_plain_generation_target(fixed.generation) and isinstance(attempt, int) and
                isinstance(index, int) and kind in ("update", "recovery") and
                index == fixed.index and 0 <= index < len(PATHS) and
                fixed.generation in state.generations, "unknown fixed staging")
        if kind == "update":
            verify_recovered(state, keys, baseline_id, current_id,
                             Journal(current_id, fixed.generation, attempt), "unknown fixed staging")
        else:
            require(fixed.generation == current_id, "unknown fixed staging")
            verify_recovered_from(state, keys, baseline_id, current_id, "unknown fixed staging")
        verify_staged_bytes(state.generations[fixed.generation].payloads[index], fixed.data, fixed.synced)
        found.append("fixed staging")
    for (kind, attempt), (value, synced) in state.selector_temps.items():
        require(isinstance(kind, str) and isinstance(attempt, int) and isinstance(value, str) and
                isinstance(synced, bool), "unknown selector staging")
        if kind == "update":
            verify_recovered(state, keys, baseline_id, current_id,
                             Journal(current_id, value, attempt), "unknown selector staging")
        else:
            require(kind == "recovery" and value == current_id, "unknown selector staging")
            verify_recovered_from(state, keys, baseline_id, current_id, "unknown selector staging")
        found.append("selector staging")
    return found


def verify_archive_edge(state: State, keys: Keys, baseline_id: str, journal: Journal, reason: str) -> None:
    require(journal.previous != journal.target, reason)
    prev_chain = verify_chain(keys, baseline_id, state.generations, journal.previous)
    target_chain = verify_chain(keys, baseline_id, state.generations, journal.target)
    require(parse_manifest(target_chain[journal.target].raw)["previous"] == prev_chain[journal.previous].ident,
            reason)


def validate_archive_history(state: State, keys: Keys, baseline_id: str, pending: Journal | None = None) -> None:
    reason = "journal history collision"
    pairs: dict[tuple[str, str], dict[int, str]] = {}
    if pending is not None:
        pairs[(pending.previous, pending.target)] = {pending.attempt: "pending"}
    for archived, kind in state.archived.items():
        require(type(archived.attempt) is int and archived.attempt >= 0 and
                is_id(archived.previous) and is_id(archived.target) and kind in ("committed", "recovered"),
                reason)
        try:
            verify_archive_edge(state, keys, baseline_id, archived, reason)
        except Reject as exc:
            refuse(f"{reason}: {exc}")
        pairs.setdefault((archived.previous, archived.target), {})[archived.attempt] = kind
    for attempts in pairs.values():
        kinds = [attempts.get(n) for n in range(len(attempts))]
        require(None not in kinds, reason)
        require(all(kind == "recovered" for kind in kinds[:-1]), reason)
        require(kinds[-1] in ("recovered", "committed", "pending"), reason)
    roots = {journal.previous for journal in state.archived}
    roots.add(pending.previous if pending is not None else state.selector)
    for ident in roots:
        chain = verify_chain(keys, baseline_id, state.generations, ident)
        for gen in chain.values():
            previous = parse_manifest(gen.raw)["previous"]
            edge_attempts = pairs.get((previous, gen.ident))
            require(edge_attempts is None or "committed" in edge_attempts.values(), reason)


def validate_pending(state: State, keys: Keys, baseline_id: str) -> tuple[Generation, Generation]:
    journal = state.journal
    if journal is None or journal.previous == journal.target:
        refuse("invalid journal")
    require(type(journal.attempt) is int and journal.attempt >= 0 and
            is_id(journal.previous) and is_id(journal.target), "invalid journal")
    require(journal not in state.archived and not committed(state, journal.previous, journal.target),
            "journal history collision")
    validate_archive_history(state, keys, baseline_id, journal)
    prev_chain = verify_chain(keys, baseline_id, state.generations, journal.previous)
    target_chain = verify_chain(keys, baseline_id, state.generations, journal.target)
    previous = prev_chain[journal.previous]
    target = target_chain[journal.target]
    require(parse_manifest(target.raw)["previous"] == previous.ident, "journal transition")
    require(state.selector in (previous.ident, target.ident), "journal selector")
    require(len(state.fixed) == len(PATHS), "fixed count")
    for old, new, found in zip(previous.payloads, target.payloads, state.fixed):
        require(found is not None and found in (old, new), "unknown fixed file")
    for name, temp in state.fixed_temps.items():
        require(isinstance(name, tuple) and len(name) == 3, "unknown fixed staging")
        kind, attempt, index = name
        require(kind in ("update", "recovery") and type(attempt) is int and attempt >= 0 and
                type(index) is int and index == temp.index and 0 <= index < len(PATHS) and
                (kind == "recovery" or attempt == journal.attempt), "unknown fixed staging")
        desired = target if kind == "update" else previous
        require(temp.generation == desired.ident, "unknown staging generation")
        verify_staged_bytes(desired.payloads[index], temp.data, temp.synced)
    for selector_name, selector_temp in state.selector_temps.items():
        require(isinstance(selector_name, tuple) and len(selector_name) == 2 and
                isinstance(selector_temp, tuple) and len(selector_temp) == 2, "unknown selector staging")
        kind, attempt = selector_name
        value, synced = selector_temp
        require(kind in ("update", "recovery") and type(attempt) is int and attempt >= 0 and
                type(synced) is bool and (kind == "recovery" or attempt == journal.attempt),
                "unknown selector staging")
        require(value == (target.ident if kind == "update" else previous.ident), "unknown selector staging")
    require(state.stage is None and state.journal_temp is None, "unexpected pending staging")
    return previous, target


def boot_clean(state: State, keys: Keys, baseline_id: str, candidate: Generation | None = None) -> str:
    require(state.journal is None, "journal needs recovery")
    validate_archive_history(state, keys, baseline_id)
    chain = verify_chain(keys, baseline_id, state.generations, state.selector)
    selected = chain[state.selector]
    require(state.fixed == list(selected.payloads), "fixed files differ from selector")
    inspect_leftovers(state, keys, baseline_id, selected.ident, candidate)
    return selected.ident


def update_plan(state: State, keys: Keys, baseline_id: str, target: Generation,
                floor: TrustedFloor | None = None) -> list[Action]:
    if floor is not None:
        floor.consult(state, keys, baseline_id)
    require(state.unsynced_archive is None, "journal archive not durable")
    current_id = boot_clean(state, keys, baseline_id, target)
    leftovers = inspect_leftovers(state, keys, baseline_id, current_id, target)
    require(not leftovers, "staging collision")
    attempts = [journal.attempt for journal in state.archived
                if journal.previous == current_id and journal.target == target.ident]
    retry = target.ident in state.generations
    if retry:
        require(bool(attempts) and state.generations[target.ident] == target and
                all(state.archived[Journal(current_id, target.ident, n)] == "recovered" for n in attempts),
                "generation collision")
    else:
        require(not attempts, "journal history collision")
    chain = verify_chain(keys, baseline_id, state.generations, current_id)
    previous = chain[current_id]
    verify_entry(keys, baseline_id, target, previous, chain)
    attempt = 1 + max(attempts, default=-1)
    journal = Journal(current_id, target.ident, attempt)
    require(journal not in state.archived and not committed(state, current_id, target.ident),
            "journal history collision")
    plan: list[Action] = []
    def create_stage() -> None:
        require(state.stage is None, "staging collision")
        state.stage = Stage(target.ident)

    expected = members(target)
    if not retry:
        plan.append(("create generation staging", create_stage))
    for name, data in ({} if retry else expected).items():
        def first(n: str = name, d: bytes = data) -> None:
            assert state.stage is not None
            state.stage.members[n] = d[:len(d) // 2]

        def finish(n: str = name, d: bytes = data) -> None:
            assert state.stage is not None
            require(state.stage.members.get(n) == d[:len(d) // 2], "staging changed")
            state.stage.members[n] = d

        def sync(n: str = name, d: bytes = data) -> None:
            assert state.stage is not None
            require(state.stage.members.get(n) == d, "staging readback")
            state.stage.synced.add(n)

        plan.extend([(f"write partial {name}", first), (f"finish {name}", finish),
                     (f"sync and verify {name}", sync)])

    def sync_generation() -> None:
        assert state.stage is not None
        require(state.stage.members == expected and state.stage.synced == set(expected), "incomplete staging")
        state.stage.ready = True

    def publish_generation() -> None:
        assert state.stage is not None
        require(state.stage.ready and state.stage.members == expected, "unverified staging")
        require(target.ident not in state.generations, "generation collision")
        state.generations[target.ident] = target
        state.stage = None

    if not retry:
        plan.extend([("sync generation directory", sync_generation),
                     ("publish generation without replacement", publish_generation),
                     ("sync generations parent", lambda: None)])

    def write_journal() -> None:
        require(state.journal_temp is None and state.journal is None, "journal collision")
        state.journal_temp = journal
        state.journal_temp_synced = False

    def sync_journal() -> None:
        require(state.journal_temp == journal, "journal staging")
        state.journal_temp_synced = True

    def publish_journal() -> None:
        require(state.journal_temp == journal and state.journal_temp_synced and state.journal is None,
                "journal publish")
        state.journal = journal
        state.journal_temp = None
        state.journal_temp_synced = False

    plan.extend([("write journal", write_journal), ("sync journal", sync_journal),
                 ("publish journal without replacement", publish_journal),
                 ("sync journal parent", lambda: None)])
    for index in range(len(PATHS)):
        plan.extend(fixed_steps(state, previous, target, target, index, "update", attempt))
    plan.extend(selector_steps(state, previous.ident, target.ident, "update", attempt))

    def verify_target() -> None:
        validate_pending(state, keys, baseline_id)
        require(state.selector == target.ident and state.fixed == list(target.payloads), "target recheck")

    def archive() -> None:
        verify_target()
        require(journal not in state.archived and not committed(state, current_id, target.ident),
                "journal history collision")
        state.archived[journal] = "committed"
        state.unsynced_archive = journal
        state.journal = None

    def sync_archive() -> None:
        require(state.unsynced_archive == journal, "journal archive changed")
        state.unsynced_archive = None

    plan.extend([("reverify complete target", verify_target), ("archive journal without replacement", archive),
                  ("sync journal archive parent", sync_archive)])
    return guard_plan(plan, floor, state, keys, baseline_id)


def fixed_steps(state: State, previous: Generation, target: Generation, desired: Generation,
                index: int, kind: str, attempt: int) -> list[Action]:
    name = (kind, attempt, index)
    data = desired.payloads[index]
    steps: list[Action] = []

    def create() -> None:
        require(name not in state.fixed_temps, "fixed staging collision")
        state.fixed_temps[name] = FixedTemp(desired.ident, index, data[:len(data) // 2])

    def finish() -> None:
        temp = state.fixed_temps[name]
        require(temp.data == data[:len(data) // 2], "fixed staging changed")
        temp.data = data

    def sync() -> None:
        temp = state.fixed_temps[name]
        require(temp.data == data, "fixed staging readback")
        temp.synced = True

    def publish() -> None:
        temp = state.fixed_temps[name]
        require(temp.synced and temp.data == data, "fixed staging not verified")
        require(state.fixed[index] in (previous.payloads[index], target.payloads[index]), "unknown fixed file")
        state.fixed[index] = data
        del state.fixed_temps[name]

    def verify() -> None:
        require(state.fixed[index] == data, "fixed recheck")

    steps.extend([(f"{kind} create partial fixed {index}", create),
                  (f"{kind} finish fixed {index}", finish),
                  (f"{kind} sync and verify fixed {index}", sync),
                  (f"{kind} rename fixed {index}", publish),
                  (f"{kind} sync fixed directory {index}", lambda: None),
                  (f"{kind} recheck fixed {index}", verify)])
    return steps


def selector_steps(state: State, previous: str, desired: str, kind: str, attempt: int) -> list[Action]:
    name = (kind, attempt)
    steps: list[Action] = []

    def create() -> None:
        require(name not in state.selector_temps, "selector staging collision")
        state.selector_temps[name] = (desired, False)

    def sync() -> None:
        require(state.selector_temps[name] == (desired, False), "selector staging changed")
        state.selector_temps[name] = (desired, True)

    def publish() -> None:
        require(state.selector_temps[name] == (desired, True), "selector not synced")
        require(state.selector in (previous, desired), "selector changed")
        state.selector = desired
        del state.selector_temps[name]

    steps.extend([(f"{kind} write selector", create), (f"{kind} sync selector", sync),
                  (f"{kind} rename selector", publish), (f"{kind} sync selector directory", lambda: None)])
    return steps


def recovery_plan(state: State, keys: Keys, baseline_id: str, floor: TrustedFloor | None = None
                  ) -> list[Action]:
    if floor is not None:
        floor.consult(state, keys, baseline_id)
    require(state.unsynced_archive is None, "journal archive not durable")
    previous, target = validate_pending(state, keys, baseline_id)
    journal = state.journal
    assert journal is not None
    used = {name[1] for name in state.fixed_temps if name[0] == "recovery"}
    used.update(name[1] for name in state.selector_temps if name[0] == "recovery")
    attempt = max(used, default=-1) + 1
    plan: list[Action] = []
    for index in range(len(PATHS)):
        plan.extend(fixed_steps(state, previous, target, previous, index, "recovery", attempt))
    plan.extend(selector_steps(state, target.ident, previous.ident, "recovery", attempt))

    def verify_previous() -> None:
        validate_pending(state, keys, baseline_id)
        require(state.selector == previous.ident and state.fixed == list(previous.payloads), "previous recheck")

    def archive() -> None:
        verify_previous()
        require(journal not in state.archived, "journal history collision")
        state.archived[journal] = "recovered"
        state.unsynced_archive = journal
        state.journal = None

    def sync_archive() -> None:
        require(state.unsynced_archive == journal, "journal archive changed")
        state.unsynced_archive = None

    plan.extend([("reverify complete previous", verify_previous),
                 ("archive recovered journal without replacement", archive),
                 ("sync recovered archive parent", sync_archive)])
    return guard_plan(plan, floor, state, keys, baseline_id)


def execute(plan: list[Action], cut: int | None = None) -> None:
    for _, action in plan if cut is None else plan[:cut]:
        action()


def reconcile(state: State, keys: Keys, baseline_id: str, floor: TrustedFloor | None = None,
              candidate: Generation | None = None) -> str:
    if floor is not None:
        floor.consult(state, keys, baseline_id)
    if state.journal is not None:
        execute(recovery_plan(state, keys, baseline_id, floor))
    ident = boot_clean(state, keys, baseline_id, candidate)
    if floor is not None:
        floor.consult(state, keys, baseline_id)
    return ident


def crash(state: State, lose_unsynced: bool) -> None:
    journal = state.unsynced_archive
    if journal is None:
        return
    state.unsynced_archive = None
    if lose_unsynced:
        del state.archived[journal]
        state.journal = journal


def expect_reject(label: str, reason: str, action: Callable[[], Any]) -> None:
    try:
        action()
    except Reject as exc:
        assert reason in str(exc), (label, reason, str(exc))
    else:
        raise AssertionError(f"accepted: {label}")


def assert_refusal_without_write(label: str, reason: str, state: State, action: Callable[[], Any]) -> None:
    before = copy.deepcopy(state)
    expect_reject(label, reason, action)
    assert state == before, label


def test_parser(base: Generation) -> None:
    raw = base.raw
    obj = json.loads(raw)
    cases = [
        ("whitespace", "not canonical", json.dumps(obj, indent=1).encode()),
        ("trailing newline", "not canonical", raw + b"\n"),
        ("duplicate key", "duplicate key", raw.replace(b'"sequence":0', b'"sequence":0,"sequence":0')),
        ("extra field", "manifest fields", canonical({**obj, "extra": 1})),
        ("reordered fields", "manifest fields", canonical(dict(reversed(list(obj.items()))))),
        ("non-ascii", "encoding", raw + "é".encode()),
        ("schema", "schema", raw.replace(b"generation-v1", b"generation-v2")),
        ("sequence float", "sequence type", raw.replace(b'"sequence":0', b'"sequence":0.0')),
        ("sequence bool", "sequence type", raw.replace(b'"sequence":0', b'"sequence":true')),
        ("sequence negative", "sequence type", raw.replace(b'"sequence":0', b'"sequence":-1')),
        ("sequence above bound", "sequence type",
         raw.replace(b'"sequence":0', f'"sequence":{SEQUENCE_MAX + 1}'.encode())),
        ("path", "file path", raw.replace(PATHS[0].encode(), b"/unexpected")),
        ("mode", "file mode", raw.replace(b'"0700"', b'"0755"', 1)),
        ("owner", "file uid", raw.replace(b'"uid":0', b'"uid":1', 1)),
        ("group", "file gid", raw.replace(b'"gid":0', b'"gid":1', 1)),
        ("size", "file size", raw.replace(str(len(base.payloads[0])).encode(), b"0", 1)),
        ("oversize", "manifest size", raw + b" " * 4096),
        ("bad radio digest", "file digest", raw.replace(digest(base.payloads[0]).encode(), BAD_RADIO.encode())),
        ("baseline previous", "baseline shape", raw.replace(b'"previous":null', b'"previous":"' + b"0" * 64 + b'"')),
    ]
    for label, reason, invalid in cases:
        expect_reject(label, reason, functools.partial(parse_manifest, invalid))
    print(f"parser: {len(cases)} canonical/schema/metadata mutations rejected")
    for sequence in (1, 2, SEQUENCE_MAX - 1, SEQUENCE_MAX):
        accepted = manifest(sequence, "forward", base.ident, None, base.payloads)
        assert parse_manifest(accepted)["sequence"] == sequence
        accepted = manifest(sequence, "rollback", base.ident, base.ident, base.payloads)
        assert parse_manifest(accepted)["sequence"] == sequence
    for sequence in (SEQUENCE_MAX + 1, SEQUENCE_MAX + 2, 2**63, 2**64):
        for operation, restores in (("forward", None), ("rollback", base.ident)):
            expect_reject(f"{operation} sequence {sequence}", "sequence type", functools.partial(
                parse_manifest, manifest(sequence, operation, base.ident, restores, base.payloads)))
    expect_reject("forward sequence zero", "transition shape", functools.partial(
        parse_manifest, manifest(0, "forward", base.ident, None, base.payloads)))
    for sequence in (1, SEQUENCE_MAX):
        assert rollback_message(base.ident, base.ident, base.ident, sequence).endswith(
            f"sequence={sequence}\n".encode("ascii"))
    invalid_sequences: tuple[Any, ...] = (0, -1, True, 0.0, SEQUENCE_MAX + 1, 2**64)
    for invalid_sequence in invalid_sequences:
        expect_reject(f"rollback statement sequence {invalid_sequence}", "rollback statement", functools.partial(
            rollback_message, base.ident, base.ident, base.ident, invalid_sequence))
    print(f"parser sequence bound: 1, 2, {SEQUENCE_MAX - 1} and {SEQUENCE_MAX} accepted for forward and "
          f"rollback; {SEQUENCE_MAX + 1}, 2**63 and 2**64 refused; rollback statements refuse 0, negative "
          f"and above {SEQUENCE_MAX}")


def test_authorization(keys: Keys, base: Generation, forward: Generation, rollback: Generation) -> None:
    baseline = base.ident
    history = {base.ident: base, forward.ident: forward}
    chain = verify_chain(keys, baseline, history, forward.ident)
    verify_entry(keys, baseline, rollback, forward, chain)
    parsed = parse_manifest(rollback.raw)
    assert parsed["sequence"] == 2 and parsed["previous"] == forward.ident and parsed["restores"] == base.ident
    assert rollback.ident not in (base.ident, forward.ident) and rollback.payloads == base.payloads
    statement = rollback_message(forward.ident, rollback.ident, base.ident, 2)
    mutations = [
        ("missing rollback", "missing rollback signature", dataclasses.replace(rollback, rollback_sig=None)),
        ("empty rollback", "rollback signature", dataclasses.replace(rollback, rollback_sig=b"")),
        ("bad rollback", "rollback signature", dataclasses.replace(rollback, rollback_sig=b"invalid")),
        ("release as rollback", "rollback signature", dataclasses.replace(rollback, rollback_sig=rollback.release_sig)),
        ("rollback key for release", "release signature", dataclasses.replace(
            rollback, release_sig=keys.sign(keys.rollback, RELEASE_NS, RELEASE_DOMAIN + rollback.raw))),
        ("release key for rollback", "rollback signature", dataclasses.replace(
            rollback, rollback_sig=keys.sign(keys.release, ROLLBACK_NS, statement))),
        ("release wrong namespace", "release signature", dataclasses.replace(
            rollback, release_sig=keys.sign(keys.release, ROLLBACK_NS, RELEASE_DOMAIN + rollback.raw))),
        ("rollback wrong namespace", "rollback signature", dataclasses.replace(
            rollback, rollback_sig=keys.sign(keys.rollback, RELEASE_NS, statement))),
        ("release wrong domain", "release signature", dataclasses.replace(
            rollback, release_sig=keys.sign(keys.release, RELEASE_NS, ROLLBACK_DOMAIN + rollback.raw))),
        ("release missing domain", "release signature", dataclasses.replace(
            rollback, release_sig=keys.sign(keys.release, RELEASE_NS, rollback.raw))),
        ("rollback wrong domain", "rollback signature", dataclasses.replace(
            rollback, rollback_sig=keys.sign(keys.rollback, ROLLBACK_NS,
                                             RELEASE_DOMAIN + statement[len(ROLLBACK_DOMAIN):]))),
        ("rollback missing domain", "rollback signature", dataclasses.replace(
            rollback, rollback_sig=keys.sign(keys.rollback, ROLLBACK_NS, statement[len(ROLLBACK_DOMAIN):]))),
        ("release truncated", "release signature", dataclasses.replace(rollback, release_sig=rollback.release_sig[:-8])),
        ("payload tamper", "payload mismatch", dataclasses.replace(
            rollback, payloads=(rollback.payloads[0] + b"x", *rollback.payloads[1:]))),
        ("payload missing", "payload count", dataclasses.replace(rollback, payloads=rollback.payloads[:-1])),
    ]
    for label, reason, gen in mutations:
        expect_reject(label, reason, functools.partial(verify_entry, keys, baseline, gen, forward, chain))
    for label, stmt in (
        ("current", rollback_message("0" * 64, rollback.ident, base.ident, 2)),
        ("target", rollback_message(forward.ident, "0" * 64, base.ident, 2)),
        ("restores", rollback_message(forward.ident, rollback.ident, "0" * 64, 2)),
        ("sequence", rollback_message(forward.ident, rollback.ident, base.ident, 3)),
    ):
        gen = dataclasses.replace(rollback, rollback_sig=keys.sign(keys.rollback, ROLLBACK_NS, stmt))
        expect_reject("wrong " + label, "rollback signature",
                      functools.partial(verify_entry, keys, baseline, gen, forward, chain))
    invalids = [
        ("wrong predecessor", "predecessor", make_generation(keys, 2, "rollback", base.ident, base.ident, base.payloads)),
        ("skipped sequence", "sequence", make_generation(keys, 3, "rollback", forward.ident, base.ident, base.payloads)),
        ("unknown source", "unverified source", make_generation(keys, 2, "rollback", forward.ident, "f" * 64, base.payloads)),
        ("source current", "source not older", make_generation(keys, 2, "rollback", forward.ident, forward.ident, forward.payloads)),
        ("wrong restored bytes", "restored content", make_generation(keys, 2, "rollback", forward.ident, base.ident, forward.payloads)),
    ]
    for label, reason, gen in invalids:
        expect_reject(label, reason, functools.partial(verify_entry, keys, baseline, gen, forward, chain))
    expect_reject("old manifest as rollback", "baseline after", lambda: verify_entry(keys, baseline, base, forward, chain))
    expect_reject("replay forward", "predecessor", lambda: verify_entry(keys, baseline, forward, forward, chain))
    expect_reject("forward with rollback sig", "unexpected rollback signature", lambda: verify_entry(
        keys, baseline, dataclasses.replace(forward, rollback_sig=b"extra"), base, {base.ident: base}))
    expect_reject("wrong image baseline pin", "baseline pin", lambda: verify_chain(keys, "0" * 64, history, forward.ident))
    corrupt_base = dataclasses.replace(base, release_sig=b"invalid")
    expect_reject("unverified baseline signature", "release signature", lambda: verify_chain(
        keys, baseline, {base.ident: corrupt_base, forward.ident: forward}, forward.ident))
    corrupt_payload = dataclasses.replace(base, payloads=(b"invalid", *base.payloads[1:]))
    expect_reject("unverified retained source payload", "payload mismatch", lambda: verify_chain(
        keys, baseline, {base.ident: corrupt_payload, forward.ident: forward}, forward.ident))
    print(f"authorization: {len(mutations) + 4 + len(invalids) + 6} negative vectors; distinct signed rollback accepted")


def test_interruption(keys: Keys, initial: State, previous: Generation, target: Generation) -> tuple[int, int]:
    baseline_id = next(ident for ident, gen in initial.generations.items()
                       if parse_manifest(gen.raw)["operation"] == "baseline")
    probe = copy.deepcopy(initial)
    total = len(update_plan(probe, keys, baseline_id, target))
    recovery_cuts = 0
    for cut in range(total + 1):
        state = copy.deepcopy(initial)
        plan = update_plan(state, keys, baseline_id, target)
        execute(plan, cut)
        if state.journal is not None:
            recovery_total = len(recovery_plan(state, keys, baseline_id))
            for recovery_cut in range(recovery_total + 1):
                for lose in (False, True):
                    interrupted = copy.deepcopy(state)
                    execute(recovery_plan(interrupted, keys, baseline_id), recovery_cut)
                    crash(interrupted, lose)
                    result = reconcile(interrupted, keys, baseline_id, candidate=target)
                    assert result == previous.ident, (cut, recovery_cut, lose)
                    assert interrupted.selector == previous.ident and interrupted.fixed == list(previous.payloads)
                    assert interrupted.journal is None
                    recovery_cuts += 1
        committed_at = next(i for i, (name, _) in enumerate(plan)
                            if name == "archive journal without replacement") + 1
        durable_at = next(i for i, (name, _) in enumerate(plan) if name == "sync journal archive parent") + 1
        outcomes = [False] if cut >= durable_at or cut < committed_at else [False, True]
        for lose in outcomes:
            view = copy.deepcopy(state)
            crash(view, lose)
            result = reconcile(view, keys, baseline_id, candidate=target)
            expected = target if cut >= committed_at and not lose else previous
            assert result == expected.ident, (cut, lose, plan[cut - 1][0] if cut else "before")
            assert view.fixed == list(expected.payloads) and view.journal is None
        state.unsynced_archive = None
    return total + 1, recovery_cuts


def test_corruption(keys: Keys, initial: State, base: Generation, forward: Generation,
                    rollback: Generation) -> None:
    pending = copy.deepcopy(initial)
    plan = update_plan(pending, keys, base.ident, forward)
    journal_index = next(i for i, (name, _) in enumerate(plan) if name == "publish journal without replacement")
    execute(plan, journal_index + 1)
    assert pending.journal == Journal(base.ident, forward.ident)
    cases: list[tuple[str, str, Callable[[State], Any]]] = [
        ("old signature corrupt", "release signature", lambda s: s.generations.update({
            base.ident: dataclasses.replace(base, release_sig=b"invalid")})),
        ("old payload corrupt", "payload mismatch", lambda s: s.generations.update({
            base.ident: dataclasses.replace(base, payloads=(b"bad", *base.payloads[1:]))})),
        ("old missing", "missing or substituted", lambda s: s.generations.pop(base.ident)),
        ("new signature corrupt", "release signature", lambda s: s.generations.update({
            forward.ident: dataclasses.replace(forward, release_sig=b"invalid")})),
        ("new missing", "missing or substituted", lambda s: s.generations.pop(forward.ident)),
        ("unknown fixed", "unknown fixed", lambda s: s.fixed.__setitem__(0, b"unknown")),
        ("missing fixed", "unknown fixed", lambda s: s.fixed.__setitem__(1, None)),
        ("foreign selector", "journal selector", lambda s: setattr(s, "selector", "f" * 64)),
        ("invalid journal", "invalid journal", lambda s: setattr(s, "journal", Journal(base.ident, base.ident))),
        ("unknown staging", "unknown fixed staging", lambda s: s.fixed_temps.update({
            ("foreign", 0, 0): FixedTemp(base.ident, 0, b"")})),
        ("staged corruption", "unrecognized staged bytes", lambda s: s.fixed_temps.update({
            ("update", 0, 0): FixedTemp(forward.ident, 0, b"garbage")})),
        ("archive collision", "journal history collision",
         lambda s: s.archived.update({Journal(base.ident, forward.ident): "committed"})),
        ("malformed archive kind", "journal history collision",
         lambda s: s.archived.update({Journal(base.ident, forward.ident, 7): "unknown"})),
        ("negative archive attempt", "journal history collision",
         lambda s: s.archived.update({Journal(base.ident, forward.ident, -1): "recovered"})),
        ("negative journal attempt", "invalid journal",
         lambda s: setattr(s, "journal", Journal(base.ident, forward.ident, -1))),
        ("malformed fixed staging key", "unknown fixed staging", lambda s: s.fixed_temps.update(
            cast(dict[tuple[str, int, int], FixedTemp], {("update", 0): FixedTemp(forward.ident, 0, b"")}))),
        ("negative fixed staging attempt", "unknown fixed staging", lambda s: s.fixed_temps.update({
            ("recovery", -1, 0): FixedTemp(base.ident, 0, b"")})),
        ("malformed selector staging value", "unknown selector staging", lambda s: s.selector_temps.update(
            cast(dict[tuple[str, int], tuple[str, bool]], {("recovery", 0): (base.ident, "yes")}))),
        ("wrong selector staging value", "unknown selector staging", lambda s: s.selector_temps.update({
            ("recovery", 0): (forward.ident, False)})),
    ]
    for label, reason, mutate in cases:
        state = copy.deepcopy(pending)
        mutate(state)
        assert_refusal_without_write(label, reason, state, functools.partial(reconcile, state, keys, base.ident))
    mixed = copy.deepcopy(pending)
    mixed.fixed[0] = forward.payloads[0]
    mixed.fixed[1] = b"unknown"
    assert_refusal_without_write("mixed with unknown file", "unknown fixed", mixed,
                                 lambda: reconcile(mixed, keys, base.ident))
    corrupt_active = copy.deepcopy(initial)
    corrupt_active.fixed[0] = b"unknown"
    assert_refusal_without_write("unverified current", "fixed files", corrupt_active,
                                 lambda: update_plan(corrupt_active, keys, base.ident, forward))
    recovering = State({base.ident: base, forward.ident: forward}, forward.ident, list(forward.payloads))
    plan = update_plan(recovering, keys, base.ident, rollback)
    execute(plan, next(i for i, (name, _) in enumerate(plan) if name == "publish journal without replacement") + 1)
    assert recovering.journal is not None
    corrupt_history = copy.deepcopy(recovering)
    corrupt_history.archived[Journal(forward.ident, "f" * 64, 0)] = "recovered"
    assert_refusal_without_write("recovered history for unknown target", "missing or substituted",
                                 corrupt_history, functools.partial(reconcile, corrupt_history, keys, base.ident))
    resumed = copy.deepcopy(recovering)
    resumed.fixed_temps[("recovery", 0, 0)] = FixedTemp(forward.ident, 0, b"")
    reconcile(resumed, keys, base.ident)
    assert resumed.journal is None and resumed.selector == forward.ident
    print(f"corruption: {len(cases) + 3} invalid old/new/journal/fixed/staging states refused before writes")


def test_collisions(keys: Keys, initial: State, base: Generation, forward: Generation) -> None:
    journal = Journal(base.ident, forward.ident)
    cases: list[tuple[str, str, Callable[[State], Any]]] = [
        ("unrecognized stage", "unknown staging", lambda s: setattr(
            s, "stage", Stage(forward.ident, recognized=False))),
        ("unsafe stage metadata", "unknown staging", lambda s: setattr(
            s, "stage", Stage(forward.ident, safe_metadata=False))),
        ("nonisolated stage", "unknown staging", lambda s: setattr(
            s, "stage", Stage(forward.ident, isolated=False))),
        ("foreign stage member", "unknown staging", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"foreign": b"bad"}))),
        ("corrupt stage member", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": b"bad"}))),
        ("corrupt unsynced signature", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw,
                                                      "release.sig": forward.release_sig[:-1] + b"x"},
                              synced={"manifest"}))),
        ("corrupt short payload prefix", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw, "release.sig": forward.release_sig,
                                                      "payload-0": b"wrong"},
                              synced={"manifest", "release.sig"}))),
        ("corrupt manifest prefix", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": b'{"schema":"' + SCHEMA.encode() + b'",bad'}))),
        ("manifest wrong sequence prefix", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw[:60].replace(
                b'"sequence":1', b'"sequence":9')}))),
        ("manifest wrong previous prefix", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw[:forward.raw.index(
                b'"previous":"') + 12] + b"0" * 8}))),
        ("manifest garbage after valid prefix", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw[:-3] + b"~~~"}))),
        ("manifest overlong", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw + b"x"}))),
        ("synced truncated manifest", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw[:-1]}, synced={"manifest"}))),
        ("signature header only", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw, "release.sig": b"-----BEGIN SSH SIGNATURE-----\n~~~"},
                              synced={"manifest"}))),
        ("signature trailing bytes", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw,
                                                      "release.sig": forward.release_sig + b"x"},
                              synced={"manifest"}))),
        ("synced truncated signature", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw,
                                                      "release.sig": forward.release_sig[:-8]},
                              synced={"manifest", "release.sig"}))),
        ("payload longer than size", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw, "release.sig": forward.release_sig,
                                                      "payload-0": forward.payloads[0] + b"x"},
                              synced={"manifest", "release.sig"}))),
        ("synced short payload", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw, "release.sig": forward.release_sig,
                                                      "payload-0": forward.payloads[0][:4]},
                              synced={"manifest", "release.sig", "payload-0"}))),
        ("payload out of order", "unknown staging", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw, "payload-1": forward.payloads[1][:4]},
                              synced={"manifest"}))),
        ("two unsynced members", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw, "release.sig": forward.release_sig[:20]}))),
        ("ready with missing members", "unrecognized staged bytes", lambda s: setattr(
            s, "stage", Stage(forward.ident, members={"manifest": forward.raw}, synced={"manifest"}, ready=True))),
        ("unverified candidate mismatch", "unverified staging candidate", lambda s: setattr(
            s, "stage", Stage("f" * 64, members={"manifest": forward.raw}))),
        ("unknown journal temp", "unknown journal staging", lambda s: setattr(s, "journal_temp", journal)),
        ("unknown fixed temp", "unknown fixed staging", lambda s: s.fixed_temps.update({
            ("update", 0, 0): FixedTemp(base.ident, 0, b"")})),
        ("unknown selector temp", "unknown selector staging", lambda s: s.selector_temps.update({
            ("update", 0): (base.ident, False)})),
    ]
    assert forward.payloads[0] != b"wrong" and forward.release_sig != b"corrupt"
    for label, reason, mutate in cases:
        state = copy.deepcopy(initial)
        mutate(state)
        if label == "unverified candidate mismatch":
            assert_refusal_without_write(label + " boot", reason, state,
                                         functools.partial(boot_clean, state, keys, base.ident, base))
        else:
            assert_refusal_without_write(label + " boot", reason, state,
                                         functools.partial(boot_clean, state, keys, base.ident, forward))
        assert_refusal_without_write(label + " update", reason, state,
                                     functools.partial(update_plan, state, keys, base.ident, forward))

    for label, mutate in (
        ("generation", lambda s: s.generations.update({forward.ident: forward})),
        ("archived journal", lambda s: s.archived.update({journal: "committed"})),
    ):
        state = copy.deepcopy(initial)
        mutate(state)
        assert_refusal_without_write(label, "collision", state,
                                     functools.partial(update_plan, state, keys, base.ident, forward))

    state = copy.deepcopy(initial)
    plan = update_plan(state, keys, base.ident, forward)
    publish = next(i for i, (name, _) in enumerate(plan) if name == "publish generation without replacement")
    execute(plan, publish)
    state.generations[forward.ident] = forward
    assert_refusal_without_write("late generation collision", "generation collision", state, plan[publish][1])

    state = copy.deepcopy(initial)
    plan = update_plan(state, keys, base.ident, forward)
    publish = next(i for i, (name, _) in enumerate(plan) if name == "publish journal without replacement")
    execute(plan, publish)
    state.journal = journal
    assert_refusal_without_write("late journal collision", "journal publish", state, plan[publish][1])

    inert = copy.deepcopy(initial)
    plan = update_plan(inert, keys, base.ident, forward)
    execute(plan, next(i for i, (name, _) in enumerate(plan) if name == "sync generation directory"))
    before = copy.deepcopy(inert)
    assert boot_clean(inert, keys, base.ident, forward) == base.ident and inert == before
    assert_refusal_without_write("recognized inert staging blocks update", "staging collision", inert,
                                 lambda: update_plan(inert, keys, base.ident, forward))
    print(f"collisions: {len(cases)} unknown objects refused for boot and update; "
          "recognized inert staging preserved, boots, and blocks updates")


def test_archive_history_and_signers(keys: Keys, initial: State, base: Generation, forward: Generation,
                                     rollback: Generation) -> None:
    alternate1 = make_generation(keys, 1, "forward", base.ident, None, payloads("alternate"))
    alternate2 = make_generation(keys, 2, "forward", alternate1.ident, None, payloads("alternate next"))
    generations = {gen.ident: gen for gen in (base, forward, alternate1, alternate2)}
    new_state = lambda archived: State(dict(generations), base.ident, list(base.payloads), archived=archived)
    corrupt_histories: list[tuple[str, dict[Journal, str]]] = [
        ("committed non-edge", {Journal(base.ident, alternate2.ident, 0): "committed"}),
        ("committed unknown target", {Journal(base.ident, "f" * 64, 0): "committed"}),
        ("committed unknown target payload", {Journal(base.ident, forward.ident, 0): "committed",
                                              Journal(forward.ident, "f" * 64, 0): "committed"}),
        ("recovered non-edge", {Journal(base.ident, alternate2.ident, 0): "recovered"}),
        ("recovered unknown target", {Journal(base.ident, "f" * 64, 0): "recovered"}),
        ("committed before recovered", {Journal(base.ident, forward.ident, 0): "committed",
                                        Journal(base.ident, forward.ident, 1): "recovered"}),
        ("recovered attempt gap", {Journal(base.ident, forward.ident, 0): "recovered",
                                   Journal(base.ident, forward.ident, 2): "recovered"}),
    ]
    floor = TrustedFloor(0, base.ident)
    for label, archived in corrupt_histories:
        state = new_state(archived)
        assert_refusal_without_write(label + " boot", "journal history collision", state,
                                     functools.partial(boot_clean, state, keys, base.ident))
        assert_refusal_without_write(label + " floor check", "journal history collision", state,
                                     functools.partial(floor.check, state, keys, base.ident))
        assert_refusal_without_write(label + " floor advance", "journal history collision", state,
                                     functools.partial(floor.advance, state, keys, base.ident))
    corrupt_edge = new_state({Journal(base.ident, forward.ident, 0): "recovered"})
    corrupt_edge.generations[forward.ident] = dataclasses.replace(forward, release_sig=b"invalid")
    assert_refusal_without_write("recovered with corrupt target chain", "journal history collision", corrupt_edge,
                                 functools.partial(boot_clean, corrupt_edge, keys, base.ident))
    corrupt_committed_edge = new_state({Journal(base.ident, forward.ident, 0): "committed"})
    corrupt_committed_edge.generations[forward.ident] = dataclasses.replace(forward, release_sig=b"invalid")
    assert_refusal_without_write("committed with corrupt target chain", "journal history collision",
                                 corrupt_committed_edge,
                                 functools.partial(boot_clean, corrupt_committed_edge, keys, base.ident))
    missing_target = new_state({Journal(base.ident, forward.ident, 0): "committed"})
    missing_target.generations.pop(forward.ident)
    assert_refusal_without_write("committed with missing target generation", "journal history collision",
                                 missing_target, functools.partial(boot_clean, missing_target, keys, base.ident))

    branch = new_state({Journal(base.ident, alternate1.ident, 0): "committed",
                        Journal(base.ident, forward.ident, 0): "recovered",
                        Journal(base.ident, forward.ident, 1): "committed"})
    assert boot_clean(branch, keys, base.ident) == base.ident
    branch_floor = TrustedFloor(0, base.ident)
    branch_floor.check(branch, keys, base.ident)
    branch_floor.advance(branch, keys, base.ident)
    assert (branch_floor.sequence, branch_floor.ident) == (0, base.ident)
    recovered = new_state({Journal(base.ident, alternate1.ident, 0): "recovered"})
    assert boot_clean(recovered, keys, base.ident) == base.ident
    settled = new_state({Journal(base.ident, alternate1.ident, 0): "committed"})
    settled.selector, settled.fixed = alternate1.ident, list(alternate1.payloads)
    assert floor.check(settled, keys, base.ident) == alternate1.ident
    floor.advance(settled, keys, base.ident)
    assert (floor.sequence, floor.ident) == (1, alternate1.ident)
    floor.sequence, floor.ident = 0, base.ident

    valid = State({base.ident: base, forward.ident: forward}, forward.ident, list(forward.payloads))
    valid_target = make_generation(keys, 2, "forward", forward.ident, None, payloads("valid next"))
    valid_plan = update_plan(valid, keys, base.ident, valid_target, TrustedFloor(1, forward.ident))
    execute(valid_plan, next(i for i, (name, _) in enumerate(valid_plan)
                             if name == "publish journal without replacement") + 1)
    assert valid.journal is not None
    fresh_target = make_generation(keys, 1, "forward", base.ident, None, payloads("fresh update"))
    post_plan_cases: list[tuple[str, State, Journal | None, dict[Journal, str]]] = [
        ("journal-free", State({base.ident: base}, base.ident, list(base.payloads)), None,
         {Journal(base.ident, forward.ident, 0): "recovered",
          Journal(base.ident, forward.ident, 2): "recovered"}),
        ("pending", copy.deepcopy(valid), valid.journal,
         {valid.journal: "committed", Journal(base.ident, forward.ident, 1): "recovered"}),
    ]
    post_plan_refusals = 0
    for label, source, journal, archived in post_plan_cases:
        live = copy.deepcopy(source)
        live_floor = TrustedFloor(0 if journal is None else 1, base.ident if journal is None else forward.ident)
        plan = (update_plan(live, keys, base.ident, fresh_target if journal is None else valid_target, live_floor)
                if journal is None else recovery_plan(live, keys, base.ident, live_floor))
        live.archived.update(archived)
        assert_refusal_without_write(label + " post-plan consult", "journal history collision", live,
                                     functools.partial(live_floor.consult, live, keys, base.ident))
        assert_refusal_without_write(label + " post-plan guarded action", "journal history collision", live,
                                     plan[0][1])
        post_plan_refusals += 2
    assert valid.journal is not None and valid.archived == {}

    pending = State({base.ident: base}, base.ident, list(base.payloads))
    pending_plan = update_plan(pending, keys, base.ident, forward)
    execute(pending_plan, next(i for i, (name, _) in enumerate(pending_plan)
                               if name == "publish journal without replacement") + 1)
    assert pending.journal == Journal(base.ident, forward.ident)
    corrupt_retried = copy.deepcopy(pending)
    corrupt_retried.archived[Journal(base.ident, forward.ident, 1)] = "recovered"
    assert_refusal_without_write("pending with recovered attempt after current", "journal history collision",
                                 corrupt_retried, functools.partial(reconcile, corrupt_retried, keys, base.ident))
    corrupt_committed = copy.deepcopy(pending)
    corrupt_committed.archived[Journal(base.ident, forward.ident, 0)] = "committed"
    assert_refusal_without_write("pending with committed duplicate", "journal history collision", corrupt_committed,
                                 functools.partial(reconcile, corrupt_committed, keys, base.ident))
    corrupt_pending_history = copy.deepcopy(pending)
    corrupt_pending_history.archived[Journal(base.ident, alternate1.ident, 0)] = "recovered"
    corrupt_pending_history.generations[alternate1.ident] = alternate1
    corrupt_pending_history.generations[base.ident] = dataclasses.replace(base, release_sig=b"invalid")
    assert_refusal_without_write("pending with corrupt archive history", "journal history collision",
                                 corrupt_pending_history,
                                 functools.partial(reconcile, corrupt_pending_history, keys, base.ident))

    staged = State({base.ident: base, forward.ident: forward}, base.ident, list(base.payloads))
    for attempt in (cast(Any, -1), cast(Any, True), cast(Any, 1.5), cast(Any, "1")):
        state = copy.deepcopy(staged)
        state.journal_temp = Journal(base.ident, forward.ident, attempt)
        assert_refusal_without_write(f"journal temp attempt {attempt!r}", "unknown journal staging", state,
                                     functools.partial(boot_clean, state, keys, base.ident))
        assert_refusal_without_write(f"journal temp attempt {attempt!r} update", "unknown journal staging", state,
                                     functools.partial(update_plan, state, keys, base.ident, forward))
    state = copy.deepcopy(staged)
    state.journal_temp = Journal(base.ident, forward.ident, 0)
    assert boot_clean(state, keys, base.ident) == base.ident

    release_text = keys.release_signers.read_text()
    rollback_text = keys.rollback_signers.read_text()
    release_blob = release_text.split()[-1]
    rollback_blob = rollback_text.split()[-1]
    chain = {base.ident: base, forward.ident: forward}
    canonical_line = f'{ROLLBACK_PRINCIPAL} namespaces="{ROLLBACK_NS}" ssh-ed25519 {rollback_blob}\n'
    canonical_release_line = f'{RELEASE_PRINCIPAL} namespaces="{RELEASE_NS}" ssh-ed25519 {release_blob}\n'
    good_signers = keys.directory / "good-rollback.signers"
    good_signers.write_text(canonical_line)
    os.chmod(good_signers, 0o600)
    link = keys.directory / "link-rollback.signers"
    link.symlink_to(good_signers)
    hard = keys.directory / "hard-rollback.signers"
    os.link(good_signers, hard)
    for label, reason, signers, principal, namespace in (
        ("symlinked signers", "signers file", link, ROLLBACK_PRINCIPAL, ROLLBACK_NS),
        ("hardlinked signers", "signers file", hard, ROLLBACK_PRINCIPAL, ROLLBACK_NS),
        ("wrong principal", "signers file", good_signers, RELEASE_PRINCIPAL, ROLLBACK_NS),
        ("wrong namespace", "signers file", good_signers, ROLLBACK_PRINCIPAL, RELEASE_NS),
    ):
        expect_reject(label, reason, functools.partial(signer_key_material, signers, principal, namespace))
    expect_reject("namespace mismatch with release signer", "signers file", functools.partial(
        signer_key_material, keys.release_signers, RELEASE_PRINCIPAL, ROLLBACK_NS))
    link.unlink()
    hard.unlink()
    good_signers.unlink()

    def tampered(target: pathlib.Path, original: str, text: str, label: str, reason: str) -> None:
        target.write_text(text)
        try:
            expect_reject(label + " verify_entry", reason, functools.partial(
                verify_entry, keys, base.ident, rollback, forward, chain))
            fresh = State({base.ident: base}, base.ident, list(base.payloads))
            assert_refusal_without_write(label + " boot", reason, fresh,
                                         functools.partial(boot_clean, fresh, keys, base.ident))
            assert_refusal_without_write(label + " floor check", reason, fresh,
                                         functools.partial(floor.check, fresh, keys, base.ident))
            assert_refusal_without_write(label + " floor advance", reason, fresh,
                                         functools.partial(floor.advance, fresh, keys, base.ident))
        finally:
            target.write_text(original)

    same_key_formats = [
        ("comment and indentation", f'# note\n  {ROLLBACK_PRINCIPAL} namespaces="{ROLLBACK_NS}" ssh-ed25519 {release_blob}\n'),
        ("extra options", f'{ROLLBACK_PRINCIPAL} no-touch-required,namespaces="{ROLLBACK_NS}" ssh-ed25519 {release_blob}\n'),
        ("tabs and trailing space", f'{ROLLBACK_PRINCIPAL}\tnamespaces="{ROLLBACK_NS}"\tssh-ed25519\t{release_blob}  \n'),
        ("key comment", f'{ROLLBACK_PRINCIPAL} namespaces="{ROLLBACK_NS}" ssh-ed25519 {release_blob} release-copy\n'),
        ("missing trailing newline", canonical_line.rstrip("\n")),
        ("rollback principal under release namespace",
         f'{ROLLBACK_PRINCIPAL} namespaces="{RELEASE_NS}" ssh-ed25519 {rollback_blob}\n'),
        ("release principal", f'{RELEASE_PRINCIPAL} namespaces="{RELEASE_NS}" ssh-ed25519 {release_blob}\n'),
        ("no namespaces option", f"{ROLLBACK_PRINCIPAL} ssh-ed25519 {rollback_blob}\n"),
    ]
    for label, text in same_key_formats:
        tampered(keys.rollback_signers, rollback_text, text, "rollback signers same key, " + label,
                 "signers file")
    tampered(keys.rollback_signers, rollback_text, canonical_release_line,
             "rollback signers carrying release identity", "signers file")
    tampered(keys.release_signers, release_text,
             f'# note\n{RELEASE_PRINCIPAL} no-touch-required,namespaces="{RELEASE_NS}" ssh-ed25519 {rollback_blob}\n',
             "release signers carrying rollback key", "signers file")
    for label, text in (
        ("empty file", ""),
        ("two keys", rollback_text + release_text),
        ("rsa key type", f'{ROLLBACK_PRINCIPAL} namespaces="{ROLLBACK_NS}" ssh-rsa {rollback_blob}\n'),
        ("trailing comment field", canonical_line[:-1] + " note\n"),
        ("oversized signers", canonical_line + "#" * VERIFIER.SIGNERS_MAX),
        ("noncanonical base64", (f"{ROLLBACK_PRINCIPAL} namespaces=\"{ROLLBACK_NS}\" ssh-ed25519 "
                                 f"{rollback_blob}==\n")),
        ("unsupported key prefix",
         (f"{ROLLBACK_PRINCIPAL} namespaces=\"{ROLLBACK_NS}\" ssh-ed25519 "
          f"{base64.b64encode(b'x' + base64.b64decode(rollback_blob)[1:]).decode('ascii')}\n")),
    ):
        tampered(keys.rollback_signers, rollback_text, text, "rollback signers " + label, "signers file")
    assert keys.rollback_signers.read_text() == rollback_text and keys.release_signers.read_text() == release_text
    message = RELEASE_DOMAIN + b"armor probe"
    genuine = keys.sign(keys.release, RELEASE_NS, message)
    assert keys.verify(False, message, genuine)
    armor_payload = b"".join(genuine[len(VERIFIER.SSHSIG_BEGIN):-len(VERIFIER.SSHSIG_END)]
                             .rstrip(b"\n").split(b"\n"))
    for label, signature in (
        ("duplicate armor", genuine + genuine),
        ("repeated begin", VERIFIER.SSHSIG_BEGIN + armor_payload[:VERIFIER.SSHSIG_WRAP] + b"\n" +
         VERIFIER.SSHSIG_BEGIN + armor_payload[VERIFIER.SSHSIG_WRAP:] + b"\n" + VERIFIER.SSHSIG_END),
        ("armor with trailing whitespace", VERIFIER.SSHSIG_BEGIN +
         armor_payload + b" \n" + VERIFIER.SSHSIG_END),
        ("short final armor line", VERIFIER.SSHSIG_BEGIN + armor_payload[:VERIFIER.SSHSIG_WRAP - 1] +
         b"\n" + armor_payload[VERIFIER.SSHSIG_WRAP:] + b"\n" + VERIFIER.SSHSIG_END),
        ("blank line inside armor", VERIFIER.SSHSIG_BEGIN + armor_payload[:VERIFIER.SSHSIG_WRAP] + b"\n\n" +
         armor_payload[VERIFIER.SSHSIG_WRAP:] + b"\n" + VERIFIER.SSHSIG_END),
    ):
        assert not keys.verify(False, message, signature), "noncanonical armor accepted: " + label
    assert not keys.verify(False, message, genuine + b"trailing")
    assert keys.verify(False, message, genuine)
    verify_entry(keys, base.ident, rollback, forward, verify_chain(keys, base.ident, chain, forward.ident))
    print(f"archive history: {len(corrupt_histories) + 4} corrupt or unknown committed/recovered histories refused "
          "on journal-free boot, floor check and floor advance; recovered-before-committed attempts, an unreached "
          "committed branch, rewound-selector histories and pending recovery with consistent history accepted; "
          "negative, boolean, float and string journal-temp attempts refused")
    print(f"post-plan archive: {post_plan_refusals} corrupt histories inserted after plan construction refused by "
          "consult itself and by the first guarded action, without writes")
    print("signer roles: release and rollback allowed-signers files must authorize different ed25519 key "
          f"material; {len(same_key_formats) + 2} same-key reformatting/tampering vectors, 7 malformed or "
          "foreign-format signer vectors, symlinked/hardlinked signers and wrong principal/namespace lookups "
          "refused on verify_entry, boot, floor check and floor advance")
    print("signer scope: model delegates allowed-signers loading and ssh-signature parsing to "
          "verify-root-generation-bundle.py, so it enforces that verifier's strict canonical single-key "
          "ed25519 line and pinned-namespace sshsig armor; it does not validate ssh-keygen option semantics, "
          "certificates, expiry or revocation, nor that signers files are the operational trust anchor")


def legacy_rel(path: str) -> str:
    return path.lstrip("/")


def legacy_write_tree(slot: pathlib.Path, gen: Generation) -> None:
    slot.mkdir(mode=0o700)
    for path, data in zip(PATHS, gen.payloads):
        target = slot / legacy_rel(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o700)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    for name, data in (("manifest", gen.raw), ("release.sig", gen.release_sig)):
        (slot / name).write_bytes(data)
        os.chmod(slot / name, 0o600)
    for current, _, _ in os.walk(slot):
        os.chmod(current, 0o700)


def legacy_regular(path: pathlib.Path, mode: int, label: str) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        refuse(f"{label} symlink")
    if not stat.S_ISREG(info.st_mode):
        refuse(f"{label} not a regular file")
    if info.st_nlink != 1:
        refuse(f"{label} hard links")
    if stat.S_IMODE(info.st_mode) != mode:
        refuse(f"{label} mode")
    return path.read_bytes()


def legacy_verify_tree(keys: Keys, slot: pathlib.Path) -> str:
    try:
        return legacy_verify_tree_unchecked(keys, slot)
    except OSError as exc:
        refuse(f"slot unreadable or incomplete: {type(exc).__name__}")


def legacy_verify_tree_unchecked(keys: Keys, slot: pathlib.Path) -> str:
    root_info = slot.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or root_info.st_mode & 0o022:
        refuse("unsafe slot directory")
    raw = legacy_regular(slot / "manifest", 0o600, "manifest")
    obj = parse_manifest(raw)
    if not keys.verify(False, RELEASE_DOMAIN + raw, legacy_regular(slot / "release.sig", 0o600, "signature")):
        refuse("release signature")
    expected_files = {legacy_rel(path) for path in PATHS}
    allowed_files = expected_files | {"manifest", "release.sig"}
    folded = {name.casefold() for name in allowed_files}
    expected_dirs: set[str] = set()
    for rel in expected_files:
        parent = pathlib.PurePosixPath(rel).parent
        while str(parent) != ".":
            expected_dirs.add(str(parent))
            parent = parent.parent
    for current, directories, filenames in os.walk(slot, followlinks=False):
        base = pathlib.Path(current)
        for directory in directories:
            full = base / directory
            if full.is_symlink():
                refuse("symlinked directory")
            if full.relative_to(slot).as_posix() not in expected_dirs:
                refuse("unexpected directory " + full.relative_to(slot).as_posix())
            if full.lstat().st_mode & 0o022:
                refuse("writable directory")
        for filename in filenames:
            rel = (base / filename).relative_to(slot).as_posix()
            if rel not in allowed_files:
                if rel.casefold() in folded:
                    refuse("case collision " + rel)
                refuse("unknown or colliding file " + rel)
    for entry in obj["files"]:
        data = legacy_regular(slot / legacy_rel(entry["path"]), 0o700, entry["path"])
        if len(data) != entry["size"]:
            refuse(entry["path"] + " size mismatch")
        if digest(data) != entry["sha256"]:
            refuse(entry["path"] + " digest mismatch")
    return digest(raw)


def legacy_read_selector(path: pathlib.Path, known: set[str]) -> str:
    try:
        value = legacy_regular(path, 0o600, "selector")
    except OSError as exc:
        refuse(f"selector unreadable: {type(exc).__name__}")
    ident = value[:-1].decode("ascii", "replace")
    if len(value) != 65 or not value.endswith(b"\n") or not is_id(ident):
        refuse("selector format")
    if ident not in known:
        refuse("selector unknown generation")
    return ident


def legacy_assert_separate(anchor: pathlib.Path, store: pathlib.Path) -> None:
    left = anchor.resolve()
    right = store.resolve()
    if left.is_relative_to(right) or right.is_relative_to(left):
        refuse("trust anchor and mutable store overlap")


def legacy_parse_attestation(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 4096:
        refuse("attestation size")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in items}) != len(items):
            refuse("attestation duplicate key")
        return dict(items)

    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        refuse("attestation encoding or JSON")
    if canonical(value) != raw:
        refuse("attestation not canonical")
    if not isinstance(value, dict) or list(value) != ["type", "boot_pins", "files"]:
        refuse("attestation fields")
    if value["type"] != "pre-ssh-image":
        refuse("attestation type")
    pins = value["boot_pins"]
    if not isinstance(pins, dict) or list(pins) != list(RUN113_PINS) or not all(map(is_id, pins.values())):
        refuse("attestation boot pins")
    files = value["files"]
    if not isinstance(files, dict) or list(files) != list(PATHS) or not all(map(is_id, files.values())):
        refuse("attestation files")
    if BAD_RADIO in files.values():
        refuse("attestation denylisted digest")
    return value


class LegacyPolicy:
    def __init__(self, keys: Keys, base_pins: dict[str, str], base_files: dict[str, str], name: str) -> None:
        self.keys = keys
        self.base_pins = dict(base_pins)
        self.base_files = dict(base_files)
        self.key, self.signers = keys.make_key(name, LEGACY_IMAGE_PRINCIPAL, LEGACY_IMAGE_NS)
        self.attested: list[tuple[dict[str, str], dict[str, str]]] = []

    def sign(self, message: bytes, key: pathlib.Path | None = None, namespace: str = LEGACY_IMAGE_NS,
             domain: bytes = LEGACY_IMAGE_DOMAIN) -> bytes:
        return self.keys.sign(key or self.key, namespace, domain + message)

    def verify(self, message: bytes, signature: bytes) -> bool:
        with tempfile.TemporaryDirectory(dir=self.keys.directory) as tmp:
            target = pathlib.Path(tmp) / "signature"
            target.write_bytes(signature)
            result = run(["ssh-keygen", "-Y", "verify", "-f", str(self.signers), "-I", LEGACY_IMAGE_PRINCIPAL,
                          "-n", LEGACY_IMAGE_NS, "-s", str(target)], LEGACY_IMAGE_DOMAIN + message)
            return result.returncode == 0

    def accept(self, raw: bytes, signature: bytes) -> None:
        value = legacy_parse_attestation(raw)
        if not self.verify(raw, signature):
            refuse("attestation signature")
        if value["boot_pins"] == self.base_pins:
            refuse("attestation does not describe a changed image")
        self.attested.append((value["boot_pins"], value["files"]))

    def check(self, pins: dict[str, str], files: dict[str, str]) -> None:
        if BAD_RADIO in files.values():
            refuse("denylisted file digest")
        if pins == self.base_pins:
            if files != self.base_files:
                refuse("userdata manifest cannot change files enforced by the installed image")
            return
        if (pins, files) not in self.attested:
            refuse("changed boot pins and files lack an independent image attestation")


def legacy_files(gen: Generation) -> dict[str, str]:
    return {entry["path"]: entry["sha256"] for entry in parse_manifest(gen.raw)["files"]}


def legacy_pinned_manifest(digests: dict[str, str]) -> bytes:
    entries = [{"path": path, "size": 1, "sha256": digests[path], "uid": 0, "gid": 0, "mode": "0700"}
               for path in PATHS]
    return canonical({"schema": SCHEMA, "sequence": 0, "operation": "baseline", "previous": None,
                      "files": entries, "restores": None})


def constant_assignments(path: pathlib.Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node.value.value
    return result


def test_legacy_run113_pins(keys: Keys, base: Generation, forward: Generation) -> None:
    source = pathlib.Path(__file__).resolve().parent
    builder_assigns = constant_assignments(source / "build-init-boot-persistent-root.py")
    assert builder_assigns["FRESH_RADIO_SHA"] == RUN113_FILES[PATHS[0]]
    assert builder_assigns["GATED_POST_SHA"] == RUN113_FILES[PATHS[1]]
    assert builder_assigns["GATED_HOOK_SHA"] == RUN113_FILES[PATHS[2]]

    candidate_assigns = constant_assignments(source / "build-init-boot-route-cache-candidate.py")
    assert candidate_assigns["RUN113_INIT"] == RUN113_PINS["init_boot_sha256"]
    assert candidate_assigns["RUN113_CARRIER"] == RUN113_PINS["vendor_boot_b_sha256"]

    assert BAD_RADIO not in RUN113_FILES.values() and BAD_RADIO not in RUN113_PINS.values()
    assert len(set(RUN113_FILES.values()) | set(RUN113_PINS.values())) == 5
    assert parse_manifest(legacy_pinned_manifest(RUN113_FILES))["files"][1]["sha256"] == RUN113_FILES[PATHS[1]]
    for path in PATHS:
        expect_reject("bad radio at " + path, "file digest", functools.partial(
            parse_manifest, legacy_pinned_manifest({**RUN113_FILES, path: BAD_RADIO})))

    policy = LegacyPolicy(keys, RUN113_PINS, RUN113_FILES, "legacy-image-run113")
    policy.check(RUN113_PINS, RUN113_FILES)
    changed_files = {path: digest(path.encode()) for path in PATHS}
    for path in PATHS:
        expect_reject("userdata-only change " + path, "enforced by the installed image", functools.partial(
            policy.check, RUN113_PINS, {**RUN113_FILES, path: changed_files[path]}))
    new_pins = {"init_boot_sha256": digest(b"new init"), "vendor_boot_b_sha256": digest(b"new vendor")}
    for name in RUN113_PINS:
        expect_reject("single changed pin " + name, "independent image attestation", functools.partial(
            policy.check, {**RUN113_PINS, name: new_pins[name]}, RUN113_FILES))
    expect_reject("unattested changed image", "independent image attestation",
                  functools.partial(policy.check, new_pins, changed_files))
    expect_reject("bad radio with run-113 pins", "denylisted file digest", functools.partial(
        policy.check, RUN113_PINS, {**RUN113_FILES, PATHS[0]: BAD_RADIO}))
    expect_reject("bad radio with changed pins", "denylisted file digest", functools.partial(
        policy.check, new_pins, {**changed_files, PATHS[0]: BAD_RADIO}))

    attestation = canonical({"type": "pre-ssh-image", "boot_pins": new_pins, "files": changed_files})
    wrong_signatures = [
        ("release key in image namespace", policy.sign(attestation, keys.release)),
        ("release key in release namespace", policy.sign(attestation, keys.release, RELEASE_NS, RELEASE_DOMAIN)),
        ("rollback key", policy.sign(attestation, keys.rollback)),
        ("image key release namespace", policy.sign(attestation, None, RELEASE_NS)),
        ("image key release domain", policy.sign(attestation, None, LEGACY_IMAGE_NS, RELEASE_DOMAIN)),
        ("image key no domain", policy.sign(attestation, None, LEGACY_IMAGE_NS, b"")),
        ("truncated", policy.sign(attestation)[:-8]),
        ("empty", b""),
    ]
    for label, signature in wrong_signatures:
        expect_reject(label, "attestation signature", functools.partial(policy.accept, attestation, signature))
    genuine = policy.sign(attestation)
    other_pins = canonical({"type": "pre-ssh-image", "boot_pins": {**new_pins, "init_boot_sha256": digest(b"other")},
                            "files": changed_files})
    expect_reject("signature over other document", "attestation signature",
                  functools.partial(policy.accept, other_pins, genuine))
    unchanged = canonical({"type": "pre-ssh-image", "boot_pins": RUN113_PINS, "files": changed_files})
    expect_reject("unchanged image", "does not describe a changed image",
                  functools.partial(policy.accept, unchanged, policy.sign(unchanged)))
    base_doc: dict[str, Any] = {"type": "pre-ssh-image", "boot_pins": new_pins, "files": changed_files}
    malformed = [
        ("extra field", "attestation fields", canonical({**base_doc, "extra": 1})),
        ("missing field", "attestation fields", canonical({"type": "pre-ssh-image", "boot_pins": new_pins})),
        ("wrong type", "attestation type", canonical({**base_doc, "type": "image"})),
        ("short pin", "attestation boot pins", canonical({**base_doc, "boot_pins": {**new_pins, "init_boot_sha256": "ab"}})),
        ("extra pin", "attestation boot pins", canonical({**base_doc, "boot_pins": {**new_pins, "x": "0" * 64}})),
        ("unknown file", "attestation files", canonical({**base_doc, "files": {**changed_files, "/x": "0" * 64}})),
        ("reordered files", "attestation files", canonical({**base_doc, "files": dict(reversed(list(changed_files.items())))})),
        ("bad radio file", "attestation denylisted digest", canonical({**base_doc, "files": {**changed_files, PATHS[1]: BAD_RADIO}})),
        ("non canonical", "attestation not canonical", json.dumps(base_doc, indent=1).encode()),
        ("duplicate key", "attestation duplicate key", attestation.replace(b'"type":"pre-ssh-image"', b'"type":"pre-ssh-image","type":"pre-ssh-image"')),
        ("not json", "attestation encoding", b"not json"),
        ("empty", "attestation size", b""),
        ("oversize", "attestation size", b" " * 4097),
    ]
    for label, reason, raw in malformed:
        expect_reject(label, reason, functools.partial(policy.accept, raw, policy.sign(raw)))
    assert not policy.attested
    expect_reject("still unattested", "independent image attestation", functools.partial(policy.check, new_pins, changed_files))

    mismatch = canonical({"type": "pre-ssh-image", "boot_pins": new_pins, "files": RUN113_FILES})
    policy.accept(mismatch, policy.sign(mismatch))
    expect_reject("attested pins with different files", "independent image attestation",
                  functools.partial(policy.check, new_pins, changed_files))
    policy.accept(attestation, genuine)
    policy.check(new_pins, changed_files)
    swapped = {"init_boot_sha256": new_pins["vendor_boot_b_sha256"], "vendor_boot_b_sha256": new_pins["init_boot_sha256"]}
    expect_reject("swapped attested pins", "independent image attestation",
                  functools.partial(policy.check, swapped, changed_files))
    expect_reject("attested pins with run-113 pin reverted", "independent image attestation", functools.partial(
        policy.check, {**new_pins, "init_boot_sha256": RUN113_PINS["init_boot_sha256"]}, changed_files))
    expect_reject("attested files under run-113 pins", "enforced by the installed image",
                  functools.partial(policy.check, RUN113_PINS, changed_files))

    fixture_policy = LegacyPolicy(keys, RUN113_PINS, legacy_files(base), "legacy-image-fixture")
    fixture_policy.check(RUN113_PINS, legacy_files(base))
    expect_reject("signed forward under installed pins", "enforced by the installed image",
                  functools.partial(fixture_policy.check, RUN113_PINS, legacy_files(forward)))
    image_signed = dataclasses.replace(forward, release_sig=fixture_policy.sign(
        forward.raw, None, RELEASE_NS, RELEASE_DOMAIN))
    expect_reject("image key as release signer", "release signature", functools.partial(
        verify_entry, keys, base.ident, image_signed, base, {base.ident: base}))
    forward_attestation = canonical({"type": "pre-ssh-image", "boot_pins": new_pins, "files": legacy_files(forward)})
    fixture_policy.accept(forward_attestation, fixture_policy.sign(forward_attestation))
    fixture_policy.check(new_pins, legacy_files(forward))
    print(f"legacy-fixture run-113 pins: {len(PATHS) * 3 + 2} digest and policy vectors, "
          f"{len(wrong_signatures) + len(malformed) + 3} attestation vectors refused; "
          "pin constants cross-checked against builder sources")
    print("legacy-fixture scope: encodes the installed run-113 pair's refusal to change pinned files and an "
          "image-signer attestation predicate; the abstract signed-generation model above presupposes a "
          "not-yet-built replacement bootstrap and does not prove either")


def test_legacy_trust_anchor(keys: Keys, base: Generation, workdir: pathlib.Path) -> None:
    root = workdir / "legacy-anchor"
    anchor = root / "anchor"
    store = root / "store"
    anchor.mkdir(parents=True)
    store.mkdir()
    legacy_assert_separate(anchor, store)
    (store / "inner-anchor").mkdir()
    (root / "link-into-store").symlink_to(store / "inner-anchor")
    (anchor / "inner-store").mkdir()
    overlaps = [
        ("anchor inside store", store / "inner-anchor", store),
        ("anchor equals store", store, store),
        ("anchor via symlink into store", root / "link-into-store", store),
        ("anchor via dot-dot into store", store / "inner-anchor" / ".." / "inner-anchor", store),
        ("store inside anchor", anchor, anchor / "inner-store"),
        ("store above anchor", root, anchor),
    ]
    for label, anchor_path, store_path in overlaps:
        expect_reject(label, "overlap", functools.partial(legacy_assert_separate, anchor_path, store_path))

    attacker_dir = store / "attacker"
    attacker_dir.mkdir()
    attacker = Keys(attacker_dir)
    forged_base = make_generation(attacker, 0, "baseline", None, None, payloads("baseline"))
    assert forged_base.raw == base.raw and forged_base.ident == base.ident
    assert forged_base.release_sig != base.release_sig
    expect_reject("store-local release key", "release signature",
                  functools.partial(verify_entry, keys, base.ident, forged_base, None, {}))
    forged_forward = make_generation(attacker, 1, "forward", base.ident, None, payloads("attacker"))
    expect_reject("store-local forward", "release signature", functools.partial(
        verify_entry, keys, base.ident, forged_forward, base, {base.ident: base}))
    expect_reject("store-local chain", "release signature", functools.partial(
        verify_chain, keys, base.ident, {base.ident: base, forged_forward.ident: forged_forward}, forged_forward.ident))
    forged_rollback = make_generation(attacker, 2, "rollback", forged_forward.ident, base.ident, base.payloads)
    expect_reject("store-local rollback", "release signature", functools.partial(
        verify_entry, keys, base.ident, forged_rollback, forged_forward, {base.ident: base}))
    anchor_rollback = dataclasses.replace(forged_rollback, release_sig=keys.sign(
        keys.release, RELEASE_NS, RELEASE_DOMAIN + forged_rollback.raw))
    expect_reject("trusted release key with store-local rollback key", "rollback signature", functools.partial(
        verify_entry, keys, base.ident, anchor_rollback, forged_forward, {base.ident: base}))

    slot = store / "slot"
    legacy_write_tree(slot, forged_base)
    expect_reject("tree signed by store-local key", "release signature", functools.partial(legacy_verify_tree, keys, slot))
    shutil.rmtree(slot)
    legacy_write_tree(slot, base)
    shutil.copy(attacker.release_signers, slot / "allowed_signers")
    expect_reject("store-local signer file", "unknown or colliding file", functools.partial(legacy_verify_tree, keys, slot))
    os.unlink(slot / "allowed_signers")
    assert legacy_verify_tree(keys, slot) == base.ident
    print(f"legacy-fixture trust anchor: {len(overlaps)} anchor/store overlaps and 7 store-local signer "
          "forgeries refused; verification used only the externally supplied signers")


def test_legacy_tree(keys: Keys, base: Generation, forward: Generation, workdir: pathlib.Path) -> None:
    root = workdir / "legacy-tree"
    root.mkdir(mode=0o700)
    slot = root / "slot"
    legacy_write_tree(slot, base)
    assert legacy_verify_tree(keys, slot) == base.ident
    pristine = {path: (slot / legacy_rel(path)).read_bytes() for path in PATHS}
    first, second, third = (slot / legacy_rel(path) for path in PATHS)
    outside = root / "outside.bin"
    outside.write_bytes(pristine[PATHS[0]])
    os.chmod(outside, 0o700)
    outside_manifest = root / "outside-manifest"
    outside_manifest.write_bytes(base.raw)
    os.chmod(outside_manifest, 0o600)
    outside_usr = root / "outside-usr"
    shutil.copytree(slot / "usr", outside_usr, symlinks=True)
    alias = root / "alias"
    attacker_dir = root / "attacker"
    attacker_dir.mkdir()
    attacker = Keys(attacker_dir)
    attacker_base = make_generation(attacker, 0, "baseline", None, None, payloads("baseline"))

    def restore() -> None:
        shutil.rmtree(slot)
        if alias.exists():
            alias.unlink()
        legacy_write_tree(slot, base)
        assert legacy_verify_tree(keys, slot) == base.ident
        assert pristine == {path: (slot / legacy_rel(path)).read_bytes() for path in PATHS}

    def unlink_then(path: pathlib.Path, action: Callable[[], Any]) -> Callable[[], None]:
        def run_action() -> None:
            path.unlink()
            action()
        return run_action

    def swap_usr() -> None:
        shutil.rmtree(slot / "usr")
        (slot / "usr").symlink_to(outside_usr)

    def swap_payloads() -> None:
        first_data, second_data = first.read_bytes(), second.read_bytes()
        first.write_bytes(second_data)
        second.write_bytes(first_data)

    def replace_manifest_with_link() -> None:
        (slot / "manifest").unlink()
        (slot / "manifest").symlink_to(outside_manifest)

    def replace_with_attacker() -> None:
        (slot / "manifest").write_bytes(attacker_base.raw)
        (slot / "release.sig").write_bytes(attacker_base.release_sig)

    def replace_with_forward() -> None:
        (slot / "manifest").write_bytes(forward.raw)
        (slot / "release.sig").write_bytes(forward.release_sig)

    def make_fifo() -> None:
        first.unlink()
        os.mkfifo(first, 0o700)

    mutations: list[tuple[str, str, Callable[[], Any]]] = [
        ("missing manifest", "incomplete", lambda: (slot / "manifest").unlink()),
        ("corrupt manifest", "manifest", lambda: (slot / "manifest").write_bytes(base.raw[:-5])),
        ("symlinked manifest", "manifest symlink", replace_manifest_with_link),
        ("loosened manifest mode", "manifest mode", lambda: os.chmod(slot / "manifest", 0o666)),
        ("missing signature", "incomplete", lambda: (slot / "release.sig").unlink()),
        ("corrupt signature", "release signature", lambda: (slot / "release.sig").write_bytes(
            b"-----BEGIN SSH SIGNATURE-----\n")),
        ("empty signature", "release signature", lambda: (slot / "release.sig").write_bytes(b"")),
        ("store-local signature", "release signature", replace_with_attacker),
        ("replayed generation metadata", "mismatch", replace_with_forward),
        ("missing payload", "incomplete", lambda: first.unlink()),
        ("truncated payload", "size mismatch", lambda: second.write_bytes(pristine[PATHS[1]][:-1])),
        ("same size flipped payload", "digest mismatch", lambda: third.write_bytes(pristine[PATHS[2]][:-1] + b"X")),
        ("other generation payload", "mismatch", lambda: first.write_bytes(forward.payloads[0])),
        ("swapped payloads", "mismatch", swap_payloads),
        ("loosened mode", "mode", lambda: os.chmod(first, 0o755)),
        ("setuid mode", "mode", lambda: os.chmod(first, 0o4700)),
        ("group writable parent", "writable directory", lambda: os.chmod(slot / "usr", 0o770)),
        ("world writable nested parent", "writable directory", lambda: os.chmod(slot / "etc" / "local.d", 0o707)),
        ("group writable slot", "unsafe slot directory", lambda: os.chmod(slot, 0o770)),
        ("symlinked payload", "symlink", unlink_then(first, lambda: first.symlink_to(outside))),
        ("dangling symlinked payload", "symlink", unlink_then(first, lambda: first.symlink_to(root / "missing"))),
        ("hard linked payload", "hard links", unlink_then(first, lambda: os.link(outside, first))),
        ("outside alias of payload", "hard links", lambda: os.link(first, alias)),
        ("inside alias of payload", "unknown or colliding file", lambda: os.link(first, slot / "etc" / "local.d" / "alias")),
        ("directory in place of file", "unexpected directory", unlink_then(third, third.mkdir)),
        ("fifo in place of file", "not a regular file", make_fifo),
        ("symlinked directory", "symlinked directory", swap_usr),
        ("unknown extra file", "unknown or colliding file", lambda: (slot / "extra").write_bytes(b"x")),
        ("unknown extra directory", "unexpected directory", lambda: (slot / "extra").mkdir()),
        ("staging name collision", "unknown or colliding file", lambda: pathlib.Path(
            str(first) + ".omnipha-new").write_bytes(b"x")),
        ("case collision", "case collision", lambda: (
            slot / "etc" / "local.d" / "10-OMNIPHA-SELF-STAGE.START").write_bytes(pristine[PATHS[2]])),
        ("case collision manifest", "case collision", lambda: (slot / "MANIFEST").write_bytes(base.raw)),
    ]
    for label, reason, mutate in mutations:
        mutate()
        expect_reject(label, reason, functools.partial(legacy_verify_tree, keys, slot))
        restore()

    selector = root / "selector"
    known = {base.ident, forward.ident}

    def write_selector(value: bytes) -> None:
        if selector.is_symlink() or selector.is_file():
            selector.unlink()
        elif selector.exists():
            selector.rmdir()
        selector.write_bytes(value)
        os.chmod(selector, 0o600)

    def selector_link() -> None:
        selector.unlink()
        selector.symlink_to(outside)

    def selector_hardlink() -> None:
        selector.unlink()
        os.link(outside_manifest, selector)

    def selector_directory() -> None:
        selector.unlink()
        selector.mkdir()

    good = base.ident.encode() + b"\n"
    write_selector(good)
    assert legacy_read_selector(selector, known) == base.ident
    selector_cases: list[tuple[str, str, Callable[[], Any]]] = [
        ("garbage", "selector format", lambda: write_selector(b"C\n")),
        ("empty", "selector format", lambda: write_selector(b"")),
        ("two ids", "selector format", lambda: write_selector(good + forward.ident.encode() + b"\n")),
        ("no newline", "selector format", lambda: write_selector(good[:-1])),
        ("crlf", "selector format", lambda: write_selector(good[:-1] + b"\r\n")),
        ("uppercase", "selector format", lambda: write_selector(base.ident.upper().encode() + b"\n")),
        ("unknown generation", "selector unknown generation", lambda: write_selector(b"f" * 64 + b"\n")),
        ("loosened mode", "selector mode", lambda: os.chmod(selector, 0o644)),
        ("symlink", "selector symlink", selector_link),
        ("hard link", "selector hard links", selector_hardlink),
        ("directory", "selector not a regular file", selector_directory),
    ]
    for label, reason, mutate in selector_cases:
        mutate()
        expect_reject("selector " + label, reason, functools.partial(legacy_read_selector, selector, known))
        write_selector(good)
        assert legacy_read_selector(selector, known) == base.ident
    print(f"legacy-fixture tree: {len(mutations)} symlink/hardlink/mode/collision/replacement mutations and "
          f"{len(selector_cases)} selector mutations refused; slot restored whole after each")
    print("legacy-fixture caveat: unprivileged host directories, path-based lstat checks with reopen races, "
          "no root ownership, ACL, capability, mount, fsync or case-insensitive filesystem coverage")


def test_gap_documentation(keys: Keys, initial: State, base: Generation, forward: Generation,
                           rollback: Generation) -> None:
    aborted = copy.deepcopy(initial)
    plan = update_plan(aborted, keys, base.ident, forward)
    execute(plan, next(i for i, (name, _) in enumerate(plan) if name == "publish journal without replacement") + 1)
    assert reconcile(aborted, keys, base.ident) == base.ident
    retry_plan = update_plan(aborted, keys, base.ident, forward)
    assert any(name == "write journal" for name, _ in retry_plan)
    assert not any(name == "publish generation without replacement" for name, _ in retry_plan)
    execute(retry_plan)
    assert reconcile(aborted, keys, base.ident) == forward.ident

    repeated = copy.deepcopy(initial)
    for cut_name in ("publish journal without replacement", "update rename selector"):
        plan = update_plan(repeated, keys, base.ident, forward)
        execute(plan, next(i for i, (name, _) in enumerate(plan) if name == cut_name) + 1)
        assert reconcile(repeated, keys, base.ident) == base.ident
    execute(update_plan(repeated, keys, base.ident, forward))
    assert reconcile(repeated, keys, base.ident) == forward.ident

    refused_retries = 0
    accepted_retries = 0
    recovered = copy.deepcopy(initial)
    first = update_plan(recovered, keys, base.ident, forward)
    execute(first, next(i for i, (name, _) in enumerate(first)
                        if name == "publish journal without replacement") + 1)
    assert reconcile(recovered, keys, base.ident) == base.ident
    total = len(update_plan(copy.deepcopy(recovered), keys, base.ident, forward))
    for cut in range(total + 1):
        view = copy.deepcopy(recovered)
        execute(update_plan(view, keys, base.ident, forward), cut)
        if view.journal is None:
            continue
        assert reconcile(view, keys, base.ident) == base.ident
        if view.fixed_temps or view.selector_temps:
            assert_refusal_without_write(f"retry after cut {cut}", "staging collision", view,
                                         functools.partial(update_plan, view, keys, base.ident, forward))
            refused_retries += 1
        else:
            execute(update_plan(view, keys, base.ident, forward))
            assert reconcile(view, keys, base.ident) == forward.ident
            accepted_retries += 1
    assert refused_retries and accepted_retries

    durable = copy.deepcopy(initial)
    execute(update_plan(durable, keys, base.ident, forward))
    next_plan = update_plan(durable, keys, base.ident, rollback)
    archive_at = next(i for i, (name, _) in enumerate(next_plan)
                      if name == "archive journal without replacement")
    execute(next_plan, archive_at + 1)
    assert durable.unsynced_archive is not None and durable.selector == rollback.ident
    assert_refusal_without_write("update before archive sync", "journal archive not durable", durable,
                                 functools.partial(update_plan, durable, keys, base.ident, forward))
    before = copy.deepcopy(durable)
    assert reconcile(durable, keys, base.ident) == rollback.ident and durable == before
    print(f"retries: journal-publish and selector-rename cuts recovered and then committed; "
          f"{refused_retries} fixed or selector staging cuts refuse another update, and no cleanup is modeled")
    print("archive durability: an unsynced committed archive blocks the next update but not a journal-free boot; "
          "no device-level durability is modeled")


def test_trusted_floor(keys: Keys, base: Generation, forward: Generation, rollback: Generation) -> None:
    floor = TrustedFloor(0, base.ident)
    initial = State({base.ident: base}, base.ident, list(base.payloads))
    store = copy.deepcopy(initial)
    assert floor.check(store, keys, base.ident) == base.ident
    execute(update_plan(store, keys, base.ident, forward))
    floor.advance(store, keys, base.ident)
    assert (floor.sequence, floor.ident) == (1, forward.ident)
    downgraded = copy.deepcopy(store)
    downgraded.selector = base.ident
    downgraded.fixed = list(base.payloads)
    assert_refusal_without_write("selector downgrade", "below trusted floor", downgraded,
                                 lambda: floor.check(downgraded, keys, base.ident))
    assert_refusal_without_write("whole-store rewind", "below trusted floor", initial,
                                 lambda: floor.check(initial, keys, base.ident))
    invalid = dataclasses.replace(rollback, rollback_sig=None)
    assert_refusal_without_write("unauthorized rollback", "missing rollback signature", store,
                                 lambda: update_plan(store, keys, base.ident, invalid))
    assert (floor.sequence, floor.ident) == (1, forward.ident)
    execute(update_plan(store, keys, base.ident, rollback))
    floor.advance(store, keys, base.ident)
    assert (floor.sequence, floor.ident) == (2, rollback.ident)
    assert rollback.ident not in (base.ident, forward.ident) and rollback.payloads == base.payloads
    assert rollback.rollback_sig is not None and rollback.rollback_sig != rollback.release_sig
    rewind = copy.deepcopy(store)
    rewind.selector = base.ident
    assert_refusal_without_write("same-bytes selector rewind", "below trusted floor", rewind,
                                 lambda: floor.check(rewind, keys, base.ident))
    expect_reject("floor cannot regress", "below trusted floor", lambda: floor.advance(initial, keys, base.ident))
    assert (floor.sequence, floor.ident) == (2, rollback.ident)
    alternate = make_generation(keys, 1, "forward", base.ident, None, payloads("alternate"))
    alternate_next = make_generation(keys, 2, "forward", alternate.ident, None, payloads("alternate next"))
    fork = State({g.ident: g for g in (base, alternate, alternate_next)}, alternate_next.ident,
                 list(alternate_next.payloads))
    assert_refusal_without_write("signed fork", "trusted checkpoint", fork,
                                 lambda: floor.check(fork, keys, base.ident))
    for label, reason, bad in (
        ("negative sequence", "invalid trusted floor", TrustedFloor(-1, forward.ident)),
        ("malformed identifier", "invalid trusted floor", TrustedFloor(1, "zz")),
        ("sequence and identifier disagree", "trusted floor mismatch", TrustedFloor(0, forward.ident)),
    ):
        candidate_store = copy.deepcopy(store)
        assert_refusal_without_write("floor " + label, reason, candidate_store,
                                     functools.partial(update_plan, candidate_store, keys, base.ident, rollback, bad))
    pending = State({base.ident: base, forward.ident: forward}, forward.ident, list(forward.payloads))
    recovery_floor = TrustedFloor(1, forward.ident)
    plan = update_plan(pending, keys, base.ident, rollback, recovery_floor)
    execute(plan, next(i for i, (name, _) in enumerate(plan)
                       if name == "publish journal without replacement") + 1)
    assert pending.journal is not None
    assert_refusal_without_write("pending journal below floor", "below trusted floor", pending,
                                 lambda: reconcile(pending, keys, base.ident, floor))

    blocked = State({base.ident: base, forward.ident: forward}, forward.ident, list(forward.payloads))
    assert_refusal_without_write("update below floor", "below trusted floor", blocked,
                                 lambda: update_plan(blocked, keys, base.ident, rollback, floor))
    recovered_pending = copy.deepcopy(pending)
    assert reconcile(recovered_pending, keys, base.ident, recovery_floor) == forward.ident
    assert recovered_pending.journal is None and recovered_pending.unsynced_archive is None

    guarded_cuts = 0
    advanced = make_generation(keys, 3, "forward", rollback.ident, None, payloads("advanced"))
    advanced_store = State({g.ident: g for g in (base, forward, rollback, advanced)}, advanced.ident,
                           list(advanced.payloads))
    sources: list[tuple[str, State, Callable[[State, TrustedFloor], list[Action]]]] = [
        ("update", State({base.ident: base, forward.ident: forward}, forward.ident, list(forward.payloads)),
         lambda s, f: update_plan(s, keys, base.ident, rollback, f)),
        ("recovery", copy.deepcopy(pending), lambda s, f: recovery_plan(s, keys, base.ident, f)),
    ]
    for label, source, build in sources:
        total = len(build(copy.deepcopy(source), TrustedFloor(1, forward.ident)))
        for step in range(total):
            live = copy.deepcopy(source)
            live_floor = TrustedFloor(1, forward.ident)
            plan = build(live, live_floor)
            execute(plan, step)
            live_floor.advance(advanced_store, keys, base.ident)
            assert_refusal_without_write(f"{label} step {step} after floor advance", "below trusted floor", live,
                                         plan[step][1])
            guarded_cuts += 1
    settled = copy.deepcopy(pending)
    settled_floor = TrustedFloor(1, forward.ident)
    assert reconcile(settled, keys, base.ident, settled_floor) == forward.ident
    settled_floor.advance(advanced_store, keys, base.ident)
    assert_refusal_without_write("post-recovery boot below floor", "below trusted floor", settled,
                                 lambda: reconcile(settled, keys, base.ident, settled_floor))
    assert_refusal_without_write("post-recovery update below floor", "below trusted floor", settled,
                                 lambda: update_plan(settled, keys, base.ident, rollback, settled_floor))
    after_recovery = update_plan(settled, keys, base.ident, rollback)
    assert any(name == "write journal" for name, _ in after_recovery)

    floorless = copy.deepcopy(store)
    floorless.selector = base.ident
    floorless.fixed = list(base.payloads)
    assert reconcile(floorless, keys, base.ident) == base.ident
    print("synthetic external monotonic floor, supplied explicitly and checked before each guarded publication "
          "or recovery action: downgrade, store rewind, pending-journal rewinds and fork refused before that "
          f"step wrote without failing the preflight; {guarded_cuts} guarded cuts (including no-op sync "
          "steps) each refused before their guarded step wrote; distinct dual-key rollback advances floor "
          "from 1 to 2")
    print("floor caveat: boot and reconcile do not consult the floor unless a caller supplies it; an unsynced "
          "archive blocks update, recovery and floor advancement but not a journal-free boot; recognized, "
          "isolated and safe-metadata stage flags are model booleans with no derived evidence; advancing "
          "assumes an atomically durable external checkpoint and no trusted monotonic anchor exists on device")


def test_signature_cache(keys: Keys) -> None:
    message = RELEASE_DOMAIN + b"cache probe"
    signature = keys.sign(keys.release, RELEASE_NS, message)
    release_key = signer_key_material(keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS)
    rollback_key = signer_key_material(keys.rollback_signers, ROLLBACK_PRINCIPAL, ROLLBACK_NS)
    assert release_key != rollback_key
    assert keys.verify(False, message, signature, release_key)
    rollback_message_bytes = ROLLBACK_DOMAIN + b"cache probe"
    rollback_signature = keys.sign(keys.rollback, ROLLBACK_NS, rollback_message_bytes)
    with mock.patch.object(VERIFIER, "ssh_verify", wraps=VERIFIER.ssh_verify) as spy:
        for _ in range(2):
            assert not keys.verify(False, message + b"tampered", signature, release_key)
            assert not keys.verify(True, rollback_message_bytes + b"tampered", rollback_signature, rollback_key)
        assert spy.call_count == 4
        assert not keys.verify(True, message, signature, rollback_key)
        assert not keys.verify(False, rollback_message_bytes, rollback_signature, release_key)
        assert spy.call_count == 4
    original = keys.release_signers.read_bytes()
    rollback_bytes = keys.rollback_signers.read_bytes()
    try:
        keys.release_signers.write_bytes(rollback_bytes)
        with mock.patch.object(VERIFIER, "ssh_verify", wraps=VERIFIER.ssh_verify) as spy:
            expect_reject("release role repinned to rollback signer", "signers file", functools.partial(
                keys.verify, False, message, signature, release_key))
            expect_reject("release role repinned to rollback signer, unpinned", "signers file",
                          functools.partial(keys.verify, False, message, signature))
            assert spy.call_count == 0
        keys.release_signers.write_bytes(original + rollback_bytes)
        expect_reject("two-line signers file", "signers file", functools.partial(
            keys.verify, False, message, signature, release_key))
        keys.release_signers.write_bytes(
            original.replace(RELEASE_NS.encode(), ROLLBACK_NS.encode()))
        expect_reject("release signer with rollback namespace", "signers file", functools.partial(
            keys.verify, False, message, signature, release_key))
        other_dir = keys.directory / "other-release"
        other_dir.mkdir()
        other_release = Keys(other_dir)
        keys.release_signers.write_bytes(other_release.release_signers.read_bytes())
        expect_reject("well-formed different release key", "signers changed", functools.partial(
            keys.verify, False, message, signature, release_key))
        assert not keys.verify(False, message, signature)
    finally:
        keys.release_signers.write_bytes(original)
    assert signer_key_material(keys.release_signers, RELEASE_PRINCIPAL, RELEASE_NS) == release_key
    assert keys.verify(False, message, signature, release_key)
    keys.verified.clear()
    with mock.patch.object(VERIFIER, "ssh_verify", wraps=VERIFIER.ssh_verify) as spy:
        assert keys.verify(False, message, signature, release_key)
        assert keys.verify(False, message, signature, release_key)
        assert spy.call_count == 1
    print("signature cache: one ssh-keygen run per distinct verified triple, repeated checks and hits served from cache; signer swaps and extra lines invalidate pins")


def test_selector_without_journal(keys: Keys, base: Generation, forward: Generation) -> None:
    state = State({base.ident: base, forward.ident: forward}, forward.ident, list(base.payloads))
    assert state.journal is None
    assert_refusal_without_write("selector differs from fixed files", "fixed files differ from selector", state,
                                 lambda: reconcile(state, keys, base.ident))
    print("no-journal boot: selector differing from fixed files refused without writes")


def main() -> None:
    if shutil.which("ssh-keygen") is None:
        raise SystemExit("FAIL: ssh-keygen is required")
    with tempfile.TemporaryDirectory(prefix="persistent-root-model-") as name:
        keys = Keys(pathlib.Path(name))
        base = make_generation(keys, 0, "baseline", None, None, payloads("baseline"))
        forward = make_generation(keys, 1, "forward", base.ident, None, payloads("forward"))
        rollback = make_generation(keys, 2, "rollback", forward.ident, base.ident, base.payloads)
        test_parser(base)
        test_authorization(keys, base, forward, rollback)
        test_signature_cache(keys)
        initial = State({base.ident: base}, base.ident, list(base.payloads))
        verify_chain(keys, base.ident, initial.generations, base.ident)
        test_corruption(keys, initial, base, forward, rollback)
        forward_counts = test_interruption(keys, initial, base, forward)
        after_forward = copy.deepcopy(initial)
        execute(update_plan(after_forward, keys, base.ident, forward))
        assert reconcile(after_forward, keys, base.ident) == forward.ident
        rollback_counts = test_interruption(keys, after_forward, forward, rollback)
        after_rollback = copy.deepcopy(after_forward)
        execute(update_plan(after_rollback, keys, base.ident, rollback))
        assert reconcile(after_rollback, keys, base.ident) == rollback.ident
        expect_reject("replay rollback", "generation collision",
                      lambda: update_plan(after_rollback, keys, base.ident, rollback))
        test_legacy_run113_pins(keys, base, forward)
        test_legacy_trust_anchor(keys, base, pathlib.Path(name))
        test_legacy_tree(keys, base, forward, pathlib.Path(name))
        test_trusted_floor(keys, base, forward, rollback)
        test_selector_without_journal(keys, base, forward)
        test_gap_documentation(keys, initial, base, forward, rollback)
        test_collisions(keys, initial, base, forward)
        test_archive_history_and_signers(keys, initial, base, forward, rollback)
        after_rollback.selector = base.ident
        assert reconcile(after_rollback, keys, base.ident) == base.ident
        rewind = copy.deepcopy(initial)
        assert reconcile(rewind, keys, base.ident) == base.ident
        print(f"interruptions: forward {forward_counts[0]} publication cuts / {forward_counts[1]} recovery cuts; "
              f"rollback {rollback_counts[0]} publication cuts / {rollback_counts[1]} recovery cuts")
        print("replay limitation: selector rewind with identical restored bytes and whole-store rewind are accepted")
    print("PASS: host-only synthetic-key signed-generation and logical transaction model")
    print("LIMITATION: not deployable; no device, filesystem durability, concurrency, mount, guard, or hardware anti-replay proof")


if __name__ == "__main__":
    main()
