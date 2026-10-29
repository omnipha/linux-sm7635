#!/bin/sh
set -eu
root=${OMNIPHA_SYS_ROOT:-/sys}
address_log=${OMNIPHA_USB_LOG:-/run/omnipha-usb-addr.log}
log=${OMNIPHA_OBSERVE_LOG:-/run/omnipha-usb-observe.log}
seconds=${OMNIPHA_OBSERVE_SECONDS:-180}
state=$(mktemp -d)
trap 'rm -rf -- "$state"' EXIT
umask 077
case $seconds in
*[!0-9]* | '' | 0) exit 1 ;;
esac
offset=$(stat -c %s "$address_log" 2>/dev/null || printf '0\n')
start=$(date +%s)
while [ $(( $(date +%s) - start )) -lt "$seconds" ]; do
	for iface in "$root"/class/net/*; do
		[ -e "$iface" ] || continue
		name=${iface##*/}
		driver=$(readlink -f "$iface/device/driver" 2>/dev/null) || driver=
		driver=${driver##*/}
		case $driver in
		cdc_ncm) address=172.16.42.1/24 ;;
		cdc_ether) address=172.16.43.1/24 ;;
		*) continue ;;
		esac
		node=$(readlink -f "$iface/device") || continue
		match=no
		while [ "$node" != / ]; do
			if [ -r "$node/idVendor" ] && [ -r "$node/idProduct" ] && [ -r "$node/manufacturer" ]; then
				if [ "$(cat "$node/idVendor")" = 18d1 ] && [ "$(cat "$node/idProduct")" = 4ee2 ] && [ "$(cat "$node/manufacturer")" = omnipha ]; then
					match=yes
				fi
				break
			fi
			node=$(dirname "$node")
		done
		[ "$match" = yes ] || continue
		if [ ! -f "$state/$name" ]; then
			printf '0 0\n' >"$state/$name"
			printf '%s interface=%s driver=%s observed\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$driver" >>"$log"
		fi
		read -r ever removed <"$state/$name"
		if ip -4 -o addr show dev "$name" 2>/dev/null | grep -Fq " $address "; then
			ever=1
		elif [ "$ever" = 1 ]; then
			removed=1
		fi
		printf '%s %s\n' "$ever" "$removed" >"$state/$name"
	done
	sleep 1
done
if [ -s "$address_log" ]; then
	tail -c +$((offset + 1)) "$address_log" >"$state/events"
else
	: >"$state/events"
fi
found=no
for record in "$state"/*; do
	[ -f "$record" ] || continue
	case $record in */events) continue ;; esac
	name=${record##*/}
	read -r ever removed <"$record"
	ran=no
	added=no
	if grep -Fq "interface=$name " "$state/events"; then ran=yes; fi
	if grep -F "interface=$name " "$state/events" | grep -Fq 'result=added'; then added=yes; fi
	if [ "$ever" = 0 ]; then removed=unknown; elif [ "$removed" = 0 ]; then removed=no; else removed=yes; fi
	printf '%s interface=%s helper_ran=%s address_added=%s removed=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$ran" "$added" "$removed" >>"$log"
	found=yes
done
if [ "$found" = no ]; then
	printf '%s result=no-diagnostic-interface\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$log"
fi
printf '%s\n' "$log"
