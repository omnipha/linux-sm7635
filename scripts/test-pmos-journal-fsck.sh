#!/bin/sh
set -eu
export LC_ALL=C TZ=UTC
umask 077
BB=/bin/busybox

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
run() { /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C TZ=UTC "$@"; }
root() { /usr/bin/sudo -n /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C TZ=UTC E2FSCK_CONFIG=/dev/null "$@"; }
hash() { "$BB" sha256sum "$1" | "$BB" cut -d ' ' -f 1; }

[ "$#" -eq 0 ] || fail 'usage: test-pmos-journal-fsck.sh (no arguments)'
for tool in "$BB" /usr/bin/env /usr/bin/sudo /sbin/losetup /sbin/blockdev /sbin/mke2fs /sbin/debugfs /sbin/dumpe2fs /sbin/e2fsck; do
	[ -f "$tool" ] && [ -x "$tool" ] || fail "missing tool: $tool"
done
root "$BB" true || fail 'passwordless sudo required'
WORK=$("$BB" mktemp -d /tmp/pmos-journal-fsck.XXXXXXXX) || fail 'cannot create temporary directory'
RO=

valid_loop() {
	case "$1" in /dev/loop*) loop_number=${1#/dev/loop};; *) return 1;; esac
	case "$loop_number" in ''|*[!0-9]*) return 1;; esac
}

finish() {
	finish_status=$1
	trap - 0 HUP INT TERM
	cleanup_ok=1
	for cleanup_image in "$WORK/clean.img" "$WORK/dirty.img" "$WORK/error.img" "$WORK/clean-error.img" "$WORK/error-count.img" "$WORK/corrupt.img" "$WORK/journal.img" "$WORK/recovery.img"; do
		[ -f "$cleanup_image" ] || continue
		if ! cleanup_loops=$(root /sbin/losetup -j "$cleanup_image" -n -O NAME); then
			printf 'FAIL: cannot inspect loop associations for %s\n' "$cleanup_image" >&2
			cleanup_ok=0
			continue
		fi
		for cleanup_loop in $cleanup_loops; do
			if ! valid_loop "$cleanup_loop" || ! root /sbin/losetup -d "$cleanup_loop"; then
				printf 'FAIL: cannot detach fixture loop %s\n' "$cleanup_loop" >&2
				cleanup_ok=0
			fi
		done
		if ! cleanup_loops=$(root /sbin/losetup -j "$cleanup_image" -n -O NAME) || [ -n "$cleanup_loops" ]; then
			printf 'FAIL: fixture loop association remains for %s\n' "$cleanup_image" >&2
			cleanup_ok=0
		fi
	done
	if [ "$cleanup_ok" -eq 1 ] && "$BB" rm -rf -- "$WORK"; then
		printf 'cleanup: no fixture image loop associations remain\n'
	else
		printf 'FAIL: cleanup incomplete; inspect %s\n' "$WORK" >&2
		finish_status=1
	fi
	exit "$finish_status"
}
trap 'finish $?' 0
trap 'exit 1' HUP INT TERM

attach_ro() {
	[ -z "$RO" ] || fail 'previous fixture loop is still attached'
	case "$1" in "$WORK/clean.img"|"$WORK/dirty.img"|"$WORK/error.img"|"$WORK/clean-error.img"|"$WORK/error-count.img"|"$WORK/corrupt.img"|"$WORK/journal.img"|"$WORK/recovery.img") :;; *) fail 'invalid fixture path';; esac
	[ -f "$1" ] && [ ! -L "$1" ] || fail 'fixture image missing or symlinked'
	[ -z "$(root /sbin/losetup -j "$1" -n -O NAME)" ] || fail 'fixture image already attached'
	RO=$(root /sbin/losetup -r -f --show "$1") || fail 'cannot attach fixture loop'
	valid_loop "$RO" || fail 'unexpected loop path'
	[ "$(root /sbin/losetup -j "$1" -n -O NAME)" = "$RO" ] || fail 'loop backing mismatch'
	[ "$(root /sbin/blockdev --getro "$RO")" = 1 ] || fail 'fixture loop is not read-only'
}

detach_ro() {
	valid_loop "$RO" || fail 'invalid loop to detach'
	[ "$(root /sbin/losetup -j "$1" -n -O NAME)" = "$RO" ] || fail 'loop backing changed before detach'
	root /sbin/losetup -d "$RO" || fail 'cannot detach fixture loop'
	RO=
	[ -z "$(root /sbin/losetup -j "$1" -n -O NAME)" ] || fail 'fixture loop still attached'
}

strict_text() {
	[ -f "$1" ] && [ "$("$BB" wc -c < "$1")" -gt 0 ] && [ "$("$BB" wc -c < "$1")" -le 8192 ] &&
		[ "$("$BB" tr -d '\012\040-\176' < "$1" | "$BB" wc -c)" -eq 0 ]
}

banner_ok() {
	strict_text "$1" && [ "$("$BB" wc -l < "$1")" -eq 1 ] &&
		"$BB" awk -v program="$2" 'NR == 1 && $0 ~ ("^" program " [0-9]+\\.[0-9]+(\\.[0-9]+)? \\([0-9]+-[A-Za-z]+-[0-9]+\\)$") {ok=1} END {exit !(NR == 1 && ok)}' "$1"
}

header_ok() {
	strict_text "$1" && banner_ok "$2" dumpe2fs || return 1
	"$BB" awk -v lines="$("$BB" wc -l < "$1")" '
		BEGIN {
			n = split("Filesystem volume name|Last mounted on|Filesystem UUID|Filesystem magic number|Filesystem revision #|Filesystem features|Filesystem flags|Default mount options|Filesystem state|Errors behavior|Filesystem OS type|Inode count|Block count|Reserved block count|Overhead clusters|Free blocks|Free inodes|First block|Block size|Fragment size|Group descriptor size|Blocks per group|Fragments per group|Inodes per group|Inode blocks per group|Filesystem created|Last mount time|Last write time|Mount count|Maximum mount count|Last checked|Check interval|Lifetime writes|Reserved blocks uid|Reserved blocks gid|First inode|Inode size|Required extra isize|Desired extra isize|Default directory hash|Directory Hash Seed|Checksum type|Checksum", names, "|")
			for (i = 1; i <= n; i++) allowed[names[i]] = 1
		}
		{
			if ($0 == "") { blank++; next }
			if (blank) bad = 1
			colon = index($0, ":")
			if (!colon || substr($0, colon + 1, 1) != " ") { bad = 1; next }
			key = substr($0, 1, colon - 1)
			value = substr($0, colon + 1)
			sub(/^ +/, "", value)
			sub(/ +$/, "", value)
			if (!allowed[key] || ++seen[key] != 1 || value == "") bad = 1
			if (key == "Filesystem volume name" && value != "fs324") bad = 1
			if (key == "Filesystem UUID" && value != "6f6d6e69-7068-4170-6d6f-732d726f6f74") bad = 1
			if (key == "Filesystem magic number" && value != "0xEF53") bad = 1
			if (key == "Filesystem state" && value != "clean") bad = 1
			if (key == "Inode count" && value != "1024") bad = 1
			if (key == "Block count" && value != "8192") bad = 1
			if (key == "Block size" && value != "4096") bad = 1
			if (key == "Inode size" && value != "256") bad = 1
			if (key == "Filesystem features") {
				count = split(value, features, / +/)
				if (count != 3) bad = 1
				for (i = 1; i <= count; i++) {
					if (features[i] != "extent" && features[i] != "64bit" && features[i] != "metadata_csum") bad = 1
					if (++feature_seen[features[i]] != 1) bad = 1
				}
			}
		}
		END {
			for (i = 1; i <= n; i++) if (seen[names[i]] != 1) bad = 1
			if (NR != lines || blank != 1) bad = 1
			exit bad ? 1 : 0
		}' "$1"
}

fsck_output_ok() {
	strict_text "$1" && banner_ok "$2" e2fsck && [ "$("$BB" wc -l < "$1")" -eq 6 ] || return 1
	"$BB" awk '
		NR == 1 && $0 != "Pass 1: Checking inodes, blocks, and sizes" {bad=1}
		NR == 2 && $0 != "Pass 2: Checking directory structure" {bad=1}
		NR == 3 && $0 != "Pass 3: Checking directory connectivity" {bad=1}
		NR == 4 && $0 != "Pass 4: Checking reference counts" {bad=1}
		NR == 5 && $0 != "Pass 5: Checking group summary information" {bad=1}
		NR == 6 {
			if ($0 !~ /^fs324: [0-9]+\/1024 files \([0-9]+\.[0-9]+% non-contiguous\), [0-9]+\/8192 blocks$/) bad=1
			split($2, files, "/")
			split($6, blocks, "/")
			if (files[1] > 1024 || blocks[1] > 8192 || substr($4, 2, length($4) - 2) + 0 > 100) bad=1
		}
		END {exit (bad || NR != 6) ? 1 : 0}' "$1"
}

fs_safe() {
	FSCK_STATUS=not-run
	root /sbin/dumpe2fs -h "$1" > "$WORK/header" 2> "$WORK/header.err" || return 1
	header_ok "$WORK/header" "$WORK/header.err" || return 1
	if root /sbin/e2fsck -fn "$1" > "$WORK/fsck.out" 2> "$WORK/fsck.err"; then
		FSCK_STATUS=0
	else
		FSCK_STATUS=$?
		return 1
	fi
	fsck_output_ok "$WORK/fsck.out" "$WORK/fsck.err"
}

expect_header_rejected() {
	if header_ok "$WORK/bad.header" "$WORK/clean.header.err"; then fail "header parser accepted $1"; fi
}
expect_fsck_rejected() {
	if fsck_output_ok "$WORK/bad.fsck" "$WORK/clean.fsck.err"; then fail "fsck parser accepted $1"; fi
}

printf '%s\n' '[defaults]' 'base_features = sparse_super' '[fs_types]' 'ext4 = {' 'features = extent' '}' 'small = {' '}' > "$WORK/mke2fs.conf"
"$BB" truncate -s 33554432 "$WORK/clean.img"
run MKE2FS_CONFIG="$WORK/mke2fs.conf" /sbin/mke2fs -q -F -t ext4 -b 4096 -I 256 -N 1024 -L fs324 -U 6f6d6e69-7068-4170-6d6f-732d726f6f74 -O none,extent,64bit,metadata_csum -E lazy_itable_init=0 "$WORK/clean.img" > "$WORK/mkfs.out" 2>&1 || fail 'synthetic mkfs failed'
clean_hash=$(hash "$WORK/clean.img")
attach_ro "$WORK/clean.img"
fs_safe "$RO" || fail 'clean synthetic filesystem refused'
"$BB" cp "$WORK/header" "$WORK/clean.header"
"$BB" cp "$WORK/header.err" "$WORK/clean.header.err"
"$BB" cp "$WORK/fsck.out" "$WORK/clean.fsck"
"$BB" cp "$WORK/fsck.err" "$WORK/clean.fsck.err"
detach_ro "$WORK/clean.img"
[ "$(hash "$WORK/clean.img")" = "$clean_hash" ] || fail 'clean check modified image'
printf 'clean: synthetic journal-free ext4 accepted on a read-only loop; image unchanged\n'

"$BB" awk '/^Filesystem state:/ {print; print; next} {print}' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'duplicate state'
"$BB" awk '/^Filesystem features:/ {print; print; next} {print}' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'duplicate features'
"$BB" awk '!/^Filesystem state:/' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'missing state'
"$BB" awk '!/^Filesystem features:/' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'missing features'
for feature in has_journal needs_recovery journal_dev unknown_feature metadata_csum; do
	"$BB" awk -v feature="$feature" '/^Filesystem features:/ {$0 = $0 " " feature} {print}' "$WORK/clean.header" > "$WORK/bad.header"
	expect_header_rejected "feature $feature"
done
"$BB" awk '/^Filesystem state:/ {$0 = "Filesystem state:         clean with errors"} {print}' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'clean-with-errors state'
"$BB" awk '/^Filesystem state:/ {print; print "FS Error count:           1"; next} {print}' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'error count'
"$BB" awk '/^Filesystem state:/ {print; print "Unknown field:            value"; next} {print}' "$WORK/clean.header" > "$WORK/bad.header"
expect_header_rejected 'unknown field'
"$BB" cp "$WORK/clean.header" "$WORK/bad.header"
printf '\000' >> "$WORK/bad.header"
expect_header_rejected 'NUL byte'
"$BB" cp "$WORK/clean.header.err" "$WORK/bad.header.err"
printf 'warning\n' >> "$WORK/bad.header.err"
if header_ok "$WORK/clean.header" "$WORK/bad.header.err"; then fail 'header parser accepted stderr warning'; fi

"$BB" awk 'NR == 2 {print} {print}' "$WORK/clean.fsck" > "$WORK/bad.fsck"
expect_fsck_rejected 'duplicate pass'
"$BB" awk 'NR != 3' "$WORK/clean.fsck" > "$WORK/bad.fsck"
expect_fsck_rejected 'missing pass'
"$BB" awk 'NR == 6 {print "Free blocks count wrong (1, counted=8119)."; print "Fix? no"; print ""} {print}' "$WORK/clean.fsck" > "$WORK/bad.fsck"
expect_fsck_rejected 'declined repair with zero status'
"$BB" awk 'NR == 6 {print; print; next} {print}' "$WORK/clean.fsck" > "$WORK/bad.fsck"
expect_fsck_rejected 'duplicate summary'
"$BB" cp "$WORK/clean.fsck" "$WORK/bad.fsck"
printf '\000' >> "$WORK/bad.fsck"
expect_fsck_rejected 'NUL byte'
"$BB" cp "$WORK/clean.fsck.err" "$WORK/bad.fsck.err"
printf 'warning\n' >> "$WORK/bad.fsck.err"
if fsck_output_ok "$WORK/clean.fsck" "$WORK/bad.fsck.err"; then fail 'fsck parser accepted stderr warning'; fi
printf 'parser: duplicate, missing, unknown, error, journal, recovery, NUL and warning controls refused\n'

for spec in 'dirty:0' 'error:2' 'clean-error:3' 'error-count:error_count'; do
	name=${spec%%:*}
	state=${spec#*:}
	"$BB" cp "$WORK/clean.img" "$WORK/$name.img"
	if [ "$state" = error_count ]; then
		run /sbin/debugfs -w -R 'ssv error_count 1' "$WORK/$name.img" > "$WORK/debug.out" 2>&1 || fail 'cannot create error-count fixture'
	else
		run /sbin/debugfs -w -R "ssv state $state" "$WORK/$name.img" > "$WORK/debug.out" 2>&1 || fail "cannot create $name fixture"
	fi
	before_hash=$(hash "$WORK/$name.img")
	attach_ro "$WORK/$name.img"
	if fs_safe "$RO"; then fail "$name filesystem accepted"; fi
	[ "$FSCK_STATUS" = not-run ] || fail "$name was not rejected by header policy"
	case "$name" in
		dirty) "$BB" grep -F -x -q 'Filesystem state:         not clean' "$WORK/header" || fail 'dirty state forge failed';;
		error) "$BB" grep -F -x -q 'Filesystem state:         not clean with errors' "$WORK/header" || fail 'error state forge failed';;
		clean-error) "$BB" grep -F -x -q 'Filesystem state:         clean with errors' "$WORK/header" || fail 'clean error state forge failed';;
		error-count) "$BB" grep -E -q '^FS Error count: +1$' "$WORK/header" || fail 'error count forge failed';;
	esac
	detach_ro "$WORK/$name.img"
	[ "$(hash "$WORK/$name.img")" = "$before_hash" ] || fail "$name check modified image"
	printf 'refused: %s; image unchanged\n' "$name"
done

"$BB" cp "$WORK/clean.img" "$WORK/corrupt.img"
run /sbin/debugfs -w -R 'ssv free_blocks_count 1' "$WORK/corrupt.img" > "$WORK/debug.out" 2>&1 || fail 'cannot create free-block-count corruption'
before_hash=$(hash "$WORK/corrupt.img")
attach_ro "$WORK/corrupt.img"
if fs_safe "$RO"; then fail 'clean-state corrupted filesystem accepted'; fi
[ "$FSCK_STATUS" = 0 ] || fail "corrupted fixture did not reach a zero e2fsck status (status $FSCK_STATUS)"
header_ok "$WORK/header" "$WORK/header.err" || fail 'corrupted fixture did not retain clean accepted header'
"$BB" grep -F -q 'Free blocks count wrong (1, counted=' "$WORK/fsck.out" || fail 'free-block-count corruption was not detected'
"$BB" grep -F -x -q 'Fix? no' "$WORK/fsck.out" || fail 'declined repair was not reported'
if fsck_output_ok "$WORK/fsck.out" "$WORK/fsck.err"; then fail 'fsck parser accepted corrupted output'; fi
corrupt_rc=$FSCK_STATUS
detach_ro "$WORK/corrupt.img"
[ "$(hash "$WORK/corrupt.img")" = "$before_hash" ] || fail 'corrupt check modified image'
printf 'refused: clean-state free-block-count corruption; e2fsck -fn exit=%s; image unchanged\n' "$corrupt_rc"

"$BB" truncate -s 33554432 "$WORK/journal.img"
run MKE2FS_CONFIG="$WORK/mke2fs.conf" /sbin/mke2fs -q -F -t ext4 -b 4096 -I 256 -N 1024 -L fs324 -U 6f6d6e69-7068-4170-6d6f-732d726f6f74 -O none,extent,64bit,metadata_csum,has_journal -E lazy_itable_init=0 "$WORK/journal.img" > "$WORK/mkfs.out" 2>&1 || fail 'journal control mkfs failed'
"$BB" cp "$WORK/clean.img" "$WORK/recovery.img"
run /sbin/debugfs -w -R 'feature needs_recovery' "$WORK/recovery.img" > "$WORK/debug.out" 2>&1 || fail 'cannot create recovery fixture'
for name in journal recovery; do
	before_hash=$(hash "$WORK/$name.img")
	attach_ro "$WORK/$name.img"
	if fs_safe "$RO"; then fail "$name filesystem accepted"; fi
	[ "$FSCK_STATUS" = not-run ] || fail "$name was not rejected by header policy"
	case "$name" in journal) feature=has_journal;; recovery) feature=needs_recovery;; esac
	"$BB" grep -E -q "^Filesystem features:.*(^| )$feature( |$)" "$WORK/header" || fail "$name feature forge failed"
	detach_ro "$WORK/$name.img"
	[ "$(hash "$WORK/$name.img")" = "$before_hash" ] || fail "$name check modified image"
	printf 'refused: %s feature; image unchanged\n' "$feature"
done
printf 'synthetic host checks passed; this is not a production filesystem safety proof\n'
