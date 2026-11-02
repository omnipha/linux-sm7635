#!/usr/bin/env python3
"""Add only the measured empty firmware_mnt repair to the persistent radio.

Input is the output of derive-radio-persistent.py for the installed staged
script. The guard, nonce interlock, capture gate, radio order and services
emitters stay byte-identical. A pre-existing firmware_mnt is removed only when
it is an unmounted, root-owned 0700, empty directory; every other pre-existing
path keeps the original refusal.

usage: derive-radio-fresh-boot.py INPUT OUTPUT
"""
import sys

OLD = '''	if ! $BB grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts; then
		[ ! -e /vendor/firmware_mnt ] && [ ! -L /vendor/firmware_mnt ] || fail 'firmware_mnt path already present but not the read-only vfat'
		$BB mkdir /vendor/firmware_mnt
'''

NEW = '''	if ! $BB grep -q ' /vendor/firmware_mnt vfat ro,' /proc/mounts; then
		if [ -e /vendor/firmware_mnt ] || [ -L /vendor/firmware_mnt ]; then
			[ -d /vendor/firmware_mnt ] && [ ! -L /vendor/firmware_mnt ] &&
				[ "$($BB stat -c '%u:%a' /vendor/firmware_mnt)" = 0:700 ] &&
				[ "$($BB awk '$2 == "/vendor/firmware_mnt" {n++} END {print n+0}' /proc/mounts)" = 0 ] ||
				fail 'firmware_mnt path already present but not the read-only vfat'
			for entry in /vendor/firmware_mnt/* /vendor/firmware_mnt/.[!.]* /vendor/firmware_mnt/..?*; do
				[ ! -e "$entry" ] && [ ! -L "$entry" ] ||
					fail 'firmware_mnt path already present but not the read-only vfat'
			done
			$BB rmdir /vendor/firmware_mnt || fail 'empty firmware_mnt repair failed'
			report 'removed the measured empty unmounted persistent firmware_mnt directory'
		fi
		$BB mkdir /vendor/firmware_mnt
'''


def derive(text):
    if text.count(OLD) != 1:
        raise SystemExit('firmware_mnt block not found exactly once')
    return text.replace(OLD, NEW, 1)


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    with open(argv[1], encoding='utf-8') as f:
        out = derive(f.read())
    with open(argv[2], 'w', encoding='utf-8') as f:
        f.write(out)


if __name__ == '__main__':
    main(sys.argv)
