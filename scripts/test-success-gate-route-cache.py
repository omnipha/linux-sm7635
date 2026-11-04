#!/usr/bin/env python3
import errno
import hashlib
import importlib.util
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('route_cache', HERE / 'derive-route-cache-gated-ack.py')
assert spec is not None and spec.loader is not None
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
GATE_AWK_OLD = candidate.OLD_AWK
GATE_AWK_CORRECTED = candidate.NEW_AWK


def run_awk(prog, text):
    proc = subprocess.run(
        ["/bin/busybox", "awk", prog],
        input=text.encode(),
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def run_gate_route_raw(prog, text):
    script = r'''
set -o pipefail || exit 1
value=$(/bin/busybox base64) || exit 1
filtered=$(/bin/busybox printf '%s\n' "$value" | /bin/busybox base64 -d | /bin/busybox tr -d '\000' | /bin/busybox base64) || exit 1
[ "$filtered" = "$value" ] || exit 1
/bin/busybox printf '%s\n' "$value" | /bin/busybox base64 -d | /bin/busybox awk "$1"
'''
    proc = subprocess.run(
        ["/bin/busybox", "sh", "-c", script, "gate-route", prog],
        input=text.encode(),
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def test_candidate_deriver_cli():
    helper_spec = importlib.util.spec_from_file_location('gate_tests', HERE / 'test-derive-success-gated-ack.py')
    assert helper_spec is not None and helper_spec.loader is not None
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    gate = helper.load('gate_binding', 'derive-success-gated-ack.py')
    old_post_sha = '113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3'
    old_hook_sha = '3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67'
    post_sha = '92f6f9cdfa3dcdc8854c7481fe01b500591f1b2b1c9908e97c4cdbfc0ae68d0c'
    hook_sha = '5bc5b0f4e2820aef8ae11b5b3e1f9264a0c7fe5fc60f8686718fb955b376fc3a'

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    temp_root = pathlib.Path(tempfile.gettempdir()).resolve()
    if temp_root == HERE.parent or HERE.parent in temp_root.parents:
        temp_root = pathlib.Path('/tmp')
    with tempfile.TemporaryDirectory(prefix='route-cache-cli.', dir=temp_root) as tmp:
        work = pathlib.Path(tmp)
        assert HERE.parent not in work.resolve().parents
        fixture = work / 'gate-fixture'
        fixture.mkdir()
        helper.prepare(fixture)
        post_input, hook_input = fixture / 'post', fixture / 'hook'
        original_post, original_hook = post_input.read_bytes(), hook_input.read_bytes()
        assert digest(original_post) == old_post_sha and digest(original_hook) == old_hook_sha
        assert (candidate.OLD_POST_SHA, candidate.OLD_HOOK_SHA) == (old_post_sha, old_hook_sha)
        assert (candidate.POST_SHA, candidate.HOOK_SHA) == (post_sha, hook_sha)

        def input_metadata(path):
            info = path.lstat()
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
                    info.st_size, info.st_mtime_ns)

        def snapshot(path):
            info = path.lstat()
            value = path.read_bytes() if stat.S_ISREG(info.st_mode) else None
            if stat.S_ISLNK(info.st_mode):
                value = os.readlink(path)
            return input_metadata(path), info.st_ctime_ns, value

        input_stats = (input_metadata(post_input), input_metadata(hook_input))
        input_snapshots = (snapshot(post_input), snapshot(hook_input))
        command = [sys.executable, '-B', str(HERE / 'derive-route-cache-gated-ack.py')]
        post_output, hook_output = work / 'candidate-post', work / 'candidate-hook'
        result = subprocess.run(command + list(map(str, (post_input, hook_input, post_output, hook_output))),
                                text=True, capture_output=True, check=False, timeout=30)
        assert (snapshot(post_input), snapshot(hook_input)) == input_snapshots
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert result.stdout == f'derived post {post_sha}; hook {hook_sha}\n'
        assert result.stderr == ''
        post, hook = post_output.read_bytes(), hook_output.read_bytes()
        assert digest(post) == post_sha and digest(hook) == hook_sha
        old, new = GATE_AWK_OLD.encode(), GATE_AWK_CORRECTED.encode()
        assert original_post.count(old) == 2 and original_post.count(new) == 0
        expected_post = original_post
        for target, name in (('1.1.1.1', 'internet'), ('"$g_dns"', 'DNS')):
            old_block, new_block = candidate.route_blocks(target, name)
            assert expected_post.count(old_block) == 1 and post.count(new_block) == 1
            expected_post = expected_post.replace(old_block, new_block)
        assert post == expected_post and post.count(old) == 0 and post.count(new) == 2
        old_pin = f'{gate.POST_PATH} {old_post_sha}'.encode()
        new_pin = f'{gate.POST_PATH} {post_sha}'.encode()
        radio_pin = f'{gate.RADIO_PATH} {gate.FRESH_RADIO_SHA}'.encode()
        launch = f"' self-post {gate.POST_PATH} >/dev/null 2>&1 & )\n".encode()
        assert original_hook.count(old_post_sha.encode()) == 1 and original_hook.count(old_pin) == 1
        assert hook == original_hook.replace(old_post_sha.encode(), post_sha.encode(), 1)
        assert hook.count(old_pin) == 0 and hook.count(new_pin) == 1
        assert hook.count(radio_pin) == 1 and hook.count(launch) == 1
        assert hook.index(new_pin) < hook.index(radio_pin) < hook.index(b'done\n') < hook.index(launch)
        for path in (post_output, hook_output):
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            assert HERE.parent not in path.resolve().parents
            subprocess.run(['sh', '-n', str(path)], check=True)
        assert (post_output.stat().st_dev, post_output.stat().st_ino) != (
            hook_output.stat().st_dev, hook_output.stat().st_ino)

        bad_post, bad_hook = work / 'bad-post-input', work / 'bad-hook-input'
        bad_post.write_bytes(original_post + b'\n')
        bad_hook.write_bytes(original_hook + b'\n')
        rejected_post, rejected_hook = work / 'rejected-post', work / 'rejected-hook'

        def reject(label, left, right, output, hook_out, reason, absent):
            protected = {left, right, post_input, hook_input, post_output, hook_output}
            protected.update(path for path in (output, hook_out) if os.path.lexists(path))
            before = {path: snapshot(path) for path in protected}
            result = subprocess.run(command + list(map(str, (left, right, output, hook_out))),
                                    text=True, capture_output=True, check=False, timeout=30)
            assert result.returncode != 0 and reason in result.stderr, (label, result.stdout, result.stderr)
            assert all(not os.path.lexists(path) for path in absent), label
            assert {path: snapshot(path) for path in protected} == before, label
            assert post_input.read_bytes() == original_post and hook_input.read_bytes() == original_hook, label
            assert post_output.read_bytes() == post and hook_output.read_bytes() == hook, label

        def reject_inputs(label, left, right, reason):
            reject(label, left, right, rejected_post, rejected_hook, reason, (rejected_post, rejected_hook))

        reject_inputs('changed post pin', bad_post, hook_input, 'inputs are not the pinned run-113 post and hook')
        reject_inputs('changed hook pin', post_input, bad_hook, 'inputs are not the pinned run-113 post and hook')
        for name, source in (('post', post_input), ('hook', hook_input)):
            for kind in ('symlink', 'hardlink'):
                alias = work / f'{kind}-{name}-input'
                if kind == 'symlink':
                    alias.symlink_to(source)
                    reason = os.strerror(errno.ELOOP)
                else:
                    os.link(source, alias)
                    reason = 'unsafe input'
                left = alias if name == 'post' else post_input
                right = alias if name == 'hook' else hook_input
                reject_inputs(f'{kind} {name} input', left, right, reason)
                assert alias.read_bytes() == source.read_bytes()
                if kind == 'symlink':
                    assert alias.is_symlink() and alias.resolve() == source
                else:
                    assert alias.stat().st_ino == source.stat().st_ino and source.stat().st_nlink == 2
                alias.unlink()

        for name, source in (('post', post_input), ('hook', hook_input)):
            hardlink = work / f'hardlink-to-{name}'
            os.link(source, hardlink)
            reject_inputs(f'original {name} input with hardlink', post_input, hook_input, 'unsafe input')
            assert hardlink.stat().st_ino == source.stat().st_ino and source.stat().st_nlink == 2
            hardlink.unlink()

        reject('duplicate outputs', post_input, hook_input, rejected_post, rejected_post,
               'outputs must be distinct paths', (rejected_post,))
        alias_dir = work / 'route-cache-alias-directory'
        alias_dir.symlink_to(work, target_is_directory=True)
        reject('aliased duplicate outputs', post_input, hook_input, rejected_post, alias_dir / rejected_post.name,
               'outputs must be distinct paths', (rejected_post,))
        reject('existing post output', post_input, hook_input, post_output, rejected_hook,
               'output already exists', (rejected_hook,))
        reject('existing hook output', post_input, hook_input, rejected_post, hook_output,
               'output already exists', (rejected_post,))
        existing = work / 'existing-output'
        existing.write_text('existing output')
        existing_post, existing_hook = work / 'existing-post-output', work / 'existing-hook-output'
        existing_post.write_text('existing post output')
        existing_hook.write_text('existing hook output')
        reject('existing output', post_input, hook_input, existing, rejected_hook,
               'output already exists', (rejected_hook,))
        reject('same existing outputs', post_input, hook_input, existing, existing,
               'output already exists', (rejected_hook,))
        reject('two existing outputs', post_input, hook_input, existing_post, existing_hook,
               'output already exists', (rejected_hook,))
        for existing_path, content in ((existing, 'existing output'), (existing_post, 'existing post output'),
                                       (existing_hook, 'existing hook output')):
            assert existing_path.read_text() == content

        reject('output equals input', post_input, hook_input, post_input, rejected_hook,
               'output already exists', (rejected_hook,))
        output_symlink = work / 'symlink-output'
        output_symlink.symlink_to(post_input)
        reject('symlink output', post_input, hook_input, rejected_post, output_symlink,
               'output already exists', (rejected_post,))
        assert output_symlink.is_symlink() and output_symlink.resolve() == post_input
        dangling = work / 'dangling-output'
        dangling_target = work / 'absent-target'
        dangling.symlink_to(dangling_target)
        reject('dangling output', post_input, hook_input, dangling, rejected_hook,
               'output already exists', (rejected_hook, dangling_target))
        assert dangling.is_symlink()
        output_hardlink = work / 'hardlink-output'
        os.link(post_output, output_hardlink)
        reject('hardlink output', post_input, hook_input, output_hardlink, rejected_hook,
               'output already exists', (rejected_hook,))
        assert output_hardlink.stat().st_ino == post_output.stat().st_ino
        output_hardlink.unlink()

        in_repo = HERE.parent / f'{work.name}-forbidden-output'
        assert not os.path.lexists(in_repo)
        reject('post output in repository', post_input, hook_input, in_repo, rejected_hook,
               'outputs must be outside the repository', (in_repo, rejected_hook))
        reject('hook output in repository', post_input, hook_input, rejected_post, in_repo,
               'outputs must be outside the repository', (rejected_post, in_repo))
        repo_alias = work / 'route-cache-repository-alias'
        repo_alias.symlink_to(HERE.parent, target_is_directory=True)
        reject('output through repository alias', post_input, hook_input, repo_alias / in_repo.name, rejected_hook,
               'outputs must be outside the repository', (in_repo, rejected_hook))
        repo_alias.unlink()
        assert (input_metadata(post_input), input_metadata(hook_input)) == input_stats
        assert post_input.read_bytes() == original_post and hook_input.read_bytes() == original_hook
        print('pass: pinned candidate CLI, two route replacements, hook binding and output safety')


def main():
    real_iproute2_out = (
        "1.1.1.1 from 192.0.2.2 via 192.0.2.1 dev wlan0 uid 0 \n"
        "    cache \n"
    )

    old_result = run_awk(GATE_AWK_OLD, real_iproute2_out)
    if old_result is not False:
        raise AssertionError("reproduction failed: old awk unexpectedly accepted two-line cache output")

    corr_result = run_awk(GATE_AWK_CORRECTED, real_iproute2_out)
    if corr_result is not True:
        raise AssertionError("corrected awk failed to accept real iproute2 cache output")

    matrix = [
        ("real iproute2 with cache", real_iproute2_out, True),
        ("real iproute2 without trailing spaces", "1.1.1.1 via 192.0.2.1 dev wlan0 uid 0\n    cache\n", True),
        ("tab indented cache", "1.1.1.1 via 192.0.2.1 dev wlan0 uid 0\n\tcache\n", True),
        ("single-line output (busybox/no cache)", "1.1.1.1 via 192.0.2.1 dev wlan0 src 192.0.2.2\n", True),
        ("single-line without via", "1.1.1.1 dev wlan0 src 192.0.2.2\n", True),
        ("no trailing newline single line", "1.1.1.1 via 192.0.2.1 dev wlan0", True),
        ("no trailing newline two line", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache", True),

        ("empty string", "", False),
        ("whitespace only", "   \n\n", False),
        ("dev is eth0", "1.1.1.1 via 192.0.2.1 dev eth0 uid 0\n    cache\n", False),
        ("dev is usb0", "1.1.1.1 via 192.0.2.1 dev usb0 uid 0\n    cache\n", False),
        ("dev prefix match wlan01", "1.1.1.1 via 192.0.2.1 dev wlan01 uid 0\n    cache\n", False),
        ("missing dev keyword", "1.1.1.1 via 192.0.2.1 wlan0 uid 0\n    cache\n", False),
        ("dev at end without argument", "1.1.1.1 via 192.0.2.1 dev", False),
        ("dangling dev after wlan0", "1.1.1.1 dev wlan0 dev\n", False),
        ("dangling dev after wlan0 with cache", "1.1.1.1 dev wlan0 dev\n    cache\n", False),
        ("uppercase interface", "1.1.1.1 dev WLAN0\n    cache\n", False),
        ("blank second line", "1.1.1.1 dev wlan0\n\n", False),
        ("DNS route with cache", "192.0.2.53 from 192.0.2.2 dev wlan0\n    cache\n", True),
        ("DNS route foreign continuation", "192.0.2.53 dev wlan0\n    dev eth0\n", False),
        ("duplicate dev wlan0 on line 1", "1.1.1.1 dev wlan0 dev wlan0\n", False),
        ("both wlan0 and eth0 dev on line 1", "1.1.1.1 dev wlan0 dev eth0\n", False),
        ("line 2 is not cache (e.g. foreign dev)", "1.1.1.1 via 192.0.2.1 dev wlan0\n    dev eth0\n", False),
        ("line 2 has trailing garbage after cache", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache foreign\n", False),
        ("three lines", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache\n    extra\n", False),
        ("four lines", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache\n    extra\n    more\n", False),
    ]

    for label, inp, expected in matrix:
        res = run_awk(GATE_AWK_CORRECTED, inp)
        if res != expected:
            raise AssertionError(f"test case '{label}' failed: got {res}, expected {expected}")
        pipe_res = run_gate_route_raw(GATE_AWK_CORRECTED, inp)
        if pipe_res != expected:
            raise AssertionError(f"gate raw check '{label}' failed: got {pipe_res}, expected {expected}")

    for label, inp in (
        ("NUL after line 1 dev", "1.1.1.1 dev wlan0\x00\n"),
        ("NUL after cache", "1.1.1.1 dev wlan0\n    cache\x00\n"),
    ):
        if run_gate_route_raw(GATE_AWK_CORRECTED, inp):
            raise AssertionError(f"gate raw check should strictly reject embedded NUL: {label}")

    test_candidate_deriver_cli()

    print("pass: defect reproduction and corrected route parser matrix verified cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
