---
date: 2026-10-25
issue: omnipha/linux-sm7635#101
subsystem: wlan
result: inconclusive
source: README.md
---
## One-shot WPSS firmware boot init_boot (2026-10-25, #101)

`scripts/build-init-boot-wpss-boot.sh` derives a distinct image from the measured
#96 session without changing its init or services; only a dormant, coordinator-
invoked `/bin/wpss-once` helper is added. It checks the modem/DMS session's
stock prerequisites and performs one bounded stock `wpss_boot=1` write after
modem hold and DMS connection are confirmed by the physical coordinator.
`scripts/verify-init-boot-wpss-boot.py`, wired into `scripts/verify-bootimg.sh`,
proves the exact cpio delta, signed envelope and new SHA with negative fixtures.
The full hash, trigger spec and predicted outcomes are in [BOOT.md](BOOT.md).
Host-only; not a physical result.
