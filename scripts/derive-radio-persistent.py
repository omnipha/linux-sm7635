#!/usr/bin/env python3
"""Derive the persistent-root-aware `services` stage of pmos-radio-bringup.sh.

The pinned script (and the builder-patched copy staged on the installed chain)
refuses its own persisted output on a persistent root. This derives a copy whose
only differences are four blocks of the services stage:
  * install_service_config: idempotent, emitter-based, never overwrites a
    differing persisted WLAN profile
  * conf.d check: pristine archive or the stage own exact output
  * runlevel inventory: only the stage own entries (local, wpa_supplicant,
    networking) pointing at their own init.d script
  * service-input check: absent (pristine) or the stage own exact output
Nonce interlock, capture gate, guard checks, pins and the lease-helper pin are
untouched. Each replaced block must match exactly once; otherwise the derivation
fails. Input and output are files, nothing is executed and no device is touched.
Chain with derive-radio-postack.py for an acked live session.

usage: derive-radio-persistent.py INPUT OUTPUT
"""
import sys

INSTALL = r'''install_service_config() {
	umask 077
	$BB cat > /etc/wpa_supplicant/wpa_supplicant.conf || fail 'profile transfer failed'
	[ -s /etc/wpa_supplicant/wpa_supplicant.conf ] &&
		[ "$($BB stat -c '%u:%a' /etc/wpa_supplicant/wpa_supplicant.conf)" = 0:600 ] || {
		$BB rm -f /etc/wpa_supplicant/wpa_supplicant.conf
		fail 'profile missing or not root-only'
	}
	$BB printf '#!/bin/busybox sh\nIP_CMD=/sbin/ip\nexport IP_CMD\nexec /bin/busybox sh /run/radio-bringup/wlan-udhcpc-lease.sh "$@"\n' > "$STATE/lease-wrapper.sh"
	$BB chmod 700 "$STATE/lease-wrapper.sh"
	$BB printf 'auto wlan0\niface wlan0 inet dhcp\n\tdhcp-script /run/radio-bringup/lease-wrapper.sh\n\tudhcpc-opts -t 5 -T 3 -A 5 -n\n' > /etc/network/interfaces
	$BB chmod 600 /etc/network/interfaces
	$BB printf 'ifquery=/run/radio-bringup/ifquery-wlan\n' > /etc/conf.d/networking
	$BB printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan0"\n' > /etc/conf.d/wpa_supplicant
	$BB chmod 600 /etc/conf.d/networking
	$BB printf '#!/bin/busybox sh\nif [ "$#" = 4 ] && [ "$1" = -i ] && [ "$2" = /etc/network/interfaces ] && [ "$3" = --list ] && [ "$4" = -a ]; then /bin/busybox printf "wlan0\\n"; exit 0; fi\nexec /sbin/ifquery "$@"\n' > "$STATE/ifquery-wlan"
	$BB chmod 700 "$STATE/ifquery-wlan"
	$BB ln -s busybox /bin/run-parts
	$BB ln -s ../bin/busybox /sbin/udhcpc
	[ "$(/sbin/ifquery -i /etc/network/interfaces --list -a)" = 'lo
wlan0' ] || fail 'unexpected ifupdown interface inventory'
	[ "$("$STATE/ifquery-wlan" -i /etc/network/interfaces --list -a)" = wlan0 ] || fail 'WLAN-only interface selector failed'
	[ "$($BB stat -c '%u:%a' /etc/network/interfaces)" = 0:600 ] &&
		[ "$($BB stat -c '%u:%a' /etc/conf.d/networking)" = 0:600 ] || fail 'service config not root-only'
	$BB ln -s /etc/init.d/wpa_supplicant /etc/runlevels/default/wpa_supplicant
	$BB ln -s /etc/init.d/networking /etc/runlevels/default/networking
}

'''
INSTALL_NEW = r'''emit_lease_wrapper() { $BB printf '#!/bin/busybox sh\nIP_CMD=/sbin/ip\nexport IP_CMD\nexec /bin/busybox sh /run/radio-bringup/wlan-udhcpc-lease.sh "$@"\n'; }
emit_interfaces() { $BB printf 'auto wlan0\niface wlan0 inet dhcp\n\tdhcp-script /run/radio-bringup/lease-wrapper.sh\n\tudhcpc-opts -t 5 -T 3 -A 5 -n\n'; }
emit_networking_conf() { $BB printf 'ifquery=/run/radio-bringup/ifquery-wlan\n'; }
emit_wpa_conf() { $BB printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan0"\n'; }
emit_ifquery() { $BB printf '#!/bin/busybox sh\nif [ "$#" = 4 ] && [ "$1" = -i ] && [ "$2" = /etc/network/interfaces ] && [ "$3" = --list ] && [ "$4" = -a ]; then /bin/busybox printf "wlan0\\n"; exit 0; fi\nexec /sbin/ifquery "$@"\n'; }

own_digest() {
	case "$1" in
	/etc/network/interfaces) emit_interfaces;;
	/etc/conf.d/networking) emit_networking_conf;;
	/etc/conf.d/wpa_supplicant) emit_wpa_conf;;
	"$STATE/ifquery-wlan") emit_ifquery;;
	"$STATE/lease-wrapper.sh") emit_lease_wrapper;;
	*) return 1;;
	esac | $BB sha256sum | $BB cut -d ' ' -f 1
}

own_runlevel_entry() {
	case "$1" in
	/etc/runlevels/default/local|/etc/runlevels/default/wpa_supplicant|/etc/runlevels/default/networking)
		[ "$($BB readlink "$1")" = "/etc/init.d/${1##*/}" ];;
	*) return 1;;
	esac
}

service_input_persistent() {
	path=$1
	case "$path" in
	/etc/wpa_supplicant/wpa_supplicant.conf)
		[ -f "$path" ] && [ ! -L "$path" ] && [ "$($BB stat -c '%u:%a' "$path")" = 0:600 ]
		return;;
	/bin/run-parts)
		[ "$($BB readlink "$path")" = busybox ]
		return;;
	/sbin/udhcpc)
		[ "$($BB readlink "$path")" = ../bin/busybox ]
		return;;
	/etc/conf.d/wpa_supplicant)
		[ -f "$path" ] && [ ! -L "$path" ] || return 1
		case "$($BB stat -c '%u:%a' "$path")" in 0:600|0:644) :;; *) return 1;; esac
		[ "$(hash "$path")" = "$WPA_CONF_SHA" ] || [ "$(own_digest "$path")" = "$(hash "$path")" ]
		return;;
	esac
	mode=0:600
	case "$path" in "$STATE/ifquery-wlan"|"$STATE/lease-wrapper.sh") mode=0:700;; esac
	[ -f "$path" ] && [ ! -L "$path" ] && [ "$($BB stat -c '%u:%a' "$path")" = "$mode" ] &&
		[ "$(own_digest "$path")" = "$(hash "$path")" ]
}

install_service_config() {
	umask 077
	( umask 077; $BB cat > "$STATE/services-stdin" ) || fail 'profile transfer failed'
	profile_sha=$(hash "$STATE/services-stdin")
	if [ -e /etc/wpa_supplicant/wpa_supplicant.conf ] || [ -L /etc/wpa_supplicant/wpa_supplicant.conf ]; then
		[ -f /etc/wpa_supplicant/wpa_supplicant.conf ] && [ ! -L /etc/wpa_supplicant/wpa_supplicant.conf ] &&
			[ "$($BB stat -c '%u:%a' /etc/wpa_supplicant/wpa_supplicant.conf)" = 0:600 ] ||
			{ $BB rm -f "$STATE/services-stdin"; fail 'persisted WLAN profile is not the root-only file this stage writes'; }
		[ "$(hash /etc/wpa_supplicant/wpa_supplicant.conf)" = "$profile_sha" ] ||
			{ $BB rm -f "$STATE/services-stdin"; fail 'persisted WLAN profile differs from standard input; no silent overwrite'; }
	else
		$BB cat "$STATE/services-stdin" > /etc/wpa_supplicant/wpa_supplicant.conf
	fi
	$BB rm -f "$STATE/services-stdin"
	[ -s /etc/wpa_supplicant/wpa_supplicant.conf ] &&
		[ "$($BB stat -c '%u:%a' /etc/wpa_supplicant/wpa_supplicant.conf)" = 0:600 ] || {
		$BB rm -f /etc/wpa_supplicant/wpa_supplicant.conf
		fail 'profile missing or not root-only'
	}
	emit_lease_wrapper > "$STATE/lease-wrapper.sh"
	$BB chmod 700 "$STATE/lease-wrapper.sh"
	emit_interfaces > /etc/network/interfaces
	$BB chmod 600 /etc/network/interfaces
	emit_networking_conf > /etc/conf.d/networking
	emit_wpa_conf > /etc/conf.d/wpa_supplicant
	$BB chmod 600 /etc/conf.d/networking
	emit_ifquery > "$STATE/ifquery-wlan"
	$BB chmod 700 "$STATE/ifquery-wlan"
	[ -L /bin/run-parts ] || $BB ln -s busybox /bin/run-parts
	[ -L /sbin/udhcpc ] || $BB ln -s ../bin/busybox /sbin/udhcpc
	[ "$(/sbin/ifquery -i /etc/network/interfaces --list -a)" = 'lo
wlan0' ] || fail 'unexpected ifupdown interface inventory'
	[ "$("$STATE/ifquery-wlan" -i /etc/network/interfaces --list -a)" = wlan0 ] || fail 'WLAN-only interface selector failed'
	[ "$($BB stat -c '%u:%a' /etc/network/interfaces)" = 0:600 ] &&
		[ "$($BB stat -c '%u:%a' /etc/conf.d/networking)" = 0:600 ] || fail 'service config not root-only'
	[ -L /etc/runlevels/default/wpa_supplicant ] || $BB ln -s /etc/init.d/wpa_supplicant /etc/runlevels/default/wpa_supplicant
	[ -L /etc/runlevels/default/networking ] || $BB ln -s /etc/init.d/networking /etc/runlevels/default/networking
}

'''

CONFD = r'''	[ -f /etc/conf.d/wpa_supplicant ] && [ ! -L /etc/conf.d/wpa_supplicant ] &&
		[ "$(hash /etc/conf.d/wpa_supplicant)" = "$WPA_CONF_SHA" ] || fail 'unexpected supplicant arguments; no -f supported'
'''
CONFD_NEW = r'''	[ -f /etc/conf.d/wpa_supplicant ] && [ ! -L /etc/conf.d/wpa_supplicant ] &&
		{ [ "$(hash /etc/conf.d/wpa_supplicant)" = "$WPA_CONF_SHA" ] ||
		  [ "$(own_digest /etc/conf.d/wpa_supplicant)" = "$(hash /etc/conf.d/wpa_supplicant)" ]; } ||
		fail 'unexpected supplicant arguments; no -f supported'
'''

RUNLEVEL = r'''		for entry in "$path"/* "$path"/.[!.]* "$path"/..?*; do
			[ ! -e "$entry" ] && [ ! -L "$entry" ] || {
				[ "$entry" = /etc/runlevels/default/local ] && [ "$($BB readlink "$entry")" = /etc/init.d/local ] || fail 'another OpenRC service enabled'
			}
		done
	done
	/sbin/rc-service local status >/dev/null 2>&1 &&
		! /sbin/rc-service networking status >/dev/null 2>&1 &&
		! /sbin/rc-service wpa_supplicant status >/dev/null 2>&1 || fail 'unexpected OpenRC service state'
'''
RUNLEVEL_NEW = r'''		for entry in "$path"/* "$path"/.[!.]* "$path"/..?*; do
			[ ! -e "$entry" ] && [ ! -L "$entry" ] || own_runlevel_entry "$entry" || fail 'another OpenRC service enabled'
		done
	done
	/sbin/rc-service local status >/dev/null 2>&1 || fail 'unexpected OpenRC service state'
	for svc in networking wpa_supplicant; do
		if /sbin/rc-service "$svc" status >/dev/null 2>&1; then
			own_runlevel_entry "/etc/runlevels/default/$svc" || fail 'unexpected OpenRC service state'
		fi
	done
'''

INPUTS = r'''	for path in /etc/network/interfaces /etc/wpa_supplicant/wpa_supplicant.conf /etc/conf.d/networking /bin/run-parts /sbin/udhcpc "$STATE/ifquery-wlan" "$STATE/lease-wrapper.sh" "$STATE/services.attempted"; do
		[ ! -e "$path" ] && [ ! -L "$path" ] || fail 'service input already exists; no overwrite'
	done
'''
INPUTS_NEW = r'''	[ ! -e "$STATE/services.attempted" ] && [ ! -L "$STATE/services.attempted" ] || fail 'services already attempted this boot; no retry'
	for path in /etc/network/interfaces /etc/wpa_supplicant/wpa_supplicant.conf /etc/conf.d/networking /etc/conf.d/wpa_supplicant /bin/run-parts /sbin/udhcpc "$STATE/ifquery-wlan" "$STATE/lease-wrapper.sh"; do
		[ ! -e "$path" ] && [ ! -L "$path" ] && continue
		service_input_persistent "$path" || fail "service input already exists and is not pristine or this stage own output: $path"
	done
'''

BLOCKS = ((INSTALL, INSTALL_NEW), (CONFD, CONFD_NEW), (RUNLEVEL, RUNLEVEL_NEW), (INPUTS, INPUTS_NEW))


def derive(text):
    for old, new in BLOCKS:
        if text.count(old) != 1:
            raise SystemExit('services block not found exactly once')
        text = text.replace(old, new, 1)
    return text


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    with open(argv[1], encoding='utf-8') as f:
        out = derive(f.read())
    with open(argv[2], 'w', encoding='utf-8') as f:
        f.write(out)


if __name__ == '__main__':
    main(sys.argv)
