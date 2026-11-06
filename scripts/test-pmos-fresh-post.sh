#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" != --inner ]; then
	work=$(mktemp -d "${TMPDIR:-/tmp}/fresh-post.XXXXXXXX")
	chmod 755 "$work"
	trap 'rm -rf "$work"' EXIT
	HERE="$HERE" WORK="$work" python3 -B - <<'PY'
import importlib.util, os, pathlib
here = pathlib.Path(os.environ['HERE'])
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, here / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
builder = load('builder', 'build-init-boot-persistent-root.py')
persist = load('persist', 'derive-radio-persistent.py')
fresh = load('fresh', 'derive-radio-fresh-boot.py')
post = load('post', 'derive-self-post-fresh-boot.py')
radio = fresh.derive(persist.derive(builder.current_scripts()['pmos-radio-bringup.sh'].decode()))
script, hook = post.derive((here / 'pmos-self-post.sh').read_text(), radio.encode())
work = pathlib.Path(os.environ['WORK'])
(work / 'radio').write_text(radio)
(work / 'post').write_text(script)
(work / 'hook').write_text(hook)
unpinned = load('unpinned', 'build-init-boot-mb003-unpinned.py')
canonical_scripts = unpinned.canonical.runtime_scripts()
scripts = unpinned.runtime_scripts()
assert canonical_scripts[builder.FRESH_RADIO] == scripts[builder.FRESH_RADIO]
edited = scripts['pmos-radio-bringup-fresh-boot.sh'] + b': host_only_radio_edit\n'
assert edited != scripts['pmos-radio-bringup-fresh-boot.sh']
(work / 'cpost').write_bytes(scripts['pmos-self-post-fresh-boot.sh'])
(work / 'cpost-canonical').write_bytes(canonical_scripts['pmos-self-post-fresh-boot.sh'])
(work / 'chook').write_bytes(scripts['10-omnipha-self-stage.start'])
(work / 'chook-canonical').write_bytes(canonical_scripts['10-omnipha-self-stage.start'])
(work / 'cradio').write_bytes(edited)
(work / 'bad-sha').write_text(unpinned.BAD_RADIO + '\n')
assert canonical_scripts['pmos-self-post-fresh-boot.sh'] != scripts['pmos-self-post-fresh-boot.sh']
assert canonical_scripts['10-omnipha-self-stage.start'] != scripts['10-omnipha-self-stage.start']
PY
	sudo -n unshare --mount --pid --fork --mount-proc env HERE="$HERE" WORK="$work" /bin/busybox sh "$0" --inner
	exit 0
fi
BB=/bin/busybox
fail() { $BB printf 'FAIL: %s\n' "$*" >&2; exit 1; }
$BB mount --make-rprivate /
R=/tmp/fresh-post-root
$BB mkdir -p "$R"
$BB mount -t tmpfs -o mode=0755,size=32m tmpfs "$R"
for dir in bin usr/libexec/omnipha run/radio-bringup run/pid1-guard proc/sys/kernel/random proc/1 sbin dev tmp; do
	$BB mkdir -p "$R/$dir"
done
$BB chmod 700 "$R/run"
$BB mkdir -p "$R/real"
$BB cp /bin/busybox "$R/real/busybox"
$BB cp "$WORK/post" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/radio" "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB cp "$WORK/hook" "$R/hook"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh" "$R/hook" "$R/run/radio-bringup" "$R/run/pid1-guard"
$BB mknod -m 666 "$R/dev/null" c 1 3
$BB mknod -m 600 "$R/dev/kmsg" c 1 11
boot=11111111-2222-3333-4444-555555555555
nonce=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
$BB printf '%s\n' "$boot" > "$R/proc/sys/kernel/random/boot_id"
$BB printf '%s\n' "$boot" > "$R/run/pid1-guard/armed"
$BB printf '%s\n' "$nonce" > "$R/run/pid1-guard/nonce"
$BB chmod 600 "$R/run/pid1-guard/nonce"
$BB touch "$R/run/keep"
$BB chmod 600 "$R/run/keep"
$BB cat > "$R/bin/busybox" <<'WRAP'
#!/real/busybox sh
BB=/real/busybox
case "${1:-}" in
	id) printf '0\n'; exit 0;;
	stat)
		case "$*" in
			*'/proc/1/root'*|*"%d:%i /"*) printf '1:2\n'; exit 0;;
		esac;;
	sha256sum)
		[ "${2:-}" != /proc/1/exe ] || exec "$BB" sha256sum /bin/busybox
		if [ -f /tmp/mock-bad ] && [ -f "${2:-}" ] && "$BB" cmp -s "$2" /tmp/edited-radio; then
			printf '%s\n' "$2" >> /tmp/mock-bad-hit
			printf '%s  %s\n' "$("$BB" cat /tmp/bad-sha)" "$2"
			exit 0
		fi;;
	awk)
		case "$*" in *'/proc/1/mounts'*) exit 0;; esac;;
	dmesg)
		"$BB" cat /tmp/dmesg
		for marker in /run/radio-bringup/*.marker; do
			[ -f "$marker" ] || continue
			printf 'pmos-self-post: guest radio marker %s\n' "$("$BB" cat "$marker")"
		done
		exit 0;;
	sleep) exit 0;;
	sh)
		if [ "${2:-}" = /usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh ] ||
			{ [ "$#" -ge 5 ] && [ -f "${2:-}" ] && case "${4:-}" in modem|wpss|driver|scan|services) true;; *) false;; esac && case "${3:-}" in *-*-*-*-*) true;; *) false;; esac; }; then
			printf '%s\n' "$2" >> /tmp/launch-paths
			"$BB" cat "$2" > /tmp/launched-radio
			printf '%s\n' "$4" >> /tmp/stages
			[ "${FAIL_STAGE:-}" != "$4" ] || exit 1
			[ "$4" != services ] || "$BB" cat > /tmp/services-stdin
			exit 0
		fi;;
	setsid)
		printf 'started\n' >> /tmp/hook-started
		if [ -f /tmp/execute-hook ]; then
			shift
			"$@"; result=$?
			printf '%s\n' "$result" > /tmp/hook-post-status
		fi
		exit 0;;
esac
exec "$BB" "$@"
WRAP
$BB chmod 755 "$R/bin/busybox"
$BB printf '#!/bin/busybox sh\nexit 0\n' > "$R/sbin/rc-service"
$BB chmod 755 "$R/sbin/rc-service"
$BB mkdir -p "$R/run/openrc"
$BB printf 'default\n' > "$R/run/openrc/softlevel"
$BB printf '1:2\n' > "$R/run/pid1-guard/root-identity"
$BB printf 'synthetic-profile\n' > "$R/run/radio-bringup/wpa_supplicant.conf"
$BB chmod 600 "$R/run/radio-bringup/wpa_supplicant.conf"
panel="usb-init: pre-SSH panel node=boe card0=1 dsi1=1 dcs=none reset=none suspend=clear brightness=0 boot $boot"
$BB printf 'boot %s\npre\n%s\n' "$boot" "$panel" > "$R/.omnipha-boot-record"
$BB chmod 600 "$R/.omnipha-boot-record"
$BB cat > "$R/run/pid1-guard/root-contract.sh" <<'CONTRACT'
boot_record_id() { return 0; }
boot_record_append() {
	[ -f /run/pmos-pre-ssh-panel.record ] && [ ! -L /run/pmos-pre-ssh-panel.record ] &&
		[ "$(/bin/busybox cat /run/pmos-pre-ssh-panel.record)" = "$(/bin/busybox sed -n 3p /.omnipha-boot-record)" ] || return 1
	/bin/busybox printf '%s\n' "$2" >> /.omnipha-boot-record
}
boot_record_verify() { /bin/busybox grep -qF "$2" /.omnipha-boot-record; }
CONTRACT
$BB chmod 700 "$R/run/pid1-guard/root-contract.sh"
$BB cp "$R/.omnipha-boot-record" "$R/tmp/record.before"
$BB printf '<12>usb-init: %s\n' "$panel" > "$R/tmp/dmesg"
run_post() { $BB chroot "$R" /real/busybox sh /usr/libexec/omnipha/pmos-self-post-fresh-boot.sh >"$R/tmp/post.out" 2>&1; }
run_post || { $BB cat "$R/tmp/post.out" >&2; fail 'fresh post rejected mocked valid boot'; }
[ "$( $BB cat "$R/tmp/stages")" = 'modem
wpss
driver
scan
services' ] || fail 'radio stage order changed'
[ "$( $BB cat "$R/tmp/services-stdin")" = synthetic-profile ] || fail 'profile not passed on stdin'
[ "$( $BB cat "$R/run/pmos-pre-ssh-panel.record")" = "$panel" ] || fail 'priority-prefixed panel line not restored'
[ ! -e "$R/run/radio-bringup/wpa_supplicant.conf" ] || fail 'profile was not scrubbed'
$BB chmod 600 "$R/run/pid1-guard/nonce"
for stage in modem wpss driver scan services; do
	token="guest-radio-$stage-$($BB printf '%s' "$boot:$nonce:$stage" | $BB sha256sum | $BB cut -c 1-16)"
	[ "$( $BB cat "$R/run/radio-bringup/$stage.marker")" = "$token" ] &&
		[ "$( $BB stat -c '%u:%a:%h' "$R/run/radio-bringup/$stage.marker")" = 0:600:1 ] || fail "marker $stage invalid"
done
reset_post() {
	$BB rm -rf "$R/run/radio-bringup/omnipha-radio-snapshot" "$R/run/radio-bringup/success-gate-294"
	$BB rm -f "$R/run/radio-bringup/"*.marker "$R/run/radio-bringup/self-post.log" "$R/run/pmos-pre-ssh-panel.record" "$R/tmp/stages" "$R/tmp/services-stdin" "$R/tmp/launch-paths" "$R/tmp/launched-radio" "$R/tmp/mock-bad-hit" "$R/tmp/hook-started" "$R/tmp/hook-post-status"
	$BB cp "$R/tmp/record.before" "$R/.omnipha-boot-record"
	$BB printf 'synthetic-profile\n' > "$R/run/radio-bringup/wpa_supplicant.conf"
	$BB chmod 600 "$R/run/radio-bringup/wpa_supplicant.conf"
	$BB printf '<12>usb-init: %s\n' "$panel" > "$R/tmp/dmesg"
}
reset_post
$BB printf 'different\n' >> "$R/tmp/dmesg"
$BB sed -i '3s/node=boe/node=vxn/' "$R/.omnipha-boot-record"
run_post && fail 'foreign panel record accepted'
[ ! -e "$R/tmp/stages" ] || fail 'radio reached after panel mismatch'
reset_post
$BB printf '[    1.500] usb-init: %s\n' "$panel" > "$R/tmp/dmesg"
run_post || fail 'timestamped panel record rejected'
[ "$( $BB cat "$R/run/pmos-pre-ssh-panel.record")" = "$panel" ] || fail 'timestamped panel line differs'
reset_post
$BB printf '<12>usb-init: %s\n' "$panel" >> "$R/tmp/dmesg"
run_post || fail 'identical panel lines rejected'
reset_post
$BB printf '<12>usb-init: %s\n' "$( $BB printf '%s' "$panel" | $BB sed 's/node=boe/node=vxn/')" >> "$R/tmp/dmesg"
run_post && fail 'conflicting panel lines accepted'
[ ! -e "$R/tmp/stages" ] || fail 'radio reached with conflicting panel lines'
reset_post
$BB printf '%s\n' "$boot" > "$R/run/pid1-guard/accepted"
run_post && fail 'accepted guard started pre-ack radio'
[ ! -e "$R/tmp/stages" ] || fail 'radio reached after ack'
$BB rm "$R/run/pid1-guard/accepted"
reset_post
$BB printf 'pending\n' > "$R/run/pid1-guard/ack"
run_post && fail 'pending ack started pre-ack radio'
[ ! -e "$R/tmp/stages" ] || fail 'radio reached with pending ack'
$BB rm "$R/run/pid1-guard/ack"
reset_post
$BB printf '%s\n' ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff > "$R/run/pid1-guard/nonce"
$BB printf 'stale\n' > "$R/run/radio-bringup/modem.marker"
run_post && fail 'stale marker accepted'
[ ! -e "$R/tmp/stages" ] || fail 'radio reached after stale marker'
$BB printf '%s\n' "$nonce" > "$R/run/pid1-guard/nonce"
reset_post
FAIL_STAGE=wpss; export FAIL_STAGE
run_post && fail 'failing stage accepted'
[ "$( $BB cat "$R/tmp/stages")" = 'modem
wpss' ] || fail 'later stages ran after failure'
unset FAIL_STAGE
$BB chroot "$R" /real/busybox sh /hook
$BB sleep 1
[ -f "$R/tmp/hook-started" ] || fail 'pinned hook did not launch'
$BB rm "$R/tmp/hook-started"
$BB printf '\n' >> "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB chroot "$R" /real/busybox sh /hook && fail 'modified radio accepted by hook'
[ ! -e "$R/tmp/hook-started" ] || fail 'hook launched modified radio'
$BB cmp -s "$WORK/radio" "$WORK/cradio" && fail 'candidate radio unchanged'
$BB cp "$WORK/cpost" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/chook" "$R/hook"
$BB cp "$WORK/cradio" "$R/tmp/edited-radio"
$BB cp "$WORK/bad-sha" "$R/tmp/bad-sha"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "$R/hook" "$R/tmp/edited-radio"
$BB chmod 600 "$R/tmp/bad-sha" "$R/run/pid1-guard/armed" "$R/run/pid1-guard/root-identity" "$R/run/pid1-guard/root-contract.sh"
$BB cp "$WORK/cpost-canonical" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/chook-canonical" "$R/hook-canonical"
$BB cp "$WORK/radio" "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh" "$R/hook-canonical"
$BB rm -f "$R/tmp/hook-started"
$BB chroot "$R" /real/busybox sh /hook-canonical
$BB sleep 1
[ -f "$R/tmp/hook-started" ] || fail 'canonical gated hook did not launch with canonical post and radio'
$BB rm -f "$R/tmp/hook-started"
$BB cp "$R/hook-canonical" "$R/hook-edited-legacy"
$BB printf '\n: host_only_hook_edit\n' >> "$R/hook-edited-legacy"
$BB chmod 700 "$R/hook-edited-legacy"
$BB cp "$WORK/cpost" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB chroot "$R" /real/busybox sh /hook-edited-legacy && fail 'edited legacy hook accepted migrated post'
[ ! -e "$R/tmp/hook-started" ] || fail 'edited legacy hook launched migrated post'
$BB cp "$WORK/cpost-canonical" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/cradio" "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB chroot "$R" /real/busybox sh /hook-canonical && fail 'retained canonical gated hook launched edited radio'
[ ! -e "$R/tmp/hook-started" ] || fail 'retained canonical gated hook launch recorded with edited radio'
reset_post
run_post && fail 'canonical gated post accepted edited radio'
$BB grep -q 'pinned radio bring-up script missing' "$R/tmp/post.out" || fail 'canonical gated post refusal reason missing'
[ ! -e "$R/tmp/stages" ] || fail 'canonical gated post reached a stage with edited radio'
$BB cp "$WORK/cpost" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
reset_post
$BB touch "$R/tmp/mock-bad"
$BB cp "$R/tmp/edited-radio" "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
run_post && fail 'mocked denylisted radio hash was launched'
$BB grep -q 'unsafe, unreadable or refused radio snapshot' "$R/tmp/post.out" || fail 'denylist refusal reason missing'
[ ! -e "$R/tmp/stages" ] || fail 'denylisted radio reached a stage'
$BB rm "$R/tmp/mock-bad"
reset_post
run_post && fail 'fixture unexpectedly passed the full success gate'
[ "$( $BB cat "$R/tmp/stages")" = 'modem
wpss
driver
scan
services' ] || fail 'edited radio did not reach all stages'
[ "$( $BB sort -u "$R/tmp/launch-paths")" = /run/radio-bringup/omnipha-radio-snapshot/radio.sh ] || fail 'edited radio not launched from snapshot'
$BB cmp -s "$R/tmp/launched-radio" "$R/tmp/edited-radio" || fail 'launched snapshot differs from edited radio'
[ "$( $BB stat -c '%u:%g:%a:%h' "$R/run/radio-bringup/omnipha-radio-snapshot/radio.sh")" = 0:0:600:1 ] || fail 'radio snapshot metadata unsafe'
$BB rm -f "$R/tmp/hook-started" "$R/tmp/stages" "$R/tmp/launch-paths" "$R/tmp/launched-radio"
$BB chroot "$R" /real/busybox sh /hook
$BB sleep 1
[ -f "$R/tmp/hook-started" ] || fail 'candidate hook did not launch edited radio path'
$BB touch "$R/tmp/execute-hook"
$BB touch "$R/tmp/mock-bad"
reset_post
$BB chroot "$R" /real/busybox sh /hook
$BB sleep 1
[ -f "$R/tmp/hook-started" ] || fail 'candidate hook did not detach post helper'
[ -f "$R/tmp/mock-bad-hit" ] || fail 'candidate hook post did not check radio hash'
[ ! -e "$R/tmp/stages" ] || fail 'denylisted radio reached stage via hook'
[ "$( $BB cat "$R/tmp/hook-post-status")" != 0 ] || fail 'denylisted post helper exited 0'
$BB rm -f "$R/tmp/mock-bad" "$R/tmp/execute-hook"
$BB chmod 600 "$R/run/pid1-guard/nonce"
[ "$( $BB cat "$R/run/pid1-guard/nonce")" = "$nonce" ] || fail 'guard nonce changed'
[ ! -e "$R/run/pid1-guard/ack" ] && [ ! -e "$R/run/pid1-guard/accepted" ] || fail 'guard acknowledgement changed'
printf 'pass: mocked fresh self-post ordering, nonce markers, priority-prefixed panel restore, refusal paths and pinned hook; no device\n'
printf 'pass: canonical gated hook and post refuse the edited radio when retained; candidate post launches the edited radio only from its snapshot\n'
printf 'scope: exact canonical hook and post are migrated by the installer; an already edited legacy hook is retained and its embedded old post pin still refuses the migrated post, so the coordinator must prove the hook is the exact legacy file before the first candidate boot\n'
printf 'mock caveat: BAD_RADIO is a mocked sha256sum reply for the synthetic edited radio, matched by byte comparison inside the fixture wrapper; no real denylisted payload was used, so this proves refusal logic on that digest only; the snapshot success gate still refuses in this fixture and no ack is exercised\n'
