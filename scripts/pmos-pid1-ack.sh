#!/bin/sh
set -eu
set -f

fail() { printf 'pid1-ack: %s\n' "$*" >&2; exit 1; }
valid_id() {
	case "$1" in
		????????-????-????-????-????????????) case "$1" in *[!0-9a-f-]*) return 1;; esac;;
		*) return 1;;
	esac
}
ssh_guest() {
	timeout -k 1 8 ssh -F /dev/null -T -p 2222 -i "$key" \
		-o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
		-o PreferredAuthentications=publickey -o PasswordAuthentication=no \
		-o KbdInteractiveAuthentication=no -o NumberOfPasswordPrompts=0 \
		-o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$hosts" \
		-o GlobalKnownHostsFile=/dev/null -o UpdateHostKeys=no \
		-o VerifyHostKeyDNS=no -o HostKeyAlgorithms=ssh-ed25519 \
		-o ControlMaster=no -o ControlPath=none -o ProxyCommand=none \
		-o ClearAllForwardings=yes -o ForwardAgent=no \
		-o ConnectTimeout=3 -o ConnectionAttempts=1 \
		root@172.16.42.2 "$1"
}
parse_probe() {
	case "$1" in *[!0-9a-f\ -]*|'') fail 'invalid probe output';; esac
	IFS=' ' read -r probe_nonce probe_id heartbeat extra <<EOF
$1
EOF
	[ -z "$extra" ] && [ "$probe_nonce" = "$nonce" ] &&
		[ "$probe_id" = "$id" ] || fail 'boot or nonce changed'
	case "$heartbeat" in ''|*[!0-9]*) fail 'invalid heartbeat';; esac
}

[ "$#" -eq 3 ] || fail 'usage: pmos-pid1-ack.sh EXPECTED_BOOT_ID PINNED_KNOWN_HOSTS CLIENT_KEY'
id=$1
hosts=$2
key=$3
valid_id "$id" || fail 'invalid expected boot ID'
[ -f "$hosts" ] && [ ! -L "$hosts" ] && [ -r "$hosts" ] &&
	[ "$(stat -c %a "$hosts")" = 600 ] || fail 'unpinned or unprotected known_hosts'
[ -f "$key" ] && [ ! -L "$key" ] && [ -r "$key" ] &&
	[ "$(stat -c %a "$key")" = 600 ] || fail 'unprotected client identity'
[ "$(stat -c %u "$hosts")" = "$(id -u)" ] &&
	[ "$(stat -c %u "$key")" = "$(id -u)" ] || fail 'host identity files have another owner'
awk '$1 == "[172.16.42.2]:2222" && $2 == "ssh-ed25519" && NF == 3 {n++} END {exit(n != 1 || NR != 1)}' "$hosts" || fail 'one pre-pinned ed25519 host key required'

probe='set -eu
b=/bin/busybox
id=$($b cat /proc/sys/kernel/random/boot_id)
[ "$($b id -u)" = 0 ] &&
[ "$($b sha256sum /proc/1/exe | $b cut -d " " -f 1)" = "$($b sha256sum /proc/1/root/bin/busybox | $b cut -d " " -f 1)" ]
if ! $b awk '\''$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}'\'' /proc/1/mounts; then
    c=/proc/1/root/run/pid1-guard/root-contract.sh
    [ -f "$c" ] && [ ! -L "$c" ] && BB=$b . "$c" && root_contract_switched_root /proc/1/mounts /proc/1/mountinfo
fi
s=/proc/1/root/run/pid1-guard
[ "$($b stat -c "%d:%i" /)" = "$($b stat -Lc "%d:%i" /proc/1/root)" ]
[ -d "$s" ] && [ ! -L "$s" ] && [ -f "$s/nonce" ] && [ ! -L "$s/nonce" ]
[ -f "$s/armed" ] && [ ! -L "$s/armed" ]
[ "$($b cat "$s/armed")" = "$id" ]
[ -f "$s/root-identity" ] && [ ! -L "$s/root-identity" ]
[ "$($b stat -Lc "%d:%i" /proc/1/root)" = "$($b cat "$s/root-identity")" ]
[ "$($b stat -c "%u:%a" "$s")" = 0:700 ]
[ -f /run/dropbear-session.pid ] && [ ! -L /run/dropbear-session.pid ]
pid=$($b cat /run/dropbear-session.pid)
case "$pid" in ""|*[!0-9]*) exit 1;; esac
[ -d "/proc/$pid" ]
[ "$($b stat -Lc "%d:%i" "/proc/$pid/root")" = "$($b stat -Lc "%d:%i" /proc/1/root)" ]
cmd=$($b tr "\000" " " < "/proc/$pid/cmdline")
case "$cmd" in
    *"dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid "|*"dropbear -F -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ") :;;
    *) exit 1;;
esac
$b awk '\''$2 == "022A10AC:08AE" && $4 == "0A" {n++} END {exit(n != 1)}'\'' /proc/net/tcp
nonce=$($b cat "$s/nonce")
case "$nonce" in ????????????????????????????????????????????????????????????????)
    case "$nonce" in *[!0-9a-f]*) exit 1;; esac;;
    *) exit 1;;
esac
now=$($b awk '\''{print int($1)}'\'' /proc/uptime)
printf "%s %s %s\n" "$nonce" "$id" "$now"'
first=$(ssh_guest "$probe") || fail 'strict-key post-cutover probe failed'
case "$first" in *[!0-9a-f\ -]*|'') fail 'invalid initial probe';; esac
IFS=' ' read -r nonce first_id first_time first_extra <<EOF
$first
EOF
[ -z "$first_extra" ] && [ "$first_id" = "$id" ] || fail 'invalid initial boot ID'
case "$first_time" in ''|*[!0-9]*) fail 'invalid initial heartbeat';; esac
case "$nonce" in ????????????????????????????????????????????????????????????????)
	case "$nonce" in *[!0-9a-f]*) fail 'invalid nonce';; esac;;
	*) fail 'invalid nonce';;
esac
parse_probe "$first"
previous=$heartbeat
i=0
while [ "$i" -lt 5 ]; do
	sleep 1
	result=$(ssh_guest "$probe") || fail 'strict-key heartbeat failed'
	parse_probe "$result"
	[ "$heartbeat" -ge "$previous" ] || fail 'clock went backwards'
	if [ "$heartbeat" -gt "$previous" ]; then break; fi
	i=$((i + 1))
done
[ "$heartbeat" -gt "$previous" ] || fail 'no advancing post-cutover heartbeat'

write_ack="${probe%printf *}
[ \"\$nonce\" = '$nonce' ] && [ \"\$id\" = '$id' ]
[ ! -e \"\$s/ack\" ] && [ ! -L \"\$s/ack\" ]
umask 077
\$b printf '%s %s\\n' \"\$nonce\" \"\$id\" > \"\$s/.ack-new\"
\$b chmod 600 \"\$s/.ack-new\"
\$b mv \"\$s/.ack-new\" \"\$s/ack\""
ssh_guest "$write_ack" >/dev/null || fail 'ack write or last identity proof failed'
i=0
while [ "$i" -lt 5 ]; do
	if ssh_guest "test \"\$(/bin/busybox cat /proc/1/root/run/pid1-guard/accepted)\" = '$id'" >/dev/null 2>&1; then
		printf 'pid1-ack: accepted on boot %s\n' "$id"
		exit 0
	fi
	sleep 1
	i=$((i + 1))
done
fail 'guard did not confirm the ack'
