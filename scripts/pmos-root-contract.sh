#!/bin/busybox sh
# Shared root-type contract. Sourced, not executed.
# The staged root is either the measured private 256m tmpfs or exactly one
# non-symlink ext4 mount of the single PARTNAME=userdata block. /run, /dev
# and /dev/pts stay their own tmpfs/devpts mounts in both cases. The ext4
# root is read-write only after its identity is pinned; nothing here mounts,
# formats or writes a partition.

BB=${BB:-/bin/busybox}
ROOT_CONTRACT_MIN_BYTES=33554432
ROOT_CONTRACT_MAX_BYTES=241421725696

root_contract_die() { return 1; }

root_contract_pinned_userdata() {
	rc_path=$1
	rc_mounts=${2:-/proc/mounts}
	rc_info=${3:-/proc/self/mountinfo}
	[ -n "$rc_path" ] || return 1
	case "$rc_path" in /*) :;; *) return 1;; esac
	case "$rc_path" in /) :;; */) return 1;; esac
	[ -d "$rc_path" ] && [ ! -L "$rc_path" ] &&
		[ "$($BB stat -c %u "$rc_path" 2>/dev/null)" = 0 ] || return 1
	rc_part=
	rc_count=0
	for rc_uevent in /sys/class/block/*/uevent; do
		[ -r "$rc_uevent" ] || continue
		[ "$($BB sed -n 's/^PARTNAME=//p' "$rc_uevent" 2>/dev/null)" = userdata ] || continue
		rc_dir=${rc_uevent%/uevent}
		rc_part=${rc_dir##*/}
		rc_count=$((rc_count + 1))
	done
	[ "$rc_count" = 1 ] && [ -n "$rc_part" ] || return 1
	case "$rc_part" in *[!A-Za-z0-9_-]*) return 1;; esac
	rc_devnum=$($BB cat "/sys/class/block/$rc_part/dev" 2>/dev/null) || return 1
	case "$rc_devnum" in [0-9]*:[0-9]*) :;; *) return 1;; esac
	rc_major=${rc_devnum%%:*}
	rc_minor=${rc_devnum##*:}
	case "$rc_major" in ''|*[!0-9]*|0) return 1;; esac
	case "$rc_minor" in ''|*[!0-9]*) return 1;; esac
	rc_node="/dev/block/$rc_part"
	[ -b "$rc_node" ] && [ ! -L "$rc_node" ] || return 1
	[ "$($BB stat -c '%t:%T' "$rc_node")" = "$($BB printf '%x:%x' "$rc_major" "$rc_minor")" ] || return 1
	rc_size=$($BB blockdev --getsize64 "$rc_node" 2>/dev/null) || return 1
	case "$rc_size" in ''|*[!0-9]*) return 1;; esac
	[ "$rc_size" -ge "$ROOT_CONTRACT_MIN_BYTES" ] && [ "$rc_size" -le "$ROOT_CONTRACT_MAX_BYTES" ] || return 1
	rc_row=$($BB awk -v path="$rc_path" -v node="$rc_node" '
		$1 == node && $2 == path && $3 == "ext4" {n++; opts = $4}
		END {if (n == 1) print opts; else exit 1}
	' "$rc_mounts") || return 1
	case ",$rc_row," in
		*,ro,*)
			case ",$rc_row," in
				*,noload,*|*,norecovery,*) :;;
				*) return 1;;
			esac
			;;
		*,rw,*) :;;
		*) return 1;;
	esac
	$BB awk -v path="$rc_path" -v node="$rc_node" -v devnum="$rc_devnum" '
		{
			sep = 0
			for (i = 7; i <= NF; i++) if ($i == "-") { sep = i; break }
			src = sep ? $(sep + 2) : ""
			fstype = sep ? $(sep + 1) : ""
			sources[NR] = src
			devs[NR] = $3
			paths[NR] = $5
		}
		$5 == path {
			n++; source = src; dev = $3
			if (!sep || $4 != "/" || fstype != "ext4") bad++
			for (i = 7; i < sep; i++)
				if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
		}
		END {
			for (i = 1; i <= NR; i++)
				if ((sources[i] == node || devs[i] == devnum) && paths[i] != path) bad++
			exit(n != 1 || bad || source != node || dev != devnum)
		}
	' "$rc_info" || return 1
	$BB awk -v node="$rc_node" -v path="$rc_path" '
		$1 == node {n++; if ($2 != path) bad++}
		END {exit(n != 1 || bad)}
	' "$rc_mounts" || return 1
	ROOT_CONTRACT_NODE=$rc_node
	ROOT_CONTRACT_SIZE=$rc_size
	ROOT_CONTRACT_OPTS=$rc_row
	return 0
}

root_contract_stage_root() {
	rc_path=$1
	rc_mounts=${2:-/proc/mounts}
	rc_info=${3:-/proc/self/mountinfo}
	$BB awk -v path="$rc_path" '
		$2 == path {
			n++
			if ($1 == "tmpfs" && $3 == "tmpfs" && $4 ~ /(^|,)size=262144k(,|$)/ && $4 ~ /(^|,)mode=700(,|$)/) kind = "tmpfs"
			else kind = "other"
		}
		END {if (n == 1 && kind == "tmpfs") exit 0; exit 1}
	' "$rc_mounts" && {
		$BB awk -v path="$rc_path" '
			$5 == "/" {host = $3}
			$5 == "/run" {outer[$3] = 1}
			$5 == path {
				n++; id = $3
				if ($4 != "/" || $0 !~ / - tmpfs tmpfs /) bad++
				for (i = 7; i <= NF && $i != "-"; i++)
					if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
			}
			{ids[NR] = $3; paths[NR] = $5}
			END {
				for (i = 1; i <= NR; i++) if (ids[i] == id && paths[i] != path) bad++
				exit(n != 1 || bad || !host || id == host || (id in outer))
			}
		' "$rc_info" || return 1
		ROOT_CONTRACT_KIND=tmpfs
		ROOT_CONTRACT_NODE=
		return 0
	}
	root_contract_pinned_userdata "$rc_path" "$rc_mounts" "$rc_info" || return 1
	ROOT_CONTRACT_KIND=ext4
	return 0
}

root_contract_switched_root() {
	rc_mounts=${1:-/proc/1/mounts}
	rc_info=${2:-/proc/self/mountinfo}
	rc_row=$($BB awk '
		$2 == "/" {n++; kind = $3; opts = $4; source = $1}
		END {if (n == 1) print kind " " source " " opts; else exit 1}
	' "$rc_mounts") || return 1
	set -- $rc_row
	rc_kind=$1
	rc_source=$2
	shift 2
	rc_opts=$*
	case "$rc_kind" in
		tmpfs)
			[ "$rc_source" = tmpfs ] || return 1
			ROOT_CONTRACT_KIND=tmpfs
			ROOT_CONTRACT_NODE=
			return 0
			;;
		ext4) :;;
		*) return 1;;
	esac
	case ",$rc_opts," in
		*,ro,*)
			case ",$rc_opts," in
				*,noload,*|*,norecovery,*) :;;
				*) return 1;;
			esac
			;;
		*,rw,*) :;;
		*) return 1;;
	esac
	case "$rc_source" in /dev/block/*) :;; *) return 1;; esac
	rc_part=${rc_source#/dev/block/}
	[ "$rc_part" != "$rc_source" ] && [ -n "$rc_part" ] || return 1
	case "$rc_part" in */*|*..*|*[!A-Za-z0-9_-]*) return 1;; esac
	[ "$($BB sed -n 's/^PARTNAME=//p' "/sys/class/block/$rc_part/uevent" 2>/dev/null)" = userdata ] || return 1
	rc_count=0
	for rc_uevent in /sys/class/block/*/uevent; do
		[ -r "$rc_uevent" ] || continue
		[ "$($BB sed -n 's/^PARTNAME=//p' "$rc_uevent" 2>/dev/null)" = userdata ] || continue
		rc_count=$((rc_count + 1))
	done
	[ "$rc_count" = 1 ] || return 1
	rc_devnum=$($BB cat "/sys/class/block/$rc_part/dev" 2>/dev/null) || return 1
	case "$rc_devnum" in [0-9]*:[0-9]*) :;; *) return 1;; esac
	if [ -e "$rc_source" ] || [ -L "$rc_source" ]; then
		[ -b "$rc_source" ] && [ ! -L "$rc_source" ] &&
			[ "$($BB stat -c '%t:%T' "$rc_source")" = "$($BB printf '%x:%x' "${rc_devnum%%:*}" "${rc_devnum##*:}")" ] || return 1
		rc_size=$($BB blockdev --getsize64 "$rc_source" 2>/dev/null) || return 1
	else
		rc_sectors=$($BB cat "/sys/class/block/$rc_part/size" 2>/dev/null) || return 1
		case "$rc_sectors" in ''|*[!0-9]*) return 1;; esac
		rc_size=$((rc_sectors * 512))
	fi
	case "$rc_size" in ''|*[!0-9]*) return 1;; esac
	[ "$rc_size" -ge "$ROOT_CONTRACT_MIN_BYTES" ] && [ "$rc_size" -le "$ROOT_CONTRACT_MAX_BYTES" ] || return 1
	$BB awk -v node="$rc_source" -v devnum="$rc_devnum" '
		{
			sep = 0
			for (i = 7; i <= NF; i++) if ($i == "-") { sep = i; break }
			src = sep ? $(sep + 2) : ""
			fstype = sep ? $(sep + 1) : ""
			sources[NR] = src
			devs[NR] = $3
			paths[NR] = $5
		}
		$5 == "/" {
			n++; source = src; dev = $3
			if (!sep || $4 != "/" || fstype != "ext4") bad++
			for (i = 7; i < sep; i++)
				if ($i ~ /^(shared|master|propagate_from):/ || $i == "unbindable") bad++
		}
		END {
			for (i = 1; i <= NR; i++)
				if ((sources[i] == node || devs[i] == devnum) && paths[i] != "/") bad++
			exit(n != 1 || bad || source != node || dev != devnum)
		}
	' "$rc_info" || return 1
	ROOT_CONTRACT_KIND=ext4
	ROOT_CONTRACT_NODE=$rc_source
	ROOT_CONTRACT_SIZE=$rc_size
	ROOT_CONTRACT_OPTS=$rc_opts
	return 0
}

boot_record_bound=4096
boot_record_id() {
	br_boot=$($BB cat /proc/sys/kernel/random/boot_id 2>/dev/null) || return 1
	case "$br_boot" in
		????????-????-????-????-????????????)
			case "$br_boot" in *[!0-9a-f-]*) return 1;; esac;;
		*) return 1;;
	esac
}
boot_record_root() {
	br_path=$1
	[ -d "$br_path" ] && [ ! -L "$br_path" ] &&
		[ "$($BB stat -c %u "$br_path" 2>/dev/null)" = 0 ] || return 1
	if [ "$br_path" = / ]; then
		root_contract_switched_root /proc/1/mounts /proc/1/mountinfo || return 1
	else
		root_contract_pinned_userdata "$br_path" || return 1
	fi
	case ",$ROOT_CONTRACT_OPTS," in *,rw,*) :;; *) return 1;; esac
}
boot_record_lines() {
	br_panel_file=${PMOS_PANEL_RECORD:-/run/pmos-pre-ssh-panel.record}
	br_panel=
	if [ -e "$br_panel_file" ] || [ -L "$br_panel_file" ]; then
		[ -f "$br_panel_file" ] && [ ! -L "$br_panel_file" ] &&
			[ "$($BB stat -c '%u:%a:%h' "$br_panel_file")" = 0:600:1 ] || return 1
		br_panel=$($BB cat "$br_panel_file") || return 1
		[ "${#br_panel}" -le 400 ] || return 1
		$BB printf '%s\n' "$br_panel" | $BB awk '
			NR == 1 && /^usb-init: pre-SSH panel card0=[ -~]*$/ {ok=1}
			END {exit(ok && NR == 1 ? 0 : 1)}' || return 1
	fi
	set -- \
		"boot $br_boot" \
		"pmos-self-stage: diagnostic hold and :22 verified on boot $br_boot"
	[ -z "$br_panel" ] || set -- "$@" "$br_panel"
	set -- "$@" \
		'pmos-stage: using unpacked persistent postmarketOS root' \
		'pmos-stage: mounted private proc/sys/configfs and guest-only dev, verified nodes and private devpts' \
		'pmos-stage: second key-only SSH listening on 172.16.42.2:2222 (diagnostic :22 untouched)' \
		'pmos-stage: STAGED ok; enter with: ssh -p 2222 root@172.16.42.2 (accept the printed key)' \
		'pmos-self-stage: mounted pinned persistent root from read-only /dev/block/sda13 (sda13) and verified its root contract' \
		'pmos-self-stage: guest :2222 public key matches the diagnostic host key; pin [172.16.42.2]:2222 before the PID 1 request' \
		'radio-bringup: stock INI, one-shot helper and service markers verified and staged in guest RAM before cutover' \
		"pmos-self-stage: staged postmarketOS root and armed PID 1 request for boot $br_boot" \
		'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init' \
		"pmos-self-post: post-cutover PID 1 on boot $br_boot; guard identity check passed; pid1 identity check passed"
	$BB printf '%s\n' "$@"
}
boot_record_rotate() {
	# Deterministic per-boot rotation, refusable and never a bypass: only a
	# complete, root-only, 0600, link-count-1 regular record whose first line
	# names a syntactically valid foreign boot ID is rotated to a
	# bound-limited per-boot archive path on the same persistent root.
	br_archive=$1/.omnipha-boot-record-$br_old_boot
	[ "$br_old_size" -ge 42 ] && [ "$br_old_size" -le "$boot_record_bound" ] || return 1
	[ ! -e "$br_archive" ] && [ ! -L "$br_archive" ] || return 1
	$BB mv -n "$br_record" "$br_archive" || return 1
	[ ! -e "$br_record" ] && [ ! -L "$br_record" ] || return 1
	[ -f "$br_archive" ] && [ ! -L "$br_archive" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$br_archive")" = "0:600:1:$br_old_size" ] &&
		[ "$($BB cat "$br_archive")" = "$br_old" ] || return 1
	$BB sync -f "$br_archive"
}
boot_record_open() {
	boot_record_root "$1" && boot_record_id || return 1
	br_record=$1/.omnipha-boot-record
	if [ -e "$br_record" ] || [ -L "$br_record" ]; then
		[ -f "$br_record" ] && [ ! -L "$br_record" ] || return 1
		br_old=$($BB cat "$br_record") || return 1
		br_old_size=$($BB stat -c %s "$br_record" 2>/dev/null) || return 1
		case "$br_old_size" in ''|*[!0-9]*) return 1;; esac
		[ "$br_old_size" = "$((${#br_old} + 1))" ] || return 1
		[ "$($BB stat -c '%u:%a:%h:%s' "$br_record")" = "0:600:1:$br_old_size" ] || return 1
		br_old_first=
		while IFS= read -r br_line; do br_old_first=$br_line; break; done <<EOF
$br_old
EOF
		case "$br_old_first" in
			"boot "????????-????-????-????-????????????)
				br_old_boot=${br_old_first#boot }
				case "$br_old_boot" in *[!0-9a-f-]*) return 1;; esac;;
			*) return 1;;
		esac
		[ "$br_old_boot" != "$br_boot" ] || return 1
		boot_record_rotate "$1" || return 1
	fi
	(umask 077; set -C; $BB printf 'boot %s\n' "$br_boot" > "$br_record") || return 1
	br_size=$($BB stat -c %s "$br_record" 2>/dev/null) || return 1
	[ -f "$br_record" ] && [ ! -L "$br_record" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$br_record")" = "0:600:1:$br_size" ] &&
		[ "$br_size" = 42 ] &&
		[ "$($BB cat "$br_record")" = "boot $br_boot" ] || return 1
	$BB sync -f "$br_record"
}
boot_record_append() {
	boot_record_root "$1" && boot_record_id || return 1
	br_record=$1/.omnipha-boot-record
	[ -f "$br_record" ] && [ ! -L "$br_record" ] || return 1
	br_old=$($BB cat "$br_record") || return 1
	br_size=$($BB stat -c %s "$br_record" 2>/dev/null) || return 1
	[ "$br_size" -ge 42 ] && [ "$br_size" -le "$boot_record_bound" ] &&
		[ "$br_size" = "$((${#br_old} + 1))" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$br_record")" = "0:600:1:$br_size" ] || return 1
	br_next="$br_old
$2"
	br_all=$(boot_record_lines) || return 1
	br_post="pmos-self-post: post-cutover PID 1 on boot $br_boot; guard identity check passed; pid1 identity check passed"
	case "$br_all" in
		"$br_next"|"$br_next
"*) :;;
		*)
			br_cutover=${br_all%"
$br_post"}
			case "$br_old" in
				"$br_cutover"|"$br_cutover
pmos-self-post: FAIL: "*) :;;
				*) return 1;;
			esac
			case "$2" in
				"pmos-self-post: FAIL: "*) :;;
				*) return 1;;
			esac
			br_fails=0
			br_rest=$br_next
			while :; do
				case "$br_rest" in
					*"pmos-self-post: FAIL: "*) br_fails=$((br_fails + 1)); br_rest=${br_rest#*pmos-self-post: FAIL: };;
					*) break;;
				esac
			done
			[ "$br_fails" -le 2 ] || return 1
			;;
	esac
	[ "$((br_size + ${#2} + 1))" -le "$boot_record_bound" ] || return 1
	$BB printf '%s\n' "$2" >> "$br_record" || return 1
	br_size=$($BB stat -c %s "$br_record" 2>/dev/null) || return 1
	[ "$br_size" = "$((${#br_next} + 1))" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$br_record")" = "0:600:1:$br_size" ] &&
		[ "$($BB cat "$br_record")" = "$br_next" ] || return 1
	$BB sync -f "$br_record"
}
boot_record_verify() {
	boot_record_root "$1" && boot_record_id || return 1
	br_record=$1/.omnipha-boot-record
	[ -f "$br_record" ] && [ ! -L "$br_record" ] || return 1
	br_size=$($BB stat -c %s "$br_record" 2>/dev/null) || return 1
	[ "$br_size" -ge 42 ] && [ "$br_size" -le "$boot_record_bound" ] &&
		[ "$($BB stat -c '%u:%a:%h:%s' "$br_record")" = "0:600:1:$br_size" ] || return 1
	br_all=$(boot_record_lines) || return 1
	br_body=$($BB cat "$br_record") || return 1
	[ "$br_size" = "$((${#br_body} + 1))" ] || return 1
	case "$2" in
		'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init')
			case "$br_all" in
				"$br_body
"*) :;;
				*) return 1;;
			esac
			case "$br_body" in
				*"
$2") :;;
				*) return 1;;
			esac;;
		"pmos-self-post: post-cutover PID 1 on boot $br_boot; guard identity check passed; pid1 identity check passed")
			[ "$br_body" = "$br_all" ] || return 1;;
		*) return 1;;
	esac
	$BB sync -f "$br_record" || return 1
	case "$2" in
		'usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init')
			[ "$($BB cat "$br_record")" = "$br_body" ];;
		*) [ "$($BB cat "$br_record")" = "$br_all" ];;
	esac
}

root_contract_promote() {
	rc_path=$1
	root_contract_pinned_userdata "$rc_path" || return 1
	case ",$ROOT_CONTRACT_OPTS," in
		*,ro,*) :;;
		*) return 1;;
	esac
	$BB mount -o remount,rw "$ROOT_CONTRACT_NODE" "$rc_path" || return 1
	root_contract_pinned_userdata "$rc_path" || return 1
	case ",$ROOT_CONTRACT_OPTS," in
		*,rw,*) :;;
		*) return 1;;
	esac
	ROOT_CONTRACT_KIND=ext4
	return 0
}
