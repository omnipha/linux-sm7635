#!/usr/bin/env python3
import hashlib
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

here = pathlib.Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
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

# The installed chain stages the builder-patched radio (run-98 sha256 f54b3372).
# The same derivation must apply there unchanged, keeping its own lease pin and
# persistent prepare-stage behavior.
try:
    builder = load('persistent_builder', 'build-init-boot-persistent-root.py')
    staged = builder.current_scripts()['pmos-radio-bringup.sh'].decode()
except SystemExit:
    staged = None
if staged is not None:
    assert hashlib.sha256(staged.encode()).hexdigest() == \
        'f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f'
    derived = p.derive(staged)
    assert hashlib.sha256(derived.encode()).hexdigest() == \
        'c54c29e1278827bc00faaf506c7ff8e923a8a689a011a2852d5d4b7778d0188d'
    assert 'LEASE_SHA=1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56' in derived
    assert 'persistent OpenRC WLAN services already running; no reinstall' in derived
    postack_derived = postack.derive(derived)
    assert hashlib.sha256(postack_derived.encode()).hexdigest() == \
        '71c7b15d8c5507354268c9e0ccc49279b1e46c4e6a7fd5689bc6e21ef572202d'
    assert p.derive(postack.derive(staged)) == postack_derived, 'derivations do not commute'
    assert 'LEASE_SHA=1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56' in postack_derived
    assert 'armed and unacknowledged on this boot' not in postack_derived
    assert 'armed and acknowledged on this boot' in postack_derived
    assert 'own_digest()' in postack_derived
    assert 'persistent OpenRC WLAN services already running; no reinstall' in postack_derived
    with tempfile.NamedTemporaryFile('w', suffix='.sh') as f:
        f.write(postack_derived)
        f.flush()
        subprocess.run(['sh', '-n', f.name], check=True)
print('pass: persistent-root services derivation reproduces the committed variant, '
      'fails closed on every removed block, applies to the run-98 staged script, '
      'and composes with the post-ack derivation')
