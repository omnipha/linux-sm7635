#!/bin/sh
set -eu

BB=/bin/busybox
PIN=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
MOCK_SHA=fe72fe25364a1a08c6482bcecb3175f2c0def38af6fc02967b1edc1d6cf28e71
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { $BB sha256sum "$1" | $BB cut -d ' ' -f 1; }
mounted() {
	$BB awk -v path="$1" -v type="$2" '$2 == path {n++; if ($3 != type) bad++} END {exit(n != 1 || bad)}' /proc/mounts
}
separate() {
	$BB awk -v a="$1" -v b="$2" '$5 == a {left = $3; na++} $5 == b {right = $3; nb++} END {exit(na != 1 || nb != 1 || left == right)}' /proc/self/mountinfo
}
valid_root() {
	[ -d "$1" ] && [ ! -L "$1" ] && mounted "$1" ext4 &&
		$BB awk -v root="$1" '$1 == "/dev/block/sda13" && $2 == root && $3 == "ext4" && $4 ~ /(^|,)rw(,|$)/ {n++} END {exit(n != 1)}' /proc/mounts &&
		[ -f "$1/bin/busybox" ] && [ ! -L "$1/bin/busybox" ] &&
		[ "$(hash "$1/bin/busybox")" = "$NATIVE_SHA" ] &&
		[ -f "$1/pid1-test.sh" ] && [ "$(hash "$1/pid1-test.sh")" = "$SCRIPT_SHA" ] &&
		[ -f "$1/usr/lib/os-release" ] &&
		$BB grep -q 'ID="postmarketos"' "$1/usr/lib/os-release" &&
		[ -x "$1/usr/bin/qemu-aarch64" ] &&
		[ ! -L "$1/dev" ] && [ ! -L "$1/dev/pts" ] &&
		[ ! -L "$1/proc" ] && [ ! -L "$1/sys" ] && [ ! -L "$1/run" ] &&
		mounted "$1/dev" tmpfs && mounted "$1/dev/pts" devpts &&
		mounted "$1/proc" proc && mounted "$1/run" tmpfs &&
		separate "$1/dev" /dev && separate "$1/dev" "$1" &&
		separate "$1/run" "$1" && separate "$1/run" "$1/dev" &&
		$BB awk -v root="$1" '
			$2 == root || index($2, root "/") == 1 {
				if ($2 != root && $2 != root "/dev" && $2 != root "/dev/pts" &&
				    $2 != root "/proc" && $2 != root "/run") bad++
			}
			END {exit(bad != 0)}' /proc/mounts &&
		[ -b "$1/dev/block/sda13" ] && [ ! -L "$1/dev/block/sda13" ] &&
		[ "$($BB stat -c '%t:%T' "$1/dev/block/sda13")" = "$($BB printf '%x:%x' "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}")" ] &&
		[ -f "$1/sys/class/block/sda13/uevent" ] && [ ! -L "$1/sys/class/block/sda13/uevent" ] &&
		[ "$($BB cat "$1/sys/class/block/sda13/uevent")" = 'PARTNAME=userdata' ] &&
		[ -f "$1/sys/class/block/sda13/dev" ] && [ ! -L "$1/sys/class/block/sda13/dev" ] &&
		[ "$($BB cat "$1/sys/class/block/sda13/dev")" = "$MAIN_NUMS" ] &&
		[ -f "$1/sys/class/block/sda13/size" ] && [ ! -L "$1/sys/class/block/sda13/size" ] &&
		[ "$($BB cat "$1/sys/class/block/sda13/size")" = 524288 ]
}
archive_ok() {
	[ -f "$1" ] && [ ! -L "$1" ] && [ "$(hash "$1")" = "$PIN" ]
}
service_state() {
	root=$1
	[ -f "$root/run/dropbear-session.pid" ] && [ ! -L "$root/run/dropbear-session.pid" ] &&
		[ -f "$root/etc/dropbear/session_host_key" ] && [ ! -L "$root/etc/dropbear/session_host_key" ] &&
		[ "$($BB stat -c '%u:%a' "$root/etc/dropbear/session_host_key")" = 0:600 ] || return 1
	pid=$($BB cat "$root/run/dropbear-session.pid")
	case "$pid" in ''|*[!0-9]*) return 1;; esac
	[ -r "/proc/$pid/stat" ] && [ -r "/proc/$pid/cmdline" ] &&
		[ "$($BB stat -Lc '%d:%i' "/proc/$pid/root" 2>/dev/null)" = "$($BB stat -Lc '%d:%i' "$root")" ] &&
		[ "$(hash "/proc/$pid/exe")" = "$(hash "$root/usr/bin/qemu-aarch64")" ] || return 1
	$BB tr '\000' ' ' < "/proc/$pid/cmdline" | $BB grep -q 'dropbear -F -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' || return 1
	inode=$($BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {n++; inode = $10} END {if (n != 1 || inode !~ /^[0-9]+$/ || inode == "0") exit 1; print inode}' /proc/net/tcp) || return 1
	owned=0
	for fd in /proc/"$pid"/fd/*; do
		if [ "$($BB readlink "$fd" 2>/dev/null)" = "socket:[$inode]" ]; then owned=1; fi
	done
	[ "$owned" = 1 ] || return 1
	start=$($BB awk '{print $22}' "/proc/$pid/stat")
	case "$start" in ''|*[!0-9]*) return 1;; esac
	$BB printf '%s %s %s %s %s\n' "$pid" "$start" "$($BB stat -Lc '%d:%i' "$root")" "$(hash "$root/etc/dropbear/session_host_key")" "$inode"
}
boot_record_setup() (
	set -eu
	case "${1:-}" in full|cutover) :;; *) exit 1;; esac
	[ -f /run/pmos-root-contract.sh ] && [ ! -L /run/pmos-root-contract.sh ] || exit 1
	. /run/pmos-root-contract.sh || exit 1
	boot=$($BB cat /proc/sys/kernel/random/boot_id) || exit 1
	panel="usb-init: pre-SSH panel node=boe card0=1 boot $boot"
	(umask 077; set -C; $BB printf '%s\n' "$panel" > /run/pmos-pre-ssh-panel.record) || exit 1
	[ -f /run/pmos-pre-ssh-panel.record ] && [ ! -L /run/pmos-pre-ssh-panel.record ] &&
		[ "$($BB stat -c '%u:%a:%h' /run/pmos-pre-ssh-panel.record)" = 0:600:1 ] &&
		[ "$($BB cat /run/pmos-pre-ssh-panel.record)" = "$panel" ] || exit 1
	boot_record_open / || exit 1
	boot_record_append / "pmos-self-stage: diagnostic hold and :22 verified on boot $boot" || exit 1
	boot_record_append / "$panel" || exit 1
	boot_record_append / 'pmos-stage: using unpacked persistent postmarketOS root' || exit 1
	boot_record_append / 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' || exit 1
	boot_record_append / 'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)' || exit 1
	boot_record_append / 'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)' || exit 1
	boot_record_append / 'pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract' || exit 1
	boot_record_append / 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request' || exit 1
	boot_record_append / 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' || exit 1
	boot_record_append / "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot" || exit 1
	boot_record_append / 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || exit 1
	boot_record_verify / 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' || exit 1
	if [ "$1" = full ]; then
		boot_record_append / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" || exit 1
		boot_record_verify / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" || exit 1
	fi
)
make_nodes() {
	for node in null zero random urandom tty; do
		case "$node" in
			null) major=1; minor=3;;
			zero) major=1; minor=5;;
			random) major=1; minor=8;;
			urandom) major=1; minor=9;;
			tty) major=5; minor=0;;
		esac
		$BB mknod -m 666 "$1/$node" c "$major" "$minor" || fail "device node $1/$node"
	done
}

if [ "${1:-}" = --client ]; then
	[ "$#" -eq 2 ] || fail 'client usage'
	case "$2" in ack|late|stale|timeout|preplanted|symlinked) :;; *) fail 'invalid client case';; esac
	ssh_guest() {
		$BB timeout -k 1 20 ssh -F /dev/null -q -T -p 2222 -i "/run/$1" \
			-o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none \
			-o PreferredAuthentications=publickey -o PasswordAuthentication=no \
			-o KbdInteractiveAuthentication=no -o NumberOfPasswordPrompts=0 \
			-o StrictHostKeyChecking=yes -o "UserKnownHostsFile=/run/$2" \
			-o GlobalKnownHostsFile=/dev/null -o UpdateHostKeys=no \
			-o VerifyHostKeyDNS=no -o HostKeyAlgorithms=ssh-ed25519 \
			-o ControlMaster=no -o ControlPath=none -o ProxyCommand=none \
			-o ClearAllForwardings=yes -o ForwardAgent=no \
			-o ConnectTimeout=3 -o ConnectionAttempts=1 root@172.16.42.2 "$3"
	}
	attempt=0
	until [ -f /proc/1/root/guest/run/service-before ]; do
		[ "$attempt" -lt 30 ] && [ ! -e /proc/1/root/guest/run/client-failed ] || fail 'pre-cutover SSH service did not start'
		$BB sleep 1
		attempt=$((attempt + 1))
	done
	before=$($BB cat /proc/1/root/guest/run/service-before)
	[ "$before" = "$(service_state /proc/1/root/guest)" ] || fail 'pre-cutover service PID, socket, key or root changed'
	server_pid=${before%% *}
	ssh_guest bad_key known_hosts true >/dev/null 2>&1 && fail 'pre-cutover wrong client identity authenticated'
	ssh_guest client_key bad-known_hosts true >/dev/null 2>&1 && fail 'pre-cutover wrong server identity authenticated'
	ssh_guest client_key known_hosts \
		'test "$(id -u)" = 0 && test ! -t 0 && test "$(cat /etc/alpine-release)" = 3.21.9 && grep -q '\''ID="postmarketos"'\'' /etc/os-release && test "$(cat /run/dropbear-session.pid)" = '"$server_pid"' && test "$(/bin/busybox stat -c '\''%d:%i'\'' /)" = "$(/bin/busybox stat -Lc '\''%d:%i'\'' /proc/1/root/guest)" && test "$(/bin/busybox readlink /etc/runlevels/default/local)" = /etc/init.d/local && test ! -e /run/openrc/softlevel && test -f /run/pid1-guard/armed && test "$(cat /proc/1/comm)" = busybox' || fail 'strict key-only pre-cutover SSH or initial PID 1 identity'
	[ "$before" = "$(service_state /proc/1/root/guest)" ] || fail 'pre-cutover service restarted after SSH'
	$BB touch /proc/1/root/guest/run/client-prepared
	attempt=0
	until [ -f /proc/1/root/run/switched-ready ]; do
		[ "$attempt" -lt 30 ] && [ ! -e /proc/1/root/run/client-failed ] || fail 'PID 1 did not switch root with the live service'
		$BB sleep 1
		attempt=$((attempt + 1))
	done
	current=$(service_state /proc/1/root/.) || fail 'post-cutover service process, socket or root missing'
	[ "$before" = "$current" ] || fail "post-cutover service state changed: $before -> $current"
	ssh_guest bad_key known_hosts true >/dev/null 2>&1 && fail 'post-cutover wrong client identity authenticated'
	ssh_guest client_key bad-known_hosts true >/dev/null 2>&1 && fail 'post-cutover wrong server identity authenticated'
	identity=$(ssh_guest client_key known_hosts \
		'test "$(id -u)" = 0 && test ! -t 0 && test "$(cat /run/dropbear-session.pid)" = '"$server_pid"' && test "$(cat /etc/alpine-release)" = 3.21.9 && grep -q '\''ID="postmarketos"'\'' /etc/os-release && test "$(cat /proc/1/comm)" = busybox && test "$(/bin/busybox sha256sum /proc/1/exe | /bin/busybox cut -d " " -f 1)" = "$(/bin/busybox sha256sum /bin/busybox | /bin/busybox cut -d " " -f 1)" && test "$(cat /run/openrc/softlevel)" = default && /sbin/rc-service local status >/dev/null && test "$(/bin/rc-status --crashed)" = "" && test -c /dev/tty && test -c /dev/pts/ptmx && /bin/busybox awk '\''$2 == "/" && $3 == "ext4" {n++} END {exit(n != 1)}'\'' /proc/1/mounts && /usr/bin/qemu-aarch64 -0 sh /bin/distro-busybox -c '\''test "$(/bin/busybox id -u)" = 0 && test "$(/bin/busybox cat /etc/alpine-release)" = 3.21.9'\'' && printf "pmos-pid1-host-ok\n"') || fail 'strict key-only SSH, switched root, OpenRC local or distro BusyBox smoke'
	[ "$identity" = pmos-pid1-host-ok ] || fail 'post-cutover distro identity'
	[ "$before" = "$(service_state /proc/1/root/.)" ] || fail 'post-cutover service restarted after SSH'
	case "$2" in
		ack|late)
			[ ! -e /proc/1/root/run/pid1-guard/ack ] && [ ! -L /proc/1/root/run/pid1-guard/ack ] || fail 'unauthenticated ack accepted'
			sh "$HOST_ACK" "$BOOT_ID" /run/bad-known_hosts /run/client_key >/dev/null 2>&1 && fail 'ack accepted wrong host key'
			sh "$HOST_ACK" "$BOOT_ID" /run/known_hosts /run/bad_key >/dev/null 2>&1 && fail 'ack accepted wrong client key'
			sh "$HOST_ACK" 00000000-0000-0000-0000-000000000000 /run/known_hosts /run/client_key >/dev/null 2>&1 && fail 'ack accepted wrong boot ID'
			if [ "$2" = late ]; then
				attempt=0
				until [ -f /proc/1/root/run/self-post-waiting ]; do
					[ "$attempt" -lt 20 ] || fail 'post-cutover waiter did not start'
					$BB sleep 1
					attempt=$((attempt + 1))
				done
				$BB sleep 8
				[ ! -e /proc/1/root/run/pid1-guard/accepted ] || fail 'late case accepted before the documented ack'
				[ ! -e /proc/1/root/run/pid1-guard/recovery-request ] || fail 'late case reached the deadline before the documented ack'
			fi
			sh "$HOST_ACK" "$BOOT_ID" /run/known_hosts /run/client_key || fail 'actual ack script failed'
			[ "$(ssh_guest client_key known_hosts 'cat /run/pid1-guard/accepted')" = "$BOOT_ID" ] || fail 'ack not accepted'
			[ ! -e /proc/1/root/run/pid1-guard/recovery-request ] || fail 'ack triggered recovery'
			[ -f /proc/1/root/run/pid1-guard/success-ready ] && [ ! -L /proc/1/root/run/pid1-guard/success-ready ] &&
				[ "$($BB stat -c '%u:%a:%h' /proc/1/root/run/pid1-guard/success-ready)" = 0:600:1 ] || fail 'fixture-published success-ready file invalid'
			$BB grep -qF 'pmos-self-post: post-cutover PID 1 on boot '"$BOOT_ID"'; guard identity check passed; pid1 identity check passed' /proc/1/root/.omnipha-boot-record || fail 'fixture-authored ordered boot record missing'
			if [ "$2" = late ]; then
				attempt=0
				until [ -f /proc/1/root/run/self-post-accepted ]; do
					[ "$attempt" -lt 20 ] || fail 'post-cutover waiter rejected the documented late ack'
					$BB sleep 1
					attempt=$((attempt + 1))
				done
				[ ! -e /proc/1/root/run/self-post-failed ] || fail 'post-cutover waiter failed after acceptance'
			fi
			;;
		stale)
			attempt=0
			until [ -f /proc/1/root/run/pid1-guard/recovery-request ]; do
				[ "$attempt" -lt 35 ] || fail 'real mock guard missed the deadline'
				$BB sleep 1
				attempt=$((attempt + 1))
			done
			nonce=$(ssh_guest client_key known_hosts 'cat /run/pid1-guard/nonce')
			[ "${#nonce}" = 64 ] || fail 'stale case has no guard nonce'
			ssh_guest client_key known_hosts "umask 077; printf '%s %s\n' '$nonce' '$BOOT_ID' > /run/pid1-guard/ack"
			$BB sleep 1
			[ ! -e /proc/1/root/run/pid1-guard/accepted ] || fail 'late ack accepted after the deadline'
			[ ! -e /proc/1/root/run/self-post-accepted ] || fail 'post-cutover waiter accepted a late ack'
			sh "$HOST_ACK" "$BOOT_ID" /run/known_hosts /run/client_key >/dev/null 2>&1 && fail 'host ack accepted after the deadline'
			rootfs=$($BB awk '$2 == "/" {print $3}' /proc/1/mounts)
			[ "$rootfs" = ext4 ] || fail 'stale case did not switch to isolated ext4'
			attempt=0
			until $BB grep -q 'pmos-self-post: FAIL: guard ack not accepted (uptime ' /proc/1/root/.omnipha-boot-record; do
				[ "$attempt" -lt 30 ] || { $BB cat /proc/1/root/.omnipha-boot-record >&2 2>/dev/null; fail 'refusal path left no post-cutover FAIL line'; }
				$BB sleep 1
				attempt=$((attempt + 1))
			done
			[ -f /proc/1/root/run/self-post-failed ] || fail 'post-cutover waiter did not fail'
			;;
		timeout)
			attempt=0
			until [ -f /proc/1/root/run/pid1-guard/nonce ]; do
				[ "$attempt" -lt 8 ] || fail 'real guard did not issue a nonce'
				$BB sleep 1
				attempt=$((attempt + 1))
			done
			ssh_guest client_key known_hosts 'printf "invalid\n" > /run/pid1-guard/ack && chmod 600 /run/pid1-guard/ack' || fail 'invalid ack fixture'
			$BB sleep 1
			[ ! -e /proc/1/root/run/pid1-guard/accepted ] || fail 'invalid ack accepted'
			ssh_guest client_key known_hosts 'rm /run/pid1-guard/ack && ln -s nonce /run/pid1-guard/ack' || fail 'symlinked ack fixture'
			$BB sleep 1
			[ ! -e /proc/1/root/run/pid1-guard/accepted ] || fail 'symlinked ack accepted'
			[ ! -e /proc/1/root/run/pid1-guard/recovery-request ] || fail 'timeout case reached deadline before invalid and symlinked ack checks'
			;;
		preplanted)
			[ "$($BB cat /proc/1/root/run/pid1-guard/ack)" = forged ] || fail 'preplanted ack missing'
			[ ! -e /proc/1/root/run/pid1-guard/nonce ] || fail 'preplanted ack issued a nonce'
			;;
		symlinked)
			[ -L /proc/1/root/run/pid1-guard/ack ] || fail 'preplanted symlink missing'
			[ ! -e /proc/1/root/run/pid1-guard/nonce ] || fail 'symlinked ack issued a nonce'
			;;
	esac
	if [ "$2" != ack ] && [ "$2" != late ] && [ "$2" != stale ]; then
		attempt=0
		until [ -f /proc/1/root/run/pid1-guard/recovery-request ]; do
			[ "$attempt" -lt 35 ] || fail 'real mock guard missed recovery request'
			$BB sleep 1
			attempt=$((attempt + 1))
		done
		case "$2" in preplanted|symlinked)
			[ ! -e /proc/1/root/run/pid1-guard/nonce ] || fail 'preplanted ack issued a nonce';;
		esac
		[ "$($BB cat /proc/1/root/run/pid1-guard/recovery-request)" = bootloader ] || fail 'mock recovery request not bootloader'
		[ ! -e /proc/1/root/run/pid1-guard/accepted ] || fail 'unacknowledged guard accepted'
	fi
	ssh_guest client_key known_hosts 'test "$(cat /proc/1/comm)" = busybox && test -c /dev/null && test "$(cat /run/openrc/softlevel)" = default && /sbin/rc-service local status >/dev/null && test "$(/bin/rc-status --crashed)" = ""' || fail 'PID 1, local OpenRC service or guard did not survive'
	$BB printf '%s\n' "$2" > /proc/1/root/run/client-result
	exit 0
fi

if [ "${1:-}" = --switched ]; then
	[ "$$" = 1 ] && [ "$($BB readlink /proc/1/exe)" = /bin/busybox ] || fail 'switch_root did not exec native BusyBox PID 1'
	mounted / ext4 && mounted /dev tmpfs && mounted /dev/pts devpts && mounted /proc proc && mounted /run tmpfs && separate /run /dev && separate /run / &&
		$BB awk '$2 == "/sys" || index($2, "/sys/") == 1 {bad++} END {exit(bad != 0)}' /proc/mounts || fail 'switch_root lost private guest mounts'
	( . /run/pmos-root-contract.sh && root_contract_switched_root /proc/1/mounts /proc/1/mountinfo ) || fail 'switched ext4 root contract failed'
	[ -b /dev/block/sda13 ] && [ ! -L /dev/block/sda13 ] &&
		[ "$($BB stat -c '%t:%T' /dev/block/sda13)" = "$($BB printf '%x:%x' "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}")" ] &&
		[ "$($BB cat /sys/class/block/sda13/uevent)" = 'PARTNAME=userdata' ] &&
		[ "$($BB cat /sys/class/block/sda13/dev)" = "$MAIN_NUMS" ] &&
		[ "$($BB cat /sys/class/block/sda13/size)" = 524288 ] || fail 'isolated userdata identity lost'
	[ ! -e /oldroot ] && [ ! -e /guest ] && [ -f /pid1-test.sh ] && [ "$(hash /pid1-test.sh)" = "$SCRIPT_SHA" ] || fail 'old root retained or switched script invalid'
	[ "$(hash /bin/busybox)" = "$NATIVE_SHA" ] && [ "$(hash /bin/distro-busybox)" = "$DISTRO_SHA" ] || fail 'native or distro BusyBox changed'
	[ -c /dev/null ] && [ -c /dev/tty ] && [ "$($BB readlink /dev/ptmx)" = pts/ptmx ] || fail 'guest devices invalid'
	[ ! -e /run/openrc/softlevel ] && [ "$($BB readlink /etc/runlevels/default/local)" = /etc/init.d/local ] || fail 'unexpected OpenRC state before cutover runlevels'
	case "$CASE" in
		ack|late) boot_record_setup full || fail 'real contract could not create ordered record';;
		stale) boot_record_setup cutover || fail 'real contract could not create pre-cutover record';;
	esac
	/sbin/openrc sysinit >/run/openrc.log 2>&1 &&
		/sbin/openrc boot >>/run/openrc.log 2>&1 &&
		/sbin/openrc default >>/run/openrc.log 2>&1 &&
		[ "$($BB cat /run/openrc/softlevel)" = default ] &&
		/sbin/rc-service local status >>/run/openrc.log 2>&1 &&
		[ "$(/bin/rc-status --crashed)" = '' ] || { $BB cat /run/openrc.log >&2; fail 'post-cutover OpenRC default/local failed'; }
	[ -f /run/pid1-guard/armed ] && [ "$($BB cat /run/pid1-guard/armed)" = "$BOOT_ID" ] &&
		[ "$(hash /run/pid1-guard/mock-restart2)" = "$MOCK_SHA" ] &&
		[ ! -e /bin/restart2 ] && [ ! -L /bin/restart2 ] || fail 'real guard was not safely mock-armed before switch_root'
	[ -f /run/service-before ] && [ ! -L /run/service-before ] || fail 'pre-cutover service record missing'
	before=$($BB cat /run/service-before)
	[ "$before" = "$(service_state /proc/1/root/.)" ] || fail 'pre-existing SSH service changed during switch_root'
	server=${before%% *}
	case "$CASE" in
		ack|late)
			attempt=0
			until [ -f /run/pid1-guard/nonce ]; do
				[ "$attempt" -lt 100 ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'guard did not issue nonce after switch_root'
				$BB sleep 0.1
				attempt=$((attempt + 1))
			done
			nonce=$($BB cat /run/pid1-guard/nonce) || fail 'guard nonce unreadable'
			[ "${#nonce}" = 64 ] || fail 'guard nonce invalid'
			(umask 077; set -C; $BB printf '%s %s\n' "$nonce" "$BOOT_ID" > /run/pid1-guard/success-ready) || fail 'fixture could not publish success-ready'
			[ "$($BB stat -c '%u:%a:%h:%s' /run/pid1-guard/success-ready)" = "0:600:1:$((${#nonce} + ${#BOOT_ID} + 2))" ] || fail 'success-ready publication invalid';;
	esac
	$BB touch /run/switched-ready
	attempt=0
	until [ -f /run/client-result ]; do
		if [ "$attempt" -ge 90 ] || [ -e /run/client-failed ] || ! $BB kill -0 "$server" 2>/dev/null; then
			$BB cat /run/dropbear.log >&2
			$BB cat /run/mock-guard.log >&2
			fail 'surviving SSH client or real mock guard did not complete'
		fi
		$BB sleep 1
		attempt=$((attempt + 1))
	done
	[ "$($BB cat /run/client-result)" = "$CASE" ] || fail 'client result changed'
	[ "$before" = "$(service_state /proc/1/root/.)" ] || fail 'pre-existing SSH service changed after guard result'
	[ "$$" = 1 ] && [ "$($BB readlink /proc/1/exe)" = /bin/busybox ] || fail 'PID 1 changed'
	$BB kill "$server" 2>/dev/null || true
	printf 'pass: %s; host fixture only, no phone: real BusyBox PID 1 switch_root to a fresh loop-backed ext4 image under a fixture-created synthetic tmpfs root with fixture-written synthetic /sys block files (not real sysfs) and fixture-made device nodes; surviving pre-cutover QEMU Dropbear PID, root, socket and pinned key, strict key-only SSH before/after, actual ack script and real guard with digest-pinned isolated mock recovery; boot record lines and success-ready are fixture-authored through the real contract functions, not production-emitted evidence; no device recovery\n' "$CASE"
	exit 0
fi

if [ "${1:-}" = --inner ]; then
	[ "$#" -eq 2 ] && [ "$$" = 1 ] || fail 'fixture did not enter a PID namespace'
	CASE=$2
	case "$CASE" in ack|late|stale|timeout|preplanted|symlinked) :;; *) fail 'invalid case';; esac
	export CASE
	MAIN_NUMS=${HOST_MAIN_NUMS:-}
	FS_UUID=${HOST_FS_UUID:-}
	MAIN_MAJOR=${MAIN_NUMS%%:*}
	MAIN_MINOR=${MAIN_NUMS##*:}
	[ "$MAIN_NUMS" = "$MAIN_MAJOR:$MAIN_MINOR" ] && [ "$MAIN_MAJOR" = 7 ] || fail 'invalid loop device identity'
	case "$MAIN_MINOR" in ''|*[!0-9]*) fail 'invalid loop device minor';; esac
	case "$FS_UUID" in
		????????-????-????-????-????????????)
			case "$FS_UUID" in *[!0-9a-f-]*) fail 'isolated userdata UUID invalid';; esac;;
		*) fail 'isolated userdata UUID invalid';;
	esac
	python3 -I - "${HOST_WORK_IMAGE:-}" "$MAIN_NUMS" "$CASE" <<'PY' || fail 'loop descriptor or backing image mismatch'
import fcntl
import os
import re
import stat
import struct
import sys

path, nums, case = sys.argv[1:]
if not re.fullmatch(r'/tmp/pmos-pid1\.[A-Za-z0-9_]{8}/userdata-' + re.escape(case) + r'\.img', path):
    raise SystemExit(1)
parent = os.stat(os.path.dirname(path), follow_symlinks=False)
if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or stat.S_IMODE(parent.st_mode) != 0o700:
    raise SystemExit(1)
loop = os.fstat(9)
if not stat.S_ISBLK(loop.st_mode) or f'{os.major(loop.st_rdev)}:{os.minor(loop.st_rdev)}' != nums:
    raise SystemExit(1)
image_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
image = os.fstat(image_fd)
if image.st_uid != 0 or stat.S_IMODE(image.st_mode) != 0o600:
    raise SystemExit(1)
info = struct.unpack('=QQQQQIIII64s64s32sQQ', fcntl.ioctl(9, 0x4C05, bytes(232)))
encoded_dev = info[0]
dev_major = (encoded_dev & 0xFFF00) >> 8
dev_minor = (encoded_dev & 0xFF) | ((encoded_dev >> 12) & 0xFFF00)
if (not stat.S_ISREG(image.st_mode) or image.st_nlink != 1 or image.st_size != 268435456
        or (dev_major, dev_minor) != (os.major(image.st_dev), os.minor(image.st_dev))
        or info[1] != image.st_ino
        or info[3] != 0 or info[4] != 0 or info[5] != os.minor(loop.st_rdev)
        or info[6] != 0 or info[8] != 4):
    raise SystemExit(1)
os.close(9)
PY
	export MAIN_NUMS
	$BB mount --make-rprivate / || fail 'private mount namespace unavailable'
	$BB mount -t tmpfs -o mode=0755 tmpfs /dev || fail 'private host dev'
	make_nodes /dev
	$BB mount -t tmpfs -o mode=0700 tmpfs /root || fail 'private host root home'
	$BB mount -t tmpfs -o mode=0700 tmpfs /run || fail 'private host run'
	$BB cp "$HOST_ARCHIVE" /run/session.tar.gz
	archive_ok /run/session.tar.gz || fail 'copied public archive hash'
	archive_ok /run/absent.tar.gz && fail 'missing archive accepted'
	$BB cp /run/session.tar.gz /run/corrupt.tar.gz
	$BB printf x >> /run/corrupt.tar.gz
	archive_ok /run/corrupt.tar.gz && fail 'corrupt archive accepted'
	$BB rm /run/corrupt.tar.gz
	ssh-keygen -q -t ed25519 -N '' -f /run/client_key
	ssh-keygen -q -t ed25519 -N '' -f /run/bad_key
	ssh-keygen -q -t ed25519 -N '' -f /run/bad_host_key
	$BB awk '{print "[172.16.42.2]:2222 " $1 " " $2}' /run/bad_host_key.pub > /run/bad-known_hosts
	ip link set lo up
	ip addr add 172.16.42.2/32 dev lo
	NATIVE_SHA=$(hash /bin/busybox)
	SCRIPT_SHA=$(hash "$HOST_SCRIPT")
	BOOT_ID=$($BB cat /proc/sys/kernel/random/boot_id)
	export NATIVE_SHA SCRIPT_SHA BOOT_ID
	ROOT=/run/pid1-root
	$BB mkdir "$ROOT"
	$BB mount -t tmpfs -o mode=0755,size=512m tmpfs "$ROOT" || fail 'synthetic initial tmpfs'
	$BB mkdir -p "$ROOT/bin" "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" "$ROOT/oldroot" "$ROOT/guest"
	$BB cp /bin/busybox "$ROOT/bin/busybox"
	$BB cp "$HOST_SCRIPT" "$ROOT/pid1-test.sh"
	$BB cp "$HOST_SCRIPT" "$ROOT/init"
	$BB mkdir -p /dev/block
	$BB mknod -m 0400 /dev/block/sda13 b "$MAIN_MAJOR" "$MAIN_MINOR" || fail 'isolated userdata node'
	[ "$($BB blockdev --getsize64 /dev/block/sda13)" = 268435456 ] || fail 'isolated userdata size mismatch'
	[ "$(blkid -s UUID -o value /dev/block/sda13 2>/dev/null)" = "$FS_UUID" ] || fail 'isolated userdata UUID mismatch'
	$BB mount -t ext4 -o rw /dev/block/sda13 "$ROOT/guest" || fail 'isolated ext4 guest mount'
	$BB mount --make-private "$ROOT/guest" || fail 'private guest mount'
	[ -d "$ROOT/guest/lost+found" ] && [ ! -L "$ROOT/guest/lost+found" ] || fail 'fresh image lacks lost+found'
	fresh_entries=$($BB ls -A "$ROOT/guest") || fail 'cannot list fresh image'
	[ "$fresh_entries" = lost+found ] || fail 'fresh image is not empty'
	fresh_entries=$($BB ls -A "$ROOT/guest/lost+found") || fail 'cannot list fresh lost+found'
	[ -z "$fresh_entries" ] || fail 'fresh image lost+found is not empty'
	$BB tar -xzf /run/session.tar.gz -C "$ROOT/guest" || fail 'pinned postmarketOS extraction'
	DISTRO_SHA=$(hash "$ROOT/guest/bin/busybox")
	export DISTRO_SHA
	$BB mv "$ROOT/guest/bin/busybox" "$ROOT/guest/bin/distro-busybox"
	$BB cp /bin/busybox "$ROOT/guest/bin/busybox"
	[ "$($BB find "$ROOT/guest/etc/runlevels" -type l | $BB wc -l)" -eq 0 ] || fail 'archive has pre-enabled runlevels'
	[ -x "$ROOT/guest/etc/init.d/local" ] && [ -d "$ROOT/guest/etc/local.d" ] &&
		[ "$($BB find "$ROOT/guest/etc/local.d" -name '*.start' | $BB wc -l)" -eq 0 ] || fail 'local fixture prerequisites missing'
	$BB ln -s /etc/init.d/local "$ROOT/guest/etc/runlevels/default/local"
	$BB cp "$HOST_SCRIPT" "$ROOT/guest/pid1-test.sh"
	$BB cp /usr/bin/qemu-aarch64 "$ROOT/guest/usr/bin/qemu-aarch64"
	$BB mkdir -p "$ROOT/guest/root/.ssh" "$ROOT/guest/etc/dropbear" "$ROOT/guest/run" "$ROOT/guest/dev/pts" "$ROOT/guest/proc" "$ROOT/guest/sys"
	$BB mount -t tmpfs -o mode=0700,size=8m tmpfs "$ROOT/guest/run" || fail 'separate private guest run'
	$BB chmod 700 "$ROOT/guest/run" "$ROOT/guest/root" "$ROOT/guest/root/.ssh"
	$BB cp /run/client_key.pub "$ROOT/guest/root/.ssh/authorized_keys"
	$BB chmod 600 "$ROOT/guest/root/.ssh/authorized_keys"
	$BB printf 'root:!:0:0:99999:7:::\n' > "$ROOT/guest/etc/shadow"
	$BB chmod 600 "$ROOT/guest/etc/shadow"
	$BB mount -t proc -o nosuid,nodev,noexec proc "$ROOT/proc" || fail 'initial proc'
	$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$ROOT/dev" || fail 'initial dev'
	$BB mount -t proc -o nosuid,nodev,noexec proc "$ROOT/guest/proc" || fail 'guest proc'
	for sys in "$ROOT/sys" "$ROOT/guest/sys"; do
		$BB mkdir -p "$sys/class/block/sda13"
		$BB printf 'PARTNAME=userdata\n' > "$sys/class/block/sda13/uevent"
		$BB printf '%s\n' "$MAIN_NUMS" > "$sys/class/block/sda13/dev"
		$BB printf '%s\n' 524288 > "$sys/class/block/sda13/size"
	done
	$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$ROOT/guest/dev" || fail 'guest dev'
	$BB mkdir "$ROOT/guest/dev/pts"
	$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts "$ROOT/guest/dev/pts" || fail 'guest devpts'
	make_nodes "$ROOT/dev"
	make_nodes "$ROOT/guest/dev"
	for dev in "$ROOT/dev" "$ROOT/guest/dev"; do
		$BB mkdir -p "$dev/block"
		$BB mknod -m 0400 "$dev/block/sda13" b "$MAIN_MAJOR" "$MAIN_MINOR" || fail 'isolated userdata node'
	done
	$BB ln -s pts/ptmx "$ROOT/guest/dev/ptmx"
	$BB umount "$ROOT/guest/dev/pts"
	$BB mount -t tmpfs tmpfs "$ROOT/guest/dev/pts" || fail 'invalid devpts negative setup'
	valid_root "$ROOT/guest" && fail 'invalid devpts accepted'
	$BB umount "$ROOT/guest/dev/pts"
	$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts "$ROOT/guest/dev/pts" || fail 'restore devpts'
	$BB umount "$ROOT/guest/dev/pts"
	$BB umount "$ROOT/guest/dev"
	$BB mount --bind /dev "$ROOT/guest/dev" || fail 'shared dev negative setup'
	valid_root "$ROOT/guest" && fail 'shared dev accepted'
	$BB umount "$ROOT/guest/dev"
	$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$ROOT/guest/dev" || fail 'restore private guest dev'
	make_nodes "$ROOT/guest/dev"
	$BB mkdir -p "$ROOT/guest/dev/block"
	$BB mknod -m 0400 "$ROOT/guest/dev/block/sda13" b "$MAIN_MAJOR" "$MAIN_MINOR" || fail 'restore guest userdata node'
	$BB mkdir "$ROOT/guest/dev/pts"
	$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts "$ROOT/guest/dev/pts" || fail 'restore private guest devpts'
	$BB ln -s pts/ptmx "$ROOT/guest/dev/ptmx"
	$BB mkdir "$ROOT/guest/run/unexpected"
	$BB mount -t tmpfs tmpfs "$ROOT/guest/run/unexpected" || fail 'unexpected guest mount negative setup'
	valid_root "$ROOT/guest" && fail 'unexpected guest mount accepted'
	$BB umount "$ROOT/guest/run/unexpected"
	$BB rmdir "$ROOT/guest/run/unexpected"
	$BB printf x >> "$ROOT/guest/bin/busybox"
	valid_root "$ROOT/guest" && fail 'corrupt guest BusyBox accepted'
	$BB cp /bin/busybox "$ROOT/guest/bin/busybox"
	$BB chroot "$ROOT/guest" /usr/bin/qemu-aarch64 -0 sh /bin/distro-busybox -c 'test "$(/bin/busybox id -u)" = 0' || fail 'distro BusyBox cannot run under QEMU'
	$BB chroot "$ROOT/guest" /usr/bin/qemu-aarch64 /usr/bin/dropbearkey -t ed25519 -f /etc/dropbear/session_host_key >/dev/null || fail 'guest host key'
	$BB chmod 600 "$ROOT/guest/etc/dropbear/session_host_key"
	$BB chroot "$ROOT/guest" /usr/bin/qemu-aarch64 /usr/bin/dropbearkey -y -f /etc/dropbear/session_host_key 2>/dev/null > "$ROOT/guest/run/second-hostkey.pub" || fail 'guest public key'
	$BB awk '/^ssh-ed25519 / {print "[172.16.42.2]:2222 " $1 " " $2}' "$ROOT/guest/run/second-hostkey.pub" > /run/known_hosts
	[ "$($BB wc -l < /run/known_hosts)" -eq 1 ] || fail 'strict host key missing'
	HOST_KEY_SHA=$(hash "$ROOT/guest/etc/dropbear/session_host_key")
	$BB chmod 600 /run/known_hosts /run/bad-known_hosts
	$BB pivot_root "$ROOT" "$ROOT/oldroot" || fail 'pivot to synthetic initial tmpfs'
	[ "$$" = 1 ] && mounted / tmpfs && mounted /guest ext4 || fail 'initial root not pivoted'
	( . /oldroot"$HOST_CONTRACT" && root_contract_pinned_userdata /guest ) || fail 'staged ext4 root contract failed'
	$BB cat > /guest/run/mock <<'MOCK'
#!/bin/busybox sh
set -eu
b=/bin/busybox
s=/run/pid1-guard
[ "$#" -eq 1 ] && [ "$1" = bootloader ] || exit 2
$b awk '$2 == "/" {n++; if ($3 != "tmpfs" && $3 != "ext4") bad++} END {exit(n != 1 || bad)}' /proc/mounts || exit 2
[ "$($b stat -c '%u:%a' "$s")" = 0:700 ] || exit 2
[ "$($b stat -c '%d:%i' /)" = "$($b cat "$s/root-identity")" ] || exit 2
[ ! -e "$s/recovery-request" ] && [ ! -L "$s/recovery-request" ] || exit 2
$b printf 'bootloader\n' > "$s/recovery-request"
MOCK
	$BB chmod 700 /guest/run/mock
	[ "$(hash /guest/run/mock)" = "$MOCK_SHA" ] || fail "mock helper digest: $(hash /guest/run/mock)"
	for budget in 0 179 x; do
		if $BB sh /oldroot"$HOST_GUARD" mock-arm /guest "$budget" /guest/run/mock "$MOCK_SHA" >/guest/run/guard-reject.log 2>&1; then fail "real guard accepted budget $budget"; fi
		case "$budget" in x) reason='invalid deadline';; *) reason='deadline must be 1..178 seconds';; esac
		$BB grep -q "$reason" /guest/run/guard-reject.log || fail "real guard budget $budget rejection reason"
	done
	if $BB sh /oldroot"$HOST_GUARD" mock-arm /guest 10 /guest/run/missing-mock "$MOCK_SHA" >/guest/run/guard-reject.log 2>&1; then fail 'real guard accepted missing mock helper'; fi
	$BB grep -q 'mock helper hash mismatch' /guest/run/guard-reject.log || fail 'real guard missing helper rejection reason'
	$BB printf 'not the pinned helper\n' > /guest/run/wrong-mock
	if $BB sh /oldroot"$HOST_GUARD" mock-arm /guest 10 /guest/run/wrong-mock "$MOCK_SHA" >/guest/run/guard-reject.log 2>&1; then fail 'real guard accepted wrong mock helper'; fi
	$BB grep -q 'mock helper hash mismatch' /guest/run/guard-reject.log || fail 'real guard wrong helper rejection reason'
	if $BB sh /oldroot"$HOST_GUARD" mock-arm /guest 10 /guest/run/mock 0000000000000000000000000000000000000000000000000000000000000000 >/guest/run/guard-reject.log 2>&1; then fail 'real guard accepted unpinned mock digest'; fi
	$BB grep -q 'mock only with pinned fixture' /guest/run/guard-reject.log || fail 'real guard wrong digest rejection reason'
	if $BB sh /oldroot"$HOST_GUARD" arm /guest 10 >/guest/run/guard-reject.log 2>&1; then fail 'real guard armed on non-target host'; fi
	$BB grep -q 'not the target device' /guest/run/guard-reject.log || fail 'real guard target rejection reason'
	[ ! -e /guest/run/pid1-guard ] && [ ! -L /guest/run/pid1-guard ] || fail 'rejected guard created state'
	$BB chroot /guest /usr/bin/qemu-aarch64 -0 sh /bin/distro-busybox -c 'test "$(/bin/busybox cat /etc/alpine-release)" = 3.21.9' || fail 'distro BusyBox smoke before switch_root'
	valid_root /guest || fail 'private guest root or nested mounts invalid'
	if [ "$CASE" = ack ] || [ "$CASE" = late ]; then budget=50; else budget=12; fi
	if [ "$CASE" = stale ]; then budget=10; fi
	$BB sh /oldroot"$HOST_GUARD" mock-arm /guest "$budget" /guest/run/mock "$MOCK_SHA" >/guest/run/mock-guard.log 2>&1 || fail 'real guard mock-arm failed'
	$BB cp /oldroot"$HOST_CONTRACT" /guest/run/pmos-root-contract.sh
	$BB chmod 700 /guest/run/pmos-root-contract.sh
	[ "$(hash /guest/run/pid1-guard/guard.sh)" = "$(hash /oldroot"$HOST_GUARD")" ] &&
		[ "$(hash /guest/run/pid1-guard/mock-restart2)" = "$MOCK_SHA" ] &&
		[ "$($BB cat /guest/run/pid1-guard/armed)" = "$BOOT_ID" ] &&
		[ ! -e /guest/run/pid1-guard/nonce ] || fail 'real guard not pinned and armed before cutover'
	case "$CASE" in
		preplanted) $BB printf 'forged\n' > /guest/run/pid1-guard/ack;;
		symlinked) $BB ln -s nonce /guest/run/pid1-guard/ack;;
	esac
	$BB chroot /guest /usr/bin/qemu-aarch64 /usr/sbin/dropbear -F -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid >/guest/run/dropbear.log 2>&1 &
	server=$!
	attempt=0
	until state=$(service_state /guest); do
		if [ "$attempt" -ge 30 ] || ! $BB kill -0 "$server" 2>/dev/null; then
			$BB cat /guest/run/dropbear.log >&2
			fail 'pre-cutover chroot Dropbear did not listen'
		fi
		$BB sleep 1
		attempt=$((attempt + 1))
	done
	[ "${state%% *}" = "$server" ] && [ "$(hash /guest/etc/dropbear/session_host_key)" = "$HOST_KEY_SHA" ] &&
		[ "$($BB stat -c '%u:%a' /guest/run)" = 0:700 ] &&
		[ "$($BB stat -c '%u:%a' /oldroot/run)" = 0:700 ] &&
		[ "$($BB stat -c '%d:%i' /guest/run)" != "$($BB stat -c '%d:%i' /oldroot/run)" ] || fail 'pre-cutover Dropbear PID, pinned host key or separate run changed'
	$BB printf '%s\n' "$state" > /guest/run/service-before
	[ ! -e /guest/run/openrc/softlevel ] && [ "$($BB readlink /guest/etc/runlevels/default/local)" = /etc/init.d/local ] || fail 'OpenRC fixture changed before cutover'
	if [ "$CASE" = late ] || [ "$CASE" = stale ]; then
		[ -d /guest/etc/local.d ] || fail 'archive local.d missing'
		$BB cat > /guest/etc/local.d/10-omnipha-self-stage.start <<'LATE'
#!/bin/busybox sh
( /bin/busybox setsid /bin/busybox sh /run/radio-bringup/pmos-self-post.sh >/dev/null 2>&1 & )
LATE
		$BB chmod 700 /guest/etc/local.d/10-omnipha-self-stage.start
		$BB mkdir -m 700 /guest/run/radio-bringup
		! $BB grep -qF 'host-owned guard ack' /oldroot"$HOST_POST" || fail 'host-ack wait remains in self-post'
		$BB grep -qF 'cold-start post-cutover PID 1' /oldroot"$HOST_POST" &&
			$BB grep -qF 'independent recovery guard remains unacknowledged' /oldroot"$HOST_POST" || fail 'self-post no longer requires the unacknowledged armed guard'
		$BB printf '%s\n' '#!/bin/busybox sh' 'set -eu' 'BB=/bin/busybox' \
			'export PATH=/bin:/sbin:/usr/bin:/usr/sbin' 'GUARD=/run/pid1-guard' \
			'record_fail() { [ "${POST_RECORD_FAIL:-0}" = 0 ] || return 0; POST_RECORD_FAIL=1; contract=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}; [ -f "$contract" ] && [ ! -L "$contract" ] && . "$contract" || return 0; boot_record_id || return 0; stamp=$($BB awk "NF == 2 && \$1 ~ /^[0-9]+([.][0-9]+)?\$/ {print \$1; ok=1} END {exit(!ok)}" /proc/uptime 2>/dev/null) || stamp=unknown; boot_record_append / "pmos-self-post: FAIL: $* (uptime $stamp)" || true; }' \
			'die() { $BB touch /run/self-post-failed; record_fail "$*"; exit 1; }' \
			'boot=$($BB cat /proc/sys/kernel/random/boot_id)' \
			'$BB touch /run/self-post-waiting' \
			'i=0; until [ -f "$GUARD/accepted" ] && [ "$($BB cat "$GUARD/accepted")" = "$boot" ]; do [ "$i" -lt 20 ] || die "guard ack not accepted"; $BB sleep 1; i=$((i + 1)); done' \
			'$BB touch /run/self-post-accepted' > /guest/run/radio-bringup/pmos-self-post.sh
		$BB chmod 700 /guest/run/radio-bringup/pmos-self-post.sh
	fi
	($BB unshare --mount $BB chroot /oldroot /bin/busybox sh "$HOST_SCRIPT" --client "$CASE" || $BB touch /guest/run/client-failed) &
	client=$!
	$BB kill -0 "$client" 2>/dev/null || fail 'isolated SSH coordinator exited'
	attempt=0
	until [ -f /guest/run/client-prepared ]; do
		if [ "$attempt" -ge 40 ] || [ -e /guest/run/client-failed ] || [ "$state" != "$(service_state /guest)" ]; then
			$BB cat /guest/run/dropbear.log >&2
			fail 'pre-cutover SSH client or surviving Dropbear not healthy'
		fi
		$BB sleep 1
		attempt=$((attempt + 1))
	done
	[ "$state" = "$(service_state /guest)" ] || fail 'Dropbear changed before switch_root'
	exec /bin/busybox switch_root /guest /bin/busybox sh /pid1-test.sh --switched
fi

[ "$#" -eq 0 ] || fail 'usage: test-pmos-pid1.sh'
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ARCHIVE=${ARCHIVE:-$HOME/sm7635-build/i139-userspace/out/postmarketos-session-aarch64.tar.gz}
archive_ok "$ARCHIVE" || fail 'missing or corrupt public postmarketOS session archive'
for host_file in "$HERE/test-pmos-pid1.sh" "$HERE/pmos-pid1-guard.sh" "$HERE/pmos-pid1-ack.sh" \
	"$HERE/pmos-self-post.sh" "$HERE/pmos-root-contract.sh"; do
	[ -f "$host_file" ] && [ ! -L "$host_file" ] || fail "missing host fixture file $host_file"
	[ -r "$host_file" ] || fail "unreadable host fixture file $host_file"
done
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
for tool in sudo unshare mke2fs blkid python3; do command -v "$tool" >/dev/null 2>&1 || fail "missing $tool"; done
sudo -n true || fail 'passwordless sudo required'
for case in ack late stale timeout preplanted symlinked; do
	sudo -n /usr/bin/python3 -I - "$case" "$HERE" "$ARCHIVE" <<'PY' || fail "$case isolated switch_root fixture"
import errno
import fcntl
import os
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid

case, here, archive = sys.argv[1:]
if case not in ('ack', 'late', 'stale', 'timeout', 'preplanted', 'symlinked'):
    raise SystemExit('invalid case')
if os.geteuid() != 0 or not os.path.isabs(here):
    raise SystemExit('invalid fixture supervisor')

env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root'}
work = None
image_path = None
image = None
number = None
image_fd = None
loop_fd = None
control_fd = None
proc = None
loop_path = None
attached = False
uncertain = False
result = 1


def interrupted(signum, frame):
    raise InterruptedError('signal ' + str(signum))


for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, interrupted)

try:
    work = tempfile.mkdtemp(prefix='pmos-pid1.', dir='/tmp')
    image_path = os.path.join(work, 'userdata-' + case + '.img')
    directory = os.stat(work, follow_symlinks=False)
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != 0 or stat.S_IMODE(directory.st_mode) != 0o700:
        raise RuntimeError('invalid private workdir')
    image_fd = os.open(image_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    if image_fd == 9:
        image_fd = fcntl.fcntl(image_fd, fcntl.F_DUPFD_CLOEXEC, 10)
        os.close(9)
    image = os.fstat(image_fd)
    os.ftruncate(image_fd, 268435456)
    image = os.fstat(image_fd)
    if not stat.S_ISREG(image.st_mode) or image.st_uid != 0 or image.st_nlink != 1 or image.st_size != 268435456:
        raise RuntimeError('invalid fresh image')
    fs_uuid = str(uuid.uuid4())
    subprocess.run(['/usr/sbin/mke2fs', '-q', '-F', '-t', 'ext4', '-b', '4096', '-U', fs_uuid,
                    '/proc/self/fd/' + str(image_fd)], env=env, pass_fds=(image_fd,),
                   stdin=subprocess.DEVNULL, check=True, timeout=60)
    control_fd = os.open('/dev/loop-control', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    control = os.fstat(control_fd)
    if not stat.S_ISCHR(control.st_mode) or (os.major(control.st_rdev), os.minor(control.st_rdev)) != (10, 237):
        raise RuntimeError('invalid loop control')
    for attempt in range(100):
        number = fcntl.ioctl(control_fd, 0x4C82)
        if number < 0 or number > 1048575:
            raise RuntimeError('invalid loop number')
        loop_path = '/dev/loop' + str(number)
        loop_fd = os.open(loop_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        node = os.fstat(loop_fd)
        if not stat.S_ISBLK(node.st_mode) or (os.major(node.st_rdev), os.minor(node.st_rdev)) != (7, number):
            raise RuntimeError('loop node identity mismatch')
        info = bytearray(232)
        struct.pack_into('=I', info, 52, 4)
        config = struct.pack('=II', image_fd, 0) + info + bytes(64)
        try:
            uncertain = True
            fcntl.ioctl(loop_fd, 0x4C0A, config)
            attached = True
            uncertain = False
            break
        except OSError as exc:
            try:
                seen = struct.unpack('=QQQQQIIII64s64s32sQQ', fcntl.ioctl(loop_fd, 0x4C05, bytes(232)))
                seen_dev = ((seen[0] & 0xFFF00) >> 8, (seen[0] & 0xFF) | ((seen[0] >> 12) & 0xFFF00))
                if seen_dev != (os.major(image.st_dev), os.minor(image.st_dev)) or seen[1] != image.st_ino:
                    uncertain = False
            except OSError as probe_exc:
                if probe_exc.errno == errno.ENXIO:
                    uncertain = False
            if exc.errno != errno.EBUSY or uncertain:
                raise
            os.close(loop_fd)
            loop_fd = None
            time.sleep(0.05)
    if not attached:
        raise RuntimeError('no free loop device after bounded retries')
    os.close(control_fd)
    control_fd = None
    if loop_fd != 9:
        os.dup2(loop_fd, 9, inheritable=False)
        os.close(loop_fd)
        loop_fd = 9
    info = struct.unpack('=QQQQQIIII64s64s32sQQ', fcntl.ioctl(loop_fd, 0x4C05, bytes(232)))
    encoded_dev = info[0]
    backing_dev = ((encoded_dev & 0xFFF00) >> 8, (encoded_dev & 0xFF) | ((encoded_dev >> 12) & 0xFFF00))
    if (backing_dev != (os.major(image.st_dev), os.minor(image.st_dev)) or info[1] != image.st_ino
            or info[3] != 0 or info[4] != 0 or info[5] != number or info[6] != 0 or info[8] != 4):
        raise RuntimeError('loop backing identity mismatch')
    env.update(HOST_ARCHIVE=archive, HOST_SCRIPT=here + '/test-pmos-pid1.sh',
               HOST_MAIN_NUMS='7:' + str(number), HOST_FS_UUID=fs_uuid, HOST_WORK_IMAGE=image_path,
               HOST_GUARD=here + '/pmos-pid1-guard.sh', HOST_ACK=here + '/pmos-pid1-ack.sh',
               HOST_POST=here + '/pmos-self-post.sh', HOST_CONTRACT=here + '/pmos-root-contract.sh')
    proc = subprocess.Popen(['/usr/bin/unshare', '--mount', '--pid', '--net', '--fork',
                             '--kill-child=KILL', '--mount-proc', '/bin/busybox', 'sh',
                             here + '/test-pmos-pid1.sh', '--inner', case],
                            env=env, pass_fds=(loop_fd,), stdin=subprocess.DEVNULL, start_new_session=True)
    if proc.wait(timeout=900) != 0:
        raise RuntimeError('namespace child failed')
    result = 0
except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
    print('FAIL: ' + case + ': ' + str(exc), file=sys.stderr)
finally:
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print('FAIL: child termination unconfirmed: ' + str(exc), file=sys.stderr)
            uncertain = True
    if control_fd is not None:
        os.close(control_fd)
    if loop_fd is not None:
        os.close(loop_fd)
    detached = not attached and not uncertain
    if attached and not uncertain:
        for attempt in range(30):
            try:
                probe = os.open(loop_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
                try:
                    node = os.fstat(probe)
                    if not stat.S_ISBLK(node.st_mode) or (os.major(node.st_rdev), os.minor(node.st_rdev)) != (7, number):
                        break
                    try:
                        seen = struct.unpack('=QQQQQIIII64s64s32sQQ', fcntl.ioctl(probe, 0x4C05, bytes(232)))
                    except OSError as exc:
                        if exc.errno == errno.ENXIO:
                            detached = True
                            break
                        raise
                    seen_dev = ((seen[0] & 0xFFF00) >> 8, (seen[0] & 0xFF) | ((seen[0] >> 12) & 0xFFF00))
                    if seen_dev != (os.major(image.st_dev), os.minor(image.st_dev)) or seen[1] != image.st_ino:
                        detached = True
                        break
                    if attempt == 5:
                        fcntl.ioctl(probe, 0x4C01)
                finally:
                    os.close(probe)
            except OSError:
                break
            time.sleep(0.1)
    if image_fd is not None:
        os.close(image_fd)
    if detached:
        try:
            if os.path.lexists(image_path):
                current = os.stat(image_path, follow_symlinks=False)
                if image is None or (current.st_dev, current.st_ino) != (image.st_dev, image.st_ino):
                    raise RuntimeError('image path changed')
                os.unlink(image_path)
            os.rmdir(work)
        except (OSError, RuntimeError) as exc:
            print('FAIL: cleanup: ' + str(exc), file=sys.stderr)
            result = 1
    else:
        print('FAIL: loop detach unconfirmed; preserving ' + work, file=sys.stderr)
        result = 1
sys.exit(result)
PY
done
