---
date: 2026-10-29
issue: omnipha/linux-sm7635#160
subsystem: userspace
result: inconclusive
source: README.md
---
## OpenRC `networking` + `wpa_supplicant` staging (2026-10-29, #160)

[BOOT.md](BOOT.md#host-only-openrc-networking--wpa_supplicant-staging-on-the-unchanged-session-image-160-2026-10-29)
records the host-only `services` stage of `scripts/pmos-radio-bringup.sh`. Using the
unchanged `fef03008…` image, it stages a root-only `/etc/network/interfaces`, the
profile from standard input at `/etc/wpa_supplicant/wpa_supplicant.conf` (guest RAM,
never in Git or logs) and a `wlan0`-only `ifquery` wrapper, enables only
`wpa_supplicant` and `networking`, and starts them with `rc-service -D`. It refuses
other enabled services, a missing profile, a changed supplicant argument list or
`/bin/ip`, and a repeat in the same boot. `sh scripts/test-pmos-radio-bringup.sh` and
`sh scripts/test-pmos-session-dev.sh` cover it. Nothing here is a phone result; the
services on the real post-cutover WLAN path are one pending coordinator-held
measurement, and #160 stays open for it.
