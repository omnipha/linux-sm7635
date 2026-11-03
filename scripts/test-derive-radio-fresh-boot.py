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
import os
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


def test_panel_record_contract(post):
    busybox = shutil.which('busybox')
    if busybox is None:
        raise SystemExit('host BusyBox is required for the #301 panel contract fixture')
    if os.geteuid() == 0:
        raise SystemExit('the #301 panel contract fixture requires an unprivileged user')

    assert sha(post) == POST_FRESH_SHA, 'the #301 fixture requires the exact c917 prefix'
    start, end = "trace 'pre check panel record'\n", "trace 'record append entry'\n"
    assert post.count(start) == post.count(end) == 1, 'panel block boundaries changed'
    block = start + post.split(start, 1)[1].split(end, 1)[0]
    assignments = [line for line in block.splitlines(keepends=True) if line.startswith('\tpanel_hits=')]
    assert assignments == [selfpost.NEW_GREP], 'candidate panel pipeline differs from NEW_GREP'
    experiment = r'''\tpanel_hits=$($BB dmesg 2>/dev/null | $BB sed 's/^<[0-9][0-9]*>//; s/^\(\[[ 0-9.]*\]\[ *T1\] \|\[[ 0-9.]*\] \)\{0,1\}usb-init: //' | $BB grep -E "^usb-init: pre-SSH panel node=(boe|vxn|none) card0=[ -~]* boot $boot\$")
'''.replace(r'\t', '\t', 1)
    assert block.count(selfpost.NEW_GREP) == 1 and experiment != selfpost.NEW_GREP
    before, after = block.split(selfpost.NEW_GREP)
    assert experiment not in block and experiment not in post, 'experimental assignment leaked into candidate'
    experimental_block = block.replace(selfpost.NEW_GREP, experiment, 1)
    assert experimental_block.count(experiment) == 1
    assert experimental_block == before + experiment + after, 'experiment changed bytes outside assignment'
    assert experimental_block.replace(experiment, selfpost.NEW_GREP, 1) == block
    assert post.count(selfpost.NEW_GREP) == 1 and sha(post) == POST_FRESH_SHA
    blocks = {}
    for variant, candidate in (('original', block), ('experiment', experimental_block)):
        for original, replacement, count in (
            ('panel=/run/pmos-pre-ssh-panel.record', 'panel=$PANEL', 1),
            ('/.omnipha-boot-record', '"$RECORD"', 3),
        ):
            assert candidate.count(original) == count, f'{variant} panel path changed: {original}'
            candidate = candidate.replace(original, replacement)
        blocks[variant] = candidate
    assert blocks['experiment'].replace(experiment, selfpost.NEW_GREP, 1) == blocks['original']
    assert 'fixture_bb dmesg' not in ''.join(blocks.values())
    trace_start, trace_end = 'trace() {\n', '\n}\n'
    assert post.count(trace_start) == 1, 'candidate trace function changed'
    trace_function = trace_start + post.split(trace_start, 1)[1].split(trace_end, 1)[0] + trace_end
    assert post.splitlines()[1] == 'set -eu'

    boot = '11111111-2222-3333-4444-555555555555'
    foreign_boot = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    panel = (f'usb-init: pre-SSH panel node=boe card0=1 dsi1=1 dcs=none reset=none '
             f'suspend=clear brightness=0 boot {boot}')
    conflict = panel.replace('node=boe', 'node=vxn')
    foreign_panel = panel.replace(boot, foreign_boot)
    transition = 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'

    def pre_lines(boot_id, panel_line):
        return [
            f'boot {boot_id}',
            f'pmos-self-stage: diagnostic hold and :22 verified on boot {boot_id}',
            panel_line,
            'pmos-stage: using unpacked persistent postmarketOS root',
            'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts',
            'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)',
            'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)',
            'pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract',
            'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request',
            'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover',
            f'pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot {boot_id}',
            transition,
        ]

    def post_line(boot_id):
        return f'pmos-self-post: post-cutover PID 1 on boot {boot_id}; guard identity check passed; pid1 identity check passed'

    setup = r'''REAL_BB=$1
ROOT=$2
PANEL=$3
INPUT=$4
BOOT_ID_FILE=$5
OWNER=$6
CONTRACT=$7
RECORD=$ROOT/.omnipha-boot-record
PMOS_PANEL_RECORD=$PANEL
fixture_bb() {
    case "$1" in
        dmesg)
            [ "$#" = 1 ] || return 1
            "$REAL_BB" cat "$INPUT"; return;;
        cat)
            if [ "$#" = 2 ] && [ "$2" = /proc/sys/kernel/random/boot_id ]; then
                "$REAL_BB" cat "$BOOT_ID_FILE"; return
            fi;;
        sync)
            [ "$#" = 3 ] && [ "$2" = -f ] && [ "$3" = "$RECORD" ]; return;;
        stat)
            if [ "$#" = 4 ] && [ "$2" = -c ]; then
                case "$3:$4" in
                    "%u:$ROOT"|"%u:%a:%h:$PANEL"|"%u:%a:%h:%s:$RECORD")
                        fixture_stat=$("$REAL_BB" "$@") || return 1
                        case "$fixture_stat" in
                            "$OWNER") printf '0\n';;
                            "$OWNER":*) printf '0:%s\n' "${fixture_stat#*:}";;
                            *) printf '%s\n' "$fixture_stat";;
                        esac
                        return;;
                esac
            fi;;
    esac
    case "$1" in
        cat|stat|sed|printf|grep|sort|wc|awk) "$REAL_BB" "$@";;
        *) printf 'fixture FAIL: unexpected BusyBox applet %s\n' "$1" >&2; return 1;;
    esac
}
BB=fixture_bb
. "$CONTRACT"
umask 077
root_contract_pinned_userdata() {
    [ "$#" = 1 ] && [ "$1" = "$ROOT" ] || return 1
    ROOT_CONTRACT_OPTS=rw
}
fixture_fail() { printf 'fixture FAIL: %s\n' "$*" >&2; exit 90; }
log() { printf '%s\n' "$*"; }
die() { fixture_fail "$*"; }
''' + trace_function
    identify = r'''boot_record_id || fixture_fail 'synthetic boot ID refused'
boot=$br_boot
printf 'fixture: boot ID %s\n' "$boot"
'''
    prepare = r'''boot_record_open "$ROOT" || fixture_fail 'open refused'
initial=$("$REAL_BB" cat "$RECORD")
post="pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"
transition='usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'
if boot_record_append "$ROOT" 'pmos-stage: using unpacked persistent postmarketOS root'; then
    fixture_fail 'out-of-order stage append accepted'
fi
if boot_record_append "$ROOT" "$post"; then fixture_fail 'out-of-order post append accepted'; fi
if boot_record_verify "$ROOT" "$transition"; then fixture_fail 'incomplete transition verified'; fi
[ "$("$REAL_BB" cat "$RECORD")" = "$initial" ] || fixture_fail 'out-of-order attempt changed record'
printf 'fixture: out-of-order append and incomplete verify refused unchanged\n'
panel_line=$("$REAL_BB" cat "$PANEL")
boot_record_append "$ROOT" "pmos-self-stage: diagnostic hold and :22 verified on boot $boot" || fixture_fail 'hold append refused'
boot_record_append "$ROOT" "$panel_line" || fixture_fail 'panel append refused'
boot_record_append "$ROOT" 'pmos-stage: using unpacked persistent postmarketOS root' || fixture_fail 'unpacked append refused'
boot_record_append "$ROOT" 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' || fixture_fail 'mount append refused'
boot_record_append "$ROOT" 'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)' || fixture_fail 'SSH append refused'
boot_record_append "$ROOT" 'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)' || fixture_fail 'staged append refused'
boot_record_append "$ROOT" 'pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract' || fixture_fail 'root append refused'
boot_record_append "$ROOT" 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request' || fixture_fail 'key append refused'
boot_record_append "$ROOT" 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' || fixture_fail 'radio marker append refused'
boot_record_append "$ROOT" "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot" || fixture_fail 'request append refused'
boot_record_append "$ROOT" "$transition" || fixture_fail 'transition append refused'
boot_record_verify "$ROOT" "$transition" || fixture_fail 'transition verify refused'
printf 'fixture: full pre-cutover record verified\n'
'''
    attempt = r'''post="pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"
if boot_record_append "$ROOT" "$post"; then
    printf 'fixture: append accepted\n'
else
    printf 'fixture: append refused\n'
fi
if boot_record_verify "$ROOT" "$post"; then
    printf 'fixture: verify accepted\n'
else
    printf 'fixture: verify refused\n'
fi
'''
    no_match = (False, False, False)
    success = (True, True, True)
    refusal = (True, False, False)
    restored_refusal = (True, True, False)
    timestamp = '[    3.000000]'
    caller = f'{timestamp}[    T1] usb-init: '
    cases = (
        ('prefix-stripped-same-boot', f'usb-init: {panel}', boot, panel, '', success, success),
        ('timestamp', f'{timestamp} usb-init: {panel}', boot, panel, '', success, success),
        ('priority', f'<6>usb-init: {panel}', boot, panel, '', success, success),
        ('priority-timestamp', f'<6>{timestamp} usb-init: {panel}', boot, panel, '', success, success),
        ('timestamp-caller', f'{caller}{panel}', boot, panel, '', no_match, success),
        ('priority-timestamp-caller', f'<6>{caller}{panel}', boot, panel, '', no_match, success),
        ('caller-unpadded', f'{timestamp}[T1] usb-init: {panel}', boot, panel, '', no_match, success),
        ('caller-wide-padding', f'{timestamp}[       T1] usb-init: {panel}', boot, panel, '', no_match, success),
        ('caller-thread-t2', f'{timestamp}[    T2] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-thread-t10', f'{timestamp}[   T10] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-thread-t01', f'{timestamp}[   T01] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-cpu', f'{timestamp}[    C1] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-trailing-padding', f'{timestamp}[T1 ] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-tab-padding', f'{timestamp}[\tT1] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-missing-bracket', f'{timestamp}[    T1 usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-missing-separator', f'{timestamp}[    T1]usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-extra-separator', f'{timestamp}[    T1]  usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-without-timestamp', f'[    T1] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-separated-from-timestamp', f'{timestamp} [    T1] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-extra-bracket', f'{timestamp}[    T1][    T1] usb-init: {panel}', boot, panel, '', no_match, no_match),
        ('caller-embedded', f'prefix {caller}{panel}', boot, panel, '', no_match, no_match),
        ('caller-single-tag', f'{timestamp}[    T1] {panel}', boot, panel, '', no_match, no_match),
        ('caller-invalid-node', f'{caller}{panel.replace("node=boe", "node=other")}', boot, panel, '', no_match, no_match),
        ('caller-prefix-only', f'{caller}', boot, panel, '', no_match, no_match),
        ('caller-malformed-priority', f'<x>{caller}{panel}', boot, panel, '', no_match, no_match),
        ('caller-extra-suffix', f'{caller}{panel} trailing', boot, panel, '', no_match, no_match),
        ('caller-overlong', f'{caller}{panel.replace("card0=1", "card0=" + "x" * 401)}', boot, panel, '', no_match, refusal),
        ('caller-foreign-only', f'{caller}{foreign_panel}', boot, panel, '', no_match, no_match),
        ('foreign-boot-only', f'usb-init: {foreign_panel}', boot, panel, '', no_match, no_match),
        ('absent', '', boot, panel, '', no_match, no_match),
        ('same-boot-conflict', f'usb-init: {panel}\nusb-init: {conflict}', boot, panel, '', refusal, refusal),
        ('caller-conflict', f'{caller}{panel}\n{caller}{conflict}', boot, panel, '', no_match, refusal),
        ('mixed-format-conflict', f'usb-init: {panel}\n{caller}{conflict}', boot, panel, '', success, refusal),
        ('unsupported-caller-conflict', f'{caller}{panel}\n{timestamp}[    T2] usb-init: {conflict}', boot, panel, '', no_match, success),
        ('identical-duplicates', f'usb-init: {panel}\nusb-init: {panel}', boot, panel, '', success, success),
        ('caller-identical-duplicates', f'{caller}{panel}\n{caller}{panel}', boot, panel, '', no_match, success),
        ('line-3-mismatch', f'usb-init: {panel}', boot, conflict, '', refusal, refusal),
        ('caller-line-3-mismatch', f'{caller}{panel}', boot, conflict, '', no_match, refusal),
        ('foreign-persistent-identity', f'usb-init: {panel}', foreign_boot, panel, '', restored_refusal, restored_refusal),
        ('foreign-mixed-with-valid', f'usb-init: {foreign_panel}\nusb-init: {panel}', boot, panel, '', success, success),
        ('caller-foreign-mixed-with-valid', f'{caller}{foreign_panel}\n{caller}{panel}', boot, panel, '', no_match, success),
        ('caller-foreign-different-node-mixed', f'{caller}{foreign_panel.replace("node=boe", "node=vxn")}\n{caller}{panel}', boot, panel, '', no_match, success),
        ('unsafe-record-mode', f'usb-init: {panel}', boot, panel, 'mode', restored_refusal, restored_refusal),
        ('hardlinked-record', f'usb-init: {panel}', boot, panel, 'link', restored_refusal, restored_refusal),
        ('oversized-record', f'usb-init: {panel}', boot, panel, 'size', restored_refusal, restored_refusal),
    )
    print('caveat #301: synthetic boot ID and dmesg; temporary-user ownership mapped to root; '
          'userdata/mount identity modeled rw; sync is a no-op; real mode, link, size and ordering checks')
    print('caveat #301: c917 panel block only; full 9a8c candidate not built or run; '
          'no device evidence, radio, gate, guard, capture or ACK execution')
    print('caveat #301: foreign persistent identity deliberately retains the current-boot panel line '
          'to isolate the record identity check')
    print('caveat experiment: in-memory host-only assignment, not a generated or deployable successor; '
          'the whole #294 candidate was not run; only timestamp-adjacent T1 with optional leading spaces is modeled')
    print('caveat experiment: the log supplies panel evidence; the persistent record supplies only line-3 equality '
          'and ordering, not independent panel evidence')
    print('caveat: the original ignores T1 lines; the experiment ignores unsupported caller formats, '
          'so conflicts exclusively in ignored formats are not detected')
    print('caveat diagnostics: unmodified contract under modeled dependencies; real guard, root/mount identity, '
          'nonce and ACK are not executed or verified; synthetic source/model is not physical proof')

    def write_private(path, value):
        path.write_text(value, encoding='ascii')
        path.chmod(0o600)

    def run(script, positional):
        return subprocess.run([busybox, 'sh', '-eu', '-c', script] + positional,
                              capture_output=True, text=True, check=False,
                              env={'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'})

    assert not pathlib.Path(tempfile.gettempdir()).resolve().is_relative_to(here.parent.resolve()), (
        'fixture temp directory is inside the repository'
    )
    with tempfile.TemporaryDirectory(prefix='panel-contract-301.') as tmp:
        work = pathlib.Path(tmp)
        owner = str(os.geteuid())
        assert work.stat().st_uid == os.geteuid() and work.stat().st_mode & 0o777 == 0o700
        scenarios = (
            (variant, name, text, seed_boot, record_panel, mutation, expectations)
            for name, text, seed_boot, record_panel, mutation, original_expected, experiment_expected in cases
            for variant, expectations in (('original', original_expected), ('experiment', experiment_expected))
        )
        for variant, name, text, seed_boot, record_panel, mutation, expectations in scenarios:
            reached, restored, accepted = expectations
            label = f'{name}/{variant}'
            case = work / f'{name}-{variant}'
            case.mkdir(mode=0o700)
            root = case / 'root'
            root.mkdir(mode=0o700)
            input_path, panel_path, boot_path = (case / item for item in ('dmesg', 'panel', 'boot-id'))
            record_path = root / '.omnipha-boot-record'

            write_private(input_path, text + '\n' if text else '')
            write_private(panel_path, record_panel + '\n')
            write_private(boot_path, seed_boot + '\n')
            positional = ['panel-contract-301', busybox, str(root), str(panel_path), str(input_path),
                          str(boot_path), owner, str(here / 'pmos-root-contract.sh')]

            result = run(setup + identify + prepare, positional)
            expected = (f'fixture: boot ID {seed_boot}\n'
                        'fixture: out-of-order append and incomplete verify refused unchanged\n'
                        'fixture: full pre-cutover record verified\n')
            assert (result.returncode, result.stdout, result.stderr) == (0, expected, ''), (label, 'prepare', result)
            pre = ('\n'.join(pre_lines(seed_boot, record_panel)) + '\n').encode('ascii')
            assert record_path.read_bytes() == pre, (label, 'pre-cutover content')
            info = record_path.stat()
            assert (info.st_uid, info.st_mode & 0o777, info.st_nlink, info.st_size) == (
                os.geteuid(), 0o600, 1, len(pre)
            ) and info.st_size <= 4096, (label, 'pre-cutover metadata', info)
            assert pre.splitlines()[2].decode('ascii') == record_panel, (label, 'panel is not line 3')
            panel_path.unlink()
            write_private(boot_path, boot + '\n')
            if mutation == 'mode':
                record_path.chmod(0o644)
            elif mutation == 'link':
                os.link(record_path, root / 'record-link')
            elif mutation == 'size':
                with record_path.open('ab') as stream:
                    stream.write(b'x' * 4096 + b'\n')
                assert record_path.stat().st_size > 4096, label
            before = record_path.read_bytes()
            before_info = record_path.stat()

            result = run(setup + identify + blocks[variant] + attempt, positional)
            expected = f'fixture: boot ID {boot}\nself-post-trace: pre check panel record rc=0\n'
            if restored:
                expected += 'self-post-trace: panel record restored from the boot kernel log rc=0\n'
            if reached:
                expected += 'self-post-trace: post check panel record rc=0\n'
                expected += 'fixture: append accepted\nfixture: verify accepted\n' if accepted else (
                    'fixture: append refused\nfixture: verify refused\n'
                )
            assert (result.returncode, result.stdout, result.stderr) == (
                0 if reached else 1, expected, ''
            ), (label, 'parser and contract', result, expected)
            assert panel_path.exists() == restored, (label, 'panel restoration', result)
            if restored:
                info = panel_path.stat()
                assert panel_path.read_text(encoding='ascii') == panel + '\n', (label, 'restored panel content')
                assert (info.st_uid, info.st_mode & 0o777, info.st_nlink, info.st_size) == (
                    os.geteuid(), 0o600, 1, len(panel) + 1
                ), (label, 'restored panel metadata', info)
            if accepted:
                assert record_path.read_bytes() == pre + (post_line(boot) + '\n').encode('ascii'), (label, 'post record')
                info = record_path.stat()
                assert (info.st_uid, info.st_mode & 0o777, info.st_nlink, info.st_size) == (
                    os.geteuid(), 0o600, 1, len(pre) + len(post_line(boot)) + 1
                ) and info.st_size <= 4096, (label, 'post metadata', info)
            else:
                assert record_path.read_bytes() == before, (label, 'refused parser attempt changed record')
                assert panel_path.exists() == restored, (label, 'panel changed before independent attempt')
                independent = run(setup + identify + attempt, positional)
                expected_independent = (f'fixture: boot ID {boot}\n'
                                        'fixture: append refused\nfixture: verify refused\n')
                assert (independent.returncode, independent.stdout, independent.stderr) == (
                    0, expected_independent, ''
                ), (label, 'independent contract attempt', independent)
                after_info = record_path.stat()
                assert panel_path.exists() == restored, (label, 'independent attempt changed panel state')
                assert record_path.read_bytes() == before and (
                    after_info.st_mode, after_info.st_nlink, after_info.st_size
                ) == (before_info.st_mode, before_info.st_nlink, before_info.st_size), (
                    label, 'independent refusal changed record'
                )
            state = 'restored' if restored else 'not restored'
            if accepted:
                outcome = 'append/verify accepted'
            elif reached:
                outcome = 'in-child and independent append/verify refused unchanged'
            else:
                outcome = 'no in-child append; independent append/verify refused unchanged'
            print(f'pass #301: {label}: parser {"continued" if reached else "exited 1 before post-check"}; '
                  f'panel {state}; {outcome}')

        diagnostics = (
            ('producer-failure-empty', '', panel, False, False, False),
            ('producer-failure-partial-raw', f'usb-init: {panel}', panel, False, False, True),
            ('producer-failure-partial-t1', f'{caller}{panel}', panel, False, True, True),
            ('existing-foreign-panel', '', foreign_panel, True, False, False),
        )
        producer_original = '''        dmesg)
            [ "$#" = 1 ] || return 1
            "$REAL_BB" cat "$INPUT"; return;;
'''
        producer_failure = '''        dmesg)
            [ "$#" = 1 ] || return 91
            printf 'invoked\\n' > "$PRODUCER_MARKER" || return 92
            "$REAL_BB" cat "$INPUT" || return 93
            return 23;;
'''
        assert setup.count(producer_original) == 1
        diagnostic_setup = setup.replace(producer_original, producer_failure, 1)
        assert diagnostic_setup.replace(producer_failure, producer_original, 1) == setup
        diagnostic_setup += r'''PRODUCER_MARKER=$INPUT.invoked
'''
        for name, text, seed_panel, existing, t1_only, has_output in diagnostics:
            for variant in ('original', 'experiment'):
                label = f'{name}/{variant}'
                case = work / f'diagnostic-{name}-{variant}'
                case.mkdir(mode=0o700)
                root = case / 'root'
                root.mkdir(mode=0o700)
                input_path, panel_path, boot_path = (case / item for item in ('dmesg', 'panel', 'boot-id'))
                record_path = root / '.omnipha-boot-record'
                producer_marker = case / 'dmesg.invoked'
                write_private(input_path, text + '\n' if text else '')
                write_private(panel_path, seed_panel + '\n')
                write_private(boot_path, boot + '\n')
                positional = ['panel-diagnostic-301', busybox, str(root), str(panel_path), str(input_path),
                              str(boot_path), owner, str(here / 'pmos-root-contract.sh')]
                if not existing:
                    probe = run(diagnostic_setup + r'''fixture_bb dmesg
''', positional)
                    assert (probe.returncode, probe.stdout, probe.stderr) == (
                        23, text + '\n' if text else '', ''
                    ), (label, 'standalone failed producer', probe)
                    assert producer_marker.read_text(encoding='ascii') == 'invoked\n', label
                    producer_marker.unlink()
                result = run(diagnostic_setup + identify + prepare, positional)
                expected = (f'fixture: boot ID {boot}\n'
                            'fixture: out-of-order append and incomplete verify refused unchanged\n'
                            'fixture: full pre-cutover record verified\n')
                assert (result.returncode, result.stdout, result.stderr) == (0, expected, ''), (
                    label, 'prepare', result
                )
                pre = ('\n'.join(pre_lines(boot, seed_panel)) + '\n').encode('ascii')
                assert record_path.read_bytes() == pre, (label, 'pre-cutover record')
                record_info = record_path.stat()
                assert (record_info.st_uid, record_info.st_mode & 0o777, record_info.st_nlink, record_info.st_size) == (
                    os.geteuid(), 0o600, 1, len(pre)
                ) and record_info.st_size <= 4096, (label, 'pre-cutover metadata', record_info)
                if existing:
                    assert boot != foreign_boot and pre.splitlines()[0] == f'boot {boot}'.encode('ascii')
                    assert pre.splitlines()[2] == foreign_panel.encode('ascii')
                    panel_before = panel_path.stat()
                    assert not panel_path.is_symlink() and panel_path.read_text(encoding='ascii') == foreign_panel + '\n'
                    assert (panel_before.st_uid, panel_before.st_mode & 0o777, panel_before.st_nlink) == (
                        os.geteuid(), 0o600, 1
                    ), (label, 'pre-existing panel metadata', panel_before)
                else:
                    panel_path.unlink()
                assert not producer_marker.exists(), (label, 'producer ran before panel block')
                result = run(diagnostic_setup + identify + blocks[variant] + attempt, positional)
                reached = existing or (has_output and (not t1_only or variant == 'experiment'))
                expected = f'fixture: boot ID {boot}\nself-post-trace: pre check panel record rc=0\n'
                if reached and not existing:
                    expected += 'self-post-trace: panel record restored from the boot kernel log rc=0\n'
                if reached:
                    expected += ('self-post-trace: post check panel record rc=0\n'
                                 'fixture: append accepted\nfixture: verify accepted\n')
                assert (result.returncode, result.stdout, result.stderr) == (
                    0 if reached else 1, expected, ''
                ), (label, 'observed panel block and contract', result, expected)
                assert producer_marker.exists() != existing, (label, 'unexpected producer invocation')
                if not existing:
                    assert producer_marker.read_text(encoding='ascii') == 'invoked\n', label
                assert panel_path.exists() == reached, (label, 'observed panel state')
                if reached:
                    panel_info = panel_path.stat()
                    assert panel_path.read_text(encoding='ascii') == seed_panel + '\n', (label, 'panel content')
                    assert (panel_info.st_uid, panel_info.st_mode & 0o777, panel_info.st_nlink, panel_info.st_size) == (
                        os.geteuid(), 0o600, 1, len(seed_panel) + 1
                    ), (label, 'panel metadata', panel_info)
                    if existing:
                        assert (panel_info.st_dev, panel_info.st_ino) == (panel_before.st_dev, panel_before.st_ino), (
                            label, 'existing panel was replaced'
                        )
                        assert not seed_panel.endswith(f' boot {boot}'), (label, 'foreign panel was accepted as same-boot')
                    expected_record = pre + (post_line(boot) + '\n').encode('ascii')
                    assert record_path.read_bytes() == expected_record, (label, 'observed appended record')
                    record_info = record_path.stat()
                    assert (record_info.st_uid, record_info.st_mode & 0o777, record_info.st_nlink, record_info.st_size) == (
                        os.geteuid(), 0o600, 1, len(expected_record)
                    ) and record_info.st_size <= 4096, (label, 'appended metadata', record_info)
                    if existing:
                        print(f'known limitation: {label}: existing foreign-boot panel bypassed dmesg and restore; '
                              'the modeled contract appended and verified, not a same-boot identity check')
                    else:
                        print(f'known limitation: {label}: producer exited 23 after synthetic output; '
                              'final grep masked failure, panel restored and modeled contract appended/verified; '
                              'failed output is not valid evidence')
                else:
                    assert record_path.read_bytes() == pre, (label, 'parser exit changed record')
                    independent = run(diagnostic_setup + identify + attempt, positional)
                    expected = (f'fixture: boot ID {boot}\n'
                                'fixture: append refused\nfixture: verify refused\n')
                    assert (independent.returncode, independent.stdout, independent.stderr) == (
                        0, expected, ''
                    ), (label, 'independent contract refusal', independent)
                    after_info = record_path.stat()
                    assert not panel_path.exists() and record_path.read_bytes() == pre and (
                        after_info.st_dev, after_info.st_ino, after_info.st_mode, after_info.st_nlink, after_info.st_size
                    ) == (
                        record_info.st_dev, record_info.st_ino, record_info.st_mode, record_info.st_nlink, record_info.st_size
                    ), (label, 'independent refusal changed synthetic state')
                    print(f'diagnostic: {label}: producer exited 23; parser exited 1 before post-check; '
                          'no panel, independent append/verify refused unchanged')

        for invalid in ('not-a-boot-id', 'g1111111-2222-3333-4444-555555555555'):
            write_private(boot_path, invalid + '\n')
            result = run(setup + r'''if boot_record_id; then fixture_fail 'invalid synthetic boot ID accepted'; fi
printf 'fixture: invalid synthetic boot ID refused\n'
''', positional)
            assert (result.returncode, result.stdout, result.stderr) == (
                0, 'fixture: invalid synthetic boot ID refused\n', ''
            ), ('boot_record_id', invalid, result)
        malformed = '11111111-2222-3333-4444-55555555555-'
        write_private(boot_path, malformed + '\n')
        result = run(setup + f'''EXPECTED_BOOT={malformed}
''' + r'''boot_record_id || fixture_fail 'malformed synthetic boot ID refused'
[ "$br_boot" = "$EXPECTED_BOOT" ] || fixture_fail 'synthetic boot ID changed'
printf 'fixture: malformed synthetic boot ID accepted\n'
''', positional)
        assert (result.returncode, result.stdout, result.stderr) == (
            0, 'fixture: malformed synthetic boot ID accepted\n', ''
        ), ('boot_record_id', malformed, result)
        print('pass #301: real boot_record_id accepted synthetic IDs and rejected invalid length and non-hex input')
        print('known limitation: boot_record_id accepted a synthetic misplaced trailing hyphen; '
              'this is not a valid boot identity')
        print('pass #301: identical duplicate panel values are accepted by sort -u, not rejected')
    assert sha(post) == POST_FRESH_SHA and post.count(selfpost.NEW_GREP) == 1, 'production prefix changed'


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
    test_panel_record_contract(post)

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
