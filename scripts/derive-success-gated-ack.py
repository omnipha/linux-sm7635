#!/usr/bin/env python3
"""Derive a host-only #294 candidate from the exact #291 post and radio.

usage: derive-success-gated-ack.py FRESH_POST RADIO POST_OUTPUT HOOK_OUTPUT

The output corrects the measured panel restore in the pinned post, then appends
an unchanged gate. It embeds a pinned static AArch64 DNS client, built twice
with aarch64-linux-gnu-gcc and rejected unless
its bytes match the recorded build. Compiler, linker or libc differences can
make this fail. Output paths must be new files outside the repository.
The gate writes volatile, root-only evidence and uses the unchanged guard's
ACK protocol. The hook launches only after both script pins pass; it does not
change existing guard recovery, deadline or evidence limitations.
"""
import base64
import hashlib
import os
import pathlib
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap

RADIO_PATH = '/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh'
POST_PATH = '/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh'
FRESH_RADIO_SHA = 'a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21'
FRESH_POST_SHA = 'c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7'
DNS_PROBE_SHA = '906a3c3f3f5c7a666f394dff434604a4b6a6bf2d683d8e04e3d947316132fe97'
DNS_PROBE_SIZE = 597840

PANEL_OLD = r'''trace 'pre check panel record'
panel=/run/pmos-pre-ssh-panel.record
if [ ! -e "$panel" ] && [ ! -L "$panel" ] && [ -f /.omnipha-boot-record ] && [ ! -L /.omnipha-boot-record ]; then
	panel_hits=$($BB dmesg 2>/dev/null | $BB sed 's/^<[0-9][0-9]*>//; s/^\(\[[ 0-9.]*\] \)\{0,1\}usb-init: //' | $BB grep -E "^usb-init: pre-SSH panel node=(boe|vxn|none) card0=[ -~]* boot $boot\$")
	panel_line=
	if [ -n "$panel_hits" ] && [ "$($BB printf '%s\n' "$panel_hits" | $BB sort -u | $BB wc -l)" = 1 ]; then
		panel_line=$($BB printf '%s\n' "$panel_hits" | $BB sed -n 1p)
	fi
	if [ -n "$panel_line" ] && [ "${#panel_line}" -le 400 ] &&
		[ "${panel_line% boot $boot}" != "$panel_line" ] &&
		[ "$($BB sed -n 3p /.omnipha-boot-record 2>/dev/null)" = "$panel_line" ]; then
		( umask 077; set -C; $BB printf '%s\n' "$panel_line" > "$panel" ) || die 'cannot restore the pre-SSH panel record'
		[ -f "$panel" ] && [ ! -L "$panel" ] && [ "$($BB stat -c '%u:%a:%h' "$panel")" = 0:600:1 ] ||
			die 'restored pre-SSH panel record is unsafe'
		trace 'panel record restored from the boot kernel log'
	fi
fi
trace 'post check panel record'
'''
PANEL_NEW = r'''trace 'pre check panel record'
panel=/run/pmos-pre-ssh-panel.record
case "$boot" in
	????????-????-????-????-????????????)
		panel_boot_hex=$(set -o pipefail; $BB printf '%s' "$boot" | $BB tr -d '-') || die 'invalid panel boot identity'
		[ "${#panel_boot_hex}" = 32 ] || die 'invalid panel boot identity'
		case "$panel_boot_hex" in *[!0-9a-f]*) die 'invalid panel boot identity';; esac;;
	*) die 'invalid panel boot identity';;
esac
panel_hits=$(set -o pipefail; $BB dmesg 2>/dev/null | $BB sed 's/^<[0-9][0-9]*>//; s/^\(\[[ 0-9.]*\]\(\[ *[TC][0-9][0-9]*\]\)\{0,1\} \)\{0,1\}usb-init: //' | $BB grep -F 'usb-init: pre-SSH panel') || die 'same-boot panel evidence unavailable'
[ -n "$panel_hits" ] || die 'same-boot panel evidence unavailable'
panel_unique=$(set -o pipefail; $BB printf '%s\n' "$panel_hits" | $BB sort -u) || die 'cannot validate panel evidence'
panel_count=$(set -o pipefail; $BB printf '%s\n' "$panel_unique" | $BB wc -l) || die 'cannot count panel evidence'
panel_payload=${panel_unique% boot "$boot"}
[ "$panel_count" = 1 ] && [ "${#panel_unique}" -le 400 ] && [ "$panel_payload" != "$panel_unique" ] &&
	(set -o pipefail; $BB printf '%s\n' "$panel_unique" | $BB grep -Eq "^usb-init: pre-SSH panel node=(boe|vxn|none) card0=[ -~]* boot [0-9a-f-]{36}\$") || die 'ambiguous or invalid same-boot panel evidence'
panel_line=$($BB sed -n 3p /.omnipha-boot-record 2>/dev/null) || die 'cannot read ordered panel record'
[ "$panel_line" = "$panel_unique" ] || die 'same-boot panel evidence differs from ordered record'
if [ -e "$panel" ] || [ -L "$panel" ]; then
	[ -f "$panel" ] && [ ! -L "$panel" ] && [ "$($BB stat -c '%u:%a:%h:%s' "$panel")" = "0:600:1:$((${#panel_unique} + 1))" ] &&
		[ "$($BB cat "$panel")" = "$panel_unique" ] || die 'existing pre-SSH panel record is unsafe or differs'
else
	( umask 077; set -C; $BB printf '%s\n' "$panel_unique" > "$panel" ) || die 'cannot restore the pre-SSH panel record'
	[ -f "$panel" ] && [ ! -L "$panel" ] && [ "$($BB stat -c '%u:%a:%h:%s' "$panel")" = "0:600:1:$((${#panel_unique} + 1))" ] &&
		[ "$($BB cat "$panel")" = "$panel_unique" ] || die 'restored pre-SSH panel record is unsafe'
	trace 'panel record restored from the boot kernel log'
fi
trace 'post check panel record'
'''

DNS_C = r'''
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/random.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

static const unsigned char question[] = {
    7,'e','x','a','m','p','l','e',3,'c','o','m',0,0,1,0,1
};

static int sane(const unsigned char *a) {
    return a[0] != 0 && a[0] != 127 && a[0] < 224 &&
           !(a[0] == 169 && a[1] == 254) && a[3] != 0 && a[3] != 255;
}

static int name(const unsigned char *p, size_t n, size_t *pos, int *matches) {
    size_t at = *pos, end = 0, q = 0, labels = 0;
    int match = 1;
    while (1) {
        if (at >= n || ++labels > 128) return 0;
        unsigned int len = p[at++];
        if ((len & 0xc0) == 0xc0) {
            if (at >= n) return 0;
            size_t target = ((len & 0x3f) << 8) | p[at++];
            if (target >= at - 2) return 0;
            if (!end) end = at;
            at = target;
            continue;
        }
        if (len & 0xc0 || len > 63 || at + len > n || q + len + 1 > 255) return 0;
        if (q >= sizeof question - 4 || question[q] != len) match = 0;
        q++;
        if (!len) break;
        for (unsigned int i = 0; i < len; i++, q++) {
            unsigned char c = p[at++];
            if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
            if (q >= sizeof question - 4 || c != question[q]) match = 0;
        }
    }
    *pos = end ? end : at;
    *matches = match && q == sizeof question - 4;
    return 1;
}

static int answer(const unsigned char *p, size_t n, const unsigned char *id,
                  unsigned char *address) {
    if (n < 12 || p[0] != id[0] || p[1] != id[1] ||
        (p[2] & 0xfa) != 0x80 || (p[3] & 15) || p[4] || p[5] != 1)
        return 0;
    unsigned int count = (p[6] << 8) | p[7];
    if (!count || count > 100) return 0;
    size_t pos = 12;
    int matches, found = 0;
    if (!name(p, n, &pos, &matches) || !matches || pos + 4 > n ||
        p[pos] || p[pos+1] != 1 || p[pos+2] || p[pos+3] != 1) return 0;
    pos += 4;
    for (unsigned int i = 0; i < count; i++) {
        if (!name(p, n, &pos, &matches) || pos + 10 > n) return 0;
        unsigned int type = (p[pos] << 8) | p[pos+1];
        unsigned int class = (p[pos+2] << 8) | p[pos+3];
        unsigned int len = (p[pos+8] << 8) | p[pos+9];
        pos += 10;
        if (pos + len > n) return 0;
        if (matches && type == 1 && class == 1 && len == 4 && sane(p + pos)) {
            memcpy(address, p + pos, 4);
            found = 1;
        }
        pos += len;
    }
    return found;
}

int main(int argc, char **argv) {
    struct sockaddr_in peer = {0};
    struct timeval timeout = {4, 0};
    unsigned char query[12 + sizeof question] = {0};
    unsigned char response[4096], address[4];
    if (argc != 2 || inet_pton(AF_INET, argv[1], &peer.sin_addr) != 1 ||
        !sane((const unsigned char *)&peer.sin_addr)) return 1;
    if (getrandom(query, 2, GRND_NONBLOCK) != 2) return 1;
    query[2] = 1;
    query[5] = 1;
    memcpy(query + 12, question, sizeof question);
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return 1;
    peer.sin_family = AF_INET;
    peer.sin_port = htons(53);
    if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, "wlan0", 6) ||
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout) ||
        connect(fd, (struct sockaddr *)&peer, sizeof peer) ||
        send(fd, query, sizeof query, 0) != sizeof query) {
        close(fd);
        return 1;
    }
    ssize_t n = recv(fd, response, sizeof response, 0);
    close(fd);
    if (n < 0 || !answer(response, (size_t)n, query, address)) return 1;
    return printf("%u.%u.%u.%u\n", address[0], address[1], address[2], address[3]) < 0;
}
'''

GATE = r'''
GATE_DIR="$STATE/success-gate-294"
gate_owned=0
gate_complete=0
gate_phase=before-publication
gate_stage=initialization
gate_reason=unexpected-exit

gate_message() {
	$BB printf 'pmos-self-post: success-gate boot=%s stage=%s phase=%s %s\n' "$boot" "$gate_stage" "$gate_phase" "$1" >/dev/kmsg 2>/dev/null || true
}

gate_file() (
	g_file="$GATE_DIR/$1"
	g_text="boot=$boot stage=$2 result=$3 phase=$gate_phase reason=${4:-none}"
	(umask 077; set -C; $BB printf '%s\n' "$g_text" > "$g_file") || exit 1
	[ -f "$g_file" ] && [ ! -L "$g_file" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$g_file" 2>/dev/null)" = "0:600:1:$((${#g_text} + 1))" ] &&
		[ "$($BB cat "$g_file" 2>/dev/null)" = "$g_text" ]
)

gate_exit() {
	g_exit=$1
	trap - EXIT HUP INT TERM
	if [ "$gate_complete" != 1 ]; then
		gate_message "refused-or-interrupted exit=$g_exit; guard outcome is not inferred"
		if [ "$gate_owned" = 1 ]; then
			gate_file refusal "$gate_stage" refused-or-interrupted "$gate_reason" || true
		fi
		(record_fail "success-gate $gate_stage $gate_phase refused-or-interrupted: $gate_reason") || true
	fi
	if [ "$gate_owned" = 1 ]; then
		$BB timeout -k 1 2 $BB rm -f "$GATE_DIR/dns-probe" "$GATE_DIR/kmsg" >/dev/null 2>&1 || true
	fi
	scrub || true
}

gate_fail() {
	gate_reason=$1
	gate_message "refused $1; guard outcome is not inferred"
	exit 1
}

gate_signal() {
	gate_reason="signal-$1"
	gate_message "interrupted by $1; guard outcome is not inferred"
	exit 1
}

trap 'gate_exit $?' EXIT
trap 'gate_signal HUP' HUP
trap 'gate_signal INT' INT
trap 'gate_signal TERM' TERM

[ -d "$STATE" ] && [ ! -L "$STATE" ] &&
	[ "$($BB stat -c '%u:%a' "$STATE" 2>/dev/null)" = 0:700 ] || gate_fail 'unsafe radio state directory'
[ -d /run ] && [ ! -L /run ] && [ "$($BB stat -c '%u:%a' /run 2>/dev/null)" = 0:700 ] || gate_fail 'run is not root-only'
$BB awk '$2 == "/run" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}' /proc/1/mounts || gate_fail 'run is not a same-boot tmpfs'
$BB mkdir -m 700 "$GATE_DIR" 2>/dev/null || gate_fail 'one-shot gate already exists or cannot be created'
gate_owned=1
[ -d "$GATE_DIR" ] && [ ! -L "$GATE_DIR" ] &&
	[ "$($BB stat -c '%u:%a' "$GATE_DIR" 2>/dev/null)" = 0:700 ] || gate_fail 'unsafe gate directory'
gate_file started initialization started || gate_fail 'cannot record start'
gate_message started

gate_identity() {
	[ "$($BB id -u)" = 0 ] &&
	[ "$($BB cat /proc/sys/kernel/random/boot_id 2>/dev/null)" = "$boot" ] &&
	[ -d "$GUARD" ] && [ ! -L "$GUARD" ] &&
	[ "$($BB stat -c '%u:%a' "$GUARD" 2>/dev/null)" = 0:700 ] &&
	[ -f "$GUARD/armed" ] && [ ! -L "$GUARD/armed" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/armed" 2>/dev/null)" = "0:600:1:$((${#boot} + 1))" ] &&
	[ "$($BB cat "$GUARD/armed" 2>/dev/null)" = "$boot" ] &&
	[ -f "$GUARD/root-identity" ] && [ ! -L "$GUARD/root-identity" ] &&
	[ "$($BB stat -c '%u:%a:%h' "$GUARD/root-identity" 2>/dev/null)" = 0:600:1 ] &&
	g_root=$($BB cat "$GUARD/root-identity" 2>/dev/null) &&
	[ -n "$g_root" ] && [ "$($BB stat -c '%d:%i' / 2>/dev/null)" = "$g_root" ] &&
	[ "$($BB stat -Lc '%d:%i' /proc/1/root 2>/dev/null)" = "$g_root" ] &&
	[ -L /proc/1/exe ] &&
	g_pid_hash=$($BB sha256sum /proc/1/exe 2>/dev/null) &&
	g_bb_hash=$($BB sha256sum /bin/busybox 2>/dev/null) &&
	[ "${g_pid_hash%% *}" = "${g_bb_hash%% *}" ] &&
	$BB timeout -k 1 5 $BB sh -c '
		BB=/bin/busybox
		if $BB awk '\''$2 == "/" {n++; if ($3 != "tmpfs") bad++} END {exit(n != 1 || bad)}'\'' /proc/1/mounts; then exit 0; fi
		[ -f /run/pid1-guard/root-contract.sh ] && [ ! -L /run/pid1-guard/root-contract.sh ] &&
		. /run/pid1-guard/root-contract.sh && root_contract_switched_root /proc/1/mounts /proc/1/mountinfo
	' >/dev/null 2>&1
}

gate_live() {
	gate_identity &&
	[ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/nonce" 2>/dev/null)" = 0:600:1:65 ] &&
	[ "$($BB cat "$GUARD/nonce" 2>/dev/null)" = "$gate_nonce" ] &&
	[ ! -e "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] &&
	[ ! -e "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
	[ -d "$GATE_DIR" ] && [ ! -L "$GATE_DIR" ] &&
	[ "$($BB stat -c '%u:%a' "$GATE_DIR" 2>/dev/null)" = 0:700 ]
}

gate_check() { gate_live || gate_fail 'boot, root, nonce or unacknowledged guard changed'; }

gate_snapshot() {
	[ -d "$GATE_DIR" ] && [ ! -L "$GATE_DIR" ] &&
		[ "$($BB stat -c '%u:%a' "$GATE_DIR" 2>/dev/null)" = 0:700 ] || gate_fail 'unsafe kmsg snapshot directory'
	[ ! -e "$GATE_DIR/kmsg" ] && [ ! -L "$GATE_DIR/kmsg" ] || gate_fail 'unsafe kmsg snapshot path'
	(umask 077; set -C
		$BB timeout -k 1 5 $BB sh -c '
			set -o pipefail || exit 1
			exec 3>&1
			"$1" timeout -k 1 5 "$1" dmesg -r -s 2097152 2>/dev/null |
				{ "$1" head -c 1048577; exec 1>&3; "$1" head -c 1 >/dev/null 2>&1; }
		' sh "$BB" > "$GATE_DIR/kmsg" 2>/dev/null
	) || gate_fail "$1"
	[ -f "$GATE_DIR/kmsg" ] && [ ! -L "$GATE_DIR/kmsg" ] || gate_fail 'unsafe kmsg snapshot'
	g_kmsg_stat=$($BB stat -c '%u:%a:%h:%s' "$GATE_DIR/kmsg" 2>/dev/null) || gate_fail 'unsafe kmsg snapshot'
	case "$g_kmsg_stat" in 0:600:1:*) g_kmsg_size=${g_kmsg_stat#0:600:1:};; *) gate_fail 'unsafe kmsg snapshot';; esac
	case "$g_kmsg_size" in ''|*[!0-9]*) gate_fail 'unsafe kmsg snapshot';; esac
	[ "$g_kmsg_size" -gt 0 ] && [ "$g_kmsg_size" -le 1048576 ] || gate_fail 'kmsg snapshot empty or oversized'
	gate_snapshot_verify
	g_kmsg_filtered=$(set -o pipefail || exit 1; $BB timeout -k 1 5 $BB tr -d '\000' < "$GATE_DIR/kmsg" | $BB wc -c) || gate_fail 'cannot inspect kmsg snapshot'
	[ "$g_kmsg_filtered" = "$g_kmsg_size" ] || gate_fail 'kmsg snapshot contains NUL or is unreadable'
	gate_snapshot_verify
}

gate_snapshot_verify() {
	[ -f "$GATE_DIR/kmsg" ] && [ ! -L "$GATE_DIR/kmsg" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$GATE_DIR/kmsg" 2>/dev/null)" = "$g_kmsg_stat" ] || gate_fail 'unsafe kmsg snapshot'
}

gate_snapshot_remove() {
	gate_snapshot_verify
	$BB rm "$GATE_DIR/kmsg" || gate_fail 'cannot remove kmsg snapshot'
}

gate_fatal_check() {
	gate_snapshot_verify
	g_kmsg_rc=0
	$BB timeout -k 1 5 $BB grep -Ei 'fatal error received:|fs_device_efs_rmts.c|hdd_psoc_idle_timeout_callback|kernel panic' "$GATE_DIR/kmsg" >/dev/null 2>&1 || g_kmsg_rc=$?
	case "$g_kmsg_rc" in 0) gate_fail "$1";; 1) gate_snapshot_verify;; *) gate_fail 'cannot inspect radio kmsg';; esac
}

gate_pass() {
	gate_check
	gate_file "$gate_stage.ok" "$gate_stage" pass || gate_fail 'cannot record stage success'
	gate_message pass
}

gate_stage=nonce-and-radio-markers
gate_identity || gate_fail 'boot or root identity changed'
[ ! -e "$GUARD/.ack-new" ] && [ ! -L "$GUARD/.ack-new" ] || gate_fail 'another ACK publisher is staging'
[ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/nonce" 2>/dev/null)" = 0:600:1:65 ] || gate_fail 'unsafe nonce'
gate_nonce=$($BB cat "$GUARD/nonce") || gate_fail 'cannot read nonce'
case "$gate_nonce" in
	????????????????????????????????????????????????????????????????) case "$gate_nonce" in *[!0-9a-f]*) gate_fail 'invalid nonce';; esac;;
	*) gate_fail 'invalid nonce';;
esac
gate_check
gate_snapshot 'cannot read same-boot kmsg'
for g_stage in modem wpss driver scan services; do
	g_token="guest-radio-$g_stage-$($BB printf '%s' "$boot:$gate_nonce:$g_stage" | $BB sha256sum | $BB cut -c 1-16)"
	g_marker="$STATE/$g_stage.marker"
	[ -f "$g_marker" ] && [ ! -L "$g_marker" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$g_marker" 2>/dev/null)" = "0:600:1:$((${#g_token} + 1))" ] &&
		[ "$($BB cat "$g_marker" 2>/dev/null)" = "$g_token" ] || gate_fail "invalid $g_stage capture marker"
	gate_snapshot_verify
	g_count=$($BB timeout -k 1 5 $BB grep -Fc "pmos-self-post: guest radio marker $g_token" "$GATE_DIR/kmsg" 2>/dev/null) || gate_fail "missing or duplicate $g_stage kmsg marker"
	gate_snapshot_verify
	[ "$g_count" = 1 ] || gate_fail "missing or duplicate $g_stage kmsg marker"
done
gate_snapshot_remove
gate_pass

gate_stage=radio-health
gate_check
for g_spec in 'remoteproc2 4080000.remoteproc-mss' 'remoteproc3 9bb00000.remoteproc-wpss'; do
	set -- $g_spec
	[ "$($BB timeout -k 1 2 $BB cat "/sys/class/remoteproc/$1/name" 2>/dev/null)" = "$2" ] &&
	[ "$($BB timeout -k 1 2 $BB cat "/sys/class/remoteproc/$1/state" 2>/dev/null)" = running ] || gate_fail 'remoteproc identity or state'
done
[ -e /sys/class/net/wlan0 ] && [ -d /sys/class/ieee80211/phy0 ] &&
	[ -d /sys/module/qca_cld3_qca6750 ] || gate_fail 'wlan0, phy0 or driver missing'
[ -f "$STATE/rmtfs.pid" ] && [ ! -L "$STATE/rmtfs.pid" ] &&
	[ "$($BB stat -c '%u:%a:%h' "$STATE/rmtfs.pid" 2>/dev/null)" = 0:600:1 ] || gate_fail 'unsafe rmtfs pidfile'
g_pid=$($BB cat "$STATE/rmtfs.pid") || gate_fail 'unreadable rmtfs pid'
case "$g_pid" in ''|*[!0-9]*) gate_fail 'invalid rmtfs pid';; esac
[ "$($BB cat "/proc/$g_pid/comm" 2>/dev/null)" = rmtfs ] &&
	[ "$(hash "/proc/$g_pid/exe")" = d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd ] &&
	$BB grep -q '/dev/uio0' "/proc/$g_pid/maps" &&
	[ "$($BB cat /sys/class/uio/uio0/name 2>/dev/null)" = rmtfs ] || gate_fail 'pinned rmtfs or its mapped UIO is not live'
for g_service in pd-mapper tqftpserv; do
	$BB timeout -k 1 3 $BB pidof "$g_service" >/dev/null 2>&1 || gate_fail "$g_service is not live"
done
gate_snapshot 'cannot read radio kmsg'
gate_fatal_check 'fatal radio evidence in kmsg'
gate_snapshot_remove
gate_pass

gate_stage=services
gate_check
[ "$($BB cat /run/openrc/softlevel 2>/dev/null)" = default ] || gate_fail 'OpenRC default is not active'
for g_service in local networking wpa_supplicant; do
	$BB timeout -k 1 5 /sbin/rc-service "$g_service" status >/dev/null 2>&1 || gate_fail "$g_service is not started"
	[ -L "/etc/runlevels/default/$g_service" ] &&
		[ "$($BB readlink "/etc/runlevels/default/$g_service")" = "/etc/init.d/$g_service" ] || gate_fail "$g_service runlevel link changed"
done
for g_spec in 'networking 334b685600b13549bb852aa5bc8f7942caf314155a481b5984a557af867df50c' 'wpa_supplicant a648c2306b296f8bbba61fcc2d0433c514f45ff4bdda68a88b22948acc9eb75f'; do
	set -- $g_spec
	[ -f "/etc/init.d/$1" ] && [ ! -L "/etc/init.d/$1" ] &&
		[ "$(hash "/etc/init.d/$1")" = "$2" ] || gate_fail "$1 service pin changed"
done
for g_spec in '/etc/network/interfaces 600' '/etc/conf.d/networking 600' "$STATE/ifquery-wlan 700" "$STATE/lease-wrapper.sh 700" "$STATE/wlan-udhcpc-lease.sh 700" "$PROFILE 600" '/etc/wpa_supplicant/wpa_supplicant.conf 600'; do
	set -- $g_spec
	[ -f "$1" ] && [ ! -L "$1" ] && [ "$($BB stat -c '%u:%a:%h' "$1" 2>/dev/null)" = "0:$2:1" ] || gate_fail 'unsafe service input'
done
[ -f /etc/conf.d/wpa_supplicant ] && [ ! -L /etc/conf.d/wpa_supplicant ] || gate_fail 'unsafe supplicant configuration'
case "$($BB stat -c '%u:%a:%h' /etc/conf.d/wpa_supplicant 2>/dev/null)" in 0:600:1|0:644:1) :;; *) gate_fail 'unsafe supplicant configuration';; esac
g_profile_hash=$(hash "$PROFILE")
[ "${#g_profile_hash}" = 64 ] && [ "$g_profile_hash" = "$(hash /etc/wpa_supplicant/wpa_supplicant.conf)" ] && [ -s "$PROFILE" ] || gate_fail 'service profile differs'
[ "$(hash "$STATE/wlan-udhcpc-lease.sh")" = 1fbf50af4658eee252a3fb6b35d32c758106b89d1757d5b9bf10cc0554e03f56 ] || gate_fail 'lease helper pin changed'
[ "$($BB cat /etc/network/interfaces)" = "$( $BB printf 'auto wlan0\niface wlan0 inet dhcp\n\tdhcp-script /run/radio-bringup/lease-wrapper.sh\n\tudhcpc-opts -t 5 -T 3 -A 5 -n\n' )" ] &&
[ "$($BB cat /etc/conf.d/networking)" = 'ifquery=/run/radio-bringup/ifquery-wlan' ] &&
[ "$($BB cat /etc/conf.d/wpa_supplicant)" = "$( $BB printf 'wpa_supplicant_args=""\nwpa_supplicant_if="wlan0"\n' )" ] &&
[ "$($BB cat "$STATE/lease-wrapper.sh")" = "$( $BB printf '#!/bin/busybox sh\nIP_CMD=/sbin/ip\nexport IP_CMD\nexec /bin/busybox sh /run/radio-bringup/wlan-udhcpc-lease.sh "$@"\n' )" ] &&
[ "$($BB cat "$STATE/ifquery-wlan")" = "$( $BB printf '#!/bin/busybox sh\nif [ "$#" = 4 ] && [ "$1" = -i ] && [ "$2" = /etc/network/interfaces ] && [ "$3" = --list ] && [ "$4" = -a ]; then /bin/busybox printf "wlan0\\n"; exit 0; fi\nexec /sbin/ifquery "$@"\n' )" ] || gate_fail 'service inputs are not the stage own configuration'
for g_level in sysinit boot default nonetwork shutdown; do
	g_path="/etc/runlevels/$g_level"
	[ -d "$g_path" ] && [ ! -L "$g_path" ] || gate_fail 'unsafe OpenRC runlevel'
	for g_entry in "$g_path"/* "$g_path"/.[!.]* "$g_path"/..?*; do
		[ ! -e "$g_entry" ] && [ ! -L "$g_entry" ] && continue
		case "$g_entry" in
			/etc/runlevels/default/local|/etc/runlevels/default/networking|/etc/runlevels/default/wpa_supplicant)
				[ -L "$g_entry" ] && [ "$($BB readlink "$g_entry")" = "/etc/init.d/${g_entry##*/}" ] || gate_fail 'foreign OpenRC runlevel entry';;
			*) gate_fail 'foreign OpenRC runlevel entry';;
		esac
	done
done
[ "$(hash "$RADIO")" = "$RADIO_SHA" ] || gate_fail 'radio pin changed during stages'
[ -f /run/dropbear-session.pid ] && [ ! -L /run/dropbear-session.pid ] || gate_fail 'guest SSH pidfile absent'
g_pid=$($BB cat /run/dropbear-session.pid) || gate_fail 'guest SSH pid unreadable'
case "$g_pid" in ''|*[!0-9]*) gate_fail 'invalid guest SSH pid';; esac
[ "$($BB stat -Lc '%d:%i' "/proc/$g_pid/root" 2>/dev/null)" = "$($BB stat -c '%d:%i' /)" ] &&
	$BB tr '\000' ' ' < "/proc/$g_pid/cmdline" | $BB grep -q 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' || gate_fail 'guest SSH process not healthy'
$BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {n++} END {exit(n != 1)}' /proc/net/tcp || gate_fail 'guest SSH listener missing'
gate_pass

gate_ipv4() {
	$BB printf '%s\n' "$1" | $BB awk '
	NR != 1 {exit 1}
	{
		if ($0 !~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ || split($0,a,".") != 4) exit 1
		for (i=1;i<=4;i++) if (length(a[i]) > 3 || (length(a[i]) > 1 && substr(a[i],1,1) == "0") || a[i]+0 > 255) exit 1
		if (a[1]+0 == 0 || a[1]+0 == 127 || a[1]+0 >= 224 || (a[1]+0 == 169 && a[2]+0 == 254) || a[4]+0 == 0 || a[4]+0 == 255) exit 1
		ok=1
	} END {if (!ok) exit 1}'
}

gate_stage=association
gate_check
g_link=$($BB timeout -k 1 5 /usr/sbin/iw dev wlan0 link 2>/dev/null) || gate_fail 'iw link failed'
$BB printf '%s\n' "$g_link" | $BB awk 'NR == 1 && $1 == "Connected" && $2 == "to" && $4 == "(on" && $5 == "wlan0)" && $3 ~ /^[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]$/ {ok=1} END {exit(!ok)}' || gate_fail 'wlan0 is not associated'
gate_pass

gate_stage=address
gate_check
g_addrs=$($BB timeout -k 1 5 /sbin/ip -o -4 addr show dev wlan0 scope global 2>/dev/null) || gate_fail 'address query failed'
g_addr=$($BB printf '%s\n' "$g_addrs" | $BB awk '$2 == "wlan0" && $3 == "inet" && $0 !~ /tentative|dadfailed|deprecated/ {split($4,a,"/"); if (a[2] ~ /^[0-9]+$/ && a[2]+0 >= 1 && a[2]+0 <= 32) {print a[1]; exit}}')
[ -n "$g_addr" ] && gate_ipv4 "$g_addr" || gate_fail 'no sane global-scope wlan0 IPv4 address'
gate_pass

gate_stage=route
gate_check
g_routes=$($BB timeout -k 1 5 /sbin/ip -4 route show default 2>/dev/null) || gate_fail 'default route query failed'
g_gw=$($BB printf '%s\n' "$g_routes" | $BB awk 'NR == 1 && $1 == "default" && $2 == "via" && $4 == "dev" && $5 == "wlan0" && $0 !~ /nexthop/ {gw=$3} END {if (NR == 1 && gw != "") print gw; else exit 1}') || gate_fail 'expected one default route via wlan0'
gate_ipv4 "$g_gw" && [ "$g_gw" != "$g_addr" ] || gate_fail 'invalid gateway'
gate_pass

gate_stage=gateway
gate_check
$BB timeout -k 1 7 $BB ping -4 -I wlan0 -c 1 -W 4 -w 5 "$g_gw" >/dev/null 2>&1 || gate_fail 'gateway ICMP on wlan0 failed'
gate_pass

gate_stage=internet
gate_check
g_route=$($BB timeout -k 1 5 /sbin/ip -4 route get 1.1.1.1 from "$g_addr" 2>/dev/null) || gate_fail 'internet route lookup failed'
$BB printf '%s\n' "$g_route" | $BB awk 'NR == 1 {for (i=1;i<NF;i++) if ($i == "dev" && $(i+1) == "wlan0") ok++} END {exit(NR != 1 || ok != 1)}' || gate_fail 'internet route is not wlan0'
$BB timeout -k 1 7 $BB ping -4 -I wlan0 -c 1 -W 4 -w 5 1.1.1.1 >/dev/null 2>&1 || gate_fail 'internet ICMP on wlan0 failed'
gate_pass

gate_stage=dns
gate_check
g_dns=$($BB timeout -k 1 3 $BB awk '$1 == "nameserver" && NF == 2 {print $2; exit}' /etc/resolv.conf 2>/dev/null) || gate_fail 'resolver unavailable'
[ -n "$g_dns" ] && gate_ipv4 "$g_dns" || gate_fail 'first resolver is not a sane IPv4 address'
g_route=$($BB timeout -k 1 5 /sbin/ip -4 route get "$g_dns" from "$g_addr" 2>/dev/null) || gate_fail 'DNS route lookup failed'
$BB printf '%s\n' "$g_route" | $BB awk 'NR == 1 {for (i=1;i<NF;i++) if ($i == "dev" && $(i+1) == "wlan0") ok++} END {exit(NR != 1 || ok != 1)}' || gate_fail 'DNS route is not wlan0'
(umask 077; set -C; $BB base64 -d > "$GATE_DIR/dns-probe" <<'GATE_DNS_EOF'
@DNS_BASE64@
GATE_DNS_EOF
) || gate_fail 'cannot extract DNS probe'
$BB chmod 700 "$GATE_DIR/dns-probe" || gate_fail 'cannot protect DNS probe'
[ -f "$GATE_DIR/dns-probe" ] && [ ! -L "$GATE_DIR/dns-probe" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GATE_DIR/dns-probe" 2>/dev/null)" = '0:700:1:597840' ] &&
	[ "$(hash "$GATE_DIR/dns-probe")" = '@DNS_SHA@' ] || gate_fail 'DNS probe pin mismatch'
g_answer=$($BB timeout -k 1 6 "$GATE_DIR/dns-probe" "$g_dns" 2>/dev/null) || gate_fail 'bound DNS query returned no valid answer'
gate_ipv4 "$g_answer" || gate_fail 'invalid DNS answer'
gate_pass

gate_stage=final-health
gate_check
g_final_link=$($BB timeout -k 1 5 /usr/sbin/iw dev wlan0 link 2>/dev/null) || gate_fail 'final association query failed'
[ "${g_final_link%%
*}" = "${g_link%%
*}" ] || gate_fail 'association changed during checks'
g_final_addrs=$($BB timeout -k 1 5 /sbin/ip -o -4 addr show dev wlan0 scope global 2>/dev/null) || gate_fail 'final address query failed'
[ "$g_final_addrs" = "$g_addrs" ] || gate_fail 'address changed during checks'
g_final_routes=$($BB timeout -k 1 5 /sbin/ip -4 route show default 2>/dev/null) || gate_fail 'final route query failed'
[ "$g_final_routes" = "$g_routes" ] || gate_fail 'default route changed during checks'
for g_spec in 'remoteproc2 4080000.remoteproc-mss' 'remoteproc3 9bb00000.remoteproc-wpss'; do
	set -- $g_spec
	[ "$($BB timeout -k 1 2 $BB cat "/sys/class/remoteproc/$1/name" 2>/dev/null)" = "$2" ] &&
	[ "$($BB timeout -k 1 2 $BB cat "/sys/class/remoteproc/$1/state" 2>/dev/null)" = running ] || gate_fail 'remoteproc changed before ACK'
done
for g_service in local networking wpa_supplicant; do
	$BB timeout -k 1 5 /sbin/rc-service "$g_service" status >/dev/null 2>&1 || gate_fail "$g_service stopped before ACK"
done
[ -e /sys/class/net/wlan0 ] && [ -d /sys/class/ieee80211/phy0 ] &&
	[ -d /sys/module/qca_cld3_qca6750 ] || gate_fail 'WLAN driver disappeared before ACK'
g_rmtfs_pid=$($BB cat "$STATE/rmtfs.pid" 2>/dev/null) || gate_fail 'rmtfs pidfile disappeared before ACK'
case "$g_rmtfs_pid" in ''|*[!0-9]*) gate_fail 'invalid final rmtfs pid';; esac
[ "$($BB cat "/proc/$g_rmtfs_pid/comm" 2>/dev/null)" = rmtfs ] &&
	[ "$(hash "/proc/$g_rmtfs_pid/exe")" = d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd ] &&
	$BB grep -q '/dev/uio0' "/proc/$g_rmtfs_pid/maps" || gate_fail 'rmtfs stopped before ACK'
for g_service in pd-mapper tqftpserv; do
	$BB timeout -k 1 3 $BB pidof "$g_service" >/dev/null 2>&1 || gate_fail "$g_service stopped before ACK"
done
gate_snapshot 'cannot recheck radio kmsg'
gate_fatal_check 'fatal radio evidence before ACK'
gate_snapshot_remove
gate_pass

gate_stage=all-checks
gate_check
gate_file all-checks.ok all-checks pass || gate_fail 'cannot record final success'
gate_message 'all checks passed; no ACK yet'
gate_stage=ack-publication
gate_check
[ ! -e "$GUARD/.ack-new" ] && [ ! -L "$GUARD/.ack-new" ] || gate_fail 'another ACK publisher is staging'
[ ! -e "$GUARD/.success-gated-ack-new" ] && [ ! -L "$GUARD/.success-gated-ack-new" ] || gate_fail 'stale ACK staging path'
(umask 077; set -C; $BB printf '%s %s\n' "$gate_nonce" "$boot" > "$GUARD/.success-gated-ack-new") || gate_fail 'cannot stage ACK'
[ -f "$GUARD/.success-gated-ack-new" ] && [ ! -L "$GUARD/.success-gated-ack-new" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/.success-gated-ack-new" 2>/dev/null)" = "0:600:1:$((${#gate_nonce} + ${#boot} + 2))" ] &&
	[ "$($BB cat "$GUARD/.success-gated-ack-new" 2>/dev/null)" = "$gate_nonce $boot" ] || gate_fail 'unsafe staged ACK'
gate_check
[ ! -e "$GUARD/.ack-new" ] && [ ! -L "$GUARD/.ack-new" ] || gate_fail 'another ACK publisher is staging'
gate_phase=publication-uncertain
$BB ln "$GUARD/.success-gated-ack-new" "$GUARD/ack" 2>/dev/null || gate_fail 'atomic no-replace publication failed'
[ -f "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] &&
[ "$($BB stat -c '%d:%i:%u:%a:%h:%s' "$GUARD/ack" 2>/dev/null)" = "$($BB stat -c '%d:%i:%u:%a:%h:%s' "$GUARD/.success-gated-ack-new" 2>/dev/null)" ] &&
[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/ack" 2>/dev/null)" = "0:600:2:$((${#gate_nonce} + ${#boot} + 2))" ] &&
[ "$($BB cat "$GUARD/ack" 2>/dev/null)" = "$gate_nonce $boot" ] || gate_fail 'published ACK is not the staged inode'
gate_identity && [ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
	[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/nonce" 2>/dev/null)" = 0:600:1:65 ] &&
	[ "$($BB cat "$GUARD/nonce" 2>/dev/null)" = "$gate_nonce" ] &&
	[ ! -e "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
	[ ! -e "$GUARD/.ack-new" ] && [ ! -L "$GUARD/.ack-new" ] || gate_fail 'guard or competing publisher changed during publication'
gate_phase=published-awaiting-guard
$BB rm "$GUARD/.success-gated-ack-new" || gate_fail 'cannot make ACK single-link'
if [ -e "$GUARD/ack" ] || [ -L "$GUARD/ack" ]; then
	if ! { [ -f "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/ack" 2>/dev/null)" = "0:600:1:$((${#gate_nonce} + ${#boot} + 2))" ] &&
		[ "$($BB cat "$GUARD/ack" 2>/dev/null)" = "$gate_nonce $boot" ]; }; then
		if [ -e "$GUARD/ack" ] || [ -L "$GUARD/ack" ]; then
			gate_fail 'published ACK changed without confirmed consumption'
		fi
	fi
fi
gate_file published.ok ack-publication pass || gate_fail 'cannot record ACK publication'
gate_message 'one ACK published; guard acceptance pending'

gate_stage=guard-acceptance
g_wait=0
while [ "$g_wait" -lt 15 ]; do
	gate_identity || gate_fail 'boot or root changed while awaiting guard'
	if [ -f "$GUARD/accepted" ] && [ ! -L "$GUARD/accepted" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$GUARD/accepted" 2>/dev/null)" = "0:600:1:$((${#boot} + 1))" ] &&
		[ "$($BB cat "$GUARD/accepted" 2>/dev/null)" = "$boot" ] &&
		[ ! -e "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
		[ ! -e "$GUARD/ack" ] && [ ! -L "$GUARD/ack" ]; then
		gate_phase=guard-accepted
		gate_file accepted.ok guard-acceptance pass || gate_fail 'guard accepted but evidence write failed'
		gate_message 'guard accepted and consumed nonce and ACK'
		gate_complete=1
		break
	fi
	$BB sleep 1
	g_wait=$((g_wait + 1))
done
[ "$gate_complete" = 1 ] || gate_fail 'acceptance not confirmed; ACK may still be consumed'
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_dns_probe(probe):
    if not isinstance(probe, bytes) or len(probe) != DNS_PROBE_SIZE or sha(probe) != DNS_PROBE_SHA:
        raise SystemExit('DNS probe does not match the pinned size and digest')
    if (probe[:7] != b'\x7fELF\x02\x01\x01' or
            struct.unpack_from('<HHI', probe, 16) != (2, 183, 1)):
        raise SystemExit('DNS probe is not an AArch64 executable')
    phoff = struct.unpack_from('<Q', probe, 32)[0]
    entsize, count = struct.unpack_from('<HH', probe, 54)
    if entsize != 56 or not 1 <= count <= 128 or phoff + entsize * count > len(probe):
        raise SystemExit('invalid DNS probe program headers')
    types = [struct.unpack_from('<I', probe, phoff + i * entsize)[0] for i in range(count)]
    if 1 not in types or 2 in types or 3 in types:
        raise SystemExit('DNS probe is not statically linked')


def build_dns_probe():
    binaries = []
    with tempfile.TemporaryDirectory(prefix='omnipha-dns-a-') as a, \
            tempfile.TemporaryDirectory(prefix='omnipha-dns-b-long-') as b:
        for directory in (a, b):
            source = pathlib.Path(directory) / 'probe.c'
            binary = pathlib.Path(directory) / 'probe'
            source.write_text(DNS_C, encoding='ascii')
            subprocess.run(
                ['aarch64-linux-gnu-gcc', '-static', '-Os', '-s', '-fno-ident',
                 '-Wl,--build-id=none', '-o', str(binary), str(source)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            with binary.open('rb') as stream:
                probe = stream.read(DNS_PROBE_SIZE + 1)
            validate_dns_probe(probe)
            binaries.append(probe)
    if binaries[0] != binaries[1]:
        raise SystemExit('DNS probe builds differ')
    return binaries[0]


def derive(text, radio, probe):
    if sha(text.encode('utf-8')) != FRESH_POST_SHA:
        raise SystemExit('fresh post is not the exact #291 candidate')
    if sha(radio) != FRESH_RADIO_SHA:
        raise SystemExit('radio is not the exact #291 candidate')
    if f'RADIO_SHA={FRESH_RADIO_SHA}\n' not in text:
        raise SystemExit('fresh post radio pin differs')
    validate_dns_probe(probe)
    if text.count(PANEL_OLD) != 1:
        raise SystemExit('fresh post panel block not found exactly once')
    prefix = text.replace(PANEL_OLD, PANEL_NEW, 1)
    encoded = '\n'.join(textwrap.wrap(base64.b64encode(probe).decode('ascii'), 96))
    gate = GATE.replace('@DNS_BASE64@', encoded).replace('@DNS_SHA@', sha(probe))
    post = prefix + gate
    post_sha = sha(post.encode('utf-8'))
    hook = f'''#!/bin/busybox sh
BB=/bin/busybox
for spec in "{POST_PATH} {post_sha}" "{RADIO_PATH} {FRESH_RADIO_SHA}"; do
\tset -- $spec
\t[ -f "$1" ] && [ ! -L "$1" ] &&
\t\t[ "$($BB stat -c '%u:%a' "$1")" = 0:700 ] &&
\t\t[ "$($BB sha256sum "$1" | $BB cut -d ' ' -f 1)" = "$2" ] || {{
\t\t$BB printf 'pmos-self-post-fresh: pinned persistent script missing or changed\\n' >/dev/kmsg 2>/dev/null || true
\t\texit 1
\t}}
done
( /bin/busybox setsid /bin/busybox sh -c '
	/bin/busybox sh "$1" >/dev/null 2>&1
	result=$?
	[ "$result" -eq 0 ] || /bin/busybox printf "pmos-self-post-fresh: process exited rc=%s\\n" "$result" 2>/dev/null >/dev/kmsg || true
	exit "$result"
' self-post {POST_PATH} >/dev/null 2>&1 & )
'''
    return post, hook


def open_output_parent(path, workspace):
    if path.name in ('', '.', '..'):
        raise SystemExit('output must name a new file')
    parent = path.parent.resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(parent, flags)
    try:
        actual = pathlib.Path(os.readlink(f'/proc/self/fd/{fd}'))
        if actual != parent or actual == workspace or workspace in actual.parents:
            raise SystemExit('outputs must be outside the repository')
        try:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return fd, path.name
        raise SystemExit('output already exists: ' + str(path))
    except BaseException:
        os.close(fd)
        raise


def write_outputs(output, hook_output, workspace, post, hook):
    parents = []
    created = []
    try:
        parents.append(open_output_parent(output, workspace))
        parents.append(open_output_parent(hook_output, workspace))
        first = os.fstat(parents[0][0])
        second = os.fstat(parents[1][0])
        if ((first.st_dev, first.st_ino, parents[0][1]) ==
                (second.st_dev, second.st_ino, parents[1][1])):
            raise SystemExit('outputs must be distinct paths')
        for (parent, name), data in zip(parents, (post, hook)):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
            fd = os.open(name, flags, 0o600, dir_fd=parent)
            info = os.fstat(fd)
            created.append((parent, name, info.st_dev, info.st_ino))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data.encode('utf-8'))
    except BaseException:
        for parent, name, dev, ino in created:
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (info.st_dev, info.st_ino) == (dev, ino):
                    os.unlink(name, dir_fd=parent)
            except OSError:
                pass
        raise
    finally:
        for parent, _ in parents:
            os.close(parent)


def main(argv):
    if len(argv) != 5:
        raise SystemExit(__doc__)
    source, radio, output, hook_output = map(pathlib.Path, argv[1:])
    workspace = pathlib.Path(__file__).resolve().parent.parent
    checked = []
    try:
        checked.append(open_output_parent(output, workspace))
        checked.append(open_output_parent(hook_output, workspace))
        first, second = (os.fstat(fd) for fd, _ in checked)
        if ((first.st_dev, first.st_ino, checked[0][1]) ==
                (second.st_dev, second.st_ino, checked[1][1])):
            raise SystemExit('outputs must be distinct paths')
    finally:
        for fd, _ in checked:
            os.close(fd)
    source_stat, radio_stat = source.stat(), radio.stat()
    if (not stat.S_ISREG(source_stat.st_mode) or not stat.S_ISREG(radio_stat.st_mode) or
            (source_stat.st_dev, source_stat.st_ino) == (radio_stat.st_dev, radio_stat.st_ino)):
        raise SystemExit('inputs must be distinct regular files')
    text, radio_bytes = source.read_text(encoding='utf-8'), radio.read_bytes()
    if sha(text.encode('utf-8')) != FRESH_POST_SHA or sha(radio_bytes) != FRESH_RADIO_SHA:
        raise SystemExit('inputs are not the exact #291 candidates')
    try:
        probe = build_dns_probe()
    except FileNotFoundError:
        raise SystemExit('aarch64-linux-gnu-gcc is required')
    except subprocess.CalledProcessError as exc:
        raise SystemExit('DNS probe compilation failed: ' + exc.stderr.decode(errors='replace'))
    post, hook = derive(text, radio_bytes, probe)
    write_outputs(output, hook_output, workspace, post, hook)


if __name__ == '__main__':
    main(sys.argv)
