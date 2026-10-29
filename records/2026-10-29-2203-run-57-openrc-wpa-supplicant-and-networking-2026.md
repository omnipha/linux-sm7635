---
date: 2026-10-29
run: 57
issue: omnipha/linux-sm7635#160
subsystem: userspace
result: inconclusive
source: README.md
---
## Run-57 OpenRC `wpa_supplicant` and `networking` (2026-10-29, #160)

[BOOT.md](BOOT.md#run-57-measured-openrc-wpa_supplicant-and-networking-on-postmarketos-pid-1-160-live-session-finding-2026-10-29)
records one coordinator-held stock-kernel session on the unchanged `fef03008…`
image. On the RAM-backed postmarketOS PID 1 the merged `scripts/pmos-radio-bringup.sh`
brought up the modem (no EFS fatal), WPSS, `/dev/wlan` and `wlan0`, and a scan saw
40 BSS. The first `rc-service -D wpa_supplicant start` chose `p2p0` instead of
`wlan0`, so `networking` found no lease and stayed stopped. Setting
`wpa_supplicant_if="wlan0"` in the RAM-only `conf.d` and starting both services
through OpenRC again associated (`COMPLETED` plus a connected `iw link`) and DHCP,
gateway (3/3), DNS and external reachability (3/3, repeated) each succeeded.
Capture stayed clean. This is in-session connectivity only; reboot autoconnect,
persistence and release images remain separate. Coordinator rollback and Android
proof are pending, and the `p2p0` interface selection is the next host-script fix.
