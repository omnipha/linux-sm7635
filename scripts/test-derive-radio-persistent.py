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
staged = builder.current_scripts()['pmos-radio-bringup.sh'].decode()
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
    hook.write_text('synthetic local hook\n')
    hook.chmod(0o700)
    setup = '''set -eu
REAL_BB=$1
PMOS_ROOT=$2
PMOS_ROOT_KIND=ext4
fixture_bb() {
    if [ "$1" = stat ] && [ "$2" = -c ] && [ "$3" = '%u:%a' ] &&
        [ "$4" = "$PMOS_ROOT/etc/local.d/10-omnipha-self-stage.start" ]; then
        owner=$($REAL_BB stat -c %u "$4")
        [ "$owner" = "$($REAL_BB id -u)" ] || return 1
        printf '0:%s\\n' "$($REAL_BB stat -c %a "$4")"
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
    assert hook.is_file() and hook.read_text() == 'synthetic local hook\n'
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
    local_link.unlink()
    bad = run_stage()
    assert bad.returncode == 0 and local_link.is_symlink(), bad.stderr
    assert not wpa.is_symlink() and not net.is_symlink()
    assert os.readlink(local_link) == '/etc/init.d/local'
print('pass: pre-cutover runlevel reconciliation, repeat, and foreign entry, target and local hook refusals; hook ownership modeled')
print('pass: persistent-root services derivation reproduces the committed variant, '
      'fails closed on every removed block, applies to the run-98 staged script, '
      'and composes with the post-ack derivation')
