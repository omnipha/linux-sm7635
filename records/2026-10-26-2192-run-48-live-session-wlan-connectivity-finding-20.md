---
date: 2026-10-26
run: 48
issue: omnipha/linux-sm7635#137
subsystem: wlan
result: confirmed
source: README.md
---
## Run-48 live-session WLAN connectivity finding (2026-10-26, #137)

[BOOT.md](BOOT.md#run-48-measured-guest-wlan-connectivity-in-one-held-session-137-live-session-finding-2026-10-26)
records a measured stock-kernel guest WLAN chain in one pinned-key, captured USB-SSH
session on the unchanged run-43 image: one guarded modem start and one WPSS
trigger reached FW ready and `wlan0`; `iw` scanned after IFF_UP (exit 0, 20
BSS), with the complete raw scan and boot ID retained privately outside Git.
The protected target matched 7 BSS privately. `wpa_supplicant` reached
`COMPLETED` with a connected `iw link`; bounded `udhcpc` applied an IPv4 lease,
default route and DNS; bounded gateway ping (3/3), DNS lookup and external
ping (3/3) each succeeded. Continuous capture stayed live with no new
fatal/crash/idle callback across the chain. This proves in-session WLAN
connectivity, not autoconnect after reboot. The coordinator still owns the
pending stock `init_boot_a` restore, five-hash proof, pstore preservation and
stock Android verification; #137 remains OPEN until that closure is recorded.
