#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
RULE=$HERE/90-omnipha-usb-net.rules
HELPER=$HERE/omnipha-usb-addr
fail() { printf 'usb-readdress fixture: %s\n' "$*" >&2; exit 1; }
for tool in sudo unshare mount ip udevadm chmod chown grep mktemp; do
	command -v "$tool" >/dev/null 2>&1 || fail "missing $tool"
done
udevadm verify "$RULE" >/dev/null
if [ "${OMNIPHA_CHECK_INSTALLED:-0}" = 1 ]; then
	cmp -s "$RULE" /etc/udev/rules.d/90-omnipha-usb-net.rules || fail 'installed rule differs'
	cmp -s "$HELPER" /usr/local/sbin/omnipha-usb-addr || fail 'installed helper differs'
fi
grep -Fq 'ATTRS{manufacturer}=="omnipha"' "$RULE" || fail 'manufacturer ancestor match missing'
grep -Fq 'ATTRS{idVendor}=="18d1"' "$RULE" || fail 'vendor match missing'
grep -Fq 'ATTRS{idProduct}=="4ee2"' "$RULE" || fail 'product match missing'
grep -Fq 'RUN+="/usr/local/sbin/omnipha-usb-addr"' "$RULE" || fail 'existing helper not called'
if grep -Fq 'ATTR{../manufacturer}' "$RULE"; then fail 'net parent has no manufacturer'; fi
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/rules.d" "$work/class/net" "$work/drivers/cdc_ncm" "$work/drivers/cdc_ether" "$work/drivers/other"
probe_if=
for candidate in /sys/class/net/*; do
	if [ -r "$candidate/device/vendor" ]; then probe_if=${candidate##*/}; break; fi
done
[ -n "$probe_if" ] || fail 'no host net device with a device-level vendor attribute to probe udev ancestor matching'
cat >"$work/rules.d/10-ancestor.rules" <<EOF
SUBSYSTEM=="net", KERNEL=="$probe_if", ATTR{../vendor}=="?*", ENV{OMNIPHA_UP1}="1"
SUBSYSTEM=="net", KERNEL=="$probe_if", ATTRS{vendor}=="?*", ENV{OMNIPHA_ATTRS}="1"
EOF
probe=$(udevadm test -a add -D "$work/rules.d" "/sys/class/net/$probe_if" 2>&1 || true)
printf '%s\n' "$probe" | grep -Fq 'OMNIPHA_ATTRS=1' || fail 'ATTRS did not match ancestor attribute'
if printf '%s\n' "$probe" | grep -Fq 'OMNIPHA_UP1=1'; then fail 'ATTR{../...} unexpectedly matched net directory'; fi
for pair in 'enxnew cdc_ncm gadget' 'enxether cdc_ether gadget' 'enxunrelated other gadget' 'enxforeign cdc_ncm foreign'; do
	set -- $pair
	name=$1 driver=$2 parent=$3
	mkdir -p "$work/devices/$parent/$name/net/$name"
	ln -s "$work/devices/$parent/$name/net/$name" "$work/class/net/$name"
	ln -s "$work/devices/$parent/$name" "$work/devices/$parent/$name/net/$name/device"
	ln -s "$work/drivers/$driver" "$work/devices/$parent/$name/driver"
done
printf '18d1\n' >"$work/devices/gadget/idVendor"
printf '4ee2\n' >"$work/devices/gadget/idProduct"
printf 'omnipha\n' >"$work/devices/gadget/manufacturer"
printf '1234\n' >"$work/devices/foreign/idVendor"
printf '5678\n' >"$work/devices/foreign/idProduct"
printf 'other\n' >"$work/devices/foreign/manufacturer"
[ ! -e "$work/class/net/enxnew/../manufacturer" ] || fail 'net parent unexpectedly has manufacturer'
[ -f "$work/class/net/enxnew/device/../manufacturer" ] || fail 'USB ancestor missing manufacturer'
chmod 755 "$HELPER"
OBSERVER=$HERE/observe-usb-addr.sh
chmod 755 "$HELPER" "$OBSERVER"
OMNIPHA_FIXTURE_ROOT=$work OMNIPHA_FIXTURE_HELPER=$HELPER OMNIPHA_FIXTURE_OBSERVER=$OBSERVER \
	sudo -n --preserve-env=OMNIPHA_FIXTURE_ROOT,OMNIPHA_FIXTURE_HELPER,OMNIPHA_FIXTURE_OBSERVER unshare -mn sh -eu -c '
	mount --make-rprivate /
	ip link add enxnew type dummy
	ip link add enxether type dummy
	ip link add enxunrelated type dummy
	ip link add enxforeign type dummy
	mount --bind "$OMNIPHA_FIXTURE_ROOT/class/net" /sys/class/net
	export OMNIPHA_USB_LOG="$OMNIPHA_FIXTURE_ROOT/record.log"
	OMNIPHA_OBSERVE_LOG="$OMNIPHA_FIXTURE_ROOT/observe.log" OMNIPHA_OBSERVE_SECONDS=151 \
		sh "$OMNIPHA_FIXTURE_OBSERVER" >/dev/null &
	observer=$!
	sleep 2
	sh "$OMNIPHA_FIXTURE_HELPER"
	ip -4 -o addr show dev enxnew | grep -Fq " 172.16.42.1/24 "
	ip -4 -o addr show dev enxether | grep -Fq " 172.16.43.1/24 "
	! ip -4 -o addr show dev enxunrelated | grep -q " inet "
	! ip -4 -o addr show dev enxforeign | grep -q " inet "
	sleep 2
	ip addr del 172.16.43.1/24 dev enxether
	wait "$observer"
	ip -4 -o addr show dev enxnew | grep -Fq " 172.16.42.1/24 "
	sh "$OMNIPHA_FIXTURE_HELPER"
	ip -4 -o addr show dev enxether | grep -Fq " 172.16.43.1/24 "
	! ip -4 -o addr show dev enxunrelated | grep -q " inet "
	! ip -4 -o addr show dev enxforeign | grep -q " inet "
'
sudo -n chown "$(id -u):$(id -g)" "$work/record.log" "$work/observe.log"
grep -Fq 'add interface=enxnew driver=cdc_ncm address=172.16.42.1/24 result=added' "$work/record.log" || fail 'missing NCM add record'
grep -Fq 'add interface=enxether driver=cdc_ether address=172.16.43.1/24 result=added' "$work/record.log" || fail 'missing ECM add record'
grep -Fq 'keep interface=enxnew driver=cdc_ncm address=172.16.42.1/24 result=already-present' "$work/record.log" || fail 'second run did not find the NCM address kept'
grep -Fq 'skip interface=enxforeign driver=cdc_ncm result=not-gadget' "$work/record.log" || fail 'foreign cdc_ncm not skipped'
grep -Fq 'interface=enxnew helper_ran=yes address_added=yes removed=no' "$work/observe.log" || fail 'observer did not record the kept NCM address'
grep -Fq 'interface=enxether helper_ran=yes address_added=yes removed=yes' "$work/observe.log" || fail 'observer did not record the removed ECM address'
if grep -Fq 'enxunrelated' "$work/record.log" "$work/observe.log"; then fail 'unrelated driver recorded'; fi
if grep -Fq 'enxforeign' "$work/observe.log"; then fail 'foreign identity observed as the gadget'; fi
printf 'usb-readdress fixture: address landed on enxnew and stayed; removal recorded; unrelated interfaces unclaimed\n'
