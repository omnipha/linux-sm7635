---
date: 2026-10-31
issue: omnipha/linux-sm7635#243
subsystem: display
result: refuted
---
# Run 86: panel probed before SSH, same boundary as #240, glass dark

Physical result for #243 on the successor pair `init_boot_a fed40c30` /
`vendor_boot_b 1765381c` (flashed once by the coordinator, both postflash
writes verified; the run-84 pair and every earlier hash stay never-reflash).
Boot `2fe58d55-b7bd-4f51-9af9-aede8f5a89b4`, postmarketOS v24.12 PID 1,
exactly one host pid1-ack accepted, key-only `:2222` with the pinned
diagnostic host key, capture `omnipha-session-capture-3bd35d69f53fedf1`
carrying both fresh run-86 markers. No reflash, no second image, no cmdline,
DT or kernel change in this run.

## Outcome: (d) — the bootloader-handoff hypothesis is refuted for this closure

## Pre-SSH record (measured, on the persistent boot record)

`usb-init: pre-SSH panel card0=0 dsi1=0 dcs=none reset=none suspend=clear
brightness=none boot 2fe58d55-...` — written at t=1.496 s, ~1 ms before
`msm_drm` finished probing (`Initialized msm_drm 1.4.0` at 1.497 s). The
display closure loaded early and clean: 17 of 19 modules accepted
(`msm_drm.ko` last at 1.478 s); `qti_battery_charger.ko` and
`qcom-spmi-wled.ko` failed with `unknown symbol` (the session kernel has
`qcom_battery` built in; WLED is DT-disabled and measured out of the path in
#240). The zero reading is a race of the fixed probe order, not a missing
load: the module log proves the probe ran after the modules and before SSH.

## Live boundary (this session, after one SETCRTC on DSI-1)

The leftover #240 KMS tool (`/tmp/kmsfill`, guest RAM only) brought the CRTC
up at 1080x2392 (`dsi_display_set_mode` mdp_transfer_time=0, fps=120, no
error). Then, with ESD polling already 0:

- DCS writes `0x11`/`0x29` accepted (`tx11=0`, `tx29=0`), each with
  `Command xfer attempted while device is in suspend state`.
- DCS read `0x0a` refused: `read error: Invalid argument`, no data.
- Backlight: `brightness=1638`, `actual_brightness=0` (`bl_ctrl_dcs`).

That is byte-for-byte the closed #240 boundary: writes accepted, command
engine in suspend, reads empty, brightness zero. Loading the measured stock
closure before SSH — while the bootloader cont-splash handoff still existed
on the very first boot after flash — did not change the panel boundary. The
glass stayed dark before SSH, after the modeset, and through the session; no
test picture was possible and no reboot check was run (both are conditional
on a lit glass per the issue).

## Next boundary (for the strategist, not this issue)

The remaining difference to a working stack is not timing: it is either the
vendor `vendor_dlkm` module variant of msm_drm/dsi-ctrl instead of the
recovery-set ramdisk modules, or a supply/handoff state the recovery kernel
cannot reach. Both need a new single-variable decision.

The persistent root, guard (`f72a68a4…`), radio and rescue partitions are
unchanged; `/dev/dri` nodes and the kmsfill process live in guest RAM only.
