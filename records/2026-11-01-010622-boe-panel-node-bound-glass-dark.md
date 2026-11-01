---
date: 2026-11-01
issue: omnipha/linux-sm7635#248
subsystem: display
result: refuted
run: 87
---
# BOE node selected and bound, glass stays dark: node selection refuted

Physical phase of #248 against the verified PR #249 pair
(`init_boot-boe-panel.img` SHA-256 `f9449ba5…`, `vendor_boot_b-boe-panel.img`
SHA-256 `a71b3f5f…`; verifier from merged main `261e2f2` PASS, 84 refused
image hashes). Written exactly once each to `init_boot_a` and `vendor_boot_b`
(01:58 MEZ, preflight and post-flash hooks PASS). No other partition, no
userdata erase, no cold start, no Android boot, no stock restore.

## Pre-write evidence

The installed run-86 pair was booted once for the read-only rescue check:
boot `1782b195` read exact stock `boot_a 197aff11`, `vendor_boot_a 23725940`,
`dtbo_a 759813db`, `vbmeta_a cc1926d2` plus installed `init_boot_a fed40c30`,
`vendor_boot_b 1765381c`. Host manifests parts/parts-a/parts-b 31/31 OK.

## Measured boundary (outcome b)

Boot `019587dc-a7c8-4a36-ab7e-d76f72971299`: key-only SSH `:22`, root-only
`/run/keep`. The pre-SSH record names the BOE node:

`usb-init: pre-SSH panel node=boe card0=1 dsi1=1 dcs=none reset=none suspend=clear brightness=0 boot 019587dc-a7c8-4a36-ab7e-d76f72971299`

dmesg at 1.474 s: `Successfully bind display panel
'qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe '` — the exact stock node.
Against run 86 (`node=vxn card0=0 dsi1=0 dcs=none brightness=none`), the
selection change took effect (`card0=1 dsi1=1`), which rules out outcome (c).
The glass did not light: `dcs=none`, backlight 1638 but `actual_brightness` 0.
No host pid1-ack was issued; the issue's step 3 stop rule applied.

## Close-out

The boot self-returned to fastboot on its own with no ack (watched, observed
at +226 s from boot USB settle; the 160 s guard arms at cutover, which never
happened). Post-flash on-device hashes on the same boot: stock rescue exact,
`init_boot_a f9449ba5…`, `vendor_boot_b a71b3f5f…` exact. Final fastboot gate:
serial `00181152O003821`, slot a, unlocked, pineapple, userspace no. The new
pair stays installed per the standing owner rule; no rollback needed.
