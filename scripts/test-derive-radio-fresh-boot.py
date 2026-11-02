#!/usr/bin/env python3
"""Host fixtures for the fresh-boot derivations. No device, no image."""
import hashlib
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
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
HOOK_SHA = 'aaeb1b999bccba577fb1536825d56562ef7892c7ee03edb510120f2fc16b1ee3'


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
    assert '( /bin/busybox setsid /bin/busybox sh /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh >/dev/null 2>&1 & )' in hook

    assert selfpost.NEW_GREP in post and selfpost.OLD_GREP not in post

    for text, name in ((radio, 'radio'), (post, 'post'), (hook, 'hook')):
        for forbidden in ('fastboot', 'init_boot', 'vendor_boot', 'avb'):
            assert forbidden not in text, (name, forbidden)
    assert '2ebdf1db' not in radio + post + hook and 'a71b3f5f' not in radio + post + hook

    with tempfile.TemporaryDirectory(prefix='fresh-boot-291.') as tmp:
        tmp = pathlib.Path(tmp)
        paths = []
        for name, text in (('radio-fresh.sh', radio), ('post-fresh.sh', post), ('hook-fresh.sh', hook)):
            path = tmp / name
            path.write_text(text)
            paths.append(path)
        sh_n(paths)

    print(f'pass: fresh-boot candidate derived fail-closed and host-verified; '
          f'radio {RADIO_FRESH_SHA[:8]} post {POST_FRESH_SHA[:8]} hook {HOOK_SHA[:8]}; '
          f'no image, no device, nonce/capture/guard checks intact')


if __name__ == '__main__':
    main()
