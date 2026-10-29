---
date: 2026-10-25
issue: omnipha/linux-sm7635#83
subsystem: boot
result: inconclusive
source: README.md
---
## Capture-gated retry session init_boot (2026-10-25, #83)

`scripts/build-init-boot-retry-marker.sh` packages exactly one host-only session
init_boot: the byte-exact measured #81 init (`ae2ccff7`) with only the session
marker reworded to the single #83 capture-gated retry log, after the armed 150 s
self-recovery timer and before the module phase. That one string change forces a
SHA-256 distinct from the measured `ae2ccff7` image of run 33 and from every
other measured SHA. The boot init starts no remoteproc, never creates
`/run/keep`, and adds no `rmmod` or reload; the supplier phase and order, the
bounded WPSS/icnss2 bind gate, the read-only mounts, the single stock WLAN load,
the module closures, the RESTART2 helper and the USB/key-only SSH path are
unchanged. Run 33 lost the fatal text because capture readiness was never proven
before the guarded start, so the coordinator runs the merged capture tooling's
`selftest --marker ... --timeout` until a live console line reaches the host
capture before the one guarded `remoteproc2` start. The 150 s userspace timer
does not cover the expected kernel panic.
`scripts/verify-init-boot-retry-marker.py` fails closed and proves the decoded
`/init` delta against the rebuilt `ae2ccff7` image is exactly the marker string;
its negative fixtures reject a missing, duplicated, moved, reworded or renumbered
marker, the reused #81 and #79 marker texts, the rebuilt measured `ae2ccff7`
image and its SHA, early keep, an init-time remoteproc start, the reused
#75/#77/#79/#81 inits, timer regressions, `rmmod`/`modprobe` and every reused
measured SHA including `ae2ccff7`, plus a host-only simulated-clock timer test,
and it is wired into `scripts/verify-bootimg.sh`. The reproducible image and the
predicted outcomes are recorded in [BOOT.md](BOOT.md). No physical boot, `wlan0`,
modem or fatal text is claimed.
