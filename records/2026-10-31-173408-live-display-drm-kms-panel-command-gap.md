---
date: 2026-10-31
issue: omnipha/linux-sm7635#240
subsystem: display
result: inconclusive
---
# live display: DRM device reached, KMS active, DSI panel commands fail

Live-session result for #240 on the installed record-rotation pair
`init_boot_a 27c4d895` / `vendor_boot_b da4651d8`, boot
`07f16bc0-8f18-41f4-9051-c52fe596c740`, key-only SSH `:2222`, postmarketOS
PID 1, capture unit `omnipha-session-capture-744df2b51c9f2ea3` healthy
throughout. No image was built; no partition, userdata or Android state was
touched. All module loads and nodes live in guest RAM only (`/dev/shm`,
`/tmp`, tmpfs `/dev`); the persistent root is unchanged.

## Working partial recipe (measured live)

1. The running kernel `6.1.84-android14-11-gf4b0d69fdf34-ab12786779` has
   `CONFIG_DRM=y`, `CONFIG_DRM_KMS_HELPER=y`, `CONFIG_DRM_MIPI_DSI=y` built
   in, but `CONFIG_DRM_MSM is not set` — the Qualcomm display stack ships only
   as the stock vendor module. No `.ko` exists anywhere on the persistent
   root; the 317 stock modules live only inside the staged vendor_boot ramdisk.
2. Extracted the stock ramdisk read-only on the host from a copy of the
   installed `vendor_boot_b-record-rotation.img` (LZ4 legacy, 4 blocks, 317
   `.ko`) and pushed only the `msm_drm.ko` dependency closure (54 modules,
   8.4 MB) plus `qpnp-amoled-regulator.ko`, `qti_amoled_ecm.ko`,
   `qcom-spmi-wled.ko`, `hwmon.ko` into guest `/dev/shm/display240`.
3. Loaded 14 missing closure modules (`msm_drm` last) with busybox `insmod`.
   All accepted (vermagic differs from the stock kernel string but loads fine,
   matching the #44 measurement). `qti_amoled_ecm` loads only after `hwmon`.
   Result: `card0`, `renderD128`, `card0-DSI-1`, `card0-DP-1`, `Virtual-1`
   under `/sys/class/drm`; SDE hw rev `0xa0020000`; `panel0-backlight`
   (raw, max 4095) registered.
4. `/dev/dri` nodes were absent only because no udev runs; created them with
   busybox `mknod` after `mount -o remount,exec /dev`.
5. Panel path (named, live): DT node
   `/proc/device-tree/soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_vxn`
   selected by cmdline `msm_drm.dsi_display0=...rm69220_fhd_plus_120hz_vid_boe`
   with fallback to the `_vxn` variant, driver `msm_drm.ko`
   ("[rm69220 amoled vid mode dsi visionox panel with DSC]"), DSI PLL 4nm,
   1080x2392 DSC 8bpc video mode, modes 120/90/60/30 Hz, connector 61,
   encoder 60, CRTC 146. No panel firmware file is needed ("dsi_prop" -2 is a
   benign fallback to the DT node).
6. A small static KMS test (dumb buffer, XRGB8888, `SETCRTC` on DSI-1)
   brings the CRTC fully up: `num_connectors: 1`, `intf_mode: 2`,
   `core_clk_rate: 630000000`, 9.8 GB/s bus votes, framebuffer
   `1080x2392 XR24` — held stably for minutes with ESD polling disabled
   (`echo 0 > /sys/kernel/debug/dri/0/DSI-1/esd_status_interval`).

## The exact remaining gap (no picture yet)

DSI command-mode transfers to the panel fail with
`dsi-ctrl-0: Command transfer failed` /
`DSI_0: Panel detected error, no data read` /
`read status failed on master` -> ESD reports `PANEL_DEAD` and the driver
re-enables the connector in a loop. Video mode starts silently (set_mode at
1080x2392@120 succeeds, no error), but the panel never shows light: the
backlight stays `actual_brightness=0` even with `brightness=4095` written
(`bl_ctrl_dcs`: brightness travels inside the DSI on-command packet that
never reaches the panel). Selftest console markers printed at the same time
appeared in capture, so the failure is panel-bound, not capture-bound.

The DSI host claims `supply gdsc not found, using dummy regulator` for
`dsi_phy`; panel node supplies `vci`/`vddio` resolve (VDDIC 1.8 V measured
disabling at suspend), so the supply state is plausible but the panel's DCS
init/reset sequence is not observable from the running stack: on this chain
the panel has been powered down since the guarded boot, and the difference
between "commands fail" and "panel dead" cannot be decided over SSH. `qpnp
amoled-regulator` loaded clean; no LAB/IBB/WLED class device binds on this
board's DT.

No reboot test was run: without a picture the recipe does not survive the
one-reboot check, and a reboot would discard all loaded modules (case (b)
outcome, not (a)).

## wlan0 observation (bounded, read-only, one record)

On this chain `wlan0` is absent because the driver stays loaded but
unprobed: `qca_cld3_qca6750` loaded (v5.2.1.94A), icnss2 bound, firmware
`qca6750/bdwlan.elf` present from the read-only `firmware_mnt` mount, but
`regulatory.db` is missing (`Direct firmware load for regulatory.db failed
with error -2`) — the same single missing file as run 69's earlier chain
observation. No rework done (out of scope).

## Next single question (for the strategist, not this issue)

The panel init depends on state that only exists if the display stack comes
up before or at boot-time handoff (cont-splash continuation), or the
`dsi-ctrl` command path needs the vendor `vendor_dlkm` variant instead of
the recovery-set module. Both require a change that executes before SSH
exists — the case (c) successor-image criterion of the issue, to be sized as
a separate single-variable issue.
