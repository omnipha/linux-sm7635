#!/usr/bin/env python3
"""Host fixtures for fresh-boot derivations and observed #291 panel limitations.

With set -e, a nonmatching panel pipeline exits the #291 candidate at the
pre-check, while the old final sed succeeds and reaches the post-check. Matching
but conflicting or invalid restore data also reaches the post-check. These are
observed limitations, not a fix or device evidence: dmesg, trace, paths and
file-owner UID and logging are modeled; shell and text processing use host
BusyBox. The extracted EXIT trap removes only a synthetic temporary profile.
"""
import hashlib
import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile

here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


persist = load('persist', 'derive-radio-persistent.py')
postack = load('postack', 'derive-radio-postack.py')
fresh = load('fresh', 'derive-radio-fresh-boot.py')
selfpost = load('selfpost', 'derive-self-post-fresh-boot.py')
builder = load('builder', 'build-init-boot-persistent-root.py')

STAGED_SHA = 'f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f'
COMMITTED_PERSISTENT_SHA = 'c54c29e1278827bc00faaf506c7ff8e923a8a689a011a2852d5d4b7778d0188d'
RADIO_FRESH_SHA = 'a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21'
POST_FRESH_SHA = 'c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7'
HOOK_SHA = '32ad1e5e4dd1607acc7888d036df2217074a197403e5601df94745ec96a520a1'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def derive_all(staged):
    radio = fresh.derive(persist.derive(staged))
    assert sha(radio) == RADIO_FRESH_SHA, sha(radio)
    assert 'LEASE_SHA=1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56' in radio
    post, hook = selfpost.derive((here / 'pmos-self-post.sh').read_text(), radio.encode())
    assert sha(post) == POST_FRESH_SHA, sha(post)
    assert sha(hook) == HOOK_SHA, sha(hook)
    return radio, post, hook


def sh_n(paths):
    for path in paths:
        subprocess.run(['sh', '-n', str(path)], check=True)


def test_panel_pipeline(source, post):
    """Reproduce current exit and restore boundaries, not a proposed fix."""
    busybox = shutil.which('busybox')
    if busybox is None:
        raise SystemExit('host BusyBox is required for the panel pipeline fixture')
    boot = '11111111-2222-3333-4444-555555555555'
    panel = f'usb-init: pre-SSH panel node=boe card0=1 dsi1=1 boot {boot}'
    foreign = panel.replace(boot, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
    conflict = panel.replace('node=boe', 'node=vxn')
    long_panel = f'usb-init: pre-SSH panel node=boe card0={"x" * 401} boot {boot}'
    caller = '[    1.562660][    T1] '

    def extract(text):
        start = "trace 'pre check panel record'\n"
        end = "trace 'record append entry'\n"
        assert text.count(start) == text.count(end) == 1
        block = text.split(start, 1)[1].split(end, 1)[0]
        assignment = [line for line in block.splitlines(keepends=True) if line.startswith('\tpanel_hits=')]
        assert len(assignment) == 1
        return start + block, assignment[0]

    old_block, old_assignment = extract(source)
    candidate_block, candidate_assignment = extract(post)
    assert old_assignment == selfpost.OLD_GREP
    assert candidate_assignment == selfpost.NEW_GREP
    assert old_block.replace(old_assignment, candidate_assignment, 1) == candidate_block
    trace_start, trace_end = 'trace() {\n', '\n}\n'
    assert source.count(trace_start) == post.count(trace_start) == 1
    trace_function = trace_start + source.split(trace_start, 1)[1].split(trace_end, 1)[0] + trace_end
    assert trace_function in post
    trap_line = 'trap scrub EXIT\n'
    scrub_line = 'scrub() { $BB rm -f "$PROFILE"; }\n'
    assert source.count(trap_line) == post.count(trap_line) == 1
    assert source.count(scrub_line) == post.count(scrub_line) == 1
    assert source.splitlines()[1] == post.splitlines()[1] == 'set -eu'
    setup = source.splitlines()[1] + '''
REAL_BB=$1
boot=$2
INPUT=$3
PANEL=$4
RECORD=$5
OWNER=$6
PROFILE=$7
fixture_bb() {
    case "$1" in
        dmesg) "$REAL_BB" cat "$INPUT";;
        stat)
            if [ "${2:-}" = -c ] && [ "${3:-}" = '%u:%a:%h' ] && [ "${4:-}" = "$PANEL" ]; then
                "$REAL_BB" stat -c '%u:%a:%h' "$PANEL" | "$REAL_BB" sed "s/^$OWNER:/0:/"
            else
                "$REAL_BB" "$@"
            fi;;
        *) "$REAL_BB" "$@";;
    esac
}
log() { printf '%s\\n' "$*"; }
die() { printf 'FAIL: %s\\n' "$*"; exit 1; }
BB=fixture_bb
''' + trace_function + scrub_line + trap_line
    suffix = '''printf 'panel hits begin\\n%s\\npanel hits end\\n' "${panel_hits-}"
if [ -f "$PANEL" ]; then
    printf 'panel file begin\\n'
    "$1" cat "$PANEL"
    printf 'panel file end\\n'
fi
'''
    replacements = (
        ('panel=/run/pmos-pre-ssh-panel.record', 'panel=$PANEL', 1),
        ('/.omnipha-boot-record', '$RECORD', 3),
    )
    blocks = {}
    for name, block in (('old', old_block), ('candidate', candidate_block)):
        for original, replacement, count in replacements:
            assert block.count(original) == count
            block = block.replace(original, replacement)
        blocks[name] = block

    cases = (
        ('raw', f'usb-init: {panel}', 'both'),
        ('timestamp', f'[    1.562660] usb-init: {panel}', 'both'),
        ('priority', f'<6>usb-init: {panel}', 'candidate'),
        ('priority-timestamp', f'<6>[    1.562660] usb-init: {panel}', 'candidate'),
        ('timestamp-caller', f'{caller}usb-init: {panel}', 'neither'),
        ('priority-timestamp-caller', f'<6>{caller}usb-init: {panel}', 'neither'),
        ('unrelated', '[    2.000000][    T2] unrelated kernel message', 'neither'),
        ('empty', '', 'neither'),
        ('foreign-boot', f'usb-init: {foreign}', 'neither'),
        ('invalid-node', f'usb-init: {panel.replace("node=boe", "node=other")}', 'neither'),
        ('single-tag', panel, 'neither'),
        ('matching-and-irrelevant', f'{caller}unrelated\nusb-init: {panel}', 'both'),
        ('duplicates', f'usb-init: {panel}\n[    1.562660] usb-init: {panel}', 'duplicates'),
        ('conflicts', f'usb-init: {panel}\nusb-init: {conflict}', 'conflicts'),
        ('record-mismatch', f'usb-init: {panel}', 'record-mismatch'),
        ('overlong', f'usb-init: {long_panel}', 'overlong'),
        ('existing-panel', f'{caller}usb-init: {panel}', 'existing-panel'),
        ('absent-record', f'{caller}usb-init: {panel}', 'absent-record'),
    )
    with tempfile.TemporaryDirectory(prefix='panel-pipeline-291.') as tmp:
        work = pathlib.Path(tmp)
        paths = (work / name for name in ('dmesg', 'panel', 'record', 'profile'))
        input_path, panel_path, record_path, profile_path = paths
        owner = str(work.stat().st_uid)
        for name, text, behavior in cases:
            input_path.write_text(text + '\n' if text else '')
            record_panel = {'record-mismatch': conflict, 'overlong': long_panel}.get(behavior, panel)
            for variant, block in blocks.items():
                panel_path.unlink(missing_ok=True)
                if behavior == 'existing-panel':
                    panel_path.write_text(panel + '\n')
                if behavior == 'absent-record':
                    record_path.unlink(missing_ok=True)
                else:
                    record_path.write_text(f'boot {boot}\npre\n{record_panel}\n')
                profile_path.write_text('synthetic-profile\n')
                result = subprocess.run(
                    [busybox, 'sh', '-c', setup + block + suffix, 'panel-fixture', busybox,
                     boot, str(input_path), str(panel_path), str(record_path), owner, str(profile_path)],
                    capture_output=True, text=True, check=False,
                )
                assert not profile_path.exists(), (name, variant)
                matching = behavior in ('both', 'duplicates', 'conflicts', 'record-mismatch', 'overlong') or (
                    behavior == 'candidate' and variant == 'candidate'
                )
                skipped = behavior in ('existing-panel', 'absent-record')
                if not matching and not skipped and variant == 'candidate':
                    assert (result.returncode, result.stdout, result.stderr) == (
                        1, 'self-post-trace: pre check panel record rc=0\n', ''
                    ), (name, variant, result)
                    assert not panel_path.exists(), (name, variant)
                    continue
                hits = ''
                if matching:
                    hits = long_panel if behavior == 'overlong' else panel
                    if behavior == 'duplicates':
                        hits = f'{panel}\n{panel}'
                    elif behavior == 'conflicts':
                        hits = f'{panel}\n{conflict}'
                restored = matching and behavior not in ('conflicts', 'record-mismatch', 'overlong')
                expected = 'self-post-trace: pre check panel record rc=0\n'
                if restored:
                    expected += 'self-post-trace: panel record restored from the boot kernel log rc=0\n'
                expected += 'self-post-trace: post check panel record rc=0\n'
                expected += f'panel hits begin\n{hits}\npanel hits end\n'
                if restored or behavior == 'existing-panel':
                    expected += f'panel file begin\n{panel}\npanel file end\n'
                assert (result.returncode, result.stdout, result.stderr) == (0, expected, ''), (name, variant, result)
                assert panel_path.exists() == (restored or behavior == 'existing-panel'), (name, variant)
                if restored:
                    assert panel_path.read_text() == panel + '\n'
                    assert panel_path.stat().st_mode & 0o777 == 0o600
                    assert panel_path.stat().st_nlink == 1

    print('pass: exact old and c917 panel pipelines on host BusyBox; caller/nonmatch exits before candidate post-check; '
          'matches, duplicates and restore refusals observed; synthetic only, not a fix or device evidence')


def main():
    staged = builder.current_scripts()['pmos-radio-bringup.sh'].decode()
    assert sha(staged) == STAGED_SHA
    committed = persist.derive(staged)
    assert sha(committed) == COMMITTED_PERSISTENT_SHA
    radio, post, hook = derive_all(staged)

    assert 'armed and unacknowledged on this boot' in radio
    assert postack.derive(committed) == postack.derive(persist.derive(staged))

    for i, (old, _new) in enumerate(persist.BLOCKS):
        try:
            persist.derive(staged.replace(old, '', 1))
        except SystemExit:
            continue
        raise AssertionError(f'persistent derivation accepted a missing block {i}')
    for bad in (committed.replace(fresh.OLD, '', 1), committed + fresh.OLD):
        try:
            fresh.derive(bad)
        except SystemExit:
            continue
        raise AssertionError('fresh radio derivation accepted a missing or duplicate block')
    source = (here / 'pmos-self-post.sh').read_text()
    for old in (selfpost.OLD_RADIO, selfpost.OLD_SHA, selfpost.OLD_GREP):
        for bad in (source.replace(old, '', 1), source + old):
            try:
                selfpost.derive(bad, radio.encode())
            except SystemExit:
                continue
            raise AssertionError('self-post derivation accepted a missing or duplicate block')
    assert radio.count('firmware_mnt path already present but not the read-only vfat') == 2
    assert radio.count('empty firmware_mnt repair failed') == 1
    for marker in ('guarded remoteproc2 start', 'wpss-once', 'guest radio marker does not match this guard nonce',
                   'services already attempted this boot; no retry', 'own_digest()',
                   'persisted WLAN profile differs from standard input; no silent overwrite'):
        assert marker in radio, marker
    for marker in ('/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh',
                   'armed and unacknowledged', 'guest radio marker', 'boot record append refused'):
        assert marker in post, marker
    assert 'RADIO_SHA=7ef63826' not in post and 'RADIO="$STATE/pmos-radio-bringup.sh"' not in post
    assert 'rm -r' not in hook and 'rm -rf' not in hook and 'rmdir' not in hook
    assert hook.startswith('#!/bin/busybox sh\n') and 'setsid' in hook and 'local.d' not in hook

    installed_hook = '( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )'
    assert installed_hook in (here / 'pmos-self-stage.sh').read_text()
    assert "setsid /bin/busybox sh -c '\n" in hook
    assert "' self-post /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh >/dev/null 2>&1 & )" in hook

    assert selfpost.NEW_GREP in post and selfpost.OLD_GREP not in post
    test_panel_pipeline(source, post)

    for text, name in ((radio, 'radio'), (post, 'post'), (hook, 'hook')):
        for forbidden in ('fastboot', 'init_boot', 'vendor_boot', 'avb'):
            assert forbidden not in text, (name, forbidden)
    assert '2ebdf1db' not in radio + post + hook and 'a71b3f5f' not in radio + post + hook

    with tempfile.TemporaryDirectory(prefix='fresh-boot-291.') as tmp:
        work = pathlib.Path(tmp)
        paths = []
        for name, text in (('radio-fresh.sh', radio), ('post-fresh.sh', post), ('hook-fresh.sh', hook)):
            path = work / name
            path.write_text(text)
            paths.append(path)
        sh_n(paths)

    print(f'pass: fresh-boot candidate derived fail-closed and host-verified; '
          f'radio {RADIO_FRESH_SHA[:8]} post {POST_FRESH_SHA[:8]} hook {HOOK_SHA[:8]}; '
          f'no image, no device, nonce/capture/guard checks intact')


if __name__ == '__main__':
    main()
