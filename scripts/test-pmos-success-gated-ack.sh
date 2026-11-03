#!/bin/sh
set -eu

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" != --inner ]; then
	[ "$#" -eq 0 ] || { printf 'usage: %s\n' "$0" >&2; exit 1; }
	work=$(mktemp -d "${TMPDIR:-/tmp}/success-gate-294.XXXXXXXX")
	chmod 755 "$work"
	trap 'rm -rf "$work"' EXIT
	python3 -B "$HERE/test-derive-success-gated-ack.py" "$work"
	mkdir "$work/root"
	sudo -n unshare --mount --pid --fork --net --mount-proc /bin/busybox sh "$0" --inner "$work"
	exit 0
fi

[ "$#" -eq 2 ] && [ "$$" -eq 1 ] || { printf 'inner fixture requires its private PID namespace\n' >&2; exit 1; }
BB=/bin/busybox
WORK=$2
R=$WORK/root
[ -d "$WORK" ] && [ ! -L "$WORK" ] && [ -d "$R" ] && [ ! -L "$R" ] || exit 1
boot=11111111-2222-3333-4444-555555555555
nonce=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
stages='nonce-and-radio-markers radio-health services association address route gateway internet dns final-health all-checks'
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
$BB mount --make-rprivate /
$BB mount -t tmpfs -o mode=0755,size=96m tmpfs "$R"
BASE=$R/base
ROOT=$R/case
$BB mkdir -p "$BASE/bin" "$BASE/real" "$BASE/dev" "$BASE/tmp" \
	"$BASE/usr/libexec/omnipha" "$BASE/usr/sbin" "$BASE/sbin" \
	"$BASE/run/radio-bringup" "$BASE/run/pid1-guard" "$BASE/run/openrc" \
	"$BASE/proc/sys/kernel/random" "$BASE/proc/1" "$BASE/proc/42" "$BASE/proc/43" "$BASE/proc/net" \
	"$BASE/sys/class/remoteproc/remoteproc2" "$BASE/sys/class/remoteproc/remoteproc3" \
	"$BASE/sys/class/net/wlan0" "$BASE/sys/class/ieee80211/phy0" "$BASE/sys/class/uio/uio0" \
	"$BASE/sys/module/qca_cld3_qca6750" "$BASE/etc/network" "$BASE/etc/conf.d" \
	"$BASE/etc/wpa_supplicant" "$BASE/etc/init.d"
for level in sysinit boot default nonetwork shutdown; do $BB mkdir -p "$BASE/etc/runlevels/$level"; done
$BB cp /bin/busybox "$BASE/real/busybox"
$BB cp "$WORK/post" "$BASE/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/radio" "$BASE/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB cp "$WORK/hook" "$BASE/hook"
$BB chmod 700 "$BASE/hook" "$BASE/usr/libexec/omnipha/"*.sh "$BASE/run" "$BASE/run/radio-bringup" "$BASE/run/pid1-guard"
$BB mknod -m 666 "$BASE/dev/null" c 1 3
$BB mknod -m 666 "$BASE/dev/zero" c 1 5
$BB touch "$BASE/dev/kmsg"
$BB chmod 666 "$BASE/dev/kmsg"
$BB printf '%s\n' "$boot" > "$BASE/proc/sys/kernel/random/boot_id"
$BB printf '%s\n' "$boot" > "$BASE/run/pid1-guard/armed"
$BB printf '%s\n' "$nonce" > "$BASE/run/pid1-guard/nonce"
$BB printf 'tmpfs / tmpfs rw 0 0\ntmpfs /run tmpfs rw 0 0\n' > "$BASE/proc/1/mounts"
$BB ln -s / "$BASE/proc/1/root"
$BB ln -s /bin/busybox "$BASE/proc/1/exe"
$BB ln -s / "$BASE/proc/43/root"
$BB printf 'rmtfs\n' > "$BASE/proc/42/comm"
$BB printf 'synthetic rmtfs executable\n' > "$BASE/proc/42/exe"
$BB printf 'synthetic mapping /dev/uio0\n' > "$BASE/proc/42/maps"
$BB printf 'dropbear\000-s\000-g\000-j\000-k\000-E\000-r\000/etc/dropbear/session_host_key\000-p\000172.16.42.2:2222\000-P\000/run/dropbear-session.pid\000' > "$BASE/proc/43/cmdline"
$BB printf ' 0: 022A10AC:08AE 00000000:0000 0A\n' > "$BASE/proc/net/tcp"
$BB printf '4080000.remoteproc-mss\n' > "$BASE/sys/class/remoteproc/remoteproc2/name"
$BB printf '9bb00000.remoteproc-wpss\n' > "$BASE/sys/class/remoteproc/remoteproc3/name"
$BB printf 'running\n' > "$BASE/sys/class/remoteproc/remoteproc2/state"
$BB printf 'running\n' > "$BASE/sys/class/remoteproc/remoteproc3/state"
$BB printf 'rmtfs\n' > "$BASE/sys/class/uio/uio0/name"
$BB printf '42\n' > "$BASE/run/radio-bringup/rmtfs.pid"
$BB printf '43\n' > "$BASE/run/dropbear-session.pid"
$BB printf 'default\n' > "$BASE/run/openrc/softlevel"
$BB touch "$BASE/run/keep"
$BB printf 'synthetic profile\n' > "$BASE/run/radio-bringup/wpa_supplicant.conf"
$BB cp "$BASE/run/radio-bringup/wpa_supplicant.conf" "$BASE/etc/wpa_supplicant/wpa_supplicant.conf"
$BB printf 'auto wlan0\niface wlan0 inet dhcp\n\tdhcp-script /run/radio-bringup/lease-wrapper.sh\n\tudhcpc-opts -t 5 -T 3 -A 5 -n\n' > "$BASE/etc/network/interfaces"
$BB printf 'ifquery=/run/radio-bringup/ifquery-wlan\n' > "$BASE/etc/conf.d/networking"
$BB printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan0"\n' > "$BASE/etc/conf.d/wpa_supplicant"
$BB printf '#!/bin/busybox sh\nIP_CMD=/sbin/ip\nexport IP_CMD\nexec /bin/busybox sh /run/radio-bringup/wlan-udhcpc-lease.sh "$@"\n' > "$BASE/run/radio-bringup/lease-wrapper.sh"
$BB printf '#!/bin/busybox sh\nif [ "$#" = 4 ] && [ "$1" = -i ] && [ "$2" = /etc/network/interfaces ] && [ "$3" = --list ] && [ "$4" = -a ]; then /bin/busybox printf "wlan0\\n"; exit 0; fi\nexec /sbin/ifquery "$@"\n' > "$BASE/run/radio-bringup/ifquery-wlan"
$BB printf 'synthetic lease helper\n' > "$BASE/run/radio-bringup/wlan-udhcpc-lease.sh"
$BB printf 'nameserver 192.0.2.53\n' > "$BASE/etc/resolv.conf"
for service in local networking wpa_supplicant; do
	$BB printf 'synthetic service %s\n' "$service" > "$BASE/etc/init.d/$service"
	$BB ln -s "/etc/init.d/$service" "$BASE/etc/runlevels/default/$service"
done
$BB chmod 600 "$BASE/run/keep" "$BASE/run/pid1-guard/armed" "$BASE/run/pid1-guard/nonce" \
	"$BASE/run/radio-bringup/rmtfs.pid" "$BASE/run/radio-bringup/wpa_supplicant.conf" \
	"$BASE/etc/wpa_supplicant/wpa_supplicant.conf" "$BASE/etc/network/interfaces" \
	"$BASE/etc/conf.d/networking" "$BASE/etc/conf.d/wpa_supplicant"
$BB chmod 700 "$BASE/run/radio-bringup/ifquery-wlan" "$BASE/run/radio-bringup/lease-wrapper.sh" "$BASE/run/radio-bringup/wlan-udhcpc-lease.sh"
panel="usb-init: pre-SSH panel node=boe card0=1 dsi1=1 dcs=none reset=none suspend=clear brightness=0 boot $boot"
$BB printf 'boot %s\npre\n%s\n' "$boot" "$panel" > "$BASE/.omnipha-boot-record"
$BB chmod 600 "$BASE/.omnipha-boot-record"
$BB cp "$BASE/.omnipha-boot-record" "$BASE/tmp/synthetic-record.before"
$BB printf '%s\n' "$panel" > "$BASE/run/pmos-pre-ssh-panel.record"
$BB chmod 600 "$BASE/run/pmos-pre-ssh-panel.record"
$BB printf '<12>usb-init: %s\n' "$panel" > "$BASE/tmp/dmesg"
$BB cat > "$BASE/run/pmos-root-contract.sh" <<'CONTRACT'
boot_record_id() { return 0; }
boot_record_append() { /real/busybox printf '%s\n' "$2" >> /tmp/synthetic-contract-events; }
boot_record_verify() { /real/busybox grep -qF "$2" /tmp/synthetic-contract-events; }
CONTRACT
$BB chmod 700 "$BASE/run/pmos-root-contract.sh"
$BB cat > "$BASE/bin/busybox" <<'MOCK'
#!/real/busybox sh
BB=/real/busybox
mode=$($BB cat /tmp/mode)
if [ "${1:-}" = setsid ]; then
	printf 'launch\n' >> /tmp/hook-launches
	[ "${2:-}" = /bin/busybox ] && [ "${3:-}" = sh ] && [ "${4:-}" = /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh ] && [ "$#" = 4 ] || exit 1
	$BB touch /tmp/hook-at-barrier
	count=0
	while [ ! -f /tmp/hook-release ]; do
		[ "$count" -lt 200 ] || { $BB touch /tmp/hook-barrier-timeout; exit 1; }
		$BB sleep 0.1
		count=$((count + 1))
	done
	if [ "$mode" = hook-noop ]; then
		printf '0\n' > /tmp/hook-post-result.new
		$BB mv /tmp/hook-post-result.new /tmp/hook-post-result
		exit 0
	fi
	$BB setsid "$2" "$3" "$4" &
	child=$!
	printf '%s\n' "$child" > /tmp/post.pid
	if wait "$child"; then result=0; else result=$?; fi
	printf '%s\n' "$result" > /tmp/hook-post-result.new
	$BB mv /tmp/hook-post-result.new /tmp/hook-post-result
	exit "$result"
fi
state=/run/radio-bringup
guard=/run/pid1-guard
gate=$state/success-gate-294
mutate() {
	case "$mode" in
		state-mode) $BB chmod 755 "$state";;
		run-mode) $BB chmod 755 /run;;
		run-mount) $BB printf 'tmpfs / tmpfs rw 0 0\n' > /proc/1/mounts;;
		radio-changed) $BB printf '\n' >> /usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh;;
		guard-mode) $BB chmod 755 "$guard";;
		wrong-boot) $BB printf '00000000-0000-0000-0000-000000000000\n' > /proc/sys/kernel/random/boot_id;;
		wrong-armed) $BB printf '00000000-0000-0000-0000-000000000000\n' > "$guard/armed";;
		wrong-root) $BB printf '9:9\n' > "$guard/root-identity";;
		pid1-exe) $BB rm /proc/1/exe; $BB ln -s /real/busybox /proc/1/exe;;
		nonce-partial) $BB printf 'abc\n' > "$guard/nonce";;
		nonce-invalid) $BB printf '%064d\n' 0 | $BB tr 0 g > "$guard/nonce";;
		nonce-mode) $BB chmod 644 "$guard/nonce";;
		nonce-symlink) $BB mv "$guard/nonce" "$guard/nonce-original"; $BB ln -s nonce-original "$guard/nonce";;
		staging-other) $BB touch "$guard/.ack-new";;
		pending-ack) $BB printf 'synthetic invalid ack\n' > "$guard/ack";;
		pending-accepted) $BB printf 'synthetic invalid accepted\n' > "$guard/accepted";;
		marker-partial) $BB printf 'partial\n' > "$state/modem.marker";;
		marker-replay) $BB printf 'guest-radio-modem-deadbeefdeadbeef\n' > "$state/modem.marker";;
		marker-symlink) $BB mv "$state/modem.marker" "$state/other.marker"; $BB ln -s other.marker "$state/modem.marker";;
		remoteproc) $BB printf 'offline\n' > /sys/class/remoteproc/remoteproc2/state;;
		remoteproc-name) $BB printf 'wrong\n' > /sys/class/remoteproc/remoteproc3/name;;
		wlan-missing) $BB rmdir /sys/class/net/wlan0;;
		rmtfs-mode) $BB chmod 644 "$state/rmtfs.pid";;
		rmtfs-partial) $BB printf 'bad\n' > "$state/rmtfs.pid";;
		rmtfs-maps) $BB printf 'wrong\n' > /proc/42/maps;;
		profile-differs) $BB printf 'other profile\n' > /etc/wpa_supplicant/wpa_supplicant.conf;;
		service-input) $BB chmod 644 /etc/network/interfaces;;
		missing-ifquery) $BB rm "$state/ifquery-wlan";;
		missing-lease-wrapper) $BB rm "$state/lease-wrapper.sh";;
		missing-lease-helper) $BB rm "$state/wlan-udhcpc-lease.sh";;
		openrc-level) $BB printf 'boot\n' > /run/openrc/softlevel;;
		service-config) $BB printf 'other\n' > /etc/conf.d/networking;;
		supplicant-unsafe) $BB chmod 666 /etc/conf.d/wpa_supplicant;;
		runlevel-unsafe) $BB rmdir /etc/runlevels/nonetwork;;
		service-link) $BB rm /etc/runlevels/default/networking; $BB ln -s /wrong /etc/runlevels/default/networking;;
		foreign-service) $BB touch /etc/runlevels/boot/foreign;;
		ssh-pid) $BB rm /run/dropbear-session.pid;;
		ssh-pid-invalid) $BB printf 'bad\n' > /run/dropbear-session.pid;;
		ssh-command) $BB printf 'wrong\000' > /proc/43/cmdline;;
		ssh-listener) $BB printf 'invalid\n' > /proc/net/tcp;;
		resolver-invalid) $BB printf 'nameserver 127.0.0.1\n' > /etc/resolv.conf;;
		resolver-partial) $BB printf 'nameserver\n' > /etc/resolv.conf;;
		gate-exists) $BB mkdir -m 700 "$gate";;
		staging-stale) $BB printf 'stale\n' > "$guard/.success-gated-ack-new";;
	esac
}
case "${1:-}" in
	mkdir)
		if [ "${2:-}" = -m ] && [ "${3:-}" = 700 ] && [ "${4:-}" = "$gate" ]; then
			$BB mkdir "$2" "$3" "$4" || exit 1
			case "$mode" in
				gate-unsafe) $BB chmod 755 "$gate";;
				start-evidence) $BB touch "$gate/started";;
				kmsg-path) $BB touch "$gate/kmsg";;
				kmsg-symlink) $BB ln -s /tmp/dmesg "$gate/kmsg";;
			esac
			exit 0
		fi;;
	printf)
		if [ "${2:-}" = '%s %s\n' ] && [ "${4:-}" = '11111111-2222-3333-4444-555555555555' ]; then
			case "$mode" in
				stage-write-fail) exit 1;;
				staged-partial) printf 'partial\n'; exit 0;;
				staged-wrong-boot) printf '%s %s\n' "$3" '00000000-0000-0000-0000-000000000000'; exit 0;;
				staged-nonce-change) $BB printf '%064d\n' 0 > "$guard/nonce";;
				staged-other) $BB touch "$guard/.ack-new";;
			esac
		fi
		if [ "${2:-}" = '%s\n' ]; then
			case "$mode:${3:-}" in
				stage-evidence:*' stage=association result=pass '*) exit 1;;
				all-evidence:*' stage=all-checks result=pass '*) exit 1;;
				published-evidence:*' stage=ack-publication result=pass '*) exit 1;;
				accepted-evidence:*' stage=guard-acceptance result=pass '*) exit 1;;
			esac
		fi;;
	cat)
		case "$mode:${2:-}" in
			nonce-unreadable:"$guard/nonce") [ ! -f "$gate/started" ] || exit 1;;
			rmtfs-unreadable:"$state/rmtfs.pid") [ ! -f "$gate/nonce-and-radio-markers.ok" ] || exit 1;;
			ssh-unreadable:/run/dropbear-session.pid) exit 1;;
		esac;;
	sha256sum)
		case "${2:-}" in
			/proc/42/exe) [ "$mode" != rmtfs-pin ] || { printf '%064d  %s\n' 0 "$2"; exit 0; }; printf 'd66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd  %s\n' "$2"; exit 0;;
			/etc/init.d/networking) [ "$mode" != service-pin ] || { printf '%064d  %s\n' 0 "$2"; exit 0; }; printf '334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c  %s\n' "$2"; exit 0;;
			/etc/init.d/wpa_supplicant) printf 'a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f  %s\n' "$2"; exit 0;;
			/run/radio-bringup/wlan-udhcpc-lease.sh) [ "$mode" != lease-pin ] || { printf '%064d  %s\n' 0 "$2"; exit 0; }; printf '1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56  %s\n' "$2"; exit 0;;
		esac;;
	dmesg)
		case "$*" in
			dmesg) snapshot=prefix;;
			'dmesg -r -s 2097152')
				if [ -f "$gate/dns.ok" ]; then snapshot=final
				elif [ -f "$gate/nonce-and-radio-markers.ok" ]; then snapshot=radio
				else snapshot=marker; fi
				printf '%s\n' "$snapshot" >> /tmp/synthetic-snapshot-requests
				[ "$( $BB stat -c '%u:%a:%h:%s' "$gate/kmsg" 2>/dev/null)" = 0:600:1:0 ] || { $BB touch /tmp/unsafe-snapshot-open; exit 1; }
				printf '%s\n' "$snapshot" >> /tmp/synthetic-snapshot-open-checks
				case "$mode:$snapshot" in
					kmsg-marker-fail:marker|kmsg-radio-fail:radio|kmsg-final-fail:final) exit 1;;
					kmsg-unsafe:radio) $BB chmod 644 "$gate/kmsg";;
					kmsg-truncated-success:radio)
						$BB printf 'truncated synthetic kernel ring buffer\n' >> /tmp/synthetic-kmsg-metadata;;
				esac;;
			*) printf '%s\n' "$*" >> /tmp/unexpected-dmesg-arguments; exit 1;;
		esac
		case "$mode:$snapshot" in
			kmsg-empty:radio) exit 0;;
			kmsg-nul:radio) printf 'synthetic\000kmsg\n';;
			mid-radio-fatal-before:radio|mid-final-fatal-before:final|radio-large-fatal-before:radio|final-large-fatal-before:final) printf 'kernel panic\n';;
		esac
		case "$mode:$snapshot" in
			large-exact:radio|large-exact:final|exact-large-fatal-after:radio|oversized-precise:radio)
				$BB cat /tmp/synthetic-exact-kmsg || exit 1
				$BB cat /tmp/dmesg || exit 1
				for marker in "$state/"*.marker; do
					[ -f "$marker" ] || continue
					printf 'pmos-self-post: guest radio marker %s\n' "$($BB cat "$marker")" || exit 1
				done
				case "$mode" in
					exact-large-fatal-after) printf 'kernel panic\n' || exit 1;;
					oversized-precise) printf x || exit 1;;
				esac
				exit 0;;
			mid-clean:radio|mid-clean:final|large-clean:radio|large-clean:final|mid-radio-fatal-*:radio|mid-final-fatal-*:final|radio-large-fatal-*:radio|final-large-fatal-*:final)
				$BB cat /tmp/synthetic-large-kmsg || exit 1;;
			kmsg-oversized:radio) $BB cat /tmp/synthetic-oversized-kmsg || exit 1; exit 0;;
		esac
		case "$mode:$snapshot" in
			mid-radio-fatal-before:radio|mid-radio-fatal-after:radio|mid-final-fatal-before:final|mid-final-fatal-after:final|radio-large-fatal-before:radio|radio-large-fatal-after:radio|final-large-fatal-before:final|final-large-fatal-after:final)
				$BB cat /tmp/dmesg
				for marker in "$state/"*.marker; do
					[ -f "$marker" ] || continue
					printf 'pmos-self-post: guest radio marker %s\n' "$($BB cat "$marker")"
				done
				case "$mode" in *-after) printf 'kernel panic\n';; esac
				exit 0;;
		esac
		$BB cat /tmp/dmesg
		for marker in "$state/"*.marker; do
			[ -f "$marker" ] || continue
			[ "$mode" != marker-missing-kmsg ] || [ ! -f /tmp/services.done ] || [ "$marker" != "$state/modem.marker" ] || continue
			printf 'pmos-self-post: guest radio marker %s\n' "$($BB cat "$marker")"
			if [ "$mode" = marker-duplicate-kmsg ] && [ -f /tmp/services.done ] && [ "$marker" = "$state/modem.marker" ]; then
				printf 'pmos-self-post: guest radio marker %s\n' "$($BB cat "$marker")"
			fi
		done
		if [ "$mode" = fatal-radio ] && [ -f /tmp/services.done ]; then printf 'kernel panic\n'; fi
		if [ "$mode" = final-fatal ] && [ -f "$gate/dns.ok" ]; then printf 'kernel panic\n'; fi
		exit 0;;
	sh)
		if [ "${2:-}" = /usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh ]; then
			printf '%s\n' "$4" >> /tmp/stages
			[ "$mode" != "prefix-fail-$4" ] || exit 1
			if [ "$4" = services ]; then
				$BB cat > /tmp/services-stdin
				case "$mode" in
					large-exact|exact-large-fatal-after|oversized-precise)
					$BB cat /tmp/dmesg > /tmp/synthetic-kmsg-overhead
					for marker in "$state/"*.marker; do
						printf 'pmos-self-post: guest radio marker %s\n' "$($BB cat "$marker")" >> /tmp/synthetic-kmsg-overhead
					done
					overhead=$($BB wc -c < /tmp/synthetic-kmsg-overhead)
					if [ "$mode" = exact-large-fatal-after ]; then
						overhead=$((overhead + 13))
					fi
					padding=$((1048576 - overhead - 1))
					$BB dd if=/dev/zero bs=1 count="$padding" 2>/dev/null | $BB tr '\000' x > /tmp/synthetic-exact-kmsg
					printf '\n' >> /tmp/synthetic-exact-kmsg
					printf '%s\n' "$((padding + 1 + overhead))" > /tmp/synthetic-snapshot-size;;
				esac
				mutate
				$BB touch /tmp/services.done
			fi
			exit 0
		fi;;
	pidof) [ "$mode" != service-process ] || exit 1; [ "$mode" != final-process ] || [ ! -f "$gate/dns.ok" ] || exit 1; printf '42\n'; exit 0;;
	grep)
		if [ "${2:-}" = -Ei ] && [ "${4:-}" = "$gate/kmsg" ]; then
			if [ "$mode" = kmsg-radio-grep-fail ] && [ ! -f "$gate/radio-health.ok" ]; then exit 2; fi
			if [ "$mode" = kmsg-final-grep-fail ] && [ -f "$gate/dns.ok" ]; then exit 2; fi
		fi
		if [ "${2:-}" = -Fc ] && [ "${4:-}" = "$gate/kmsg" ] && [ "$mode" = kmsg-marker-grep-fail ]; then exit 2; fi;;
	tr)
		if [ "${2:-}" = -d ] && [ "$mode" = kmsg-inspect-fail ] && [ -f "$gate/nonce-and-radio-markers.ok" ]; then exit 1; fi;;
	awk)
		case "$*" in *'/etc/resolv.conf'*) [ "$mode" != resolver-query ] || exit 1;; esac;;
	chmod)
		if [ "${2:-}" = 700 ] && [ "${3:-}" = "$gate/dns-probe" ] && [ "$mode" = dns-chmod ]; then exit 1; fi;;
	base64)
		if [ "$mode" = dns-extract ]; then exit 1; fi
		if [ "$mode" = dns-pin ]; then $BB base64 "$@" >/dev/null; printf 'synthetic corrupt probe'; exit 0; fi;;
	ping)
		for target do :; done
		[ "$mode:$target" != gateway-ping:192.0.2.1 ] || exit 1
		[ "$mode:$target" != internet-ping:1.1.1.1 ] || exit 1
		exit 0;;
	timeout)
		if [ "${5:-}" = "$gate/dns-probe" ]; then
			printf '%s\n' "${6:-}" >> /tmp/dns-invocations
			[ "$mode" != dns-failure ] || exit 1
			case "$mode" in
				dns-invalid) printf '127.0.0.1\n';;
				*) printf '93.184.216.34\n';;
			esac
			exit 0
		fi;;
	ln)
		if [ "${2:-}" = "$guard/.success-gated-ack-new" ] && [ "${3:-}" = "$guard/ack" ]; then
			printf 'attempt\n' >> /tmp/publication-attempts
			if [ "$mode" = publication-race ]; then printf 'synthetic competing ack\n' > "$guard/ack"; fi
			if [ "$mode" = interrupt-before-link ]; then kill -TERM "$($BB cat /tmp/post.pid)"; exit 1; fi
			$BB ln "$2" "$3" || exit 1
			printf 'published\n' >> /tmp/publications
			$BB cp "$guard/ack" /tmp/ack-at-link
			$BB stat -c '%u:%a:%h:%s' "$guard/ack" > /tmp/ack-at-link.stat
			case "$mode" in
				published-corrupt) $BB printf 'partial\n' > "$guard/ack";;
				published-guard-change) $BB printf '%064d\n' 0 > "$guard/nonce";;
				interrupt-after-link) kill -TERM "$($BB cat /tmp/post.pid)";;
			esac
			exit 0
		fi;;
	rm)
		if [ "${2:-}" = "$gate/kmsg" ] && [ "$mode" = kmsg-remove-fail ]; then exit 1; fi
		if [ "${2:-}" = "$guard/.success-gated-ack-new" ]; then
			if [ "$mode" = interrupt-before-unlink ]; then kill -TERM "$($BB cat /tmp/post.pid)"; exit 1; fi
			[ "$mode" != unlink-fail ] || exit 1
			$BB rm "$2" || exit 1
			case "$mode" in
				published-replaced) $BB rm "$guard/ack"; $BB printf 'partial\n' > "$guard/ack";;
				wait-root-change) $BB printf '9:9\n' > "$guard/root-identity";;
				interrupt-after-publication) kill -TERM "$($BB cat /tmp/post.pid)";;
			esac
			exit 0
		fi;;
	sleep)
		if [ -f "$gate/published.ok" ]; then
			if [ "$mode" = interrupt-after-evidence ]; then
				kill -TERM "$($BB cat /tmp/post.pid)"
			elif [ "$mode" = accepted-wrong-boot ]; then
				$BB rm -f "$guard/nonce" "$guard/ack"
				$BB printf '00000000-0000-0000-0000-000000000000\n' > "$guard/accepted"
				$BB chmod 600 "$guard/accepted"
			elif [ "$mode" = accepted-partial ]; then
				$BB rm -f "$guard/nonce" "$guard/ack"
				$BB printf 'partial\n' > "$guard/accepted"
				$BB chmod 600 "$guard/accepted"
			elif [ "$mode" != acceptance-timeout ]; then
				$BB cp "$guard/ack" /tmp/ack-before-consumption
				$BB stat -c '%u:%a:%h:%s' "$guard/ack" > /tmp/ack-before-consumption.stat
				$BB rm "$guard/nonce" "$guard/ack"
				$BB cat "$guard/armed" > "$guard/accepted"
				$BB chmod 600 "$guard/accepted"
			fi
		fi
		exit 0;;
esac
exec "$BB" "$@"
MOCK
$BB chmod 755 "$BASE/bin/busybox"
$BB cat > "$BASE/sbin/rc-service" <<'SERVICE'
#!/real/busybox sh
BB=/real/busybox
mode=$($BB cat /tmp/mode)
gate=/run/radio-bringup/success-gate-294
if [ "$mode" = service-status ] && [ -f "$gate/radio-health.ok" ]; then exit 1; fi
if [ "$mode" = final-service ] && [ -f "$gate/dns.ok" ]; then exit 1; fi
exit 0
SERVICE
$BB cat > "$BASE/usr/sbin/iw" <<'IW'
#!/real/busybox sh
BB=/real/busybox
mode=$($BB cat /tmp/mode)
if [ -f /tmp/iw.called ]; then final=1; else final=0; $BB touch /tmp/iw.called; fi
if [ "$final" = 0 ]; then
	case "$mode" in
		association-query) exit 1;;
		association-disconnected) printf 'Not connected.\n'; exit 0;;
		guard-nonce-change) $BB printf '%064d\n' 0 > /run/pid1-guard/nonce;;
		guard-armed-change) $BB printf 'changed\n' > /run/pid1-guard/armed;;
		guard-accepted-change) $BB printf 'synthetic\n' > /run/pid1-guard/accepted;;
		guard-ack-change) $BB printf 'synthetic invalid ack\n' > /run/pid1-guard/ack;;
		interrupt-before) kill -TERM "$($BB cat /tmp/post.pid)";;
	esac
else
	case "$mode" in
		final-association-query) exit 1;;
		final-association) printf 'Connected to 00:11:22:33:44:66 (on wlan0)\n'; exit 0;;
		final-remoteproc) $BB printf 'offline\n' > /sys/class/remoteproc/remoteproc2/state;;
		final-wlan) $BB rmdir /sys/class/net/wlan0;;
		final-rmtfs-missing) $BB rm /run/radio-bringup/rmtfs.pid;;
		final-rmtfs-invalid) $BB printf 'bad\n' > /run/radio-bringup/rmtfs.pid;;
		final-rmtfs) $BB printf 'dead\n' > /proc/42/comm;;
	esac
fi
printf 'Connected to 00:11:22:33:44:55 (on wlan0)\n'
IW
$BB cat > "$BASE/sbin/ip" <<'IP'
#!/real/busybox sh
BB=/real/busybox
mode=$($BB cat /tmp/mode)
case "$*" in
	'-o -4 addr show dev wlan0 scope global')
		if [ -f /tmp/address.called ]; then final=1; else final=0; $BB touch /tmp/address.called; fi
		if [ "$final" = 0 ]; then
			case "$mode" in address-query) exit 1;; address-invalid) printf '2: wlan0 inet 169.254.1.2/24 scope global wlan0\n'; exit 0;; address-partial) printf '2: wlan0 inet 192.0.2.2 scope global wlan0\n'; exit 0;; esac
		else
			[ "$mode" != final-address-query ] || exit 1
			if [ "$mode" = final-address ]; then printf '2: wlan0 inet 192.0.2.3/24 scope global wlan0\n'; exit 0; fi
		fi
		printf '2: wlan0 inet 192.0.2.2/24 scope global wlan0\n';;
	'-4 route show default')
		if [ -f /tmp/default.called ]; then final=1; else final=0; $BB touch /tmp/default.called; fi
		if [ "$final" = 0 ]; then
			case "$mode" in route-query) exit 1;; route-duplicate) printf 'default via 192.0.2.1 dev wlan0\ndefault via 192.0.2.4 dev wlan0\n'; exit 0;; gateway-invalid) printf 'default via 127.0.0.1 dev wlan0\n'; exit 0;; esac
		else
			[ "$mode" != final-route-query ] || exit 1
			if [ "$mode" = final-route ]; then printf 'default via 192.0.2.4 dev wlan0\n'; exit 0; fi
		fi
		printf 'default via 192.0.2.1 dev wlan0\n';;
	'-4 route get 1.1.1.1 from 192.0.2.2')
		[ "$mode" != internet-query ] || exit 1
		if [ "$mode" = internet-route ]; then printf '1.1.1.1 dev eth0\n'; else printf '1.1.1.1 via 192.0.2.1 dev wlan0\n'; fi;;
	'-4 route get 192.0.2.53 from 192.0.2.2')
		[ "$mode" != dns-query ] || exit 1
		if [ "$mode" = dns-route ]; then printf '192.0.2.53 dev eth0\n'; else printf '192.0.2.53 via 192.0.2.1 dev wlan0\n'; fi;;
	*) exit 1;;
esac
IP
$BB chmod 755 "$BASE/sbin/rc-service" "$BASE/sbin/ip" "$BASE/usr/sbin/iw"

reset_case() {
	$BB rm -rf "$ROOT"
	$BB cp -a "$BASE" "$ROOT"
	$BB printf '%s\n' "$1" > "$ROOT/tmp/mode"
	case "$1" in
		large-clean|mid-clean|mid-radio-fatal-*|mid-final-fatal-*|radio-large-fatal-*|final-large-fatal-*)
			case "$1" in mid-*) blocks=256;; *) blocks=900;; esac
			$BB dd if=/dev/zero bs=1024 count="$blocks" 2>/dev/null | $BB tr '\000' x > "$ROOT/tmp/synthetic-large-kmsg"
			$BB printf '\n' >> "$ROOT/tmp/synthetic-large-kmsg"
			[ "$( $BB wc -c < "$ROOT/tmp/synthetic-large-kmsg")" = "$((blocks * 1024 + 1))" ] || fail "$1: synthetic large kmsg size"
			;;
		kmsg-oversized)
			$BB dd if=/dev/zero bs=1024 count=1024 2>/dev/null | $BB tr '\000' x > "$ROOT/tmp/synthetic-oversized-kmsg"
			$BB printf '\n' >> "$ROOT/tmp/synthetic-oversized-kmsg"
			[ "$( $BB wc -c < "$ROOT/tmp/synthetic-oversized-kmsg")" = 1048577 ] || fail "$1: synthetic oversized kmsg size"
			;;
	esac
	$BB stat -c '%d:%i' "$ROOT" > "$ROOT/run/pid1-guard/root-identity"
	$BB chmod 600 "$ROOT/run/pid1-guard/root-identity"
}
run_post() {
	$BB chroot "$ROOT" /real/busybox sh /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh > "$ROOT/tmp/post.out" 2>&1 &
	pid=$!
	$BB printf '%s\n' "$pid" > "$ROOT/tmp/post.pid"
	if wait "$pid"; then return 0; else return 1; fi
}
run_hook() {
	$BB timeout -k 1 10 $BB chroot "$ROOT" /real/busybox sh /hook > "$ROOT/tmp/hook.out" 2>&1
}
wait_hook_file() {
	hook_file=$1
	hook_label=$2
	hook_count=0
	until [ -f "$hook_file" ]; do
		[ "$hook_count" -lt 600 ] && [ ! -e "$ROOT/tmp/hook-barrier-timeout" ] || {
			$BB cat "$ROOT/tmp/hook.out" >&2
			fail "$hook_label: timed out waiting for $hook_file"
		}
		$BB sleep 0.1
		hook_count=$((hook_count + 1))
	done
}
start_hook() {
	hook_case=$1
	run_hook || { $BB cat "$ROOT/tmp/hook.out" >&2; fail "$hook_case: hook did not return success before launch release"; }
	wait_hook_file "$ROOT/tmp/hook-at-barrier" "$hook_case"
	[ "$( $BB cat "$ROOT/tmp/hook-launches")" = launch ] || fail "$hook_case: expected one detached launch"
	[ ! -e "$ROOT/tmp/stages" ] && [ ! -e "$ROOT/run/radio-bringup/success-gate-294" ] && [ ! -e "$ROOT/tmp/hook-post-result" ] || fail "$hook_case: post ran before release"
	check_no_publication "$hook_case before release"
	$BB touch "$ROOT/tmp/hook-release"
	wait_hook_file "$ROOT/tmp/hook-post-result" "$hook_case"
	[ "$( $BB cat "$ROOT/tmp/hook-launches")" = launch ] || fail "$hook_case: multiple detached launches"
}
check_prefix() {
	[ "$( $BB cat "$ROOT/tmp/stages" 2>/dev/null)" = 'modem
wpss
driver
scan
services' ] || fail "$1: real #291 prefix did not reach all synthetic radio stages"
	[ "$( $BB cat "$ROOT/tmp/services-stdin" 2>/dev/null)" = 'synthetic profile' ] || fail "$1: profile was not passed to mock services"
}
check_no_publication() {
	[ ! -e "$ROOT/tmp/publications" ] || fail "$1: unexpected ACK publication"
	if [ -f "$ROOT/run/pid1-guard/ack" ] && [ ! -L "$ROOT/run/pid1-guard/ack" ]; then
		$BB printf '%s %s\n' "$nonce" "$boot" > "$ROOT/tmp/expected-ack"
		if $BB cmp -s "$ROOT/tmp/expected-ack" "$ROOT/run/pid1-guard/ack"; then fail "$1: valid ACK exists"; fi
	fi
}
check_evidence() {
	file=$1
	text=$2
	[ -f "$file" ] && [ ! -L "$file" ] || fail "missing evidence $file"
	[ "$( $BB stat -c '%u:%a:%h:%s' "$file")" = "0:600:1:$((${#text} + 1))" ] || fail "unsafe evidence $file"
	$BB printf '%s\n' "$text" > "$ROOT/tmp/expected-evidence"
	$BB cmp -s "$file" "$ROOT/tmp/expected-evidence" || fail "incorrect evidence $file"
}
check_passes() {
	stop=$1
	gate=$ROOT/run/radio-bringup/success-gate-294
	found=0
	for stage in $stages; do
		if [ "$stage" = "$stop" ]; then found=1; fi
		if [ "$found" = 0 ]; then
			check_evidence "$gate/$stage.ok" "boot=$boot stage=$stage result=pass phase=before-publication reason=none"
		elif [ -e "$gate/$stage.ok" ] || [ -L "$gate/$stage.ok" ]; then
			if [ "$stage" = "$stop" ] && [ "${2:-}" = evidence-write ] && [ -f "$gate/$stage.ok" ] && [ ! -L "$gate/$stage.ok" ] && [ ! -s "$gate/$stage.ok" ]; then
				:
			else
				fail "$stop: later stage $stage recorded success"
			fi
		fi
	done
	[ "$found" = 1 ] || [ "$stop" = ack-publication ] || fail "unknown terminal stage $stop"
}
expect_refusal() {
	case_name=$1
	terminal=$2
	reason=$3
	reset_case "$case_name"
	if run_post; then fail "$case_name: candidate unexpectedly succeeded"; fi
	check_prefix "$case_name"
	check_no_publication "$case_name"
	case "$case_name" in
		missing-ifquery|missing-lease-wrapper|missing-lease-helper)
			case "$case_name" in
				missing-ifquery) missing=ifquery-wlan;;
				missing-lease-wrapper) missing=lease-wrapper.sh;;
				missing-lease-helper) missing=wlan-udhcpc-lease.sh;;
			esac
			[ ! -e "$ROOT/run/radio-bringup/$missing" ] && [ ! -L "$ROOT/run/radio-bringup/$missing" ] &&
				[ ! -e "$ROOT/tmp/publication-attempts" ] && [ ! -e "$ROOT/run/pid1-guard/ack" ] && [ ! -L "$ROOT/run/pid1-guard/ack" ] &&
				[ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] && [ ! -L "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "$case_name: missing helper or publication state changed";;
	esac
	gate=$ROOT/run/radio-bringup/success-gate-294
	check_evidence "$gate/started" "boot=$boot stage=initialization result=started phase=before-publication reason=none"
	check_evidence "$gate/refusal" "boot=$boot stage=$terminal result=refused-or-interrupted phase=before-publication reason=$reason"
	case "$case_name" in
		stage-evidence|all-evidence) check_passes "$terminal" evidence-write;;
		*) check_passes "$terminal";;
	esac
	[ ! -e "$gate/published.ok" ] && [ ! -e "$gate/accepted.ok" ] || fail "$case_name: false publication evidence"
	[ ! -e "$gate/kmsg" ] && [ ! -L "$gate/kmsg" ] || fail "$case_name: kmsg snapshot not cleaned"
	[ ! -e "$ROOT/tmp/unexpected-dmesg-arguments" ] && [ ! -e "$ROOT/tmp/unsafe-snapshot-open" ] || fail "$case_name: unexpected dmesg arguments or unsafe snapshot"
	[ ! -e "$ROOT/run/radio-bringup/wpa_supplicant.conf" ] || fail "$case_name: profile not scrubbed"
	printf 'pass: %s -> %s\n' "$case_name" "$terminal"
}
check_publication() {
	[ "$( $BB cat "$ROOT/tmp/publication-attempts")" = attempt ] || fail "$1: not exactly one publication attempt"
	[ "$( $BB cat "$ROOT/tmp/publications")" = published ] || fail "$1: not exactly one successful publication"
	$BB printf '%s %s\n' "$nonce" "$boot" > "$ROOT/tmp/expected-ack"
	$BB cmp -s "$ROOT/tmp/expected-ack" "$ROOT/tmp/ack-at-link" || fail "$1: ACK bytes differ"
	[ "$( $BB cat "$ROOT/tmp/ack-at-link.stat")" = "0:600:2:$((${#nonce} + ${#boot} + 2))" ] || fail "$1: published inode metadata differs"
}

reset_case success
run_post || { $BB cat "$ROOT/tmp/post.out" >&2; fail 'success case refused'; }
check_prefix success
check_publication success
$BB cmp -s "$ROOT/tmp/expected-ack" "$ROOT/tmp/ack-before-consumption" || fail 'consumed ACK bytes differ'
[ "$( $BB cat "$ROOT/tmp/ack-before-consumption.stat")" = "0:600:1:$((${#nonce} + ${#boot} + 2))" ] || fail 'consumed ACK not single-link root-only'
[ "$( $BB cat "$ROOT/tmp/dns-invocations")" = 192.0.2.53 ] || fail 'synthetic DNS not invoked exactly once with resolver'
gate=$ROOT/run/radio-bringup/success-gate-294
check_evidence "$gate/started" "boot=$boot stage=initialization result=started phase=before-publication reason=none"
for stage in $stages; do check_evidence "$gate/$stage.ok" "boot=$boot stage=$stage result=pass phase=before-publication reason=none"; done
check_evidence "$gate/published.ok" "boot=$boot stage=ack-publication result=pass phase=published-awaiting-guard reason=none"
check_evidence "$gate/accepted.ok" "boot=$boot stage=guard-acceptance result=pass phase=guard-accepted reason=none"
[ ! -e "$gate/refusal" ] && [ ! -e "$gate/dns-probe" ] && [ ! -e "$gate/kmsg" ] && [ ! -e "$ROOT/run/radio-bringup/wpa_supplicant.conf" ] || fail 'success cleanup'
[ "$( $BB cat "$ROOT/tmp/synthetic-snapshot-requests")" = 'marker
radio
final' ] && [ "$( $BB cat "$ROOT/tmp/synthetic-snapshot-open-checks")" = 'marker
radio
final' ] && [ ! -e "$ROOT/tmp/unsafe-snapshot-open" ] && [ ! -e "$ROOT/tmp/unexpected-dmesg-arguments" ] || fail 'success: expected three protected bounded synthetic kmsg reads'
if [ -f "$ROOT/tmp/synthetic-contract-events" ]; then
	if $BB grep -qF 'FAIL:' "$ROOT/tmp/synthetic-contract-events"; then fail 'success: unexpected synthetic failure event'; fi
fi
[ ! -e "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/nonce" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail 'mock guard did not consume ACK and nonce'
check_evidence "$ROOT/run/pid1-guard/accepted" "$boot"
printf 'pass: complete real generated post, exact ACK bytes and synthetic guard acceptance\n'

reset_case success
start_hook hook-success
[ "$( $BB cat "$ROOT/tmp/hook-post-result")" = 0 ] || fail 'hook-success: detached post failed'
check_prefix hook-success
check_publication hook-success
$BB cmp -s "$ROOT/tmp/expected-ack" "$ROOT/tmp/ack-before-consumption" || fail 'hook-success: consumed ACK bytes differ'
[ "$( $BB cat "$ROOT/tmp/ack-before-consumption.stat")" = "0:600:1:$((${#nonce} + ${#boot} + 2))" ] || fail 'hook-success: consumed ACK metadata differs'
gate=$ROOT/run/radio-bringup/success-gate-294
check_evidence "$gate/started" "boot=$boot stage=initialization result=started phase=before-publication reason=none"
for stage in $stages; do check_evidence "$gate/$stage.ok" "boot=$boot stage=$stage result=pass phase=before-publication reason=none"; done
check_evidence "$gate/published.ok" "boot=$boot stage=ack-publication result=pass phase=published-awaiting-guard reason=none"
check_evidence "$gate/accepted.ok" "boot=$boot stage=guard-acceptance result=pass phase=guard-accepted reason=none"
check_evidence "$ROOT/run/pid1-guard/accepted" "$boot"
[ ! -e "$gate/refusal" ] && [ ! -e "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/nonce" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail 'hook-success: incorrect final guard state'
printf 'pass: generated hook returned asynchronously and launched complete prefix and gate with one accepted ACK\n'

for script in post radio; do
	for defect in missing changed mode symlink dangling; do
		reset_case hook-noop
		case "$script" in
			post) pin=$ROOT/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh;;
			radio) pin=$ROOT/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh;;
		esac
		case "$defect" in
			missing) $BB rm "$pin";;
			changed) $BB printf '\n' >> "$pin";;
			mode) $BB chmod 755 "$pin";;
			symlink) $BB mv "$pin" "$pin.original"; $BB ln -s "${pin##*/}.original" "$pin";;
			dangling) $BB rm "$pin"; $BB ln -s absent "$pin";;
		esac
		if run_hook; then
			$BB touch "$ROOT/tmp/hook-release"
			fail "hook-$script-$defect: unsafe pin accepted"
		else
			hook_rc=$?
		fi
		[ "$hook_rc" = 1 ] || fail "hook-$script-$defect: hook returned $hook_rc instead of pin refusal"
		$BB sleep 0.2
		if [ -e "$ROOT/tmp/hook-launches" ] || [ -e "$ROOT/tmp/hook-at-barrier" ]; then
			$BB touch "$ROOT/tmp/hook-release"
			fail "hook-$script-$defect: post launched"
		fi
		[ ! -e "$ROOT/tmp/stages" ] && [ ! -e "$ROOT/run/radio-bringup/success-gate-294" ] || fail "hook-$script-$defect: post ran"
		[ ! -e "$ROOT/tmp/publication-attempts" ] && [ ! -e "$ROOT/run/pid1-guard/ack" ] && [ ! -L "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] && [ ! -L "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "hook-$script-$defect: ACK state changed"
		check_no_publication "hook-$script-$defect"
		$BB touch "$ROOT/tmp/hook-release"
		printf 'pass: generated hook refused %s %s pin without launching\n' "$script" "$defect"
	done
done

for failed_stage in modem wpss driver scan services; do
	reset_case "prefix-fail-$failed_stage"
	start_hook "hook-prefix-fail-$failed_stage"
	[ "$( $BB cat "$ROOT/tmp/hook-post-result")" != 0 ] || fail "hook-prefix-fail-$failed_stage: detached post succeeded"
	expected=
	for stage in modem wpss driver scan services; do
		if [ -n "$expected" ]; then expected="$expected
$stage"; else expected=$stage; fi
		[ "$stage" != "$failed_stage" ] || break
	done
	[ "$( $BB cat "$ROOT/tmp/stages")" = "$expected" ] || fail "hook-prefix-fail-$failed_stage: unexpected radio-stage sequence"
	[ ! -e "$ROOT/run/radio-bringup/success-gate-294" ] && [ ! -e "$ROOT/tmp/publication-attempts" ] && [ ! -e "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "hook-prefix-fail-$failed_stage: gate or ACK state changed"
	check_no_publication "hook-prefix-fail-$failed_stage"
	[ ! -e "$ROOT/run/radio-bringup/wpa_supplicant.conf" ] || fail "hook-prefix-fail-$failed_stage: profile not scrubbed"
	printf 'pass: generated hook detached prefix refused %s before gate or ACK\n' "$failed_stage"
done

for mode in association-disconnected address-invalid route-duplicate gateway-ping internet-ping dns-failure final-association; do
	reset_case "$mode"
	start_hook "hook-$mode"
	[ "$( $BB cat "$ROOT/tmp/hook-post-result")" != 0 ] || fail "hook-$mode: detached post succeeded"
	check_prefix "hook-$mode"
	check_no_publication "hook-$mode"
	[ ! -e "$ROOT/tmp/publication-attempts" ] && [ ! -e "$ROOT/run/pid1-guard/ack" ] && [ ! -L "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] && [ ! -L "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "hook-$mode: ACK state changed"
	case "$mode" in
		association-disconnected) terminal=association; reason='wlan0 is not associated';;
		address-invalid) terminal=address; reason='no sane global-scope wlan0 IPv4 address';;
		route-duplicate) terminal=route; reason='expected one default route via wlan0';;
		gateway-ping) terminal=gateway; reason='gateway ICMP on wlan0 failed';;
		internet-ping) terminal=internet; reason='internet ICMP on wlan0 failed';;
		dns-failure) terminal=dns; reason='bound DNS query returned no valid answer';;
		final-association) terminal=final-health; reason='association changed during checks';;
	esac
	gate=$ROOT/run/radio-bringup/success-gate-294
	check_evidence "$gate/refusal" "boot=$boot stage=$terminal result=refused-or-interrupted phase=before-publication reason=$reason"
	check_passes "$terminal"
	[ ! -e "$gate/published.ok" ] && [ ! -e "$gate/accepted.ok" ] || fail "hook-$mode: false success evidence"
	printf 'pass: generated hook detached gate refused %s before ACK\n' "$terminal"
done

snapshot_ok=1
for mode in mid-clean large-clean large-exact; do
	reset_case "$mode"
	if ! run_post; then
		check_prefix "$mode"
		check_no_publication "$mode"
		check_evidence "$ROOT/run/radio-bringup/success-gate-294/refusal" "boot=$boot stage=radio-health result=refused-or-interrupted phase=before-publication reason=cannot read radio kmsg"
		snapshot_ok=0
		printf 'FAIL: %s: clean <=1 MiB snapshot refused at radio-health\n' "$mode" >&2
		continue
	fi
	check_prefix "$mode"
	check_publication "$mode"
	gate=$ROOT/run/radio-bringup/success-gate-294
	for stage in $stages; do check_evidence "$gate/$stage.ok" "boot=$boot stage=$stage result=pass phase=before-publication reason=none"; done
	check_evidence "$gate/published.ok" "boot=$boot stage=ack-publication result=pass phase=published-awaiting-guard reason=none"
	check_evidence "$gate/accepted.ok" "boot=$boot stage=guard-acceptance result=pass phase=guard-accepted reason=none"
	[ "$( $BB cat "$ROOT/tmp/synthetic-snapshot-requests")" = 'marker
radio
final' ] && [ ! -e "$ROOT/tmp/unexpected-dmesg-arguments" ] || fail "$mode: snapshot requests differ"
	[ ! -e "$gate/kmsg" ] && [ ! -e "$gate/refusal" ] || fail "$mode: snapshot cleanup"
	if [ "$mode" = large-exact ]; then
		[ "$( $BB cat "$ROOT/tmp/synthetic-snapshot-size")" = 1048576 ] || fail "$mode: incorrect snapshot size"
	fi
	printf 'pass: %s synthetic kmsg accepted, one ACK, snapshot cleaned\n' "$mode"
done

for failed_stage in modem wpss driver scan services; do
	reset_case "prefix-fail-$failed_stage"
	if run_post; then fail "prefix-fail-$failed_stage: generated post succeeded"; fi
	expected=
	for stage in modem wpss driver scan services; do
		if [ -n "$expected" ]; then expected="$expected
$stage"; else expected=$stage; fi
		[ "$stage" != "$failed_stage" ] || break
	done
	[ "$( $BB cat "$ROOT/tmp/stages")" = "$expected" ] || fail "prefix-fail-$failed_stage: unexpected radio-stage sequence"
	[ ! -e "$ROOT/run/radio-bringup/success-gate-294" ] || fail "prefix-fail-$failed_stage: gate ran"
	[ ! -e "$ROOT/tmp/publication-attempts" ] || fail "prefix-fail-$failed_stage: attempted publication"
	check_no_publication "prefix-fail-$failed_stage"
	[ ! -e "$ROOT/run/radio-bringup/wpa_supplicant.conf" ] || fail "prefix-fail-$failed_stage: profile not scrubbed"
	printf 'pass: real prefix stops at synthetic %s radio failure before gate\n' "$failed_stage"
done

expect_refusal guard-mode nonce-and-radio-markers 'boot or root identity changed'
expect_refusal wrong-boot nonce-and-radio-markers 'boot or root identity changed'
expect_refusal wrong-armed nonce-and-radio-markers 'boot or root identity changed'
expect_refusal wrong-root nonce-and-radio-markers 'boot or root identity changed'
expect_refusal pid1-exe nonce-and-radio-markers 'boot or root identity changed'
expect_refusal staging-other nonce-and-radio-markers 'another ACK publisher is staging'
expect_refusal nonce-partial nonce-and-radio-markers 'unsafe nonce'
expect_refusal nonce-mode nonce-and-radio-markers 'unsafe nonce'
expect_refusal nonce-symlink nonce-and-radio-markers 'unsafe nonce'
expect_refusal nonce-unreadable nonce-and-radio-markers 'cannot read nonce'
expect_refusal nonce-invalid nonce-and-radio-markers 'invalid nonce'
expect_refusal pending-ack nonce-and-radio-markers 'boot, root, nonce or unacknowledged guard changed'
expect_refusal pending-accepted nonce-and-radio-markers 'boot, root, nonce or unacknowledged guard changed'
expect_refusal marker-partial nonce-and-radio-markers 'invalid modem capture marker'
expect_refusal marker-replay nonce-and-radio-markers 'invalid modem capture marker'
expect_refusal marker-symlink nonce-and-radio-markers 'invalid modem capture marker'
expect_refusal marker-missing-kmsg nonce-and-radio-markers 'missing or duplicate modem kmsg marker'
expect_refusal marker-duplicate-kmsg nonce-and-radio-markers 'missing or duplicate modem kmsg marker'
expect_refusal kmsg-marker-fail nonce-and-radio-markers 'cannot read same-boot kmsg'
expect_refusal kmsg-marker-grep-fail nonce-and-radio-markers 'missing or duplicate modem kmsg marker'
expect_refusal kmsg-path nonce-and-radio-markers 'unsafe kmsg snapshot path'
expect_refusal kmsg-symlink nonce-and-radio-markers 'unsafe kmsg snapshot path'
expect_refusal kmsg-remove-fail nonce-and-radio-markers 'cannot remove kmsg snapshot'
expect_refusal remoteproc radio-health 'remoteproc identity or state'
expect_refusal remoteproc-name radio-health 'remoteproc identity or state'
expect_refusal wlan-missing radio-health 'wlan0, phy0 or driver missing'
expect_refusal rmtfs-mode radio-health 'unsafe rmtfs pidfile'
expect_refusal rmtfs-unreadable radio-health 'unreadable rmtfs pid'
expect_refusal rmtfs-partial radio-health 'invalid rmtfs pid'
expect_refusal rmtfs-pin radio-health 'pinned rmtfs or its mapped UIO is not live'
expect_refusal rmtfs-maps radio-health 'pinned rmtfs or its mapped UIO is not live'
expect_refusal service-process radio-health 'pd-mapper is not live'
expect_refusal kmsg-radio-fail radio-health 'cannot read radio kmsg'
expect_refusal kmsg-radio-grep-fail radio-health 'cannot inspect radio kmsg'
expect_refusal kmsg-inspect-fail radio-health 'cannot inspect kmsg snapshot'
expect_refusal kmsg-empty radio-health 'kmsg snapshot empty or oversized'
expect_refusal kmsg-unsafe radio-health 'unsafe kmsg snapshot'
expect_refusal kmsg-nul radio-health 'kmsg snapshot contains NUL or is unreadable'
expect_refusal mid-radio-fatal-before radio-health 'fatal radio evidence in kmsg'
expect_refusal mid-radio-fatal-after radio-health 'fatal radio evidence in kmsg'
expect_refusal fatal-radio radio-health 'fatal radio evidence in kmsg'
expect_refusal openrc-level services 'OpenRC default is not active'
expect_refusal service-status services 'local is not started'
expect_refusal service-link services 'networking runlevel link changed'
expect_refusal service-pin services 'networking service pin changed'
expect_refusal service-input services 'unsafe service input'
expect_refusal missing-ifquery services 'unsafe service input'
expect_refusal missing-lease-wrapper services 'unsafe service input'
expect_refusal missing-lease-helper services 'unsafe service input'
expect_refusal supplicant-unsafe services 'unsafe supplicant configuration'
expect_refusal profile-differs services 'service profile differs'
expect_refusal lease-pin services 'lease helper pin changed'
expect_refusal service-config services 'service inputs are not the stage own configuration'
expect_refusal runlevel-unsafe services 'unsafe OpenRC runlevel'
expect_refusal foreign-service services 'foreign OpenRC runlevel entry'
expect_refusal radio-changed services 'radio pin changed during stages'
expect_refusal ssh-pid services 'guest SSH pidfile absent'
expect_refusal ssh-unreadable services 'guest SSH pid unreadable'
expect_refusal ssh-pid-invalid services 'invalid guest SSH pid'
expect_refusal ssh-command services 'guest SSH process not healthy'
expect_refusal ssh-listener services 'guest SSH listener missing'
expect_refusal association-query association 'iw link failed'
expect_refusal association-disconnected association 'wlan0 is not associated'
expect_refusal stage-evidence association 'cannot record stage success'
expect_refusal guard-nonce-change association 'boot, root, nonce or unacknowledged guard changed'
expect_refusal guard-armed-change association 'boot, root, nonce or unacknowledged guard changed'
expect_refusal guard-accepted-change association 'boot, root, nonce or unacknowledged guard changed'
expect_refusal guard-ack-change association 'boot, root, nonce or unacknowledged guard changed'
expect_refusal address-query address 'address query failed'
expect_refusal address-invalid address 'no sane global-scope wlan0 IPv4 address'
expect_refusal address-partial address 'no sane global-scope wlan0 IPv4 address'
expect_refusal route-query route 'default route query failed'
expect_refusal route-duplicate route 'expected one default route via wlan0'
expect_refusal gateway-invalid route 'invalid gateway'
expect_refusal gateway-ping gateway 'gateway ICMP on wlan0 failed'
expect_refusal internet-query internet 'internet route lookup failed'
expect_refusal internet-route internet 'internet route is not wlan0'
expect_refusal internet-ping internet 'internet ICMP on wlan0 failed'
expect_refusal resolver-query dns 'resolver unavailable'
expect_refusal resolver-invalid dns 'first resolver is not a sane IPv4 address'
expect_refusal resolver-partial dns 'first resolver is not a sane IPv4 address'
expect_refusal dns-query dns 'DNS route lookup failed'
expect_refusal dns-route dns 'DNS route is not wlan0'
expect_refusal dns-extract dns 'cannot extract DNS probe'
expect_refusal dns-chmod dns 'cannot protect DNS probe'
expect_refusal dns-pin dns 'DNS probe pin mismatch'
expect_refusal dns-failure dns 'bound DNS query returned no valid answer'
expect_refusal dns-invalid dns 'invalid DNS answer'
expect_refusal final-association-query final-health 'final association query failed'
expect_refusal final-association final-health 'association changed during checks'
expect_refusal final-address-query final-health 'final address query failed'
expect_refusal final-address final-health 'address changed during checks'
expect_refusal final-route-query final-health 'final route query failed'
expect_refusal final-route final-health 'default route changed during checks'
expect_refusal final-remoteproc final-health 'remoteproc changed before ACK'
expect_refusal final-service final-health 'local stopped before ACK'
expect_refusal final-wlan final-health 'WLAN driver disappeared before ACK'
expect_refusal final-rmtfs-missing final-health 'rmtfs pidfile disappeared before ACK'
expect_refusal final-rmtfs-invalid final-health 'invalid final rmtfs pid'
expect_refusal final-rmtfs final-health 'rmtfs stopped before ACK'
expect_refusal final-process final-health 'pd-mapper stopped before ACK'
expect_refusal kmsg-final-fail final-health 'cannot recheck radio kmsg'
expect_refusal kmsg-final-grep-fail final-health 'cannot inspect radio kmsg'
expect_refusal mid-final-fatal-before final-health 'fatal radio evidence before ACK'
expect_refusal mid-final-fatal-after final-health 'fatal radio evidence before ACK'
expect_refusal final-fatal final-health 'fatal radio evidence before ACK'
expect_refusal all-evidence all-checks 'cannot record final success'
expect_refusal staging-stale ack-publication 'stale ACK staging path'
expect_refusal stage-write-fail ack-publication 'cannot stage ACK'
expect_refusal staged-partial ack-publication 'unsafe staged ACK'
expect_refusal staged-wrong-boot ack-publication 'unsafe staged ACK'
expect_refusal staged-nonce-change ack-publication 'boot, root, nonce or unacknowledged guard changed'
expect_refusal staged-other ack-publication 'another ACK publisher is staging'

reset_case kmsg-oversized
if run_post; then fail 'oversized kmsg produced success'; fi
check_prefix kmsg-oversized
check_no_publication kmsg-oversized
gate=$ROOT/run/radio-bringup/success-gate-294
case "$( $BB cat "$gate/refusal")" in
	*'reason=kmsg snapshot empty or oversized') reason='kmsg snapshot empty or oversized';;
	*'reason=cannot read radio kmsg') reason='cannot read radio kmsg';;
	*) fail 'oversized kmsg: unexpected refusal';;
esac
check_evidence "$gate/refusal" "boot=$boot stage=radio-health result=refused-or-interrupted phase=before-publication reason=$reason"
check_passes radio-health
[ ! -e "$gate/published.ok" ] && [ ! -e "$gate/accepted.ok" ] && [ ! -e "$gate/kmsg" ] || fail 'oversized kmsg: false success or leaked snapshot'
printf 'pass: synthetic 1048577-byte kmsg refused with %s and no ACK\n' "$reason"

reset_case oversized-precise
if run_post; then fail 'precise 1048577-byte kmsg produced success'; fi
check_prefix oversized-precise
check_no_publication oversized-precise
[ "$( $BB cat "$ROOT/tmp/synthetic-snapshot-size")" = 1048576 ] || fail 'oversized-precise: incorrect baseline'
gate=$ROOT/run/radio-bringup/success-gate-294
case "$( $BB cat "$gate/refusal")" in
	*'reason=kmsg snapshot empty or oversized') reason='kmsg snapshot empty or oversized';;
	*'reason=cannot read radio kmsg') reason='cannot read radio kmsg';;
	*) fail 'precise oversized kmsg: unexpected refusal';;
esac
check_evidence "$gate/refusal" "boot=$boot stage=radio-health result=refused-or-interrupted phase=before-publication reason=$reason"
check_passes radio-health
[ ! -e "$gate/published.ok" ] && [ ! -e "$gate/accepted.ok" ] && [ ! -e "$gate/kmsg" ] || fail 'precise oversized kmsg: false success or leaked snapshot'
printf 'pass: precise 1048577-byte kmsg refused with %s and no ACK\n' "$reason"

reset_case kmsg-truncated-success
if run_post; then
	check_prefix kmsg-truncated-success
	check_publication kmsg-truncated-success
	[ -s "$ROOT/tmp/synthetic-kmsg-metadata" ] || fail 'truncated kmsg fixture did not exercise the radio snapshot'
	check_evidence "$ROOT/run/radio-bringup/success-gate-294/accepted.ok" "boot=$boot stage=guard-acceptance result=pass phase=guard-accepted reason=none"
	printf 'pass: short successful dmesg accepted; no truncation indicator is available in this BusyBox interface\n' >&2
else
	check_prefix kmsg-truncated-success
	check_no_publication kmsg-truncated-success
	[ -f "$ROOT/run/radio-bringup/success-gate-294/refusal" ] || fail 'truncated kmsg: missing refusal evidence'
	printf 'pass: truncated synthetic kmsg refused before ACK\n'
fi

for mode in radio-large-fatal-before radio-large-fatal-after exact-large-fatal-after final-large-fatal-before final-large-fatal-after; do
	reset_case "$mode"
	if run_post; then fail "$mode: fatal kmsg produced success"; fi
	check_prefix "$mode"
	check_no_publication "$mode"
	if [ "$mode" = exact-large-fatal-after ]; then
		[ "$( $BB cat "$ROOT/tmp/synthetic-snapshot-size")" = 1048576 ] || fail "$mode: incorrect 1 MiB snapshot size"
	fi
	gate=$ROOT/run/radio-bringup/success-gate-294
	case "$mode" in
		radio-*|exact-*) terminal=radio-health; expected='fatal radio evidence in kmsg';;
		final-*) terminal=final-health; expected='fatal radio evidence before ACK';;
	esac
	expected_text="boot=$boot stage=$terminal result=refused-or-interrupted phase=before-publication reason=$expected"
	if [ "$( $BB cat "$gate/refusal")" = "$expected_text" ]; then
		check_evidence "$gate/refusal" "$expected_text"
		check_passes "$terminal"
		printf 'pass: %s detected in bounded snapshot\n' "$mode"
	else
		case "$terminal" in
			radio-health) read_reason='cannot read radio kmsg';;
			final-health) read_reason='cannot recheck radio kmsg';;
		esac
		check_evidence "$gate/refusal" "boot=$boot stage=$terminal result=refused-or-interrupted phase=before-publication reason=$read_reason"
		check_passes "$terminal"
		snapshot_ok=0
		printf 'FAIL: %s: oversized-by-ulimit snapshot refused before fatal inspection\n' "$mode" >&2
	fi
	[ ! -e "$gate/published.ok" ] && [ ! -e "$gate/accepted.ok" ] && [ ! -e "$gate/kmsg" ] || fail "$mode: false success or leaked snapshot"
done

for mode in state-mode run-mode run-mount gate-exists gate-unsafe start-evidence; do
	reset_case "$mode"
	if run_post; then fail "$mode: candidate unexpectedly succeeded"; fi
	check_prefix "$mode"
	check_no_publication "$mode"
	gate=$ROOT/run/radio-bringup/success-gate-294
	case "$mode" in
		state-mode) reason='unsafe radio state directory';;
		run-mode) reason='run is not root-only';;
		run-mount) reason='run is not a same-boot tmpfs';;
		gate-exists) reason='one-shot gate already exists or cannot be created';;
		gate-unsafe) reason='unsafe gate directory';;
		start-evidence) reason='cannot record start';;
	esac
	if [ "$mode" = gate-unsafe ] || [ "$mode" = start-evidence ]; then
		check_evidence "$gate/refusal" "boot=$boot stage=initialization result=refused-or-interrupted phase=before-publication reason=$reason"
	else
		[ ! -e "$gate/started" ] && [ ! -e "$gate/refusal" ] || fail "$mode: unowned gate evidence written"
	fi
	$BB grep -qF "success-gate initialization before-publication refused-or-interrupted: $reason" "$ROOT/tmp/synthetic-contract-events" || fail "$mode: wrong synthetic contract event"
	printf 'pass: %s -> initialization\n' "$mode"
done

reset_case publication-race
if run_post; then fail 'competing publisher accepted'; fi
check_prefix publication-race
check_no_publication publication-race
[ "$( $BB cat "$ROOT/tmp/publication-attempts")" = attempt ] || fail 'competing publisher did not race atomic link'
[ "$( $BB cat "$ROOT/run/pid1-guard/ack")" = 'synthetic competing ack' ] || fail 'competing ACK replaced'
check_evidence "$ROOT/run/radio-bringup/success-gate-294/refusal" "boot=$boot stage=ack-publication result=refused-or-interrupted phase=publication-uncertain reason=atomic no-replace publication failed"
printf 'pass: competing ACK preserved by atomic no-replace publication\n'

for mode in published-corrupt published-guard-change unlink-fail published-replaced published-evidence; do
	reset_case "$mode"
	if run_post; then fail "$mode: candidate unexpectedly succeeded"; fi
	check_prefix "$mode"
	check_publication "$mode"
	gate=$ROOT/run/radio-bringup/success-gate-294
	case "$mode" in
		published-corrupt) phase=publication-uncertain; reason='published ACK is not the staged inode';;
		published-guard-change) phase=publication-uncertain; reason='guard or competing publisher changed during publication';;
		unlink-fail) phase=published-awaiting-guard; reason='cannot make ACK single-link';;
		published-replaced) phase=published-awaiting-guard; reason='published ACK changed without confirmed consumption';;
		published-evidence) phase=published-awaiting-guard; reason='cannot record ACK publication';;
	esac
	check_evidence "$gate/refusal" "boot=$boot stage=ack-publication result=refused-or-interrupted phase=$phase reason=$reason"
	if [ "$mode" = published-evidence ]; then
		[ -f "$gate/published.ok" ] && [ ! -s "$gate/published.ok" ] || fail "$mode: evidence write did not leave an empty file"
	else
		[ ! -e "$gate/published.ok" ] || fail "$mode: false publication evidence"
	fi
	[ ! -e "$gate/accepted.ok" ] || fail "$mode: false acceptance evidence"
	case "$mode" in
		published-corrupt|published-replaced)
			if $BB cmp -s "$ROOT/tmp/expected-ack" "$ROOT/run/pid1-guard/ack"; then fail "$mode: corrupt ACK remained valid"; fi;;
		published-guard-change|unlink-fail|published-evidence)
			$BB cmp -s "$ROOT/tmp/expected-ack" "$ROOT/run/pid1-guard/ack" || fail "$mode: published ACK state differs";;
	esac
	printf 'pass: %s -> %s\n' "$mode" "$phase"
done

for mode in interrupt-before interrupt-before-link interrupt-after-link interrupt-before-unlink interrupt-after-publication interrupt-after-evidence; do
	reset_case "$mode"
	if run_post; then fail "$mode: interrupted candidate succeeded"; fi
	check_prefix "$mode"
	gate=$ROOT/run/radio-bringup/success-gate-294
	case "$mode" in
		interrupt-before)
			check_no_publication "$mode"
			terminal=association; phase=before-publication;;
		interrupt-before-link)
			check_no_publication "$mode"
			terminal=ack-publication; phase=publication-uncertain;;
		interrupt-after-link)
			check_publication "$mode"
			[ -f "$ROOT/run/pid1-guard/ack" ] && [ -f "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "$mode: linked ACK missing"
			terminal=ack-publication; phase=publication-uncertain;;
		interrupt-before-unlink)
			check_publication "$mode"
			[ -f "$ROOT/run/pid1-guard/ack" ] && [ -f "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "$mode: linked ACK missing"
			terminal=ack-publication; phase=published-awaiting-guard;;
		interrupt-after-publication)
			check_publication "$mode"
			[ -f "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "$mode: published ACK state differs"
			terminal=ack-publication; phase=published-awaiting-guard;;
		interrupt-after-evidence)
			check_publication "$mode"
			[ -f "$ROOT/run/pid1-guard/ack" ] && [ ! -e "$ROOT/run/pid1-guard/.success-gated-ack-new" ] || fail "$mode: published ACK state differs"
			check_evidence "$gate/published.ok" "boot=$boot stage=ack-publication result=pass phase=published-awaiting-guard reason=none"
			terminal=guard-acceptance; phase=published-awaiting-guard;;
	esac
	check_evidence "$gate/refusal" "boot=$boot stage=$terminal result=refused-or-interrupted phase=$phase reason=signal-TERM"
	if [ "$mode" != interrupt-after-evidence ]; then
		[ ! -e "$gate/published.ok" ] || fail "$mode: premature publication evidence"
	fi
	[ ! -e "$gate/accepted.ok" ] || fail "$mode: interruption falsely accepted"
	printf 'pass: %s -> %s\n' "$mode" "$phase"
done

for mode in acceptance-timeout accepted-wrong-boot accepted-partial wait-root-change accepted-evidence; do
	reset_case "$mode"
	if run_post; then fail "$mode: candidate falsely reported acceptance"; fi
	check_prefix "$mode"
	check_publication "$mode"
	gate=$ROOT/run/radio-bringup/success-gate-294
	check_evidence "$gate/published.ok" "boot=$boot stage=ack-publication result=pass phase=published-awaiting-guard reason=none"
	case "$mode" in
		wait-root-change) phase=published-awaiting-guard; reason='boot or root changed while awaiting guard';;
		accepted-evidence) phase=guard-accepted; reason='guard accepted but evidence write failed';;
		*) phase=published-awaiting-guard; reason='acceptance not confirmed; ACK may still be consumed';;
	esac
	check_evidence "$gate/refusal" "boot=$boot stage=guard-acceptance result=refused-or-interrupted phase=$phase reason=$reason"
	if [ "$mode" = accepted-evidence ]; then
		[ -f "$gate/accepted.ok" ] && [ ! -s "$gate/accepted.ok" ] || fail "$mode: evidence write did not leave an empty file"
		check_evidence "$ROOT/run/pid1-guard/accepted" "$boot"
	else
		[ ! -e "$gate/accepted.ok" ] || fail "$mode: false acceptance evidence"
	fi
	printf 'pass: %s -> %s\n' "$mode" "$phase"
done

reset_case association-disconnected
if run_post; then fail 'replay setup unexpectedly succeeded'; fi
check_no_publication replay-setup
$BB cp "$ROOT/run/radio-bringup/success-gate-294/refusal" "$ROOT/tmp/original-refusal"
$BB rm -f "$ROOT/run/radio-bringup/"*.marker "$ROOT/tmp/stages" "$ROOT/tmp/services-stdin" "$ROOT/tmp/services.done"
$BB cp "$ROOT/tmp/synthetic-record.before" "$ROOT/.omnipha-boot-record"
$BB printf 'synthetic profile\n' > "$ROOT/run/radio-bringup/wpa_supplicant.conf"
$BB chmod 600 "$ROOT/run/radio-bringup/wpa_supplicant.conf"
$BB printf 'success\n' > "$ROOT/tmp/mode"
if run_post; then fail 'same-boot replay succeeded'; fi
check_prefix replay
check_no_publication replay
$BB cmp -s "$ROOT/tmp/original-refusal" "$ROOT/run/radio-bringup/success-gate-294/refusal" || fail 'replay overwrote prior refusal evidence'
$BB grep -qF 'one-shot gate already exists or cannot be created' "$ROOT/tmp/synthetic-contract-events" || fail 'same-boot replay did not refuse the existing gate in the synthetic contract event'
printf 'pass: same-boot replay refused without replacing prior evidence\n'
[ "$snapshot_ok" = 1 ] || fail 'bounded kmsg coverage exposed a size-limit or truncation problem'
