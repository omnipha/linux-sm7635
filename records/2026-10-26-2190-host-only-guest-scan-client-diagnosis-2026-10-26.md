---
date: 2026-10-26
issue: omnipha/linux-sm7635#132
subsystem: wlan
result: inconclusive
source: README.md
---
## Host-only guest scan-client diagnosis (2026-10-26, #132)

[BOOT.md](BOOT.md#run-46-guest-scan-client-diagnosis-132-host-only-2026-10-26)
separates the measured run-46 link-up fallback from a reproducible host
inventory of the unchanged run-43 image, stock ramdisks and read-only
`vendor_a` mount. The BusyBox `iw` applet and standalone `iw` are absent;
Android `/vendor` Wi-Fi binaries are present but not directly usable without
the Android runtime/services. It identifies an independently packaged arm64
`iw` with musl/libnl dependencies and a separate, authorization-gated
RAM-only delivery option; no scan, new image or device operation is performed.
