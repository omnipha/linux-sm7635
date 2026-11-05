#!/usr/bin/env python3
import base64
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location(
    "verify_root_generation_bundle", HERE / "verify-root-generation-bundle.py")
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def load_builder() -> Any:
    builder_spec = importlib.util.spec_from_file_location(
        "persistent_builder", HERE / "build-init-boot-persistent-root.py")
    assert builder_spec is not None and builder_spec.loader is not None
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)
    return builder


def get_baseline_payloads() -> tuple[bytes, bytes, bytes]:
    builder = load_builder()
    scripts = builder.runtime_scripts()
    payloads = (scripts[builder.FRESH_RADIO], scripts[builder.FRESH_POST], scripts[builder.GATED_HOOK])
    assert tuple(hashlib.sha256(item).hexdigest() for item in payloads) == verifier.BASELINE_DIGESTS
    assert tuple(len(item) for item in payloads) == verifier.BASELINE_SIZES
    return payloads


class Keys:
    def __init__(self, work: pathlib.Path, name: str, principal: str, namespace: str) -> None:
        key = work / name
        done = subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(key)],
            capture_output=True, check=False)
        assert done.returncode == 0, done.stderr
        assert key.stat().st_mode & 0o077 == 0
        fields = pathlib.Path(str(key) + ".pub").read_text().split()
        signers = work / (name + ".signers")
        verifier.write_private(signers, f'{principal} namespaces="{namespace}" {fields[0]} {fields[1]}\n'.encode("ascii"))
        self.name = name
        self.key = key
        self.signers = signers
        self.public = fields[1]
        self._signed: dict[bytes, bytes] = {}

    def sign(self, namespace: str, message: bytes) -> bytes:
        if message in self._signed:
            return self._signed[message]
        with tempfile.TemporaryDirectory(dir=self.key.parent) as tmp:
            target = pathlib.Path(tmp) / "message"
            target.write_bytes(message)
            done = subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-f", str(self.key), "-n", namespace, str(target)],
                capture_output=True, check=False)
            assert done.returncode == 0, done.stderr
            signature = pathlib.Path(str(target) + ".sig").read_bytes()
        self._signed[message] = signature
        return signature


def expect_refusal(label: str, reason_fragment: str, func: Any, *args: Any, **kwargs: Any) -> None:
    try:
        func(*args, **kwargs)
    except verifier.Reject as exc:
        assert reason_fragment in str(exc), f"{label}: expected {reason_fragment!r} in {str(exc)!r}"
    else:
        raise AssertionError(f"{label}: expected Reject({reason_fragment!r}) but succeeded")


def signature_payload(signature: bytes) -> bytes:
    body = signature[len(verifier.SSHSIG_BEGIN):-len(verifier.SSHSIG_END)]
    return b"".join(body[:-1].split(b"\n"))


def rewrap_signature(signature: bytes, width: int) -> bytes:
    data = signature_payload(signature)
    assert len(data) > width and len(data) % width != 0
    lines = [data[i:i + width] for i in range(0, len(data), width)]
    assert all(len(line) == width for line in lines[:-1]) and 0 < len(lines[-1]) < width
    return verifier.SSHSIG_BEGIN + b"\n".join(lines) + b"\n" + verifier.SSHSIG_END


def armor_signature(blob: bytes) -> bytes:
    changed = base64.b64encode(blob)
    lines = [changed[i:i + verifier.SSHSIG_WRAP] for i in range(0, len(changed), verifier.SSHSIG_WRAP)]
    return verifier.SSHSIG_BEGIN + b"\n".join(lines) + b"\n" + verifier.SSHSIG_END


def malformed_signatures(signature: bytes) -> tuple[tuple[str, bytes, str], ...]:
    return (
        ("trailing garbage", signature + b"garbage\n", "signature encoding"),
        ("trailing newline", signature + b"\n", "signature encoding"),
        ("duplicate signature", signature + signature, "signature encoding"),
        ("leading junk", b"junk\n" + signature, "signature encoding"),
        ("blank body line", signature.replace(b"\nU1NI", b"\n\nU1NI", 1), "signature encoding"),
        ("crlf", signature.replace(b"\n", b"\r\n"), "signature encoding"),
        ("space in body", signature.replace(b"U1NI", b"U1N ", 1), "signature encoding"),
        ("rewrap 64", rewrap_signature(signature, 64), "signature encoding"),
        ("binary trailing junk", armor_signature(
            base64.b64decode(signature_payload(signature), validate=True) + b"\n"), "signature structure"),
    )


def expect_chain_armor_refusal(label: str, reason: str, blobs: list[bytes], release: Keys, rollback: Keys,
                               baseline_id: str) -> None:
    expect_refusal(label, reason, verifier.verify_chain, blobs,
                   release.signers, rollback.signers, baseline_id)


def build_manifest(sequence: int, operation: str, previous: str | None, restores: str | None,
                   payloads: tuple[bytes, bytes, bytes]) -> bytes:
    files = [{
        "path": path,
        "size": len(data),
        "sha256": verifier.digest(data),
        "uid": 0,
        "gid": 0,
        "mode": "0700",
    } for path, data in zip(verifier.PATHS, payloads)]
    obj = {
        "schema": verifier.SCHEMA,
        "sequence": sequence,
        "operation": operation,
        "previous": previous,
        "files": files,
        "restores": restores,
    }
    return verifier.canonical(obj)


def forward_payloads(label: str, base: tuple[bytes, bytes, bytes]) -> tuple[bytes, bytes, bytes]:
    return (base[0] + b"#", base[1] + label.encode() + b"\n" + b"#", base[2] + b"#")


def make_bundle(release: Keys, sequence: int, operation: str, previous: str | None,
                restores: str | None, payloads: tuple[bytes, bytes, bytes],
                rollback: Keys | None = None) -> tuple[bytes, str]:
    raw_manifest = build_manifest(sequence, operation, previous, restores, payloads)
    manifest_id = verifier.digest(raw_manifest)
    release_sig = release.sign(verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + raw_manifest)
    rollback_sig = None
    if rollback is not None:
        stmt = verifier.rollback_message(previous or ("0" * 64), manifest_id,
                                         restores or ("0" * 64), sequence)
        rollback_sig = rollback.sign(verifier.ROLLBACK_NS, stmt)
    blob = verifier.encode_bundle(raw_manifest, release_sig, payloads, rollback_sig)
    return blob, manifest_id


def run_tests() -> None:
    with tempfile.TemporaryDirectory(prefix="root-generation-bundle-") as tmp_dir:
        work = pathlib.Path(tmp_dir)
        release = Keys(work, "release", verifier.RELEASE_PRINCIPAL, verifier.RELEASE_NS)
        rollback = Keys(work, "rollback", verifier.ROLLBACK_PRINCIPAL, verifier.ROLLBACK_NS)
        other = Keys(work, "other", verifier.RELEASE_PRINCIPAL, verifier.RELEASE_NS)
        assert release.signers.read_text().split()[-1] != rollback.signers.read_text().split()[-1]
        assert release.signers.read_text().split()[-1] != other.signers.read_text().split()[-1]
        assert rollback.signers.read_text().split()[-1] != other.signers.read_text().split()[-1]

        baseline_payloads = get_baseline_payloads()
        b_blob, b_id = make_bundle(release, 0, "baseline", None, None, baseline_payloads)
        assert b_id == "9d62f0e549d5821693ff2fb97a4c887e708c6831eef63146326df130d8242e61"
        chain = verifier.verify_chain([b_blob], release.signers, rollback.signers, b_id)
        assert len(chain) == 1 and chain[0].ident == b_id and not chain[0].rollback
        assert chain[0].payloads == baseline_payloads

        expect_refusal("baseline wrong pin", "baseline pin", verifier.verify_chain,
                       [b_blob], release.signers, rollback.signers, "0" * 64)
        expect_refusal("baseline wrong release key", "release signature", verifier.verify_chain,
                       [b_blob], other.signers, rollback.signers, b_id)
        expect_refusal("identical release and rollback signers", "keys not distinct",
                       verifier.verify_chain, [b_blob], release.signers, release.signers, b_id)

        same_key_rollback_signers = work / "same_key_rollback.signers"
        same_key_rollback_signers.write_text(
            f'{verifier.ROLLBACK_PRINCIPAL} namespaces="{verifier.ROLLBACK_NS}" {release.signers.read_text().split()[-2]} {release.public}\n')
        assert same_key_rollback_signers.read_bytes() != release.signers.read_bytes()
        expect_refusal("different signers files sharing underlying key", "keys not distinct",
                       verifier.verify_chain, [b_blob], release.signers, same_key_rollback_signers, b_id)

        good_line = release.signers.read_text()
        link = work / "release_link.signers"
        link.symlink_to(release.signers)
        hard = work / "release_hard.signers"
        hard.hardlink_to(release.signers)
        variants = {
            "symlinked signers": link,
            "hardlinked signers": hard,
            "missing signers": work / "absent.signers",
        }
        for label, text in (
            ("two key lines", good_line + good_line),
            ("extra option", good_line.replace(" ssh-ed25519", ",cert-authority ssh-ed25519", 1)),
            ("wrong principal", good_line.replace(verifier.RELEASE_PRINCIPAL, "fixture-other", 1)),
            ("wrong namespace", good_line.replace(verifier.RELEASE_NS, verifier.ROLLBACK_NS, 1)),
            ("trailing comment field", good_line[:-1] + " note\n"),
            ("no trailing newline", good_line[:-1]),
            ("oversized signers", good_line + "#" * verifier.SIGNERS_MAX + "\n"),
            ("rsa key type", good_line.replace("ssh-ed25519", "ssh-rsa", 1)),
        ):
            mutated = work / (label.replace(" ", "_") + ".signers")
            verifier.write_private(mutated, text.encode("ascii"))
            variants[label] = mutated
        for label, path in variants.items():
            expect_refusal(label, "signers file", verifier.load_signers, path,
                           verifier.RELEASE_PRINCIPAL, verifier.RELEASE_NS)
        link.unlink()
        hard.unlink()

        model_spec = importlib.util.spec_from_file_location(
            "model_migration", HERE / "test-persistent-root-migration.py")
        assert model_spec is not None and model_spec.loader is not None
        model = importlib.util.module_from_spec(model_spec)
        model_spec.loader.exec_module(model)
        assert verifier.SCHEMA == model.SCHEMA
        assert verifier.RELEASE_NS == model.RELEASE_NS
        assert verifier.ROLLBACK_NS == model.ROLLBACK_NS
        assert verifier.RELEASE_DOMAIN == model.RELEASE_DOMAIN
        assert verifier.ROLLBACK_DOMAIN == model.ROLLBACK_DOMAIN
        assert verifier.RELEASE_PRINCIPAL == model.RELEASE_PRINCIPAL
        assert verifier.ROLLBACK_PRINCIPAL == model.ROLLBACK_PRINCIPAL

        model_dir = work / "model_keys"
        model_dir.mkdir()
        model_keys = model.Keys(model_dir)
        probe_manifest = build_manifest(0, "baseline", None, None, get_baseline_payloads())
        probe_statement = verifier.rollback_message("1" * 64, "2" * 64, "3" * 64, 7)
        assert probe_statement == model.rollback_message("1" * 64, "2" * 64, "3" * 64, 7)
        assert probe_manifest == model.manifest(0, "baseline", None, None, get_baseline_payloads())
        model_release_sig = model_keys.sign(model_keys.release, model.RELEASE_NS,
                                            model.RELEASE_DOMAIN + probe_manifest)
        model_rollback_sig = model_keys.sign(model_keys.rollback, model.ROLLBACK_NS, probe_statement)
        assert verifier.ssh_verify(model_keys.release_signers, verifier.RELEASE_PRINCIPAL,
                                   verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + probe_manifest,
                                   model_release_sig)
        assert verifier.ssh_verify(model_keys.rollback_signers, verifier.ROLLBACK_PRINCIPAL,
                                   verifier.ROLLBACK_NS, probe_statement, model_rollback_sig)
        assert not verifier.ssh_verify(model_keys.release_signers, verifier.RELEASE_PRINCIPAL,
                                       verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + probe_manifest + b"x",
                                       model_release_sig)
        shutil.copyfile(release.signers, model_keys.release_signers)
        shutil.copyfile(rollback.signers, model_keys.rollback_signers)
        ours_release_sig = release.sign(verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + probe_manifest)
        ours_rollback_sig = rollback.sign(verifier.ROLLBACK_NS, probe_statement)
        assert model_keys.verify(False, model.RELEASE_DOMAIN + probe_manifest, ours_release_sig)
        assert model_keys.verify(True, probe_statement, ours_rollback_sig)
        assert not model_keys.verify(True, model.RELEASE_DOMAIN + probe_manifest, ours_release_sig)
        assert not model_keys.verify(False, probe_statement, ours_rollback_sig)
        del model_keys

        diff_dir = work / "model_diff"
        diff_dir.mkdir()
        diff_keys = model.Keys(diff_dir)
        diff_base = model.make_generation(diff_keys, 0, "baseline", None, None, model.payloads("baseline"))
        diff_fwd = model.make_generation(diff_keys, 1, "forward", diff_base.ident, None,
                                         model.payloads("forward"))
        diff_reissue = model.make_generation(diff_keys, 2, "forward", diff_fwd.ident, None,
                                             diff_base.payloads)
        diff_history = {gen.ident: gen for gen in (diff_base, diff_fwd, diff_reissue)}
        assert model.verify_chain(diff_keys, diff_base.ident, diff_history, diff_reissue.ident)
        del diff_keys

        expect_refusal("empty chain", "chain input", verifier.verify_chain,
                       [], release.signers, rollback.signers, b_id)

        b2_blob, _ = make_bundle(release, 0, "baseline", None, None, baseline_payloads)
        expect_refusal("baseline after initialization", "baseline after initialization",
                       verifier.verify_chain, [b_blob, b2_blob], release.signers,
                       rollback.signers, b_id)

        unpinned = forward_payloads("unpinned", baseline_payloads)
        unpinned_blob, _ = make_bundle(release, 0, "baseline", None, None, unpinned)
        expect_refusal("baseline without pinned bytes", "baseline bytes", verifier.verify_chain,
                       [unpinned_blob], release.signers, rollback.signers,
                       verifier.digest(build_manifest(0, "baseline", None, None, unpinned)))

        f1_payloads = forward_payloads("forward-1", baseline_payloads)
        f1_blob, f1_id = make_bundle(release, 1, "forward", b_id, None, f1_payloads)
        f2_payloads = forward_payloads("forward-2", f1_payloads)
        f2_blob, f2_id = make_bundle(release, 2, "forward", f1_id, None, f2_payloads)
        chain = verifier.verify_chain([b_blob, f1_blob, f2_blob], release.signers,
                                      rollback.signers, b_id)
        assert [item.ident for item in chain] == [b_id, f1_id, f2_id]
        assert [item.parsed["sequence"] for item in chain] == [0, 1, 2]

        skip_blob, _ = make_bundle(release, 2, "forward", b_id, None, f1_payloads)
        expect_refusal("forward skipped sequence", "sequence", verifier.verify_chain,
                       [b_blob, skip_blob], release.signers, rollback.signers, b_id)
        wrong_prev_blob, _ = make_bundle(release, 1, "forward", "f" * 64, None, f1_payloads)
        expect_refusal("forward wrong predecessor", "predecessor", verifier.verify_chain,
                       [b_blob, wrong_prev_blob], release.signers, rollback.signers, b_id)
        replay_bytes_blob, _ = make_bundle(release, 1, "forward", b_id, None, baseline_payloads)
        expect_refusal("forward reissues earlier bytes", "forward reissues earlier bytes",
                       verifier.verify_chain, [b_blob, replay_bytes_blob], release.signers,
                       rollback.signers, b_id)
        forward_with_rollback_blob, _ = make_bundle(
            release, 1, "forward", b_id, None, f1_payloads, rollback)
        expect_refusal("forward carrying rollback evidence", "forward authorization",
                       verifier.verify_chain, [b_blob, forward_with_rollback_blob],
                       release.signers, rollback.signers, b_id)

        rb1_blob, rb1_id = make_bundle(
            release, 3, "rollback", f2_id, b_id, baseline_payloads, rollback)
        chain = verifier.verify_chain([b_blob, f1_blob, f2_blob, rb1_blob], release.signers,
                                      rollback.signers, b_id)
        assert chain[-1].ident == rb1_id and chain[-1].rollback
        assert chain[-1].parsed["restores"] == b_id
        assert chain[-1].payloads == baseline_payloads

        rb2_blob, rb2_id = make_bundle(
            release, 4, "rollback", rb1_id, f1_id, f1_payloads, rollback)
        chain = verifier.verify_chain([b_blob, f1_blob, f2_blob, rb1_blob, rb2_blob],
                                      release.signers, rollback.signers, b_id)
        assert chain[-1].ident == rb2_id and chain[-1].parsed["restores"] == f1_id

        rb3_blob, rb3_id = make_bundle(
            release, 5, "rollback", rb2_id, b_id, baseline_payloads, rollback)
        chain = verifier.verify_chain([b_blob, f1_blob, f2_blob, rb1_blob, rb2_blob, rb3_blob],
                                      release.signers, rollback.signers, b_id)
        assert chain[-1].ident == rb3_id and chain[-1].parsed["restores"] == b_id

        replay_blob, replay_id = make_bundle(
            release, 3, "rollback", f2_id, b_id, baseline_payloads, rollback)
        expect_refusal("replay of an already-seen generation id", "generation replay",
                       verifier.verify_chain, [b_blob, f1_blob, f2_blob, rb1_blob, replay_blob],
                       release.signers, rollback.signers, b_id)
        del replay_id

        expect_refusal("rollback signed by release key", "rollback signature",
                       verifier.verify_chain,
                       [b_blob, f1_blob, f2_blob,
                        make_bundle(release, 3, "rollback", f2_id, b_id, baseline_payloads, release)[0]],
                       release.signers, rollback.signers, b_id)
        swapped_manifest = build_manifest(1, "forward", b_id, None, f1_payloads)
        swapped_sig = rollback.sign(verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + swapped_manifest)
        swapped_blob = verifier.encode_bundle(swapped_manifest, swapped_sig, f1_payloads)
        expect_refusal("release statement signed by rollback key", "release signature",
                       verifier.verify_chain, [b_blob, swapped_blob], release.signers,
                       rollback.signers, b_id)
        expect_refusal("rollback signed by other key", "rollback signature",
                       verifier.verify_chain,
                       [b_blob, f1_blob, f2_blob,
                        make_bundle(release, 3, "rollback", f2_id, b_id, baseline_payloads, other)[0]],
                       release.signers, rollback.signers, b_id)

        restored_manifest = build_manifest(3, "rollback", f2_id, b_id, baseline_payloads)
        wrong_current = build_manifest(3, "rollback", f1_id, b_id, baseline_payloads)
        wrong_current_id = verifier.digest(wrong_current)
        forged_sig = rollback.sign(verifier.ROLLBACK_NS, verifier.rollback_message(
            f1_id, verifier.digest(restored_manifest), b_id, 3))
        forged = verifier.encode_bundle(restored_manifest, release.sign(
            verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + restored_manifest),
            baseline_payloads, forged_sig)
        expect_refusal("rollback statement names the wrong current", "rollback signature",
                       verifier.verify_chain, [b_blob, f1_blob, f2_blob, forged],
                       release.signers, rollback.signers, b_id)
        del wrong_current, wrong_current_id

        ghost_blob, _ = make_bundle(release, 3, "rollback", f2_id, "e" * 64,
                                    baseline_payloads, rollback)
        expect_refusal("rollback restores an unknown generation", "restored id",
                       verifier.verify_chain, [b_blob, f1_blob, f2_blob, ghost_blob],
                       release.signers, rollback.signers, b_id)
        predecessor_blob, _ = make_bundle(release, 3, "rollback", f2_id, f2_id,
                                          f2_payloads, rollback)
        expect_refusal("rollback restores the predecessor itself", "source not older",
                       verifier.verify_chain, [b_blob, f1_blob, f2_blob, predecessor_blob],
                       release.signers, rollback.signers, b_id)
        divergent = (baseline_payloads[0] + b"#", baseline_payloads[1],
                     baseline_payloads[2])
        divergent_blob, _ = make_bundle(release, 3, "rollback", f2_id, b_id,
                                        divergent, rollback)
        expect_refusal("rollback alters the restored bytes", "restored bytes",
                       verifier.verify_chain, [b_blob, f1_blob, f2_blob, divergent_blob],
                       release.signers, rollback.signers, b_id)
        missing_evidence_blob, _ = make_bundle(release, 3, "rollback", f2_id, b_id,
                                               baseline_payloads)
        expect_refusal("rollback without rollback evidence", "rollback evidence",
                       verifier.verify_chain, [b_blob, f1_blob, f2_blob, missing_evidence_blob],
                       release.signers, rollback.signers, b_id)

        manifest, release_sig, payloads, rollback_sig = verifier.parse_bundle(b_blob)
        assert manifest and release_sig and payloads == baseline_payloads and rollback_sig is None
        flipped_sig = bytes([release_sig[0] ^ 1]) + release_sig[1:]
        try:
            verifier.verify_chain([verifier.encode_bundle(manifest, flipped_sig, payloads)],
                                  release.signers, rollback.signers, b_id)
        except verifier.Reject as exc:
            assert any(tag in str(exc) for tag in ("release signature", "signature encoding")), str(exc)
        else:
            raise AssertionError("baseline corrupted signature accepted")
        flipped_payload = (bytes([payloads[0][-1] ^ 1]) + payloads[0][:-1], payloads[1], payloads[2])
        expect_refusal("baseline corrupted payload", "payload mismatch",
                       verifier.verify_chain,
                       [verifier.encode_bundle(manifest, release_sig, flipped_payload)],
                       release.signers, rollback.signers, b_id)

        expect_refusal("corrupted magic", "bundle header", verifier.parse_bundle,
                       b"NOPE" + b_blob[4:])
        expect_refusal("corrupted version", "bundle header", verifier.parse_bundle,
                       b_blob[:4] + bytes((2, 0, 0, 0)) + b_blob[8:])
        expect_refusal("trailing bytes", "trailing bytes", verifier.parse_bundle, b_blob + b"x")
        expect_refusal("short bundle", "bundle size", verifier.parse_bundle, b_blob[:11])
        expect_refusal("bad count", "bundle count", verifier.parse_bundle,
                       b_blob[:8] + (4).to_bytes(4, "big") + b_blob[12:])
        expect_refusal("truncated member", "member bounds", verifier.parse_bundle,
                       b_blob[:-1])
        expect_refusal("member order enforced", "member order or kind", verifier.parse_bundle,
                       bytes(bytearray(b_blob[:12]) + bytearray(b_blob[12 + 5 + len(manifest):])))
        expect_refusal("oversized manifest member", "member bounds", verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big")
                       + verifier.frame_member(verifier.KIND_MANIFEST, b"a" * 5000)
                       + b"rest")
        expect_refusal("manifest member with zero length", "member bounds",
                       verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big")
                       + verifier.frame_member(verifier.KIND_MANIFEST, b""))

        members = [verifier.frame_member(verifier.KIND_RELEASE_SIG, release_sig),
                   verifier.frame_member(verifier.KIND_MANIFEST, manifest)]
        members += [verifier.frame_member(kind, data)
                    for kind, data in zip(verifier.KIND_PAYLOADS, payloads)]
        expect_refusal("reordered members", "member order or kind", verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big") + b"".join(members))

        members = [verifier.frame_member(verifier.KIND_MANIFEST, manifest),
                   verifier.frame_member(verifier.KIND_MANIFEST, manifest)]
        members += [verifier.frame_member(kind, data)
                    for kind, data in zip(verifier.KIND_PAYLOADS, payloads)]
        expect_refusal("duplicated manifest tag", "member order or kind", verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big") + b"".join(members))

        members = [verifier.frame_member(verifier.KIND_MANIFEST, manifest),
                   verifier.frame_member(verifier.KIND_ROLLBACK_SIG, release_sig)]
        members += [verifier.frame_member(kind, data)
                    for kind, data in zip(verifier.KIND_PAYLOADS, payloads)]
        expect_refusal("rollback tag before payloads", "member order or kind",
                       verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big") + b"".join(members))

        framed = [verifier.frame_member(kind, data)
                  for kind, data in zip(verifier.KIND_PAYLOADS, payloads)]
        head = [verifier.frame_member(verifier.KIND_MANIFEST, manifest),
                verifier.frame_member(verifier.KIND_RELEASE_SIG, release_sig)]
        for label, tail in (
            ("duplicated payload tag", [framed[0], framed[0], framed[2]]),
            ("swapped payload order", [framed[1], framed[0], framed[2]]),
            ("payload tag reversed", [framed[2], framed[1], framed[0]]),
            ("duplicated final payload", [framed[0], framed[1], framed[1]]),
        ):
            expect_refusal(label, "member order or kind", verifier.parse_bundle,
                           verifier.HEADER + (5).to_bytes(4, "big") + b"".join(head + tail))
        rollback_framed = verifier.frame_member(verifier.KIND_ROLLBACK_SIG, release_sig)
        expect_refusal("duplicated rollback tag", "member order or kind", verifier.parse_bundle,
                       verifier.HEADER + (6).to_bytes(4, "big")
                       + b"".join(head + [rollback_framed, rollback_framed] + framed[:2]))
        expect_refusal("rollback tag after payloads", "member order or kind", verifier.parse_bundle,
                       verifier.HEADER + (6).to_bytes(4, "big")
                       + b"".join(head + framed + [rollback_framed]))
        expect_refusal("rollback count without rollback member", "member order or kind",
                       verifier.parse_bundle,
                       verifier.HEADER + (6).to_bytes(4, "big") + b"".join(head + framed))
        expect_refusal("oversized payload length", "member bounds", verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big") + b"".join(head)
                       + bytes((verifier.KIND_PAYLOADS[0],)) + (verifier.PAYLOAD_MAX + 1).to_bytes(4, "big"))
        expect_refusal("oversized signature length", "member bounds", verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big") + head[0]
                       + bytes((verifier.KIND_RELEASE_SIG,)) + (verifier.SIGNATURE_MAX + 1).to_bytes(4, "big"))
        expect_refusal("length beyond buffer", "member bounds", verifier.parse_bundle,
                       verifier.HEADER + (5).to_bytes(4, "big") + head[0]
                       + bytes((verifier.KIND_RELEASE_SIG,)) + (0xFFFFFFFF).to_bytes(4, "big"))
        expect_refusal("bundle over total bound", "bundle size", verifier.parse_bundle,
                       b"\0" * (verifier.BUNDLE_MAX + 1))
        expect_refusal("encode wrong payload count", "bundle input", verifier.encode_bundle,
                       manifest, release_sig, payloads[:2])
        expect_refusal("encode empty payload", "bundle input", verifier.encode_bundle,
                       manifest, release_sig, (b"", payloads[1], payloads[2]))
        expect_refusal("encode oversized payload", "bundle input", verifier.encode_bundle,
                       manifest, release_sig, (b"x" * (verifier.PAYLOAD_MAX + 1), payloads[1], payloads[2]))

        bad_files = [{
            "path": path,
            "size": len(data),
            "sha256": verifier.BAD_RADIO if index == 0 else verifier.digest(data),
            "uid": 0, "gid": 0, "mode": "0700",
        } for index, (path, data) in enumerate(zip(verifier.PATHS, baseline_payloads))]
        bad_manifest = verifier.canonical({
            "schema": verifier.SCHEMA, "sequence": 1, "operation": "forward",
            "previous": b_id, "files": bad_files, "restores": None,
        })
        expect_refusal("altered radio digest", "file digest", verifier.parse_manifest, bad_manifest)

        valid_manifest = build_manifest(0, "baseline", None, None, baseline_payloads)
        assert verifier.parse_manifest(valid_manifest)["sequence"] == 0
        spaced = json.dumps(json.loads(valid_manifest)).encode("ascii")
        expect_refusal("noncanonical manifest spacing", "not canonical",
                       verifier.parse_manifest, spaced)
        expect_refusal("trailing whitespace", "not canonical",
                       verifier.parse_manifest, valid_manifest + b"\n")
        expect_refusal("duplicate key", "duplicate key", verifier.parse_manifest,
                       valid_manifest[:-1] + b',"restores":null}')
        expect_refusal("float spelling", "sequence type", verifier.parse_manifest,
                       valid_manifest.replace(b'"sequence":0', b'"sequence":0.0'))
        expect_refusal("escaped path", "not canonical", verifier.parse_manifest,
                       valid_manifest.replace(b'"/usr/libexec', b'"\\u002fusr/libexec', 1))
        expect_refusal("empty manifest", "manifest size", verifier.parse_manifest, b"")
        expect_refusal("oversized manifest", "manifest size",
                       verifier.parse_manifest, b"{" + b"a" * 5000 + b"}")
        expect_refusal("deeply nested manifest", "manifest fields",
                       verifier.parse_manifest, b"[" * 2040 + b"]" * 2040)
        expect_refusal("truncated manifest accepted as staging", "manifest encoding or JSON",
                       verifier.parse_manifest,
                       b'{"files":[{"gid":0,"mode":"0700","path":"/usr')

        expect_refusal("cli production use refused", "production use refused",
                       verifier.main, ["--production", "/dev/sda13"])
        expect_refusal("cli no args", "production use refused", verifier.main, [])
        expect_refusal("cli verify arg", "production use refused",
                       verifier.main, ["--verify", "/dev/sda13"])
        expect_refusal("cli verify payload", "production use refused",
                       verifier.main, ["--verify", b_blob])
        expect_refusal("cli sign arg", "production use refused",
                       verifier.main, ["--sign", "manifest.json"])
        expect_refusal("cli sign payload", "production use refused",
                       verifier.main, ["--sign", "manifest.json", "key"])
        expect_refusal("cli verify path", "production use refused",
                       verifier.main, ["--verify", "/etc/shadow"])
        expect_refusal("cli sign path", "production use refused",
                       verifier.main, ["--sign", "/etc/shadow", "/etc/ssh/ssh_host_ed25519_key"])

        script = HERE / "verify-root-generation-bundle.py"
        for label, args in (
            ("subprocess no args", []),
            ("subprocess production", ["--production", "/dev/sda13"]),
            ("subprocess verify", ["--verify", "/etc/shadow"]),
            ("subprocess sign", ["--sign", "manifest.json", "key"]),
            ("subprocess extra self-test", ["--self-test", "--extra"]),
        ):
            done = subprocess.run(["python3", "-B", str(script), *args], capture_output=True, check=False)
            assert done.returncode == 1, label
            assert b"refused: production use refused" in done.stderr, label
            assert done.stdout == b"", label

        def mutate_signature(signature: bytes, namespace: str, mutate: Any) -> bytes:
            body = signature[len(verifier.SSHSIG_BEGIN):-len(verifier.SSHSIG_END)]
            data = b"".join(body[:-1].split(b"\n"))
            blob = bytearray(base64.b64decode(data, validate=True))
            mutate(blob)
            changed = base64.b64encode(bytes(blob))
            lines = [changed[i:i + verifier.SSHSIG_WRAP] for i in range(0, len(changed), verifier.SSHSIG_WRAP)]
            armored = verifier.SSHSIG_BEGIN + b"\n".join(lines) + b"\n" + verifier.SSHSIG_END
            expect_refusal(f"mutated {namespace} signature", "signature",
                           verifier.canonical_signature, armored, namespace)
            return armored

        release_sig = release.sign(verifier.RELEASE_NS, verifier.RELEASE_DOMAIN + build_manifest(
            0, "baseline", None, None, baseline_payloads))
        rollback_sig = rollback.sign(verifier.ROLLBACK_NS, verifier.rollback_message(
            "1" * 64, "2" * 64, "3" * 64, 7))
        for label, signature, namespace in (
            ("release", release_sig, verifier.RELEASE_NS),
            ("rollback", rollback_sig, verifier.ROLLBACK_NS),
        ):
            assert verifier.canonical_signature(signature, namespace) == signature
            assert b"Hash:" not in signature
            assert all(len(line) == verifier.SSHSIG_WRAP for line in
                       signature[len(verifier.SSHSIG_BEGIN):-len(verifier.SSHSIG_END)][:-1].split(b"\n")[:-1])
            for bad_label, bad, reason in malformed_signatures(signature):
                expect_refusal(f"{label} {bad_label}", reason,
                               verifier.canonical_signature, bad, namespace)
            mutate_signature(signature, namespace, lambda blob: blob.__setitem__(6, blob[6] ^ 1))
            mutate_signature(signature, namespace, lambda blob: blob.append(1))
            wrong_ns = verifier.ROLLBACK_NS if namespace == verifier.RELEASE_NS else verifier.RELEASE_NS
            expect_refusal(f"{label} wrong namespace", "signature namespace",
                           verifier.canonical_signature, signature, wrong_ns)
        oversized = verifier.SSHSIG_BEGIN + (b"A" * verifier.SSHSIG_WRAP + b"\n") * 40 + verifier.SSHSIG_END
        expect_refusal("signature limit before parsing", "signature bounds",
                       verifier.canonical_signature, oversized, verifier.RELEASE_NS)

        baseline_manifest, baseline_release_sig, baseline_payload_members, _ = verifier.parse_bundle(b_blob)
        rollback_manifest, rollback_release_sig, rollback_payload_members, rollback_evidence = (
            verifier.parse_bundle(rb1_blob))
        assert rollback_evidence is not None
        for label, bad_release, reason in malformed_signatures(baseline_release_sig):
            expect_chain_armor_refusal(
                f"release {label}", reason,
                [verifier.encode_bundle(baseline_manifest, bad_release, baseline_payload_members)],
                release, rollback, b_id)
        for label, bad_rollback, reason in malformed_signatures(rollback_evidence):
            expect_chain_armor_refusal(
                label, reason,
                [b_blob, f1_blob, f2_blob, verifier.encode_bundle(
                    rollback_manifest, rollback_release_sig, rollback_payload_members, bad_rollback)],
                release, rollback, b_id)
        assert verifier.verify_chain(
            [b_blob, f1_blob, f2_blob, verifier.encode_bundle(
                rollback_manifest, rollback_release_sig, rollback_payload_members, rollback_evidence)],
            release.signers, rollback.signers, b_id)[-1].ident == rb1_id

        partial = (baseline_payloads[0] + b"#", baseline_payloads[1], baseline_payloads[2])
        partial_blob, partial_id = make_bundle(release, 1, "forward", b_id, None, partial)
        chain = verifier.verify_chain([b_blob, partial_blob], release.signers, rollback.signers, b_id)
        assert chain[-1].ident == partial_id and chain[-1].payloads == partial
        altered = (baseline_payloads[0] + b" ", baseline_payloads[1] + b" ", baseline_payloads[2] + b" ")
        altered_blob, altered_id = make_bundle(release, 2, "forward", partial_id, None, altered)
        chain = verifier.verify_chain([b_blob, partial_blob, altered_blob], release.signers,
                                      rollback.signers, b_id)
        assert chain[-1].ident == altered_id
        replay_tuple, _ = make_bundle(release, 3, "forward", altered_id, None, baseline_payloads)
        expect_refusal("full tuple reissue", "forward reissues earlier bytes",
                       verifier.verify_chain, [b_blob, partial_blob, altered_blob, replay_tuple],
                       release.signers, rollback.signers, b_id)
        print("tuple policy: experimental full-tuple reissue refusal only; a partial reissue of an earlier "
              "generation is accepted, not semantic downgrade prevention. Hash comparison does not authorize "
              "rollback. This differs from the model, which accepts full reissue.")

        expect_refusal("truncated JSON", "manifest encoding or JSON",
                       verifier.parse_manifest, b'{"schema":')
        expect_refusal("unterminated string", "manifest encoding or JSON",
                       verifier.parse_manifest, b'{"schema":"unterminated')
        expect_refusal("trailing comma", "manifest encoding or JSON",
                       verifier.parse_manifest, valid_manifest[:-1] + b",}")
        expect_refusal("extra top-level value", "manifest encoding or JSON",
                       verifier.parse_manifest, valid_manifest + b"{}")
        expect_refusal("null byte", "manifest encoding or JSON",
                       verifier.parse_manifest, valid_manifest.replace(b"schema", b"sche\x00ma", 1))
        expect_refusal("infinity spelling", "number spelling",
                       verifier.parse_manifest, valid_manifest.replace(b'"sequence":0', b'"sequence":Infinity'))
        expect_refusal("not an object", "manifest fields",
                       verifier.parse_manifest, b'[]')
        expect_refusal("wrong field order", "manifest fields",
                       verifier.parse_manifest, valid_manifest.replace(
                           b'"schema":"' + verifier.SCHEMA.encode() + b'","sequence":0',
                           b'"sequence":0,"schema":"' + verifier.SCHEMA.encode() + b'"'))

        chain_input = [b_blob, f1_blob]
        for index in (0, 8, 15, 40, len(f1_blob) // 2, len(f1_blob) - 1):
            flipped = bytearray(f1_blob)
            flipped[index] ^= 0x55
            try:
                verifier.verify_chain([chain_input[0], bytes(flipped)], release.signers,
                                      rollback.signers, b_id)
            except verifier.Reject:
                pass
            else:
                raise AssertionError(f"mutation at {index} accepted")
        del chain_input

        print("chain fixture: pinned baseline 9d62f0e5, two forwards, two ancestor rollbacks")
        print("sshsig: model and this verifier accept each other's real ssh-keygen Ed25519 signatures; "
              "interop is ssh-keygen armor only, not arbitrary OpenSSH signature dialects")
        print("principals: fixed fixture principal strings only; not a general allowed-signers format")
        print("keys: distinct files sharing one underlying key refused; rollback key cannot release")
        print("difference: this verifier refuses a forward that reissues earlier bytes; the model accepts it")
        print("rollback: exact older ancestor only; predecessor and unknown source refused")
        print("LIMITATION: host-only self-test; no image, userdata, device, durability, or hardware anti-replay")


if __name__ == "__main__":
    run_tests()
    print("ALL TESTS PASSED")
