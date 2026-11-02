#!/usr/bin/env python3
import importlib.util, pathlib, subprocess, sys, tempfile
here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('d', here / 'derive-radio-postack.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
for name in ('pmos-radio-bringup.sh', 'pmos-radio-bringup-persistent.sh'):
    d.derive((here / name).read_text())
src = (here / 'pmos-radio-bringup.sh').read_text()
out = d.derive(src)
assert out != src
assert 'armed and acknowledged on this boot' in out
assert 'unacknowledged on this boot' not in out
assert '/run/pid1-guard/nonce' not in out.split('capture_gate()')[1].split('once()')[0]
assert 'host-verified capture marker is not in this boot kmsg' in out
# only the two blocks differ: same line count of untouched tail
assert src.split('once() {')[1] == out.split('once() {')[1]
for bad in (src.replace("armed and unacknowledged on this boot", "x"), src.replace('capture_gate() {', 'capture_gate2() {')):
    try:
        d.derive(bad)
    except SystemExit:
        continue
    raise AssertionError('derivation accepted a changed input')
with tempfile.NamedTemporaryFile('w', suffix='.sh') as f:
    f.write(out); f.flush()
    subprocess.run(['sh', '-n', f.name], check=True)
persistent = d.derive((here / 'pmos-radio-bringup-persistent.sh').read_text())
assert 'armed and acknowledged on this boot' in persistent
assert 'own_digest()' in persistent
print('pass: post-ack radio derivation replaces exactly the guard and capture gate, fails closed otherwise')
