#!/bin/sh
set -eu

BB=/bin/busybox
PIN=7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26
MOCK_SHA=e112e65f2e9a6dc28531b45eda218284e4afb152dc3a02b588f7a25255cce2d1
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { $BB sha256sum "$1" | $BB cut -d ' ' -f 1; }
mounted() {
	$BB awk -v path="$1" -v type="$2" '$2 == path {n++; if ($3 != type) bad++} END {exit(n != 1 || bad)}' /proc/mounts
}
separate() {
	$BB awk -v a="$1" -v b="$2" '$5 == a {left = $3; na++} $5 == b {right = $3; nb++} END {exit(na != 1 || nb != 1 || left == right)}' /proc/self/mountinfo
}
valid_root() {
	[ -d "$1" ] && [ ! -L "$1" ] && mounted "$1" tmpfs &&
		[ -f "$1/bin/busybox" ] && [ ! -L "$1/bin/busybox" ] &&
		[ "$(hash "$1/bin/busybox")" = "$NATIVE_SHA" ] &&
		[ -f "$1/pid1-test.sh" ] && [ "$(hash "$1/pid1-test.sh")" = "$SCRIPT_SHA" ] &&
		[ -f "$1/usr/lib/os-release" ] &&
		$BB grep -q 'ID="postmarketos"' "$1/usr/lib/os-release" &&
		[ -x "$1/usr/bin/qemu-aarch64" ] &&
		[ ! -L "$1/dev" ] && [ ! -L "$1/dev/pts" ] &&
		[ ! -L "$1/proc" ] && [ ! -L "$1/sys" ] && [ ! -L "$1/run" ] &&
		mounted "$1/dev" tmpfs && mounted "$1/dev/pts" devpts &&
		mounted "$1/proc" proc && mounted "$1/sys" sysfs && mounted "$1/run" tmpfs &&
		separate "$1/dev" /dev && separate "$1/dev" "$1" &&
		separate "$1/run" "$1" && separate "$1/run" "$1/dev" &&
		$BB awk -v root="$1" '
			$2 == root || index($2, root "/") == 1 {
				if ($2 != root && $2 != root "/dev" && $2 != root "/dev/pts" &&
				    $2 != root "/proc" && $2 != root "/sys" && $2 != root "/run") bad++
			}
			END {exit(bad != 0)}' /proc/mounts
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
	case "$2" in ack|timeout|preplanted|symlinked) :;; *) fail 'invalid client case';; esac
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
		'test "$(id -u)" = 0 && test ! -t 0 && test "$(cat /run/dropbear-session.pid)" = '"$server_pid"' && test "$(cat /etc/alpine-release)" = 3.21.9 && grep -q '\''ID="postmarketos"'\'' /etc/os-release && test "$(cat /proc/1/comm)" = busybox && test "$(/bin/busybox sha256sum /proc/1/exe | /bin/busybox cut -d " " -f 1)" = "$(/bin/busybox sha256sum /bin/busybox | /bin/busybox cut -d " " -f 1)" && test "$(cat /run/openrc/softlevel)" = default && /sbin/rc-service local status >/dev/null && test "$(/bin/rc-status --crashed)" = "" && test -c /dev/tty && test -c /dev/pts/ptmx && /bin/busybox awk '\''$2 == "/" && $3 == "tmpfs" {n++} END {exit(n != 1)}'\'' /proc/1/mounts && /usr/bin/qemu-aarch64 -0 sh /bin/distro-busybox -c '\''test "$(/bin/busybox id -u)" = 0 && test "$(/bin/busybox cat /etc/alpine-release)" = 3.21.9'\'' && printf "pmos-pid1-host-ok\n"') || fail 'strict key-only SSH, switched root, OpenRC local or distro BusyBox smoke'
	[ "$identity" = pmos-pid1-host-ok ] || fail 'post-cutover distro identity'
	[ "$before" = "$(service_state /proc/1/root/.)" ] || fail 'post-cutover service restarted after SSH'
	case "$2" in
		ack)
			[ ! -e /proc/1/root/run/pid1-guard/ack ] && [ ! -L /proc/1/root/run/pid1-guard/ack ] || fail 'unauthenticated ack accepted'
			sh "$HOST_ACK" "$BOOT_ID" /run/bad-known_hosts /run/client_key >/dev/null 2>&1 && fail 'ack accepted wrong host key'
			sh "$HOST_ACK" "$BOOT_ID" /run/known_hosts /run/bad_key >/dev/null 2>&1 && fail 'ack accepted wrong client key'
			sh "$HOST_ACK" 00000000-0000-0000-0000-000000000000 /run/known_hosts /run/client_key >/dev/null 2>&1 && fail 'ack accepted wrong boot ID'
			sh "$HOST_ACK" "$BOOT_ID" /run/known_hosts /run/client_key || fail 'actual ack script failed'
			[ "$(ssh_guest client_key known_hosts 'cat /run/pid1-guard/accepted')" = "$BOOT_ID" ] || fail 'ack not accepted'
			[ ! -e /proc/1/root/run/pid1-guard/recovery-request ] || fail 'ack triggered recovery'
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
	if [ "$2" != ack ]; then
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
	mounted / tmpfs && mounted /dev tmpfs && mounted /dev/pts devpts && mounted /proc proc && mounted /sys sysfs && mounted /run tmpfs && separate /run /dev && separate /run / || fail 'switch_root lost private guest mounts'
	[ ! -e /oldroot ] && [ ! -e /guest ] && [ -f /pid1-test.sh ] && [ "$(hash /pid1-test.sh)" = "$SCRIPT_SHA" ] || fail 'old root retained or switched script invalid'
	[ "$(hash /bin/busybox)" = "$NATIVE_SHA" ] && [ "$(hash /bin/distro-busybox)" = "$DISTRO_SHA" ] || fail 'native or distro BusyBox changed'
	[ -c /dev/null ] && [ -c /dev/tty ] && [ "$($BB readlink /dev/ptmx)" = pts/ptmx ] || fail 'guest devices invalid'
	[ ! -e /run/openrc/softlevel ] && [ "$($BB readlink /etc/runlevels/default/local)" = /etc/init.d/local ] || fail 'unexpected OpenRC state before cutover runlevels'
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
	printf 'pass: %s; real BusyBox PID 1 switch_root to synthetic tmpfs with surviving pre-cutover QEMU Dropbear PID, root, socket and pinned key, strict key-only SSH before/after, actual ack script and real guard with digest-pinned isolated mock recovery; no device recovery\n' "$CASE"
	exit 0
fi

if [ "${1:-}" = --inner ]; then
	[ "$#" -eq 2 ] && [ "$$" = 1 ] || fail 'fixture did not enter a PID namespace'
	CASE=$2
	case "$CASE" in ack|timeout|preplanted|symlinked) :;; *) fail 'invalid case';; esac
	export CASE
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
	$BB mount -t tmpfs -o mode=0755,size=512m tmpfs "$ROOT/guest" || fail 'postmarketOS root tmpfs'
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
	$BB mount -t sysfs -o nosuid,nodev,noexec sysfs "$ROOT/sys" || fail 'initial sysfs'
	$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$ROOT/dev" || fail 'initial dev'
	$BB mount -t proc -o nosuid,nodev,noexec proc "$ROOT/guest/proc" || fail 'guest proc'
	$BB mount -t sysfs -o nosuid,nodev,noexec sysfs "$ROOT/guest/sys" || fail 'guest sysfs'
	$BB mount -t tmpfs -o mode=0755,size=1m tmpfs "$ROOT/guest/dev" || fail 'guest dev'
	$BB mkdir "$ROOT/guest/dev/pts"
	$BB mount -t devpts -o newinstance,ptmxmode=0666 devpts "$ROOT/guest/dev/pts" || fail 'guest devpts'
	make_nodes "$ROOT/dev"
	make_nodes "$ROOT/guest/dev"
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
	[ "$$" = 1 ] && mounted / tmpfs && mounted /guest tmpfs || fail 'initial root not pivoted'
	$BB cat > /guest/run/mock <<'MOCK'
#!/bin/busybox sh
set -eu
b=/bin/busybox
s=/run/pid1-guard
[ "$#" -eq 1 ] && [ "$1" = bootloader ] || exit 2
$b awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/mounts || exit 2
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
	if [ "$CASE" = ack ]; then budget=50; else budget=12; fi
	$BB sh /oldroot"$HOST_GUARD" mock-arm /guest "$budget" /guest/run/mock "$MOCK_SHA" >/guest/run/mock-guard.log 2>&1 || fail 'real guard mock-arm failed'
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
sudo -n true || fail 'passwordless sudo required'
for case in ack timeout preplanted symlinked; do
	sudo -n unshare --mount --pid --net --fork --kill-child --mount-proc \
		env HOST_ARCHIVE="$ARCHIVE" HOST_SCRIPT="$HERE/test-pmos-pid1.sh" \
		HOST_GUARD="$HERE/pmos-pid1-guard.sh" HOST_ACK="$HERE/pmos-pid1-ack.sh" \
		/bin/busybox sh "$HERE/test-pmos-pid1.sh" --inner "$case" || fail "$case isolated switch_root fixture"
done
