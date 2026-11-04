#!/bin/sh
set -eu
LC_ALL=C
export LC_ALL
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
FAILS=0
PIDS=
WORK=${WORK:-}

say() { printf '%s\n' "$*"; }
note() { printf 'observed: %s\n' "$*"; }
ok() { printf 'ok: %s\n' "$*"; }
ko() { printf 'FAIL: %s\n' "$*" >&2; FAILS=$((FAILS + 1)); }
die() { code=$1; shift; printf 'ERROR: %s\n' "$*" >&2; exit "$code"; }
expect() { name=$1; shift; if "$@"; then ok "$name"; else ko "$name"; fi; }

valid_work() {
	case "$WORK" in
	/tmp/pmos-writer-exclusion.[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]) return 0 ;;
	esac
	return 1
}

wait_for() {
	i=0
	while [ ! -e "$1" ]; do
		i=$((i + 1))
		[ "$i" -le 200 ] || return 1
		sleep 0.05
	done
	return 0
}

asuser() {
	setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
		--reuid=65534 --regid=65534 --clear-groups "$@"
}

append_as() {
	who=$1
	file=$2
	line=$3
	if [ "$who" = user ]; then
		WERR=$(asuser /bin/sh -c 'printf "%s\n" "$2" >> "$1"' sh "$file" "$line" 2>&1) && WRC=0 || WRC=$?
	else
		WERR=$(/bin/sh -c 'printf "%s\n" "$2" >> "$1"' sh "$file" "$line" 2>&1) && WRC=0 || WRC=$?
	fi
}

wrote_ok() { [ "$WRC" -eq 0 ]; }

denied_erofs() {
	[ "$WRC" -ne 0 ] || return 1
	case "$WERR" in
	*'Read-only file system'*) return 0 ;;
	esac
	return 1
}

denied_other() {
	[ "$WRC" -ne 0 ] || return 1
	case "$WERR" in
	*'Read-only file system'*) return 1 ;;
	esac
	return 0
}

mount_opts() {
	awk -v p="$1" '$5 == p {o = $6; n++} END {if (n == 1) print o; else exit 1}' "${2:-/proc/self/mountinfo}"
}

mount_fstype() {
	awk -v p="$1" '
		$5 == p {for (i = 7; i <= NF; i++) if ($i == "-") {t = $(i + 1); n++}}
		END {if (n == 1) print t; else exit 1}
	' /proc/self/mountinfo
}

absent_mount() { ! mount_opts "$1" "$2" >/dev/null 2>&1; }

has_opt() {
	case ",$1," in
	*,"$2",*) return 0 ;;
	esac
	return 1
}

snap() { cksum < "$1"; }

contender_blocked() {
	pid=$1
	[ -r "/proc/$pid/comm" ] || return 1
	[ "$(cat "/proc/$pid/comm" 2>/dev/null)" = flock ] || return 1
	[ ! -e "$S/contender-got" ] || return 1
	state=$(sed -n 's/^State:[[:space:]]*\(.\).*/\1/p' "/proc/$pid/status" 2>/dev/null) || return 1
	case "$state" in
	S|D) return 0 ;;
	esac
	return 1
}

validate_inner() {
	[ "$(id -u)" = 0 ] || die 2 'inner phase requires root'
	valid_work || die 4 'unexpected work directory'
	[ -d "$WORK" ] && [ ! -L "$WORK" ] && [ "$(stat -c '%u:%a' "$WORK")" = 0:711 ] || die 4 'work directory is not root-owned 0711'
	[ -n "${OUTER_NS:-}" ] || die 4 'host mount namespace id missing'
	[ "$(readlink /proc/self/ns/mnt)" != "$OUTER_NS" ] || die 4 'not in a private mount namespace'
	M=$WORK/mnt
	V=$WORK/view
	S=$WORK/sync
	TARGET=$M/data/target
	LOCK=$M/data/lock
	export WORK M V S TARGET LOCK OUTER_NS
}

inner_exit() {
	rc=$?
	trap - EXIT INT TERM
	for p in $PIDS; do kill "$p" 2>/dev/null || true; done
	umount "$M/ro" 2>/dev/null || true
	umount "$V" 2>/dev/null || true
	umount "$S" 2>/dev/null || true
	umount "$M" 2>/dev/null || true
	exit "$rc"
}

phase_flock() {
	say '== phase 1: flock is advisory; a non-cooperating ordinary writer is not excluded =='
	( exec 9>"$LOCK"; flock -n 9 || exit 21; : > "$S/held"; wait_for "$S/release" || exit 22; : > "$S/released" ) &
	HOLDER=$!
	PIDS="$PIDS $HOLDER"
	wait_for "$S/held" || die 4 'lock holder never took the lock'
	flock -n -E 77 "$LOCK" true && LRC=0 || LRC=$?
	expect 'cooperating non-blocking contender is refused while the lock is held' [ "$LRC" -eq 77 ]
	expect 'holder barrier still present after one refused probe' [ -e "$S/held" ]
	flock -x -w 20 -E 78 "$LOCK" /bin/sh -c ': > "$1"' sh "$S/contender-got" &
	CONTENDER=$!
	PIDS="$PIDS $CONTENDER"
	i=0
	while ! contender_blocked "$CONTENDER"; do
		i=$((i + 1))
		[ "$i" -le 200 ] || break
		sleep 0.05
	done
	[ "$i" -le 200 ] || die 4 'cooperating blocking contender never reached a sleeping flock state'
	sleep 0.3
	expect 'blocking contender is still a sleeping flock process, not yet exec-ed, after 0.3 s' contender_blocked "$CONTENDER"
	before=$(snap "$TARGET")
	asuser /bin/sh -c '
s=$1
t=$2
i=0
while [ ! -e "$s/writer-go" ]; do
	i=$((i + 1))
	[ "$i" -le 200 ] || exit 31
	sleep 0.05
done
n=0
while [ "$n" -lt 20 ]; do
	printf "nonflock-%s\n" "$n" >> "$t" || exit 32
	n=$((n + 1))
done
: > "$s/writer-done"
' sh "$S" "$TARGET" &
	WRITER=$!
	PIDS="$PIDS $WRITER"
	: > "$S/writer-go"
	wait_for "$S/writer-done" || die 4 'non-cooperating writer never finished'
	wait "$WRITER" && wrc=0 || wrc=$?
	expect 'non-cooperating unprivileged writer exited 0 while the lock was held' [ "$wrc" -eq 0 ]
	flock -n -E 77 "$LOCK" true && LRC=0 || LRC=$?
	expect 'lock was still held after the unprivileged write' [ "$LRC" -eq 77 ]
	expect 'holder had not released before the write finished' [ ! -e "$S/released" ]
	expect 'cooperating contender had not acquired the lock during the write' [ ! -e "$S/contender-got" ]
	expect 'target changed under the held lock' [ "$(snap "$TARGET")" != "$before" ]
	expect 'all 20 unlocked writer lines landed after the seed line' [ "$(wc -l < "$TARGET")" -eq 21 ]
	note "lock held by root, unprivileged uid 65534 appended 20 lines without taking it; target now has $(wc -l < "$TARGET") lines"
	: > "$S/release"
	wait_for "$S/released" || die 4 'holder never released'
	wait "$HOLDER" && hrc=0 || hrc=$?
	expect 'holder exited cleanly' [ "$hrc" -eq 0 ]
	wait_for "$S/contender-got" || die 4 'contender never acquired after release'
	wait "$CONTENDER" && crc=0 || crc=$?
	expect 'cooperating contender acquired only after release' [ "$crc" -eq 0 ]
}

phase_ro() {
	say '== phase 2: read-only bind mount denies a non-cooperating writer through that mount only =='
	mkdir -m 0755 "$M/ro"
	mount --bind "$M/data" "$M/ro"
	RO=$M/ro/target
	MOPTS=$(mount_opts "$M/ro") || die 4 'bind mount missing'
	expect 'bind mount starts read-write' has_opt "$MOPTS" rw
	mount -o remount,bind,ro "$M/ro"
	MOPTS=$(mount_opts "$M/ro") || die 4 'bind mount missing'
	expect 'bind mount is now ro in mountinfo' has_opt "$MOPTS" ro
	MOPTS=$(mount_opts "$M") || die 4 'tmpfs mount missing'
	expect 'underlying tmpfs mount stays rw (flag is per mount)' has_opt "$MOPTS" rw
	before=$(snap "$TARGET")
	append_as user "$RO" ro-user
	expect 'unprivileged writer denied with EROFS through the ro bind mount' denied_erofs
	note "unprivileged write via ro bind: rc=$WRC msg=$WERR"
	expect 'file unchanged after denied unprivileged write' [ "$(snap "$TARGET")" = "$before" ]
	append_as root "$RO" ro-root
	expect 'root writer also denied with EROFS while the bind mount is ro' denied_erofs
	note "root write via ro bind: rc=$WRC msg=$WERR"
	expect 'file unchanged after denied root write' [ "$(snap "$TARGET")" = "$before" ]
	REM=$(asuser mount -o remount,bind,rw "$M/ro" 2>&1) && RRC=0 || RRC=$?
	expect 'unprivileged writer cannot remount rw' [ "$RRC" -ne 0 ]
	note "unprivileged remount attempt: rc=$RRC msg=$REM"
	MOPTS=$(mount_opts "$M/ro") || die 4 'bind mount missing'
	expect 'bind mount still ro after unprivileged remount attempt' has_opt "$MOPTS" ro
	append_as user "$TARGET" bypass-rw-path
	expect 'BYPASS: unprivileged writer succeeds through the still-rw original path' wrote_ok
	expect 'BYPASS: file changed although a ro bind mount of the same directory exists' [ "$(snap "$TARGET")" != "$before" ]
	note 'a ro bind mount protects only writers that go through that mount; same-filesystem rw paths stay open'
	before=$(snap "$TARGET")
	mount -o remount,bind,rw "$M/ro" && RRC=0 || RRC=$?
	expect 'BYPASS: root can remount the bind mount rw' [ "$RRC" -eq 0 ]
	append_as user "$RO" user-after-root-remount
	expect 'BYPASS: unprivileged writer succeeds through the formerly ro path after root remount' wrote_ok
	expect 'BYPASS: file changed after privileged remount' [ "$(snap "$TARGET")" != "$before" ]
	note 'no exclusion is claimed against a privileged actor in the same mount namespace'
	mount -o remount,bind,ro "$M/ro"
	before=$(snap "$TARGET")
	append_as user "$RO" ro-user-again
	expect 'denial returns once the mount is remounted ro' denied_erofs
	expect 'file unchanged after re-denied write' [ "$(snap "$TARGET")" = "$before" ]
	umount "$M/ro"
}

phase_ns() {
	say '== phase 3 (exploratory): writer mount namespace with ro view; rescue namespace keeps rw and remount =='
	unshare --mount --propagation private /bin/sh "$WORK/inner.sh" --writer-ns &
	NSPID=$!
	PIDS="$PIDS $NSPID"
	wait_for "$S/ns-ready" || die 4 'writer namespace never became ready'
	rescue_id=$(readlink /proc/self/ns/mnt)
	writer_id=$(readlink "/proc/$NSPID/ns/mnt")
	expect 'writer namespace is distinct from the rescue namespace' [ "$rescue_id" != "$writer_id" ]
	NSINFO=/proc/$NSPID/mountinfo
	MOPTS=$(mount_opts "$V" "$NSINFO") || die 4 'writer view mount missing'
	expect 'writer namespace sees the view as ro' has_opt "$MOPTS" ro
	expect 'writer namespace no longer has the rw tmpfs path' absent_mount "$M" "$NSINFO"
	expect 'rescue namespace has no writer view mount' absent_mount "$V" /proc/self/mountinfo
	MOPTS=$(mount_opts "$M") || die 4 'rescue tmpfs mount missing'
	expect 'rescue namespace keeps the tmpfs rw' has_opt "$MOPTS" rw
	append_as root "$TARGET" rescue-write
	expect 'rescue root writes while the writer namespace view is ro' wrote_ok
	mount -o remount,bind,ro "$M"
	MOPTS=$(mount_opts "$M") || die 4 'rescue tmpfs mount missing'
	expect 'rescue root can remount its own mount ro' has_opt "$MOPTS" ro
	append_as root "$TARGET" rescue-while-ro
	expect 'rescue root is itself denied while its own mount is ro' denied_erofs
	mount -o remount,bind,rw "$M" && RRC=0 || RRC=$?
	expect 'rescue root can remount its own mount rw again' [ "$RRC" -eq 0 ]
	MOPTS=$(mount_opts "$V" "$NSINFO") || die 4 'writer view mount missing'
	expect 'rescue remounts did not change the writer namespace view' has_opt "$MOPTS" ro
	nsenter --mount="/proc/$NSPID/ns/mnt" mount -o remount,bind,rw "$V" && RRC=0 || RRC=$?
	expect 'BYPASS: rescue root can enter the writer namespace and remount its view rw' [ "$RRC" -eq 0 ]
	MOPTS=$(mount_opts "$V" "$NSINFO") || die 4 'writer view mount missing'
	expect 'BYPASS: writer namespace view is rw after the nsenter remount' has_opt "$MOPTS" rw
	nsenter --mount="/proc/$NSPID/ns/mnt" mount -o remount,bind,ro "$V"
	MOPTS=$(mount_opts "$V" "$NSINFO") || die 4 'writer view mount missing'
	expect 'writer namespace view restored to ro' has_opt "$MOPTS" ro
	: > "$S/ns-go"
	wait "$NSPID" && nrc=0 || nrc=$?
	expect 'writer namespace checks all passed' [ "$nrc" -eq 0 ]
	expect 'rescue sees the rescue-side write' grep -q '^rescue-write$' "$TARGET"
	expect 'rescue sees the writer-namespace root write made after its own remount' grep -q '^nsroot-write$' "$TARGET"
}

writer_ns() {
	validate_inner
	mount --make-rprivate /
	mount --bind "$M/data" "$V"
	mount -o remount,bind,ro "$V"
	umount -l "$M"
	: > "$S/ns-ready"
	wait_for "$S/ns-go" || die 4 'rescue namespace never signalled go'
	expect 'writer namespace: tmpfs path is gone' [ ! -e "$M/data" ]
	append_as user "$V/target" ns-user
	expect 'writer namespace: unprivileged writer denied with EROFS' denied_erofs
	note "writer namespace unprivileged write: rc=$WRC msg=$WERR"
	append_as user "$M/data/target" ns-user-origin
	expect 'writer namespace: original rw path is unreachable' denied_other
	REM=$(asuser mount -o remount,bind,rw "$V" 2>&1) && RRC=0 || RRC=$?
	expect 'writer namespace: unprivileged remount fails' [ "$RRC" -ne 0 ]
	note "writer namespace unprivileged remount: rc=$RRC msg=$REM"
	expect 'writer namespace: sees rescue-side write through ro view' grep -q '^rescue-write$' "$V/target"
	append_as root "$V/target" ns-root-denied
	expect 'writer namespace: root denied while view is ro' denied_erofs
	mount -o remount,bind,rw "$V" && RRC=0 || RRC=$?
	expect 'BYPASS: writer namespace root can remount its own view rw' [ "$RRC" -eq 0 ]
	append_as root "$V/target" nsroot-write
	expect 'BYPASS: writer namespace root writes after remount' wrote_ok
	mount -o remount,bind,ro "$V"
	[ "$FAILS" -eq 0 ] || exit 1
	exit 0
}

run_inner() {
	validate_inner
	[ "$$" -le 3 ] || die 4 'inner run is not PID 1-3 of a fresh pid namespace'
	trap inner_exit EXIT
	trap 'exit 130' INT TERM
	mount --make-rprivate /
	mkdir -m 0755 "$M" "$V" "$S"
	mount -t tmpfs -o size=4m,mode=0755,nosuid,nodev tmpfs "$M"
	mount -t tmpfs -o size=1m,mode=1777,nosuid,nodev tmpfs "$S"
	[ "$(mount_fstype "$M")" = tmpfs ] || die 4 'work mount is not tmpfs'
	[ "$(mount_fstype "$S")" = tmpfs ] || die 4 'sync mount is not tmpfs'
	mkdir -m 0755 "$M/data"
	: > "$LOCK"
	printf 'seed\n' > "$TARGET"
	chown 65534:65534 "$TARGET"
	chmod 0644 "$TARGET"
	note "kernel $(uname -r); synthetic tmpfs only, private mount namespace, no block device paths used"
	phase_flock
	phase_ro
	phase_ns
	say '== summary =='
	if [ "$FAILS" -ne 0 ]; then
		say "result: $FAILS expectation(s) failed"
		exit 1
	fi
	say 'result: all demonstrations behaved as described'
	say 'limits: advisory flock excludes only cooperating flock users; a ro bind mount excludes only writers going through that mount and root can remount or bypass it; a separate mount namespace does not exclude privileged or same-filesystem writers; synthetic tmpfs, not proof of sufficient exclusion for any real block device'
	exit 0
}

if [ "${1:-}" = --inner ]; then
	run_inner
fi
if [ "${1:-}" = --writer-ns ]; then
	writer_ns
fi

finish() {
	rc=$?
	trap - EXIT INT TERM
	if [ -n "$WORK" ] && valid_work; then
		if awk -v w="$WORK" 'index($5, w) == 1 {f = 1} END {exit !f}' /proc/self/mountinfo; then
			printf 'ERROR: mount left behind under %s\n' "$WORK" >&2
			[ "$rc" -ne 0 ] || rc=4
		else
			sudo -n rmdir -- "$WORK/mnt" "$WORK/view" "$WORK/sync" 2>/dev/null || true
			sudo -n rm -f -- "$WORK/inner.sh" 2>/dev/null || true
			if ! sudo -n rmdir -- "$WORK" 2>/dev/null; then
				printf 'ERROR: cannot remove %s\n' "$WORK" >&2
				[ "$rc" -ne 0 ] || rc=4
			fi
		fi
	fi
	exit "$rc"
}

[ "$#" -eq 0 ] || die 2 'usage: test-pmos-writer-exclusion.sh'
for tool in sudo unshare nsenter timeout flock setpriv mktemp readlink awk stat cksum tee; do
	command -v "$tool" >/dev/null 2>&1 || die 2 "missing $tool"
done
[ -r "$0" ] || die 2 'cannot read this script'
sudo -n true 2>/dev/null || die 2 'passwordless sudo required'
WORK=
trap finish EXIT
trap 'exit 130' INT TERM
WORK=$(sudo -n mktemp -d /tmp/pmos-writer-exclusion.XXXXXXXX) || die 4 'cannot create root-owned work directory'
valid_work || die 4 'unexpected work directory name'
sudo -n chmod 0711 -- "$WORK" || die 4 'cannot chmod work directory'
sudo -n tee -- "$WORK/inner.sh" < "$0" >/dev/null || die 4 'cannot stage inner script'
sudo -n chmod 0600 -- "$WORK/inner.sh" || die 4 'cannot chmod inner script'
OUTER_NS=$(readlink /proc/self/ns/mnt)
sudo -n env -i PATH="$PATH" LC_ALL=C WORK="$WORK" OUTER_NS="$OUTER_NS" \
	timeout -k 2 90 unshare --mount --pid --fork --kill-child --mount-proc \
	/bin/sh "$WORK/inner.sh" --inner && irc=0 || irc=$?
case "$irc" in
0) ;;
124|137) printf 'ERROR: bounded run timed out (rc=%s)\n' "$irc" >&2; exit 3 ;;
*) printf 'ERROR: inner phase failed (rc=%s)\n' "$irc" >&2; exit "$irc" ;;
esac
exit 0
