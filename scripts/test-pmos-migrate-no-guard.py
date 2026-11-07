import hashlib
import importlib.util
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
MIGRATE = HERE / "pmos-migrate-no-guard.sh"
BAD_RADIO = "d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3"
LEGACY_RADIO = pathlib.Path.home() / "phone-second-life-data/mb003/legacy-pinned-20261107-1607/pmos-radio-bringup-fresh-boot.sh"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build-init-boot-mb003-no-guard.py", "no_guard_test_module")


class NoGuardMigrationTests(unittest.TestCase):
    def setUp(self):
        bb = shutil.which("busybox")
        self.assertIsNotNone(bb)
        assert bb is not None
        self.bb = bb
        self.temp = tempfile.TemporaryDirectory(prefix="test-migrate.")
        self.root = pathlib.Path(self.temp.name)
        (self.root / "usr/libexec/omnipha").mkdir(parents=True)
        (self.root / "etc/local.d").mkdir(parents=True)
        (self.root / "run").mkdir()
        self.radio = self.root / "usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
        self.post = self.root / "usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
        self.hook = self.root / "etc/local.d/10-omnipha-self-stage.start"
        scripts = builder.unpinned.runtime_scripts()
        self.radio.write_bytes(scripts[builder.FRESH_RADIO])
        self.post.write_bytes(scripts[builder.FRESH_POST])
        self.hook.write_bytes(scripts[builder.GATED_HOOK])

    def tearDown(self):
        self.temp.cleanup()

    def migrate(self):
        return subprocess.run([self.bb, "sh", str(MIGRATE), str(self.root)],
                              env={"PATH": "/usr/bin:/bin", "BB": self.bb},
                              capture_output=True, text=True, check=False)

    def hashes(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (self.radio, self.post, self.hook)}

    def test_live_radio_is_tested_original_and_migrates(self):
        self.assertTrue(LEGACY_RADIO.is_file())
        self.assertEqual(hashlib.sha256(LEGACY_RADIO.read_bytes()).hexdigest(),
                         "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14")
        self.assertEqual(self.hashes()["pmos-radio-bringup-fresh-boot.sh"],
                         "146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14")
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        migrated = self.hashes()
        self.assertNotEqual(migrated["pmos-radio-bringup-fresh-boot.sh"], BAD_RADIO)
        self.assertTrue((self.root / "etc/.omnipha-no-guard-migrated").is_file())
        again = self.migrate()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.hashes(), migrated)
        self.assertFalse((self.root / "run/no-guard-work").exists())

    def test_bad_radio_refused_without_changes(self):
        self.radio.write_bytes(b"#!/bin/busybox sh\nexit 0\n")
        digest = hashlib.sha256(self.radio.read_bytes()).hexdigest()
        self.assertNotEqual(digest, BAD_RADIO)
        text = MIGRATE.read_text()
        replaced = text.replace(BAD_RADIO, digest, 1)
        self.assertEqual(text.count(BAD_RADIO), 1)
        with tempfile.TemporaryDirectory(prefix="test-migrate-bad.") as tmp:
            script = pathlib.Path(tmp) / "migrate.sh"
            script.write_text(replaced)
            script.chmod(0o700)
            before = self.hashes()
            result = subprocess.run([self.bb, "sh", str(script), str(self.root)],
                                    env={"PATH": "/usr/bin:/bin", "BB": self.bb},
                                    capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.hashes(), before)
        self.assertFalse((self.root / "etc/.omnipha-no-guard-migrated").exists())
        self.assertFalse(any(self.root.rglob("*.before-no-guard")))

    def test_post_failure_rolls_back_radio(self):
        self.post.write_bytes(self.post.read_bytes() + b"\nif [ invalid; then\n")
        before = self.hashes()
        result = self.migrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.hashes(), before)
        self.assertFalse((self.root / "etc/.omnipha-no-guard-migrated").exists())
        self.assertFalse(any(self.root.rglob("*.before-no-guard")))
        self.assertFalse(any(self.root.rglob("*.omnipha-new")))

    def test_symlink_refused_without_marker(self):
        self.hook.unlink()
        self.hook.symlink_to("missing")
        result = self.migrate()
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.root / "etc/.omnipha-no-guard-migrated").exists())

    def test_hook_kill_block_removed_and_route_preserved(self):
        original = self.hook.read_text()
        self.hook.write_text(original + """
( /bin/busybox setsid /bin/busybox sh -c '
	/bin/busybox sleep 80
	case "$cmd" in *"guard.sh watch"*) /bin/busybox kill -TERM "$pid";; esac
' no-guard >/dev/null 2>&1 & )
""")
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("guard.sh watch", self.hook.read_text())
        self.assertNotIn("kill -TERM", self.hook.read_text())
        self.assertIn('dev" && $(i+1) == "wlan0"', self.post.read_text())


if __name__ == "__main__":
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    unittest.main()
