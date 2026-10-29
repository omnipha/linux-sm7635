---
date: 2026-10-28
issue: omnipha/linux-sm7635#150
subsystem: boot
result: inconclusive
source: README.md
---
## Post-cutover `default/local` host fixture and reuse review (2026-10-28, #150)

[BOOT.md](BOOT.md#host-only-review-and-reuse-gate-for-post-cutover-defaultlocal-and-radio-diagnosis-150-2026-10-28)
records the host-only preparation for the #150 coordinator-held session. The
live `device-op.py` reuse rule leaves the unchanged #145 `init_boot_a` candidate
`fef03008…` as the only reusable changed image, and #151 changes only a script
staged over SSH into RAM, so no new image is built. `sh scripts/test-pmos-pid1.sh`
now stages the #151 `default/local` link into its isolated BusyBox `switch_root`
fixture, runs OpenRC `sysinit` → `boot` → `default` in the switched root and
asserts `local` started with nothing crashed, across the ack, timeout,
preplanted and symlinked guard cases. This is a host fixture only; on-device
`local` startup, radio state and WLAN after cutover remain unmeasured and #150
stays open for the coordinator-held session.
