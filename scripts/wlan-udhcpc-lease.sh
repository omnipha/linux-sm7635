#!/bin/busybox sh
set -eu

[ "${interface:-}" = wlan0 ] || exit 1
IP_CMD=${IP_CMD:-/bin/ip}
BUSYBOX=${BUSYBOX:-/bin/busybox}
RESOLV_CONF=${RESOLV_CONF:-/etc/resolv.conf}

case "${1:-}" in
	deconfig)
		"$IP_CMD" addr flush dev wlan0
		;;
	bound|renew)
		[ -n "${ip:-}" ] && [ -n "${subnet:-}" ] || exit 1
		prefix=$("$BUSYBOX" ipcalc -p "$ip" "$subnet") || exit 1
		case "$prefix" in
			PREFIX=*) prefix=${prefix#PREFIX=} ;;
			*) exit 1 ;;
		esac
		case "$prefix" in
			''|*[!0-9]*) exit 1 ;;
		esac
		"$IP_CMD" addr flush dev wlan0
		"$IP_CMD" addr add "$ip/$prefix" dev wlan0
		if [ -n "${router:-}" ]; then
			set -f
			set -- $router
			"$IP_CMD" route replace default via "$1" dev wlan0
		fi
		: > "$RESOLV_CONF"
		if [ -n "${dns:-}" ]; then
			set -f
			for server in $dns; do
				"$BUSYBOX" printf 'nameserver %s\n' "$server" >> "$RESOLV_CONF"
			done
		fi
		;;
	*) exit 1 ;;
esac
