#!/bin/sh
set -eu

BB=/bin/busybox
MOCK_SHA=e112e65f2e9a6dc28531b45eda218284e4afb152dc3a02b588f7a25255cce2d1
GUARD_SHA=f72a68a4c3a0e9bb7e72aa88883dcc9087a684985f5af688e34ea13c0226d3ad
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { "$BB" sha256sum "$1" | "$BB" cut -d ' ' -f 1; }

if [ "${1:-}" = --switched ]; then
	[ "$#" = 2 ] && [ "$$" = 1 ] || fail 'switched process is not PID 1'
	case "$2" in success|partial|invalid|interrupt|post-interrupt|dead-watcher|replay|late) CASE=$2;; *) fail 'invalid case';; esac
	umask 077
	for ns in mnt pid net; do
		eval "host_ns=\${HOST_${ns}_NS:-}"
		[ -n "$host_ns" ] && [ "$("$BB" readlink "/proc/1/ns/$ns")" != "$host_ns" ] || fail "$ns namespace not isolated after switch_root"
	done
	"$BB" awk -F: 'NR > 2 {gsub(/[ \t]/, "", $1); if ($1 != "lo") bad++; else n++} END {exit(bad || n != 1)}' /proc/net/dev || fail 'switched network namespace has unexpected interfaces'
	[ "$(hash /proc/1/exe)" = "$(hash /bin/busybox)" ] || fail 'PID 1 executable differs from real BusyBox'
	[ "$("$BB" stat -c '%d:%i' /)" = "$("$BB" stat -Lc '%d:%i' /proc/1/root)" ] || fail 'PID 1 root differs'
	"$BB" awk '$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts || fail 'root is not tmpfs'
	"$BB" awk '$2 == "/run" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts || fail 'run is not tmpfs'
	[ "$(hash /run/pid1-guard/guard.sh)" = "$GUARD_SHA" ] && [ "$(hash /run/pid1-guard/mock-restart2)" = "$MOCK_SHA" ] || fail 'guard or recovery helper changed'
	[ ! -e /bin/restart2 ] && [ ! -L /bin/restart2 ] || fail 'real recovery helper present'
	boot=$("$BB" cat /proc/sys/kernel/random/boot_id)
	deadline_reached() {
		now=$("$BB" awk '{print int($1)}' /proc/uptime)
		[ "$now" -ge "$((TEST_ARM_UPTIME + TEST_BUDGET))" ] || fail 'guard requested recovery before its real deadline'
	}
	i=0
	until [ -f /run/pid1-guard/nonce ]; do
		[ "$i" -lt 100 ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'guard did not issue nonce after switch_root'
		"$BB" sleep 0.1
		i=$((i + 1))
	done
	nonce=$("$BB" cat /run/pid1-guard/nonce)
	[ "${#nonce}" = 64 ] || fail 'guard nonce invalid'
	case "$CASE" in
		dead-watcher|post-interrupt)
			[ "$(hash /pidfd-signal)" = "$HOST_PIDFD_SHA" ] || fail 'pidfd helper changed'
			"$BB" printf '/bin/busybox\000sh\000/run/pid1-guard/guard.sh\000watch\000mock\000%s\000%s\000' "$TEST_BUDGET" "$MOCK_SHA" > /run/watch-command
			find_watch() {
				found=
				for proc in /proc/[0-9]*; do
					[ -r "$proc/cmdline" ] || continue
					"$BB" cmp -s "$proc/cmdline" /run/watch-command || continue
					candidate=${proc#/proc/}
					case "$candidate" in ''|*[!0-9]*|1) fail 'invalid watch PID';; esac
					[ -z "$found" ] || fail 'multiple matching watch processes'
					[ "$(hash "$proc/exe")" = "$(hash /bin/busybox)" ] &&
						[ "$("$BB" stat -Lc '%d:%i' "$proc/root")" = "$("$BB" stat -c '%d:%i' /)" ] || fail 'watch executable or root differs'
					for ns in mnt pid net; do
						[ "$("$BB" readlink "$proc/ns/$ns")" = "$("$BB" readlink "/proc/1/ns/$ns")" ] || fail "watch $ns namespace differs"
					done
					proc_id=$("$BB" awk '{print $1 ":" $6 ":" $22}' "$proc/stat")
					case "$proc_id" in "$candidate:$candidate:"*) :;; *) fail 'watch is not the isolated setsid session leader';; esac
					found=$candidate
				done
				[ -n "$found" ] || fail 'fixture watch process missing'
				watch_pid=$found
				watch_id=$proc_id
			}
			signal_watch() {
				find_watch
				[ "$watch_pid" = "$expected_watch_pid" ] && [ "$watch_id" = "$expected_watch_id" ] || fail 'watch identity changed before signal'
				/pidfd-signal "$watch_pid" "$watch_id" "$1" || fail 'pidfd watch signal rejected'
			}
			[ "$("$BB" cat /run/pid1-guard/armed)" = "$boot" ] && [ ! -e /run/pid1-guard/ack ] && [ ! -e /run/pid1-guard/accepted ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'watch not armed and unacknowledged'
			find_watch
			[ "$watch_id" = "$("$BB" cat /run/arm-watch-id)" ] || fail 'watch differs from the one observed immediately after mock-arm'
			expected_watch_pid=$watch_pid
			expected_watch_id=$watch_id;;
	esac
	if [ "$CASE" = dead-watcher ]; then
		now=$("$BB" awk '{print int($1)}' /proc/uptime)
		[ "$now" -lt "$((TEST_ARM_UPTIME + TEST_BUDGET))" ] || fail 'watch was not killed before its earliest possible deadline'
		signal_watch KILL
		i=0
		while "$BB" cmp -s "/proc/$expected_watch_pid/cmdline" /run/watch-command 2>/dev/null; do
			[ "$i" -lt 50 ] || fail 'watch survived pidfd SIGKILL'
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		killed_at=$("$BB" awk '{print int($1)}' /proc/uptime)
		"$BB" sleep "$((TEST_BUDGET + 2))"
		now=$("$BB" awk '{print int($1)}' /proc/uptime)
		[ "$now" -ge "$((killed_at + TEST_BUDGET))" ] || fail 'dead-watcher observation shorter than its budget'
		deadline_reached
		[ ! -e /run/pid1-guard/recovery-request ] && [ ! -e /run/pid1-guard/accepted ] && [ ! -e /run/pid1-guard/ack ] && [ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail 'dead-watcher state changed'
		for proc in /proc/[0-9]*; do
			if "$BB" cmp -s "$proc/cmdline" /run/watch-command 2>/dev/null; then fail 'watch process survived or was restarted'; fi
		done
		printf 'pass: dead-watcher: exact isolated watch killed; no acceptance or mock bootloader request beyond its budget\n'
		exit 0
	fi
	if [ "$CASE" = post-interrupt ]; then
		signal_watch STOP
		i=0
		until [ "$("$BB" awk '{print $3}' "/proc/$expected_watch_pid/stat" 2>/dev/null)" = T ]; do
			[ "$i" -lt 50 ] || fail 'watch did not stop'
			"$BB" sleep 0.1
			i=$((i + 1))
		done
	fi
	"$BB" mkdir -m 700 /run/radio-bringup
	"$BB" mkdir -p /run/openrc /sys/class/remoteproc/remoteproc2 /sys/class/remoteproc/remoteproc3 \
		/sys/class/net/wlan0 /sys/class/ieee80211/phy0 /sys/module/qca_cld3_qca6750 /sys/class/uio/uio0 \
		/etc/init.d /etc/conf.d /etc/network /etc/wpa_supplicant /etc/runlevels/sysinit \
		/etc/runlevels/boot /etc/runlevels/default /etc/runlevels/nonetwork /etc/runlevels/shutdown
	"$BB" printf '%s\n' 4080000.remoteproc-mss > /sys/class/remoteproc/remoteproc2/name
	"$BB" printf '%s\n' 9bb00000.remoteproc-wpss > /sys/class/remoteproc/remoteproc3/name
	"$BB" printf '%s\n' running > /sys/class/remoteproc/remoteproc2/state
	"$BB" printf '%s\n' running > /sys/class/remoteproc/remoteproc3/state
	"$BB" printf '%s\n' rmtfs > /sys/class/uio/uio0/name
	"$BB" printf '%s\n' default > /run/openrc/softlevel
	"$BB" sleep 120 &
	rmtfs=$!
	"$BB" printf '%s\n' "$rmtfs" > /run/radio-bringup/rmtfs.pid
	"$BB" sh -c 'while :; do /bin/busybox sleep 1; done' 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' &
	dropbear=$!
	"$BB" printf '%s\n' "$dropbear" > /run/dropbear-session.pid
	for stage in modem wpss driver scan services; do
		token="guest-radio-$stage-$("$BB" printf '%s' "$boot:$nonce:$stage" | "$BB" sha256sum | "$BB" cut -c 1-16)"
		"$BB" printf '%s\n' "$token" > "/run/radio-bringup/$stage.marker"
	done
	"$BB" printf '%s\n' synthetic-profile > /run/radio-bringup/wpa_supplicant.conf
	"$BB" cp /run/radio-bringup/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf
	"$BB" printf 'auto wlan0\niface wlan0 inet dhcp\n\tdhcp-script /run/radio-bringup/lease-wrapper.sh\n\tudhcpc-opts -t 5 -T 3 -A 5 -n\n' > /etc/network/interfaces
	"$BB" printf '%s\n' 'ifquery=/run/radio-bringup/ifquery-wlan' > /etc/conf.d/networking
	"$BB" printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan0"\n' > /etc/conf.d/wpa_supplicant
	"$BB" printf '%s\n' 'nameserver 192.0.2.53' > /etc/resolv.conf
	"$BB" cat > /run/radio-bringup/lease-wrapper.sh <<'WRAPPER'
#!/bin/busybox sh
IP_CMD=/sbin/ip
export IP_CMD
exec /bin/busybox sh /run/radio-bringup/wlan-udhcpc-lease.sh "$@"
WRAPPER
	"$BB" cat > /run/radio-bringup/ifquery-wlan <<'IFQUERY'
#!/bin/busybox sh
if [ "$#" = 4 ] && [ "$1" = -i ] && [ "$2" = /etc/network/interfaces ] && [ "$3" = --list ] && [ "$4" = -a ]; then /bin/busybox printf "wlan0\n"; exit 0; fi
exec /sbin/ifquery "$@"
IFQUERY
	"$BB" printf '%s\n' fixture > /run/radio-bringup/wlan-udhcpc-lease.sh
	for service in local networking wpa_supplicant; do
		"$BB" printf '%s\n' fixture > "/etc/init.d/$service"
		"$BB" ln -s "/etc/init.d/$service" "/etc/runlevels/default/$service"
	done
	"$BB" chmod 600 /run/radio-bringup/rmtfs.pid /run/radio-bringup/*.marker \
		/run/radio-bringup/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf \
		/etc/network/interfaces /etc/conf.d/networking /etc/conf.d/wpa_supplicant
	"$BB" chmod 700 /run/radio-bringup/lease-wrapper.sh /run/radio-bringup/ifquery-wlan /run/radio-bringup/wlan-udhcpc-lease.sh
	[ "$CASE" != partial ] || "$BB" rm /run/radio-bringup/scan.marker
	"$BB" printf '%s\n' "$CASE" > /run/case

	if [ "$CASE" = replay ]; then
		old=$("$BB" cat /replay-nonce)
		[ "${#old}" = 64 ] && [ "$old" != "$nonce" ] || fail 'fresh guard nonce did not differ from captured nonce'
		"$BB" printf '%s %s\n' "$old" "$boot" > /run/pid1-guard/ack
		"$BB" chmod 600 /run/pid1-guard/ack
	fi
	if [ "$CASE" = late ] || [ "$CASE" = replay ]; then
		i=0
		until [ -f /run/pid1-guard/recovery-request ]; do
			[ "$i" -lt 200 ] || fail 'guard did not reach its real deadline'
			[ ! -e /run/pid1-guard/accepted ] || fail 'guard accepted replay or no ACK'
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] || fail 'mock recovery is not bootloader'
		deadline_reached
		[ ! -e /run/pid1-guard/accepted ] || fail 'guard accepted replay or no ACK'
	fi
	if [ "$CASE" = replay ]; then
		[ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail 'replay consumed nonce'
		[ "$("$BB" cat /run/pid1-guard/ack)" = "$old $boot" ] || fail 'replay ACK changed'
		printf 'pass: replay: earlier accepted nonce rejected by a fresh real guard through its deadline\n'
		exit 0
	fi
	"$BB" sh /gate-runner > /run/gate.log 2>&1 &
	gate=$!
	if [ "$CASE" = interrupt ]; then
		i=0
		until [ -f /run/iw-waiting ]; do
			[ "$i" -lt 100 ] && "$BB" kill -0 "$gate" 2>/dev/null || { "$BB" cat /run/gate.log >&2; fail 'gate did not reach interruption barrier'; }
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		[ ! -e /run/pid1-guard/ack ] && [ ! -e /run/pid1-guard/.success-gated-ack-new ] || fail 'gate published before interruption'
		"$BB" kill -TERM "$gate"
		"$BB" touch /run/iw-release
	fi
	if [ "$CASE" = post-interrupt ]; then
		i=0
		until [ -f /run/publication-barrier ]; do
			[ "$i" -lt 100 ] && "$BB" kill -0 "$gate" 2>/dev/null || { "$BB" cat /run/gate.log >&2; fail 'gate did not reach single-link publication barrier'; }
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		[ "$("$BB" awk '{print $3}' "/proc/$expected_watch_pid/stat")" = T ] || fail 'watch unexpectedly resumed before interruption'
		[ -f /run/pid1-guard/ack ] && [ ! -L /run/pid1-guard/ack ] &&
			[ "$("$BB" stat -c '%u:%a:%h:%s' /run/pid1-guard/ack)" = "0:600:1:$((${#nonce} + ${#boot} + 2))" ] &&
			[ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] &&
			[ ! -e /run/pid1-guard/.success-gated-ack-new ] && [ ! -e /run/pid1-guard/accepted ] &&
			[ ! -e /run/pid1-guard/recovery-request ] || fail 'ACK not valid single-link and unconsumed at barrier'
		"$BB" kill -TERM "$gate"
		"$BB" touch /run/publication-release
	fi
	if wait "$gate"; then result=0; else result=$?; fi
	if [ "$CASE" = post-interrupt ]; then
		[ "$("$BB" wc -l < /run/kmsg-requests)" = 3 ] || fail 'post-interrupt gate did not take three bounded snapshots'
		[ "$result" != 0 ] || fail 'post-publication interrupted gate succeeded'
		"$BB" grep -F 'stage=ack-publication result=refused-or-interrupted phase=published-awaiting-guard reason=signal-TERM' /run/radio-bringup/success-gate-294/refusal >/dev/null || { "$BB" cat /run/gate.log /run/radio-bringup/success-gate-294/refusal >&2; fail 'post-publication interruption phase'; }
		[ -f /run/pid1-guard/ack ] && [ "$("$BB" stat -c '%u:%a:%h:%s' /run/pid1-guard/ack)" = "0:600:1:$((${#nonce} + ${#boot} + 2))" ] && [ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] && [ ! -e /run/pid1-guard/accepted ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'interrupted publisher did not leave a valid unconsumed ACK'
		signal_watch CONT
		i=0
		until [ -f /run/pid1-guard/accepted ] && [ ! -e /run/pid1-guard/nonce ] && [ ! -e /run/pid1-guard/ack ]; do
			[ "$i" -lt 100 ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'resumed real guard did not accept interrupted publication'
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		[ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] && [ ! -e /run/radio-bringup/success-gate-294/accepted.ok ] || fail 'post-interruption acceptance evidence changed'
		"$BB" sleep "$((TEST_BUDGET + 2))"
		[ ! -e /run/pid1-guard/recovery-request ] && [ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] || fail 'post-interruption guard acceptance did not survive budget'
		printf 'pass: post-interrupt: gate recorded published-awaiting-guard interruption; resumed real guard accepted the single-link ACK\n'
		exit 0
	fi
	if [ "$CASE" = success ]; then
		[ "$result" = 0 ] || { "$BB" cat /run/gate.log >&2; fail 'generated gate failed'; }
		[ "$("$BB" wc -l < /run/kmsg-requests)" = 3 ] && [ ! -e /run/radio-bringup/success-gate-294/kmsg ] || fail 'three bounded snapshots were not completed and removed'
		for stage in nonce-and-radio-markers radio-health services association address route gateway internet dns final-health all-checks published accepted; do
			[ -f "/run/radio-bringup/success-gate-294/$stage.ok" ] || fail "missing success evidence: $stage"
		done
		[ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] && [ ! -e /run/pid1-guard/nonce ] && [ ! -e /run/pid1-guard/ack ] || fail 'guard did not consume nonce and ACK'
		[ ! -e /run/pid1-guard/.success-gated-ack-new ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'success left staging or requested recovery'
		if "$BB" sh /gate-runner > /run/retry.log 2>&1; then fail 'one-shot gate accepted a second invocation'; fi
		[ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] && [ ! -e /run/pid1-guard/nonce ] && [ ! -e /run/pid1-guard/ack ] || fail 're-invocation changed accepted state'
		"$BB" sleep "$((TEST_BUDGET + 2))"
		[ ! -e /run/pid1-guard/recovery-request ] || fail 'accepted guard requested recovery after deadline'
		printf 'REPLAY_NONCE=%s\n' "$nonce"
		printf 'pass: success: generated gate published; real guard accepted and consumed nonce and ACK; one-shot retry refused\n'
		exit 0
	fi
	[ "$result" != 0 ] || fail "$CASE gate unexpectedly succeeded"
	case "$CASE" in
		partial) reason='stage=nonce-and-radio-markers result=refused-or-interrupted phase=before-publication reason=invalid scan capture marker';;
		invalid) reason='stage=dns result=refused-or-interrupted phase=before-publication reason=invalid DNS answer';;
		interrupt) reason='stage=association result=refused-or-interrupted phase=before-publication reason=signal-TERM';;
		late) reason='stage=guard-acceptance result=refused-or-interrupted phase=published-awaiting-guard reason=acceptance not confirmed; ACK may still be consumed';;
	esac
	"$BB" grep -F "$reason" /run/radio-bringup/success-gate-294/refusal >/dev/null || { "$BB" cat /run/gate.log /run/radio-bringup/success-gate-294/refusal >&2; fail "$CASE refusal reason"; }
	if [ "$CASE" != late ]; then
		[ ! -e /run/pid1-guard/ack ] && [ ! -e /run/pid1-guard/.success-gated-ack-new ] && [ ! -e /run/radio-bringup/success-gate-294/published.ok ] || fail "$CASE published an ACK"
		[ ! -e /run/pid1-guard/recovery-request ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE gate did not refuse before the independent deadline"
	fi
	i=0
	until [ -f /run/pid1-guard/recovery-request ]; do
		[ "$i" -lt 200 ] || fail "$CASE guard did not independently request recovery"
		[ ! -e /run/pid1-guard/accepted ] || fail "$CASE guard accepted"
		"$BB" sleep 0.1
		i=$((i + 1))
	done
	[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] && [ ! -e /run/pid1-guard/accepted ] && [ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail "$CASE recovery or nonce invalid"
	deadline_reached
	if [ "$CASE" = late ]; then
		[ -f /run/radio-bringup/success-gate-294/published.ok ] && [ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] || fail 'late gate did not expose post-deadline publication'
	fi
	printf 'pass: %s: gate refused or was interrupted; real guard requested mock bootloader and did not accept\n' "$CASE"
	exit 0
fi

if [ "${1:-}" = --inner ]; then
	[ "$#" = 2 ] && [ "$$" = 1 ] && [ "$("$BB" id -u)" = 0 ] || fail 'not isolated root PID 1'
	for ns in mnt pid net; do
		eval "host_ns=\${HOST_${ns}_NS:-}"
		[ -n "$host_ns" ] && [ "$("$BB" readlink "/proc/1/ns/$ns")" != "$host_ns" ] || fail "$ns namespace not isolated"
	done
	"$BB" awk -F: 'NR > 2 {gsub(/[ \t]/, "", $1); if ($1 != "lo") bad++; else n++} END {exit(bad || n != 1)}' /proc/net/dev || fail 'network namespace has unexpected interfaces'
	case "$2" in success|partial|invalid|interrupt|post-interrupt|dead-watcher|replay|late) CASE=$2;; *) fail 'invalid case';; esac
	"$BB" mount --make-rprivate / || fail 'cannot privatize mounts'
	"$BB" mount -t tmpfs -o mode=0700,size=32m tmpfs /run || fail 'private staging run'
	"$BB" cp "$HOST_WORK/gate" /run/gate
	"$BB" cp "$HOST_WORK/radio" /run/radio
	"$BB" cp "$HOST_WORK/replay-nonce" /run/replay-nonce
	case "$CASE" in
		dead-watcher|post-interrupt)
			"$BB" cp "$HOST_WORK/pidfd-signal" /run/pidfd-signal
			[ "$(hash /run/pidfd-signal)" = "$HOST_PIDFD_SHA" ] || fail 'pidfd helper copy changed';;
	esac
	"$BB" cp "$HOST_SCRIPT" /run/test.sh
	"$BB" cp "$HOST_GUARD" /run/guard.sh
	[ "$(hash /run/guard.sh)" = "$GUARD_SHA" ] || fail 'guard pin changed'
	"$BB" mount -t tmpfs -o mode=0700,size=64m tmpfs /tmp || fail 'private staging tmp'
	"$BB" mkdir /tmp/initial
	"$BB" mount -t tmpfs -o mode=0755,size=32m tmpfs /tmp/initial || fail 'initial tmpfs'
	R=/tmp/initial
	"$BB" mkdir -p "$R/bin" "$R/oldroot" "$R/guest" "$R/proc" "$R/dev"
	"$BB" cp /bin/busybox "$R/bin/busybox"
	"$BB" cp /run/guard.sh "$R/guard.sh"
	"$BB" touch "$R/init"
	"$BB" mount -t proc -o nosuid,nodev,noexec proc "$R/proc" || fail 'initial proc'
	"$BB" mount -t tmpfs -o mode=0755,size=32m tmpfs "$R/guest" || fail 'guest tmpfs'
	G=$R/guest
	"$BB" mkdir -p "$G/bin" "$G/proc" "$G/dev" "$G/run" "$G/sys" "$G/sbin" "$G/usr/sbin" "$G/usr/libexec/omnipha"
	"$BB" mount -t tmpfs -o mode=0700,size=16m tmpfs "$G/run" || fail 'private guest run'
	"$BB" mount -t proc -o nosuid,nodev,noexec proc "$G/proc" || fail 'guest proc'
	"$BB" mount -t tmpfs -o mode=0755,size=1m tmpfs "$G/dev" || fail 'private guest dev'
	"$BB" mknod -m 666 "$G/dev/null" c 1 3
	"$BB" mknod -m 666 "$G/dev/urandom" c 1 9
	"$BB" touch "$G/dev/kmsg"
	"$BB" cp /bin/busybox "$G/bin/busybox"
	"$BB" cp /run/test.sh "$G/test.sh"
	"$BB" cp /run/replay-nonce "$G/replay-nonce"
	case "$CASE" in
		dead-watcher|post-interrupt)
			"$BB" cp /run/pidfd-signal "$G/pidfd-signal"
			"$BB" chmod 700 "$G/pidfd-signal"
			[ "$(hash "$G/pidfd-signal")" = "$HOST_PIDFD_SHA" ] || fail 'guest pidfd helper changed';;
	esac
	"$BB" cp /run/radio "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
	"$BB" chmod 700 "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
	"$BB" cat > "$G/run/mock" <<'MOCK'
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
	"$BB" chmod 700 "$G/run/mock"
	[ "$(hash "$G/run/mock")" = "$MOCK_SHA" ] || fail 'recovery mock digest changed'
	"$BB" cat > "$G/run/tool" <<'TOOL'
#!/bin/busybox sh
b=/bin/busybox
case "${1:-}" in
	dmesg)
		[ "$#" = 4 ] && [ "$2" = -r ] && [ "$3" = -s ] && [ "$4" = 2097152 ] || exit 1
		$b printf '%s\n' "$*" >> /run/kmsg-requests
		for marker in /run/radio-bringup/*.marker; do
			[ -f "$marker" ] || continue
			$b printf 'pmos-self-post: guest radio marker %s\n' "$("$b" cat "$marker")"
		done
		exit 0;;
	pidof) case "${2:-}" in pd-mapper|tqftpserv) exit 0;; esac; exit 1;;
	ping) case "$*" in 'ping -4 -I wlan0 -c 1 -W 4 -w 5 192.0.2.1'|'ping -4 -I wlan0 -c 1 -W 4 -w 5 1.1.1.1') exit 0;; esac; exit 1;;
	rm)
		if [ "$#" = 2 ] && [ "$2" = /run/pid1-guard/.success-gated-ack-new ] && [ "$($b cat /run/case)" = post-interrupt ]; then
			$b rm "$2" || exit 1
			$b touch /run/publication-barrier
			while [ ! -f /run/publication-release ]; do $b sleep 0.1; done
			exit 0
		fi;;
	cat)
		if [ "$#" = 2 ] && [ -f /run/radio-bringup/rmtfs.pid ] && [ "$2" = "/proc/$($b cat /run/radio-bringup/rmtfs.pid)/comm" ]; then
			$b printf '%s\n' rmtfs; exit 0
		fi;;
	grep)
		if [ "$#" = 4 ] && [ "$2" = -q ] && [ "$3" = /dev/uio0 ] && [ "$4" = "/proc/$($b cat /run/radio-bringup/rmtfs.pid)/maps" ]; then exit 0; fi;;
	awk)
		if [ "$#" = 3 ] && [ "$2" = '$2 == "022A10AC:08AE" && $4 == "0A" {n++} END {exit(n != 1)}' ] && [ "$3" = /proc/net/tcp ]; then exit 0; fi;;
	timeout)
		if [ "$#" = 6 ] && [ "$2" = -k ] && [ "$3" = 1 ] && [ "$4" = 6 ] && [ "$5" = /run/radio-bringup/success-gate-294/dns-probe ] && [ "$6" = 192.0.2.53 ]; then
			if [ "$($b cat /run/case)" = invalid ]; then $b printf '%s\n' 127.0.0.1; else $b printf '%s\n' 192.0.2.80; fi
			exit 0
		fi
		if [ "$#" = 8 ] && [ "$2" = -k ] && [ "$3" = 1 ] && [ "$4" = 5 ] && [ "$5" = /usr/sbin/iw ] && [ "$6" = dev ] && [ "$7" = wlan0 ] && [ "$8" = link ] && [ "$($b cat /run/case)" = interrupt ]; then
			$b touch /run/iw-waiting
			while [ ! -f /run/iw-release ]; do $b sleep 0.1; done
			$b printf '%s\n' 'Connected to 02:00:00:00:00:01 (on wlan0)'
			exit 0
		fi;;
esac
exec "$b" "$@"
TOOL
	"$BB" chmod 700 "$G/run/tool"
	"$BB" cat > "$G/sbin/rc-service" <<'RC'
#!/bin/busybox sh
[ "$#" = 2 ] && [ "$2" = status ] || exit 1
case "$1" in local|networking|wpa_supplicant) exit 0;; *) exit 1;; esac
RC
	"$BB" cat > "$G/usr/sbin/iw" <<'IW'
#!/bin/busybox sh
[ "$*" = 'dev wlan0 link' ] || exit 1
/bin/busybox printf '%s\n' 'Connected to 02:00:00:00:00:01 (on wlan0)'
IW
	"$BB" cat > "$G/sbin/ip" <<'IP'
#!/bin/busybox sh
case "$*" in
	'-o -4 addr show dev wlan0 scope global') /bin/busybox printf '%s\n' '3: wlan0 inet 192.0.2.2/24 scope global wlan0';;
	'-4 route show default') /bin/busybox printf '%s\n' 'default via 192.0.2.1 dev wlan0';;
	'-4 route get 1.1.1.1 from 192.0.2.2'|'-4 route get 192.0.2.53 from 192.0.2.2') /bin/busybox printf '%s\n' '192.0.2.1 dev wlan0 src 192.0.2.2';;
	*) exit 1;;
esac
IP
	"$BB" chmod 700 "$G/sbin/rc-service" "$G/usr/sbin/iw" "$G/sbin/ip"
	"$BB" cat > "$G/gate-runner" <<'PREAMBLE'
#!/bin/busybox sh
set -eu
BB=/run/tool
STATE=/run/radio-bringup
GUARD=/run/pid1-guard
RADIO=/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh
RADIO_SHA=a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21
PROFILE=$STATE/wpa_supplicant.conf
umask 077
boot=$(/bin/busybox cat /proc/sys/kernel/random/boot_id)
hash() {
	case "$1" in
		"/proc/$(/bin/busybox cat "$STATE/rmtfs.pid")/exe") /bin/busybox printf '%s\n' d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd;;
		/etc/init.d/networking) /bin/busybox printf '%s\n' 334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c;;
		/etc/init.d/wpa_supplicant) /bin/busybox printf '%s\n' a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f;;
		/run/radio-bringup/wlan-udhcpc-lease.sh) /bin/busybox printf '%s\n' 1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56;;
		*) /bin/busybox sha256sum "$1" | /bin/busybox cut -d ' ' -f 1;;
	esac
}
record_fail() { /bin/busybox printf '%s\n' "$*" > /run/record-fail; }
scrub() { /bin/busybox rm -f "$PROFILE"; }
PREAMBLE
	"$BB" cat /run/gate >> "$G/gate-runner"
	"$BB" chmod 700 "$G/gate-runner"
	"$BB" pivot_root "$R" "$R/oldroot" || fail 'pivot to isolated initial root'
	"$BB" umount -l /oldroot || fail 'cannot detach host root'
	case "$CASE" in success|post-interrupt) TEST_BUDGET=20;; dead-watcher) TEST_BUDGET=5;; *) TEST_BUDGET=12;; esac
	TEST_ARM_UPTIME=$("$BB" awk '{print int($1)}' /proc/uptime)
	export TEST_BUDGET TEST_ARM_UPTIME MOCK_SHA
	"$BB" sh /guard.sh mock-arm /guest "$TEST_BUDGET" /guest/run/mock "$MOCK_SHA" || fail 'real mock guard did not arm'
	[ "$(hash /guest/run/pid1-guard/guard.sh)" = "$GUARD_SHA" ] && [ ! -e /guest/run/pid1-guard/nonce ] || fail 'guard copy changed or minted before switch'
	case "$CASE" in
		dead-watcher|post-interrupt)
			"$BB" printf '/bin/busybox\000sh\000/run/pid1-guard/guard.sh\000watch\000mock\000%s\000%s\000' "$TEST_BUDGET" "$MOCK_SHA" > /guest/run/watch-command
			watch=
			for proc in /proc/[0-9]*; do
				"$BB" cmp -s "$proc/cmdline" /guest/run/watch-command 2>/dev/null || continue
				[ -z "$watch" ] || fail 'multiple watch processes at arm'
				watch=${proc#/proc/}
				done
			[ -n "$watch" ] || fail 'watch process missing at arm'
			"$BB" awk '{print $1 ":" $6 ":" $22}' "/proc/$watch/stat" > /guest/run/arm-watch-id;;
	esac
	exec /bin/busybox switch_root /guest /bin/busybox sh /test.sh --switched "$CASE"
fi

[ "$#" = 0 ] || fail 'usage: test-pmos-success-gate-guard.sh'
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=$HERE/test-pmos-success-gate-guard.sh
[ "$(hash "$HERE/pmos-pid1-guard.sh")" = "$GUARD_SHA" ] || fail 'guard pin changed'
[ "$("$BB" uname -m)" != aarch64 ] || fail 'guard mock requires a non-aarch64 host'
[ -f "$BB" ] && [ ! -L "$BB" ] || fail 'native BusyBox must be a regular executable'
for tool in python3 aarch64-linux-gnu-gcc cc sudo unshare timeout; do command -v "$tool" >/dev/null 2>&1 || fail "missing $tool"; done
sudo -n true || fail 'passwordless sudo required'
WORK=$(mktemp -d /tmp/pmos-success-gate.XXXXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
trap 'exit 1' HUP INT TERM
cc -static -O2 -Wall -Wextra -Werror -x c -o "$WORK/pidfd-signal" - <<'C'
#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

static void reject(const char *reason) {
    fprintf(stderr, "pidfd fixture: %s\n", reason);
    exit(1);
}

static int same_object(const char *left, const char *right) {
    struct stat a, b;
    return !stat(left, &a) && !stat(right, &b) && a.st_dev == b.st_dev && a.st_ino == b.st_ino;
}

int main(int argc, char **argv) {
    char *end, path[128], data[1024], expected[128], state;
    const char *budget = getenv("TEST_BUDGET"), *mock = getenv("MOCK_SHA");
    const char *names[] = {"mnt", "pid", "net"};
    const char *hosts[] = {getenv("HOST_mnt_NS"), getenv("HOST_pid_NS"), getenv("HOST_net_NS")};
    int sig, fd;
    long raw, parsed_pid, ppid, pgrp, sid;
    unsigned long long start;
    struct pollfd pollfd;
    FILE *file;
    size_t len, want, i;
    char *after;
    if (argc != 4 || getuid() != 0 || geteuid() != 0 || getppid() != 1 || !budget || !mock) reject("invalid caller");
    for (i = 0; budget[i]; i++) if (budget[i] < '0' || budget[i] > '9') reject("invalid budget");
    if (!i || strlen(mock) != 64) reject("invalid guard arguments");
    for (i = 0; i < 64; i++) if (!((mock[i] >= '0' && mock[i] <= '9') || (mock[i] >= 'a' && mock[i] <= 'f'))) reject("invalid mock digest");
    for (i = 0; i < 3; i++) {
        ssize_t n;
        if (!hosts[i] || !*hosts[i]) reject("missing host namespace identity");
        snprintf(path, sizeof path, "/proc/self/ns/%s", names[i]);
        n = readlink(path, data, sizeof data - 1);
        if (n < 0 || (size_t)n >= sizeof data - 1) reject("namespace identity unavailable");
        data[n] = 0;
        if (!strcmp(data, hosts[i])) reject("host namespace");
        snprintf(expected, sizeof expected, "/proc/1/ns/%s", names[i]);
        if (!same_object(path, expected)) reject("namespace differs from fixture PID 1");
    }
    errno = 0;
    raw = strtol(argv[1], &end, 10);
    if (errno || *end || raw <= 1 || raw > INT_MAX) reject("invalid PID");
    if (!strcmp(argv[3], "STOP")) sig = SIGSTOP;
    else if (!strcmp(argv[3], "CONT")) sig = SIGCONT;
    else if (!strcmp(argv[3], "KILL")) sig = SIGKILL;
    else reject("invalid signal");
    fd = (int)syscall(SYS_pidfd_open, (pid_t)raw, 0);
    if (fd < 0) reject("pidfd_open failed");
    pollfd.fd = fd;
    pollfd.events = POLLIN;
    pollfd.revents = 0;
    if (poll(&pollfd, 1, 0) != 0) reject("watch already exited");
    snprintf(path, sizeof path, "/proc/%ld/stat", raw);
    file = fopen(path, "r");
    if (!file || !fgets(data, sizeof data, file) || fclose(file)) reject("watch stat unavailable");
    after = strrchr(data, ')');
    if (!after || sscanf(data, "%ld", &parsed_pid) != 1 || parsed_pid != raw ||
        sscanf(after + 1, " %c %ld %ld %ld %*d %*d %*u %*u %*u %*u %*u %*u %*u %*d %*d %*d %*d %*d %*d %llu",
               &state, &ppid, &pgrp, &sid, &start) != 5) reject("watch stat malformed");
    if (ppid != 1 || pgrp != raw || sid != raw || (sig == SIGCONT ? state != 'T' : state == 'T' || state == 'Z')) reject("watch process state or session differs");
    snprintf(expected, sizeof expected, "%ld:%ld:%llu", raw, sid, start);
    if (strcmp(expected, argv[2])) reject("watch start identity changed");
    snprintf(path, sizeof path, "/proc/%ld/root", raw);
    if (!same_object(path, "/") || !same_object("/proc/1/root", "/")) reject("watch root differs");
    snprintf(path, sizeof path, "/proc/%ld/exe", raw);
    if (!same_object(path, "/bin/busybox") || !same_object("/proc/1/exe", "/bin/busybox")) reject("watch executable differs");
    for (i = 0; i < 3; i++) {
        snprintf(path, sizeof path, "/proc/%ld/ns/%s", raw, names[i]);
        snprintf(expected, sizeof expected, "/proc/1/ns/%s", names[i]);
        if (!same_object(path, expected)) reject("watch namespace differs");
    }
    snprintf(path, sizeof path, "/proc/%ld/cmdline", raw);
    file = fopen(path, "rb");
    if (!file) reject("watch command unavailable");
    len = fread(data, 1, sizeof data, file);
    if (ferror(file) || fclose(file)) reject("watch command unreadable");
    want = (size_t)snprintf(expected, sizeof expected, "/bin/busybox");
    if (want + 1 > sizeof data || len < want + 1 || memcmp(data, expected, want + 1)) reject("watch argv0 differs");
    {
        const char *args[] = {"sh", "/run/pid1-guard/guard.sh", "watch", "mock", budget, mock};
        size_t pos = want + 1;
        for (i = 0; i < sizeof args / sizeof args[0]; i++) {
            want = strlen(args[i]) + 1;
            if (pos + want > len || memcmp(data + pos, args[i], want)) reject("watch arguments differ");
            pos += want;
        }
        if (pos != len) reject("extra watch arguments");
    }
    if (poll(&pollfd, 1, 0) != 0 || syscall(SYS_pidfd_send_signal, fd, sig, NULL, 0)) reject("pidfd signal failed");
    if (sig == SIGKILL && poll(&pollfd, 1, 5000) != 1) reject("killed watch did not exit");
    close(fd);
    return 0;
}
C
HOST_PIDFD_SHA=$(hash "$WORK/pidfd-signal")
HERE=$HERE WORK=$WORK python3 -B - <<'PY'
import importlib.util
import os
import pathlib
import sys
here = pathlib.Path(os.environ['HERE'])
sys.path.insert(0, str(here))
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
builder = load('builder', 'build-init-boot-persistent-root.py')
persist = load('persist', 'derive-radio-persistent.py')
fresh = load('fresh', 'derive-radio-fresh-boot.py')
postgen = load('postgen', 'derive-self-post-fresh-boot.py')
gen = load('gate_gen', 'derive-success-gated-ack.py')
radio = fresh.derive(persist.derive(builder.current_scripts()['pmos-radio-bringup.sh'].decode()))
post, _ = postgen.derive((here / 'pmos-self-post.sh').read_text(), radio.encode())
probe = gen.build_dns_probe()
candidate, hook = gen.derive(post, radio.encode(), probe)
if not candidate.startswith(post) or not candidate[len(post):].startswith('\nGATE_DIR='):
    raise SystemExit('candidate does not contain the generated gate suffix')
if '@DNS_BASE64@' in candidate or '@DNS_SHA@' in candidate:
    raise SystemExit('candidate contains unresolved probe placeholders')
work = pathlib.Path(os.environ['WORK'])
(work / 'gate').write_text(candidate[len(post):])
(work / 'radio').write_text(radio)
(work / 'candidate').write_text(candidate)
(work / 'hook').write_text(hook)
(work / 'replay-nonce').write_text('none\n')
PY
for generated in "$WORK/candidate" "$WORK/hook"; do sh -n "$generated" || fail "generated syntax: $generated"; done
printf '%s\n' 'fixture: generated gate suffix only; preceding self-post and radio stages are not executed'
printf '%s\n' 'fixture: mocked radio/process/service evidence, selected hashes, kmsg, network commands and DNS result; real probe bytes are checked but not executed'
printf '%s\n' 'fixture: dead-watcher uses pidfd SIGKILL; post-interrupt pauses the real watcher and barriers the publisher after single-link ACK publication'
HOST_mnt_NS=$(readlink /proc/self/ns/mnt)
HOST_pid_NS=$(readlink /proc/self/ns/pid)
HOST_net_NS=$(readlink /proc/self/ns/net)
run_case() {
	sudo -n timeout -k 5 90 unshare --mount --pid --net --fork --kill-child --mount-proc \
		env -i HOST_mnt_NS="$HOST_mnt_NS" HOST_pid_NS="$HOST_pid_NS" HOST_net_NS="$HOST_net_NS" \
		HOST_WORK="$WORK" HOST_SCRIPT="$SCRIPT" HOST_GUARD="$HERE/pmos-pid1-guard.sh" HOST_PIDFD_SHA="$HOST_PIDFD_SHA" \
		/bin/busybox sh "$SCRIPT" --inner "$1"
}
result=$(run_case success) || fail 'isolated success case'
nonce=$(printf '%s\n' "$result" | "$BB" awk -F= '/^REPLAY_NONCE=/ {print $2}')
case "$nonce" in ????????????????????????????????????????????????????????????????) case "$nonce" in *[!0-9a-f]*) fail 'invalid captured nonce';; esac;; *) fail 'missing captured nonce';; esac
printf '%s\n' "$nonce" > "$WORK/replay-nonce"
printf '%s\n' "$result" | "$BB" grep -v '^REPLAY_NONCE='
for case in partial invalid interrupt post-interrupt dead-watcher replay late; do run_case "$case" || fail "$case isolated fixture"; done
printf '%s\n' 'pass: host-only isolated tmpfs switch_root; unchanged digest-pinned guard; generated gate with mocked external evidence, no network or device'
