---
date: 2026-10-29
issue: omnipha/linux-sm7635#171
subsystem: userspace
result: inconclusive
source: README.md
---
## Host-only `recovery_b` self-stage carrier (2026-10-29, #171)

[BOOT.md](BOOT.md#host-only-recovery_b-self-stage-payload-and-init-171-2026-10-29)
records the distinct host-built pair for the second-boot measurement. `recovery_b` (104,857,600 bytes) is the first approved carrier after `vendor_boot_b` that holds the unchanged payload layout, so `userdata` is not wiped. `scripts/build-recovery-b-userspace-payload.sh` writes the pinned archive and header into stock `recovery_b` between its signed prefix and `AVBf` footer; `scripts/pmos-self-stage.sh` differs from the measured script only in the carrier name and size, and `scripts/build-init-boot-self-stage.sh` rebuilds `init_boot` with it. The verifiers refuse the run-58 pair (`4b83ea24…`, `1bdb7c22…`), `fef03008…`, stock images and marker-only deltas. Guards and timing are unchanged. Not a phone result; #171 stays open for the coordinator-held measurement.
