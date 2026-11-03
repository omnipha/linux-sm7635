#!/usr/bin/env python3
"""Exercise the exact generated fresh-boot monitor without a device or real kmsg."""
import hashlib
import importlib.util
import pathlib
import shutil
import subprocess
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    busybox = shutil.which('busybox')
    if not busybox:
        raise SystemExit('BusyBox is required')
    builder = load('builder', 'build-init-boot-persistent-root.py')
    persist = load('persist', 'derive-radio-persistent.py')
    fresh = load('fresh', 'derive-radio-fresh-boot.py')
    postgen = load('postgen', 'derive-self-post-fresh-boot.py')
    gate = load('gate', 'derive-success-gated-ack.py')
    radio = fresh.derive(persist.derive(builder.current_scripts()['pmos-radio-bringup.sh'].decode()))
    post, fresh_hook = postgen.derive((HERE / 'pmos-self-post.sh').read_text(), radio.encode())
    # Extract and execute the actual monitor, not a rewritten model. Device-only
    # paths are replaced by a private test file and the host BusyBox binary.
    prefix = "( /bin/busybox setsid /bin/busybox sh -c '\n"
    suffix = f"' self-post {postgen.POST_PATH} >/dev/null 2>&1 & )\n"
    assert fresh_hook.count(prefix) == fresh_hook.count(suffix) == 1
    monitor = fresh_hook.split(prefix, 1)[1].split(suffix, 1)[0]
    assert monitor.count('/dev/kmsg') == 1
    assert monitor.count('/bin/busybox') == 2
    assert '"$1" >/dev/null 2>&1' in monitor
    monitor = monitor.replace('/bin/busybox', busybox).replace('/dev/kmsg', '"$2"')
    with tempfile.TemporaryDirectory(prefix='fresh-exit-fixture-') as tmp:
        work = pathlib.Path(tmp)
        executable, log = work / 'post', work / 'kmsg'
        cases = (
            ('success', 'echo PRIVATE_PROFILE; exit 0', 0),
            ('ordinary-nonzero', 'echo PRIVATE_PROFILE >&2; exit 42', 42),
            ('errexit', 'set -e; false', 1),
            ('unbound', 'set -u; echo "$MISSING_SECRET_VAR"', 2),
            ('syntax-error', 'this is ; invalid syntax )', 2),
        )
        for name, script, expected_rc in cases:
            log.unlink(missing_ok=True)
            executable.write_text('#!/bin/busybox sh\n' + script + '\n')
            result = subprocess.run([busybox, 'setsid', busybox, 'sh', '-c', monitor,
                                     'self-post', str(executable), str(log)],
                                    capture_output=True, text=True, check=False)
            assert result.returncode == expected_rc, (name, result.returncode, result.stderr)
            assert result.stdout == result.stderr == '', (name, result.stdout, result.stderr)
            logged = log.read_text() if log.exists() else ''
            expected = '' if expected_rc == 0 else f'pmos-self-post-fresh: process exited rc={expected_rc}\n'
            assert logged == expected, (name, repr(logged))
        # A missing kmsg sink must not replace the underlying failure status.
        executable.write_text('#!/bin/busybox sh\nexit 42\n')
        result = subprocess.run([busybox, 'setsid', busybox, 'sh', '-c', monitor,
                                 'self-post', str(executable), str(work / 'absent' / 'kmsg')],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 42, result
        assert result.stdout == result.stderr == '', (result.stdout, result.stderr)

        # A post waiting at a barrier must not keep the launcher's pipes open.
        started, release = work / 'started', work / 'release'
        log.unlink(missing_ok=True)
        executable.write_text(
            f'#!/bin/sh\necho started > "{started}"\n'
            f'while [ ! -f "{release}" ]; do sleep 0.05; done\nexit 42\n'
        )
        launch = prefix + fresh_hook.split(prefix, 1)[1].split(suffix, 1)[0] + suffix
        launch = (launch.replace('/bin/busybox', busybox)
                        .replace(postgen.POST_PATH, str(executable))
                        .replace('/dev/kmsg', str(log)))
        try:
            result = subprocess.run(['/bin/sh', '-c', launch], capture_output=True,
                                    text=True, timeout=2, check=False)
            assert result.returncode == 0, result
            assert result.stdout == result.stderr == '', (result.stdout, result.stderr)
            deadline = time.monotonic() + 2
            while not started.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert started.exists(), 'background post did not start'
        finally:
            # Also release a child from the old launch if the test times out.
            release.touch()
        deadline = time.monotonic() + 2
        while not log.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert log.read_text() == 'pmos-self-post-fresh: process exited rc=42\n'
        # Both generators must carry byte-identical monitor logic.
        probe = gate.build_dns_probe()
        candidate, hook = gate.derive(post, radio.encode(), probe)
        assert hashlib.sha256(candidate.encode()).hexdigest() == '9a8c40adce2f84d61e30fd49f6d0f3be5a08d3a57909e9335c3c02f2751ea97b'
        assert hook.split(prefix, 1)[1].split(suffix, 1)[0] == fresh_hook.split(prefix, 1)[1].split(suffix, 1)[0]
    print('pass: detached fresh/success hook reports exit status to kmsg; success, failure, errexit, unbound, syntax, sink loss; no device')


if __name__ == '__main__':
    main()
