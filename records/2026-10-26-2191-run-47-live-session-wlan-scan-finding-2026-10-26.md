---
date: 2026-10-26
run: 47
issue: omnipha/linux-sm7635#134
subsystem: wlan
result: confirmed
source: README.md
---
## Run-47 live-session WLAN scan finding (2026-10-26, #134)

[BOOT.md](BOOT.md#run-47-measured-guest-scan-success-association-unmeasured-134-live-session-finding-2026-10-26)
records a measured guest `iw` scan success in one held, captured, pinned-key SSH
session on the unchanged run-43 image. The first scan returned `-ENETDOWN`
(exit 156) because `wlan0` was administratively down (flags `0x1002`); after one
safe link-up (flags `0x1003`), one 20 s-bounded retry returned exit 0 with 17 BSS
(10 at 2.4 GHz, 7 at 5 GHz) and zero new fatal/crash/idle capture lines. The
worker did not inspect SSIDs/BSSIDs or touch a profile. This proves the stock
nl80211 driver serves scans, **not** target visibility, association, DHCP or
network access. Run 47 later returned to verified five-partition stock and
#134 was closed as superseded by #137. The earlier host-only [handoff plan](BOOT.md#planned-live-session-wlan-handoff-scan-through-connectivity-134-host-only-2026-10-26)
prepares one bounded, coordinator-owned live-session handoff on the **unchanged**
run-43 image (`0f998e29…`) from the #132 inventory. It host-verifies the cached
Alpine v3.21 aarch64 bundle (`iw`/`wpa_supplicant`/`wpa_cli` + musl/libnl): APK
and per-file SHA-256, the musl interpreter and dependency closure, and QEMU smoke
loads through the bundled loader (`iw version 6.9`, `wpa_supplicant v2.10`, exit 0)
— proving **loading only**, not a guest scan. It inventories guest DHCP tooling
without touching a WLAN profile (`udhcpc` present; run-43 cpio ships **no**
`/etc/udhcpc/default.script`, so the hash-checked, synthetic-tested lease helper
is transferred into RAM). The host-only plan documents fail-closed preboot
readiness for the protected profile/client/DHCP without printing secrets, plus
root-only RAM transfer, a 20 s-bounded scan and conditional bounded
association/address/reachability with per-stage stop rules. The new measured
scan above is a separate live result; it does **not** close #134 until the
coordinator records the remaining per-stage outcome and verified rollback.
