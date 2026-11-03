#!/usr/bin/env python3
"""Derive the persistent-root fresh-boot self-post and its existing local.d hook.

Only the radio path/digest and BusyBox dmesg priority-prefix parsing differ
from the traced self-post. The boot-record append/verify, bounded nonce wait,
guard checks, nonce-derived guest capture markers and stage order are kept.
The generated hook pins both persistent-root scripts before using the same
local.d startup mechanism as the installed chain.

usage: derive-self-post-fresh-boot.py SELF_POST RADIO POST_OUTPUT HOOK_OUTPUT
"""
import hashlib
import pathlib
import sys

RADIO_DIR = '/usr/libexec/omnipha'
RADIO_PATH = RADIO_DIR + '/pmos-radio-bringup-fresh-boot.sh'
POST_PATH = RADIO_DIR + '/pmos-self-post-fresh-boot.sh'
OLD_RADIO = 'RADIO="$STATE/pmos-radio-bringup.sh"\n'
OLD_SHA = 'RADIO_SHA=7ef6382644c2e07705d2a8df77840031318c298478c8f93e9bbfd05c00b61812\n'
OLD_GREP = '''\tpanel_hits=$($BB dmesg 2>/dev/null | $BB grep -E "^(\\[[ 0-9.]*\\] )?usb-init: usb-init: pre-SSH panel node=(boe|vxn|none) card0=[ -~]* boot $boot\\$" | $BB sed 's/^\\(\\[[ 0-9.]*\\] \\)\\{0,1\\}usb-init: //')\n'''
NEW_GREP = '''\tpanel_hits=$($BB dmesg 2>/dev/null | $BB sed 's/^<[0-9][0-9]*>//; s/^\\(\\[[ 0-9.]*\\] \\)\\{0,1\\}usb-init: //' | $BB grep -E "^usb-init: pre-SSH panel node=(boe|vxn|none) card0=[ -~]* boot $boot\\$")\n'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit('self-post block not found exactly once')
    return text.replace(old, new, 1)


def derive(text, radio):
    radio_sha = hashlib.sha256(radio).hexdigest()
    post = replace_once(text, OLD_RADIO, f'RADIO="{RADIO_PATH}"\n')
    post = replace_once(post, OLD_SHA, f'RADIO_SHA={radio_sha}\n')
    post = replace_once(post, OLD_GREP, NEW_GREP)
    post_sha = hashlib.sha256(post.encode()).hexdigest()
    hook = f'''#!/bin/busybox sh
BB=/bin/busybox
for spec in "{POST_PATH} {post_sha}" "{RADIO_PATH} {radio_sha}"; do
	set -- $spec
	[ -f "$1" ] && [ ! -L "$1" ] &&
		[ "$($BB stat -c '%u:%a' "$1")" = 0:700 ] &&
		[ "$($BB sha256sum "$1" | $BB cut -d ' ' -f 1)" = "$2" ] || {{
		$BB printf 'pmos-self-post-fresh: pinned persistent script missing or changed\\n' >/dev/kmsg 2>/dev/null || true
		exit 1
	}}
done
( /bin/busybox setsid /bin/busybox sh -c '
	/bin/busybox sh "$1" >/dev/null 2>&1
	result=$?
	[ "$result" -eq 0 ] || /bin/busybox printf "pmos-self-post-fresh: process exited rc=%s\\n" "$result" >/dev/kmsg 2>/dev/null || true
	exit "$result"
' self-post {POST_PATH} & )
'''
    return post, hook


def main(argv):
    if len(argv) != 5:
        raise SystemExit(__doc__)
    source, radio, output, hook_output = map(pathlib.Path, argv[1:])
    post, hook = derive(source.read_text(), radio.read_bytes())
    output.write_text(post)
    hook_output.write_text(hook)


if __name__ == '__main__':
    main(sys.argv)
