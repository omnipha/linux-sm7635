#!/bin/busybox sh
set -eu

BB=/bin/busybox
PMOS_ROOT=/run/pmos
PMOS_TARBALL=/run/pmos-session.tar.gz
LOG=/run/pmos-teardown.log

log() { $BB printf 'pmos-teardown: %s\n' "$*" | $BB tee -a "$LOG" >&2; }
die() { log "FAIL: $*; leaving guest rootfs intact"; exit 1; }

check_mounts() {
	for path in "$PMOS_ROOT" "$PMOS_ROOT/run" "$PMOS_ROOT/dev" "$PMOS_ROOT/dev/pts" "$PMOS_ROOT/sys" "$PMOS_ROOT/sys/kernel" "$PMOS_ROOT/sys/kernel/config" "$PMOS_ROOT/proc"; do
		[ ! -L "$path" ] || die "guest mount path is a symlink"
	done
	CONTRACT=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
	[ -f "$CONTRACT" ] || CONTRACT="${SOURCE:-/run}/pmos-root-contract.sh"
	[ -f "$CONTRACT" ] || CONTRACT="$(dirname -- "$0")/pmos-root-contract.sh"
	[ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] && . "$CONTRACT" || die "root contract unavailable"
	$BB awk -v root="$PMOS_ROOT" '
		$2 == root || index($2, root "/") == 1 {
			if ($2 == root && $1 == "tmpfs" && $3 == "tmpfs" &&
			    $4 ~ /(^|,)size=262144k(,|$)/ && $4 ~ /(^|,)mode=700(,|$)/) base++
			else if ($2 == root && $3 == "ext4" && $1 ~ /^\/dev\/block\//) {base++; ext4++}
			else if ($2 == root "/run" && $1 == "tmpfs" && $3 == "tmpfs" &&
			    $4 ~ /(^|,)size=8192k(,|$)/ && $4 ~ /(^|,)mode=700(,|$)/) run++
			else if ($2 == root "/proc" && $3 == "proc") proc++
			else if ($2 == root "/sys" && $3 == "sysfs") sys++
			else if ($2 == root "/sys/kernel/config" && $3 == "configfs") config++
			else if ($2 == root "/dev" && $3 == "tmpfs") dev++
			else if ($2 == root "/dev/pts" && $3 == "devpts") pts++
			else bad++
		}
		END {exit(bad || base > 1 || run > 1 || proc > 1 || sys > 1 || config > 1 || dev > 1 || pts > 1 ||
			((run || proc || sys || config || dev || pts) && !base) ||
			((proc || sys || config || dev || pts) && !run) || (config && !sys) || (pts && !dev))}
	' /proc/mounts || die "unexpected, duplicated or incorrectly sized guest mount"
	if $BB awk -v root="$PMOS_ROOT" '$2 == root && $3 == "ext4" {n++} END {exit(n == 0)}' /proc/mounts; then
		root_contract_pinned_userdata "$PMOS_ROOT" || die "guest mount identity or source invalid"
	fi
	$BB awk -v root="$PMOS_ROOT" '
		$5 == "/" {host_root = $3}
		$5 == "/run" {host_run = $3}
		$5 == "/sys/kernel/config" {host_config = $1}
		$5 == "/dev" {host_dev = $3}
		$5 == "/dev/pts" {host_pts = $3}
		$5 == "/proc" {host_proc = $1}
		$5 == "/sys" {host_sys = $1}
		$5 == root {
			base++; root_mount = $1; root_id = $3
			if ($4 != "/" || ($0 !~ / - tmpfs tmpfs / &&
			    $0 !~ / - ext4 \/dev\/block\//)) bad++
			for (i = 7; i <= NF && $i != "-"; i++)
				if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
		}
		$5 == root "/run" {
			run++; run_parent = $2; run_id = $3
			if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++
			for (i = 7; i <= NF && $i != "-"; i++)
				if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
		}
		$5 == root "/proc" {proc++; proc_mount = $1; if ($4 != "/" || $0 !~ / - proc proc /) bad++}
		$5 == root "/sys" {sys++; sys_mount = $1; if ($4 != "/" || $0 !~ / - sysfs sysfs /) bad++}
		$5 == root "/sys/kernel/config" {config++; config_mount = $1; if ($4 != "/" || $0 !~ / - configfs configfs /) bad++}
		$5 == root "/dev" {dev++; dev_id = $3; if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++}
		$5 == root "/dev/pts" {pts++; pts_id = $3; if ($4 != "/" || $0 !~ / - devpts devpts /) bad++}
		{ids[NR] = $3; paths[NR] = $5; mounts[NR] = $1}
		END {
			for (i = 1; i <= NR; i++)
				if (base && ids[i] == root_id && paths[i] != root ||
				    run && ids[i] == run_id && paths[i] != root "/run" ||
				    dev && ids[i] == dev_id && paths[i] != root "/dev" ||
				    pts && ids[i] == pts_id && paths[i] != root "/dev/pts" ||
				    proc && mounts[i] == proc_mount && paths[i] != root "/proc" ||
				    sys && mounts[i] == sys_mount && paths[i] != root "/sys" ||
				    config && mounts[i] == config_mount && paths[i] != root "/sys/kernel/config") bad++
			exit(bad || base > 1 || run > 1 || proc > 1 || sys > 1 || config > 1 || dev > 1 || pts > 1 ||
				(base && (!host_root || root_id == host_root || (host_run && root_id == host_run))) ||
				(run && (!base || run_parent != root_mount || run_id == root_id ||
					run_id == host_root || (host_run && run_id == host_run))) ||
				(proc && host_proc && proc_mount == host_proc) ||
				(sys && host_sys && sys_mount == host_sys) ||
				(config && host_config && config_mount == host_config) ||
				(dev && ((host_dev && dev_id == host_dev) || dev_id == root_id)) ||
				(pts && host_pts && pts_id == host_pts))
		}
	' /proc/self/mountinfo || die "guest mount identity or source invalid"
}

check_mounts
if [ -d "$PMOS_ROOT" ]; then
	[ "$($BB stat -c '%u:%a' "$PMOS_ROOT")" = 0:700 ] || die "guest root is not private"
	$BB awk -v root="$PMOS_ROOT" '$2 == root {n++} END {exit(n != 1)}' /proc/mounts || die "unmounted guest root"
	if $BB awk -v path="$PMOS_ROOT/run" '$2 == path {n++} END {exit(n != 1)}' /proc/mounts; then
		[ "$($BB stat -c '%u:%a' "$PMOS_ROOT/run")" = 0:700 ] || die "guest run is not root-only"
		if [ -f "$PMOS_ROOT/run/dropbear-session.pid" ]; then
			pid=$($BB cat "$PMOS_ROOT/run/dropbear-session.pid")
			case "$pid" in ''|*[!0-9]*) die "invalid second SSH pidfile";; esac
			if [ -d "/proc/$pid" ]; then
				[ "$($BB readlink "/proc/$pid/root" 2>/dev/null || true)" = "$PMOS_ROOT" ] &&
					$BB tr '\0' ' ' < "/proc/$pid/cmdline" | $BB grep -q 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' ||
					die "pidfile does not identify the guest SSH"
				$BB kill "$pid" || die "cannot stop second SSH"
				log "stopped second SSH (pid $pid)"
			fi
		fi

		for d in dev/pts dev sys/kernel/config sys proc; do
			check_mounts
			if $BB awk -v path="$PMOS_ROOT/$d" '$2 == path {found++} END {exit(found != 1)}' /proc/mounts; then
				$BB umount "$PMOS_ROOT/$d" || die "unmount $d"
				log "unmounted $d"
			fi
		done
		check_mounts
		if $BB awk -v path="$PMOS_ROOT/run" '$2 == path {found++} END {exit(found != 1)}' /proc/mounts; then
			$BB umount "$PMOS_ROOT/run" || die "unmount run"
			log "unmounted run"
		fi
	else
		$BB awk -v root="$PMOS_ROOT" '
			$2 == root {base++}
			index($2, root "/") == 1 {child++}
			END {exit(base != 1 || child)}
		' /proc/mounts || die "guest run absent with child mounts"
		$BB awk -v root="$PMOS_ROOT" '
			$5 == root {base++}
			index($5, root "/") == 1 {child++}
			END {exit(base != 1 || child)}
		' /proc/self/mountinfo || die "guest run absent with child mounts"
		[ ! -e "$PMOS_ROOT/run/dropbear-session.pid" ] && [ ! -L "$PMOS_ROOT/run/dropbear-session.pid" ] ||
			die "guest run absent with second SSH pidfile"
		$BB awk '$2 ~ /:08AE$/ && $4 == "0A" {live++} END {exit(live != 0)}' /proc/net/tcp ||
			die "second SSH listener still live"
		if [ -f /proc/net/tcp6 ]; then
			$BB awk '$2 ~ /:08AE$/ && $4 == "0A" {live++} END {exit(live != 0)}' /proc/net/tcp6 ||
				die "second SSH listener still live"
		fi
		root_device=$($BB stat -c %d "$PMOS_ROOT") || die "guest root identity unavailable"
		for process_root in /proc/[0-9]*/root; do
			[ -d "${process_root%/root}" ] || continue
			process_device=$($BB stat -Lc %d "$process_root" 2>/dev/null) ||
				{ [ ! -d "${process_root%/root}" ] && continue; die "cannot inspect process root"; }
			[ "$process_device" != "$root_device" ] || die "guest process still live"
		done
	fi
	check_mounts
	$BB umount "$PMOS_ROOT" || die "unmount guest root"
	log "unmounted guest root"
	$BB rmdir "$PMOS_ROOT" || die "remove empty guest mountpoint"
	log "removed $PMOS_ROOT"
	[ ! -L "$PMOS_TARBALL" ] || die "staged tarball is a symlink"
	if [ -f "$PMOS_TARBALL" ]; then
		$BB rm -f "$PMOS_TARBALL" || die "remove staged tarball"
		log "removed staged tarball"
	fi
fi

$BB grep -q ':0016 ' /proc/net/tcp && log "diagnostic :22 listener still present" ||
	log "WARNING: diagnostic :22 listener not seen"
$BB readlink /proc/1/exe 2>/dev/null | $BB grep -q busybox && log "PID 1 unchanged" || true
[ -e /run/keep ] && log "/run/keep present" || log "note: /run/keep absent"
log "teardown complete; guest is clean for coordinator session close"
