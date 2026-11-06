#!/bin/sh
set -eu

BB=/bin/busybox
MOCK_SHA=fe72fe25364a1a08c6482bcecb3175f2c0def38af6fc02967b1edc1d6cf28e71
CONTRACT_SHA=c76c31ff148ab19ff5b2de6f1e40a036ee6ec275d54b0b5d1eaab0bbf0f06cc6
GUARD_SHA=dcc4124dd404823f891e683d455177613d91afc2bd91582835cc1d6bbe118243
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
hash() { "$BB" sha256sum "$1" | "$BB" cut -d ' ' -f 1; }

if [ "${1:-}" = --switched ]; then
	[ "$#" = 2 ] && [ "$$" = 1 ] || fail 'switched process is not PID 1'
	case "$2" in success|partial|invalid|interrupt|post-interrupt|dead-watcher|replay|late|premature|no-record|bad-record|record-mode|record-symlink|record-links|record-foreign|record-order|record-malformed|panel-absent|panel-record-absent|panel-foreign|panel-conflict|panel-malformed|panel-mode|panel-symlink|panel-links|contract-missing|contract-corrupt|contract-mode|contract-symlink|contract-links|ready-mode|ready-symlink|ready-links|ready-nonce|ready-boot|ready-newline|staging|staging-record-invalid|gate-staging|preplanted-multilink|full-success|full-radio-fail|full-invalid|full-route-cache-success|full-route-cache-internet-dev|full-route-cache-internet-extra|full-route-cache-dns-dev|full-route-cache-dns-extra|full-unpinned-success) CASE=$2;; *) fail 'invalid case';; esac
	umask 077
	for ns in mnt pid net; do
		eval "host_ns=\${HOST_${ns}_NS:-}"
		[ -n "$host_ns" ] && [ "$("$BB" readlink "/proc/1/ns/$ns")" != "$host_ns" ] || fail "$ns namespace not isolated after switch_root"
	done
	"$BB" awk -F: 'NR > 2 {gsub(/[ \t]/, "", $1); if ($1 != "lo") bad++; else n++} END {exit(bad || n != 1)}' /proc/net/dev || fail 'switched network namespace has unexpected interfaces'
	[ "$(hash /proc/1/exe)" = "$(hash /bin/busybox)" ] || fail 'PID 1 executable differs from real BusyBox'
	[ "$("$BB" stat -c '%d:%i' /)" = "$("$BB" stat -Lc '%d:%i' /proc/1/root)" ] || fail 'PID 1 root differs'
	"$BB" awk '$2 == "/" {n++; if ($3 != "ext4") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts || fail 'root is not isolated ext4'
	"$BB" awk '$2 == "/run" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts || fail 'run is not tmpfs'
	[ "$(hash /run/pid1-guard/guard.sh)" = "$GUARD_SHA" ] && [ "$(hash /run/pid1-guard/mock-restart2)" = "$MOCK_SHA" ] || fail 'guard or recovery helper changed'
	[ ! -e /bin/restart2 ] && [ ! -L /bin/restart2 ] || fail 'real recovery helper present'
	case "$CASE" in
		contract-*)
			i=0
			until [ -f /run/pid1-guard/recovery-request ]; do
			[ "$i" -lt 240 ] && [ ! -e /run/pid1-guard/nonce ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE did not fail closed"
				"$BB" sleep 0.1
				i=$((i + 1))
			done
			[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE recovery invalid"
			printf 'pass: %s: copied root contract invalid before cutover; no nonce, deadline recovery\n' "$CASE"
			exit 0;;
	esac
	[ -f /run/pid1-guard/root-contract.sh ] && [ ! -L /run/pid1-guard/root-contract.sh ] &&
		[ "$(hash /run/pid1-guard/root-contract.sh)" = "$CONTRACT_SHA" ] || fail 'real root contract not carried into switch_root'
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
		panel-absent) PANEL_EVIDENCE=absent "$BB" sh /boot-record-setup.sh || fail 'real contract could not create no-panel record';;
		full-*) FULL_POST=1 "$BB" sh /boot-record-setup.sh || fail 'real contract could not create pre-cutover-only record';;
		*) "$BB" sh /boot-record-setup.sh || fail 'real contract could not create ordered record';;
	esac
	[ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] && [ ! -e /run/pid1-guard/accepted ] && [ ! -e /run/pid1-guard/recovery-request ] && [ ! -e /run/pid1-guard/ack ] || fail 'guard changed while creating record'
	case "$CASE" in
		no-record) "$BB" rm /.omnipha-boot-record;;
		bad-record) "$BB" printf '%s\n' 'invalid terminal record' >> /.omnipha-boot-record;;
		record-mode) "$BB" chmod 644 /.omnipha-boot-record;;
		record-symlink) "$BB" mv /.omnipha-boot-record /run/record-link-target; "$BB" ln -s /run/record-link-target /.omnipha-boot-record;;
		record-links) "$BB" ln /.omnipha-boot-record /.record-link;;
		record-foreign) "$BB" printf 'boot 11111111-2222-3333-4444-555555555555\n' > /.omnipha-boot-record;;
		record-order) "$BB" sed -i '1{h;d};2{p;g}' /.omnipha-boot-record;;
		record-malformed) "$BB" head -c 20 /dev/urandom > /.omnipha-boot-record;;
		panel-record-absent) "$BB" rm -f /run/pmos-pre-ssh-panel.record;;
		panel-foreign) "$BB" printf 'usb-init: pre-SSH panel node=boe card0=1 boot 11111111-2222-3333-4444-555555555555\n' > /run/pmos-pre-ssh-panel.record;;
		panel-conflict) "$BB" printf 'usb-init: pre-SSH panel node=vxn card0=2 boot %s\n' "$boot" > /run/pmos-pre-ssh-panel.record;;
		panel-malformed) "$BB" printf 'corrupt panel record\n' > /run/pmos-pre-ssh-panel.record;;
		panel-mode) "$BB" chmod 644 /run/pmos-pre-ssh-panel.record;;
		panel-symlink) "$BB" mv /run/pmos-pre-ssh-panel.record /run/panel-link-target; "$BB" ln -s /run/panel-link-target /run/pmos-pre-ssh-panel.record;;
		panel-links) "$BB" ln /run/pmos-pre-ssh-panel.record /run/panel-link;;
		staging-record-invalid) "$BB" printf 'invalid\n' >> /.omnipha-boot-record;;
	esac
	case "$CASE" in
		panel-absent)
			[ ! -e /run/pmos-pre-ssh-panel.record ] && [ ! -L /run/pmos-pre-ssh-panel.record ] || fail 'no-panel fixture unexpectedly has a panel record'
			if "$BB" grep -qF 'usb-init: pre-SSH panel node=' /.omnipha-boot-record; then fail 'no-panel fixture record includes panel evidence'; fi;;
		staging|staging-record-invalid)
			(umask 077; set -C; "$BB" printf '%s %s\n' "$nonce" "$boot" > /run/pid1-guard/success-ready)
			(umask 077; set -C; "$BB" printf '%s %s\n' "$nonce" "$boot" > /run/pid1-guard/.staging-ack-new)
			"$BB" chmod 640 /run/pid1-guard/.staging-ack-new
			"$BB" ln /run/pid1-guard/.staging-ack-new /run/pid1-guard/ack
			[ "$("$BB" stat -c '%u:%a:%h:%s' /run/pid1-guard/ack)" = "0:640:2:$((${#nonce} + ${#boot} + 2))" ] || fail 'malformed staging ACK does not have 2 links'
			"$BB" sleep 2
			[ ! -e /run/pid1-guard/recovery-request ] && [ ! -e /run/pid1-guard/accepted ] || fail 'two-link malformed ACK caused premature recovery or acceptance'
			"$BB" chmod 600 /run/pid1-guard/ack
			"$BB" rm /run/pid1-guard/.staging-ack-new
			[ "$("$BB" stat -c '%u:%a:%h' /run/pid1-guard/ack)" = 0:600:1 ] || fail 'ACK not single link after unstage'
			i=0
			if [ "$CASE" = staging ]; then
				until [ -f /run/pid1-guard/accepted ]; do
					[ "$i" -lt 60 ] && [ ! -e /run/pid1-guard/recovery-request ] || fail 'single-link ACK not accepted after staging'
					"$BB" sleep 0.1
					i=$((i + 1))
				done
				[ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] && [ ! -e /run/pid1-guard/nonce ] && [ ! -e /run/pid1-guard/ack ] || fail 'staging ACK consumption failed'
				printf 'pass: staging: malformed two-link ACK with success-ready did not cause premature recovery; accepted once single-link 0600\n'
			else
				until [ -f /run/pid1-guard/recovery-request ]; do
					[ "$i" -lt 160 ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE did not request recovery"
					"$BB" sleep 0.1
					i=$((i + 1))
				done
				[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE recovery invalid"
				printf 'pass: %s: two-link staging did not recover; invalid record refused once single-link\n' "$CASE"
			fi
			exit 0;;
		ready-mode|ready-symlink|ready-links|ready-nonce|ready-boot|ready-newline|no-record|bad-record|record-mode|record-symlink|record-links|record-foreign|record-order|record-malformed|panel-record-absent|panel-foreign|panel-conflict|panel-malformed|panel-mode|panel-symlink|panel-links|premature)
				if [ "$CASE" != premature ]; then
					case "$CASE" in
						ready-symlink) "$BB" printf '%s %s\n' "$nonce" "$boot" > /run/ready-target; "$BB" ln -s /run/ready-target /run/pid1-guard/success-ready;;
						ready-nonce) "$BB" printf '%064d %s\n' 0 "$boot" > /run/pid1-guard/success-ready;;
						ready-boot) "$BB" printf '%s %s\n' "$nonce" 11111111-2222-3333-4444-555555555555 > /run/pid1-guard/success-ready;;
						ready-newline) "$BB" printf '%s %s\000' "$nonce" "$boot" > /run/pid1-guard/success-ready;;
						*) "$BB" printf '%s %s\n' "$nonce" "$boot" > /run/pid1-guard/success-ready;;
					esac
					case "$CASE" in
						ready-mode) "$BB" chmod 644 /run/pid1-guard/success-ready;;
						ready-links) "$BB" ln /run/pid1-guard/success-ready /run/pid1-guard/ready-link;;
					esac
				fi
				"$BB" printf '%s %s\n' "$nonce" "$boot" > /run/pid1-guard/ack
				i=0
				until [ -f /run/pid1-guard/recovery-request ]; do
					[ "$i" -lt 60 ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE did not request recovery promptly"
					"$BB" sleep 0.1
					i=$((i + 1))
				done
				[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] &&
					[ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] &&
					[ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail "$CASE recovery changed ACK or nonce"
				if [ "$CASE" = premature ]; then
					now=$("$BB" awk '{print int($1)}' /proc/uptime)
					[ "$now" -lt "$((TEST_ARM_UPTIME + TEST_BUDGET))" ] || fail 'premature ACK reached recovery only at the deadline'
					"$BB" printf '%s %s\n' "$nonce" "$boot" > /run/pid1-guard/success-ready
					"$BB" sleep 2
					[ ! -e /run/pid1-guard/accepted ] && [ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] && [ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail 'late readiness accepted premature ACK'
				fi
				printf 'pass: %s: real guard refused and requested mock recovery without consuming ACK or nonce\n' "$CASE"
				exit 0;;
		esac
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
	case "$CASE" in
		full-*) :;;
		*) for stage in modem wpss driver scan services; do
			token="guest-radio-$stage-$("$BB" printf '%s' "$boot:$nonce:$stage" | "$BB" sha256sum | "$BB" cut -c 1-16)"
			"$BB" printf '%s\n' "$token" > "/run/radio-bringup/$stage.marker"
		done;;
	esac
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
	case "$CASE" in full-*) :;; *) "$BB" chmod 600 /run/radio-bringup/*.marker;; esac
	"$BB" chmod 600 /run/radio-bringup/rmtfs.pid \
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
			[ "$i" -lt 300 ] || fail 'guard did not reach its real deadline'
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
	case "$CASE" in
		full-*)
			GATE_DIR=/run/radio-bringup/success-gate-294
			case "$CASE" in
				full-route-cache-*)
					[ "$(hash /derived-post)" = 92f6f9cdfa3dcdc8854c7481fe01b500591f1b2b1c9908e97c4cdbfc0ae68d0c ] || fail 'candidate case derived post is not the candidate post';;
				full-unpinned-*)
					[ "$(hash /derived-post)" = "$HOST_UNPINNED_POST_SHA" ] || fail 'unpinned case derived post is not the generated candidate post';;
				*)
					[ "$(hash /derived-post)" = 113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3 ] || fail 'full case derived post is not the canonical generated post';;
			esac
			[ "$(hash /run/pid1-guard/guard.sh)" = "$GUARD_SHA" ] &&
				[ "$("$BB" stat -Lc '%d:%i' /proc/1/exe)" = "$("$BB" stat -c '%d:%i' /bin/busybox)" ] || fail 'full case guard or PID 1 is not real BusyBox'
			"$BB" printf '/bin/busybox\000sh\000/run/pid1-guard/guard.sh\000watch\000mock\000%s\000%s\000' "$TEST_BUDGET" "$MOCK_SHA" > /run/full-watch-command
			watch=
			for proc in /proc/[0-9]*; do
				"$BB" cmp -s "$proc/cmdline" /run/full-watch-command 2>/dev/null || continue
				[ -z "$watch" ] || fail 'multiple full case guards'
				[ "$("$BB" stat -Lc '%d:%i' "$proc/exe")" = "$("$BB" stat -c '%d:%i' /bin/busybox)" ] &&
					[ "$("$BB" stat -Lc '%d:%i' "$proc/root")" = "$("$BB" stat -c '%d:%i' /)" ] || fail 'full case guard executable or root differs'
				watch=$proc
			done
			[ -n "$watch" ] || fail 'full case real guard watcher missing'
			"$BB" sed 's|^BB=/bin/busybox$|BB=/run/tool|' /derived-post > /run/full-post.sh
			"$BB" chmod 700 /run/full-post.sh
			[ "$("$BB" grep -c '^BB=/run/tool$' /run/full-post.sh)" = 1 ] || fail 'full case BB redirect missing or duplicated'
			"$BB" sed 's|^BB=/run/tool$|BB=/bin/busybox|' /run/full-post.sh > /run/full-post-reversed
			"$BB" cmp -s /run/full-post-reversed /derived-post || fail 'full case derived post changed beyond the single BB line'
			"$BB" cp /.omnipha-boot-record /run/pre-cutover-record
			[ "$("$BB" sed -n '$p' /run/pre-cutover-record)" = 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' ] || fail 'full case record not at cutover'
			! "$BB" grep -q 'pmos-self-post: post-cutover PID 1' /run/pre-cutover-record || fail 'full case final post entry was preseeded'
			"$BB" printf '%s\n' "$boot" > /run/full-boot
			"$BB" chmod 600 /run/full-boot
			"$BB" printf '' > /run/keep
			"$BB" chmod 600 /run/keep
			"$BB" cat > /run/tool <<'FULLWRAP'
#!/bin/busybox sh
b=/bin/busybox
req() { $b printf '%s\n' "$*" >> /run/tool-requests; }
rmtfs_pid=$($b cat /run/radio-bringup/rmtfs.pid 2>/dev/null)
for arg in "$@"; do
	case "$arg" in
		/|/bin/busybox|/proc/1/*|/proc/self/mountinfo|/proc/sys/kernel/random/boot_id|/run/pid1-guard|/run/pid1-guard/*|/run/pmos-root-contract.sh|/run/pmos-pre-ssh-panel.record|/.omnipha-boot-record*|/sys/class/block/*|/dev/block/*)
			exec "$b" "$@";;
	esac
done
case "${1:-}" in
	stat|cut|printf|sed|tr|sort|wc|cmp|ln|rm|mv|cp|touch|chmod|mkdir|rmdir|sleep|sync|blockdev|id|readlink|head|base64|tee|dd)
		exec "$b" "$@";;
	timeout)
		if [ "$#" = 6 ] && [ "$2" = -k ] && [ "$3" = 1 ] && [ "$4" = 6 ] && [ "$5" = /run/radio-bringup/success-gate-294/dns-probe ] && [ "$6" = 192.0.2.53 ]; then
			req 'intercepted DNS probe'
			if [ "$($b cat /run/case)" = full-invalid ]; then $b printf '%s\n' 127.0.0.1; else $b printf '%s\n' 192.0.2.80; fi
			exit 0
		fi
		exec "$b" "$@";;
	cat)
		if [ "$#" = 2 ] && [ -n "$rmtfs_pid" ] && [ "$2" = "/proc/$rmtfs_pid/comm" ]; then req 'intercepted rmtfs comm'; $b printf '%s\n' rmtfs; exit 0; fi
		exec "$b" "$@";;
	sha256sum)
		if [ "$#" = 2 ]; then
			if [ -n "$rmtfs_pid" ] && [ "$2" = "/proc/$rmtfs_pid/exe" ]; then
				req 'intercepted rmtfs executable hash'
				$b printf '%s  %s\n' d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd "$2"; exit 0
			fi
			case "$2" in
				/etc/init.d/networking) req 'intercepted networking service hash'; $b printf '%s  %s\n' 334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c "$2"; exit 0;;
				/etc/init.d/wpa_supplicant) req 'intercepted supplicant service hash'; $b printf '%s  %s\n' a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f "$2"; exit 0;;
				/run/radio-bringup/wlan-udhcpc-lease.sh) req 'intercepted lease helper hash'; $b printf '%s  %s\n' 1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56 "$2"; exit 0;;
			esac
		fi
		exec "$b" "$@";;
	grep)
		if [ "$#" = 4 ] && [ "$2" = -q ] && [ "$3" = /dev/uio0 ] && [ -n "$rmtfs_pid" ] && [ "$4" = "/proc/$rmtfs_pid/maps" ]; then req 'intercepted rmtfs UIO map'; exit 0; fi
		exec "$b" "$@";;
	awk)
		if [ "$#" = 3 ] && [ "$2" = '$2 == "022A10AC:08AE" && $4 == "0A" {n++} END {exit(n != 1)}' ] && [ "$3" = /proc/net/tcp ]; then req 'intercepted SSH listener check'; exit 0; fi
		exec "$b" "$@";;
	dmesg)
		req "intercepted dmesg $*"
		$b printf '%s\n' "usb-init: usb-init: pre-SSH panel node=boe card0=1 boot $($b cat /run/full-boot)"
		for marker in /run/radio-bringup/*.marker; do
			[ -f "$marker" ] || continue
			$b printf 'pmos-self-post: guest radio marker %s\n' "$("$b" cat "$marker")"
		done
		exit 0;;
	pidof)
		req "intercepted pidof $*"
		case "${2:-}" in pd-mapper|tqftpserv) exit 0;; esac
		exit 1;;
	ping)
		req "intercepted ping $*"
		case "$*" in 'ping -4 -I wlan0 -c 1 -W 4 -w 5 192.0.2.1'|'ping -4 -I wlan0 -c 1 -W 4 -w 5 1.1.1.1') exit 0;; esac
		exit 1;;
	sh)
		if [ "$#" = 5 ] && [ "$2" = /usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh ]; then
			req "intercepted radio stage $4 path $2 marker $5"
			if [ "$($b cat /run/case)" = full-radio-fail ] && [ "$4" = scan ]; then exit 1; fi
			exit 0
		fi
		exec "$b" "$@";;
	*)
		req "refused $*"
		exit 1;;
esac
FULLWRAP
			"$BB" chmod 700 /run/tool
			printf '%s\n' 'fixture full: pinned canonical, route-cache or unpinned candidate post executed after replacing only BB=/bin/busybox with /run/tool; PID 1, the real guard and /bin/busybox stay real BusyBox' \
				'fixture full: wrapper passes guard, ACK/ready, ordered-record, identity and radio-marker file operations through unchanged; other invocations use the applet allowlist' \
				'fixture full: mocked boundaries only: dmesg kmsg replay (synthetic pre-cutover panel line and marker publication), rmtfs/daemon process evidence and pinned hashes, pidof, ping, route replies, DNS probe answer, radio stage invocations' \
				'fixture full unpinned: the candidate launches the edited synthetic radio directly through the persistent path; radio stage execution is mocked, not the physical radio; no snapshot, chain metadata, hash or denylist check; no BAD_RADIO bytes'
			: > /run/tool-requests
			full_result=0
			"$BB" sh /run/full-post.sh > /run/full-post.log 2>&1 || full_result=$?
			"$BB" cp /run/pre-cutover-record /run/expected-full-record
			"$BB" printf 'pmos-self-post: post-cutover PID 1 on boot %s; guard identity check passed; pid1 identity check passed\n' "$boot" >> /run/expected-full-record
			"$BB" cmp -s /run/expected-full-record /.omnipha-boot-record || fail "$CASE record not exactly pre-cutover entries plus post entry"
			case "$CASE" in
				full-route-cache-*)
					case "$CASE" in
						full-route-cache-internet-*) expected_routes=internet;;
						*) expected_routes=$("$BB" printf 'internet\ndns\n');;
					esac
					[ "$("$BB" cat /run/route-requests)" = "$expected_routes" ] || fail "$CASE route lookup order differs"
					for route_stage in internet dns; do
						case "$route_stage:$CASE" in
							dns:full-route-cache-internet-*) [ ! -e /run/route-dns-reply ] || fail "$CASE unexpectedly queried DNS route"; continue;;
							internet:*) target=1.1.1.1;;
							dns:*) target=192.0.2.53;;
						esac
						dev=wlan0
						continuation='    cache '
						case "$CASE:$route_stage" in
							full-route-cache-internet-dev:internet|full-route-cache-dns-dev:dns) dev=eth0;;
							full-route-cache-internet-extra:internet|full-route-cache-dns-extra:dns) continuation='    cache extra';;
						esac
						"$BB" printf '%s\n' "$target from 192.0.2.2 via 192.0.2.1 dev $dev uid 0 " "$continuation" |
							"$BB" cmp -s - "/run/route-$route_stage-reply" || fail "$CASE $route_stage reply differs"
					done;;
			esac
			case "$CASE" in
				full-success|full-route-cache-success|full-unpinned-success)
					[ "$full_result" = 0 ] || { "$BB" cat /run/full-post.log >&2; "$BB" cat "$GATE_DIR/refusal" >&2 2>/dev/null || true; fail "$CASE post did not succeed"; }
					[ "$("$BB" sed -n '$p' /.omnipha-boot-record)" = "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed" ] || fail "$CASE post record line missing"
					! "$BB" grep -q 'pmos-self-post: FAIL' /.omnipha-boot-record || fail "$CASE record contains a failure"
					for stage in modem wpss driver scan services; do
						token="guest-radio-$stage-$("$BB" printf '%s' "$boot:$nonce:$stage" | "$BB" sha256sum | "$BB" cut -c 1-16)"
						[ -f "/run/radio-bringup/$stage.marker" ] && [ ! -L "/run/radio-bringup/$stage.marker" ] &&
							[ "$("$BB" stat -c '%u:%a:%h' "/run/radio-bringup/$stage.marker")" = 0:600:1 ] &&
							[ "$("$BB" cat "/run/radio-bringup/$stage.marker")" = "$token" ] || fail "$CASE marker $stage invalid"
					done
					for stage in nonce-and-radio-markers radio-health services association address route gateway internet dns final-health all-checks published accepted; do
						[ -f "$GATE_DIR/$stage.ok" ] || fail "$CASE missing evidence: $stage"
					done
					[ ! -e "$GATE_DIR/kmsg" ] && [ ! -e "$GATE_DIR/dns-probe" ] || fail "$CASE left bounded snapshots behind"
					[ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] && [ ! -e /run/pid1-guard/nonce ] && [ ! -e /run/pid1-guard/ack ] ||
						fail "$CASE real guard did not consume nonce and ACK"
					[ -f /run/pid1-guard/success-ready ] && [ "$("$BB" stat -c '%h' /run/pid1-guard/success-ready)" = 1 ] || fail "$CASE success-ready invalid"
					[ ! -e /run/pid1-guard/.success-gated-ack-new ] && [ ! -e /run/pid1-guard/recovery-request ] || fail "$CASE left staging or recovery"
					"$BB" sleep "$((TEST_BUDGET + 2))"
					[ ! -e /run/pid1-guard/recovery-request ] && [ "$("$BB" cat /run/pid1-guard/accepted)" = "$boot" ] || fail "$CASE accepted guard requested recovery"
					;;
				full-radio-fail)
					[ "$full_result" != 0 ] || fail 'full-radio-fail post unexpectedly succeeded'
					"$BB" grep -q 'radio bring-up scan failed' /run/full-post.log || fail 'full-radio-fail failure reason missing'
					[ ! -e /run/radio-bringup/services.marker ] && [ -f /run/radio-bringup/scan.marker ] && [ -f /run/radio-bringup/driver.marker ] || fail 'full-radio-fail stage order wrong'
					[ ! -e "$GATE_DIR" ] || fail 'full-radio-fail started a gate'
					;;
				full-invalid)
					[ "$full_result" != 0 ] || fail 'full-invalid post unexpectedly succeeded'
					"$BB" grep -F 'stage=dns result=refused-or-interrupted phase=before-publication reason=invalid DNS answer' "$GATE_DIR/refusal" >/dev/null ||
						{ "$BB" cat /run/full-post.log "$GATE_DIR/refusal" >&2 2>/dev/null || true; fail 'full-invalid DNS refusal reason'; }
					;;
				full-route-cache-internet-*)
					[ "$full_result" != 0 ] || fail "$CASE post unexpectedly succeeded"
					"$BB" grep -xF "boot=$boot stage=internet result=refused-or-interrupted phase=before-publication reason=internet route is not wlan0" "$GATE_DIR/refusal" >/dev/null ||
						{ "$BB" cat /run/full-post.log "$GATE_DIR/refusal" >&2 2>/dev/null || true; fail "$CASE refusal reason"; }
					[ -f "$GATE_DIR/gateway.ok" ] && [ ! -e "$GATE_DIR/internet.ok" ] && [ ! -e "$GATE_DIR/dns.ok" ] || fail "$CASE stage evidence invalid"
					! "$BB" grep -qF 'intercepted ping ping -4 -I wlan0 -c 1 -W 4 -w 5 1.1.1.1' /run/tool-requests || fail "$CASE pinged internet after route refusal"
					;;
				full-route-cache-dns-*)
					[ "$full_result" != 0 ] || fail "$CASE post unexpectedly succeeded"
					"$BB" grep -xF "boot=$boot stage=dns result=refused-or-interrupted phase=before-publication reason=DNS route is not wlan0" "$GATE_DIR/refusal" >/dev/null ||
						{ "$BB" cat /run/full-post.log "$GATE_DIR/refusal" >&2 2>/dev/null || true; fail "$CASE refusal reason"; }
					[ -f "$GATE_DIR/internet.ok" ] && [ ! -e "$GATE_DIR/dns.ok" ] || fail "$CASE stage evidence invalid"
					;;
			esac
			if [ "$CASE" != full-success ] && [ "$CASE" != full-route-cache-success ] && [ "$CASE" != full-unpinned-success ]; then
				[ ! -e /run/pid1-guard/ack ] && [ ! -L /run/pid1-guard/ack ] &&
					[ ! -e /run/pid1-guard/.ack-new ] && [ ! -L /run/pid1-guard/.ack-new ] &&
					[ ! -e /run/pid1-guard/.success-gated-ack-new ] && [ ! -L /run/pid1-guard/.success-gated-ack-new ] &&
					[ ! -e /run/pid1-guard/success-ready ] && [ ! -L /run/pid1-guard/success-ready ] &&
					[ ! -e /run/pid1-guard/.success-ready-new ] && [ ! -L /run/pid1-guard/.success-ready-new ] &&
					[ ! -e "$GATE_DIR/published.ok" ] || fail "$CASE published an ACK or readiness"
				[ ! -e /run/pid1-guard/recovery-request ] && [ ! -e /run/pid1-guard/accepted ] || fail "$CASE gate refused before the independent deadline"
				i=0
				until [ -f /run/pid1-guard/recovery-request ]; do
					[ "$i" -lt 300 ] && [ ! -e /run/pid1-guard/accepted ] || { "$BB" cat /run/tool-requests >&2; fail "$CASE guard did not independently request recovery"; }
					"$BB" sleep 0.1
					i=$((i + 1))
				done
				[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] && [ ! -e /run/pid1-guard/accepted ] && [ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail "$CASE recovery or nonce invalid"
				deadline_reached
				case "$CASE" in
					full-route-cache-*)
						for path in /run/pid1-guard/ack /run/pid1-guard/.ack-new /run/pid1-guard/.success-gated-ack-new /run/pid1-guard/success-ready /run/pid1-guard/.success-ready-new "$GATE_DIR/published.ok"; do
							[ ! -e "$path" ] && [ ! -L "$path" ] || fail "$CASE published ACK or readiness after refusal"
						done
						! "$BB" grep -qF 'intercepted DNS probe' /run/tool-requests || fail "$CASE probed DNS after route refusal";;
				esac
			fi
			case "$CASE" in
				full-radio-fail) expected_stages='modem wpss driver scan';;
				*) expected_stages='modem wpss driver scan services';;
			esac
			actual_stages=$("$BB" awk '/^intercepted radio stage / {printf "%s%s", sep, $4; sep=" "}' /run/tool-requests)
			[ "$actual_stages" = "$expected_stages" ] || fail "$CASE radio stage invocation order differs: $actual_stages"
			! "$BB" grep -q '^refused ' /run/tool-requests || { "$BB" grep '^refused ' /run/tool-requests >&2; fail "$CASE wrapper refused an operation"; }
			"$BB" grep -q 'intercepted dmesg' /run/tool-requests || fail "$CASE mocked panel/kmsg boundary not exercised"
			case "$CASE" in
				full-success|full-route-cache-success|full-invalid|full-unpinned-success)
					for boundary in 'DNS probe' 'rmtfs comm' 'rmtfs executable hash' 'rmtfs UIO map' 'SSH listener check' 'networking service hash' 'supplicant service hash' 'lease helper hash' pidof ping; do
						"$BB" grep -qF "intercepted $boundary" /run/tool-requests || fail "$CASE mock boundary not exercised: $boundary"
					done;;
				full-route-cache-*)
					for boundary in 'rmtfs comm' 'rmtfs executable hash' 'rmtfs UIO map' 'SSH listener check' 'networking service hash' 'supplicant service hash' 'lease helper hash' pidof ping; do
						"$BB" grep -qF "intercepted $boundary" /run/tool-requests || fail "$CASE mock boundary not exercised: $boundary"
					done;;
			esac
			case "$CASE" in
				full-unpinned-success)
					persistent=/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh
					[ "$("$BB" awk -v path="$persistent" '$1 == "intercepted" && $2 == "radio" && $3 == "stage" && $5 == "path" && $6 == path {print $4}' /run/tool-requests)" = "$(printf '%s\n' modem wpss driver scan services)" ] ||
						fail "$CASE direct persistent radio path was not recorded"
					! "$BB" grep -qE 'omnipha-radio-snapshot|radio_snapshot|radio snapshot|mocked snapshot hash|BAD_RADIO' /run/tool-requests /run/full-post.log ||
						fail "$CASE used a snapshot, hash or denylist path"
					[ ! -e /run/radio-bringup/omnipha-radio-snapshot ] && [ ! -L /run/radio-bringup/omnipha-radio-snapshot ] ||
						fail "$CASE created a radio snapshot"
					"$BB" grep -qxF ': mb003-unpinned-synthetic-edit' "$persistent" &&
						"$BB" cmp -s "$persistent" /run/edited-radio || fail "$CASE edited synthetic radio was not passed through"
					[ "$(hash "$persistent")" != 146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14 ] &&
						[ "$(hash "$persistent")" != d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3 ] ||
						fail "$CASE edited radio has the canonical pin or BAD_RADIO digest";;
			esac
			printf 'pass: %s: generated post with BB redirected ran once; guard and ordered record were real; external evidence was synthetic\n' "$CASE"
			exit 0;;
	esac
	"$BB" sh /gate-runner > /run/gate.log 2>&1 &
	gate=$!
	if [ "$CASE" = gate-staging ]; then
		i=0
		until [ -f /run/link-barrier ]; do
			[ "$i" -lt 100 ] && "$BB" kill -0 "$gate" 2>/dev/null || { "$BB" cat /run/gate.log >&2; fail 'publisher did not reach two-link barrier'; }
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		[ "$("$BB" stat -c '%u:%a:%h:%s' /run/pid1-guard/ack)" = "0:600:2:$((${#nonce} + ${#boot} + 2))" ] &&
			[ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] &&
			[ "$("$BB" cat /run/pid1-guard/success-ready)" = "$nonce $boot" ] || fail 'publisher two-link state invalid'
		"$BB" sleep 2
		[ ! -e /run/pid1-guard/recovery-request ] && [ ! -e /run/pid1-guard/accepted ] || fail 'guard consumed or recovered during two-link publication'
		"$BB" touch /run/link-release
	fi
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
	if [ "$CASE" = preplanted-multilink ]; then
		[ "$result" != 0 ] && [ ! -e /run/pid1-guard/accepted ] || fail 'preplanted two-link ACK was accepted or gate succeeded'
		[ "$("$BB" stat -c '%u:%a:%h:%s' /run/pid1-guard/ack)" = "0:600:2:$((${#nonce} + ${#boot} + 2))" ] &&
			[ "$("$BB" cat /run/pid1-guard/ack)" = "$nonce $boot" ] &&
			[ "$("$BB" cat /run/pid1-guard/nonce)" = "$nonce" ] || fail 'preplanted ACK or nonce changed'
		i=0
		until [ -f /run/pid1-guard/recovery-request ]; do
			[ "$i" -lt 300 ] && [ ! -e /run/pid1-guard/accepted ] || fail 'preplanted ACK did not recover'
			"$BB" sleep 0.1
			i=$((i + 1))
		done
		[ "$("$BB" cat /run/pid1-guard/recovery-request)" = bootloader ] && [ ! -e /run/pid1-guard/accepted ] || fail 'preplanted recovery invalid'
		printf 'pass: preplanted-multilink: genuine publisher failed no-replace; forged two-link ACK was not accepted and recovery occurred\n'
		exit 0
	fi
	if [ "$CASE" = success ] || [ "$CASE" = panel-absent ] || [ "$CASE" = gate-staging ]; then
		[ "$result" = 0 ] || { "$BB" cat /run/gate.log /run/radio-bringup/success-gate-294/refusal >&2 2>/dev/null || true; "$BB" ls -la /run/pid1-guard >&2; fail 'generated gate failed'; }
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
		[ "$CASE" != success ] || printf 'REPLAY_NONCE=%s\n' "$nonce"
		printf 'pass: %s: generated gate published; real guard accepted the contract-verified record and consumed nonce and ACK; one-shot retry refused\n' "$CASE"
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
		[ "$i" -lt 300 ] || fail "$CASE guard did not independently request recovery"
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
	case "$2" in success|partial|invalid|interrupt|post-interrupt|dead-watcher|replay|late|premature|no-record|bad-record|record-mode|record-symlink|record-links|record-foreign|record-order|record-malformed|panel-absent|panel-record-absent|panel-foreign|panel-conflict|panel-malformed|panel-mode|panel-symlink|panel-links|contract-missing|contract-corrupt|contract-mode|contract-symlink|contract-links|ready-mode|ready-symlink|ready-links|ready-nonce|ready-boot|ready-newline|staging|staging-record-invalid|gate-staging|preplanted-multilink|full-success|full-radio-fail|full-invalid|full-route-cache-success|full-route-cache-internet-dev|full-route-cache-internet-extra|full-route-cache-dns-dev|full-route-cache-dns-extra|full-unpinned-success) CASE=$2;; *) fail 'invalid case';; esac
	"$BB" mount --make-rprivate / || fail 'cannot privatize mounts'
	MAIN_NUMS=$HOST_MAIN_NUMS
	"$BB" mount -t tmpfs -o mode=0700,size=32m tmpfs /run || fail 'private staging run'
	"$BB" cp "$HOST_WORK/gate" /run/gate
	case "$CASE" in
		full-*) "$BB" cp "$HOST_WORK/full-radio" /run/radio;;
		*) "$BB" cp "$HOST_WORK/radio" /run/radio;;
	esac
	"$BB" cp "$HOST_WORK/derived-post" /run/derived-post
	case "$CASE" in
		full-route-cache-*) "$BB" cp "$HOST_WORK/candidate-post" /run/candidate-post;;
		full-unpinned-*) "$BB" cp "$HOST_WORK/unpinned-post" /run/candidate-post;;
	esac
	"$BB" cp "$HOST_WORK/replay-nonce" /run/replay-nonce
	case "$CASE" in
		dead-watcher|post-interrupt)
			"$BB" cp "$HOST_WORK/pidfd-signal" /run/pidfd-signal
			[ "$(hash /run/pidfd-signal)" = "$HOST_PIDFD_SHA" ] || fail 'pidfd helper copy changed';;
	esac
	"$BB" cp "$HOST_SCRIPT" /run/test.sh
	"$BB" cp "$HOST_GUARD" /run/guard.sh
	"$BB" cp "$HOST_CONTRACT" /run/pmos-root-contract.sh
	[ "$(hash /run/guard.sh)" = "$GUARD_SHA" ] && [ "$(hash /run/pmos-root-contract.sh)" = "$CONTRACT_SHA" ] || fail 'guard or root contract pin changed'
	"$BB" mount -t tmpfs -o mode=0700,size=64m tmpfs /tmp || fail 'private staging tmp'
	"$BB" mkdir /tmp/initial
	"$BB" mount -t tmpfs -o mode=0755,size=32m tmpfs /tmp/initial || fail 'initial tmpfs'
	R=/tmp/initial
	"$BB" mkdir -p "$R/bin" "$R/oldroot" "$R/guest" "$R/proc" "$R/dev" "$R/sys/class/block/sda13"
	"$BB" printf 'PARTNAME=userdata\n' > "$R/sys/class/block/sda13/uevent"
	"$BB" printf '%s\n' "$MAIN_NUMS" > "$R/sys/class/block/sda13/dev"
	"$BB" printf '%s\n' 524288 > "$R/sys/class/block/sda13/size"
	"$BB" mount -t tmpfs -o mode=0755,size=1m tmpfs /dev || fail 'private fixture dev'
	"$BB" mknod -m 666 /dev/null c 1 3
	"$BB" mknod -m 666 /dev/urandom c 1 9
	"$BB" mkdir -p /dev/block
	"$BB" mknod -m 0400 /dev/block/sda13 b "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}"
	"$BB" mount -t ext4 -o rw /dev/block/sda13 "$R/guest" || fail 'isolated ext4 guest mount'
	"$BB" mount --make-private "$R/guest"
	"$BB" find "$R/guest" -mindepth 1 -maxdepth 1 ! -name lost+found -exec "$BB" rm -rf -- {} +
	"$BB" cp /run/pmos-root-contract.sh "$R/pmos-root-contract.sh"
	"$BB" cp /bin/busybox "$R/bin/busybox"
	"$BB" cp /run/guard.sh "$R/guard.sh"
	"$BB" touch "$R/init"
	"$BB" mount -t proc -o nosuid,nodev,noexec proc "$R/proc" || fail 'initial proc'
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
		full-route-cache-*)
			"$BB" cp /run/candidate-post "$G/derived-post"
			[ "$(hash "$G/derived-post")" = 92f6f9cdfa3dcdc8854c7481fe01b500591f1b2b1c9908e97c4cdbfc0ae68d0c ] || fail 'candidate post copy changed';;
		full-unpinned-*)
			"$BB" cp /run/candidate-post "$G/derived-post"
			[ "$(hash "$G/derived-post")" = "$HOST_UNPINNED_POST_SHA" ] || fail 'unpinned candidate post copy changed';;
		full-*)
			"$BB" cp /run/derived-post "$G/derived-post"
			[ "$(hash "$G/derived-post")" = 113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3 ] || fail 'derived post copy changed';;
	esac
	case "$CASE" in
		dead-watcher|post-interrupt)
			"$BB" cp /run/pidfd-signal "$G/pidfd-signal"
			"$BB" chmod 700 "$G/pidfd-signal"
			[ "$(hash "$G/pidfd-signal")" = "$HOST_PIDFD_SHA" ] || fail 'guest pidfd helper changed';;
	esac
	"$BB" mkdir -p "$G/dev/block" "$G/sys/class/block/sda13"
	"$BB" mknod -m 0400 "$G/dev/block/sda13" b "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}"
	"$BB" printf 'PARTNAME=userdata\n' > "$G/sys/class/block/sda13/uevent"
	"$BB" printf '%s\n' "$MAIN_NUMS" > "$G/sys/class/block/sda13/dev"
	"$BB" printf '%s\n' 524288 > "$G/sys/class/block/sda13/size"
	"$BB" cp /run/pmos-root-contract.sh "$G/run/pmos-root-contract.sh"
	"$BB" cp /run/radio "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
	"$BB" chmod 700 "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
	case "$CASE" in
		full-*) [ "$(hash "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh")" = 146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14 ] || fail 'canonical radio copy changed';;
	esac
	case "$CASE" in
		full-unpinned-*)
			"$BB" printf '\n: mb003-unpinned-synthetic-edit\n' >> "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
			"$BB" cp "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh" "$G/run/edited-radio"
			[ "$(hash "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh")" != 146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14 ] &&
				[ "$(hash "$G/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh")" != d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3 ] || fail 'edited synthetic radio hash invalid';;
	esac
	"$BB" cat > "$G/run/mock" <<'MOCK'
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
	ln)
		if [ "$#" = 3 ] && [ "$2" = /run/pid1-guard/.success-gated-ack-new ] && [ "$3" = /run/pid1-guard/ack ]; then
			case "$("$b" cat /run/case)" in
				gate-staging)
					"$b" ln "$2" "$3" || exit 1
					"$b" touch /run/link-barrier
					while [ ! -f /run/link-release ]; do "$b" sleep 0.1; done
					exit 0;;
				preplanted-multilink)
					[ -f /run/pid1-guard/success-ready ] && [ "$("$b" stat -c '%u:%a:%h' /run/pid1-guard/success-ready)" = 0:600:1 ] || exit 1
					(umask 077; set -C; "$b" cat /run/pid1-guard/success-ready > /run/pid1-guard/preplanted-ack) || exit 1
					"$b" ln /run/pid1-guard/preplanted-ack "$3" || exit 1
					"$b" sleep 2
					[ ! -e /run/pid1-guard/accepted ] && [ ! -e /run/pid1-guard/recovery-request ] || exit 1
					exec "$b" ln "$2" "$3";;
			esac
		fi;;
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
	'-4 route get 1.1.1.1 from 192.0.2.2'|'-4 route get 192.0.2.53 from 192.0.2.2')
		fixture=$(/bin/busybox cat /run/case)
		case "$fixture" in
			full-route-cache-*)
				case "$4" in 1.1.1.1) stage=internet;; 192.0.2.53) stage=dns;; *) exit 1;; esac
				dev=wlan0
				continuation='    cache '
				case "$fixture:$stage" in
					full-route-cache-internet-dev:internet|full-route-cache-dns-dev:dns) dev=eth0;;
					full-route-cache-internet-extra:internet|full-route-cache-dns-extra:dns) continuation='    cache extra';;
				esac
				/bin/busybox printf '%s\n' "$stage" >> /run/route-requests
				/bin/busybox printf '%s\n' "$4 from 192.0.2.2 via 192.0.2.1 dev $dev uid 0 " "$continuation" | /bin/busybox tee "/run/route-$stage-reply";;
			*) /bin/busybox printf '%s\n' '192.0.2.1 dev wlan0 src 192.0.2.2';;
		esac;;
	*) exit 1;;
esac
IP
	"$BB" chmod 700 "$G/sbin/rc-service" "$G/usr/sbin/iw" "$G/sbin/ip"
	"$BB" cat > "$G/boot-record-setup.sh" <<'REC'
#!/bin/busybox sh
set -eu
BB=/bin/busybox
. /run/pmos-root-contract.sh
boot=$($BB cat /proc/sys/kernel/random/boot_id)
panel="usb-init: pre-SSH panel node=boe card0=1 boot $boot"
if [ "${PANEL_EVIDENCE:-present}" = present ]; then
	(umask 077; set -C; $BB printf '%s\n' "$panel" > /run/pmos-pre-ssh-panel.record)
	[ -f /run/pmos-pre-ssh-panel.record ] && [ ! -L /run/pmos-pre-ssh-panel.record ] &&
		[ "$($BB stat -c '%u:%a:%h' /run/pmos-pre-ssh-panel.record)" = 0:600:1 ] &&
		[ "$($BB cat /run/pmos-pre-ssh-panel.record)" = "$panel" ]
fi
boot_record_open /
boot_record_append / "pmos-self-stage: diagnostic hold and :22 verified on boot $boot"
if [ "${PANEL_EVIDENCE:-present}" = present ]; then
	boot_record_append / "$panel"
fi
boot_record_append / 'pmos-stage: using unpacked persistent postmarketOS root'
boot_record_append / 'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts'
boot_record_append / 'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)'
boot_record_append / 'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)'
boot_record_append / 'pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract'
boot_record_append / 'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request'
boot_record_append / 'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover'
boot_record_append / "pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $boot"
boot_record_append / 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'
boot_record_verify / 'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init'
if [ "${FULL_POST:-0}" != 1 ]; then
	boot_record_append / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"
	boot_record_verify / "pmos-self-post: post-cutover PID 1 on boot $boot; guard identity check passed; pid1 identity check passed"
fi
REC
	"$BB" chmod 700 "$G/boot-record-setup.sh"
	"$BB" cat > "$G/gate-runner" <<'PREAMBLE'
#!/bin/busybox sh
set -eu
BB=/run/tool
STATE=/run/radio-bringup
GUARD=/run/pid1-guard
RADIO=/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh
RADIO_SHA=f2dc583067ee309059ab3b76f1253aa4261d3f4599b066f64b32b02a0cdae65b
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
	"$BB" mkdir -p /dev/block
	"$BB" mknod -m 0400 /dev/block/sda13 b "${MAIN_NUMS%%:*}" "${MAIN_NUMS##*:}"
	"$BB" umount -l /oldroot || fail 'cannot detach host root'
	case "$CASE" in
		full-invalid|full-route-cache-internet-*|full-route-cache-dns-*) TEST_BUDGET=20;;
		full-radio-fail) TEST_BUDGET=15;;
		full-success|full-route-cache-success|full-unpinned-success) TEST_BUDGET=30;;
		success|panel-absent|gate-staging|post-interrupt|preplanted-multilink) TEST_BUDGET=30;;
		dead-watcher) TEST_BUDGET=10;;
		*) TEST_BUDGET=18;;
	esac
	TEST_ARM_UPTIME=$("$BB" awk '{print int($1)}' /proc/uptime)
	export TEST_BUDGET TEST_ARM_UPTIME MOCK_SHA
	"$BB" sh /guard.sh mock-arm /guest "$TEST_BUDGET" /guest/run/mock "$MOCK_SHA" || fail 'real mock guard did not arm'
	[ "$(hash /guest/run/pid1-guard/guard.sh)" = "$GUARD_SHA" ] && [ ! -e /guest/run/pid1-guard/nonce ] || fail 'guard copy changed or minted before switch'
	case "$CASE" in
		contract-missing) "$BB" rm /guest/run/pid1-guard/root-contract.sh;;
		contract-corrupt) "$BB" printf '\n' >> /guest/run/pid1-guard/root-contract.sh;;
		contract-mode) "$BB" chmod 644 /guest/run/pid1-guard/root-contract.sh;;
		contract-symlink) "$BB" mv /guest/run/pid1-guard/root-contract.sh /guest/run/contract-link-target; "$BB" ln -s /run/contract-link-target /guest/run/pid1-guard/root-contract.sh;;
		contract-links) "$BB" ln /guest/run/pid1-guard/root-contract.sh /guest/run/pid1-guard/contract-link;;
	esac
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

ROUTE_CACHE_ONLY=0
UNPINNED_ONLY=0
case "$#:${1:-}" in
	0:) :;;
	1:--route-cache-only) ROUTE_CACHE_ONLY=1;;
	1:--unpinned-only) UNPINNED_ONLY=1;;
	*) fail 'usage: test-pmos-success-gate-guard.sh [--route-cache-only|--unpinned-only]';;
esac
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=$HERE/test-pmos-success-gate-guard.sh
[ "$(hash "$HERE/pmos-pid1-guard.sh")" = "$GUARD_SHA" ] || fail 'guard pin changed'
[ "$(hash "$HERE/pmos-root-contract.sh")" = "$CONTRACT_SHA" ] || fail 'root contract pin changed'
[ "$("$BB" uname -m)" != aarch64 ] || fail 'guard mock requires a non-aarch64 host'
[ -f "$BB" ] && [ ! -L "$BB" ] || fail 'native BusyBox must be a regular executable'
export PATH="/usr/sbin:/sbin:$PATH"
for tool in python3 aarch64-linux-gnu-gcc cc sudo unshare timeout truncate mke2fs losetup; do command -v "$tool" >/dev/null 2>&1 || fail "missing $tool"; done
sudo -n true || fail 'passwordless sudo required'
WORK=$(mktemp -d /tmp/pmos-success-gate.XXXXXXXX)
MAIN_DEV=
cleanup() {
	[ -z "$MAIN_DEV" ] || sudo -n losetup -d "$MAIN_DEV" >/dev/null 2>&1 || true
	rm -rf -- "$WORK"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
WORK_DISK=$WORK/userdata.img
truncate -s 268435456 "$WORK_DISK"
mke2fs -q -F -t ext4 -b 4096 "$WORK_DISK"
MAIN_DEV=$(sudo -n losetup --find --show "$WORK_DISK")
MAIN_NUMS="$((0x$(stat -c %t "$MAIN_DEV"))):$((0x$(stat -c %T "$MAIN_DEV")))"
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
import ast
import base64
import hashlib
import importlib.util
import os
import pathlib
import sys
import textwrap
here = pathlib.Path(os.environ['HERE'])
sys.path.insert(0, str(here))
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
persist = load('persist', 'derive-radio-persistent.py')
fresh = load('fresh', 'derive-radio-fresh-boot.py')
gen = load('gate_gen', 'derive-success-gated-ack.py')
builder = load('builder', 'build-init-boot-persistent-root.py')
radio = fresh.derive(persist.derive((here / 'pmos-radio-bringup.sh').read_text()))
probe = gen.build_dns_probe()
encoded = '\n'.join(textwrap.wrap(base64.b64encode(probe).decode('ascii'), 96))
gate = gen.GATE.replace('@DNS_BASE64@', encoded).replace('@DNS_SHA@', gen.sha(probe))
if '$GUARD/success-ready' not in gate or '$GUARD/.success-ready-new' not in gate:
    raise SystemExit('real generated gate does not publish success-ready')
selfpost = load('selfpost', 'derive-self-post-fresh-boot.py')
staged = builder.current_scripts()['pmos-radio-bringup.sh']
if gen.sha(staged) != 'f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f':
    raise SystemExit('builder staged radio pin changed')
full_radio = fresh.derive(persist.derive(staged.decode()))
if gen.sha(full_radio.encode()) != '146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14':
    raise SystemExit('canonical fresh radio pin changed')
prefix, _ = selfpost.derive((here / 'pmos-self-post.sh').read_text(), full_radio.encode())
post, hook = gen.derive(prefix, full_radio.encode(), probe)
if (gen.sha(post.encode()) != '113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3' or
        gen.sha(hook.encode()) != '3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67'):
    raise SystemExit('canonical generated post or hook pin changed')
if post.count('\nBB=/bin/busybox\n') != 1:
    raise SystemExit('canonical post BB assignment changed')
route_cache = load('route_cache', 'derive-route-cache-gated-ack.py')
candidate_post, candidate_hook = route_cache.derive(post.encode(), hook.encode())
if (gen.sha(candidate_post) != '92f6f9cdfa3dcdc8854c7481fe01b500591f1b2b1c9908e97c4cdbfc0ae68d0c' or
        gen.sha(candidate_hook) != '5bc5b0f4e2820aef8ae11b5b3e1f9264a0c7fe5fc60f8686718fb955b376fc3a'):
    raise SystemExit('route-cache candidate post or hook pin changed')
if candidate_post.count(b'\nBB=/bin/busybox\n') != 1:
    raise SystemExit('route-cache candidate post BB assignment changed')
unpinned_tree = ast.parse((here / 'build-init-boot-mb003-unpinned.py').read_text())
unpinned_assigns = {'BAD_RADIO', 'VARIANT_MSG'}
unpinned_funcs = {'sha', 'replace_count', 'unpinned_post'}
unpinned_body = [node for node in unpinned_tree.body
                 if (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                     isinstance(node.targets[0], ast.Name) and node.targets[0].id in unpinned_assigns) or
                 (isinstance(node, ast.FunctionDef) and node.name in unpinned_funcs)]
if len(unpinned_body) != len(unpinned_assigns) + len(unpinned_funcs):
    raise SystemExit('unpinned candidate post interface definitions changed')
unpinned_ns = {'hashlib': hashlib, 'canonical': builder, 'require': builder.require}
exec(compile(ast.Module(body=unpinned_body, type_ignores=[]), 'mb003-unpinned-post-interface', 'exec'), unpinned_ns)
unpinned_bad_radio = unpinned_ns['BAD_RADIO']
unpinned_post = unpinned_ns['unpinned_post'](builder.runtime_scripts()[builder.FRESH_POST])
if (unpinned_bad_radio != 'd7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3' or
        b'RADIO_SHA=' in unpinned_post or unpinned_post.count(b'\nBB=/bin/busybox\n') != 1 or
        unpinned_bad_radio.encode() in unpinned_post or b'radio_snapshot' in unpinned_post or
        b'omnipha-radio-snapshot' in unpinned_post or b'radio snapshot' in unpinned_post or
        unpinned_post.count(b'\nRADIO="/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"\n') != 1 or
        unpinned_post.count(b'$BB sh "$RADIO" "$boot" "$stage" "$marker" || die "radio bring-up $stage failed"\n') != 1 or
        unpinned_post.count(b'$BB sh "$RADIO" "$boot" services "$marker" < "$PROFILE" || die \'radio bring-up services failed\'\n') != 1):
    raise SystemExit('unpinned candidate post direct radio launch interface changed')
work = pathlib.Path(os.environ['WORK'])
(work / 'gate').write_text(gate)
(work / 'radio').write_text(radio)
(work / 'full-radio').write_text(full_radio)
(work / 'derived-post').write_text(post)
(work / 'candidate-post').write_bytes(candidate_post)
(work / 'unpinned-post').write_bytes(unpinned_post)
(work / 'replay-nonce').write_text('none\n')
PY
sh -n "$WORK/gate" || fail 'generated gate syntax'
sh -n "$WORK/derived-post" || fail 'generated full post syntax'
sh -n "$WORK/full-radio" || fail 'canonical fresh radio syntax'
sh -n "$WORK/candidate-post" || fail 'candidate full post syntax'
sh -n "$WORK/unpinned-post" || fail 'unpinned candidate post syntax'
HOST_UNPINNED_POST_SHA=$(hash "$WORK/unpinned-post")
printf '%s\n' 'fixture: isolated loop-backed ext4 with synthetic userdata identity; real contract open/append/verify builds each ordered stage; external stage observations and panel evidence are synthetic'
printf '%s\n' 'fixture: gate-only cases run the generated gate suffix; full cases also run the self-post prefix with simulated radio-stage invocations'
printf '%s\n' 'fixture: full cases execute the pinned canonical post, the separately derived route-cache candidate or the generated mb003 unpinned candidate with only its BB line redirected; guard, identity, ACK/ready, ordered-record and marker file operations pass to real BusyBox'
printf '%s\n' 'fixture: mocked radio/process/service evidence, selected hashes, kmsg, network commands, actual-style route-cache replies and DNS result; real probe bytes are checked but not executed'
printf '%s\n' 'fixture: dead-watcher uses pidfd SIGKILL; post-interrupt pauses the real watcher and barriers the publisher after single-link ACK publication'
HOST_mnt_NS=$(readlink /proc/self/ns/mnt)
HOST_pid_NS=$(readlink /proc/self/ns/pid)
HOST_net_NS=$(readlink /proc/self/ns/net)
run_case() {
	sudo -n timeout -k 5 150 unshare --mount --pid --net --fork --kill-child --mount-proc \
		env -i HOST_mnt_NS="$HOST_mnt_NS" HOST_pid_NS="$HOST_pid_NS" HOST_net_NS="$HOST_net_NS" \
		HOST_WORK="$WORK" HOST_SCRIPT="$SCRIPT" HOST_GUARD="$HERE/pmos-pid1-guard.sh" \
		HOST_CONTRACT="$HERE/pmos-root-contract.sh" HOST_MAIN_NUMS="$MAIN_NUMS" HOST_PIDFD_SHA="$HOST_PIDFD_SHA" \
		HOST_UNPINNED_POST_SHA="$HOST_UNPINNED_POST_SHA" \
		/bin/busybox sh "$SCRIPT" --inner "$1"
}
if [ "$UNPINNED_ONLY" = 1 ]; then
	run_case full-unpinned-success || fail 'full-unpinned-success isolated fixture'
	printf '%s\n' 'pass: mb003 unpinned candidate direct persistent radio launch in host-only isolated ext4 switch_root; real guard, nonce and ACK; radio stages and external evidence were mocked; no device or BAD_RADIO radio'
	exit 0
fi
if [ "$ROUTE_CACHE_ONLY" = 0 ]; then
	for case in full-radio-fail full-success full-invalid; do run_case "$case" || fail "$case isolated fixture"; done
fi
for case in full-route-cache-success full-route-cache-internet-dev full-route-cache-internet-extra full-route-cache-dns-dev full-route-cache-dns-extra; do run_case "$case" || fail "$case isolated fixture"; done
if [ "$ROUTE_CACHE_ONLY" = 1 ]; then
	printf '%s\n' 'pass: route-cache candidate cases in host-only isolated ext4 switch_root; external evidence was synthetic'
	exit 0
fi
run_case full-unpinned-success || fail 'full-unpinned-success isolated fixture'
result=$(run_case success) || fail 'isolated success case'
nonce=$(printf '%s\n' "$result" | "$BB" awk -F= '/^REPLAY_NONCE=/ {print $2}')
case "$nonce" in ????????????????????????????????????????????????????????????????) case "$nonce" in *[!0-9a-f]*) fail 'invalid captured nonce';; esac;; *) fail 'missing captured nonce';; esac
printf '%s\n' "$nonce" > "$WORK/replay-nonce"
printf '%s\n' "$result" | "$BB" grep -v '^REPLAY_NONCE='
for case in premature no-record bad-record record-mode record-symlink record-links record-foreign record-order record-malformed panel-absent panel-record-absent panel-foreign panel-conflict panel-malformed panel-mode panel-symlink panel-links contract-missing contract-corrupt contract-mode contract-symlink contract-links ready-mode ready-symlink ready-links ready-nonce ready-boot ready-newline staging staging-record-invalid gate-staging preplanted-multilink; do run_case "$case" || fail "$case isolated fixture"; done
for case in partial invalid interrupt post-interrupt dead-watcher replay late; do run_case "$case" || fail "$case isolated fixture"; done
printf '%s\n' 'pass: host-only isolated ext4 switch_root; digest-pinned guard and real generated gate; real ordered-record contract; mocked external evidence; no network or physical device'
printf '%s\n' 'pass: full cases run the generated post with simulated radio stages; the real guard accepts success and requests mock recovery at the real deadline on failure'
printf '%s\n' 'pass: unpinned case runs the builder unpinned_post transform with an edited synthetic radio through the direct persistent path; builder packaging, installer, images and device access are not exercised'
