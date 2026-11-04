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
            if [ "$race" = file ]; then
                (umask 077; set -C; printf 'raced target\\n' > "$4") || return 1
            elif [ "$race" = dir ]; then
                "$REAL_BB" mkdir "$4" || return 1
            fi;;
        awk)
            if [ "$2" = -v ] && [ "$3" = "r=$GUEST" ]; then
                "$REAL_BB" awk "$2" "$3" "$4" "$mountinfo"
                return
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
def run_installer(guest, sources, mountinfo_path=None, race='none', dev_spoof='none', root_kind='rw', bb=busybox):
    return subprocess.run([bb, 'sh', '-c', installer_setup + test_installer, 'fixture',
                           bb, str(guest), str(sources), str(mountinfo_path or (guest / 'mountinfo')), race, dev_spoof, root_kind],
                          capture_output=True, text=True, check=False)
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
print('pass: chain installer atomically installs, preserves, and refuses foreign hooks, untrusted scripts, hardlinks, symlinks, staging collisions and unpinned payloads')
print('pass: run-113 and route-cache installers refuse each other; candidate installs missing post and hook, preserving radio')
print('pass: isolated canonical and route-cache session-stage reconciliation accepts its own hook and rejects the other; ownership modeled')
print('pass: persistent-root services derivation reproduces the committed variant, '
      'fails closed on every removed block, applies to the run-98 staged script, '
      'and composes with the post-ack derivation')
