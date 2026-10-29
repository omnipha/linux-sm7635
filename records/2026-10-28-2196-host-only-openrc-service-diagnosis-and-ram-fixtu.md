---
date: 2026-10-28
issue: omnipha/linux-sm7635#149
subsystem: userspace
result: inconclusive
source: README.md
---
## Host-only OpenRC service diagnosis and RAM fixture (2026-10-28, #149)

[BOOT.md](BOOT.md#host-only-openrc-runlevel-inventory-and-minimal-ram-only-defaultlocal-fixture-149-2026-10-28)
traces run-52's empty `default` runlevel to `apk.static --no-scripts` in the
134-APK `7a76a110…` public archive: 67 OpenRC service scripts were present,
but no runlevel was enabled. The #145 stage supplied BusyBox `/sbin/init` and
its three-line OpenRC inittab without populating a runlevel; run 52 reached
`softlevel=default` with 0 services started and 0 failed, not an init failure.
A minimal RAM-only stage now enables only `default/local`, after rejecting any
pre-enabled runlevel, missing `local` script/configuration or unexpected startup
hook. `scripts/test-alpine-session.sh` checks the pinned hook/service inventory
and negative inputs; `scripts/test-pmos-session-dev.sh` tests the actual OpenRC
`sysinit` → `boot` → `default` sequence with `local` started and rejects the
missing network/deviceinfo and incompatible guest `/dev` prerequisites in
isolated host namespaces. The archive, image, pinned transition/guard, inittab,
USB control, key-only SSH and guest-private `/dev` remain unchanged. This is a
host fixture only; device service/WLAN startup after cutover and USB continuity
with the new runlevel remain unmeasured and require a separate issue/session.
