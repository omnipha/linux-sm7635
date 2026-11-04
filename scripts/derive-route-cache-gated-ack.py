#!/usr/bin/env python3
"""Derive the run-113 route-cache gate candidate from the pinned run-113 chain.
"""
import hashlib
import importlib.util
import os
import pathlib
import stat
import sys

HERE = pathlib.Path(__file__).resolve().parent
OLD_POST_SHA = '113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3'
OLD_HOOK_SHA = '3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67'
POST_SHA = 'e48445964beda83d2f661730360954d8c8f9acead7ecbfc6965e2475356c743f'
HOOK_SHA = '6488f1339f4ff6876219a452712c71e9465ddd3887f835d9475a346cd0310377'
OLD_AWK = ('NR == 1 {for (i=1;i<NF;i++) if ($i == "dev" && $(i+1) == "wlan0") ok++} '
           'END {exit(NR != 1 || ok != 1)}')
NEW_AWK = ('NR == 1 {for (i=1;i<NF;i++) if ($i == "dev") '
           '{if ($(i+1) == "wlan0") ok++; else bad++}} '
           r'NR == 2 {if ($0 !~ /^[ \t]*cache[ \t]*$/) bad++} '
           'NR > 2 {bad++} END {exit(NR < 1 || ok != 1 || bad)}')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def derive(post, hook):
    if sha(post) != OLD_POST_SHA or sha(hook) != OLD_HOOK_SHA:
        raise ValueError('inputs are not the pinned run-113 post and hook')
    old, new = OLD_AWK.encode(), NEW_AWK.encode()
    if post.count(old) != 2 or hook.count(OLD_POST_SHA.encode()) != 1:
        raise ValueError('pinned route checks or hook binding changed')
    updated_post = post.replace(old, new)
    updated_hook = hook.replace(OLD_POST_SHA.encode(), POST_SHA.encode())
    if sha(updated_post) != POST_SHA or sha(updated_hook) != HOOK_SHA:
        raise ValueError('derived post or hook digest differs from the reviewed candidate')
    return updated_post, updated_hook


def read_input(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                not 0 < before.st_size <= maximum):
            raise ValueError('unsafe input')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(fd)
        if before != after or len(data) != before.st_size or path.lstat() != before:
            raise ValueError('input changed while reading')
        return data
    finally:
        os.close(fd)


def main():
    if len(sys.argv) != 5:
        raise SystemExit('usage: derive-route-cache-gated-ack.py POST HOOK POST_OUTPUT HOOK_OUTPUT')
    post_path, hook_path, post_output, hook_output = map(pathlib.Path, sys.argv[1:])
    post, hook = derive(read_input(post_path, 1048576), read_input(hook_path, 16384))
    spec = importlib.util.spec_from_file_location('original_gate', HERE / 'derive-success-gated-ack.py')
    if spec is None or spec.loader is None:
        raise ValueError('cannot load original output writer')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    original.write_outputs(post_output, hook_output, HERE.parent, post.decode(), hook.decode())
    print(f'derived post {POST_SHA}; hook {HOOK_SHA}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(f'FAIL: {exc}') from exc
