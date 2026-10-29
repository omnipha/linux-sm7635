---
date: 2026-10-26
run: 40
issue: omnipha/linux-sm7635#111
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Run 40 capture/recovery ordering gap (#111, host-only, 2026-10-26)

**Stop: neither proposed image ordering repair preserves bounded unattended
self-recovery if capture never becomes ready.** No successor image was built,
verified for flashing, or flashed; the psoc-idle discriminator remains untested.
The run-40 `0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7`
image and all earlier measured SHAs remain never-reflash. This is the issue's
explicit documented-gap outcome, not outcome (a), (b), (c), or a claim that the
single #109 WLAN hold failed. No physical device operation was performed for
#111.

### Evidence and ordering proof

- Run-40 host record at `~/phone-second-life-data/mb003/pstore/
  attempt-20261026-0043-initboot-psochold/record-run40.py:19-26`: the #109
  image was flashed once, key-only SSH first succeeded at uptime 120 s, but
  the device returned to fastboot before capture readiness or selftest. There
  was no guarded modem start, `/bin/wpss-once`, or `/dev/wlan` ON write. The
  separate capture check returned `ready: false`, `boot_id: null`
  (`stage7-capture-check.txt:1`); the host capture only began at 00:50:36
  (`capture/capture.log:1`), after the 00:47:05 reboot
  (`stage4-reboot-t0.txt:1`). Pstore contains the #109 marker and the expected
  early `wlan0 absent`, with no fatal line (`stage9-discriminator.txt:1-2`).
  The five-partition stock rollback and stock Android boot completion are
  recorded at `record-run40.py:21`. This is consistent with expiration of the
  untouched 150 s timer; it is not proof of a WLAN failure or a new kernel
  failure.
- The run-40 session init arms the background `sleep 150` immediately after
  `log 'starting'` and before the module phase; at expiry it tests for
  `/run/keep`, calls `/bin/restart2 bootloader` if absent, and falls back to
  `reboot -f` (`initramfs/init:27-40`, frozen timer constant at
  `scripts/build-init-boot-eud-softdep-payload.py:26,32-40`). `/run/keep` is
  deliberately not created by init: only a verified key-only SSH worker may
  create it after the host link and *fresh capture selftest* are proven (the
  #83 section below, "only after key-only SSH, the host link and the capture
  `selftest` are verified"); early-keep and disabled-timer fixtures at
  `scripts/verify-init-boot-live-fatal-stream.py:223-229`. The capture
  selftest itself waits for a new console marker sent over that boot's SSH
  connection, not for a preboot host-service state
  (`omnipha/agents/scripts/session-capture.py:211-251`); hence it cannot pass
  before this session has booted and armed the timer.
- **Keep before the timer window:** creating `/run/keep` in init before the
  timer, or setting it over SSH before the capture selftest, disables the only
  userspace recovery path even when capture never becomes ready. If the gate
  remains failed, the file persists until reboot and the timer's
  `if [ ! -e /run/keep ]` is false at expiry. This is unbounded, not a
  repair. The early/unconditional keep negative fixtures above reject it.
- **Arm only after the capture gate:** moving the 150 s timer into a
  post-selftest SSH action means it is never armed in the exact run-40 failure
  case (`ready: false`, no selftest); an unattended initramfs would then have
  no time bound to reach fastboot. Existing timer-placement fixtures reject
  moving it after even the module loop
  (`scripts/verify-init-boot-eud-softdep.py:159-163`). Moving it later but
  *before* the capture gate leaves the timer-before-gate race intact. A
  separate always-armed watchdog would be a new recovery mechanism, not one
  of the two ordering-only deltas requested by #111.

Starting host capture earlier, fixing the host route before reboot, or requiring
its service to be active preboot can reduce the run-40 setup delay, but cannot
establish the **fresh, boot-specific** capture selftest before the timer is
armed. Leaving the timer unchanged while trying that scheduling improvement
would preserve bounded recovery, but would not implement either requested
ordering repair or guarantee the selftest completes within 150 s (SSH first
arrived at uptime 120 s in run 40). It is not substituted for a vetted image
repair. The pinned vendor tree remains
NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`: the unchanged #109
`/dev/wlan` ON handler waits for driver load then stops the **separate** HDD
psoc-idle timer (`vendor/qcom/opensource/wlan/qcacld-3.0/core/hdd/src/
wlan_hdd_main.c:19163-19184,14132-14136`). That 25 s-capped one-shot WLAN
variable (`scripts/build-init-boot-psoc-hold-payload.py:39-84,111-128`)
never ran in run 40 and cannot repair the session's 150 s recovery gate.
The userspace timer also cannot recover a kernel panic (see the #83 section's
"The 150 s userspace timer does not cover the expected kernel panic"); this
gap makes no stronger recovery claim.

**Disposition:** do not flash `0b40ac34…` again and do not package a cosmetic
new SHA, move/disable the timer, plant early keep, or change the WPSS trigger.
A different, explicitly scoped and independently bounded capture/recovery
mechanism would require a new issue and proof; #111 stops at this host-only
ordering gap, with no physical session or rollback to perform.
