#!/bin/busybox sh
BB=/bin/busybox
ROOT=/run/pmos
GUARD=/run/pmos-pid1-guard.sh
GUARD_SHA256=2a92fbcfe029ec3be1af8b73d4cd8d0ac317ecd267a9dc9ba9637932207d5da3
fail() { log "pid1 transition refused: $*"; return 1; }
[ "$$" = 1 ] || { fail 'not PID 1'; return 1; }
[ -e /run/keep ] && [ ! -L /run/keep ] || { fail 'diagnostic hold missing'; return 1; }
[ "$($BB stat -c '%u:%a' /run)" = 0:755 ] || { fail 'diagnostic /run changed'; return 1; }
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] &&
	[ "$($BB stat -c '%u:%a' "$ROOT")" = 0:700 ] || { fail 'root ownership or mode'; return 1; }
CONTRACT=${PMOS_ROOT_CONTRACT:-/run/pmos-root-contract.sh}
[ -f "$CONTRACT" ] || CONTRACT="${SOURCE:-/run}/pmos-root-contract.sh"
[ -f "$CONTRACT" ] && [ ! -L "$CONTRACT" ] && . "$CONTRACT" || { fail 'root contract unavailable'; return 1; }
root_contract_stage_root "$ROOT" || { fail 'root or child mount invalid'; return 1; }
$BB awk -v root="$ROOT" '
	$2 == root {n++; if ($1 == "tmpfs" && ($3 != "tmpfs" || $4 !~ /(^|,)size=262144k(,|$)/)) bad++; if ($1 != "tmpfs" && $3 != "ext4") bad++}
	$2 == root "/proc" {p++; if ($3 != "proc") bad++}
	$2 == root "/sys" {s++; if ($3 != "sysfs") bad++}
	$2 == root "/dev" {d++; if ($3 != "tmpfs") bad++}
	$2 == root "/dev/pts" {t++; if ($3 != "devpts") bad++}
	$2 == root "/run" {u++; if ($1 != "tmpfs" || $3 != "tmpfs" || $4 !~ /(^|,)size=8192k(,|$)/ || $4 !~ /(^|,)mode=700(,|$)/) bad++}
	$2 == root "/sys/kernel/config" {c++; if ($3 != "configfs") bad++}
	$2 == root || index($2, root "/") == 1 {
		if ($2 != root && $2 != root "/proc" && $2 != root "/sys" &&
		    $2 != root "/dev" && $2 != root "/dev/pts" && $2 != root "/run" &&
		    $2 != root "/sys/kernel/config") bad++
	}
	END {exit(bad || n != 1 || p != 1 || s != 1 || d != 1 || t != 1 || u != 1 || c > 1)}
' /proc/mounts || { fail 'root or child mount invalid'; return 1; }
$BB awk -v root="$ROOT" '
	$5 == "/" {old = $3}
	$5 == "/dev" {dev = $3}
	$5 == "/run" {oldrun = $3}
	$5 == root {n++; parent = $1; guest = $3; if ($4 != "/" || ($0 !~ / - tmpfs tmpfs / && $0 !~ / - ext4 /)) bad++}
	$5 == root "/dev" {dn++; gd = $3; if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++}
	$5 == root "/dev/pts" {tn++; pts = $3; if ($4 != "/" || $0 !~ / - devpts devpts /) bad++}
	$5 == root "/run" {rn++; runparent = $2; gr = $3; if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++}
	END {exit(bad || n != 1 || dn != 1 || tn != 1 || rn != 1 || !old || guest == old || gd == dev || gd == guest || pts == gd || runparent != parent || gr == guest || gr == old || (oldrun && gr == oldrun))}
' /proc/self/mountinfo || { fail 'root or device mount is shared'; return 1; }
for path in proc sys dev dev/pts sys/kernel/config run sbin; do
	[ ! -L "$ROOT/$path" ] || { fail "symlinked $path"; return 1; }
done
[ "$($BB readlink "$ROOT/sbin/init")" = ../bin/busybox ] &&
	[ -x "$ROOT/bin/busybox" ] && [ -x "$ROOT/sbin/openrc" ] &&
	[ -f "$ROOT/etc/inittab" ] && [ ! -L "$ROOT/etc/inittab" ] &&
	[ "$($BB cat "$ROOT/etc/inittab")" = "$($BB printf '::sysinit:/sbin/openrc sysinit\n::sysinit:/sbin/openrc boot\n::wait:/sbin/openrc default')" ] &&
	[ "$($BB stat -c '%u:%a' "$ROOT/run")" = 0:700 ] &&
	[ -f "$ROOT/run/keep" ] && [ ! -L "$ROOT/run/keep" ] &&
	[ "$($BB stat -c '%u:%a' "$ROOT/run/keep")" = 0:600 ] &&
	[ "$($BB stat -c '%t:%T' "$ROOT/dev/null")" = 1:3 ] &&
	[ "$($BB stat -c '%t:%T' "$ROOT/dev/console")" = 5:1 ] &&
	[ "$($BB stat -c '%t:%T' "$ROOT/dev/urandom")" = 1:9 ] &&
	[ "$($BB readlink "$ROOT/dev/ptmx")" = pts/ptmx ] &&
	$BB grep -q 'ID="postmarketos"' "$ROOT/usr/lib/os-release" || { fail 'init, root or device inputs missing'; return 1; }
[ -f "$ROOT/run/dropbear-session.pid" ] && [ ! -L "$ROOT/run/dropbear-session.pid" ] &&
	[ -f "$ROOT/etc/dropbear/session_host_key" ] && [ ! -L "$ROOT/etc/dropbear/session_host_key" ] &&
	[ "$($BB stat -c '%u:%a' "$ROOT/etc/dropbear/session_host_key")" = 0:600 ] &&
	$BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {guest++} $2 == "022A10AC:0016" && $4 == "0A" {diagnostic++} END {exit(guest != 1 || diagnostic != 1)}' /proc/net/tcp || { fail 'either SSH service absent'; return 1; }
pid=$($BB cat "$ROOT/run/dropbear-session.pid")
case "$pid" in ''|*[!0-9]*) fail 'bad second service pid'; return 1;; esac
[ -d "/proc/$pid" ] &&
	[ "$($BB readlink "/proc/$pid/root" 2>/dev/null)" = "$ROOT" ] &&
	[ "$($BB stat -Lc '%d:%i' "/proc/$pid/root")" = "$($BB stat -c '%d:%i' "$ROOT")" ] &&
	$BB tr '\000' ' ' < "/proc/$pid/cmdline" | $BB grep -q 'dropbear -s -g -j -k -E -r /etc/dropbear/session_host_key -p 172.16.42.2:2222 -P /run/dropbear-session.pid ' || { fail 'second service changed'; return 1; }
[ -f "$GUARD" ] && [ ! -L "$GUARD" ] &&
	[ "$($BB stat -c '%u:%a:%h' "$GUARD")" = 0:700:1 ] || { fail 'guard input missing'; return 1; }
[ "$($BB sha256sum "$GUARD" | $BB cut -d ' ' -f 1)" = "$GUARD_SHA256" ] || { fail 'guard digest mismatch'; return 1; }
$BB awk -v root="$ROOT" '
	function isolated() {if ($7 != "-" || NF != 10) bad++}
	function under_run(parent, steps) {
		while (parent != old_mount) {
			if (++steps > oldrun || !(parent in oldrun_parents)) return 0
			parent = oldrun_parents[parent]
		}
		return steps > 0
	}
	$5 == "/" {old++; old_mount = $1; old_dev = $3; isolated()}
	$5 == "/run" {oldrun++; oldrun_parents[$1] = $2; oldrun_devs[$3] = 1; isolated()}
	$5 == "/dev" {hostdev_devs[$3] = 1}
	$5 == "/dev/pts" {hostpts_devs[$3] = 1}
	$5 == "/proc" {hostproc_mounts[$1] = 1}
	$5 == "/sys" {hostsys_mounts[$1] = 1}
	$5 == "/sys/kernel/config" {hostconfig++; hostconfig_mounts[$1] = 1}
	$5 == root {
		base++; base_mount = $1; base_parent = $2; base_dev = $3
		if ($4 != "/" || ($0 !~ / - tmpfs tmpfs / && $0 !~ / - ext4 /)) bad++
		isolated()
	}
	$5 == root "/run" {
		run++; run_mount = $1; run_parent = $2; run_dev = $3
		if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++
		isolated()
	}
	$5 == root "/dev" {
		dev++; dev_mount = $1; dev_parent = $2; dev_dev = $3
		if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++
		isolated()
	}
	$5 == root "/proc" {
		proc++; proc_mount = $1; proc_parent = $2
		if ($4 != "/" || $0 !~ / - proc proc /) bad++
		isolated()
	}
	$5 == root "/sys" {
		sys++; sys_mount = $1; sys_parent = $2
		if ($4 != "/" || $0 !~ / - sysfs sysfs /) bad++
		isolated()
	}
	$5 == root "/sys/kernel/config" {
		config++; config_mount = $1; config_parent = $2
		if ($4 != "/" || $0 !~ / - configfs configfs /) bad++
		isolated()
	}
	$5 == root "/dev/pts" {
		pts++; pts_mount = $1; pts_parent = $2; pts_dev = $3
		if ($4 != "/" || $0 !~ / - devpts devpts /) bad++
		isolated()
	}
	{
		ids[NR] = $3; mounts[NR] = $1; paths[NR] = $5
		if ($5 == root || index($5, root "/") == 1)
			if ($5 != root && $5 != root "/run" && $5 != root "/dev" &&
			    $5 != root "/proc" && $5 != root "/sys" &&
			    $5 != root "/sys/kernel/config" && $5 != root "/dev/pts") bad++
	}
	END {
		for (i = 1; i <= NR; i++)
			if (ids[i] == base_dev && paths[i] != root ||
			    ids[i] == run_dev && paths[i] != root "/run" ||
			    ids[i] == dev_dev && paths[i] != root "/dev" ||
			    ids[i] == pts_dev && paths[i] != root "/dev/pts" ||
			    mounts[i] == proc_mount && paths[i] != root "/proc" ||
			    mounts[i] == sys_mount && paths[i] != root "/sys" ||
			    config && mounts[i] == config_mount && paths[i] != root "/sys/kernel/config") bad++
			exit(bad || old != 1 || hostconfig > 1 ||
			base != 1 || run != 1 || dev != 1 || proc != 1 || sys != 1 ||
			pts != 1 || config != hostconfig ||
			!(oldrun ? under_run(base_parent) : base_parent == old_mount) ||
			run_parent != base_mount || dev_parent != base_mount ||
			proc_parent != base_mount || sys_parent != base_mount ||
			pts_parent != dev_mount || (config && config_parent != sys_mount) ||
			base_dev == old_dev || run_dev == old_dev ||
			dev_dev == old_dev || pts_dev == old_dev ||
			(base_dev in oldrun_devs) || (run_dev in oldrun_devs) ||
			(dev_dev in oldrun_devs) || (pts_dev in oldrun_devs) ||
			base_dev == run_dev || base_dev == dev_dev || run_dev == dev_dev ||
			pts_dev == base_dev || pts_dev == run_dev || pts_dev == dev_dev ||
			(dev_dev in hostdev_devs) || (pts_dev in hostpts_devs) ||
			(proc_mount in hostproc_mounts) ||
			(sys_mount in hostsys_mounts) ||
			(config && (config_mount in hostconfig_mounts)))
	}
' /proc/self/mountinfo || { fail 'mount propagation or ancestry invalid'; return 1; }
if ! $BB sh "$GUARD" arm "$ROOT" 160; then
	if [ -e "$ROOT/run/pid1-guard/armed" ] || [ -L "$ROOT/run/pid1-guard/armed" ]; then
		log 'pid1 transition guard arm failed after arming; independent guard remains armed'
		while :; do $BB sleep 60; done
	fi
	fail 'independent recovery guard not armed'
	return 1
fi
[ -f "$ROOT/run/pid1-guard/armed" ] && [ ! -L "$ROOT/run/pid1-guard/armed" ] &&
	[ "$($BB cat "$ROOT/run/pid1-guard/armed")" = "$($BB cat /proc/sys/kernel/random/boot_id)" ] &&
	[ ! -e "$ROOT/run/pid1-guard/nonce" ] && [ ! -L "$ROOT/run/pid1-guard/nonce" ] || {
	log 'pid1 transition guard not awaiting transition; independent guard remains armed'
	while :; do $BB sleep 60; done
}
log 'pid1 transition guard armed; exec switch_root to postmarketOS init'
exec /bin/busybox switch_root "$ROOT" /sbin/init
