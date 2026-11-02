#!/usr/bin/env python3
"""Derive the live-session (post-ack) variant of pmos-radio-bringup.sh.

The pinned radio script runs only while the PID 1 guard is armed and NOT
acknowledged, and its capture gate needs the guard nonce, which the ack
deletes. For a radio stage started from an acknowledged live session this
derives a copy whose only differences are:
  * guard check: armed == boot id AND accepted == boot id AND no ack file
  * capture gate: the host capture marker must be in this boot's kmsg
Everything else stays byte-identical. Each replaced block must match exactly
once; otherwise the derivation fails. Input and output are files, nothing is
executed and no device is touched.

usage: derive-radio-postack.py INPUT OUTPUT
"""
import re
import sys

GUARD = (
    '[ "$($BB cat /run/pid1-guard/armed 2>/dev/null)" = "$boot" ] &&\n'
    '\t[ -f /run/pid1-guard/nonce ] && [ ! -L /run/pid1-guard/nonce ] &&\n'
    '\t[ ! -e /run/pid1-guard/accepted ] && [ ! -L /run/pid1-guard/accepted ] &&\n'
    '\t[ ! -e /run/pid1-guard/ack ] && [ ! -L /run/pid1-guard/ack ] ||\n'
    "\tfail 'PID 1 guard is not armed and unacknowledged on this boot'\n"
)
GUARD_NEW = (
    '[ "$($BB cat /run/pid1-guard/armed 2>/dev/null)" = "$boot" ] &&\n'
    '\t[ -f /run/pid1-guard/accepted ] && [ ! -L /run/pid1-guard/accepted ] &&\n'
    '\t[ "$($BB cat /run/pid1-guard/accepted 2>/dev/null)" = "$boot" ] &&\n'
    '\t[ ! -e /run/pid1-guard/ack ] && [ ! -L /run/pid1-guard/ack ] ||\n'
    "\tfail 'PID 1 guard is not armed and acknowledged on this boot'\n"
)
GATE_NEW = (
    "capture_gate() {\n"
    "\t[ -n \"$marker\" ] || fail 'fresh host capture selftest marker required before a risky stage'\n"
    "\tcase \"$marker\" in *[!A-Za-z0-9_.-]*) fail 'invalid capture marker';; esac\n"
    "\t$BB dmesg 2>/dev/null | $BB grep -qF \"$marker\" || fail 'host-verified capture marker is not in this boot kmsg'\n"
    "}\n"
)


def derive(text):
    if text.count(GUARD) != 1:
        raise SystemExit('guard block not found exactly once')
    text = text.replace(GUARD, GUARD_NEW, 1)
    gate = re.compile(r"capture_gate\(\) \{\n.*?\n\}\n", re.S)
    found = gate.findall(text)
    if len(found) != 1:
        raise SystemExit('capture_gate not found exactly once')
    return gate.sub(lambda _m: GATE_NEW, text, count=1)


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    with open(argv[1], encoding='utf-8') as f:
        out = derive(f.read())
    with open(argv[2], 'w', encoding='utf-8') as f:
        f.write(out)


if __name__ == '__main__':
    main(sys.argv)
