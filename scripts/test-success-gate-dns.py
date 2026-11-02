#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import ipaddress
import json
import os
import pathlib
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True

HERE = pathlib.Path(__file__).resolve().parent
PROBE_SHA = '906a3c3f3f5c7a666f394dff434604a4b6a6bf2d683d8e04e3d947316132fe97'
PROBE_SIZE = 597840
SERVER = '192.0.2.53'
OTHER_SERVER = '192.0.2.54'
ANSWER = '203.0.113.42'
QUESTION = b'\x07example\x03com\x00\x00\x01\x00\x01'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def namespace(path):
    info = os.stat(path)
    return info.st_dev, info.st_ino


def run_ip(*args):
    return subprocess.run(['ip', *args], check=True, capture_output=True, text=True).stdout


def verify_network(parent_pid, parent_namespace):
    require(os.geteuid() == 0, 'private namespace fixture requires root')
    require(namespace(f'/proc/{parent_pid}/ns/net') == parent_namespace,
            'original process or network namespace changed')
    require(namespace('/proc/self/ns/net') != parent_namespace,
            'refusing to touch the original network namespace')
    require({name for _, name in socket.if_nameindex()} == {'lo'},
            'new network namespace contains unexpected interfaces')
    for family in ('-4', '-6'):
        routes = json.loads(run_ip('-j', family, 'route', 'show', 'table', 'all'))
        require(not routes, f'new network namespace contains {family} routes: {routes}')


def verify_isolation():
    links = json.loads(run_ip('-j', '-details', 'link', 'show'))
    require({link['ifname'] for link in links} == {'lo', 'wlan0'},
            f'unexpected network interfaces: {links}')
    wlan = next(link for link in links if link['ifname'] == 'wlan0')
    require(wlan.get('linkinfo', {}).get('info_kind') == 'dummy',
            f'wlan0 is not a dummy interface: {wlan}')
    for family in ('-4', '-6'):
        routes = json.loads(run_ip('-j', family, 'route', 'show', 'table', 'all'))
        require(all(route.get('dev') in ('lo', 'wlan0') and
                    route.get('dst') != 'default' and 'gateway' not in route
                    for route in routes), f'unexpected {family} route: {routes}')


def dns_socket(address=SERVER, port=53):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    sock.bind((address, port))
    return sock


@contextlib.contextmanager
def probe(binary, *args, trace=False):
    command = ['qemu-aarch64']
    if trace:
        command.append('-strace')
    command.extend((str(binary), *args))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def result(process, label, code=1, output=b'', timeout=3, trace=False):
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f'{label}: probe did not finish within {timeout}s') from exc
    require(process.returncode == code and stdout == output,
            f'{label}: exit={process.returncode}, stdout={stdout!r}, stderr={stderr!r}')
    require(trace or not stderr, f'{label}: unexpected stderr: {stderr!r}')
    return stderr.decode(errors='replace')


def require_socket_option(trace, option, outcome, label):
    pattern = rf'\bsetsockopt\(\d+,1,{option},[^\n]*\) = {outcome}(?:\s|$)'
    require(re.search(pattern, trace) is not None,
            f'{label}: unexpected socket option {option} trace: {trace}')


def require_bound_socket(client, connected=True):
    listing = subprocess.run(['ss', '-H', '-u', '-a', '-n'], check=True,
                             capture_output=True, text=True).stdout
    endpoint = f'{client[0]}%wlan0:{client[1]}'
    require(any(endpoint in line.split() and
                (not connected or f'{SERVER}:53' in line.split())
                for line in listing.splitlines()),
            f'socket is not bound to wlan0: {listing}')


def receive_query(server, label):
    try:
        query, client = server.recvfrom(4096)
    except TimeoutError as exc:
        raise AssertionError(f'{label}: no DNS query received') from exc
    require(len(query) == 12 + len(QUESTION) and
            query[2:] == b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + QUESTION,
            f'{label}: malformed query {query.hex()}')
    require(client[0] == SERVER and 0 < client[1] < 65536,
            f'{label}: unexpected query source {client}')
    return query, client


def response(query, address=ANSWER, flags=0x8180, question=None, owner=b'\xc0\x0c',
             record_type=1, record_class=1, length=4):
    if question is None:
        question = query[12:]
    header = query[:2] + struct.pack('!HHHHH', flags, 1, 1, 0, 0)
    record = owner + struct.pack('!HHIH', record_type, record_class, 60, length)
    return header + question + record + ipaddress.IPv4Address(address).packed


def test_missing_device(binary):
    run_ip('link', 'set', 'lo', 'up')
    run_ip('addr', 'add', f'{SERVER}/32', 'dev', 'lo')
    with dns_socket() as server, dns_socket(SERVER, 0) as control:
        control.sendto(b'control', (SERVER, 53))
        data, client = server.recvfrom(512)
        require(data == b'control', 'unbound loopback control did not reach server')
        server.sendto(b'control-ok', client)
        require(control.recvfrom(512)[0] == b'control-ok', 'loopback control reply failed')
        with probe(binary, SERVER, trace=True) as process:
            trace = result(process, 'missing wlan0', trace=True)
        require_socket_option(trace, 25, r'-1 errno=19', 'missing wlan0')
        server.settimeout(0.2)
        try:
            packet, source = server.recvfrom(512)
        except TimeoutError:
            pass
        else:
            raise AssertionError(f'missing wlan0: unexpected packet {packet!r} from {source}')
    run_ip('addr', 'del', f'{SERVER}/32', 'dev', 'lo')
    print('pass: absent wlan0 fails without a query while unbound loopback UDP works', flush=True)


def configure_wlan():
    run_ip('link', 'add', 'wlan0', 'type', 'dummy')
    run_ip('link', 'set', 'wlan0', 'up')
    for address in (SERVER, OTHER_SERVER):
        run_ip('addr', 'add', f'{address}/32', 'dev', 'wlan0')
    verify_isolation()
    print('pass: isolated namespace contains only loopback and dummy wlan0; no default route', flush=True)


def test_invalid_arguments(binary):
    invalid = [(), (SERVER, SERVER), ('not-an-ip',), ('127.0.0.1',), ('0.0.0.0',),
               ('169.254.1.2',), ('224.0.0.1',), ('192.0.2.0',), ('192.0.2.255',)]
    with dns_socket() as server:
        for args in invalid:
            with probe(binary, *args) as process:
                result(process, f'invalid resolver arguments {args!r}')
        server.settimeout(0.2)
        try:
            packet, source = server.recvfrom(512)
        except TimeoutError:
            pass
        else:
            raise AssertionError(f'invalid arguments sent {packet!r} from {source}')
    print(f'pass: {len(invalid)} invalid resolver argument cases', flush=True)


def test_responses(binary):
    cases = [
        ('valid', lambda q: response(q), True),
        ('valid uppercase question', lambda q: response(q, question=b'\x07EXAMPLE\x03COM\x00\x00\x01\x00\x01'), True),
        ('wrong transaction', lambda q: bytes([q[0] ^ 1]) + response(q)[1:], False),
        ('wrong question name', lambda q: response(q, question=b'\x07evample\x03com\x00\x00\x01\x00\x01'), False),
        ('wrong question type', lambda q: response(q, question=QUESTION[:-4] + b'\x00\x1c\x00\x01'), False),
        ('wrong question class', lambda q: response(q, question=QUESTION[:-2] + b'\x00\x03'), False),
        ('not a response', lambda q: response(q, flags=0x0100), False),
        ('truncation flag', lambda q: response(q, flags=0x8380), False),
        ('refused response', lambda q: response(q, flags=0x8185), False),
        ('name error', lambda q: response(q, flags=0x8183), False),
        ('truncated header', lambda q: response(q)[:11], False),
        ('truncated question', lambda q: response(q)[:20], False),
        ('truncated answer', lambda q: response(q)[:-1], False),
        ('missing answer', lambda q: response(q)[:6] + b'\x00\x00' + response(q)[8:], False),
        ('too many answers', lambda q: response(q)[:6] + b'\x00\x65' + response(q)[8:], False),
        ('bad compression pointer', lambda q: response(q, owner=b'\xc0\x1d'), False),
        ('wrong answer name', lambda q: response(q, owner=b'\x05other\x03com\x00'), False),
        ('wrong answer type', lambda q: response(q, record_type=28), False),
        ('wrong answer class', lambda q: response(q, record_class=3), False),
        ('wrong answer length', lambda q: response(q, length=5), False),
        ('loopback answer', lambda q: response(q, address='127.0.0.1'), False),
        ('link-local answer', lambda q: response(q, address='169.254.1.2'), False),
        ('multicast answer', lambda q: response(q, address='224.0.0.1'), False),
        ('zero host answer', lambda q: response(q, address='192.0.2.0'), False),
        ('broadcast host answer', lambda q: response(q, address='192.0.2.255'), False),
    ]
    with dns_socket() as server:
        for label, make_response, valid in cases:
            with probe(binary, SERVER, trace=label == 'valid') as process:
                query, client = receive_query(server, label)
                if label == 'valid':
                    require_bound_socket(client)
                server.sendto(make_response(query), client)
                trace = result(process, label, code=0 if valid else 1,
                               output=f'{ANSWER}\n'.encode() if valid else b'',
                               trace=label == 'valid')
                if label == 'valid':
                    require_socket_option(trace, 25, '0', label)
                    require_socket_option(trace, 20, '0', label)
    print(f'pass: {len(cases)} real UDP responses, including valid, malformed, truncated and refused', flush=True)
    print('pass: probe socket bound to wlan0 and configured a receive timeout', flush=True)


def test_wrong_sources(binary):
    with dns_socket() as server:
        for label, address, port in (('wrong source address', OTHER_SERVER, 53),
                                     ('wrong source port', SERVER, 0)):
            with dns_socket(address, port) as attacker:
                with probe(binary, SERVER) as process:
                    query, client = receive_query(server, label)
                    forged = response(query, address='198.51.100.11')
                    attacker.sendto(forged, client)
                    time.sleep(0.2)
                    require(process.poll() is None, f'{label}: probe accepted the forged packet')
                    server.sendto(response(query), client)
                    result(process, label, code=0, output=f'{ANSWER}\n'.encode())
                with dns_socket(*client) as same_tuple:
                    same_tuple.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b'wlan0\x00')
                    require_bound_socket(same_tuple.getsockname(), connected=False)
                    attacker.sendto(forged, same_tuple.getsockname())
                    observed, source = same_tuple.recvfrom(4096)
                    require(observed == forged and source == attacker.getsockname(),
                            f'{label}: forged packet did not reach device-bound control')
    print('pass: wrong source address and port ignored; same-tuple wlan0 control receives them', flush=True)


def test_timeout(binary):
    with dns_socket() as server, probe(binary, SERVER) as process:
        receive_query(server, 'silent server')
        start = time.monotonic()
        result(process, 'silent server', timeout=7)
        elapsed = time.monotonic() - start
        require(3.4 <= elapsed <= 6.5, f'silent server: unexpected receive timeout {elapsed:.2f}s')
    print(f'pass: silent UDP server timed out in {elapsed:.2f}s', flush=True)


def inner(parent_pid, parent_namespace, binary):
    verify_network(parent_pid, parent_namespace)
    data = binary.read_bytes()
    require(len(data) == PROBE_SIZE and hashlib.sha256(data).hexdigest() == PROBE_SHA,
            'runtime executable differs from the pinned AArch64 probe')
    test_missing_device(binary)
    configure_wlan()
    test_invalid_arguments(binary)
    test_responses(binary)
    test_wrong_sources(binary)
    test_timeout(binary)
    verify_isolation()
    print('pass: exact pinned AArch64 probe ran under qemu-aarch64; no device or external network', flush=True)


def outer():
    for tool in ('aarch64-linux-gnu-gcc', 'qemu-aarch64', 'sudo', 'unshare', 'ip', 'ss'):
        require(shutil.which(tool) is not None, f'required command not found: {tool}')
    spec = importlib.util.spec_from_file_location('success_gate', HERE / 'derive-success-gated-ack.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot load DNS probe generator')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    require(gate.DNS_PROBE_SHA == PROBE_SHA and gate.DNS_PROBE_SIZE == PROBE_SIZE,
            'generator DNS probe pin changed')
    data = gate.build_dns_probe()
    require(len(data) == PROBE_SIZE and hashlib.sha256(data).hexdigest() == PROBE_SHA,
            'compiled DNS probe differs from the pinned executable')
    print(f'pass: generator reproduced pinned static AArch64 executable {PROBE_SHA}', flush=True)
    subprocess.run(['sudo', '-n', 'true'], check=True, timeout=10)
    print('pass: non-interactive sudo available; testing namespace and network privileges', flush=True)
    with tempfile.TemporaryDirectory(prefix='success-gate-dns-', dir='/tmp') as directory:
        binary = pathlib.Path(directory) / 'dns-probe'
        binary.write_bytes(data)
        binary.chmod(0o700)
        dev, ino = namespace('/proc/self/ns/net')
        command = ['sudo', '-n', 'unshare', '--net', '--fork', sys.executable, '-B',
                   str(pathlib.Path(__file__).resolve()), '--inner', str(os.getpid()),
                   str(dev), str(ino), str(binary)]
        subprocess.run(command, check=True, timeout=90)


def main():
    if len(sys.argv) == 1:
        outer()
    elif len(sys.argv) == 6 and sys.argv[1] == '--inner':
        inner(int(sys.argv[2]), (int(sys.argv[3]), int(sys.argv[4])), pathlib.Path(sys.argv[5]))
    else:
        raise SystemExit(f'usage: {sys.argv[0]}')


if __name__ == '__main__':
    main()
