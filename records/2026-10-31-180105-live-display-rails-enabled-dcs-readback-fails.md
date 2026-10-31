---
date: 2026-10-31
issue: omnipha/linux-sm7635#240
subsystem: display
result: inconclusive
---
# live display: rails enabled, DCS writes accepted, readback fails

Live-session follow-up on #240 after the audit found untried in-session
levers. Boot `07f16bc0-8f18-41f4-9051-c52fe596c740`, key-only `:2222`,
capture `omnipha-session-capture-744df2b51c9f2ea3` green throughout. No image,
no flash, no reboot, no partition/userdata writes; all changes are guest RAM
state. Records every step of the supervisor's reset/power/rail checklist.

## Reset path (step 1)

Panel `qcom,platform-reset-gpio` = phandle `0x65` (`pinctrl@f000000`), offset
`0x0c` = TLMM GPIO 12; reset sequence `1,1,0 / 1,1,32` (high, low 1 ms, high
32 ms). `/sys/class/gpio` legacy sysfs is absent, so the GPIO character device
was used (`/dev/gpiochip0` mknod 254:0, GPIO_V2 ioctls). `GPIO_V2_GET_LINEINFO`
shows `line=12 flags=0x9 consumer=reset_gpio` — **claimed**, so no manual
toggle was attempted (exactly as the bounded step requires). TE is GPIO 129,
`func1`, input. The driver's reset line was exercised indirectly by the full
panel power cycles below instead.

## Power rails verdict (step 3, measured)

`regulator_summary` with the CRTC active:

- `soc:qcom,dsi-display-primary-vddio` = `pm7550_l9` 1800 mV, enabled (use 1)
- `soc:qcom,dsi-display-primary-vci` = `pm7550_l19` 3000 mV, enabled (use 1)
- `vddic_1v8_t0` enabled for the DSI display
- `ae95000.qcom,mdss_dsi_phy0-vdda-0p9` = `pm7550_l2` 880 mV, enabled
- `ae94000.qcom,mdss_dsi_ctrl0-vdda-1p2` = `pm7550_l4` 1200 mV, enabled
- `ae95000...-gdsc` resolves to `regulator-dummy` (the DSI PHY's dummy-supply
  log line is cosmetic, not a missing rail)
- `disp_cc_mdss_core_gdsc`/`_int2_gdsc` are proxy rails with no direct enable
  consumer; the real DISP CC clocks run (`disp_cc_pll0` 1890 MHz,
  `dsi0_phy_pll_out_byteclk` 103.194 MHz, `dsi0_phy_pll_out_dsiclk`
  165.11 MHz, `mdss_pclk0` 110.07 MHz, `mdss_byte0_clk` 103.194 MHz, all `Y`).

No LAB/IBB rail exists on this DT (AMOLED panel, no LCD bias). `qcom,wled@f500`
is `status=disabled`; the AMOLED uses DCS brightness, so WLED is not in the
path. `qpnp-amoled-regulator` and `qti_amoled_ecm` both bind **zero devices**:
the live DT has no AMOLED PMIC node, so panel main power is bootloader-held
and not OS-switchable. `display_panel_extdvdd_default` is TLMM GPIO 161
(output-high, no consumer anywhere in DT); it was **unclaimed** and was driven
high with GPIO_V2 ioctls, held across a full power cycle. All named rails are
therefore enabled or proven absent-by-design.

## Power re-sequence (step 2)

- `rmmod msm_drm` is not a usable lever while DRM is registered (`in use`),
  and `msm-dsi-display` has no `bind`/`unbind` attributes (component driver).
- The working re-sequence is the KMS master drop: killing the KMS holder
  dropped every panel rail to use 0 (measured in `regulator_summary`), and a
  fresh `SETCRTC` re-enabled all of them and re-ran `dsi_display_set_mode`
  with **no** `Command transfer failed` lines — the enable-time DCS traffic
  now goes out cleanly (compare run-84-era errors at 1221/1226 s).
- With GPIO 161 held high through a second full off/on cycle, result is the
  same: rails cycle, mode sets, no enable errors.

## Remaining measured gap

- DCS **writes** through `/sys/kernel/debug/dri/0/DSI-1/tx_cmd` are accepted
  (`0x11` sleep-out, `0x29` display-on: rc 0, `last_cmd_tx_sts:0x0`), each with
  `Command xfer attempted while device is in suspend state`.
- DCS **reads** fail: `DSI_0: Panel detected error, no data read` /
  `read message failed read length, rc=0`, so ESD still cannot read status.
- Backlight stays `actual_brightness=0` with `brightness=4095` written
  (`bl_ctrl_dcs`: brightness rides in the panel on/brightness command flow).
- The CRTC itself is healthy: `num_connectors: 1`, `intf_mode: 2`,
  `core_clk_rate 630000000`, stable 1080x2392 XR24 test framebuffer, ESD
  polling disabled. A persistent SSH process keeps the test pattern scanned
  out so an operator can look at the glass.

Interpretation bounded by the measurements: video streaming and DSI command
writes work, but the panel never returns data and never lights. Every rail
named by the DT is enabled, reset is claimed and exercised by power cycles,
and the external DVDD GPIO is high. What cannot be done over this session is
a panel power-on/reset that happens **before** the bootloader's cont-splash
handoff is torn down (the DSI host still reports `suspend state` for the
command engine while video is active), or a vendor-module/DT variant that
changes that handoff. Both execute before SSH exists — the issue's case (c)
criterion for a separate single-variable successor-image issue, to be owned
by the strategist, not created here.

Outcome: still (b), no picture observed; the previous "pre-SSH blocker" claim
is now backed by the rail/reset/command evidence above instead of speculation.
