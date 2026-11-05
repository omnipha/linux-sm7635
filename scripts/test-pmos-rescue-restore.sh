#!/bin/bash
set -euo pipefail
export LC_ALL=C TZ=UTC
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

fixture() {
	set -euo pipefail
	export LC_ALL=C TZ=UTC E2FSCK_CONFIG=/dev/null
	umask 077
	PATH=/usr/sbin:/usr/bin:/sbin:/bin
	export PATH

	fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

	[ "$#" -eq 1 ] && [ "$(id -u)" = 0 ] || fail 'invalid fixture invocation'
	[ "$(readlink /proc/self/ns/mnt)" != "$1" ] || fail 'mount namespace was not isolated'
	[ "$(findmnt -n -o PROPAGATION /)" = private ] || fail 'mount propagation is not private'

	WORK=$(mktemp -d /tmp/pmos-rescue-restore.XXXXXXXX) || fail 'cannot create fixture directory'
	case "$WORK" in /tmp/pmos-rescue-restore.????????) :;; *) fail 'invalid fixture directory';; esac
	[ ! -L "$WORK" ] && [ "$(readlink -f "$WORK")" = "$WORK" ] || fail 'unsafe fixture directory'
	IMG="$WORK/fixture.img"
	MNT="$WORK/mnt"
	LOOP=

	mount_count() {
		awk -v target="$MNT" '$5 == target {n++} END {print n+0}' /proc/self/mountinfo
	}

	associations() {
		losetup -j "$IMG" -n -O NAME
	}

	valid_loop() {
		case "$1" in /dev/loop*) local n=${1#/dev/loop};; *) return 1;; esac
		case "$n" in ''|*[!0-9]*) return 1;; esac
		[ -b "$1" ]
	}

	loop_matches() {
		[ -n "$LOOP" ] && valid_loop "$LOOP" || return 1
		[ "$(losetup -n -O BACK-FILE "$LOOP")" = "$IMG" ] || return 1
		[ "$(associations)" = "$LOOP" ]
	}

	mount_matches() {
		[ "$(mount_count)" = 1 ] || return 1
		[ "$(findmnt -n --mountpoint "$MNT" -o TARGET)" = "$MNT" ] || return 1
		[ "$(findmnt -n --mountpoint "$MNT" -o SOURCE)" = "$LOOP" ] || return 1
		[ "$(findmnt -n --mountpoint "$MNT" -o FSTYPE)" = ext4 ]
	}

	cleanup() {
		local status=$1 count attached
		trap '' HUP INT TERM
		trap - EXIT
		count=$(mount_count) || { printf 'FAIL: cannot inspect fixture mount; preserving %s\n' "$WORK" >&2; exit 1; }
		if [ "$count" != 0 ]; then
			if [ "$count" != 1 ] || ! loop_matches || ! mount_matches || ! umount "$MNT"; then
				printf 'FAIL: cannot safely unmount fixture; preserving %s\n' "$WORK" >&2
				exit 1
			fi
		fi
		[ "$(mount_count)" = 0 ] || { printf 'FAIL: fixture mount remains; preserving %s\n' "$WORK" >&2; exit 1; }
		if [ -e "$IMG" ]; then
			attached=$(associations) || { printf 'FAIL: cannot inspect fixture loops; preserving %s\n' "$WORK" >&2; exit 1; }
			if [ -n "$attached" ]; then
				if [ -z "$LOOP" ]; then LOOP=$attached; fi
				if [ "$attached" != "$LOOP" ] || ! loop_matches || ! losetup -d "$LOOP"; then
					printf 'FAIL: cannot safely detach fixture loop; preserving %s\n' "$WORK" >&2
					exit 1
				fi
			fi
			attached=$(associations) || { printf 'FAIL: cannot verify loop cleanup; preserving %s\n' "$WORK" >&2; exit 1; }
			[ -z "$attached" ] || { printf 'FAIL: fixture loop remains; preserving %s\n' "$WORK" >&2; exit 1; }
		fi
		if [ "$status" -ne 0 ]; then
			printf 'FAIL: fixture preserved for inspection: %s\n' "$WORK" >&2
			exit "$status"
		fi
		rm -rf -- "$WORK" || exit 1
		exit "$status"
	}
	trap 'cleanup $?' EXIT
	trap 'exit 1' HUP INT TERM

	read_u16_le() {
		od -An -v -j "$1" -N 2 -t u1 "$2" | awk 'NF == 2 {printf "%.0f\n", $1 + $2 * 256; found=1} END {if (!found) exit 1}'
	}

	read_u32_le() {
		od -An -v -j "$1" -N 4 -t u1 "$2" | awk 'NF == 4 {printf "%.0f\n", $1 + $2 * 256 + $3 * 65536 + $4 * 16777216; found=1} END {if (!found) exit 1}'
	}

	verify_features() {
		[ "$(read_u16_le 1080 "$IMG")" = 61267 ] || fail 'invalid ext4 superblock magic'
		[ "$(read_u32_le 1116 "$IMG")" = "$((0x28))" ] || fail 'compat mask mismatch'
		[ "$(read_u32_le 1120 "$IMG")" = "$((0x2c2))" ] || fail 'incompat mask mismatch'
		[ "$(read_u32_le 1124 "$IMG")" = "$((0x46b))" ] || fail 'ro_compat mask mismatch'
	}

	fsck_output_clean() {
		awk '
			NR == 1 && $0 !~ /^e2fsck [0-9]+\.[0-9]+(\.[0-9]+)? \([0-9]+-[A-Za-z]+-[0-9]+\)$/ {bad=1}
			NR == 2 && $0 != "Pass 1: Checking inodes, blocks, and sizes" {bad=1}
			NR == 3 && $0 != "Pass 2: Checking directory structure" {bad=1}
			NR == 4 && $0 != "Pass 3: Checking directory connectivity" {bad=1}
			NR == 5 && $0 != "Pass 4: Checking reference counts" {bad=1}
			NR == 6 && $0 != "Pass 5: Checking group summary information" {bad=1}
			NR == 7 && $0 !~ /^fs324: [0-9]+\/[0-9]+ files \([0-9]+\.[0-9]+% non-contiguous\), [0-9]+\/[0-9]+ blocks$/ {bad=1}
			END {exit (bad || NR != 7)}' "$1"
	}

	fsck_clean() {
		local before after
		[ "$(mount_count)" = 0 ] && [ -z "$(associations)" ] || fail 'offline check attempted on attached fixture'
		[ "$(read_u16_le 1082 "$IMG")" = 1 ] || fail 'fixture not marked clean'
		before=$(sha256sum "$IMG")
		e2fsck -fn "$IMG" > "$1" 2>&1 || fail 'offline e2fsck -fn failed'
		fsck_output_clean "$1" || fail 'offline e2fsck output not clean'
		after=$(sha256sum "$IMG")
		[ "$before" = "$after" ] || fail 'offline inspection changed the image'
	}

	attach() {
		[ -z "$LOOP" ] && [ -z "$(associations)" ] || fail 'fixture loop already attached'
		[ -f "$IMG" ] && [ ! -L "$IMG" ] && [ "$(readlink -f "$IMG")" = "$IMG" ] || fail 'invalid fixture image'
		LOOP=$(losetup --find --show "$IMG") || fail 'cannot attach fixture loop'
		loop_matches || fail 'fixture loop backing mismatch'
	}

	detach() {
		[ "$(mount_count)" = 0 ] && loop_matches || fail 'unsafe fixture detach'
		losetup -d "$LOOP" || fail 'cannot detach fixture loop'
		[ -z "$(associations)" ] || fail 'fixture loop still associated'
		LOOP=
	}

	mount_ro() {
		[ -d "$MNT" ] && [ ! -L "$MNT" ] && [ "$(readlink -f "$MNT")" = "$WORK/mnt" ] || fail 'unsafe mount target'
		[ "$(mount_count)" = 0 ] && loop_matches || fail 'unsafe fixture mount'
		mount -t ext4 -o ro,noload "$LOOP" "$MNT" || fail 'fixture read-only mount failed'
		mount_matches || fail 'fixture mount identity mismatch'
		findmnt -n --mountpoint "$MNT" -o OPTIONS | awk -F, '{for (i=1; i<=NF; i++) {if ($i == "ro") ro=1; if ($i == "noload" || $i == "norecovery") nr=1}} END {exit !(ro && nr)}' || fail 'fixture is not ro,noload'
	}

	remount() {
		case "$1" in ro|rw) :;; *) fail 'invalid remount mode';; esac
		loop_matches && mount_matches || fail 'unsafe fixture remount'
		mount -o "remount,$1" "$LOOP" "$MNT" || fail 'fixture remount failed'
		loop_matches && mount_matches || fail 'fixture remount identity changed'
		findmnt -n --mountpoint "$MNT" -o OPTIONS | awk -F, -v expected="$1" '{for (i=1; i<=NF; i++) if ($i == expected) ok=1} END {exit !ok}' || fail 'fixture mount mode mismatch'
	}

	unmount_fs() {
		loop_matches && mount_matches || fail 'unsafe fixture unmount'
		umount "$MNT" || fail 'cannot unmount fixture'
		[ "$(mount_count)" = 0 ] || fail 'fixture mount remains'
	}

	snapshot_tree() {
		loop_matches && mount_matches || fail 'unsafe fixture snapshot'
		find "$MNT" -mindepth 1 -print0 | sort -z > "$WORK/paths" || fail 'cannot list fixture paths'
		while IFS= read -r -d '' path; do
			local relative=${path#"$MNT"} type digest target
			case "$relative" in *$'\n'*|*$'\r'*|'') fail 'unsupported fixture path';; esac
			type=$(stat -c %F "$path") || fail 'cannot inspect fixture path'
			case "$type" in
				directory) printf 'DIR %s\n' "$relative";;
				'regular file') digest=$(sha256sum "$path") || fail 'cannot hash fixture file'; printf 'REG %s %s\n' "$relative" "${digest%% *}";;
				'symbolic link') target=$(readlink "$path") || fail 'cannot inspect fixture symlink'; printf 'LNK %s %s\n' "$relative" "$target";;
				*) fail "unexpected fixture path type: $relative";;
			esac
		done < "$WORK/paths" | sort
	}

	truncate -s 33554432 "$IMG"
	[ -f "$IMG" ] && [ ! -L "$IMG" ] && [ "$(stat -c %s "$IMG")" = 33554432 ] || fail 'invalid fixture image'
	printf '%s\n' '[defaults]' 'base_features = sparse_super' '[fs_types]' 'ext4 = {' 'features = extent' '}' 'small = {' '}' > "$WORK/mke2fs.conf"
	MKE2FS_CONFIG="$WORK/mke2fs.conf" mke2fs -q -F -t ext4 -b 4096 -I 256 -L fs324 \
		-O none,dir_index,ext_attr,filetype,extent,64bit,flex_bg,sparse_super,large_file,huge_file,dir_nlink,extra_isize,metadata_csum \
		-E lazy_itable_init=0 "$IMG" > "$WORK/mkfs.out" 2>&1 || fail 'fixture mkfs failed'
	verify_features
	fsck_clean "$WORK/fsck-before.out"
	printf 'features: compat 0x28, incompat 0x2c2, ro_compat 0x46b; no journal; initial offline fsck clean\n'

	mkdir -m 700 "$MNT"
	attach
	mount_ro
	if mkdir "$MNT/denied" 2>/dev/null; then fail 'write succeeded on read-only mount'; fi
	remount rw
	mkdir -p "$MNT/usr/lib" "$MNT/bin" "$MNT/sbin" "$MNT/etc"
	printf '%s\n' 'ID="postmarketos"' > "$MNT/usr/lib/os-release"
	printf '%s\n' busybox > "$MNT/bin/busybox"
	printf '%s\n' openrc > "$MNT/sbin/openrc"
	printf '%s\n' '::sysinit:/sbin/openrc sysinit' > "$MNT/etc/inittab"
	ln -s ../bin/busybox "$MNT/sbin/init"
	remount ro
	baseline=$(snapshot_tree)
	printf '%s\n' "$baseline" | awk '$1 == "REG" && $2 == "/usr/lib/os-release" {n++} END {exit n != 1}' || fail 'baseline target missing'

	remount rw
	mv "$MNT/usr/lib/os-release" "$MNT/usr/lib/os-release.disabled"
	remount ro
	fault=$(snapshot_tree)
	expected=$(printf '%s\n' "$baseline" | awk '$1 == "REG" && $2 == "/usr/lib/os-release" {$2="/usr/lib/os-release.disabled"} {print}' | sort)
	[ "$fault" = "$expected" ] || fail 'fault changed more than the target pathname or content'
	unmount_fs
	detach
	fsck_clean "$WORK/fsck-interrupted.out"
	printf 'interruption: clean unmount after one rename, offline fsck clean; not a power-loss test\n'

	attach
	mount_ro
	[ "$(snapshot_tree)" = "$fault" ] || fail 'fault state did not persist across clean unmount'
	remount rw
	mv "$MNT/usr/lib/os-release.disabled" "$MNT/usr/lib/os-release"
	remount ro
	[ "$(snapshot_tree)" = "$baseline" ] || fail 'restored logical tree differs from baseline'
	unmount_fs
	detach
	verify_features
	fsck_clean "$WORK/fsck-after.out"
	printf 'restore: baseline paths, types, symlink targets and file contents restored; metadata may differ\n'

	cp "$IMG" "$WORK/dirty.img"
	debugfs -w -R 'ssv state 0' "$WORK/dirty.img" > "$WORK/debugfs.out" 2>&1 || fail 'cannot create dirty-state control'
	[ "$(read_u16_le 1082 "$WORK/dirty.img")" = 0 ] || fail 'dirty-state control not created'
	dumpe2fs -h "$WORK/dirty.img" > "$WORK/dirty.header" 2>&1 || fail 'cannot inspect dirty control'
	awk -F: '/^Filesystem state:/ {sub(/^ +/, "", $2); if ($2 == "not clean") ok=1} END {exit !ok}' "$WORK/dirty.header" || fail 'dirty-state control not detected'
	before=$(sha256sum "$WORK/dirty.img")
	if e2fsck -fn "$WORK/dirty.img" > "$WORK/fsck-dirty.out" 2>&1; then dirty_rc=0; else dirty_rc=$?; fi
	[ "$(sha256sum "$WORK/dirty.img")" = "$before" ] || fail 'dirty control changed during offline inspection'
	[ "$(read_u16_le 1082 "$WORK/dirty.img")" = 0 ] || fail 'dirty control state changed'
	if [ "$dirty_rc" -eq 0 ] && fsck_output_clean "$WORK/fsck-dirty.out"; then
		printf 'dirty control: e2fsck -fn exited 0 with clean-looking output despite state=0; image unchanged\n'
	else
		printf 'dirty control: state=0 refused separately; e2fsck -fn exit=%s; image unchanged\n' "$dirty_rc"
	fi
	printf 'synthetic host checks passed; not a device measurement or rescue authorization\n'
}

[ "$#" -eq 0 ] || { printf 'FAIL: usage: %s (no arguments)\n' "$0" >&2; exit 1; }
for tool in sudo unshare truncate losetup mke2fs e2fsck dumpe2fs debugfs findmnt mount umount sha256sum od awk stat readlink cp mkdir ln mv chmod sync find sort printf env id; do
	command -v "$tool" >/dev/null || { printf 'FAIL: missing tool: %s\n' "$tool" >&2; exit 1; }
done
sudo -n true || { printf 'FAIL: passwordless sudo required\n' >&2; exit 1; }
parent_ns=$(readlink /proc/self/ns/mnt)
{ declare -f fixture; printf '%s\n' 'fixture "$@"'; } |
	sudo -n timeout -k 5 180 unshare --mount --propagation private env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C TZ=UTC bash -s -- "$parent_ns"
