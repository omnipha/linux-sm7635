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
	case "$rc_path" in */) return 1;; esac
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
	return 0
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
