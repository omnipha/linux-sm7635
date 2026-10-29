---
date: 2026-10-26
issue: omnipha/linux-sm7635#124
subsystem: wlan
result: inconclusive
source: README.md
---
## Fail-closed /dev/wlan node for the registered char device (2026-10-26, #124)

`scripts/build-init-boot-psoc-hold-wlan-node.sh` derives a new distinct-SHA
image from the measured `8b62520f…` run-42 #120 image with exactly one init
phase, after the WLAN closure and before console ready. It reads the live
`/sys/class/wlan/wlan/dev` numeric major:minor, requires the major to match the
single `qcwlanstate` character-device major in `/proc/devices`, then creates
`/dev/wlan` mode 0600 with a bounded `mknod` and verifies its exact character
major:minor. On any failure it logs the reason, leaves no node and attempts
nothing further. `bin/wpss-once` stays byte-exact, including the fail-closed
`/dev/wlan` exit-9 precheck; init itself never starts the helper. The builder
requires two serial byte-identical images; the verifier is wired into
`scripts/verify-bootimg.sh` and rejects missing, hardcoded or misplaced node
steps, all earlier SHAs and regressions of the #120 invariant. Full SHA and the
three predicted outcomes for a separately authorized single-variable physical
session are in [BOOT.md](BOOT.md). Host-only; no device result or flash
permission.
