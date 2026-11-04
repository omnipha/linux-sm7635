#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile

NAMESPACE = "omnipha-persistent-root-migration@1"
RELEASE_PRINCIPAL = "omnipha-release"
IMAGE_PRINCIPAL = "omnipha-image-attestor"
DEVICE = "nothing-asteroids"
CHANNEL = "persistent-root"
TARGET_PATHS = (
    "etc/local.d/10-omnipha-self-stage.start",
    "usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh",
    "usr/libexec/omnipha/pmos-self-post-fresh-boot.sh",
)
RUN113_PINS = {
    "init_boot_sha256":
        "d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c",
    "vendor_boot_b_sha256":
        "221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500",
}
RUN113_FILES = {
    "etc/local.d/10-omnipha-self-stage.start":
        "3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67",
    "usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh":
        "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14",
    "usr/libexec/omnipha/pmos-self-post-fresh-boot.sh":
        "113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3",
}
BAD_RADIO_SHA256 = (
    "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3")
DENYLIST = frozenset((BAD_RADIO_SHA256,))
ZERO_DIGEST = "0" * 64
MANIFEST_MAX = 4096
FILE_MAX = 65536
GENERATION_MAX = 1 << 31
MODE = "0700"
TOP_KEYS = frozenset((
    "device", "channel", "generation", "predecessor", "boot_pins", "files",
    "rollback"))
PREDECESSOR_KEYS = frozenset(("generation", "manifest_sha256", "authorizes"))
PINS_KEYS = frozenset(("init_boot_sha256", "vendor_boot_b_sha256"))
FILE_KEYS = frozenset(("path", "mode", "size", "sha256"))
ROLLBACK_KEYS = frozenset(("allowed", "to_generation"))
ATTESTATION_KEYS = frozenset(("type", "boot_pins", "files"))
AUTHORIZATIONS = (["forward"], ["forward", "rollback"])
LIMITATION = (
    "LIMITATION: NON-DEPLOYABLE host-only model. It abstracts the filesystem "
    "as ordinary host directories with os.fsync/os.replace; it proves nothing "
    "about a real device, ext4 journaling, power-cut durability, the pre-SSH "
    "boot image, or any production installer or cutover.")


class Refused(Exception):
    pass


def refuse(message):
    raise Refused(message)


def run(command):
    return subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def is_hex(value):
    return (isinstance(value, str) and len(value) == 64 and
            all(char in "0123456789abcdef" for char in value))


def is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            refuse("duplicate JSON object key")
        result[key] = value
    return result


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode() + b"\n"


def load_strict(raw, limit):
    if not isinstance(raw, bytes) or not raw or len(raw) > limit:
        refuse("document is not bounded non-empty bytes")
    if b"\r" in raw or b"\0" in raw:
        refuse("document contains forbidden bytes")
    try:
        value = json.loads(raw.decode("ascii"),
                           object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        refuse("document is not strict ASCII JSON")
    if canonical(value) != raw:
        refuse("document is not the canonical deterministic encoding")
    return value


def check_pins(value, label):
    if not isinstance(value, dict) or frozenset(value) != PINS_KEYS:
        refuse(label + " boot pins key set is not exact")
    for key in sorted(PINS_KEYS):
        if not is_hex(value[key]):
            refuse(label + " boot pin " + key + " is not a sha256")


def check_digest_map(value, label):
    if not isinstance(value, dict) or frozenset(value) != frozenset(TARGET_PATHS):
        refuse(label + " file set is not the exact three known target paths")
    for path in TARGET_PATHS:
        if not is_hex(value[path]):
            refuse(label + " digest for " + path + " is not a sha256")
        if value[path] in DENYLIST:
            refuse(label + " digest for " + path + " is denylisted")


def parse_manifest(raw):
    value = load_strict(raw, MANIFEST_MAX)
    if not isinstance(value, dict) or frozenset(value) != TOP_KEYS:
        refuse("manifest top-level key set is not exact")
    if value["device"] != DEVICE or value["channel"] != CHANNEL:
        refuse("manifest device or channel mismatch")
    generation = value["generation"]
    if not is_plain_int(generation) or not 0 < generation < GENERATION_MAX:
        refuse("manifest generation is not a bounded positive integer")
    predecessor = value["predecessor"]
    if not isinstance(predecessor, dict) or frozenset(predecessor) != PREDECESSOR_KEYS:
        refuse("predecessor key set is not exact")
    if not is_plain_int(predecessor["generation"]):
        refuse("predecessor generation is not an integer")
    if predecessor["generation"] != generation - 1:
        refuse("predecessor generation is not the immediately earlier one")
    if not is_hex(predecessor["manifest_sha256"]):
        refuse("predecessor digest is not a sha256")
    if (predecessor["generation"] == 0) != (
            predecessor["manifest_sha256"] == ZERO_DIGEST):
        refuse("only the genesis predecessor may carry the zero digest")
    if predecessor["authorizes"] not in AUTHORIZATIONS:
        refuse("predecessor authorization is not explicit forward or rollback")
    check_pins(value["boot_pins"], "manifest")
    files = value["files"]
    if not isinstance(files, list) or len(files) != len(TARGET_PATHS):
        refuse("files is not the exact list of three entries")
    digests = {}
    for entry in files:
        if not isinstance(entry, dict) or frozenset(entry) != FILE_KEYS:
            refuse("file entry key set is not exact")
        path = entry["path"]
        if not isinstance(path, str) or not path or path.startswith("/"):
            refuse("file path is not a relative path")
        if any(part in ("", ".", "..") for part in path.split("/")):
            refuse("file path traverses or is malformed")
        if path not in TARGET_PATHS:
            refuse("unknown file path " + path)
        if path in digests:
            refuse("duplicate file path")
        if entry["mode"] != MODE:
            refuse("file mode is not the pinned root-only mode")
        if not is_plain_int(entry["size"]) or not 0 < entry["size"] <= FILE_MAX:
            refuse("file size is not a bounded positive integer")
        if not is_hex(entry["sha256"]):
            refuse("file digest is not a sha256")
        digests[path] = entry["sha256"]
    check_digest_map(digests, "manifest")
    if [entry["path"] for entry in files] != sorted(TARGET_PATHS):
        refuse("file entries are not in canonical path order")
    rollback = value["rollback"]
    if not isinstance(rollback, dict) or frozenset(rollback) != ROLLBACK_KEYS:
        refuse("rollback key set is not exact")
    if not isinstance(rollback["allowed"], bool):
        refuse("rollback allowance is not a boolean")
    if rollback["allowed"] != ("rollback" in predecessor["authorizes"]):
        refuse("rollback allowance contradicts predecessor authorization")
    if (not is_plain_int(rollback["to_generation"]) or
            rollback["to_generation"] != predecessor["generation"]):
        refuse("rollback target is not the predecessor generation")
    return value


def parse_attestation(raw):
    value = load_strict(raw, MANIFEST_MAX)
    if not isinstance(value, dict) or frozenset(value) != ATTESTATION_KEYS:
        refuse("attestation key set is not exact")
    if value["type"] != "pre-ssh-image":
        refuse("attestation type mismatch")
    check_pins(value["boot_pins"], "attestation")
    check_digest_map(value["files"], "attestation")
    return value


def manifest_digests(manifest):
    return {entry["path"]: entry["sha256"] for entry in manifest["files"]}


class Anchor:
    def __init__(self, directory, base_pins, base_files):
        self.dir = pathlib.Path(directory)
        self.dir.mkdir(parents=True)
        self.signers = self.dir / "allowed_signers"
        self.keys = {}
        self.base_pins = dict(base_pins)
        self.base_files = dict(base_files)
        self.attested = []
        for principal in (RELEASE_PRINCIPAL, IMAGE_PRINCIPAL):
            self.keys[principal] = self.make_key(principal)
        lines = []
        for principal in (RELEASE_PRINCIPAL, IMAGE_PRINCIPAL):
            public = pathlib.Path(str(self.keys[principal]) + ".pub")
            fields = public.read_text().split()
            lines.append(principal + ' namespaces="' + NAMESPACE + '" ' +
                         fields[0] + " " + fields[1] + "\n")
        self.signers.write_text("".join(lines))
        self.floor_path = self.dir / "floor"
        self.set_floor(0)

    def make_key(self, name):
        key = self.dir / (name + ".key")
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name,
             "-f", str(key)])
        return key

    def set_floor(self, value):
        temp = self.dir / "floor.tmp"
        temp.write_text(str(value) + "\n")
        os.replace(temp, self.floor_path)

    def floor(self):
        return int(self.floor_path.read_text())

    def sign(self, key, payload, namespace=NAMESPACE):
        with tempfile.TemporaryDirectory() as scratch:
            message = pathlib.Path(scratch) / "payload"
            message.write_bytes(payload)
            run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n",
                 namespace, str(message)])
            return pathlib.Path(str(message) + ".sig").read_bytes()

    def verify(self, principal, payload, signature, namespace=NAMESPACE):
        with tempfile.TemporaryDirectory() as scratch:
            sig = pathlib.Path(scratch) / "payload.sig"
            sig.write_bytes(signature)
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(self.signers), "-I",
                 principal, "-n", namespace, "-s", str(sig)],
                input=payload, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=False)
            return result.returncode == 0

    def check_signature(self, principal, payload, signature):
        if not self.verify(principal, payload, signature):
            refuse("signature invalid for " + principal)

    def assert_outside(self, store_root):
        if self.dir.resolve().is_relative_to(pathlib.Path(store_root).resolve()):
            refuse("signer trust anchor lives inside the mutable store")

    def accept_attestation(self, raw, signature):
        value = parse_attestation(raw)
        self.check_signature(IMAGE_PRINCIPAL, raw, signature)
        if value["boot_pins"] == self.base_pins:
            refuse("attestation does not describe a changed pre-SSH image")
        self.attested.append((value["boot_pins"], value["files"]))

    def check_policy(self, manifest):
        pins = manifest["boot_pins"]
        files = manifest_digests(manifest)
        if pins == self.base_pins:
            if files != self.base_files:
                refuse("userdata manifest cannot change files enforced by "
                       "the installed pre-SSH image")
            return
        if (pins, files) not in self.attested:
            refuse("changed boot pins and files lack an independent "
                   "image attestation")


class Release:
    def __init__(self, manifest, raw, blobs, signature):
        self.manifest = manifest
        self.raw = raw
        self.blobs = blobs
        self.signature = signature

    def digest(self):
        return sha256_hex(self.raw)


def make_release(anchor, blobs, generation, previous, authorizes, pins,
                 key=None, namespace=NAMESPACE):
    files = [{"path": path, "mode": MODE, "size": len(blobs[path]),
              "sha256": sha256_hex(blobs[path])} for path in sorted(TARGET_PATHS)]
    if previous is None:
        predecessor_generation = 0
        predecessor_digest = ZERO_DIGEST
        authorization = ["forward"]
    else:
        predecessor_generation = previous.manifest["generation"]
        predecessor_digest = previous.digest()
        authorization = list(authorizes)
    predecessor = {"generation": predecessor_generation,
                   "manifest_sha256": predecessor_digest,
                   "authorizes": authorization}
    manifest = {"device": DEVICE, "channel": CHANNEL, "generation": generation,
                "predecessor": predecessor, "boot_pins": dict(pins),
                "files": files,
                "rollback": {"allowed": "rollback" in authorization,
                             "to_generation": predecessor_generation}}
    raw = canonical(manifest)
    signature = anchor.sign(key or anchor.keys[RELEASE_PRINCIPAL], raw, namespace)
    return Release(manifest, raw, blobs, signature)


def blobs_for(tag):
    return {path: ("omnipha host-only fixture " + tag + " " + path +
                   "\n").encode() * 3 for path in TARGET_PATHS}


def fsync_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Plan:
    def __init__(self, stage, commit):
        self.stage = stage
        self.commit = commit

    def steps(self):
        return self.stage + self.commit


class Store:
    def __init__(self, root, anchor):
        self.root = pathlib.Path(root)
        self.anchor = anchor
        self.root.mkdir(parents=True)
        self.slots = {}
        for name in ("A", "B"):
            self.slots[name] = self.root / ("slot-" + name.lower())
            self.slots[name].mkdir()
        self.selector = self.root / "selector"
        self.selector.write_bytes(b"A\n")

    @staticmethod
    def other(name):
        return "B" if name == "A" else "A"

    def read_selector(self):
        try:
            value = self.selector.read_bytes()
        except OSError as exc:
            raise Refused("selector is unreadable") from exc
        if value == b"A\n":
            return "A"
        if value == b"B\n":
            return "B"
        refuse("selector is not exactly one known slot name")

    def selector_steps(self, name):
        temp = self.root / "selector.tmp"

        def write_temp():
            with open(temp, "wb") as handle:
                handle.write((name + "\n").encode())
                handle.flush()
                os.fsync(handle.fileno())

        def replace():
            os.replace(temp, self.selector)
            fsync_path(self.root)

        return [write_temp, replace]

    def stage_steps(self, name, release):
        slot = self.slots[name]

        def clear():
            for child in slot.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            for path in TARGET_PATHS:
                (slot / path).parent.mkdir(parents=True, exist_ok=True)

        def first_half(path):
            def action():
                data = release.blobs[path]
                fd = os.open(slot / path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                             0o600)
                try:
                    os.write(fd, data[:len(data) // 2])
                finally:
                    os.close(fd)
            return action

        def second_half(path):
            def action():
                data = release.blobs[path]
                fd = os.open(slot / path, os.O_WRONLY | os.O_APPEND)
                try:
                    os.write(fd, data[len(data) // 2:])
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.chmod(slot / path, int(MODE, 8))
            return action

        def write_manifest():
            (slot / "manifest").write_bytes(release.raw)

        def write_signature():
            (slot / "manifest.sig").write_bytes(release.signature)

        def sync_slot():
            fsync_path(slot / "manifest")
            fsync_path(slot / "manifest.sig")
            fsync_path(slot)

        steps = [clear]
        for path in TARGET_PATHS:
            steps.append(first_half(path))
            steps.append(second_half(path))
        steps.extend([write_manifest, write_signature, sync_slot])
        return steps

    def verify_slot(self, name):
        try:
            return self.verify_slot_unchecked(name)
        except OSError as exc:
            raise Refused("slot " + name + " is unreadable or incomplete: " +
                          type(exc).__name__) from exc

    def verify_slot_unchecked(self, name):
        slot = self.slots[name]
        raw = (slot / "manifest").read_bytes()
        manifest = parse_manifest(raw)
        self.anchor.check_signature(
            RELEASE_PRINCIPAL, raw, (slot / "manifest.sig").read_bytes())
        self.anchor.check_policy(manifest)
        allowed = set(TARGET_PATHS) | {"manifest", "manifest.sig"}
        for current, directories, files in os.walk(slot, followlinks=False):
            base = pathlib.Path(current)
            for directory in directories:
                if (base / directory).is_symlink():
                    refuse("slot contains a symlinked directory")
            for filename in files:
                relative = (base / filename).relative_to(slot).as_posix()
                if relative not in allowed:
                    refuse("slot contains unknown or colliding file " + relative)
        for entry in manifest["files"]:
            target = slot / entry["path"]
            if target.is_symlink():
                refuse(entry["path"] + " is a symlink")
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode):
                refuse(entry["path"] + " is not a regular file")
            if info.st_nlink != 1:
                refuse(entry["path"] + " has extra hard links")
            if stat.S_IMODE(info.st_mode) != int(MODE, 8):
                refuse(entry["path"] + " mode differs from the manifest")
            data = target.read_bytes()
            if len(data) != entry["size"]:
                refuse(entry["path"] + " size differs from the manifest")
            if sha256_hex(data) != entry["sha256"]:
                refuse(entry["path"] + " digest differs from the manifest")
        return manifest, sha256_hex(raw)

    def boot(self):
        name = self.read_selector()
        manifest, digest = self.verify_slot(name)
        if manifest["generation"] < self.anchor.floor():
            refuse("selected generation is below the trusted rollback floor")
        return name, manifest, digest

    def check_release(self, release):
        manifest = parse_manifest(release.raw)
        if manifest != release.manifest:
            refuse("release object differs from its signed bytes")
        self.anchor.check_signature(
            RELEASE_PRINCIPAL, release.raw, release.signature)
        self.anchor.check_policy(manifest)
        for entry in manifest["files"]:
            data = release.blobs[entry["path"]]
            if len(data) != entry["size"] or sha256_hex(data) != entry["sha256"]:
                refuse("release payload differs from its signed manifest")
        return manifest

    def plan_provision(self, release):
        manifest = self.check_release(release)
        if manifest["generation"] != 1:
            refuse("only generation 1 may be provisioned")
        steps = self.stage_steps("A", release)

        def verify():
            self.verify_slot("A")

        def raise_floor():
            self.anchor.set_floor(1)

        return Plan(steps, [verify] + self.selector_steps("A") + [raise_floor])

    def plan_install(self, release):
        manifest = self.check_release(release)
        name, current, digest = self.boot()
        predecessor = manifest["predecessor"]
        if predecessor["generation"] != current["generation"]:
            refuse("release predecessor generation is not the current state")
        if predecessor["manifest_sha256"] != digest:
            refuse("release does not name the current generation digest")
        target = self.other(name)

        def verify():
            self.verify_slot(target)

        def raise_floor():
            self.anchor.set_floor(manifest["generation"])

        return Plan(self.stage_steps(target, release),
                    [verify] + self.selector_steps(target) + [raise_floor])

    def plan_rollback(self):
        name, current, _ = self.boot()
        if not current["rollback"]["allowed"]:
            refuse("current generation does not authorize rollback")
        target = self.other(name)
        previous, previous_digest = self.verify_slot(target)
        if previous["generation"] != current["rollback"]["to_generation"]:
            refuse("rollback target is not the authorized generation")
        if previous_digest != current["predecessor"]["manifest_sha256"]:
            refuse("rollback target is not the authorized predecessor digest")
        if (previous["boot_pins"] != current["boot_pins"] or
                manifest_digests(previous) != manifest_digests(current)):
            refuse("rollback would need a different pre-SSH image")

        def lower_floor():
            self.anchor.set_floor(previous["generation"])

        return Plan([], [lower_floor] + self.selector_steps(target))

    @staticmethod
    def execute(plan, count=None):
        steps = plan.steps()
        for action in steps if count is None else steps[:count]:
            action()


def expect_refused(label, action):
    try:
        action()
    except Refused:
        return
    raise AssertionError(label + ": refusal expected but none occurred")


def edited(raw, edit):
    value = json.loads(raw)
    edit(value)
    return canonical(value)


def make_world(root, tag):
    anchor = Anchor(root / (tag + "-anchor"), RUN113_PINS, base_files_for_fixture())
    store = Store(root / (tag + "-store"), anchor)
    anchor.assert_outside(store.root)
    return anchor, store


def base_files_for_fixture():
    return {path: sha256_hex(data) for path, data in blobs_for("base").items()}


def provisioned(root, tag):
    anchor, store = make_world(root, tag)
    genesis = make_release(anchor, blobs_for("base"), 1, None, None, RUN113_PINS)
    store.execute(store.plan_provision(genesis))
    return anchor, store, genesis


def test_signatures(root):
    anchor, _ = make_world(root, "sig")
    payload = canonical({"probe": 1})
    signature = anchor.sign(anchor.keys[RELEASE_PRINCIPAL], payload)
    assert anchor.verify(RELEASE_PRINCIPAL, payload, signature)
    assert not anchor.verify(RELEASE_PRINCIPAL, payload + b" ", signature)
    assert not anchor.verify(RELEASE_PRINCIPAL, payload, signature[:-8])
    assert not anchor.verify(IMAGE_PRINCIPAL, payload, signature)
    other_ns = anchor.sign(anchor.keys[RELEASE_PRINCIPAL], payload, "other-ns@1")
    assert not anchor.verify(RELEASE_PRINCIPAL, payload, other_ns)
    assert not anchor.verify(RELEASE_PRINCIPAL, payload, other_ns, "other-ns@1")
    stranger = anchor.make_key("stranger")
    forged = anchor.sign(stranger, payload)
    assert not anchor.verify(RELEASE_PRINCIPAL, payload, forged)
    assert not anchor.verify("stranger", payload, forged)
    image_signed = anchor.sign(anchor.keys[IMAGE_PRINCIPAL], payload)
    assert not anchor.verify(RELEASE_PRINCIPAL, payload, image_signed)
    assert anchor.verify(IMAGE_PRINCIPAL, payload, image_signed)
    print("ssh-keygen: Ed25519 SSHSIG accepts only exact payload, signer and "
          "namespace; tamper, truncation, wrong key, wrong principal and wrong "
          "namespace all rejected")


def test_anchor_placement(root):
    anchor, store = make_world(root, "placement")
    inside = Anchor(store.root / "inner-anchor", RUN113_PINS, {})
    expect_refused("anchor inside store", lambda: inside.assert_outside(store.root))
    outside_release = make_release(
        anchor, blobs_for("base"), 1, None, None, RUN113_PINS,
        key=inside.keys[RELEASE_PRINCIPAL])
    expect_refused("store-local signer",
                   lambda: store.plan_provision(outside_release))
    print("trust anchor: a signer anchor inside the mutable store is refused "
          "and a release signed by a store-local key is not trusted")


def test_manifest_schema(root):
    anchor, _ = make_world(root, "schema")
    release = make_release(anchor, blobs_for("base"), 1, None, None, RUN113_PINS)
    raw = release.raw
    assert parse_manifest(raw)["generation"] == 1
    duplicate = raw[:-2] + b',"device":"' + DEVICE.encode() + b'"}\n'
    cases = {
        "duplicate keys": duplicate,
        "extra top field": edited(raw, lambda v: v.update(extra=1)),
        "missing top field": edited(raw, lambda v: v.pop("rollback")),
        "extra file field": edited(raw, lambda v: v["files"][0].update(x=1)),
        "path traversal": edited(
            raw, lambda v: v["files"][0].update(path="../etc/shadow")),
        "absolute path": edited(
            raw, lambda v: v["files"][0].update(path="/" + TARGET_PATHS[0])),
        "dot segment": edited(
            raw, lambda v: v["files"][0].update(path="etc/./local.d/x")),
        "unknown file": edited(
            raw, lambda v: v["files"][0].update(path="etc/local.d/99-extra.start")),
        "duplicate file": edited(
            raw, lambda v: v["files"][1].update(path=v["files"][0]["path"])),
        "fourth file": edited(
            raw, lambda v: v["files"].append(dict(v["files"][0]))),
        "two files": edited(raw, lambda v: v["files"].pop()),
        "wrong order": edited(raw, lambda v: v["files"].reverse()),
        "loose mode": edited(raw, lambda v: v["files"][0].update(mode="0755")),
        "numeric mode": edited(raw, lambda v: v["files"][0].update(mode=448)),
        "string size": edited(raw, lambda v: v["files"][0].update(size="10")),
        "float size": edited(raw, lambda v: v["files"][0].update(size=10.0)),
        "bool size": edited(raw, lambda v: v["files"][0].update(size=True)),
        "zero size": edited(raw, lambda v: v["files"][0].update(size=0)),
        "negative size": edited(raw, lambda v: v["files"][0].update(size=-1)),
        "huge size": edited(
            raw, lambda v: v["files"][0].update(size=FILE_MAX + 1)),
        "short digest": edited(raw, lambda v: v["files"][0].update(sha256="ab")),
        "upper digest": edited(
            raw, lambda v: v["files"][0].update(sha256="A" * 64)),
        "string generation": edited(raw, lambda v: v.update(generation="1")),
        "bool generation": edited(raw, lambda v: v.update(generation=True)),
        "zero generation": edited(raw, lambda v: v.update(generation=0)),
        "huge generation": edited(
            raw, lambda v: v.update(generation=GENERATION_MAX)),
        "wrong device": edited(raw, lambda v: v.update(device="other")),
        "wrong channel": edited(raw, lambda v: v.update(channel="other")),
        "implicit rollback": edited(
            raw, lambda v: v["rollback"].update(allowed=True)),
        "rollback target": edited(
            raw, lambda v: v["rollback"].update(to_generation=5)),
        "unknown authorization": edited(
            raw, lambda v: v["predecessor"].update(authorizes=["sideways"])),
        "rollback only": edited(
            raw, lambda v: v["predecessor"].update(authorizes=["rollback"])),
        "predecessor skip": edited(
            raw, lambda v: v["predecessor"].update(generation=5)),
        "zero digest later": edited(
            raw, lambda v: v.update(generation=2)),
        "short pin": edited(
            raw, lambda v: v["boot_pins"].update(init_boot_sha256="ab")),
        "extra pin": edited(raw, lambda v: v["boot_pins"].update(x="0" * 64)),
        "not canonical": raw.replace(b",", b", ", 1),
        "no newline": raw[:-1],
        "crlf": raw.replace(b"\n", b"\r\n"),
        "nul byte": raw + b"\0",
        "non ascii": raw.replace(b"omnipha", "omnipha\u00e9".encode(), 1),
        "oversized": b"{" + b" " * MANIFEST_MAX + b"}\n",
        "empty": b"",
        "not json": b"not json\n",
        "array": b"[]\n",
        "nan size": raw.replace(b'"size":', b'"size":NaN,"x":', 1),
        "text type": "text",
    }
    for label, payload in cases.items():
        expect_refused(label, lambda p=payload: parse_manifest(p))
    print("schema: " + str(len(cases)) + " strict manifest mutations refused")


def test_denylist_and_pins(root):
    anchor, store, genesis = provisioned(root, "policy")
    bad_blobs = blobs_for("base")
    forged_manifest = json.loads(genesis.raw)
    forged_manifest["files"][1]["sha256"] = BAD_RADIO_SHA256
    expect_refused("denylisted radio", lambda: parse_manifest(
        canonical(forged_manifest)))
    real = make_release(anchor, {path: b"x" * 10 for path in TARGET_PATHS}, 1,
                        None, None, RUN113_PINS)
    real_manifest = json.loads(real.raw)
    for entry in real_manifest["files"]:
        entry["sha256"] = RUN113_FILES[entry["path"]]
    assert parse_manifest(canonical(real_manifest))["boot_pins"] == RUN113_PINS
    real_manifest["files"][1]["sha256"] = BAD_RADIO_SHA256
    expect_refused("real trio with bad radio",
                   lambda: parse_manifest(canonical(real_manifest)))
    signed_bad = Release(forged_manifest, canonical(forged_manifest), bad_blobs,
                         anchor.sign(anchor.keys[RELEASE_PRINCIPAL],
                                     canonical(forged_manifest)))
    assert anchor.verify(RELEASE_PRINCIPAL, signed_bad.raw, signed_bad.signature)
    expect_refused("signed denylisted radio",
                   lambda: store.plan_install(signed_bad))
    changed = dict(blobs_for("base"))
    changed[TARGET_PATHS[1]] = b"new radio\n"
    bypass = make_release(anchor, changed, 2, genesis, ["forward"], RUN113_PINS)
    assert anchor.verify(RELEASE_PRINCIPAL, bypass.raw, bypass.signature)
    expect_refused("userdata manifest bypass", lambda: store.plan_install(bypass))
    new_pins = {"init_boot_sha256": sha256_hex(b"new init"),
                "vendor_boot_b_sha256": sha256_hex(b"new vendor")}
    pinned = make_release(anchor, changed, 2, genesis, ["forward"], new_pins)
    expect_refused("unattested changed image",
                   lambda: store.plan_install(pinned))
    attestation = canonical({
        "type": "pre-ssh-image", "boot_pins": new_pins,
        "files": {p: sha256_hex(d) for p, d in changed.items()}})
    expect_refused("attestation by release key", lambda: anchor.accept_attestation(
        attestation, anchor.sign(anchor.keys[RELEASE_PRINCIPAL], attestation)))
    expect_refused("unchanged image attestation", lambda: anchor.accept_attestation(
        canonical({"type": "pre-ssh-image", "boot_pins": RUN113_PINS,
                   "files": base_files_for_fixture()}),
        anchor.sign(anchor.keys[IMAGE_PRINCIPAL], canonical(
            {"type": "pre-ssh-image", "boot_pins": RUN113_PINS,
             "files": base_files_for_fixture()}))))
    mismatch = canonical({
        "type": "pre-ssh-image", "boot_pins": new_pins,
        "files": base_files_for_fixture()})
    anchor.accept_attestation(
        mismatch, anchor.sign(anchor.keys[IMAGE_PRINCIPAL], mismatch))
    expect_refused("attested pins with different files",
                   lambda: store.plan_install(pinned))
    anchor.accept_attestation(
        attestation, anchor.sign(anchor.keys[IMAGE_PRINCIPAL], attestation))
    store.execute(store.plan_install(pinned))
    _, manifest, _ = store.boot()
    assert manifest["generation"] == 2 and manifest["boot_pins"] == new_pins
    print("policy: signed denylisted radio and userdata-only file changes "
          "refused; changed files accepted only with an image-signer "
          "attestation binding new boot pins to the same file digests")


def test_install_rollback_and_state(root):
    anchor, store, genesis = provisioned(root, "state")
    assert store.boot()[1]["generation"] == 1 and anchor.floor() == 1
    second = make_release(anchor, blobs_for("base"), 2, genesis,
                          ["forward", "rollback"], RUN113_PINS)
    store.execute(store.plan_install(second))
    _, manifest, digest = store.boot()
    assert manifest["generation"] == 2 and digest == second.digest()
    assert anchor.floor() == 2
    expect_refused("replay of installed release",
                   lambda: store.plan_install(second))
    skipped = make_release(anchor, blobs_for("base"), 4, second, ["forward"],
                           RUN113_PINS)
    expect_refused("skipped generation", lambda: store.plan_install(skipped))
    other_chain = make_release(anchor, blobs_for("base"), 3, genesis, ["forward"],
                               RUN113_PINS)
    expect_refused("wrong predecessor", lambda: store.plan_install(other_chain))
    tampered = Release(second.manifest, second.raw,
                       dict(blobs_for("base"), **{TARGET_PATHS[0]: b"evil\n"}),
                       second.signature)
    expect_refused("payload differs from manifest",
                   lambda: store.plan_install(tampered))
    selector_before = store.selector.read_bytes()
    store.selector.write_bytes(b"A\n")
    expect_refused("selector flipped to older signed slot", lambda: store.boot())
    store.selector.write_bytes(selector_before)
    assert store.boot()[1]["generation"] == 2
    store.execute(store.plan_rollback())
    assert store.boot()[1]["generation"] == 1 and anchor.floor() == 1
    anchor_two, store_two, genesis_two = provisioned(root, "norollback")
    second_two = make_release(anchor_two, blobs_for("base"), 2, genesis_two,
                              ["forward"], RUN113_PINS)
    store_two.execute(store_two.plan_install(second_two))
    expect_refused("unapproved rollback", lambda: store_two.plan_rollback())
    store_two.selector.write_bytes(b"A\n")
    expect_refused("unapproved rollback by selector flip",
                   lambda: store_two.boot())
    forged_slot = store_two.slots["B"]
    forged = edited((forged_slot / "manifest").read_bytes(),
                    lambda v: v.update(generation=40))
    (forged_slot / "manifest").write_bytes(forged)
    store_two.selector.write_bytes(b"B\n")
    expect_refused("forged current state", lambda: store_two.boot())
    print("state: forward install, authorized rollback, replay, skip, wrong "
          "predecessor, payload mismatch, selector-flip downgrade, unapproved "
          "rollback and forged current manifest handled")


def test_interruptions(root):
    anchor, store, genesis = provisioned(root, "cut-probe")
    release = make_release(anchor, blobs_for("base"), 2, genesis,
                           ["forward", "rollback"], RUN113_PINS)
    plan = store.plan_install(release)
    total = len(plan.steps())
    replace_at = len(plan.stage) + 3
    for cut in range(total + 1):
        anchor_c, store_c, genesis_c = provisioned(root, "cut-" + str(cut))
        release_c = make_release(anchor_c, blobs_for("base"), 2, genesis_c,
                                 ["forward", "rollback"], RUN113_PINS)
        store_c.execute(store_c.plan_install(release_c), cut)
        name, manifest, digest = store_c.boot()
        expected = 2 if cut >= replace_at else 1
        assert manifest["generation"] == expected, cut
        assert digest == (release_c if expected == 2 else genesis_c).digest(), cut
        store_c.verify_slot(name)
        if expected == 1:
            store_c.execute(store_c.plan_install(release_c))
            assert store_c.boot()[1]["generation"] == 2
        else:
            expect_refused("replay after commit",
                           lambda s=store_c, r=release_c: s.plan_install(r))
    print("interruption: install cut at each of " + str(total + 1) +
          " points (incl. torn half-written files) boots exactly one whole "
          "verified old or new generation and retry converges")
    for cut in range(len(plan.stage) + 1):
        anchor_m, store_m, genesis_m = provisioned(root, "mis-" + str(cut))
        release_m = make_release(anchor_m, blobs_for("base"), 2, genesis_m,
                                 ["forward"], RUN113_PINS)
        misordered = store_m.plan_install(release_m)
        store_m.execute(Plan(misordered.stage, []), cut)
        store_m.selector.write_bytes(b"B\n")
        try:
            _, manifest_m, _ = store_m.boot()
            assert manifest_m["generation"] in (1, 2)
            assert cut >= len(misordered.stage) - 1
        except Refused:
            assert cut < len(misordered.stage) - 1
    print("interruption: a selector flipped before manifest and signature "
          "are both staged is refused; afterwards it still yields one whole "
          "generation")
    for cut in range(4):
        anchor_r, store_r, genesis_r = provisioned(root, "rb-" + str(cut))
        release_r = make_release(anchor_r, blobs_for("base"), 2, genesis_r,
                                 ["forward", "rollback"], RUN113_PINS)
        store_r.execute(store_r.plan_install(release_r))
        store_r.execute(store_r.plan_rollback(), cut)
        _, manifest, _ = store_r.boot()
        assert manifest["generation"] == (1 if cut >= 3 else 2), cut
    print("interruption: rollback cut at each point boots one whole "
          "generation")


def test_slot_integrity(root):
    _, store, genesis = provisioned(root, "slot")
    slot = store.slots["A"]
    pristine = {path: (slot / path).read_bytes() for path in TARGET_PATHS}

    def restore():
        shutil.rmtree(slot)
        slot.mkdir()
        store.execute(Plan(store.stage_steps("A", genesis), []))
        store.selector.write_bytes(b"A\n")
        assert store.boot()[1]["generation"] == 1
        assert pristine == {p: (slot / p).read_bytes() for p in TARGET_PATHS}

    outside = root / "slot-outside.bin"
    outside.write_bytes(pristine[TARGET_PATHS[0]])
    os.chmod(outside, int(MODE, 8))
    swapped = root / "slot-outside-dir"
    shutil.copytree(slot / "usr", swapped, symlinks=True)

    def unlink_then(path, action):
        (slot / path).unlink()
        action()

    mutations = {
        "missing manifest": lambda: (slot / "manifest").unlink(),
        "corrupt manifest": lambda: (slot / "manifest").write_bytes(
            genesis.raw[:-5]),
        "missing signature": lambda: (slot / "manifest.sig").unlink(),
        "corrupt signature": lambda: (slot / "manifest.sig").write_bytes(
            b"-----BEGIN SSH SIGNATURE-----\n"),
        "empty signature": lambda: (slot / "manifest.sig").write_bytes(b""),
        "missing payload": lambda: (slot / TARGET_PATHS[0]).unlink(),
        "truncated payload": lambda: (slot / TARGET_PATHS[1]).write_bytes(
            pristine[TARGET_PATHS[1]][:-1]),
        "same size flipped payload": lambda: (slot / TARGET_PATHS[2]).write_bytes(
            pristine[TARGET_PATHS[2]][:-1] + b"X"),
        "loosened mode": lambda: os.chmod(slot / TARGET_PATHS[0], 0o755),
        "symlinked payload": lambda: unlink_then(
            TARGET_PATHS[0], lambda: (slot / TARGET_PATHS[0]).symlink_to(outside)),
        "hard linked payload": lambda: unlink_then(
            TARGET_PATHS[0], lambda: os.link(outside, slot / TARGET_PATHS[0])),
        "extra hard link name": lambda: os.link(
            slot / TARGET_PATHS[0], slot / "etc" / "local.d" / "alias"),
        "directory in place of file": lambda: unlink_then(
            TARGET_PATHS[2], lambda: (slot / TARGET_PATHS[2]).mkdir()),
        "symlinked directory": lambda: (
            shutil.rmtree(slot / "usr"), (slot / "usr").symlink_to(swapped)),
        "unknown extra file": lambda: (slot / "extra").write_bytes(b"x"),
        "staging name collision": lambda: (
            slot / (TARGET_PATHS[0] + ".omnipha-new")).write_bytes(b"x"),
        "case collision": lambda: (
            slot / "etc" / "local.d" / "10-OMNIPHA-SELF-STAGE.START").write_bytes(
                pristine[TARGET_PATHS[0]]),
        "denylisted content": lambda: (slot / TARGET_PATHS[1]).write_bytes(
            b"denied\n"),
        "selector garbage": lambda: store.selector.write_bytes(b"C\n"),
        "selector empty": lambda: store.selector.write_bytes(b""),
        "selector two names": lambda: store.selector.write_bytes(b"A\nB\n"),
    }
    for label, mutate in mutations.items():
        mutate()
        expect_refused(label, lambda: store.boot())
        restore()
    other = store.slots["B"]
    expect_refused("never-written slot", lambda: store.verify_slot("B"))
    assert not any(other.iterdir())
    print("integrity: " + str(len(mutations)) + " missing, corrupt, link, "
          "collision and selector corruptions refused; slot restored whole "
          "after each")


def main():
    if shutil.which("ssh-keygen") is None:
        raise SystemExit("FAIL: host ssh-keygen is required")
    with tempfile.TemporaryDirectory(prefix="persistent-root-migration.") as tmp:
        root = pathlib.Path(tmp)
        for test in (test_signatures, test_anchor_placement,
                     test_manifest_schema, test_denylist_and_pins,
                     test_install_rollback_and_state, test_interruptions,
                     test_slot_integrity):
            test(root)
    print(LIMITATION)
    print("persistent-root migration model tests: OK")


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit("FAIL: " + str(exc)) from exc
