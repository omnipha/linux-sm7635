---
date: 2026-10-29
issue: omnipha/linux-sm7635#176
subsystem: userspace
result: inconclusive
source: records/
---
## Lean-file note: duplicate records for runs 55-58

The one-time migration left two records per run. The older files
(`records/2026-10-29-2200` through `2205`) are README pointers and mark the
same runs `inconclusive`. The later files (`2290`, `2292`, `2294`, `2297`)
are the measured BOOT sections and mark them `confirmed`.

Existing records stay unchanged. Read the later file for each run:

- run 55: `records/2026-10-29-2290-run-55-measured-post-cutover-modem-hold-past-the.md`
- run 56: `records/2026-10-29-2292-run-56-measured-post-cutover-wlan-association-an.md`
- run 57: `records/2026-10-29-2294-run-57-measured-openrc-wpa-supplicant-and-networ.md`
- run 58: `records/2026-10-29-2297-run-58-first-boot-self-stage-and-wlan-associatio.md`

`status.yaml` now names the subsystem `wlan` and lists the measured SHAs that
must not be reflashed. `PLAN.md` records that the host part of #169 is merged
in PR #170. `docs/boot-image.md` points at `INDEX.md` and `records/` instead
of BOOT.md.
