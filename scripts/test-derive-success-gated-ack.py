#!/usr/bin/env python3
import base64
import ctypes
import hashlib
import importlib.util
import os
import pathlib
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


def test_dns_parser(gate, work):
    source = work / 'dns-parser.c'
    library = work / 'dns-parser.so'
    source.write_text(gate.DNS_C + '''
int fixture_answer(const unsigned char *p, size_t n, const unsigned char *id, unsigned char *address) {
    return answer(p, n, id, address);
}
''')
    subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-o', str(library), str(source)], check=True)
    parser = ctypes.CDLL(str(library)).fixture_answer
    parser.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    parser.restype = ctypes.c_int
    query_id = b'\x12\x34'
    question = b'\x07example\x03com\x00\x00\x01\x00\x01'
    header = query_id + struct.pack('!HHHHH', 0x8180, 1, 1, 0, 0)
    record = b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 60, 4) + b'\x5d\xb8\xd8\x22'
    valid = header + question + record

    def parse(packet):
        address = ctypes.create_string_buffer(4)
        result = parser(packet, len(packet), query_id, address)
        return result, address.raw

    assert parse(valid) == (1, b'\x5d\xb8\xd8\x22')
    assert parse(valid[:13] + b'EXAMPLE' + valid[20:]) == (1, b'\x5d\xb8\xd8\x22')
    invalid = [valid[:cut] for cut in range(len(valid))]
    invalid.extend((
        b'\x00\x00' + valid[2:],
        valid[:2] + b'\x01\x00' + valid[4:],
        valid[:2] + b'\x83\x80' + valid[4:],
        valid[:2] + b'\x81\x83' + valid[4:],
        valid[:4] + b'\x00\x02' + valid[6:],
        valid[:6] + b'\x00\x00' + valid[8:],
        valid[:6] + b'\x00\x65' + valid[8:],
        valid[:13] + b'evample' + valid[20:],
        valid[:29] + b'\xc0\x1d' + valid[31:],
        valid[:-4] + b'\x7f\x00\x00\x01',
        valid[:-4] + b'\xa9\xfe\x01\x02',
        valid[:-4] + b'\xe0\x00\x00\x01',
        valid[:-4] + b'\xc0\x00\x02\xff',
        valid[:31] + b'\x00\x1c' + valid[33:],
        valid[:41] + b'\x00\x05' + valid[43:],
    ))
    for index, packet in enumerate(invalid):
        assert parse(packet)[0] == 0, index
    print(f'pass: native build of exact generated DNS parser: 2 valid, {len(invalid)} malformed or unsafe packets; no sockets')


def prepare(work):
    builder = load('builder', 'build-init-boot-persistent-root.py')
    persist = load('persist', 'derive-radio-persistent.py')
    fresh = load('fresh', 'derive-radio-fresh-boot.py')
    selfpost = load('selfpost', 'derive-self-post-fresh-boot.py')
    gate = load('gate', 'derive-success-gated-ack.py')
    radio = fresh.derive(persist.derive(builder.current_scripts()['pmos-radio-bringup.sh'].decode()))
    prefix, fresh_hook = selfpost.derive((HERE / 'pmos-self-post.sh').read_text(), radio.encode())
    assert digest(radio.encode()) == 'a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21'
    assert digest(prefix.encode()) == 'c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7'
    source, radio_path, post_path, hook_path = (work / name for name in ('prefix', 'radio', 'post', 'hook'))
    source.write_text(prefix)
    radio_path.write_text(radio)
    command = [sys.executable, '-B', str(HERE / 'derive-success-gated-ack.py')]
    subprocess.run(command + list(map(str, (source, radio_path, post_path, hook_path))), check=True)
    post, hook = post_path.read_text(), hook_path.read_text()
    assert post.startswith(prefix)
    encoded = post.split("<<'GATE_DNS_EOF'\n", 1)[1].split('\nGATE_DNS_EOF', 1)[0]
    probe = base64.b64decode(encoded, validate=False)
    assert probe[:6] == b'\x7fELF\x02\x01' and probe[18:20] == b'\xb7\x00'
    assert len(probe) == gate.DNS_PROBE_SIZE and digest(probe) == gate.DNS_PROBE_SHA
    gate.validate_dns_probe(probe)
    assert stat.S_IMODE(post_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(hook_path.stat().st_mode) == 0o600
    expected_gate = gate.GATE.replace('@DNS_BASE64@', '\n'.join(textwrap.wrap(base64.b64encode(probe).decode('ascii'), 96)))
    expected_gate = expected_gate.replace('@DNS_SHA@', digest(probe))
    assert post == prefix + expected_gate
    assert digest(post.encode()) == '9a8c40adce2f84d61e30fd49f6d0f3be5a08d3a57909e9335c3c02f2751ea97b'
    assert gate.derive(prefix, radio.encode(), probe) == (post, hook)
    fresh_pin = f'{gate.POST_PATH} {digest(prefix.encode())}'
    gate_pin = f'{gate.POST_PATH} {digest(post.encode())}'
    radio_pin = f'{gate.RADIO_PATH} {digest(radio.encode())}'
    launch = f"' self-post {gate.POST_PATH} & )\n"
    assert fresh_hook.count(fresh_pin) == 1 and fresh_hook.count(radio_pin) == 1
    assert fresh_hook.count(launch) == 1
    assert hook == fresh_hook.replace(fresh_pin, gate_pin, 1)
    assert hook.count(gate_pin) == 1 and hook.count(radio_pin) == 1
    assert hook.count(fresh_pin) == 0 and hook.count(launch) == 1
    assert hook.index(gate_pin) < hook.index(radio_pin) < hook.index('done\n') < hook.index(launch)
    assert 'refusing launch' not in hook
    for bad_post, bad_radio in ((prefix + '\n', radio.encode()), (prefix, radio.encode() + b'\n')):
        try:
            gate.derive(bad_post, bad_radio, probe)
        except SystemExit:
            pass
        else:
            raise AssertionError('changed #291 input accepted')
    radio_assignment = f'RADIO_SHA={gate.FRESH_RADIO_SHA}\n'
    assert prefix.count(radio_assignment) == 1
    bad_pin = prefix.replace(radio_assignment, f'RADIO_SHA={"0" * 64}\n', 1)
    with mock.patch.object(gate, 'FRESH_POST_SHA', digest(bad_pin.encode())):
        try:
            gate.derive(bad_pin, radio.encode(), probe)
        except SystemExit as exc:
            assert 'fresh post radio pin differs' in str(exc)
        else:
            raise AssertionError('wrong radio pin in fresh post accepted')
    for bad_probe in (probe[:-1], probe + b'\x00', probe[:-1] + bytes([probe[-1] ^ 1]), b''):
        for check in (gate.validate_dns_probe, lambda value: gate.derive(prefix, radio.encode(), value)):
            try:
                check(bad_probe)
            except SystemExit:
                pass
            else:
                raise AssertionError('changed DNS probe pin accepted')
    for label, fake_digest, fake_size in (
        ('digest', '0' * 64, gate.DNS_PROBE_SIZE),
        ('size', gate.DNS_PROBE_SHA, gate.DNS_PROBE_SIZE + 1),
    ):
        with mock.patch.object(gate, 'DNS_PROBE_SHA', fake_digest), mock.patch.object(gate, 'DNS_PROBE_SIZE', fake_size):
            try:
                gate.build_dns_probe()
            except SystemExit as exc:
                assert 'pinned size and digest' in str(exc), (label, exc)
            else:
                raise AssertionError(f'compiler output passed wrong {label} pin')
    for path in (post_path, hook_path):
        subprocess.run(['sh', '-n', str(path)], check=True)

    def reject(label, args, reason):
        result = subprocess.run(command + list(map(str, args)), capture_output=True, check=False)
        assert result.returncode != 0, label
        assert reason.encode() in result.stderr, (label, result.stderr)

    def absent(*paths):
        for path in paths:
            assert not os.path.lexists(path), path

    original_post, original_hook = post_path.read_bytes(), hook_path.read_bytes()
    duplicate = work / 'duplicate-output'
    reject('duplicate outputs', (source, radio_path, duplicate, duplicate), 'outputs must be distinct paths')
    absent(duplicate)
    alias_dir = work / 'alias-directory'
    alias_dir.symlink_to(work, target_is_directory=True)
    reject('aliased duplicate outputs', (source, radio_path, duplicate, alias_dir / duplicate.name), 'outputs must be distinct paths')
    absent(duplicate)
    spare = work / 'spare-output'
    reject('existing post output', (source, radio_path, post_path, spare), 'output already exists')
    absent(spare)
    reject('existing hook output', (source, radio_path, spare, hook_path), 'output already exists')
    absent(spare)
    hardlink = work / 'hardlink-output'
    os.link(source, hardlink)
    reject('hardlink output', (source, radio_path, hardlink, spare), 'output already exists')
    assert hardlink.read_bytes() == source.read_bytes() and hardlink.stat().st_ino == source.stat().st_ino
    absent(spare)
    symlink = work / 'symlink-output'
    symlink.symlink_to(hook_path)
    reject('symlink output', (source, radio_path, spare, symlink), 'output already exists')
    assert symlink.is_symlink() and symlink.resolve() == hook_path
    absent(spare)
    dangling = work / 'dangling-output'
    dangling.symlink_to(work / 'absent-target')
    reject('dangling output symlink', (source, radio_path, dangling, spare), 'output already exists')
    assert dangling.is_symlink()
    absent(spare, work / 'absent-target')
    reject('output equals input', (source, radio_path, source, spare), 'output already exists')
    absent(spare)
    reject('same input', (radio_path, radio_path, work / 'bad-post', work / 'bad-hook'), 'inputs must be distinct regular files')
    absent(work / 'bad-post', work / 'bad-hook')
    bad_post = work / 'wrong-prefix'
    bad_radio = work / 'wrong-radio'
    bad_post.write_text(prefix + '\n')
    bad_radio.write_bytes(radio.encode() + b'\n')
    for label, left, right in (('post pin', bad_post, radio_path), ('radio pin', source, bad_radio)):
        reject(label, (left, right, work / 'bad-post', work / 'bad-hook'), 'inputs are not the exact #291 candidates')
        absent(work / 'bad-post', work / 'bad-hook')
    assert source.read_text() == prefix and radio_path.read_text() == radio
    assert post_path.read_bytes() == original_post and hook_path.read_bytes() == original_hook
    print(f'pass: exact #291 prefix and radio; CLI output safety and digest-pin negatives; generated post {digest(post.encode())}')
    test_dns_parser(gate, work)


def main():
    if len(sys.argv) == 2:
        prepare(pathlib.Path(sys.argv[1]))
    elif len(sys.argv) == 1:
        with tempfile.TemporaryDirectory(prefix='success-gate-derive.') as tmp:
            prepare(pathlib.Path(tmp))
    else:
        raise SystemExit('usage: test-derive-success-gated-ack.py [work-directory]')


if __name__ == '__main__':
    main()
