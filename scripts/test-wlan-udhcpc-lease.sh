#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH='' cd -- "$HERE/.." && pwd)
IMAGE=${IMAGE:-$HOME/sm7635-build/out/init_boot-psoc-hold-wlan-node.img}
LEASE="$HERE/wlan-udhcpc-lease.sh"
WORK=$(mktemp -d /tmp/issue134-lease-tests.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

failures=0
run_lease() {
	IPLOG="$WORK/ip.log" IP_CMD="$WORK/ip" BUSYBOX="$WORK/busybox" \
		RESOLV_CONF="$WORK/resolv.conf" \
		qemu-aarch64 "$WORK/busybox" sh "$LEASE" "$1"
}

if ! command -v qemu-aarch64 >/dev/null 2>&1; then
	echo "FAIL: qemu-aarch64 not available on this host"
	exit 1
fi
if [ ! -f "$IMAGE" ]; then
	echo "FAIL: run-43 image not present at $IMAGE"
	exit 1
fi

python3 -B - "$ROOT" "$IMAGE" "$WORK/busybox" <<'PY'
import hashlib, importlib.util, pathlib, struct, sys
root, image_path, out = (pathlib.Path(a) for a in sys.argv[1:4])
spec = importlib.util.spec_from_file_location('closure', root / 'scripts/vendor-module-closure.py')
closure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closure)
image = image_path.read_bytes()
assert hashlib.sha256(image).hexdigest() == \
    '0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa', 'run-43 image hash changed'
size = struct.unpack_from('<I', image, 12)[0]
archive, _ = closure.unpack_legacy_lz4(image[4096:4096 + size], closure.lz4_library())
entries, _ = closure.parse_newc(archive, 'run-43 generic cpio')
busybox = next(e['data'] for e in entries if e['name'] == 'bin/busybox')
assert hashlib.sha256(busybox).hexdigest() == \
    'c2f279d1d5640a0f327890d41cad594c0f059f3fed3f96dd72fdcc4f5e18ec02', 'guest busybox hash changed'
out.write_bytes(busybox)
out.chmod(0o755)
PY

printf '#!/bin/sh\necho "ip $*" >> "$IPLOG"\n' > "$WORK/ip"
chmod +x "$WORK/ip"

: > "$WORK/ip.log"
interface=wlan0 ip=192.0.2.5 subnet=255.255.255.0 router=192.0.2.1 \
	dns="192.0.2.53 192.0.2.54" run_lease bound
grep -q '^ip addr flush dev wlan0$' "$WORK/ip.log" ||
	{ echo "FAIL: bound must flush wlan0 first"; failures=$((failures + 1)); }
grep -q '^ip addr add 192.0.2.5/24 dev wlan0$' "$WORK/ip.log" ||
	{ echo "FAIL: bound must add the leased /24 address"; failures=$((failures + 1)); }
grep -q '^ip route replace default via 192.0.2.1 dev wlan0$' "$WORK/ip.log" ||
	{ echo "FAIL: bound must install the default route"; failures=$((failures + 1)); }
[ "$(cat "$WORK/resolv.conf")" = "nameserver 192.0.2.53
nameserver 192.0.2.54" ] ||
	{ echo "FAIL: resolver must hold both nameservers"; failures=$((failures + 1)); }

: > "$WORK/ip.log"
interface=wlan0 run_lease deconfig
[ "$(cat "$WORK/ip.log")" = "ip addr flush dev wlan0" ] ||
	{ echo "FAIL: deconfig must only flush wlan0"; failures=$((failures + 1)); }

: > "$WORK/ip.log"
if interface=usb0 ip=192.0.2.5 subnet=255.255.255.0 run_lease bound 2>/dev/null; then
	echo "FAIL: a non-wlan0 interface must be rejected"; failures=$((failures + 1))
fi
[ ! -s "$WORK/ip.log" ] ||
	{ echo "FAIL: rejected interface must not invoke ip"; failures=$((failures + 1)); }

if interface=wlan0 run_lease bogus 2>/dev/null; then
	echo "FAIL: an unknown DHCP verb must be rejected"; failures=$((failures + 1))
fi

: > "$WORK/ip.log"
if interface=wlan0 run_lease bound 2>/dev/null; then
	echo "FAIL: bound without a lease must be rejected"; failures=$((failures + 1))
fi
[ ! -s "$WORK/ip.log" ] ||
	{ echo "FAIL: rejected bound must not invoke ip"; failures=$((failures + 1)); }

if [ "$failures" -ne 0 ]; then
	echo "FAIL: $failures lease-helper check(s) failed"
	exit 1
fi
echo "pass: wlan-udhcpc-lease.sh applies a synthetic lease via the guest BusyBox under QEMU"
echo "synthetic only: no device, interface, resolver, profile, flash or live lease"
