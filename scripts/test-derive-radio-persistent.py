#!/usr/bin/env python3
import hashlib
import importlib.util
import os
import pathlib
import shutil
import subprocess
import tempfile

here = pathlib.Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


p = load('persist', 'derive-radio-persistent.py')
postack = load('postack', 'derive-radio-postack.py')
src = (here / 'pmos-radio-bringup.sh').read_text()
committed = (here / 'pmos-radio-bringup-persistent.sh').read_text()
out = p.derive(src)
assert out == committed, 'committed persistent variant is not the derived output'
assert hashlib.sha256(out.encode()).hexdigest() == '58476d7718227dc216d19942ad032170248296ccb0227fa667d15d0cd37ab8ac'
assert out.split('own_digest() {')[1] != src
for marker in ('armed and unacknowledged on this boot', 'capture_gate()', 'LEASE_SHA=',
               'guest radio marker does not match this guard nonce'):
    assert marker in out, marker
assert 'wpa_supplicant_if="wlan0"' in out
assert 'another OpenRC service enabled' in out
assert 'persisted WLAN profile differs from standard input; no silent overwrite' in out

for i, (old, _new) in enumerate(p.BLOCKS):
    bad = src.replace(old, '', 1)
    try:
        p.derive(bad)
    except SystemExit:
        continue
    raise AssertionError(f'derivation accepted a missing block {i}')

for name, text in (('repo', out), ('postack', postack.derive(out))):
    with tempfile.NamedTemporaryFile('w', suffix='.sh') as f:
        f.write(text)
        f.flush()
        subprocess.run(['sh', '-n', f.name], check=True)

builder = load('persistent_builder', 'build-init-boot-persistent-root.py')
current = builder.current_scripts()
runtime = builder.runtime_scripts()
verifier = load('persistent_verifier', 'verify-init-boot-persistent-root.py')
verifier.check_runtime_scripts(runtime)
variant = load('route_cache_variant_311', 'build-init-boot-route-cache-candidate.py')
candidate_scripts = variant.runtime_scripts()
assert variant.verifier.builder is variant.builder
assert variant.RUN113_INIT in variant.verifier.refused() and variant.RUN113_CARRIER in variant.verifier.refused()
assert builder.GATED_POST_SHA == variant.route_cache.OLD_POST_SHA
assert builder.GATED_HOOK_SHA == variant.route_cache.OLD_HOOK_SHA
for count in (0, -1, 2):
    try:
        variant.replace_count(b'old', b'old', b'new', count)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid variant replacement count accepted')
staged = current['pmos-radio-bringup.sh'].decode()
assert hashlib.sha256(staged.encode()).hexdigest() == \
    'f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f'
derived = p.derive(staged)
assert p.SHORTCUT in staged and p.SHORTCUT not in derived
for bad in (staged + p.SHORTCUT, staged.replace(p.SHORTCUT, '', 1),
            staged.replace(p.SHORTCUT, p.SHORTCUT.replace('return 0', 'return 1'), 1)):
    try:
        p.derive(bad)
    except SystemExit:
        pass
    else:
        raise AssertionError('derivation accepted a missing, duplicated or modified services shortcut')
assert hashlib.sha256(derived.encode()).hexdigest() == \
    '1b6ec7be7db00345b9266ab7687521d0ac68108500498a852ddfb83c173d6fd4'
assert 'LEASE_SHA=1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56' in derived
assert 'persistent OpenRC WLAN services already running; no reinstall' not in derived
postack_derived = postack.derive(derived)
assert hashlib.sha256(postack_derived.encode()).hexdigest() == \
    '3b1f583dbaf925ebcf2f42c5628649ec34e8e3fdf0031e9ee2b436f334d24a8a'
assert p.derive(postack.derive(staged)) == postack_derived, 'derivations do not commute'
assert 'LEASE_SHA=1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56' in postack_derived
assert 'armed and unacknowledged on this boot' not in postack_derived
assert 'armed and acknowledged on this boot' in postack_derived
assert 'own_digest()' in postack_derived
with tempfile.NamedTemporaryFile('w', suffix='.sh') as f:
    f.write(postack_derived)
    f.flush()
    subprocess.run(['sh', '-n', f.name], check=True)
stage = builder.current_scripts()['pmos-session-stage.sh'].decode()
start = stage.index('for level in sysinit boot default nonetwork shutdown; do\n')
end = stage.index('for hook in "$PMOS_ROOT"/etc/local.d/*.start', start)
second = stage.index('if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then\n\tfor service in wpa_supplicant networking; do\n', end)
block = stage[start:stage.index('if [ ! -e "$PMOS_ROOT/sbin/init" ]', second)]
assert block.index('unexpected enabled OpenRC service') < block.index('unexpected local startup hook')
assert block.index('unexpected local startup hook') < block.index('cannot defer OpenRC service')
assert block.index('cannot defer OpenRC service') < block.index('cannot enable RAM-only local service')
busybox = shutil.which('busybox')
assert busybox is not None
with tempfile.TemporaryDirectory(prefix='radio-order-311.') as tmp:
    root = pathlib.Path(tmp)
    for level in ('sysinit', 'boot', 'default', 'nonetwork', 'shutdown'):
        (root / 'etc/runlevels' / level).mkdir(parents=True)
    (root / 'etc/init.d').mkdir(parents=True)
    (root / 'etc/local.d').mkdir(parents=True)
    local = root / 'etc/init.d/local'
    local.write_text('local\n')
    local.chmod(0o755)
    default = root / 'etc/runlevels/default'
    local_link = default / 'local'
    local_link.symlink_to('/etc/init.d/local')
    hook = root / 'etc/local.d/10-omnipha-self-stage.start'
    hook.write_bytes(runtime['10-omnipha-self-stage.start'])
    hook.chmod(0o700)
    assert hook.read_bytes() == runtime['10-omnipha-self-stage.start']
    setup = '''set -eu
REAL_BB=$1
PMOS_ROOT=$2
PMOS_ROOT_KIND=ext4
fixture_bb() {
    if [ "$1" = stat ] && [ "$2" = -c ] && [ "$3" = '%u:%g:%a:%h' ] &&
        [ "$4" = "$PMOS_ROOT/etc/local.d/10-omnipha-self-stage.start" ]; then
        owner=$($REAL_BB stat -c %u "$4")
        [ "$owner" = "$($REAL_BB id -u)" ] || return 1
        printf '0:0:%s:%s\\n' "$($REAL_BB stat -c %a "$4")" "$($REAL_BB stat -c %h "$4")"
        return
    fi
    "$REAL_BB" "$@"
}
BB=fixture_bb
die() { printf 'FAIL: %s\\n' "$*" >&2; exit 1; }
'''
    def run_stage(bb=busybox):
        return subprocess.run([bb, 'sh', '-c', setup + block, 'fixture', bb, str(root)],
                              capture_output=True, text=True, check=False)
    wpa, net = default / 'wpa_supplicant', default / 'networking'
    for path in (wpa, net):
        path.symlink_to('/etc/init.d/' + path.name)
    ok = run_stage()
    assert ok.returncode == 0, ok.stderr
    assert local_link.is_symlink() and not wpa.is_symlink() and not net.is_symlink()
    assert hook.is_file() and hook.read_bytes() == runtime['10-omnipha-self-stage.start']
    ok = run_stage()
    assert ok.returncode == 0 and local_link.is_symlink() and not wpa.exists() and not net.exists(), ok.stderr
    for path in (wpa, net):
        path.symlink_to('/etc/init.d/' + path.name)
    foreign = root / 'etc/runlevels/boot/foreign'
    foreign.touch()
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected enabled OpenRC service' in bad.stderr
    assert wpa.is_symlink() and net.is_symlink()
    foreign.unlink()
    net.unlink()
    net.symlink_to('/etc/init.d/sshd')
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected enabled OpenRC service' in bad.stderr
    assert wpa.is_symlink() and net.is_symlink() and os.readlink(net) == '/etc/init.d/sshd'
    net.unlink()
    net.symlink_to('/etc/init.d/networking')
    foreign = root / 'etc/runlevels/nonetwork/.foreign'
    foreign.touch()
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected enabled OpenRC service' in bad.stderr
    assert wpa.is_symlink() and net.is_symlink()
    foreign.unlink()
    foreign = root / 'etc/local.d/11-foreign.start'
    foreign.touch()
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr
    assert wpa.is_symlink() and net.is_symlink()
    foreign.unlink()
    hook.chmod(0o755)
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr
    assert wpa.is_symlink() and net.is_symlink()
    hook.chmod(0o700)
    original_hook = hook.read_bytes()
    hook.write_bytes(b'foreign root-owned hook\n')
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr
    assert wpa.is_symlink() and net.is_symlink()
    legacy_hook = (b'#!/bin/busybox sh\n'
                   b'( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh '
                   b'>/dev/null 2>&1 & )\n')
    hook.write_bytes(legacy_hook)
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr, bad.stderr
    assert hook.read_bytes() == legacy_hook and wpa.is_symlink() and net.is_symlink()
    hook.write_bytes(original_hook)
    hook_alias = root / 'hook-alias'
    os.link(hook, hook_alias)
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr, bad.stderr
    hook_alias.unlink()
    hook.unlink()
    hook.symlink_to('/etc/init.d/local')
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr
    hook.unlink()
    hook.symlink_to('missing')
    bad = run_stage()
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr
    hook.unlink()
    ok = run_stage()
    assert ok.returncode == 0 and not hook.exists(), ok.stderr
    hook.write_bytes(original_hook)
    hook.chmod(0o700)
    local_link.unlink()
    bad = run_stage()
    assert bad.returncode == 0 and local_link.is_symlink(), bad.stderr
    assert not wpa.is_symlink() and not net.is_symlink()
    assert os.readlink(local_link) == '/etc/init.d/local'
assert hashlib.sha256(runtime['pmos-radio-bringup.sh']).hexdigest() == builder.FRESH_RADIO_SHA
assert hashlib.sha256(runtime['pmos-self-post-fresh-boot.sh']).hexdigest() == builder.GATED_POST_SHA
assert hashlib.sha256(runtime['10-omnipha-self-stage.start']).hexdigest() == builder.GATED_HOOK_SHA
assert b"chain_dir=/run/omnipha-self-stage" in runtime['pmos-self-stage.sh']
assert b"RADIO_SHA=" + builder.FRESH_RADIO_SHA.encode() in runtime['pmos-self-stage.sh']
assert b"RADIO_SHA=" + builder.STAGED_RADIO_SHA.encode() in current['pmos-self-stage.sh']
print('pass: runtime_scripts overlay derives fresh radio, gated post and hook without current_scripts recursion')
print('pass: pre-cutover runlevel reconciliation, repeat, and foreign entry, target and local hook refusals; hook ownership modeled')
installer = 'set -eu\n' + builder.persistent_installer().decode()
installer_setup = '''set -eu
REAL_BB=$1
GUEST=$2
sources=$3
mountinfo=$4
race=$5
dev_spoof=$6
root_kind=$7
fixture_bb() {
    case "$1" in
        ln)
            [ "$2" = -T ] || return 1
            case "$4" in
                *.omnipha-legacy)
                    case "$race" in
                        backup-fail) return 1;;
                        backup-exists) printf 'raced backup\\n' > "$4";;
                        target-edit) printf '# raced edit\\n' >> "$3";;
                    esac;;
                *)
                    if [ "$race" = file ]; then
                        (umask 077; set -C; printf 'raced target\\n' > "$4") || return 1
                    elif [ "$race" = dir ]; then
                        "$REAL_BB" mkdir "$4" || return 1
                    fi;;
            esac;;
        mv)
            [ "$race" != replace-fail ] || return 1;;
        sync)
            [ "$race" != sync-fail ] || return 1
            case "$race:$3" in backup-sync-fail:*.omnipha-legacy) return 1;; esac;;
        awk)
            if [ "$2" = -v ] && [ "$3" = "r=$GUEST" ]; then
                "$REAL_BB" awk "$2" "$3" "$4" "$mountinfo"
                return
            fi;;
        sha256sum)
            if [ -n "${SHA_MODE:-}" ] && [ "$#" -eq 2 ] && [ "$2" = "${SHA_PATH:-}" ]; then
                printf '%s\\n' "$2" >> "$SHA_TRACE"
                case "$SHA_MODE" in
                    digest) printf '%s  %s\\n' "$SHA_VALUE" "$2"; return 0;;
                    fail) return 1;;
                    fail-with-output) printf '%s  %s\\n' "$SHA_VALUE" "$2"; return 1;;
                    empty) return 0;;
                    garbage) printf 'not-a-digest  %s\\n' "$2"; return 0;;
                esac
            fi;;
        stat)
            if [ "$2" = -c ]; then
                case "$4" in
                    "$GUEST"|"$GUEST/usr"|"$GUEST/etc"|"$GUEST/etc/local.d"|\\
                    "$GUEST/usr/libexec"|"$GUEST/usr/libexec/omnipha"|\\
                    "$GUEST"/usr/libexec/omnipha/*|"$GUEST"/etc/local.d/*|\\
                    "$sources"|"$sources"/*|"$GUEST"/usr/libexec/omnipha/*.omnipha-new*|\\
                    "$GUEST"/etc/local.d/*.omnipha-new*)
                        owner=$($REAL_BB stat -c %u "$4")
                        [ "$owner" = "$($REAL_BB id -u)" ] || return 1
                        mode=$($REAL_BB stat -c %a "$4")
                        links=$($REAL_BB stat -c %h "$4")
                        device=$($REAL_BB stat -c %d "$GUEST")
                        this=$($REAL_BB stat -c %d "$4")
                        if [ "$dev_spoof" = dev ]; then
                            this=$((this + 1))
                        fi
                        if [ "$3" = '%u:%a' ] || [ "$3" = '%u:%g:%a' ]; then
                            printf '0:0:%s\\n' "$mode"
                            return
                        fi
                        if [ "$3" = '%u:%g:%a:%d' ]; then
                            printf '0:0:%s:%s\\n' "$mode" "$this"
                            return
                        fi
                        if [ "$3" = '%u:%g:%a:%h' ]; then
                            printf '0:0:%s:%s\\n' "$mode" "$links"
                            return
                        fi
                        if [ "$3" = '%d:%i' ]; then
                            printf '%s\\n' "$($REAL_BB stat -c '%d:%i' "$4")"
                            return
                        fi
                        if [ "$3" = '%d:%i:%u:%g:%a:%h' ]; then
                            printf '%s:0:0:%s:%s\\n' "$($REAL_BB stat -c '%d:%i' "$4")" "$mode" "$links"
                            return
                        fi
                        if [ "$3" = '%d:%i:%u:%g:%a:%s:%Y' ]; then
                            printf '%s:0:0:%s:%s\\n' "$($REAL_BB stat -c '%d:%i' "$4")" "$mode" "$($REAL_BB stat -c '%s:%Y' "$4")"
                            return
                        fi
                        if [ "$3" = '%d' ]; then
                            printf '%s\\n' "$device"
                            return
                        fi
                        if [ "$3" = '%t:%T' ]; then
                            printf '11:1\\n'
                            return
                        fi
                        ;;
                esac
            fi;;
    esac
    "$REAL_BB" "$@"
}
BB=fixture_bb
die() { printf 'FAIL: %s\\n' "$*" >&2; exit 1; }
'''
assert installer.count('chain_dir=/run/omnipha-self-stage\n') == 1
assert installer.count('/run/pmos-root-contract.sh') == 3
test_installer = installer.replace('chain_dir=/run/omnipha-self-stage\n', 'chain_dir="$sources"\n', 1)
test_installer = test_installer.replace('/run/pmos-root-contract.sh', '"$sources/fixture-contract"')
assert 'chain_dir="$sources"' in test_installer and '. "$sources/fixture-contract"' in test_installer
assert '/run/pmos-root-contract.sh' not in test_installer
def run_installer(guest, sources, mountinfo_path=None, race='none', dev_spoof='none', root_kind='rw', bb=busybox, sha=None):
    env = dict(os.environ)
    env.pop('SHA_MODE', None)
    if sha is not None:
        env.update({'SHA_MODE': sha[0], 'SHA_PATH': str(sha[1]), 'SHA_VALUE': sha[2], 'SHA_TRACE': str(sha[3])})
    return subprocess.run([bb, 'sh', '-c', installer_setup + test_installer, 'fixture',
                           bb, str(guest), str(sources), str(mountinfo_path or (guest / 'mountinfo')), race, dev_spoof, root_kind],
                          capture_output=True, text=True, check=False, env=env)
specs = (('pmos-radio-bringup-fresh-boot.sh', 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'),
         ('pmos-self-post-fresh-boot.sh', 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh'),
         ('10-omnipha-self-stage.start', 'etc/local.d/10-omnipha-self-stage.start'))
with tempfile.TemporaryDirectory(prefix='chain-install-311.') as tmp:
    work = pathlib.Path(tmp)
    sources = work / 'carrier'
    sources.mkdir(mode=0o700)
    payloads = builder.runtime_scripts()
    mountinfo_path = work / 'mountinfo'
    mountinfo_path.write_text('17 35 0:31 / /run rw - tmpfs tmpfs rw\n')
    contract = sources / 'fixture-contract'
    contract.write_text('''root_contract_pinned_userdata() {
    [ "$1" = "$GUEST" ] || return 1
    ROOT_CONTRACT_OPTS=${fixture_root_opts:-$root_kind}
}
''')
    for name, target in specs:
        data = payloads[name]
        path = sources / name
        path.write_bytes(data)
        path.chmod(0o700 if name != 'pmos-self-post-fresh-boot.sh' else 0o600)
    guest = work / 'guest'
    guest.mkdir(mode=0o700)
    (guest / 'usr').mkdir(mode=0o755)
    (guest / 'etc').mkdir(mode=0o775)
    (guest / 'etc/local.d').mkdir(mode=0o755)
    contract_data = contract.read_text()
    contract.unlink()
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'persistent chain root is not pinned read-write userdata' in bad.stderr, bad.stderr
    contract.symlink_to(work / 'missing-contract')
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'persistent chain root is not pinned read-write userdata' in bad.stderr, bad.stderr
    contract.unlink()
    valid_contract = sources / 'valid-contract'
    valid_contract.write_text(contract_data)
    contract.symlink_to(valid_contract)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'persistent chain root is not pinned read-write userdata' in bad.stderr, bad.stderr
    contract.unlink()
    valid_contract.unlink()
    contract.write_text(contract_data)
    mountinfo_path.write_text(f'1 0 0:1 / {guest}/usr rw - ext4 fake rw\n')
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'nested mount in persistent chain parents' in bad.stderr, bad.stderr
    assert not (guest / 'usr/libexec').exists()
    mountinfo_path.write_text('17 35 0:31 / /run rw - tmpfs tmpfs rw\n')
    bad = run_installer(guest, sources, mountinfo_path, root_kind='ro,noload')
    assert bad.returncode != 0 and 'persistent chain root is not pinned read-write userdata' in bad.stderr, bad.stderr
    bad = run_installer(guest, sources, mountinfo_path, dev_spoof='dev')
    assert bad.returncode != 0 and 'unsafe persistent chain parent metadata' in bad.stderr, bad.stderr
    (guest / 'usr').chmod(0o777)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unsafe persistent chain parent metadata' in bad.stderr, bad.stderr
    (guest / 'usr').chmod(0o755)
    (guest / 'usr').chmod(0o775)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unsafe persistent chain parent metadata' in bad.stderr, bad.stderr
    (guest / 'usr').chmod(0o755)
    assert 'cannot publish chain file without replacement' in installer
    assert 'persistent chain staging path already exists' in installer
    assert 'unpinned carrier payload' in installer and 'untrusted persistent chain file' in installer
    assert installer.count("set -- $chain_spec") == 3 and builder.FRESH_RADIO_SHA[:8] in installer
    assert builder.GATED_POST_SHA in installer and builder.GATED_HOOK_SHA in installer
    staged = builder.current_scripts()['pmos-self-stage.sh'].decode()
    assert staged.index('pmos-session-stage.sh') < staged.index('chain_dir=/run/omnipha-self-stage') < \
        staged.index('cannot publish chain file without replacement') < \
        staged.index('pmos-radio-bringup prepare failed') < staged.index('PID 1 request already exists')
    for name, _target in specs:
        if name == 'pmos-self-post-fresh-boot.sh':
            (sources / name).chmod(0o700)
    legacy_target = guest / 'etc/local.d/10-omnipha-self-stage.start'
    legacy_target.write_bytes(legacy_hook)
    legacy_target.chmod(0o700)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    assert legacy_target.read_bytes() == legacy_hook
    assert not (guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh').exists()
    legacy_target.unlink()
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    assert (guest / 'etc').stat().st_mode & 0o777 == 0o775
    for _name, target in specs:
        path = guest / target
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_mode & 0o777 == 0o700 and path.stat().st_nlink == 1, target
        assert path.read_bytes() == payloads[_name], target
        assert not (guest / (target + '.omnipha-new')).exists(), target
    for _name, target in (('pmos-radio-bringup-fresh-boot.sh', 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'),
                          ('pmos-self-post-fresh-boot.sh', 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh'),
                          ('10-omnipha-self-stage.start', 'etc/local.d/10-omnipha-self-stage.start')):
        assert (guest / target).read_bytes() == payloads[_name]
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    for _name, target in specs:
        path = guest / target
        assert path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1
        assert path.read_bytes() == payloads[_name]
    victim = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
    bad_content = victim.read_bytes()
    victim.write_bytes(b'forged run-106 radio payload\n')
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    victim.write_bytes(bad_content)
    victim.chmod(0o755)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    victim.chmod(0o700)
    victim.unlink()
    victim.symlink_to('/bin/true')
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    victim.unlink()
    victim.write_bytes(bad_content)
    victim.chmod(0o700)
    hard_alias = work / 'chain-alias'
    os.link(victim, hard_alias)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    os.unlink(hard_alias)
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    for path in guest.rglob('*.omnipha-new'):
        path.unlink()
    sabotage = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh.omnipha-new'
    sabotage.write_bytes(b'partial\n')
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'persistent chain staging path already exists' in bad.stderr, bad.stderr
    sabotage.unlink()
    foreign_hook = guest / 'etc/local.d/99-foreign.start'
    foreign_hook.write_text('foreign\n')
    foreign_hook.chmod(0o700)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr, bad.stderr
    foreign_hook.unlink()
    foreign_hook.symlink_to('/etc/init.d/local')
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr, bad.stderr
    foreign_hook.unlink()
    for parent in ('usr', 'etc'):
        blocked = guest / parent
        blocked.chmod(0o777)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unsafe persistent chain parent metadata' in bad.stderr, bad.stderr
        blocked.chmod(0o755 if parent != 'etc' else 0o775)
    (guest / 'usr').chmod(0o775)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unsafe persistent chain parent metadata' in bad.stderr, bad.stderr
    (guest / 'usr').chmod(0o755)
    extra = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
    extra.unlink()
    extra_parent = extra.parent
    shutil.rmtree(extra_parent)
    symlink_parent = extra_parent
    symlink_parent.symlink_to(work)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and ('unsafe persistent chain' in bad.stderr or 'unpinned carrier' in bad.stderr), bad.stderr
    symlink_parent.unlink()
    symlink_parent.mkdir(mode=0o700)
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    sources.joinpath('pmos-self-post-fresh-boot.sh').write_bytes(b'unpinned carrier payload\n')
    sources.joinpath('pmos-self-post-fresh-boot.sh').chmod(0o700)
    target_post = guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh'
    target_post.unlink()
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
    assert not target_post.exists() or target_post.read_bytes() != b'unpinned carrier payload\n'
    sources.joinpath('pmos-self-post-fresh-boot.sh').write_bytes(payloads['pmos-self-post-fresh-boot.sh'])
    sources.joinpath('pmos-self-post-fresh-boot.sh').chmod(0o700)
    target_radio = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
    target_radio.unlink()
    bad = run_installer(guest, sources, mountinfo_path, race='file')
    assert bad.returncode != 0 and 'cannot publish chain file without replacement' in bad.stderr, bad.stderr
    assert target_radio.read_text() == 'raced target\n'
    target_radio.unlink()
    pathlib.Path(str(target_radio) + '.omnipha-new').unlink(missing_ok=True)
    bad = run_installer(guest, sources, mountinfo_path, race='dir')
    assert bad.returncode != 0 and 'cannot publish chain file without replacement' in bad.stderr, bad.stderr
    assert target_radio.is_dir()
    target_radio.rmdir()
    pathlib.Path(str(target_radio) + '.omnipha-new').unlink(missing_ok=True)
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    assert target_radio.read_bytes() == payloads['pmos-radio-bringup-fresh-boot.sh']
    route_cache = variant.route_cache
    candidate_post = candidate_scripts['pmos-self-post-fresh-boot.sh']
    candidate_hook = candidate_scripts['10-omnipha-self-stage.start']
    assert candidate_post != payloads['pmos-self-post-fresh-boot.sh']
    assert hashlib.sha256(candidate_post).hexdigest() == route_cache.POST_SHA
    assert hashlib.sha256(candidate_hook).hexdigest() == route_cache.HOOK_SHA
    for name in ('pmos-session-stage.sh', 'pmos-self-stage.sh'):
        assert candidate_scripts[name] != builder.runtime_scripts()[name]
        subprocess.run(['sh', '-n', '/dev/stdin'], check=True,
                       input=candidate_scripts[name].decode(), text=True)
    sources.joinpath('pmos-self-post-fresh-boot.sh').write_bytes(candidate_post)
    sources.joinpath('pmos-self-post-fresh-boot.sh').chmod(0o700)
    sources.joinpath('10-omnipha-self-stage.start').write_bytes(candidate_hook)
    sources.joinpath('10-omnipha-self-stage.start').chmod(0o700)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
    assert (guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh').read_bytes() == \
        payloads['pmos-self-post-fresh-boot.sh']
    assert (guest / 'etc/local.d/10-omnipha-self-stage.start').read_bytes() == \
        payloads['10-omnipha-self-stage.start']
    sources.joinpath('pmos-self-post-fresh-boot.sh').write_bytes(payloads['pmos-self-post-fresh-boot.sh'])
    sources.joinpath('pmos-self-post-fresh-boot.sh').chmod(0o700)
    sources.joinpath('10-omnipha-self-stage.start').write_bytes(payloads['10-omnipha-self-stage.start'])
    sources.joinpath('10-omnipha-self-stage.start').chmod(0o700)
    post_target = guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh'
    post_target.write_bytes(candidate_post)
    post_target.chmod(0o700)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    post_target.write_bytes(payloads['pmos-self-post-fresh-boot.sh'])
    post_target.chmod(0o700)
    hook_target = guest / 'etc/local.d/10-omnipha-self-stage.start'
    hook_target.write_bytes(candidate_hook)
    hook_target.chmod(0o700)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    hook_target.write_bytes(payloads['10-omnipha-self-stage.start'])
    hook_target.chmod(0o700)
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    canonical_test_installer = test_installer
    variant_installer = variant.builder.persistent_installer().decode()
    assert variant_installer in candidate_scripts['pmos-self-stage.sh'].decode()
    candidate_test_installer = 'set -eu\n' + variant_installer.replace(
        'chain_dir=/run/omnipha-self-stage\n', 'chain_dir="$sources"\n', 1).replace(
        '/run/pmos-root-contract.sh', '"$sources/fixture-contract"')
    test_installer = candidate_test_installer
    for name in ('pmos-self-post-fresh-boot.sh', '10-omnipha-self-stage.start'):
        sources.joinpath(name).write_bytes(candidate_scripts[name])
        sources.joinpath(name).chmod(0o700)
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
    assert post_target.read_bytes() == payloads['pmos-self-post-fresh-boot.sh']
    assert hook_target.read_bytes() == payloads['10-omnipha-self-stage.start']
    def file_state(path):
        data = path.read_bytes()
        metadata = path.lstat()
        return data, (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid, metadata.st_gid,
                      metadata.st_nlink, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)
    post_target.unlink()
    hook_target.unlink()
    assert target_radio.read_bytes() == payloads['pmos-radio-bringup-fresh-boot.sh']
    assert target_radio.is_file() and not target_radio.is_symlink()
    radio_metadata = target_radio.stat()
    assert radio_metadata.st_mode & 0o777 == 0o700 and radio_metadata.st_nlink == 1
    radio_state = file_state(target_radio)
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    assert post_target.read_bytes() == candidate_post and hook_target.read_bytes() == candidate_hook
    assert target_radio.read_bytes() == payloads['pmos-radio-bringup-fresh-boot.sh']
    assert file_state(target_radio) == radio_state
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    assert file_state(target_radio) == radio_state
    sources.joinpath('pmos-self-post-fresh-boot.sh').write_bytes(payloads['pmos-self-post-fresh-boot.sh'])
    bad = run_installer(guest, sources, mountinfo_path)
    assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
    assert post_target.read_bytes() == candidate_post and hook_target.read_bytes() == candidate_hook
    assert file_state(target_radio) == radio_state

    for protected_name, protected_target in specs:
        test_installer = canonical_test_installer
        for name, _ in specs:
            sources.joinpath(name).write_bytes(payloads[name])
            sources.joinpath(name).chmod(0o700)
            (guest / _).write_bytes(payloads[name])
            (guest / _).chmod(0o700)
        target_path = guest / protected_target
        original_data = target_path.read_bytes()
        target_path.write_bytes(b'mismatched protected content\n')
        target_path.chmod(0o700)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
        target_path.write_bytes(original_data)
        target_path.chmod(0o700)
        bad_source = sources / protected_name
        bad_source.write_bytes(b'mismatched carrier payload\n')
        bad_source.chmod(0o700)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
        bad_source.write_bytes(payloads[protected_name])
        bad_source.chmod(0o700)
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr

    test_installer = canonical_test_installer
    for name, _ in specs:
        sources.joinpath(name).write_bytes(payloads[name])
        sources.joinpath(name).chmod(0o700)
        (guest / _).write_bytes(payloads[name])
        (guest / _).chmod(0o700)
    for auth_name, auth_target, auth_payload in (
            ('pmos-self-post-fresh-boot.sh', 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh', candidate_post),
            ('10-omnipha-self-stage.start', 'etc/local.d/10-omnipha-self-stage.start', candidate_hook)):
        (guest / auth_target).write_bytes(auth_payload)
        (guest / auth_target).chmod(0o700)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
        (guest / auth_target).write_bytes(payloads[auth_name])
        (guest / auth_target).chmod(0o700)
    for auth_name, auth_target, auth_payload in (
            ('pmos-self-post-fresh-boot.sh', 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh', candidate_post),
            ('10-omnipha-self-stage.start', 'etc/local.d/10-omnipha-self-stage.start', candidate_hook)):
        (guest / auth_target).unlink()
        sources.joinpath(auth_name).write_bytes(auth_payload)
        sources.joinpath(auth_name).chmod(0o700)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
        assert not (guest / auth_target).exists()
        sources.joinpath(auth_name).write_bytes(payloads[auth_name])
        sources.joinpath(auth_name).chmod(0o700)
        (guest / auth_target).write_bytes(payloads[auth_name])
        (guest / auth_target).chmod(0o700)

    unrelated_file = guest / 'etc/unrelated-unpinned.conf'
    unrelated_bytes = b'unrelated config data preserved across installer passes\n'
    unrelated_file.write_bytes(unrelated_bytes)
    unrelated_file.chmod(0o644)
    protected_state_before = {spec[1]: file_state(guest / spec[1]) for spec in specs}
    unrelated_state_before = file_state(unrelated_file)
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    assert unrelated_file.read_bytes() == unrelated_bytes
    assert file_state(unrelated_file) == unrelated_state_before
    for _, spec_target in specs:
        assert (guest / spec_target).read_bytes() == payloads[_]
        assert file_state(guest / spec_target) == protected_state_before[spec_target]
    ok = run_installer(guest, sources, mountinfo_path)
    assert ok.returncode == 0, ok.stderr
    assert unrelated_file.read_bytes() == unrelated_bytes
    assert file_state(unrelated_file) == unrelated_state_before
    for _, spec_target in specs:
        assert (guest / spec_target).read_bytes() == payloads[_]
        assert file_state(guest / spec_target) == protected_state_before[spec_target]
    unrelated_file.unlink()
    radio_state = file_state(target_radio)

    def stage_block(stage_text):
        first = stage_text.index('for level in sysinit boot default nonetwork shutdown; do\n')
        hooks = stage_text.index('for hook in "$PMOS_ROOT"/etc/local.d/*.start', first)
        deferral = stage_text.index('if [ "${PMOS_ROOT_KIND:-tmpfs}" = ext4 ]; then\n\tfor service in wpa_supplicant networking; do\n', hooks)
        return stage_text[first:stage_text.index('if [ ! -e "$PMOS_ROOT/sbin/init" ]', deferral)]
    def run_stage_block(block, bb=busybox):
        return subprocess.run([bb, 'sh', '-c', setup + block, 'fixture', bb, str(guest)],
                              capture_output=True, text=True, check=False)
    for level in ('sysinit', 'boot', 'default', 'nonetwork', 'shutdown'):
        (guest / 'etc/runlevels' / level).mkdir(parents=True)
    (guest / 'etc/init.d').mkdir()
    (guest / 'etc/init.d/local').write_text('local\n')
    (guest / 'etc/init.d/local').chmod(0o755)
    default = guest / 'etc/runlevels/default'
    local_link = default / 'local'
    radio_links = tuple(default / name for name in ('wpa_supplicant', 'networking'))
    canonical_hook = payloads['10-omnipha-self-stage.start']
    for label, stage_text, own_hook, foreign_hook in (
            ('canonical', runtime['pmos-session-stage.sh'].decode(), canonical_hook, candidate_hook),
            ('route-cache', candidate_scripts['pmos-session-stage.sh'].decode(), candidate_hook, canonical_hook)):
        stage_fragment = stage_block(stage_text)
        for stage_hook, expected_ok in ((foreign_hook, False), (own_hook, True)):
            hook_target.write_bytes(stage_hook)
            hook_target.chmod(0o700)
            local_link.unlink(missing_ok=True)
            for path in radio_links:
                path.unlink(missing_ok=True)
                path.symlink_to('/etc/init.d/' + path.name)
            before = tuple(file_state(path) for path in (target_radio, post_target, hook_target))
            result = run_stage_block(stage_fragment)
            if expected_ok:
                assert result.returncode == 0, (label, result.stderr)
                assert local_link.is_symlink() and os.readlink(local_link) == '/etc/init.d/local', label
                assert all(not path.exists() and not path.is_symlink() for path in radio_links), label
            else:
                assert result.returncode != 0 and 'unexpected local startup hook' in result.stderr, (label, result.stderr)
                assert not local_link.exists() and not local_link.is_symlink(), label
                assert all(path.is_symlink() and os.readlink(path) == '/etc/init.d/' + path.name
                           for path in radio_links), label
            assert tuple(file_state(path) for path in (target_radio, post_target, hook_target)) == before, label
            assert file_state(target_radio) == radio_state, label
    for label, stage_text, hook_sha in (
            ('canonical', runtime['pmos-session-stage.sh'].decode(), builder.GATED_HOOK_SHA),
            ('route-cache', candidate_scripts['pmos-session-stage.sh'].decode(), variant.route_cache.HOOK_SHA)):
        hook_index = stage_text.index('for hook in "$PMOS_ROOT"/etc/local.d/*.start')
        pin_index = stage_text.index(hook_sha, hook_index)
        assert stage_text.count(hook_sha) == 1
        assert pin_index < stage_text.index('unexpected local startup hook', hook_index)
        other_sha = variant.route_cache.HOOK_SHA if label == 'canonical' else builder.GATED_HOOK_SHA
        assert stage_text[stage_text.index('for hook in "$PMOS_ROOT"/etc/local.d/*.start'):
                          stage_text.index('cannot enable RAM-only local service')].count(other_sha) == 0
    unpinned_path = here / 'build-init-boot-mb003-unpinned.py'
    unpinned_present = unpinned_path.is_file()
    if unpinned_present:
        unpinned = load('mb003_unpinned', 'build-init-boot-mb003-unpinned.py')
        assert unpinned.canonical is not builder and unpinned.builder is not builder
        assert unpinned.canonical.FRESH_RADIO_SHA == builder.FRESH_RADIO_SHA
        assert unpinned.BAD_RADIO == 'd7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3'
        unpinned_scripts = unpinned.runtime_scripts()
        self_stage = unpinned_scripts['pmos-self-stage.sh'].decode()
        start = self_stage.index('chain_dir=/run/omnipha-self-stage\n')
        end = self_stage.index('done\n', self_stage.index("persistent chain changed after installation", start)) + len('done\n')
        unpinned_installer = self_stage[start:end]
        assert 'chain_metadata()' in unpinned_installer
        assert unpinned_installer.count(unpinned.BAD_RADIO) == 1 and 'refused persistent chain file' in unpinned_installer
        assert unpinned.BAD_RADIO not in builder.persistent_installer().decode()
        assert builder.FRESH_RADIO_SHA in unpinned_installer
        assert unpinned_installer.count(builder.GATED_POST_SHA) == 1 and unpinned_installer.count(builder.GATED_HOOK_SHA) == 1
        assert '.omnipha-legacy' in unpinned_installer and '.start.omnipha-legacy' not in unpinned_installer
        assert hashlib.sha256(unpinned_scripts['pmos-self-post-fresh-boot.sh']).hexdigest() in unpinned_installer
        assert hashlib.sha256(unpinned_scripts['10-omnipha-self-stage.start']).hexdigest() in unpinned_installer
        unpinned_stage = unpinned_scripts['pmos-session-stage.sh'].decode()
        assert unpinned_stage != runtime['pmos-session-stage.sh'].decode()
        assert builder.GATED_HOOK_SHA.encode() not in unpinned_scripts['pmos-session-stage.sh']
        unpinned_test_installer = 'set -eu\n' + unpinned_installer.replace(
            'chain_dir=/run/omnipha-self-stage\n', 'chain_dir="$sources"\n', 1).replace(
            '/run/pmos-root-contract.sh', '"$sources/fixture-contract"')
        assert unpinned_test_installer.count('/run/pmos-root-contract.sh') == 0
        root_contract_text = (here / 'pmos-root-contract.sh').read_bytes()
        assert root_contract_text == runtime['pmos-root-contract.sh'] == unpinned_scripts['pmos-root-contract.sh']
        for snippet in (b'root_contract_pinned_userdata()', b'root_contract_switched_root()',
                        b'root_contract_promote()', b'root_contract_stage_root()'):
            assert root_contract_text.count(snippet) == 1
        test_installer = unpinned_test_installer
        def reset_unpinned():
            for name, target in specs:
                sources.joinpath(name).write_bytes(unpinned_scripts[name])
                sources.joinpath(name).chmod(0o700)
                path = guest / target
                for suffix in ('', '.omnipha-new', '.omnipha-legacy'):
                    candidate = path.with_name(path.name + suffix)
                    if candidate.is_dir() and not candidate.is_symlink():
                        candidate.rmdir()
                    else:
                        candidate.unlink(missing_ok=True)
                path.write_bytes(unpinned_scripts[name])
                path.chmod(0o700)
        reset_unpinned()
        unrelated_file.write_bytes(unrelated_bytes)
        unrelated_file.chmod(0o644)
        edits = {
            'pmos-radio-bringup-fresh-boot.sh': b': host_only_radio_edit\n',
            'pmos-self-post-fresh-boot.sh': b': host_only_post_edit\n',
            '10-omnipha-self-stage.start': b': host_only_hook_edit\n',
        }
        for edited_name, _edited_target in specs:
            reset_unpinned()
            edited_path = guest / _edited_target
            assert unpinned_scripts[edited_name].endswith(b'\n')
            edited_path.write_bytes(unpinned_scripts[edited_name] + edits[edited_name])
            edited_path.chmod(0o700)
            assert edited_path.read_bytes().count(edits[edited_name]) == 1
            before_guest = {target: file_state(guest / target) for _, target in specs}
            before_sources = {name: file_state(sources / name) for name, _ in specs}
            for _pass in range(2):
                ok = run_installer(guest, sources, mountinfo_path)
                assert ok.returncode == 0, (edited_name, _pass, ok.stderr)
                assert {target: file_state(guest / target) for _, target in specs} == before_guest, edited_name
                assert {name: file_state(sources / name) for name, _ in specs} == before_sources, edited_name
            for name, target in specs:
                path = guest / target
                metadata = path.lstat()
                assert path.is_file() and not path.is_symlink() and metadata.st_nlink == 1
                assert metadata.st_mode & 0o777 == 0o700 and metadata.st_uid == os.getuid(), target
                if name == edited_name:
                    assert path.read_bytes() == unpinned_scripts[name] + edits[name]
                else:
                    assert path.read_bytes() == unpinned_scripts[name], (edited_name, name)
                assert not (guest / (target + '.omnipha-new')).exists()
        reset_unpinned()
        radio_target = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
        radio_target.write_bytes(unpinned_scripts['pmos-radio-bringup-fresh-boot.sh'] + edits['pmos-radio-bringup-fresh-boot.sh'])
        radio_target.chmod(0o700)
        edited_radio_state = file_state(radio_target)
        bad_carrier = sources / 'pmos-radio-bringup-fresh-boot.sh'
        bad_carrier.write_bytes(radio_target.read_bytes())
        bad_carrier.chmod(0o700)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
        assert file_state(radio_target) == edited_radio_state
        bad_carrier.write_bytes(b'denylisted carrier stand-in\n')
        bad_carrier.chmod(0o700)
        assert hashlib.sha256(bad_carrier.read_bytes()).hexdigest() != unpinned.BAD_RADIO
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, bad.stderr
        assert file_state(radio_target) == edited_radio_state
        bad_carrier.write_bytes(unpinned_scripts['pmos-radio-bringup-fresh-boot.sh'])
        bad_carrier.chmod(0o700)
        canonical_scripts = unpinned.canonical.runtime_scripts()
        assert all(canonical_scripts[name] == payloads[name] for name, _ in specs)
        assert unpinned_scripts['pmos-radio-bringup-fresh-boot.sh'] == canonical_scripts['pmos-radio-bringup-fresh-boot.sh']
        reset_unpinned()
        for name, target in specs:
            path = guest / target
            path.write_bytes(unpinned_scripts[name])
            path.chmod(0o700)
        state = {target: file_state(guest / target) for _, target in specs}
        for pass_number in range(2):
            ok = run_installer(guest, sources, mountinfo_path)
            assert ok.returncode == 0, ok.stderr
            assert {target: file_state(guest / target) for _, target in specs} == state
        reset_unpinned()
        for _name, target in specs:
            path = guest / target
            assert hashlib.sha256(path.read_bytes()).hexdigest() != unpinned.BAD_RADIO
            before_files = {item: file_state(guest / item) for _, item in specs}
            carrier_before = {name: file_state(sources / name) for name, _ in specs}
            trace = work / 'sha-trace'
            trace.unlink(missing_ok=True)
            bad = run_installer(guest, sources, mountinfo_path, sha=('digest', path, unpinned.BAD_RADIO, trace))
            assert bad.returncode != 0 and 'refused persistent chain file' in bad.stderr, (target, bad.stderr)
            assert trace.read_text().splitlines() == [str(path)]
            assert {item: file_state(guest / item) for _, item in specs} == before_files
            assert {name: file_state(sources / name) for name, _ in specs} == carrier_before
            assert not any(guest.rglob('*.omnipha-new'))
        trace.unlink()
        reset_unpinned()
        foreign_hook = guest / 'etc/local.d/99-foreign.start'
        foreign_hook.write_text('foreign\n')
        foreign_hook.chmod(0o700)
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr, bad.stderr
        foreign_hook.unlink()
        foreign_hook.symlink_to('/etc/init.d/local')
        bad = run_installer(guest, sources, mountinfo_path)
        assert bad.returncode != 0 and 'unexpected local startup hook' in bad.stderr, bad.stderr
        foreign_hook.unlink()
        for label, mutate, undo in (
                ('hardlink', lambda p: os.link(p, work / 'unpinned-alias'), lambda p: os.unlink(work / 'unpinned-alias')),
                ('mode', lambda p: p.chmod(0o755), lambda p: p.chmod(0o700))):
            for _name, target in specs:
                path = guest / target
                state = file_state(path)
                mutate(path)
                bad = run_installer(guest, sources, mountinfo_path)
                assert bad.returncode != 0 and bad.stderr.count('untrusted persistent chain file') == 1, (label, target, bad.stderr)
                undo(path)
                assert file_state(path)[0] == state[0]
        for _name, target in specs:
            path = guest / target
            data = path.read_bytes()
            path.unlink()
            path.symlink_to('/bin/true')
            bad = run_installer(guest, sources, mountinfo_path)
            assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, (target, bad.stderr)
            path.unlink()
            path.write_bytes(data)
            path.chmod(0o700)
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        for name, target in specs:
            path = guest / target
            before_files = {item: file_state(guest / item) for _, item in specs}
            trace.unlink(missing_ok=True)
            for mode, value in (('fail', ''), ('fail-with-output', unpinned.BAD_RADIO),
                                ('empty', ''), ('garbage', '')):
                trace.unlink(missing_ok=True)
                result = run_installer(guest, sources, mountinfo_path, sha=(mode, path, value, trace))
                assert result.returncode != 0 and 'untrusted persistent chain file' in result.stderr, (mode, target, result.stderr)
                assert trace.read_text().splitlines() == [str(path)], (mode, target)
                assert {item: file_state(guest / item) for _, item in specs} == before_files
            trace.unlink()
            bad = run_installer(guest, sources, mountinfo_path,
                                sha=('digest', path, '0' * 64, trace))
            assert bad.returncode == 0, (target, bad.stderr)
            assert {item: file_state(guest / item) for _, item in specs} == before_files
        reset_unpinned()
        for name, target in specs:
            path = guest / target
            path.unlink()
            before_files = {item: file_state(guest / item) for _, item in specs if item != target}
            trace.unlink(missing_ok=True)
            bad = run_installer(guest, sources, mountinfo_path,
                                sha=('digest', sources / name, unpinned.BAD_RADIO, trace))
            assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, (name, bad.stderr)
            assert trace.read_text().splitlines() == [str(sources / name)]
            assert not path.exists() and not path.is_symlink()
            assert {item: file_state(guest / item) for _, item in specs if item != target} == before_files
            path.write_bytes(unpinned_scripts[name])
            path.chmod(0o700)
            trace.unlink()
        test_installer = canonical_test_installer
        reset_unpinned()
        for name, target in specs:
            path = guest / target
            path.write_bytes(payloads[name])
            path.chmod(0o700)
        canonical_before = {target: file_state(guest / target) for _, target in specs}
        bad = run_installer(guest, sources, mountinfo_path,
                            sha=('digest', guest / specs[0][1], unpinned.BAD_RADIO, trace))
        assert bad.returncode != 0 and 'untrusted persistent chain file' in bad.stderr, bad.stderr
        assert 'refused persistent chain file' not in bad.stderr
        assert {target: file_state(guest / target) for _, target in specs} == canonical_before
        trace.unlink(missing_ok=True)
        test_installer = unpinned_test_installer
        reset_unpinned()
        legacy_hook_path = guest / 'etc/local.d/10-omnipha-self-stage.start'
        legacy_hook_path.write_bytes(canonical_scripts['10-omnipha-self-stage.start'])
        legacy_hook_path.chmod(0o700)
        legacy_post_path = guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh'
        legacy_post_path.write_bytes(canonical_scripts['pmos-self-post-fresh-boot.sh'])
        legacy_post_path.chmod(0o700)
        edited_radio_path = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
        edited_radio_bytes = unpinned_scripts['pmos-radio-bringup-fresh-boot.sh'] + edits['pmos-radio-bringup-fresh-boot.sh']
        edited_radio_path.write_bytes(edited_radio_bytes)
        edited_radio_path.chmod(0o700)
        legacy_states = {legacy_hook_path: file_state(legacy_hook_path),
                         legacy_post_path: file_state(legacy_post_path)}
        hook_backup = guest / 'etc/local.d/10-omnipha-self-stage.start.omnipha-legacy'
        post_backup = guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh.omnipha-legacy'
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        assert file_state(edited_radio_path)[0] == edited_radio_bytes
        assert legacy_hook_path.read_bytes() == unpinned_scripts['10-omnipha-self-stage.start']
        assert legacy_post_path.read_bytes() == unpinned_scripts['pmos-self-post-fresh-boot.sh']
        assert file_state(edited_radio_path)[0] == edited_radio_bytes
        assert hook_backup.read_bytes() == canonical_scripts['10-omnipha-self-stage.start']
        assert post_backup.read_bytes() == canonical_scripts['pmos-self-post-fresh-boot.sh']
        assert tuple(file_state(path)[0] for path in (hook_backup, post_backup)) == \
            tuple(state[0] for state in (legacy_states[legacy_hook_path], legacy_states[legacy_post_path]))
        assert hook_backup.stat().st_mode & 0o777 == 0o700 and post_backup.stat().st_mode & 0o777 == 0o700
        assert legacy_hook_path.stat().st_nlink == 1 and legacy_post_path.stat().st_nlink == 1
        assert hook_backup.stat().st_nlink == 1 and post_backup.stat().st_nlink == 1
        assert not (guest / 'etc/local.d/10-omnipha-self-stage.start.omnipha-new').exists()
        assert not (guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh.omnipha-new').exists()
        assert hook_backup.stat().st_ino == legacy_states[legacy_hook_path][1][1]
        assert post_backup.stat().st_ino == legacy_states[legacy_post_path][1][1]
        migrated = {legacy_hook_path: file_state(legacy_hook_path),
                    legacy_post_path: file_state(legacy_post_path),
                    edited_radio_path: file_state(edited_radio_path)}
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        assert {legacy_hook_path: file_state(legacy_hook_path),
                legacy_post_path: file_state(legacy_post_path),
                edited_radio_path: file_state(edited_radio_path)} == migrated
        assert hook_backup.read_bytes() == canonical_scripts['10-omnipha-self-stage.start']
        assert post_backup.read_bytes() == canonical_scripts['pmos-self-post-fresh-boot.sh']
        modified_post = unpinned_scripts['pmos-self-post-fresh-boot.sh'] + edits['pmos-self-post-fresh-boot.sh']
        modified_hook = unpinned_scripts['10-omnipha-self-stage.start'] + edits['10-omnipha-self-stage.start']
        for modified_name, modified_target, modified_digest in (
                ('pmos-self-post-fresh-boot.sh', 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh', modified_post),
                ('10-omnipha-self-stage.start', 'etc/local.d/10-omnipha-self-stage.start', modified_hook)):
            reset_unpinned()
            modified_path = guest / modified_target
            modified_path.write_bytes(modified_digest)
            modified_path.chmod(0o700)
            assert hashlib.sha256(modified_path.read_bytes()).hexdigest() != unpinned.BAD_RADIO
            before_files = {item: file_state(guest / item) for _, item in specs}
            for pass_number in range(2):
                ok = run_installer(guest, sources, mountinfo_path)
                assert ok.returncode == 0, (modified_name, ok.stderr)
                assert {item: file_state(guest / item) for _, item in specs} == before_files
            assert modified_path.read_bytes() == modified_digest
            assert not (guest / (modified_target + '.omnipha-legacy')).exists()
        edited_radio_target = guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
        reset_unpinned()
        edited_radio_target.write_bytes(edited_radio_bytes)
        edited_radio_target.chmod(0o700)
        assert hashlib.sha256(edited_radio_target.read_bytes()).hexdigest() != unpinned.BAD_RADIO
        edited_radio_state = file_state(edited_radio_target)
        for pass_number in range(2):
            ok = run_installer(guest, sources, mountinfo_path)
            assert ok.returncode == 0, ok.stderr
            assert file_state(edited_radio_target) == edited_radio_state
        assert edited_radio_target.read_bytes() == edited_radio_bytes
        assert not (guest / 'usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh.omnipha-legacy').exists()
        reset_unpinned()
        edited_radio_target.write_bytes(edited_radio_bytes)
        edited_radio_target.chmod(0o700)
        legacy_hook_path.write_bytes(canonical_scripts['10-omnipha-self-stage.start'])
        legacy_hook_path.chmod(0o700)
        legacy_post_path.write_bytes(canonical_scripts['pmos-self-post-fresh-boot.sh'])
        legacy_post_path.chmod(0o700)
        partial_states = {legacy_hook_path: file_state(legacy_hook_path),
                          legacy_post_path: file_state(legacy_post_path),
                          edited_radio_target: file_state(edited_radio_target)}
        for label, mutate, undo in (
                ('stale', lambda p: p.with_name(p.name + '.omnipha-legacy').write_bytes(b'stale\n'), lambda p: p.with_name(p.name + '.omnipha-legacy').unlink()),
                ('backup-dir', lambda p: p.with_name(p.name + '.omnipha-legacy').mkdir(mode=0o700), lambda p: p.with_name(p.name + '.omnipha-legacy').rmdir())):
            for target_name, target_path in (('pmos-self-post-fresh-boot.sh', legacy_post_path),
                                             ('10-omnipha-self-stage.start', legacy_hook_path)):
                mutate(target_path)
                bad = run_installer(guest, sources, mountinfo_path)
                assert bad.returncode != 0 and 'persistent chain legacy backup' in bad.stderr, (label, target_name, bad.stderr)
                assert target_path.read_bytes() == partial_states[target_path][0]
                undo(target_path)
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        assert hook_backup.read_bytes() == canonical_scripts['10-omnipha-self-stage.start']
        assert post_backup.read_bytes() == canonical_scripts['pmos-self-post-fresh-boot.sh']
        assert file_state(edited_radio_target)[0] == edited_radio_bytes
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        for collision in ('file', 'dir'):
            sabotage = guest / 'usr/libexec/omnipha/pmos-self-post-fresh-boot.sh.omnipha-new'
            reset_unpinned()
            legacy_hook_path.write_bytes(canonical_scripts['10-omnipha-self-stage.start'])
            legacy_hook_path.chmod(0o700)
            legacy_post_path.write_bytes(canonical_scripts['pmos-self-post-fresh-boot.sh'])
            legacy_post_path.chmod(0o700)
            post_state = file_state(legacy_post_path)
            hook_state = file_state(legacy_hook_path)
            if collision == 'file':
                sabotage.write_bytes(b'spoofed staging\n')
                sabotage.chmod(0o600)
            else:
                for victim in guest.rglob('*.omnipha-new'):
                    if victim.is_dir():
                        victim.rmdir()
                    else:
                        victim.unlink()
                sabotage.mkdir(mode=0o700)
            bad = run_installer(guest, sources, mountinfo_path)
            assert bad.returncode != 0 and 'persistent chain staging path already exists' in bad.stderr, (collision, bad.stderr)
            assert file_state(legacy_post_path) == post_state
            assert file_state(legacy_hook_path) == hook_state
            assert not post_backup.exists() and not hook_backup.exists()
        reset_unpinned()
        legacy_hook_path.write_bytes(canonical_scripts['10-omnipha-self-stage.start'])
        legacy_hook_path.chmod(0o700)
        legacy_post_path.write_bytes(canonical_scripts['pmos-self-post-fresh-boot.sh'])
        legacy_post_path.chmod(0o700)
        edited_radio_target.write_bytes(edited_radio_bytes)
        edited_radio_target.chmod(0o700)
        pristine_before = {legacy_hook_path: file_state(legacy_hook_path),
                           legacy_post_path: file_state(legacy_post_path),
                           edited_radio_target: file_state(edited_radio_target)}
        for race, expected in (
                ('backup-fail', 'cannot create persistent chain legacy backup'),
                ('backup-exists', 'cannot create persistent chain legacy backup'),
                ('target-edit', 'persistent chain legacy backup changed'),
                ('replace-fail', 'cannot replace legacy chain file')):
            for path in (legacy_hook_path, legacy_post_path):
                path.write_bytes(pristine_before[path][0])
                path.chmod(0o700)
                path.with_name(path.name + '.omnipha-legacy').unlink(missing_ok=True)
                path.with_name(path.name + '.omnipha-new').unlink(missing_ok=True)
            edited_radio_target.write_bytes(edited_radio_bytes)
            edited_radio_target.chmod(0o700)
            bad = run_installer(guest, sources, mountinfo_path, race=race)
            assert bad.returncode != 0 and expected in bad.stderr, (race, bad.stderr)
            assert file_state(edited_radio_target)[0] == edited_radio_bytes
            for path in (legacy_hook_path, legacy_post_path):
                backup = path.with_name(path.name + '.omnipha-legacy')
                staged = path.with_name(path.name + '.omnipha-new')
                if race in ('backup-fail', 'backup-exists'):
                    assert path.read_bytes() == pristine_before[path][0], race
                    assert not backup.exists() or backup.read_bytes() != pristine_before[path][0] or race == 'backup-exists'
                elif race == 'target-edit':
                    assert not backup.exists() or backup.read_bytes() != pristine_before[path][0]
                else:
                    assert path.read_bytes() == pristine_before[path][0]
                    if staged.exists():
                        assert backup.is_file() and backup.read_bytes() == pristine_before[path][0], race
                        assert backup.stat().st_ino == path.stat().st_ino and path.stat().st_nlink == 2
                        assert staged.read_bytes() == unpinned_scripts[
                            'pmos-self-post-fresh-boot.sh' if path is legacy_post_path else '10-omnipha-self-stage.start']
                        again = run_installer(guest, sources, mountinfo_path)
                        assert again.returncode != 0 and (
                            'persistent chain staging path already exists' in again.stderr or
                            'unsafe persistent chain legacy backup' in again.stderr or
                            'partial persistent chain migration' in again.stderr), (race, again.stderr)
                        assert path.read_bytes() == pristine_before[path][0] and backup.read_bytes() == pristine_before[path][0]
                    else:
                        assert not backup.exists(), race
                staged.unlink(missing_ok=True)
                backup.unlink(missing_ok=True)
        reset_unpinned()
        legacy_hook_path.write_bytes(canonical_scripts['10-omnipha-self-stage.start'])
        legacy_hook_path.chmod(0o700)
        legacy_post_path.write_bytes(canonical_scripts['pmos-self-post-fresh-boot.sh'])
        legacy_post_path.chmod(0o700)
        edited_radio_target.write_bytes(edited_radio_bytes)
        edited_radio_target.chmod(0o700)
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        assert legacy_hook_path.read_bytes() == unpinned_scripts['10-omnipha-self-stage.start']
        assert legacy_post_path.read_bytes() == unpinned_scripts['pmos-self-post-fresh-boot.sh']
        assert hook_backup.read_bytes() == canonical_scripts['10-omnipha-self-stage.start']
        assert post_backup.read_bytes() == canonical_scripts['pmos-self-post-fresh-boot.sh']
        assert file_state(edited_radio_target)[0] == edited_radio_bytes
        assert hook_backup.stat().st_ino != legacy_hook_path.stat().st_ino
        assert post_backup.stat().st_ino != legacy_post_path.stat().st_ino
        recovered_hook = hook_backup.read_bytes()
        recovered_post = post_backup.read_bytes()
        legacy_hook_path.write_bytes(recovered_hook)
        legacy_hook_path.chmod(0o700)
        legacy_post_path.write_bytes(recovered_post)
        legacy_post_path.chmod(0o700)
        hook_backup.unlink()
        post_backup.unlink()
        assert legacy_hook_path.read_bytes() == canonical_scripts['10-omnipha-self-stage.start']
        assert legacy_post_path.read_bytes() == canonical_scripts['pmos-self-post-fresh-boot.sh']
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        assert legacy_hook_path.read_bytes() == unpinned_scripts['10-omnipha-self-stage.start']
        assert legacy_post_path.read_bytes() == unpinned_scripts['pmos-self-post-fresh-boot.sh']
        assert hook_backup.read_bytes() == recovered_hook and post_backup.read_bytes() == recovered_post
        for name, target in specs:
            path = guest / target
            before = file_state(path)
            bad = run_installer(guest, sources, mountinfo_path, sha=('digest', path, unpinned.BAD_RADIO, work / 'sha-trace'))
            assert bad.returncode != 0 and 'refused persistent chain file' in bad.stderr, (name, bad.stderr)
            assert file_state(path)[0] == before[0]
            (work / 'sha-trace').unlink(missing_ok=True)
        reset_unpinned()
        for name, target in specs:
            path = sources / name
            path.write_bytes(b'carrier-mismatch\n')
            path.chmod(0o700)
            bad = run_installer(guest, sources, mountinfo_path)
            assert bad.returncode != 0 and 'unpinned carrier payload' in bad.stderr, (name, bad.stderr)
            path.write_bytes(unpinned_scripts[name])
            path.chmod(0o700)
        ok = run_installer(guest, sources, mountinfo_path)
        assert ok.returncode == 0, ok.stderr
        edited_hook = unpinned_scripts['10-omnipha-self-stage.start'] + edits['10-omnipha-self-stage.start']
        canonical_fragment = stage_block(runtime['pmos-session-stage.sh'].decode())
        candidate_fragment = stage_block(unpinned_stage)
        for label, fragment, accepted in (
                ('canonical', canonical_fragment, False),
                ('unpinned-candidate', candidate_fragment, True)):
            hook_target.write_bytes(edited_hook)
            hook_target.chmod(0o700)
            local_link.unlink(missing_ok=True)
            for path in radio_links:
                path.unlink(missing_ok=True)
                path.symlink_to('/etc/init.d/' + path.name)
            before = file_state(hook_target)
            result = run_stage_block(fragment)
            if accepted:
                assert result.returncode == 0, (label, result.stderr)
                assert local_link.is_symlink() and not any(path.exists() for path in radio_links), label
            else:
                assert result.returncode != 0 and 'unexpected local startup hook' in result.stderr, (label, result.stderr)
                assert not local_link.exists() and all(path.is_symlink() for path in radio_links), label
            assert file_state(hook_target) == before, label
        hook_target.write_bytes(payloads['10-omnipha-self-stage.start'])
        hook_target.chmod(0o700)
        unrelated_file.unlink()
        print('pass: pristine canonical legacy hook and post migrate to unpinned defaults with same-inode .omnipha-legacy backups; edited radio retained; repeat boots are no-ops')
        print('pass: modified hook and post stay byte-identical without backup; backup collisions, stale or directory backups, staging collisions and races (backup failure, target edit, replace failure) fail closed')
        print('pass: BAD digest, failed, empty, malformed and fail-with-output sha256sum are refused for radio, post and hook; carrier mismatches refused')
        print('pass: unpinned edited radio/post/hook preserved one at a time across installer passes')
        print('pass: unpinned installer keeps root-contract, foreign-hook and untrusted file refusals')
        print('pass: candidate session stage accepts the edited hook that canonical stage rejects')
    else:
        raise AssertionError('build-init-boot-mb003-unpinned.py is required for unpinned host checks')
print('pass: actual unchanged installer fails closed on each mismatched protected file, carrier and installed')
print('pass: old installer cannot adopt newly authorized post or hook generation, present or missing')
print('pass: unrelated unpinned file and protected files survive two installer passes in isolated temp tree')
print('pass: generated session-stage hooks independently pinned per variant in reconciliation block')
print('pass: chain installer atomically installs, preserves, and refuses foreign hooks, untrusted scripts, hardlinks, symlinks, staging collisions and unpinned payloads')
print('pass: run-113 and route-cache installers refuse each other; candidate installs missing post and hook, preserving radio')
print('pass: isolated canonical and route-cache session-stage reconciliation accepts its own hook and rejects the other; ownership modeled')
print('pass: persistent-root services derivation reproduces the committed variant, '
      'fails closed on every removed block, applies to the run-98 staged script, '
      'and composes with the post-ack derivation')
