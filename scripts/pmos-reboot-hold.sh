#!/bin/sh
set -eu
set -f

fail() { printf 'reboot-hold: %s\n' "$*" >&2; exit 1; }
valid_id() {
	case "$1" in
		????????-????-????-????-????????????) case "$1" in *[!0-9a-f-]*) return 1;; esac;;
		*) return 1;;
	esac
}
ssh_diagnostic() {
	timeout -k 1 8 ssh -F /dev/null -T -p 22 -i "$key" \
		-o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
		-o PreferredAuthentications=publickey -o PasswordAuthentication=no \
		-o KbdInteractiveAuthentication=no -o NumberOfPasswordPrompts=0 \
		-o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$hosts" \
		-o GlobalKnownHostsFile=/dev/null -o UpdateHostKeys=no \
		-o VerifyHostKeyDNS=no -o HostKeyAlgorithms=ssh-ed25519 \
		-o "HostKeyAlias=$host_alias" \
		-o ControlMaster=no -o ControlPath=none -o ProxyCommand=none \
		-o ClearAllForwardings=yes -o ForwardAgent=no \
		-o ConnectTimeout=3 -o ConnectionAttempts=1 \
		root@172.16.42.2 "$1"
}

[ "$#" -eq 3 ] || fail 'usage: REBOOT_HOLD_PRE_BOOT_ID=ID REBOOT_HOLD_CAPTURE_DIR=DIR pmos-reboot-hold.sh EXPECTED_NEW_BOOT_ID|--arm PINNED_KNOWN_HOSTS_22 CLIENT_KEY'
id=$1
hosts=$2
key=$3
pre_boot=${REBOOT_HOLD_PRE_BOOT_ID:-}
capture=${REBOOT_HOLD_CAPTURE_DIR:-}
capture_tool=${REBOOT_HOLD_CAPTURE_TOOL:-}
[ -n "$capture_tool" ] && [ -f "$capture_tool" ] && [ ! -L "$capture_tool" ] ||
	fail 'capture tool required'
if [ "$id" = --arm ]; then
	valid_id "$pre_boot" || fail 'invalid or missing pre-reboot boot ID'
	limit=${REBOOT_HOLD_ARM_SECONDS:-240}
	case "$limit" in ''|*[!0-9]*) fail 'invalid arm limit';; esac
	[ "$limit" -ge 1 ] && [ "$limit" -le 600 ] || fail 'arm limit must be 1..600 seconds'
	ready=$capture/capture/ready.json
	n=0
	while [ "$n" -lt "$limit" ]; do
		if [ -f "$ready" ] && [ ! -L "$ready" ]; then
			next=$(sed -n 's/.*"boot_id": *"\([0-9a-f-]\{36\}\)".*/\1/p' "$ready" 2>/dev/null) || next=
			if valid_id "$next" && [ "$next" != "$pre_boot" ]; then
				if sh "$0" "$next" "$hosts" "$key"; then
					exit 0
				fi
			fi
		fi
		sleep 1
		n=$((n + 1))
	done
	fail 'no fresh boot appeared before the arm limit'
fi
valid_id "$id" || fail 'invalid expected boot ID'
if [ -n "$pre_boot" ]; then
	valid_id "$pre_boot" || fail 'invalid pre-reboot boot ID'
else
	pre_boot=$(sed -n 's/^# connected .* boot_id=\([0-9a-f-]\{36\}\)$/\1/p' "$capture/capture/kmsg.log" 2>/dev/null | head -n 1)
	valid_id "$pre_boot" || fail 'pre-reboot boot ID missing or not present in capture'
fi
[ "$id" != "$pre_boot" ] || fail 'expected boot is still the pre-reboot boot'
[ -f "$hosts" ] && [ ! -L "$hosts" ] && [ -r "$hosts" ] &&
	[ "$(stat -c %a "$hosts")" = 600 ] || fail 'unpinned or unprotected known_hosts'
[ -f "$key" ] && [ ! -L "$key" ] && [ -r "$key" ] &&
	[ "$(stat -c %a "$key")" = 600 ] || fail 'unprotected client identity'
[ "$(stat -c %u "$hosts")" = "$(id -u)" ] &&
	[ "$(stat -c %u "$key")" = "$(id -u)" ] || fail 'host identity files have another owner'
host_alias=$(awk '($1 == "172.16.42.2" || $1 == "[172.16.42.2]:22") && $2 == "ssh-ed25519" && NF == 3 {n++; print $1} END {if (n != 1 || NR != 1) exit 1}' "$hosts") ||
	fail 'one pre-pinned ed25519 host key for diagnostic :22 required'

cap=$capture/capture
[ -n "$capture" ] && [ -d "$cap" ] && [ ! -L "$cap" ] || fail 'capture directory required'
[ -f "$cap/ready.json" ] && [ ! -L "$cap/ready.json" ] &&
	[ -f "$cap/kmsg.log" ] && [ ! -L "$cap/kmsg.log" ] &&
	[ ! -e "$cap/STOP" ] || fail 'capture not healthy'
check_json=$(python3 "$capture_tool" check "$capture" 2>/dev/null) || fail 'capture check failed'
check_boot=$(printf '%s\n' "$check_json" | sed -n 's/.*"boot_id": *"\([0-9a-f-]\{36\}\)".*/\1/p')
[ "$check_boot" = "$id" ] || fail 'capture check is not on the expected boot'
capture_boot=$(sed -n 's/.*"boot_id": *"\([0-9a-f-]\{36\}\)".*/\1/p' "$cap/ready.json")
[ "$capture_boot" != "$pre_boot" ] || fail 'capture is still on the pre-reboot boot'
[ "$capture_boot" = "$id" ] || fail 'capture is not on the expected boot'
last_connected=$(sed -n 's/^# connected .* boot_id=\([0-9a-f-]\{36\}\)$/\1/p' "$cap/kmsg.log" | tail -n 1)
[ "$last_connected" = "$id" ] || fail 'capture has not connected to the expected boot'

probe='set -eu
b=/bin/busybox
[ "$($b id -u)" = 0 ] || exit 1
if ! $b readlink /proc/1/exe 2>/dev/null | $b grep -q busybox; then
	$b grep -qa busybox /proc/1/cmdline || exit 1
fi
id=$($b cat /proc/sys/kernel/random/boot_id)
up=$($b awk '\''{print int($1)}'\'' /proc/uptime)
$b awk '\''$2 == "022A10AC:0016" && $4 == "0A" {n++} END {exit(n != 1)}'\'' /proc/net/tcp
printf "%s %s\n" "$id" "$up"'
first=$(ssh_diagnostic "$probe") || fail 'strict-key diagnostic probe failed'
case "$first" in *[!0-9a-f\ -]*|'') fail 'invalid probe output';; esac
IFS=' ' read -r probe_id probe_up extra <<EOF
$first
EOF
[ -z "$extra" ] || fail 'invalid probe output'
[ "$probe_id" != "$pre_boot" ] || fail 'diagnostic boot is still the pre-reboot boot'
[ "$probe_id" = "$id" ] || fail 'diagnostic boot is not the expected fresh boot'
case "$probe_up" in ''|*[!0-9]*) fail 'invalid uptime';; esac
[ "$probe_up" -lt 145 ] || fail 'diagnostic boot is past the 145 s hold window'

create='set -eu
b=/bin/busybox
[ "$($b id -u)" = 0 ] || exit 1
[ "$($b cat /proc/sys/kernel/random/boot_id)" = '"'$id'"' ] || exit 1
[ "$($b awk '\''{print int($1)}'\'' /proc/uptime)" -lt 145 ] || exit 1
[ ! -e /run/keep ] || exit 1
[ ! -L /run/keep ] || exit 1
umask 077
$b touch /run/keep
$b chmod 600 /run/keep
[ -f /run/keep ] || exit 1
[ ! -L /run/keep ] || exit 1
[ "$($b stat -c "%u:%a" /run/keep)" = 0:600 ] || exit 1
printf "%s\n" held'
result=$(ssh_diagnostic "$create") || fail 'cannot create the diagnostic hold'
[ "$result" = held ] || fail 'diagnostic hold not confirmed'
printf 'reboot-hold: root-only /run/keep created on boot %s\n' "$id"
