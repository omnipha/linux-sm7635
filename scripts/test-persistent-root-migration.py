#!/usr/bin/env python3
import ast
import copy
import dataclasses
import functools
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any, NoReturn
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
    if type(obj["sequence"]) is not int or obj["sequence"] < 0:
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
    return ROLLBACK_DOMAIN + (
        f"current={current}\ntarget={target}\nrestores={restores}\nsequence={sequence}\n"
    ).encode("ascii")


def run(args: list[str], data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, input=data, capture_output=True, check=False)


class Keys:
    def __init__(self, directory: pathlib.Path) -> None:
        self.directory = directory
        self.verified: set[tuple[bool, bytes, bytes, bytes]] = set()
        self.release, self.release_signers = self.make_key("release", RELEASE_PRINCIPAL, RELEASE_NS)
        self.rollback, self.rollback_signers = self.make_key("rollback", ROLLBACK_PRINCIPAL, ROLLBACK_NS)
        assert self.release.read_bytes() != self.rollback.read_bytes()
        assert self.release_signers.read_text().split()[-1] != self.rollback_signers.read_text().split()[-1]
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

    def verify(self, rollback: bool, message: bytes, signature: bytes) -> bool:
        signers = self.rollback_signers if rollback else self.release_signers
        cache_key = (rollback, message, signature, signers.read_bytes())
        if cache_key in self.verified:
            return True
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            target = pathlib.Path(tmp) / "signature"
            target.write_bytes(signature)
            principal = ROLLBACK_PRINCIPAL if rollback else RELEASE_PRINCIPAL
            namespace = ROLLBACK_NS if rollback else RELEASE_NS
            result = run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", principal,
                          "-n", namespace, "-s", str(target)], message)
        if result.returncode == 0:
            self.verified.add(cache_key)
            return True
        return False


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
                 ancestors: dict[str, Generation]) -> None:
    obj = parse_manifest(gen.raw)
    if not keys.verify(False, RELEASE_DOMAIN + gen.raw, gen.release_sig):
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
    if not keys.verify(True, statement, gen.rollback_sig):
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
    ancestors: dict[str, Generation] = {}
    previous = None
    for gen in reversed(chain):
        verify_entry(keys, baseline_id, gen, previous, ancestors)
        ancestors[gen.ident] = gen
        previous = gen
    return ancestors


@dataclasses.dataclass(frozen=True)
class Journal:
    previous: str
    target: str


@dataclasses.dataclass
class Stage:
    target: str
    members: dict[str, bytes] = dataclasses.field(default_factory=dict)
    synced: set[str] = dataclasses.field(default_factory=set)
    ready: bool = False
    recognized: bool = True


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
    archived: set[Journal] = dataclasses.field(default_factory=set)


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


def validate_pending(state: State, keys: Keys, baseline_id: str) -> tuple[Generation, Generation]:
    journal = state.journal
    if journal is None or journal.previous == journal.target:
        refuse("invalid journal")
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
        require(name[0] in ("update", "recovery") and name[2] == temp.index and
                0 <= temp.index < len(PATHS), "unknown fixed staging")
        require(temp.generation in (previous.ident, target.ident), "unknown staging generation")
        source = state.generations[temp.generation].payloads[temp.index]
        require(source.startswith(temp.data) and (not temp.synced or temp.data == source),
                "unrecognized staged bytes")
    for selector_name, (value, _) in state.selector_temps.items():
        require(selector_name[0] in ("update", "recovery") and value in (previous.ident, target.ident),
                "unknown selector staging")
    require(state.stage is None and state.journal_temp is None, "unexpected pending staging")
    return previous, target


def boot_clean(state: State, keys: Keys, baseline_id: str) -> str:
    require(state.journal is None, "journal needs recovery")
    require(state.stage is None or state.stage.recognized, "unknown staging")
    chain = verify_chain(keys, baseline_id, state.generations, state.selector)
    selected = chain[state.selector]
    require(state.fixed == list(selected.payloads), "fixed files differ from selector")
    return selected.ident


def update_plan(state: State, keys: Keys, baseline_id: str, target: Generation) -> list[Action]:
    current_id = boot_clean(state, keys, baseline_id)
    require(state.stage is None and state.journal_temp is None and not state.fixed_temps and
            not state.selector_temps, "staging collision")
    require(target.ident not in state.generations, "generation collision")
    chain = verify_chain(keys, baseline_id, state.generations, current_id)
    previous = chain[current_id]
    verify_entry(keys, baseline_id, target, previous, chain)
    journal = Journal(current_id, target.ident)
    require(journal not in state.archived, "journal history collision")
    plan: list[Action] = []

    def create_stage() -> None:
        require(state.stage is None, "staging collision")
        state.stage = Stage(target.ident)

    plan.append(("create generation staging", create_stage))
    expected = members(target)
    for name, data in expected.items():
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
        plan.extend(fixed_steps(state, previous, target, target, index, "update", 0))
    plan.extend(selector_steps(state, previous.ident, target.ident, "update", 0))

    def verify_target() -> None:
        validate_pending(state, keys, baseline_id)
        require(state.selector == target.ident and state.fixed == list(target.payloads), "target recheck")

    def archive() -> None:
        verify_target()
        require(journal not in state.archived, "journal history collision")
        state.archived.add(journal)
        state.journal = None

    plan.extend([("reverify complete target", verify_target), ("archive journal without replacement", archive),
                 ("sync journal archive parent", lambda: None)])
    return plan


def fixed_steps(state: State, previous: Generation, target: Generation, desired: Generation,
                index: int, kind: str, attempt: int) -> list[Action]:
    name = (kind, attempt, index)
    data = desired.payloads[index]

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

    return [(f"{kind} create partial fixed {index}", create),
            (f"{kind} finish fixed {index}", finish),
            (f"{kind} sync and verify fixed {index}", sync),
            (f"{kind} rename fixed {index}", publish),
            (f"{kind} sync fixed directory {index}", lambda: None),
            (f"{kind} recheck fixed {index}", verify)]


def selector_steps(state: State, previous: str, desired: str, kind: str, attempt: int) -> list[Action]:
    name = (kind, attempt)

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

    return [(f"{kind} write selector", create), (f"{kind} sync selector", sync),
            (f"{kind} rename selector", publish), (f"{kind} sync selector directory", lambda: None)]


def recovery_plan(state: State, keys: Keys, baseline_id: str) -> list[Action]:
    previous, target = validate_pending(state, keys, baseline_id)
    journal = state.journal
    assert journal is not None
    require(journal not in state.archived, "journal history collision")
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
        state.archived.add(journal)
        state.journal = None

    plan.extend([("reverify complete previous", verify_previous),
                 ("archive recovered journal without replacement", archive),
                 ("sync recovered archive parent", lambda: None)])
    return plan


def execute(plan: list[Action], cut: int | None = None) -> None:
    for _, action in plan if cut is None else plan[:cut]:
        action()


def reconcile(state: State, keys: Keys, baseline_id: str) -> str:
    if state.journal is not None:
        execute(recovery_plan(state, keys, baseline_id))
    return boot_clean(state, keys, baseline_id)


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
                interrupted = copy.deepcopy(state)
                execute(recovery_plan(interrupted, keys, baseline_id), recovery_cut)
                result = reconcile(interrupted, keys, baseline_id)
                assert result == previous.ident, (cut, recovery_cut)
                assert interrupted.selector == previous.ident and interrupted.fixed == list(previous.payloads)
                assert interrupted.journal is None
                recovery_cuts += 1
        committed_at = next(i for i, (name, _) in enumerate(plan)
                            if name == "archive journal without replacement") + 1
        result = reconcile(state, keys, baseline_id)
        expected = target if cut >= committed_at else previous
        assert result == expected.ident, (cut, plan[cut - 1][0] if cut else "before")
        assert state.fixed == list(expected.payloads) and state.journal is None
    return total + 1, recovery_cuts


def test_corruption(keys: Keys, initial: State, base: Generation, forward: Generation) -> None:
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
        ("archive collision", "journal history collision", lambda s: s.archived.add(Journal(base.ident, forward.ident))),
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
    print(f"corruption: {len(cases) + 2} invalid old/new/journal/fixed/staging states refused before writes")


def test_collisions(keys: Keys, initial: State, base: Generation, forward: Generation) -> None:
    journal = Journal(base.ident, forward.ident)
    cases: list[tuple[str, str, Callable[[State], Any]]] = [
        ("recognized stage", "staging collision", lambda s: setattr(s, "stage", Stage(forward.ident))),
        ("unrecognized stage", "unknown staging", lambda s: setattr(
            s, "stage", Stage(forward.ident, recognized=False))),
        ("journal temp", "staging collision", lambda s: setattr(s, "journal_temp", journal)),
        ("fixed temp", "staging collision", lambda s: s.fixed_temps.update({
            ("update", 0, 0): FixedTemp(base.ident, 0, b"")})),
        ("selector temp", "staging collision", lambda s: s.selector_temps.update({
            ("update", 0): (base.ident, False)})),
        ("generation", "generation collision", lambda s: s.generations.update({forward.ident: forward})),
        ("archived journal", "journal history collision", lambda s: s.archived.add(journal)),
    ]
    for label, reason, mutate in cases:
        state = copy.deepcopy(initial)
        mutate(state)

        def frozen(state: State = state) -> None:
            update_plan(state, keys, base.ident, forward)

        assert_refusal_without_write(label, reason, state, frozen)

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

    state = copy.deepcopy(initial)
    state.stage = Stage(forward.ident, members={"foreign": b"unverified"}, recognized=True)
    state.fixed_temps[("foreign", 0, 0)] = FixedTemp(base.ident, 0, b"unknown")
    assert boot_clean(state, keys, base.ident) == base.ident
    print(f"collisions: {len(cases) + 2} abstract staging/publication collisions refused without writes")
    print("model gap: without a journal, boot trusts the recognized-stage flag and ignores fixed temps")


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


def test_gap_documentation(keys: Keys, initial: State, base: Generation, forward: Generation) -> None:
    state = copy.deepcopy(initial)
    execute(update_plan(state, keys, base.ident, forward), 0)
    state.stage = Stage(forward.ident, members={"foreign": b"unverified"}, recognized=True)
    state.fixed_temps[("foreign", 0, 0)] = FixedTemp(base.ident, 0, b"unknown")
    state.selector_temps[("foreign", 0)] = ("f" * 64, False)
    state.journal_temp = Journal(base.ident, forward.ident)
    assert boot_clean(state, keys, base.ident) == base.ident
    aborted = copy.deepcopy(initial)
    plan = update_plan(aborted, keys, base.ident, forward)
    execute(plan, next(i for i, (name, _) in enumerate(plan) if name == "publish journal without replacement") + 1)
    assert reconcile(aborted, keys, base.ident) == base.ident
    expect_reject("retry of recovered transition", "generation collision",
                  lambda: update_plan(aborted, keys, base.ident, forward))
    print("model gaps (asserted so a fix is noticed): clean boot ignores leftover temp objects and trusts a "
          "boolean 'recognized' stage flag; a recovered transition cannot be retried")


@dataclasses.dataclass
class TrustedFloor:
    sequence: int
    ident: str

    def check(self, state: State, keys: Keys, baseline_id: str) -> str:
        ident = boot_clean(state, keys, baseline_id)
        chain = verify_chain(keys, baseline_id, state.generations, ident)
        require(parse_manifest(chain[ident].raw)["sequence"] >= self.sequence, "below trusted floor")
        require(self.ident in chain, "trusted checkpoint not in chain")
        return ident

    def advance(self, state: State, keys: Keys, baseline_id: str) -> None:
        ident = self.check(state, keys, baseline_id)
        self.sequence = parse_manifest(state.generations[ident].raw)["sequence"]
        self.ident = ident


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
    print("synthetic external monotonic floor, consulted read-side only: downgrade, store rewind and fork "
          "refused when the floor is checked; distinct dual-key rollback advances floor from 1 to 2")
    print("floor caveat: reconcile and update planning do not consult the floor, so a rewound store is still "
          "written to before a floor check; no trusted monotonic anchor exists on device; advancement is "
          "assumed atomic and trusted, not modeled across crashes")


def test_signature_cache(keys: Keys) -> None:
    message = RELEASE_DOMAIN + b"cache probe"
    signature = keys.sign(keys.release, RELEASE_NS, message)
    assert keys.verify(False, message, signature)
    with mock.patch(__name__ + ".run", wraps=run) as spy:
        for rollback in (False, True):
            for _ in range(2):
                assert not keys.verify(rollback, message + b"tampered", signature)
        assert spy.call_count == 4
        assert all(call.args[0][:3] == ["ssh-keygen", "-Y", "verify"] for call in spy.call_args_list)
    original = keys.release_signers.read_bytes()
    try:
        keys.release_signers.write_bytes(keys.rollback_signers.read_bytes())
        with mock.patch(__name__ + ".run", wraps=run) as spy:
            assert not keys.verify(False, message, signature)
            assert not keys.verify(False, message, signature)
            assert spy.call_count == 2
    finally:
        keys.release_signers.write_bytes(original)
    assert keys.verify(False, message, signature)
    print("signature cache: repeated failed release/rollback checks execute ssh-keygen; signer changes invalidate hits")


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
        test_corruption(keys, initial, base, forward)
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
        test_gap_documentation(keys, initial, base, forward)
        test_collisions(keys, initial, base, forward)
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
