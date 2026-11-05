#!/usr/bin/env python3
import base64
import binascii
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from typing import NoReturn
from unittest import mock

sys.dont_write_bytecode = True

HERE = pathlib.Path(__file__).resolve().parent
MODULE = HERE / "persistent_root_trust.py"
SPEC = importlib.util.spec_from_file_location("persistent_root_trust", MODULE)
assert SPEC is not None and SPEC.loader is not None
trust = importlib.util.module_from_spec(SPEC)
sys.modules["persistent_root_trust"] = trust
SPEC.loader.exec_module(trust)
SLOTS = ("release", "rollback")
RESULTS = {"pass": 0, "reject": 0}


def fail(message: str) -> NoReturn:
    raise SystemExit(f"FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def accepts(name: str, action: Callable[[], object]) -> object:
    try:
        result = action()
    except (trust.Reject, OSError, ValueError, TypeError, AssertionError) as error:
        fail(f"{name}: unexpected rejection: {type(error).__name__}")
    RESULTS["pass"] += 1
    return result


def rejects(name: str, action: Callable[[], object], reason: str | None = None) -> None:
    try:
        action()
    except trust.Reject as error:
        require(reason is None or str(error) == reason, f"{name}: wrong rejection reason")
        RESULTS["reject"] += 1
        return
    except (OSError, ValueError, TypeError, AssertionError) as error:
        fail(f"{name}: wrong rejection type: {type(error).__name__}")
    fail(f"{name}: action was accepted")


def synthetic_line(key: bytes, algorithm: bytes = b"ssh-ed25519") -> bytes:
    blob = (len(algorithm).to_bytes(4, "big") + algorithm +
            len(key).to_bytes(4, "big") + key)
    return algorithm + b" " + base64.b64encode(blob) + b"\n"


def synthetic_pins(lines: dict[str, bytes]) -> dict[str, str]:
    return {slot: trust.digest(trust.parse_public_line(lines[slot]))
            for slot in SLOTS}


def mutate(line: bytes, index: int, replacement: bytes) -> bytes:
    return line[:index] + replacement + line[index + len(replacement):]


def keygen(directory: pathlib.Path, name: str, kind: str) -> bytes:
    private = directory / name
    public = directory / (name + ".pub")
    result = subprocess.run(
        ["ssh-keygen", "-q", "-t", kind, "-N", "", "-C", "", "-f", str(private)],
        capture_output=True, check=False, env={})
    require(result.returncode == 0, "ssh-keygen failed for synthetic test key")
    line = public.read_bytes()
    if line.endswith(b" \n"):
        line = line[:-2] + b"\n"
    private.unlink()
    public.unlink()
    return line


EXPECTED_OWNER_FINGERPRINTS = {
    "release": "SHA256:aiUM8xoA0XpncAyFhsf+mVp2h/MqO0ag9byKnaohBJ8",
    "rollback": "SHA256:bhAnhbEInLjaSxPUHzjnXjZkGuN0SvA5VkCCVTLfpsA",
}
EXPECTED_OWNER_COMMENTS = {
    "release": "omnipha-sm7635-release-20261105",
    "rollback": "omnipha-sm7635-rollback-20261105",
}


def owner_public_lines() -> dict[str, bytes]:
    config = json.loads((HERE.parent / "configs" /
                         "persistent-root-trust-anchors.json").read_bytes().decode("ascii"))
    return {slot: config["keys"][slot].encode("ascii") + b"\n" for slot in SLOTS}


def owner_role_values() -> dict[str, str]:
    lines = owner_public_lines()
    release = lines["release"][:-1].decode("ascii")
    rollback = lines["rollback"][:-1].decode("ascii")
    release_body = release.rsplit(" ", 1)[0]
    rollback_body = rollback.rsplit(" ", 1)[0]
    return {
        "release": release,
        "rollback": rollback,
        "release_as_rollback": release_body + " " + EXPECTED_OWNER_COMMENTS["rollback"],
        "rollback_as_release": rollback_body + " " + EXPECTED_OWNER_COMMENTS["release"],
        "rollback_bare": rollback_body,
    }


def check_owner_key(slot: str, line: bytes) -> None:
    body = line[:-1]
    require(line.endswith(b"\n") and b"\n" not in body,
            f"owner {slot} anchor is not one record")
    fields = body.split(b" ")
    require(len(fields) == 3, f"owner {slot} anchor does not carry a comment")
    require(all(0x20 <= byte <= 0x7E for byte in body),
            f"owner {slot} anchor is not bounded ASCII")
    require(fields[0] == b"ssh-ed25519" and len(fields[1]) == 68,
            f"owner {slot} anchor is not one encoded Ed25519 key")
    encoded = fields[1]
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        fail(f"owner {slot} encoding is malformed")
    RESULTS["pass"] += 1
    header = (len(b"ssh-ed25519").to_bytes(4, "big") + b"ssh-ed25519" +
              (32).to_bytes(4, "big"))
    require(len(blob) == len(header) + 32 and blob.startswith(header),
            f"owner {slot} blob is not one public key")
    require(base64.b64encode(blob) == encoded,
            f"owner {slot} encoding is not canonical")
    raw = blob[len(header):]
    require(len(raw) == 32, f"owner {slot} raw key is not 32 bytes")
    require(hashlib.sha256(raw).hexdigest() == trust.OWNER_ANCHOR_SHA256[slot],
            f"owner {slot} raw-key pin mismatch")
    fingerprint = ("SHA256:" + base64.b64encode(
        hashlib.sha256(blob).digest()).decode("ascii").rstrip("="))
    require(fingerprint == EXPECTED_OWNER_FINGERPRINTS[slot],
            f"owner {slot} fingerprint mismatch")
    comment = fields[2].decode("ascii")
    require(comment == EXPECTED_OWNER_COMMENTS[slot],
            f"owner {slot} comment mismatch")
    with tempfile.TemporaryDirectory(prefix="persistent-root-trust-fp.") as private:
        path = pathlib.Path(private) / f"{slot}.pub"
        path.write_bytes(line)
        shown = subprocess.run(["ssh-keygen", "-lf", str(path)],
                               capture_output=True, check=False, env={})
        require(shown.returncode == 0,
                f"ssh-keygen could not fingerprint owner {slot} anchor")
        require(EXPECTED_OWNER_FINGERPRINTS[slot].encode("ascii") in shown.stdout,
                f"ssh-keygen fingerprint mismatch for owner {slot} anchor")
        require(EXPECTED_OWNER_COMMENTS[slot].encode("ascii") in shown.stdout,
                f"ssh-keygen comment mismatch for owner {slot} anchor")


def owner_fingerprint_gate() -> None:
    lines = owner_public_lines()
    require(tuple(lines) == SLOTS, "owner config slots are not exact")
    for slot in SLOTS:
        check_owner_key(slot, lines[slot])
    require(lines["release"] != lines["rollback"],
            "owner release and rollback anchors are not distinct")
    require(lines["release"].split(b" ")[1] !=
            lines["rollback"].split(b" ")[1],
            "owner release and rollback raw keys are not distinct")
    require(lines["release"].split(b" ")[0] == lines["rollback"].split(b" ")[0] ==
            b"ssh-ed25519", "owner anchor types are not Ed25519")


def parser_positives(line_a: bytes, line_b: bytes) -> None:
    require(line_a.endswith(b"\n") and line_b.endswith(b"\n"),
            "ssh-keygen public material is not single lines")
    blob_a = accepts("generated line a",
                     lambda: trust.parse_public_line(line_a))
    blob_b = accepts("generated line b",
                     lambda: trust.parse_public_line(line_b))
    require(isinstance(blob_a, bytes) and isinstance(blob_b, bytes) and
            len(blob_a) == 32 and len(blob_b) == 32,
            "parsed anchor blobs are not 32 bytes")
    require(blob_a != blob_b, "generated anchors are not distinct")
    require(trust.parse_public_line(line_a) == blob_a,
            "anchor parsing is not deterministic")
    require(isinstance(blob_a, bytes) and blob_a == accepts(
        "synthetic blob line", lambda: trust.parse_public_line(synthetic_line(blob_a))),
            "synthetic and generated encodings disagree")


def parser_negatives(line_a: bytes, line_b: bytes, other_line: bytes) -> None:
    blob_a = trust.parse_public_line(line_a)
    body = line_a[:-1]
    space = body.index(b" ")
    encoded = body[space + 1:]
    cases: list[tuple[str, bytes]] = [
        ("missing trailing newline", body),
        ("empty line", b"\n"),
        ("two lines", line_a + line_b),
        ("comment suffix", body + b" owner@host\n"),
        ("double space separator", line_a[:space] + b"  " + encoded + b"\n"),
        ("leading space", b" " + line_a),
        ("trailing space", body + b" \n"),
        ("carriage return", body + b"\r\n"),
        ("tab separator", line_a[:space] + b"\t" + encoded + b"\n"),
        ("uppercase type", b"SSH-ED25519 " + encoded + b"\n"),
        ("extended type", mutate(body, 10, b"9999")),
        ("non-Ed25519 type", synthetic_line(blob_a, b"ecdsa-sha2-nistp256")),
        ("bad base64 symbol", mutate(body, space + 1, b"!")),
        ("short base64", body[:-1] + b"\n"),
        ("long base64", body[:space + 1] + encoded + b"A\n"),
        ("non-canonical base64", body[:space + 1] +
         encoded[:-2] + b"==\n"),
        ("wrong blob length", synthetic_line(blob_a + b"\x00")),
        ("short blob key", synthetic_line(blob_a[:31])),
        ("blob type mismatch", synthetic_line(
            blob_a, b"ssh-ed25519\x00")),
        ("garbage base64 payload", line_a[:space + 1] + b"A" * 68 + b"\n"),
        ("non-ASCII byte", mutate(body, space + 5, b"\x80")),
        ("NUL byte", mutate(body, space + 5, b"\x00")),
        ("embedded newline", mutate(body, space + 5, b"\n")),
        ("oversized line", line_a[:space + 1] + b"A" * 69 + b"\n"),
        ("private key material", b"-----BEGIN OPENSSH PRIVATE KEY-----\n"),
        ("openssh private body", b"ssh-ed25519 " + b"A" * 68 +
         b"\n-----BEGIN OPENSSH PRIVATE KEY-----\n"),
        ("other algorithm line", other_line),
    ]
    def run_case(payload: bytes) -> Callable[[], object]:
        return lambda: trust.parse_public_line(payload)

    for name, case in cases:
        rejects(name, run_case(case))
    rejects("empty bytes", lambda: trust.parse_public_line(b""))
    rejects("same key with comment", lambda: trust.parse_public_line(
        body + b" extra\n"))
    rejects("exact boundary plus one", lambda: trust.parse_public_line(
        line_a[:-1] + b"A\n"))
    accepts("exact boundary line", lambda: trust.parse_public_line(
        line_a))
    require(len(line_a) == trust.MAX_LINE, "boundary line is not at the size bound")


def validator_cases(line_a: bytes, line_b: bytes) -> None:
    pins = synthetic_pins({"release": line_a, "rollback": line_b})
    blobs = accepts("owner-approved anchor pair",
                    lambda: trust.validate_with_pins(
                        {"release": line_a, "rollback": line_b}, pins))
    require(isinstance(blobs, dict) and blobs["release"] != blobs["rollback"],
            "validated anchor pair is not distinct")
    accepts("repeated validation", lambda: trust.validate_with_pins(
        {"release": line_b, "rollback": line_a},
        {"release": pins["rollback"], "rollback": pins["release"]}))
    rejects("duplicate anchors", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_a}, pins))
    rejects("swapped pins", lambda: trust.validate_with_pins(
        {"release": line_b, "rollback": line_a}, pins))
    rejects("perturbed release pin", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b},
        {"release": ("0" if pins["release"][0] != "0" else "1") + pins["release"][1:],
         "rollback": pins["rollback"]}))
    rejects("missing slot", lambda: trust.validate_with_pins(
        {"release": line_a}, pins))
    rejects("extra slot", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b, "extra": line_a}, pins))
    rejects("pin None", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b},
        {"release": None, "rollback": pins["rollback"]}))
    rejects("pin uppercase", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b},
        {"release": pins["release"].upper(), "rollback": pins["rollback"]}))
    rejects("pin short", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b},
        {"release": pins["release"][:-1], "rollback": pins["rollback"]}))
    rejects("pins equal", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b},
        {"release": pins["release"], "rollback": pins["release"]}))
    rejects("pins missing", lambda: trust.validate_with_pins(
        {"release": line_a, "rollback": line_b}, {"release": pins["release"]}))


def config_bytes(release: object, rollback: object) -> bytes:
    return json.dumps({"schema": trust.SCHEMA,
                       "keys": {"release": release, "rollback": rollback}},
                      indent=2).encode("ascii") + b"\n"


def synthetic_config_bytes(line_a: bytes, line_b: bytes) -> bytes:
    value_a = line_a[:-1].decode("ascii") + " " + EXPECTED_OWNER_COMMENTS["release"]
    value_b = line_b[:-1].decode("ascii") + " " + EXPECTED_OWNER_COMMENTS["rollback"]
    return config_bytes(value_a, value_b)


def with_config(data: bytes, action: Callable[[], object]) -> object:
    with tempfile.TemporaryDirectory(prefix="persistent-root-trust.") as private:
        path = pathlib.Path(private) / "persistent-root-trust-anchors.json"
        path.write_bytes(data)
        path.chmod(0o600)
        return action_with(path, action)


def action_with(path: pathlib.Path, action: Callable[[], object]) -> object:
    with mock.patch.object(trust, "CONFIG_PATH", path):
        return action()


def config_cases(line_a: bytes, line_b: bytes) -> None:
    value_a = line_a[:-1].decode("ascii")
    value_b = line_b[:-1].decode("ascii")
    comment_a = " " + trust.OWNER_ANCHOR_COMMENTS["release"].decode("ascii")
    comment_b = " " + trust.OWNER_ANCHOR_COMMENTS["rollback"].decode("ascii")
    commented_a = value_a + comment_a
    commented_b = value_b + comment_b
    lines = accepts("well-formed config", lambda: trust.parse_config(
        config_bytes(commented_a, commented_b)))
    require(isinstance(lines, dict) and lines["release"] == line_a and
            lines["rollback"] == line_b,
            "config parsing lost anchor lines")
    rejects("shipped null slots", lambda: trust.parse_config(
        config_bytes(None, None)))
    rejects("one null slot", lambda: trust.parse_config(
        config_bytes(None, commented_b)))
    rejects("absent comment", lambda: trust.parse_config(
        config_bytes(value_a, commented_b)))
    rejects("wrong release comment", lambda: trust.parse_config(
        config_bytes(value_a + comment_b, commented_b)))
    rejects("swapped comments", lambda: trust.parse_config(
        config_bytes(value_a + comment_b, value_b + comment_a)))
    rejects("extra comment field", lambda: trust.parse_config(
        config_bytes(commented_a + " extra", commented_b)))
    rejects("slot as number", lambda: trust.parse_config(
        config_bytes(1, commented_b)))
    rejects("slot as list", lambda: trust.parse_config(
        config_bytes([commented_a], commented_b)))
    rejects("slot as object", lambda: trust.parse_config(
        config_bytes({"key": commented_a}, commented_b)))
    rejects("wrong schema", lambda: trust.parse_config(
        config_bytes(commented_a, commented_b).replace(
            trust.SCHEMA.encode("ascii"), b"omnipha-sm7635-persistent-root-trust-anchors-v2")))
    rejects("missing schema member", lambda: trust.parse_config(
        json.dumps({"keys": {"release": commented_a, "rollback": commented_b}}).encode("ascii")))
    rejects("extra top member", lambda: trust.parse_config(
        config_bytes(commented_a, commented_b)[:-2] + b', "note": "x"}\n'))
    rejects("extra slot member", lambda: trust.parse_config(
        json.dumps({"schema": trust.SCHEMA, "keys": {
            "release": commented_a, "rollback": commented_b, "extra": None}},
            indent=2).encode("ascii") + b"\n"))
    rejects("duplicate config member", lambda: trust.parse_config(
        b'{"schema": "' + trust.SCHEMA.encode("ascii") +
        b'", "schema": "' + trust.SCHEMA.encode("ascii") +
        b'", "keys": {"release": ' + json.dumps(commented_a).encode("ascii") +
        b', "rollback": ' + json.dumps(commented_b).encode("ascii") + b"}}"))
    rejects("missing keys member", lambda: trust.parse_config(
        json.dumps({"schema": trust.SCHEMA}).encode("ascii")))
    rejects("keys as list", lambda: trust.parse_config(
        json.dumps({"schema": trust.SCHEMA, "keys": []}).encode("ascii")))
    rejects("not JSON", lambda: trust.parse_config(b"release,rollback\n"))
    rejects("non-ASCII config", lambda: trust.parse_config(
        config_bytes(commented_a, commented_b).replace(b"\n", b"\xe2\x80\xa8", 1)))
    rejects("nonstandard JSON", lambda: trust.parse_config(b"NaN"))
    rejects("config too large", lambda: trust.parse_config(
        config_bytes(commented_a, commented_b) + b" " * 5000))
    rejects("empty config", lambda: trust.parse_config(b""))
    def run_config(payload: bytes) -> Callable[[], object]:
        return lambda: trust.parse_config(payload)

    for name, data in [("null config", b"null"), ("list config", b"[]")]:
        rejects(name, run_config(data))


def reader_cases(line_a: bytes, line_b: bytes) -> None:
    good = synthetic_config_bytes(line_a, line_b)
    accepts("regular single-link config", lambda: with_config(
        good, lambda: trust.parse_config(trust.read_fixed_config())))
    with tempfile.TemporaryDirectory(prefix="persistent-root-trust.") as private:
        root = pathlib.Path(private)
        root.chmod(0o700)
        config = root / "persistent-root-trust-anchors.json"
        config.write_bytes(good)
        config.chmod(0o600)
        hard = root / "hard.json"
        os.link(config, hard)
        rejects("hard-linked config", lambda: action_with(
            hard, trust.read_fixed_config))
        hard.unlink()
        link = root / "symlink.json"
        link.symlink_to(config)
        rejects("symlinked config", lambda: action_with(
            link, trust.read_fixed_config))
        rejects("missing config", lambda: action_with(
            root / "absent.json", trust.read_fixed_config))
        rejects("directory config", lambda: action_with(
            root, trust.read_fixed_config))
        empty = root / "empty.json"
        empty.write_bytes(b"")
        rejects("empty config file", lambda: action_with(
            empty, trust.read_fixed_config))
        fifo = root / "fifo.json"
        os.mkfifo(fifo)
        rejects("fifo config file", lambda: action_with(
            fifo, trust.read_fixed_config))
        oversized = root / "oversized.json"
        oversized.write_bytes(b" " * (trust.MAX_CONFIG + 1))
        rejects("oversized config file", lambda: action_with(
            oversized, trust.read_fixed_config))
        exact = root / "exact.json"
        exact.write_bytes(b" " * trust.MAX_CONFIG)
        accepts("config at exact size bound", lambda: action_with(
            exact, trust.read_fixed_config))


def production_gate(line_a: bytes, line_b: bytes) -> None:
    require(all(isinstance(trust.OWNER_ANCHOR_SHA256[slot], str) and
                len(str(trust.OWNER_ANCHOR_SHA256[slot])) == 64
                for slot in SLOTS), "owner authorization pins are absent")
    require(trust.OWNER_ANCHOR_SHA256["release"] != trust.OWNER_ANCHOR_SHA256["rollback"],
            "owner authorization pins are not distinct")
    owner_fingerprint_gate()
    repo_config = (HERE.parent / "configs" / "persistent-root-trust-anchors.json").read_bytes()
    accepts("recorded owner anchors", trust.load_owner_anchors)
    require(trust.main(["--check-owner-anchors"]) == 0,
            "recorded owner anchor check did not pass")
    for args in ([], ["--check-owner-anchors", "--pins", "x"], ["--config", "/tmp"], ["--other"]):
        result = subprocess.run([sys.executable, "-B", str(MODULE), *args],
                                capture_output=True, env={}, check=False)
        require(result.returncode == 2, "gate returned wrong status on invalid invocation")
        require(result.stdout == b"", "gate emitted stdout on invalid invocation")
        require(result.stderr == b"usage: persistent_root_trust.py --check-owner-anchors\n",
                "gate emitted unexpected stderr")
    with tempfile.TemporaryDirectory(prefix="persistent-root-trust.") as private:
        root = pathlib.Path(private)
        (root / "configs").mkdir()
        (root / "scripts").mkdir()
        copied = root / "scripts" / "persistent_root_trust.py"
        shutil.copyfile(MODULE, copied)
        copied.chmod(0o700)
        target = root / "configs" / "persistent-root-trust-anchors.json"

        def test_subproc_gate(expected_code: int, expected_stderr: bytes, expected_stdout: bytes = b"") -> None:
            res = subprocess.run([sys.executable, "-B", str(copied), "--check-owner-anchors"],
                                 capture_output=True, check=False)
            require(res.returncode == expected_code,
                    f"copied gate exit mismatch: expected {expected_code}, got {res.returncode}")
            require(res.stdout == expected_stdout, "copied gate stdout mismatch")
            require(res.stderr == expected_stderr, "copied gate stderr mismatch")

        fail_stderr = b"owner trust anchors: FAIL\n"
        target.write_bytes(synthetic_config_bytes(line_a, line_b))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(repo_config)
        test_subproc_gate(0, b"", b"owner trust anchors: PASS\n")

        target.unlink()
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(b"not json\n")
        test_subproc_gate(1, fail_stderr)

        official = owner_role_values()
        target.write_bytes(config_bytes(official["release"], official["release"]))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(config_bytes(official["rollback"], official["release"]))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(config_bytes(official["release"], official["release_as_rollback"]))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(config_bytes(official["rollback_as_release"], official["release_as_rollback"]))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(config_bytes(official["release"], official["rollback_bare"]))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(config_bytes(official["release"], None))
        test_subproc_gate(1, fail_stderr)

        target.write_bytes(b"NaN")
        test_subproc_gate(1, fail_stderr)

        with tempfile.TemporaryDirectory(prefix="persistent-root-trust-throwaway.") as keydir:
            throwaway_a = keygen(pathlib.Path(keydir), "throwaway-a", "ed25519")
            throwaway_b = keygen(pathlib.Path(keydir), "throwaway-b", "ed25519")
        target.write_bytes(synthetic_config_bytes(throwaway_a, throwaway_b))
        test_subproc_gate(1, fail_stderr)

    with mock.patch.object(trust, "CONFIG_PATH",
                           pathlib.Path("/nonexistent/anchors.json")):
        rejects("gate refuses absent config", trust.load_owner_anchors)
    with tempfile.TemporaryDirectory(prefix="persistent-root-trust.") as private:
        root = pathlib.Path(private)
        path = root / "synthetic-anchors.json"
        path.write_bytes(synthetic_config_bytes(line_a, line_b))
        with mock.patch.object(trust, "CONFIG_PATH", path):
            lines = trust.parse_config(trust.read_fixed_config())
            rejects("synthetic input against owner pins",
                    lambda: trust.validate_with_pins(lines, trust.OWNER_ANCHOR_SHA256))
            rejects("synthetic repo-style config through production loader",
                    trust.load_owner_anchors)
        swapped_key_path = root / "swapped-key-anchors.json"
        owner_cfg_obj = json.loads(repo_config.decode("ascii"))
        swapped_key_path.write_bytes(config_bytes(owner_cfg_obj["keys"]["rollback"],
                                                  owner_cfg_obj["keys"]["release"]))
        rejects("swapped roles config through owner loader",
                lambda: action_with(swapped_key_path, trust.load_owner_anchors),
                "release owner anchor comment is not exact")
        release_body = owner_cfg_obj["keys"]["release"].rsplit(" ", 1)[0]
        rollback_body = owner_cfg_obj["keys"]["rollback"].rsplit(" ", 1)[0]
        role_swapped_path = root / "role-swapped-anchors.json"
        role_swapped_path.write_bytes(config_bytes(
            rollback_body + " " + EXPECTED_OWNER_COMMENTS["release"],
            release_body + " " + EXPECTED_OWNER_COMMENTS["rollback"]))
        rejects("swapped role material through owner loader",
                lambda: action_with(role_swapped_path, trust.load_owner_anchors),
                "release anchor is not the owner-authorized value")
        duplicate_path = root / "duplicate-anchors.json"
        duplicate_path.write_bytes(config_bytes(
            release_body + " " + EXPECTED_OWNER_COMMENTS["release"],
            release_body + " " + EXPECTED_OWNER_COMMENTS["rollback"]))
        rejects("duplicate role material through owner loader",
                lambda: action_with(duplicate_path, trust.load_owner_anchors),
                "release and rollback anchors are not distinct")
        diff_pins = {"release": trust.OWNER_ANCHOR_SHA256["rollback"],
                     "rollback": trust.OWNER_ANCHOR_SHA256["release"]}
        with mock.patch.object(trust, "OWNER_ANCHOR_SHA256", diff_pins):
            rejects("official config with different role pins", trust.load_owner_anchors)
        absent_pins = {"release": None, "rollback": trust.OWNER_ANCHOR_SHA256["rollback"]}
        with mock.patch.object(trust, "OWNER_ANCHOR_SHA256", absent_pins):
            rejects("official config with absent release pin", trust.load_owner_anchors)
    recorded = trust.parse_config(repo_config)
    accepts("recorded config validates", lambda: trust.validate_with_pins(
        recorded, trust.OWNER_ANCHOR_SHA256))
    rejects("recorded config against absent pins", lambda: trust.validate_with_pins(
        recorded, {"release": None, "rollback": None}))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="persistent-root-trust-keys.") as private:
        keys = pathlib.Path(private)
        keys.chmod(0o700)
        line_a = keygen(keys, "release", "ed25519")
        line_b = keygen(keys, "rollback", "ed25519")
        other_line = keygen(keys, "other", "ecdsa")
        parser_positives(line_a, line_b)
        parser_negatives(line_a, line_b, other_line)
        validator_cases(line_a, line_b)
        config_cases(line_a, line_b)
        reader_cases(line_a, line_b)
    production_gate(line_a, line_b)
    print(f"persistent root trust anchors: {RESULTS['pass']} pass, "
          f"{RESULTS['reject']} rejected")
    print("not proven: owner approval semantics beyond exact digest equality")
    print("not proven: any future bootstrap embedding or build-time consumption")


if __name__ == "__main__":
    main()
