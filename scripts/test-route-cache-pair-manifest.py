#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import io
import itertools
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
WRAPPER = HERE / "verify-route-cache-pair-manifest.py"
CANONICAL = HERE / "verify-dependent-pair-manifest.py"
SCHEMA = "omnipha-sm7635-route-cache-pair-v1"
MANIFEST_NAME = "root-contract-route-cache-pair.manifest.json"
IMAGES = (("init_boot_a", "init_boot-route-cache-candidate.img", 8388608),
          ("vendor_boot_b", "vendor_boot_b-route-cache-candidate.img", 100663296))
CANONICAL_SCHEMA = "omnipha-sm7635-dependent-pair-v1"
CANONICAL_MANIFEST = "root-contract-pair.manifest.json"
CANONICAL_IMAGES = (("init_boot_a", "init_boot-root-contract-carrier.img", 8388608),
                    ("vendor_boot_b", "vendor_boot_b-root-contract.img", 100663296))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_image(path, size, prefix):
    with path.open("wb") as stream:
        stream.write(prefix)
        stream.truncate(size)
    path.chmod(0o600)


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def protected_state(paths):
    return [(path.lstat(), path.read_bytes()) for path in paths]


class CandidateManifestTests(unittest.TestCase):
    wrapper: Any
    canonical: Any
    variant: Any
    checker: Any

    @classmethod
    def setUpClass(cls):
        cls.canonical = load(CANONICAL, "candidate_manifest_test_canonical")
        cls.wrapper = load(WRAPPER, "candidate_manifest_test_wrapper")
        cls.variant = cls.wrapper.load("build-init-boot-route-cache-candidate.py", "candidate_manifest_test_variant")
        cls.checker = cls.wrapper.manifest.load(
            "verify-init-boot-psoc-hold-wlan-node.py", "candidate_manifest_test_decode")

    def setUp(self):
        temp_root = pathlib.Path(tempfile.gettempdir()).resolve()
        if temp_root == HERE.parent or temp_root.is_relative_to(HERE.parent):
            temp_root = pathlib.Path("/tmp").resolve()
        self.assertFalse(temp_root == HERE.parent or temp_root.is_relative_to(HERE.parent))
        self.temp = tempfile.TemporaryDirectory(prefix="route-cache-manifest.", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.init = self.root / IMAGES[0][1]
        self.carrier = self.root / IMAGES[1][1]
        self.manifest_path = self.root / MANIFEST_NAME
        self.lock = self.root / "build.lock"
        self.refs = tuple(self.root / name for name in ("stock-init", "base-image", "stock-carrier"))
        self.ref_contents = (b"stock init\n", b"base image\n", b"stock carrier\n")
        for path, content in zip(self.refs, self.ref_contents):
            path.write_bytes(content)
        create_image(self.init, IMAGES[0][2], b"candidate init\n")
        create_image(self.carrier, IMAGES[1][2], b"candidate carrier\n")
        self.digests = (digest_file(self.init), digest_file(self.carrier))
        self.canonical_paths = (self.root / CANONICAL_IMAGES[0][1], self.root / CANONICAL_IMAGES[1][1],
                                self.root / CANONICAL_MANIFEST)
        for path, content in zip(self.canonical_paths, (b"canonical init\n", b"canonical carrier\n",
                                                       b"historical generic manifest\n")):
            path.write_bytes(content)
            path.chmod(0o600)
        self.canonical_state = protected_state(self.canonical_paths)
        self.library = object()
        self.after_snapshot = None
        self.bad_digest = False
        self.calls = 0
        self.real_load = self.wrapper.load
        self.real_manifest_load = self.wrapper.manifest.load
        self.addCleanup(mock.patch.object(self.wrapper, "load", side_effect=self.load_variant).start().stop)
        self.addCleanup(mock.patch.object(self.wrapper.manifest, "load", side_effect=self.load_checker).start().stop)
        self.addCleanup(mock.patch.object(self.variant.verifier.base, "lz4", return_value=self.library).start().stop)
        self.addCleanup(mock.patch.object(self.variant, "verify_candidate", side_effect=self.verify_candidate).start().stop)

    def load_variant(self, filename, name):
        self.assertEqual(filename, "build-init-boot-route-cache-candidate.py")
        self.assertEqual(name, "route_cache_pair_variant")
        return self.variant

    def load_checker(self, filename, name):
        self.assertEqual(filename, "verify-init-boot-psoc-hold-wlan-node.py")
        self.assertEqual(name, "route_cache_pair_decode")
        return self.checker

    def verify_candidate(self, init, carrier, stock, base, stock_carrier, library, decode_frame):
        self.calls += 1
        self.assertEqual((len(init), len(carrier)), (IMAGES[0][2], IMAGES[1][2]))
        self.assertEqual((stock, base, stock_carrier), self.ref_contents)
        self.assertIs(library, self.library)
        self.assertIs(decode_frame, self.checker.hostkey_checker.decode_frame)
        digests = (hashlib.sha256(init).hexdigest(), hashlib.sha256(carrier).hexdigest())
        if self.after_snapshot is not None:
            self.after_snapshot()
        if self.bad_digest:
            digests = ("0" * 64, digests[1])
        return (*digests, 123, 456)

    def invoke(self, action, paths=None, lock=None, extra=()):
        init, carrier, manifest = paths or (self.init, self.carrier, self.manifest_path)
        args = [str(WRAPPER), action, str(init), str(carrier), str(manifest)]
        if action != "invalidate":
            args.extend(map(str, self.refs))
        args.append(str(lock or self.lock))
        args.extend(map(str, extra))
        output = io.StringIO()
        with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.wrapper.main()
        return output.getvalue()

    def assert_canonical_unchanged(self):
        self.assertEqual(protected_state(self.canonical_paths), self.canonical_state)

    def replace_image(self, path):
        replacement = self.root / "replacement"
        if path == self.init:
            create_image(replacement, IMAGES[0][2], b"candidate init\n")
        else:
            create_image(replacement, IMAGES[1][2], b"candidate carrier\n")
        old = path.stat()
        os.replace(replacement, path)
        self.assertNotEqual((old.st_dev, old.st_ino), (path.stat().st_dev, path.stat().st_ino))

    def test_constants_and_canonical_isolation(self):
        wrapper = self.wrapper
        canonical = self.canonical
        self.assertEqual((wrapper.SCHEMA, wrapper.MANIFEST_NAME, wrapper.IMAGES), (SCHEMA, MANIFEST_NAME, IMAGES))
        self.assertEqual((canonical.SCHEMA, canonical.MANIFEST_NAME, canonical.IMAGES),
                         (CANONICAL_SCHEMA, CANONICAL_MANIFEST, CANONICAL_IMAGES))
        self.assertIsNot(wrapper.manifest, canonical)
        self.assertEqual(wrapper.manifest.paths(self.init, self.carrier, self.manifest_path),
                         (self.init, self.carrier, self.manifest_path))
        canonical_value = canonical.declaration(self.digests)
        canonical.check_manifest(canonical_value, self.digests)
        wrong_schema = dict(canonical_value, schema=SCHEMA)
        with self.assertRaises(ValueError):
            canonical.check_manifest(wrong_schema, self.digests)
        candidate_value = wrapper.manifest.declaration(self.digests)
        wrapper.manifest.check_manifest(candidate_value, self.digests)
        with self.assertRaises(ValueError):
            canonical.check_manifest(candidate_value, self.digests)
        with self.assertRaises(ValueError):
            wrapper.manifest.check_manifest(dict(candidate_value, schema=CANONICAL_SCHEMA), self.digests)
        self.assert_canonical_unchanged()

    def test_write_verify_invalidate_and_inherited_lock(self):
        output = self.invoke("write")
        self.assertIn(f"write: {MANIFEST_NAME}", output)
        self.assertEqual(self.calls, 1)
        info = self.manifest_path.lstat()
        self.assertEqual((stat.S_IMODE(info.st_mode), info.st_nlink), (0o600, 1))
        value = json.loads(self.manifest_path.read_text())
        self.assertEqual(value, {"schema": SCHEMA, "images": [
            {"partition": partition, "filename": filename, "size": size, "sha256": digest}
            for (partition, filename, size), digest in zip(IMAGES, self.digests)
        ]})
        output = self.invoke("verify")
        self.assertIn(f"init_boot_a {self.digests[0]}", output)
        self.assertIn(f"vendor_boot_b {self.digests[1]}", output)
        fd = os.open(self.lock, os.O_RDWR)
        try:
            self.invoke("verify", extra=("--lock-fd", fd))
        finally:
            os.close(fd)
        self.assertEqual(self.calls, 3)
        self.invoke("invalidate")
        self.assertFalse(self.manifest_path.exists())
        self.invoke("invalidate")
        self.assert_canonical_unchanged()

    def test_mixed_canonical_paths_rejected_before_lock(self):
        self.manifest_path.write_text("candidate manifest sentinel\n")
        self.manifest_path.chmod(0o600)
        candidate_state = self.manifest_path.read_bytes()
        choices = ((self.init, self.canonical_paths[0]), (self.carrier, self.canonical_paths[1]),
                   (self.manifest_path, self.canonical_paths[2]))
        for index, paths in enumerate(itertools.product(*choices)):
            if paths == (self.init, self.carrier, self.manifest_path):
                continue
            for action in ("write", "verify", "invalidate"):
                with self.subTest(paths=paths, action=action):
                    lock = self.root / f"rejected-{index}-{action}.lock"
                    with self.assertRaises(ValueError):
                        self.invoke(action, paths=paths, lock=lock)
                    self.assertFalse(lock.exists())
                    self.assertEqual(self.manifest_path.read_bytes(), candidate_state)
                    self.assert_canonical_unchanged()
        self.assertEqual(self.calls, 0)

    def test_image_modes_symlinks_and_hardlinks_rejected(self):
        self.invoke("write")
        for path in (self.init, self.carrier):
            with self.subTest(path=path.name, kind="mode"):
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    self.invoke("verify")
                path.chmod(0o600)
            with self.subTest(path=path.name, kind="symlink"):
                target = self.root / "image-target"
                path.rename(target)
                path.symlink_to(target)
                with self.assertRaises(OSError):
                    self.invoke("verify")
                path.unlink()
                target.rename(path)
            with self.subTest(path=path.name, kind="hardlink"):
                link = self.root / "image-hardlink"
                os.link(path, link)
                with self.assertRaises(ValueError):
                    self.invoke("verify")
                link.unlink()
        self.assertEqual(self.calls, 1)
        self.assert_canonical_unchanged()

    def test_unsafe_manifest_and_canonical_alias_rejected(self):
        self.invoke("write")
        original = self.manifest_path.read_bytes()
        self.manifest_path.chmod(0o644)
        for action in ("write", "verify", "invalidate"):
            with self.subTest(kind="mode", action=action), self.assertRaises(ValueError):
                self.invoke(action)
        self.assertEqual(self.manifest_path.read_bytes(), original)
        self.manifest_path.chmod(0o600)
        self.manifest_path.unlink()
        for kind in ("symlink", "hardlink"):
            if kind == "symlink":
                self.manifest_path.symlink_to(self.canonical_paths[2])
            else:
                os.link(self.canonical_paths[2], self.manifest_path)
            for action in ("write", "verify", "invalidate"):
                with self.subTest(kind=kind, action=action), self.assertRaises((ValueError, OSError)):
                    self.invoke(action)
            self.assertEqual(self.canonical_paths[2].read_bytes(), self.canonical_state[2][1])
            self.manifest_path.unlink()
        self.assertEqual(self.calls, 1)
        self.assertEqual([path.read_bytes() for path in self.canonical_paths],
                         [state[1] for state in self.canonical_state])

    def test_replaced_images_rejected_even_if_content_unchanged(self):
        for path in (self.init, self.carrier):
            with self.subTest(path=path.name):
                self.after_snapshot = lambda path=path: self.replace_image(path)
                with self.assertRaisesRegex(ValueError, "image changed after verification"):
                    self.invoke("write")
                self.after_snapshot = None
                self.assertFalse(self.manifest_path.exists())
                self.assertEqual((digest_file(self.init), digest_file(self.carrier)), self.digests)
        self.assert_canonical_unchanged()

    def test_publication_revalidates_and_cleans_up_on_replacement(self):
        original_unchanged = self.wrapper.manifest.unchanged
        calls = 0

        def replace_before_publish(path, size, digest, identity):
            nonlocal calls
            calls += 1
            if calls == 4:
                self.replace_image(self.carrier)
            return original_unchanged(path, size, digest, identity)

        with (mock.patch.object(self.wrapper.manifest, "unchanged", side_effect=replace_before_publish),
              self.assertRaisesRegex(ValueError, "image changed after verification")):
            self.invoke("write")
        self.assertEqual(calls, 4)
        self.assertFalse(self.manifest_path.exists())
        self.assertFalse(self.manifest_path.with_name(MANIFEST_NAME + ".omnipha-new").exists())
        self.assert_canonical_unchanged()

    def test_cli_subprocesses_write_verify_invalidate_and_lock_inheritance(self):
        cli_caller = f"""
import sys, pathlib, importlib.util, hashlib
here = pathlib.Path({str(HERE)!r})
spec = importlib.util.spec_from_file_location('cli_wrapper', here / 'verify-route-cache-pair-manifest.py')
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
variant = wrapper.load('build-init-boot-route-cache-candidate.py', 'cli_variant')
def dummy_verify(init, carrier, stock, base, stock_carrier, lib, decode):
    return (hashlib.sha256(init).hexdigest(), hashlib.sha256(carrier).hexdigest(), 123, 456)
variant.verify_candidate = dummy_verify
real_load = wrapper.load
wrapper.load = lambda fn, nm: variant if fn == 'build-init-boot-route-cache-candidate.py' else real_load(fn, nm)
wrapper.main()
"""
        write_call = [sys.executable, "-B", "-c", cli_caller, "write",
                      str(self.init), str(self.carrier), str(self.manifest_path),
                      *map(str, self.refs), str(self.lock)]
        proc_write = subprocess.run(write_call, capture_output=True, text=True, check=False)
        self.assertEqual(proc_write.returncode, 0, f"CLI write failed: {proc_write.stderr}")
        self.assertTrue(self.manifest_path.is_file())

        verify_call = [sys.executable, "-B", "-c", cli_caller, "verify",
                       str(self.init), str(self.carrier), str(self.manifest_path),
                       *map(str, self.refs), str(self.lock)]
        proc_verify = subprocess.run(verify_call, capture_output=True, text=True, check=False)
        self.assertEqual(proc_verify.returncode, 0, f"CLI verify failed: {proc_verify.stderr}")

        fd = os.open(self.lock, os.O_RDWR)
        os.set_inheritable(fd, True)
        try:
            proc_verify_fd = subprocess.run(verify_call + ["--lock-fd", str(fd)],
                                            capture_output=True, text=True, check=False,
                                            close_fds=False)
            self.assertEqual(proc_verify_fd.returncode, 0,
                             f"CLI verify with --lock-fd failed: {proc_verify_fd.stderr}")
        finally:
            os.close(fd)

        invalidate_call = [sys.executable, "-B", "-c", cli_caller, "invalidate",
                           str(self.init), str(self.carrier), str(self.manifest_path), str(self.lock)]
        proc_inv = subprocess.run(invalidate_call, capture_output=True, text=True, check=False)
        self.assertEqual(proc_inv.returncode, 0, f"CLI invalidate failed: {proc_inv.stderr}")
        self.assertFalse(self.manifest_path.exists())
        self.assert_canonical_unchanged()

    def test_bad_verifier_digest_and_schema_rejected(self):
        self.bad_digest = True
        with self.assertRaises(ValueError):
            self.invoke("write")
        self.assertFalse(self.manifest_path.exists())
        self.bad_digest = False
        self.invoke("write")
        value = json.loads(self.manifest_path.read_text())
        value["schema"] = CANONICAL_SCHEMA
        self.manifest_path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.invoke("verify")
        self.assert_canonical_unchanged()

    def test_lock_and_staging_protections(self):
        self.invoke("write")
        data = self.manifest_path.read_bytes()
        unsafe_lock = self.root / "unsafe-lock"
        unsafe_lock.symlink_to(self.lock)
        with self.assertRaises(OSError):
            self.invoke("invalidate", lock=unsafe_lock)
        self.assertEqual(self.manifest_path.read_bytes(), data)
        staging = self.manifest_path.with_name(MANIFEST_NAME + ".omnipha-new")
        staging.write_text("stale staging\n")
        with self.assertRaisesRegex(ValueError, "manifest staging path exists"):
            self.invoke("write")
        self.assertFalse(self.manifest_path.exists())
        self.assertEqual(staging.read_text(), "stale staging\n")
        self.assert_canonical_unchanged()

    def test_wrapper_guard_and_cli_fail_closed(self):
        for attribute, value in (("SCHEMA", CANONICAL_SCHEMA), ("MANIFEST_NAME", CANONICAL_MANIFEST),
                                 ("IMAGES", CANONICAL_IMAGES), ("verified_pair", None)):
            with self.subTest(attribute=attribute), mock.patch.object(self.wrapper.manifest, attribute, value):
                with self.assertRaisesRegex(ValueError, "unsafe route-cache candidate manifest wrapper"):
                    self.invoke("invalidate")
                self.assertFalse(self.lock.exists())
        proc = subprocess.run([sys.executable, "-B", str(WRAPPER)], capture_output=True, text=True, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("FAIL: usage: verify-route-cache-pair-manifest.py", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assert_canonical_unchanged()


class WrapperIsolationTests(unittest.TestCase):
    def test_second_manifest_instance_unaffected(self):
        wrapper = load(WRAPPER, "candidate_manifest_isolation_wrapper")
        second = load(CANONICAL, "candidate_manifest_isolation_second")
        self.assertEqual((second.SCHEMA, second.MANIFEST_NAME, second.IMAGES),
                         (CANONICAL_SCHEMA, CANONICAL_MANIFEST, CANONICAL_IMAGES))
        wrapper.check_wrapper()
        self.assertEqual((wrapper.SCHEMA, wrapper.MANIFEST_NAME, wrapper.IMAGES),
                         (SCHEMA, MANIFEST_NAME, IMAGES))
        self.assertIs(wrapper.manifest.verified_pair, wrapper.verified_pair)

    def test_build_candidate_gated_to_structure(self):
        variant = load(WRAPPER.parent / "build-init-boot-route-cache-candidate.py",
                       "candidate_manifest_isolation_variant")
        with (mock.patch.object(sys, "argv", ["variant"]),
              contextlib.redirect_stdout(io.StringIO()),
              self.assertRaisesRegex(SystemExit, "image output is disabled")):
            variant.main()


if __name__ == "__main__":
    unittest.main(verbosity=2)
