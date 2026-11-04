#!/usr/bin/env python3
import copy
import hashlib
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
VERIFIER = HERE / "verify-dependent-pair-manifest.py"
OUT = pathlib.Path.home() / "sm7635-build" / "out"
DATA = pathlib.Path.home() / "phone-second-life-data" / "mb003" / "parts"

INIT_NAME = "init_boot-root-contract-carrier.img"
CARRIER_NAME = "vendor_boot_b-root-contract.img"
MANIFEST_NAME = "root-contract-pair.manifest.json"

STOCK_INIT = DATA / "init_boot_a.img"
BASE_IMAGE = OUT / "init_boot-mindstorms-wlan.img"
STOCK_CARRIER = DATA / "vendor_boot_b.img"

EXPECTED_INIT_SHA = "d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c"
EXPECTED_CARRIER_SHA = "221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500"


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def run_cli(*args):
    return subprocess.run([sys.executable, "-B", str(VERIFIER), *args],
                          capture_output=True, text=True, check=False,
                          close_fds=False)


def main():
    require(VERIFIER.is_file(), "missing manifest tool")
    for path in (STOCK_INIT, BASE_IMAGE, STOCK_CARRIER):
        require(path.is_file() and not path.is_symlink(), f"missing reference: {path}")

    real_init = OUT / INIT_NAME
    real_carrier = OUT / CARRIER_NAME
    require(real_init.is_file() and real_carrier.is_file(), "settled artifacts missing")
    require(sha256(real_init.read_bytes()) == EXPECTED_INIT_SHA, "init sha changed")
    require(sha256(real_carrier.read_bytes()) == EXPECTED_CARRIER_SHA, "carrier sha changed")

    with tempfile.TemporaryDirectory(prefix="test-pair-manifest.") as tmpdir:
        tmp = pathlib.Path(tmpdir)
        lock_path = tmp / "build.lock"
        lock_path.write_text("lock\n")
        lock_path.chmod(0o600)

        test_init = tmp / INIT_NAME
        test_carrier = tmp / CARRIER_NAME
        test_manifest = tmp / MANIFEST_NAME

        test_init.write_bytes(real_init.read_bytes())
        test_carrier.write_bytes(real_carrier.read_bytes())
        test_init.chmod(0o600)
        test_carrier.chmod(0o600)

        write_proc = run_cli("write", str(test_init), str(test_carrier), str(test_manifest),
                             str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(write_proc.returncode == 0, f"write failed: {write_proc.stderr}")
        require(test_manifest.is_file(), "manifest not created")
        info = test_manifest.lstat()
        require(stat.S_IMODE(info.st_mode) == 0o600, "manifest mode not 0600")

        v_proc = run_cli("verify", str(test_init), str(test_carrier), str(test_manifest),
                         str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(v_proc.returncode == 0, f"verify generated failed: {v_proc.stderr}")
        require(f"init_boot_a {EXPECTED_INIT_SHA}" in v_proc.stdout, "init hash missing from verify output")
        require(f"vendor_boot_b {EXPECTED_CARRIER_SHA}" in v_proc.stdout, "carrier hash missing from verify output")

        raw_manifest = json.loads(test_manifest.read_text())

        def expect_rejection(label, bad_manifest, bad_init=None, bad_carrier=None, fixup_mode=True):
            assert test_manifest.name == MANIFEST_NAME, f"fixture misnamed ({label})"
            if isinstance(bad_manifest, str):
                test_manifest.write_text(bad_manifest)
            elif bad_manifest is not None:
                test_manifest.write_text(json.dumps(bad_manifest, indent=1))
            if fixup_mode:
                test_manifest.chmod(0o600)
            cur_init = bad_init if bad_init is not None else test_init
            cur_carrier = bad_carrier if bad_carrier is not None else test_carrier
            res = run_cli("verify", str(cur_init), str(cur_carrier), str(test_manifest),
                          str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
            require(res.returncode != 0, f"expected failure for {label}, got success: {res.stdout}")

        bad_schema = copy.deepcopy(raw_manifest)
        bad_schema["schema"] = "omnipha-sm7635-dependent-pair-v2"
        expect_rejection("bad-schema", bad_schema)

        no_schema = copy.deepcopy(raw_manifest)
        del no_schema["schema"]
        expect_rejection("no-schema", no_schema)

        extra_root_key = copy.deepcopy(raw_manifest)
        extra_root_key["extra"] = "forbidden"
        expect_rejection("extra-root-key", extra_root_key)

        empty_images = copy.deepcopy(raw_manifest)
        empty_images["images"] = []
        expect_rejection("empty-images", empty_images)

        single_image = copy.deepcopy(raw_manifest)
        single_image["images"] = [raw_manifest["images"][0]]
        expect_rejection("single-image", single_image)

        extra_image = copy.deepcopy(raw_manifest)
        extra_image["images"].append({
            "partition": "boot_a", "filename": "boot.img",
            "size": 15753216, "sha256": "0" * 64
        })
        expect_rejection("extra-image", extra_image)

        duplicate_partition = copy.deepcopy(raw_manifest)
        duplicate_partition["images"][1]["partition"] = "init_boot_a"
        expect_rejection("duplicate-partition", duplicate_partition)

        extra_entry_key = copy.deepcopy(raw_manifest)
        extra_entry_key["images"][0]["extra"] = True
        expect_rejection("extra-entry-key", extra_entry_key)

        corrupt_init_sha = copy.deepcopy(raw_manifest)
        corrupt_init_sha["images"][0]["sha256"] = "0" * 64
        expect_rejection("corrupt-init-sha", corrupt_init_sha)

        corrupt_carrier_sha = copy.deepcopy(raw_manifest)
        corrupt_carrier_sha["images"][1]["sha256"] = "1" * 64
        expect_rejection("corrupt-carrier-sha", corrupt_carrier_sha)

        corrupt_size = copy.deepcopy(raw_manifest)
        corrupt_size["images"][0]["size"] = 1234
        expect_rejection("corrupt-size", corrupt_size)

        bad_filename = copy.deepcopy(raw_manifest)
        bad_filename["images"][0]["filename"] = "wrong-init.img"
        expect_rejection("bad-filename", bad_filename)

        expect_rejection("corrupt-json", "{not-valid-json}")
        # restore the valid manifest for subsequent cases
        test_manifest.write_text(json.dumps(raw_manifest, indent=1, sort_keys=True) + "\n")
        test_manifest.chmod(0o600)
        res = run_cli("verify", str(test_init), str(test_carrier), str(test_manifest),
                      str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(res.returncode == 0, f"restored manifest no longer verifies: {res.stderr}")

        # Test write rejection when manifest target is a pre-existing directory
        saved_manifest = tmp / "saved-manifest"
        test_manifest.rename(saved_manifest)
        test_manifest.mkdir(mode=0o700)
        w_proc = run_cli("write", str(test_init), str(test_carrier), str(test_manifest),
                         str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(w_proc.returncode != 0, f"write accepted directory manifest: {w_proc.stdout}")
        test_manifest.rmdir()
        saved_manifest.rename(test_manifest)

        test_manifest.chmod(0o644)
        expect_rejection("unsafe-mode", None, fixup_mode=False)
        test_manifest.chmod(0o600)

        target = tmp / "manifest-target.json"
        test_manifest.rename(target)
        test_manifest.symlink_to(target)
        res = run_cli("verify", str(test_init), str(test_carrier), str(test_manifest),
                      str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(res.returncode != 0, "symlink manifest accepted")
        test_manifest.unlink()
        target.rename(test_manifest)

        flipped_init = tmp / "init-corrupt.img"
        data = bytearray(test_init.read_bytes())
        data[0] ^= 0x01
        flipped_init.write_bytes(data)
        flipped_init.chmod(0o600)
        expect_rejection("flipped-init-content", raw_manifest, bad_init=flipped_init)
        flipped_init.unlink()

        flipped_carrier = tmp / "carrier-corrupt.img"
        cdata = bytearray(test_carrier.read_bytes())
        cdata[0] ^= 0x01
        flipped_carrier.write_bytes(cdata)
        flipped_carrier.chmod(0o600)
        expect_rejection("flipped-carrier-content", raw_manifest, bad_carrier=flipped_carrier)
        flipped_carrier.unlink()

        stale_staging = test_manifest.with_name(test_manifest.name + ".omnipha-new")
        stale_staging.write_text("pre-existing\n")
        w_proc = run_cli("write", str(test_init), str(test_carrier), str(test_manifest),
                         str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(w_proc.returncode != 0, f"write accepted pre-existing staging: {w_proc.stdout}")
        stale_staging.unlink()

        misnamed_init = tmp / "other_init.img"
        misnamed_init.write_bytes(test_init.read_bytes())
        misnamed_init.chmod(0o600)
        w_proc = run_cli("write", str(misnamed_init), str(test_carrier), str(tmp / "out-manifest.json"),
                         str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(w_proc.returncode != 0, f"write accepted misnamed init: {w_proc.stdout}")
        misnamed_init.unlink()

        misnamed_carrier = tmp / "other_carrier.img"
        misnamed_carrier.write_bytes(test_carrier.read_bytes())
        misnamed_carrier.chmod(0o600)
        w_proc = run_cli("write", str(test_init), str(misnamed_carrier), str(tmp / "out-manifest.json"),
                         str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path))
        require(w_proc.returncode != 0, f"write accepted misnamed carrier: {w_proc.stdout}")
        misnamed_carrier.unlink()

        inv_proc = run_cli("invalidate", str(test_init), str(test_carrier), str(test_manifest), str(lock_path))
        require(inv_proc.returncode == 0, f"invalidate failed: {inv_proc.stderr}")
        require(not test_manifest.exists(), "invalidate did not remove manifest")

        # Test --lock-fd passing
        fd = os.open(lock_path, os.O_RDWR)
        os.set_inheritable(fd, True)
        try:
            write_fd_proc = run_cli("write", str(test_init), str(test_carrier), str(test_manifest),
                                    str(STOCK_INIT), str(BASE_IMAGE), str(STOCK_CARRIER), str(lock_path),
                                    "--lock-fd", str(fd))
            require(write_fd_proc.returncode == 0, f"write with --lock-fd failed: {write_fd_proc.stderr}")
            require(test_manifest.is_file(), "manifest not created via --lock-fd")
        finally:
            os.close(fd)

    print("pass: dependent-pair manifest host positive and negative fixtures verified cleanly")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
