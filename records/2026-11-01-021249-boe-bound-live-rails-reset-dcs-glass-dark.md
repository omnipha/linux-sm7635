---
date: 2026-11-01
run: 88
issue: omnipha/linux-sm7635#251
subsystem: display
result: refuted
---
# BOE-bound live session: rails, reset and DCS exercised, glass stays dark

Run 88 live phase of #251 on the never-reflash run-87 pair, booted by the
coordinator with exactly one host pid1-ack (accepted on this boot). Boot
`5fea620d-dee0-4799-aea8-ccb3b2eb1c7d`, postmarketOS PID 1, key-only SSH
`:2222` with the pinned host key, capture
`omnipha-session-capture-1ce1f8c4f83239ec` green (first selftest timeout
corrected by the coordinator before handoff). No image, no flash, no
partition or userdata write, no cold start; every change below is guest RAM
state (temporary `/dev/dri/card0`, `/dev/gpiochip0`, `/tmp/lineinfo`), all
left running or discarded, nothing persisted.

## Session identity rechecked

boot_id over SSH matches the handoff; `/run/keep` root-only present; both
rescue hashes and both installed hashes re-read read-only over the session:
stock `boot_a 197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`,
`vbmeta_a cc1926d2`, installed `init_boot_a f9449ba5`,
`vendor_boot_b a71b3f5f` — exact. Port 22 reset one connection early (its
dropbear lives in the recovery ramdisk); all work ran over the proven
`:2222`.

## Step 1: bound node and KMS state — BOE, active

dmesg at 1.381 s: `Successfully bind display panel
'qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe '`. `/sys/class/drm`: card0,
renderD128, DSI-1 `connected` with the four 1080x2392 vid modes
(120/90/60/30), DP-1 and Virtual-1 disconnected, three sde CRTCs. The live
DT confirms the bound node is the BOE sibling: `qcom,dsi-default-panel` of
`soc:qcom,dsi-display-primary` still resolves to the `_vxn` phandle
(`0x59b`), so the BOE binding comes from the `dsi_display0` insmod option,
and the bound DT node compared below is
`soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe`.

## Step 2: CRTC up at the panel mode, rail/reset/AMOLED reading

The leftover #240 guest tool `/tmp/kmsfill` set CRTC 0 on DSI-1 at
`1080x2392x120vid` (fb XR24, `setcrtc ok`), then held it as KMS master.
`regulator_summary` with the CRTC active: `vddio pm7550_l9` 1800 mV and
`vci pm7550_l19` 3000 mV both enabled for `soc:qcom,dsi-display-primary`
(use 1), `vddic_1v8_t0` enabled, `ae95000...vdda-0p9` 880 mV and
`ae94000...vdda-1p2` 1200 mV enabled, `disp_cc_mdss_core_gdsc` enabled.
`qpnp-amoled-regulator` and `qti_amoled_ecm` bind zero devices (no AMOLED
PMIC node in the live DT); `qcom-spmi-wled.ko` fails `unknown symbol` and
WLED stays out of the path (bl control is `bl_ctrl_dcs`).

The BOE DT node names exactly the same supplies and reset as the `_vxn`
node: `qcom,panel-supply-entries` → the shared `dsi_panel_pwr_supply_amoled`
supply node (phandle `0x596`), `qcom,platform-reset-gpio` → TLMM GPIO 12
via `pinctrl@f000000` (`0x0c`), reset sequence `1,1,0 / 1,1,32`. Lineinfo:
GPIO 12 `flags=0x9 consumer=reset_gpio` — claimed by the panel driver, so
not toggled manually. TE is GPIO 129 (`func1`, input, unclaimed). The only
unclaimed panel GPIO is extdvdd TLMM GPIO 161
(`display_panel_extdvdd_default`, `gpio161` output-high in DT, no consumer
anywhere): `flags=0x4` before, `0x9` while held.

## Step 3: re-sequence the #240 way

KMS master drop (kill the holder): CRTC 0 `enable=0 active=0`; panel rails
stayed up (vddio/vci use 1 — the driver keeps panel power across a modeset
disable on this chain, unlike run 86's read). Fresh SETCRTC re-enabled the
CRTC and re-ran `dsi_display_set_mode` with no `Command transfer failed`.
With GPIO 161 held high by `/tmp/gpiopulse` across a second full
drop/re-set cycle the result is the same: rails hold, mode sets cleanly.
One new measured artifact of this chain: the master drop logs
`dsi-ctrl-0: No change in state, cmd_state=0` /
`disable mvid engine failed rc=-22` for the BOE panel — the video engine
never reports a transition it can disable.

## Step 4: DCS and brightness — the same boundary

With the CRTC active and ESD polling off, single-spaced `0x11` and `0x29`
writes are accepted (`tx11=0`, `tx29=0`) but each ends
`last_cmd_tx_sts:0x1`; dmesg logs only `Command requested for transfer to
panel: 11/29` and, notably, zero `Command xfer attempted while device is
in suspend state` lines this run (run 86/#240 saw them on every write).
The one DCS read (`0x0a`) returns `no valid data from panel` /
`read error: Invalid argument` — empty. Backlight:
`brightness=4095` written, `actual_brightness=0` (also unreadable as
`Invalid argument` while the CRTC cycles). The glass stayed dark
throughout; no picture was possible and no reboot check was run (both
conditional on a lit glass per the issue).

## Outcome: (b) — contrast measured, same boundary on the BOE chain

Node selection is now measured out as the last remaining difference: the
BOE node names the same rails (vddio/vci via the shared amoled supply
node), the same reset GPIO 12 and sequence, and the same DCS-controlled
backlight as `_vxn`. With all of them exercised — rails enabled, reset
cycled by the driver through full KMS power cycles, extdvdd 161 held high,
`0x11`/`0x29` accepted, brightness commanded — the panel returns no data,
reports `last_cmd_tx_sts:0x1`, keeps `actual_brightness=0` and the glass
stays dark. The boundary is identical to #240/#243/#248 on the `_vxn`
chain. Per the issue's stop condition this records the boundary and stops:
the next single variable (pre-SSH power-on/reset before the cont-splash
handoff, or a supply state this userspace cannot reach) belongs to the
strategist, not this issue.
