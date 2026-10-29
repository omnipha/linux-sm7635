#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
fail() { printf 'reboot-hold fixture: %s\n' "$*" >&2; exit 1; }
if [ "${1:-}" != --inner ]; then
	[ "$#" -eq 0 ] || fail 'usage: test-pmos-reboot-hold.sh'
	for tool in python3 sudo unshare timeout ssh ssh-keygen busybox; do
		command -v "$tool" >/dev/null 2>&1 || fail "missing $tool"
	done
	[ -x /usr/sbin/sshd ] || fail 'missing sshd'
	sudo -n true || fail 'passwordless sudo required'
	sudo -n timeout -k 2 90 unshare --mount --pid --net --fork --kill-child --mount-proc \
		env HERE="$HERE" /bin/busybox sh "$0" --inner || fail 'isolated reboot-hold fixture'
	exit 0
fi

BB=/bin/busybox
[ "$$" = 1 ] && $BB readlink /proc/1/exe | $BB grep -q busybox || fail 'PID 1 is not BusyBox'
$BB mount --make-rprivate /
$BB mount -t tmpfs -o mode=0700,size=32m tmpfs /run
$BB mount -t tmpfs -o mode=0700,size=4m tmpfs /root
$BB mkdir -p /root/.ssh /run/sshd /run/capture/capture /run/bin
$BB chmod 700 /root /root/.ssh /run/capture /run/capture/capture
OLD=11111111-1111-4111-8111-111111111111
NEW=22222222-2222-4222-8222-222222222222
OTHER=33333333-3333-4333-8333-333333333333
$BB printf '%s\n' "$NEW" >/run/boot_id
$BB printf '28.00 28.00\n' >/run/uptime
$BB mount --bind /run/boot_id /proc/sys/kernel/random/boot_id
$BB mount --bind /run/uptime /proc/uptime
ip link set lo up
ip addr add 172.16.42.2/32 dev lo

ssh-keygen -q -t ed25519 -N '' -f /run/host_key
ssh-keygen -q -t ed25519 -N '' -f /run/wrong_host_key
ssh-keygen -q -t ed25519 -N '' -f /run/client_key
ssh-keygen -q -t ed25519 -N '' -f /run/stale_key
$BB cp /run/client_key.pub /root/.ssh/authorized_keys
$BB awk '{print "[172.16.42.2]:22 " $1 " " $2}' /run/host_key.pub >/run/known_hosts_22
$BB awk '{print "172.16.42.2 " $1 " " $2}' /run/host_key.pub >/run/known_hosts_bare
$BB awk '{print "[172.16.42.2]:22 " $1 " " $2}' /run/wrong_host_key.pub >/run/wrong_known_hosts
$BB awk '{print "[172.16.42.2]:2222 " $1 " " $2}' /run/host_key.pub >/run/known_hosts_2222
$BB chmod 600 /root/.ssh/authorized_keys /run/client_key /run/stale_key \
	/run/known_hosts_22 /run/known_hosts_bare /run/wrong_known_hosts /run/known_hosts_2222

$BB cat >/run/sshd_config <<'CFG'
Port 22
ListenAddress 172.16.42.2
HostKey /run/host_key
PidFile /run/sshd.pid
AuthorizedKeysFile /root/.ssh/authorized_keys
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
StrictModes yes
PrintMotd no
Subsystem sftp internal-sftp
CFG
/usr/sbin/sshd -f /run/sshd_config -E /run/sshd.log
n=0
until $BB awk '$2 == "022A10AC:0016" && $4 == "0A" {c++} END {exit(c != 1)}' /proc/net/tcp; do
	[ "$n" -lt 50 ] || fail 'diagnostic :22 listener did not start'
	$BB sleep 0.1
	n=$((n + 1))
done
! $BB awk '$2 == "022A10AC:08AE" && $4 == "0A" {c++} END {exit(c == 0)}' /proc/net/tcp || fail ':2222 unexpectedly listening'

REAL_SSH=$(command -v ssh)
$BB cat >/run/bin/ssh <<EOF
#!/bin/busybox sh
/bin/busybox printf '%s\n' "\$*" >> /run/ssh.calls
exec "$REAL_SSH" "\$@"
EOF
$BB chmod 700 /run/bin/ssh
export PATH="/run/bin:$PATH"

$BB cat >/run/capture-tool.py <<'PY'
import json
import pathlib
import sys
cap = pathlib.Path(sys.argv[2]) / "capture"
if sys.argv[1] != "check" or (cap / "STOP").exists() or not (cap / "capture.pid").exists():
    raise SystemExit(1)
ready = json.loads((cap / "ready.json").read_text())
print(json.dumps({"ready": True, "boot_id": ready["boot_id"]}))
PY
$BB printf '%s\n' "$$" >/run/capture/capture/capture.pid
$BB printf '\n# connected fixture boot_id=%s\n\n# connected fixture boot_id=%s\n' "$OLD" "$NEW" >/run/capture/capture/kmsg.log

HELPER=$HERE/pmos-reboot-hold.sh
export REBOOT_HOLD_PRE_BOOT_ID=$OLD
export REBOOT_HOLD_CAPTURE_DIR=/run/capture
export REBOOT_HOLD_CAPTURE_TOOL=/run/capture-tool.py

reset() {
	$BB rm -f /run/keep /run/capture/capture/STOP
	$BB printf '%s\n' "$NEW" >/run/boot_id
	$BB printf '28.00 28.00\n' >/run/uptime
	$BB printf '{"ready":true,"boot_id":"%s"}\n' "$NEW" >/run/capture/capture/ready.json
	: >/run/ssh.calls
}
reject() {
	label=$1
	target=$2
	hosts=$3
	key=$4
	if sh "$HELPER" "$target" "$hosts" "$key" >/run/reject.out 2>&1; then
		fail "$label accepted"
	fi
	if [ "$label" = symlink-hold ]; then
		[ -L /run/keep ] || fail 'symlink negative was replaced'
	else
		[ ! -e /run/keep ] && [ ! -L /run/keep ] || fail "$label created /run/keep"
	fi
	! $BB grep -qE '(:2222|-p 2222)' /run/ssh.calls /run/reject.out || fail "$label referenced :2222"
	! $BB grep -qF PRIVATE /run/reject.out || fail "$label leaked key material"
	printf 'rejected: %s\n' "$label"
}

reset
sh "$HELPER" "$NEW" /run/known_hosts_22 /run/client_key >/run/accept.out
[ -f /run/keep ] && [ ! -L /run/keep ] && [ "$($BB stat -c '%u:%a' /run/keep)" = 0:600 ] || fail 'positive hold invalid'
! $BB grep -qE '(:2222|-p 2222)' /run/ssh.calls /run/accept.out || fail 'positive helper used :2222'
! $BB grep -qF PRIVATE /run/accept.out || fail 'positive helper leaked key material'
sh "$HELPER" "$NEW" /run/known_hosts_22 /run/client_key >/dev/null 2>&1 && fail 'existing hold accepted'
reset
sh "$HELPER" "$NEW" /run/known_hosts_bare /run/client_key >/dev/null || fail 'bare 172.16.42.2 known_hosts rejected'
[ -f /run/keep ] && [ ! -L /run/keep ] && [ "$($BB stat -c '%u:%a' /run/keep)" = 0:600 ] || fail 'bare known_hosts hold invalid'

wait_snippet=$($BB sed -n '/^wait_n=0$/,/^log "diagnostic hold and :22 verified on boot \$boot"$/p' "$HERE/pmos-self-stage.sh")
[ "$($BB printf '%s\n' "$wait_snippet" | $BB wc -l)" = 14 ] || fail 'self-stage wait loop changed'
(
	boot=$NEW
	log() { $BB printf '%s\n' "$*" >/run/stage.log; }
	die() { exit 1; }
	eval "$wait_snippet"
) || fail 'pinned self-stage wait loop did not pass with the helper hold inside 145 s'
$BB grep -qF "diagnostic hold and :22 verified on boot $NEW" /run/stage.log || fail 'self-stage verification log missing'
printf 'accepted: hold created over real :22 SSH at simulated 28 s; self-stage wait passes with no :2222 listener\n'

reset
$BB printf '%s\n' "$OTHER" >/run/boot_id
reject wrong-boot "$NEW" /run/known_hosts_22 /run/client_key

reset
$BB printf '%s\n' "$OLD" >/run/boot_id
reject boot-still-pre-reboot "$NEW" /run/known_hosts_22 /run/client_key

reset
reject expected-is-pre-reboot "$OLD" /run/known_hosts_22 /run/client_key
[ ! -s /run/ssh.calls ] || fail 'pre-reboot expected ID contacted SSH'

reset
reject stale-client-key "$NEW" /run/known_hosts_22 /run/stale_key

reset
reject wrong-host-key "$NEW" /run/wrong_known_hosts /run/client_key

reset
reject port-2222-known-hosts "$NEW" /run/known_hosts_2222 /run/client_key
[ ! -s /run/ssh.calls ] || fail ':2222 known_hosts contacted SSH'

reset
$BB ln -s /run/missing /run/keep
reject symlink-hold "$NEW" /run/known_hosts_22 /run/client_key

reset
$BB printf '145.00 145.00\n' >/run/uptime
reject late-helper "$NEW" /run/known_hosts_22 /run/client_key
(
	boot=$NEW
	log() { :; }
	die() { $BB printf '%s\n' "$*" >/run/late-stage.log; exit 1; }
	eval "$wait_snippet"
) && fail 'self-stage wait passed at 145 s without a hold'
$BB grep -qF 'diagnostic hold not set before self-recovery deadline' /run/late-stage.log || fail 'late self-stage reason'

reset
(
	unset REBOOT_HOLD_PRE_BOOT_ID
	sh "$HELPER" "$NEW" /run/known_hosts_22 /run/client_key >/run/derived.out 2>&1
) || fail 'pre-reboot boot was not derived from the capture history'
[ -f /run/keep ] && [ ! -L /run/keep ] || fail 'derived pre-reboot hold absent'
reset
(
	unset REBOOT_HOLD_PRE_BOOT_ID
	sh "$HELPER" "$OLD" /run/known_hosts_22 /run/client_key >/run/derived.out 2>&1
) && fail 'derived pre-reboot boot accepted'
$BB grep -qF 'still the pre-reboot boot' /run/derived.out || fail 'derived pre-reboot reason'
[ ! -s /run/ssh.calls ] || fail 'derived pre-reboot rejection contacted SSH'
printf 'rejected: derived pre-reboot boot from capture history\n'

reset
$BB printf '{"ready":true,"boot_id":"%s"}\n' "$OLD" >/run/capture/capture/ready.json
(
	export REBOOT_HOLD_ARM_SECONDS=3
	sh "$HELPER" --arm /run/known_hosts_22 /run/client_key >/run/arm.out 2>&1 &
	arm=$!
	$BB sleep 1
	$BB printf '{"ready":true,"boot_id":"%s"}\n' "$NEW" >/run/capture/capture/ready.json
	wait "$arm"
) || fail 'armed helper did not hold the fresh boot'
[ -f /run/keep ] && [ ! -L /run/keep ] && [ "$($BB stat -c '%u:%a' /run/keep)" = 0:600 ] || fail 'armed hold invalid'
! $BB grep -qE '(:2222|-p 2222)' /run/ssh.calls /run/arm.out || fail 'armed helper used :2222'
$BB grep -qF "reboot-hold: root-only /run/keep created on boot $NEW" /run/arm.out || fail 'armed helper did not name the fresh boot'
printf 'accepted: helper armed on the pre-reboot boot creates the hold after the fresh boot appears\n'

reset
$BB printf '{"ready":true,"boot_id":"%s"}\n' "$OLD" >/run/capture/capture/ready.json
reject stale-capture "$NEW" /run/known_hosts_22 /run/client_key
[ ! -s /run/ssh.calls ] || fail 'stale capture contacted SSH'

reset
: >/run/capture/capture/STOP
reject stopped-capture "$NEW" /run/known_hosts_22 /run/client_key
[ ! -s /run/ssh.calls ] || fail 'stopped capture contacted SSH'

$BB kill "$($BB cat /run/sshd.pid)" 2>/dev/null || true
printf 'pass: real OpenSSH :22 reboot-hold fixture; hold inside 145 s, wrong/pre-reboot boot, stale client/host key, :2222 pin, symlink hold, late helper, and stale/stopped capture all fail closed; no :2222 wait\n'
