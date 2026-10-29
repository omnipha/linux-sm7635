---
date: 2026-10-29
run: 56
issue: omnipha/linux-sm7635#150
subsystem: wlan
result: inconclusive
source: README.md
---
## Run-56 post-cutover WLAN association and reachability (2026-10-29, #150)

[BOOT.md](BOOT.md#run-56-measured-post-cutover-wlan-association-and-reachability-on-postmarketos-pid-1-150-live-session-finding-2026-10-29)
records one coordinator-held stock-kernel session on the unchanged `fef03008…`
image. On the RAM-backed postmarketOS PID 1 the merged `scripts/pmos-radio-bringup.sh`
brought up the modem (no EFS fatal), WPSS, `/dev/wlan` and `wlan0`; a scan saw 44
BSS; the designated host-local profile associated (`COMPLETED` plus a connected
`iw link`) and DHCP, gateway (3/3), DNS and external reachability (3/3, repeated)
each succeeded. Capture stayed clean. Two hand-start pitfalls (no `-f` in the
Alpine supplicant, `IP_CMD=/sbin/ip` for the lease helper) are recorded. This is
in-session connectivity only, with the supplicant and DHCP started by hand; OpenRC
`networking`/`wpa_supplicant` services, persistence and release images remain
separate. Coordinator rollback and Android proof are pending.
