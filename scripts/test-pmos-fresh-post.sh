#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" != --inner ]; then
	work=$(mktemp -d "${TMPDIR:-/tmp}/fresh-post.XXXXXXXX")
	chmod 755 "$work"
	trap 'rm -rf "$work"' EXIT
	HERE="$HERE" WORK="$work" python3 -B - <<'PY'
import hashlib, importlib.util, os, pathlib
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
assert canonical_scripts['pmos-self-post-fresh-boot.sh'] != scripts['pmos-self-post-fresh-boot.sh']
assert canonical_scripts['10-omnipha-self-stage.start'] != scripts['10-omnipha-self-stage.start']
def sha(data):
    return hashlib.sha256(data).hexdigest()
legacy = unpinned.canonical
fresh_sha = legacy.FRESH_RADIO_SHA.encode()
legacy_post_sha = legacy.GATED_POST_SHA.encode()
legacy_hook_sha = legacy.GATED_HOOK_SHA.encode()
canon_post = canonical_scripts['pmos-self-post-fresh-boot.sh']
canon_hook = canonical_scripts['10-omnipha-self-stage.start']
cand_post = scripts['pmos-self-post-fresh-boot.sh']
cand_hook = scripts['10-omnipha-self-stage.start']
assert sha(canon_post).encode() == legacy_post_sha and sha(canon_hook).encode() == legacy_hook_sha
assert canon_post.count(b'RADIO_SHA=' + fresh_sha) == 1 and b'sha256sum' in canon_hook
assert canon_hook.count(legacy_post_sha) == 1 and canon_hook.count(fresh_sha) == 1
assert b'pinned radio bring-up script missing' in canon_post
for name, data in (('post', cand_post), ('hook', cand_hook)):
    for forbidden in (fresh_sha, legacy_post_sha, legacy_hook_sha, b'RADIO_SHA', b'omnipha-radio-snapshot',
                      b'radio_snapshot', b'pinned radio bring-up script missing',
                      b'd7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3'):
        assert forbidden not in data, (name, forbidden)
assert b'sha256sum' not in cand_hook and b'stat ' not in cand_hook and b'[ -f "$1" ]' not in cand_hook
assert cand_post.count(b'$BB sh "$RADIO" "$boot"') == 2
assert sha(edited).encode() != fresh_sha and sha(edited) != 'd7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3'
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
		[ "${2:-}" != /proc/1/exe ] || exec "$BB" sha256sum /bin/busybox;;
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
		if [ "$#" -ge 5 ] && [ -f "${2:-}" ] && case "${4:-}" in modem|wpss|driver|scan|services) true;; *) false;; esac && case "${3:-}" in *-*-*-*-*) true;; *) false;; esac; then
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
			"$@"
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
RADIO_PATH=/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh
reset_post() {
	$BB rm -rf "$R/run/radio-bringup/omnipha-radio-snapshot" "$R/run/radio-bringup/success-gate-294"
	$BB rm -f "$R/run/radio-bringup/"*.marker "$R/run/radio-bringup/self-post.log" "$R/run/pmos-pre-ssh-panel.record" "$R/tmp/stages" "$R/tmp/services-stdin" "$R/tmp/launch-paths" "$R/tmp/launched-radio" "$R/tmp/hook-started"
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
$BB cp "$WORK/cpost-canonical" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/chook-canonical" "$R/hook-canonical"
$BB cp "$WORK/radio" "$R$RADIO_PATH"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "$R$RADIO_PATH" "$R/hook-canonical"
$BB chmod 600 "$R/run/pid1-guard/armed" "$R/run/pid1-guard/root-identity" "$R/run/pid1-guard/root-contract.sh"
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
$BB cp "$WORK/cradio" "$R$RADIO_PATH"
$BB chmod 700 "$R$RADIO_PATH"
$BB grep -q 'RADIO_SHA=146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14' "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" || fail 'retained legacy post lost its radio pin'
$BB grep -q '113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3' "$R/hook-canonical" || fail 'retained legacy hook lost its post pin'
$BB grep -q '146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14' "$R/hook-canonical" || fail 'retained legacy hook lost its radio pin'
$BB grep -q 'sha256sum' "$R/hook-canonical" || fail 'retained legacy hook lost its digest check'
$BB chroot "$R" /real/busybox sh /hook-canonical && fail 'retained canonical gated hook launched edited radio'
[ ! -e "$R/tmp/hook-started" ] || fail 'retained canonical gated hook launch recorded with edited radio'
reset_post
run_post && fail 'canonical gated post accepted edited radio'
$BB grep -q 'pinned radio bring-up script missing' "$R/tmp/post.out" || fail 'canonical gated post refusal reason missing'
[ ! -e "$R/tmp/stages" ] || fail 'canonical gated post reached a stage with edited radio'
$BB cp "$WORK/cpost" "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
$BB cp "$WORK/chook" "$R/hook"
$BB chmod 700 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "$R/hook"
$BB grep -q 'RADIO_SHA=\|sha256sum\|omnipha-radio-snapshot\|radio_snapshot\|d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3' "$R/hook" && fail 'candidate hook retained a pin, digest or snapshot check'
$BB grep -q 'RADIO_SHA=\|omnipha-radio-snapshot\|radio_snapshot\|pinned radio bring-up script missing\|d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3' "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" && fail 'candidate post retained a radio pin, snapshot or digest refusal'
check_direct_launch() {
	run_post && fail 'candidate fixture unexpectedly completed the success gate'
	[ "$( $BB cat "$R/tmp/stages")" = 'modem
wpss
driver
scan
services' ] || fail 'edited radio did not reach all simulated stages'
	[ "$( $BB sort -u "$R/tmp/launch-paths")" = "$RADIO_PATH" ] || fail 'edited radio was not launched from its persistent path'
	$BB cmp -s "$R/tmp/launched-radio" "$WORK/cradio" || fail 'launched radio bytes differ from synthetic edited radio'
	[ ! -e "$R/run/radio-bringup/omnipha-radio-snapshot" ] && [ ! -L "$R/run/radio-bringup/omnipha-radio-snapshot" ] || fail 'candidate post created a radio snapshot'
	$BB grep -q 'omnipha-radio-snapshot\|refused radio snapshot\|d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3' "$R/tmp/post.out" && fail 'candidate post reported a snapshot or digest refusal'
	return 0
}
reset_post
$BB cp "$WORK/cradio" "$R$RADIO_PATH"
$BB chmod 644 "$R$RADIO_PATH"
check_direct_launch
reset_post
$BB cp "$WORK/cradio" "$R/tmp/synthetic-radio"
$BB chmod 600 "$R/tmp/synthetic-radio"
$BB rm -f "$R$RADIO_PATH"
$BB ln -s /tmp/synthetic-radio "$R$RADIO_PATH"
check_direct_launch
$BB rm -f "$R/tmp/hook-started"
$BB chmod 644 "$R/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh" "$R/tmp/synthetic-radio"
$BB chroot "$R" /real/busybox sh /hook
$BB sleep 1
[ -f "$R/tmp/hook-started" ] || fail 'candidate hook refused existing scripts because of mode or link'
$BB rm -f "$R/tmp/hook-started" "$R$RADIO_PATH"
$BB chroot "$R" /real/busybox sh /hook
$BB sleep 1
[ -f "$R/tmp/hook-started" ] || fail 'candidate hook performed a file test instead of launching post directly'
reset_post
run_post && fail 'candidate post succeeded without the persistent radio'
[ ! -e "$R/tmp/stages" ] || fail 'candidate post reached a stage without the persistent radio'
$BB chmod 600 "$R/run/pid1-guard/nonce"
[ "$( $BB cat "$R/run/pid1-guard/nonce")" = "$nonce" ] || fail 'guard nonce changed'
[ ! -e "$R/run/pid1-guard/ack" ] && [ ! -e "$R/run/pid1-guard/accepted" ] || fail 'guard acknowledgement changed'
printf 'pass: mocked fresh self-post ordering, nonce markers, priority-prefixed panel restore, refusal paths and pinned hook; no device\n'
printf 'pass: retained legacy hook and post still contain their old pins and refuse the synthetic edited radio; candidate post launches that radio directly from its persistent path\n'
printf 'scope: an already edited legacy hook is retained and its embedded old post pin still refuses the migrated post; proving the installed hook is that exact legacy file before the first candidate boot is coordinator preboot responsibility, not a candidate hook or host-fixture check\n'
printf 'limitation: radio stage execution is simulated by the busybox wrapper and is not device radio execution; no device was accessed; the launched bytes are the synthetic edit only, not a known-bad payload; this fixture does not prove radio safety, digest refusal, snapshot metadata or success-gate acknowledgement\n'
