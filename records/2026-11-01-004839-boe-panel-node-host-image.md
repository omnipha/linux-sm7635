---
date: 2026-11-01
issue: omnipha/linux-sm7635#248
subsystem: display
result: confirmed
---
# BOE panel node: host image for the single-variable node-selection test

Host-only delivery for #248. No USB, flash, boot or partition write was
performed. The installed run-86 pair `init_boot_a fed40c30` /
`vendor_boot_b 1765381c`, the run-84 pair `27c4d895` / `da4651d8`, and every
earlier measured hash stay never-reflash.

## Why the node selection needed a change at all

Stock Android and our own boots log the same kernel command line, including
exactly one panel token,
`msm_drm.dsi_display0=qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe:`. Stock
binds the BOE node; run 86 bound the `_vxn` node. The token is not kernel
built-in command line: `msm_drm.ko` declares `dsi_display0` as a module
parameter (`module_param_string`), so the kernel consumes it only when the
module loader passes it. Stock userspace loads `msm_drm` through the module
loader with that option, and the pinned `vendor_a` also writes
`module/msm_drm/parameters/dsi_display0` directly. Our initramfs loads
`msm_drm.ko` with bare `insmod` and no option, so the parameter stays empty,
`boot_disp_en` stays false and `dsi_display_dev_probe` takes the
`qcom,dsi-default-panel` phandle, which the stock device tree sets to the
`_vxn` node. `dsi_prop` does not exist in any pinned image, so the firmware
path cannot select the node either.

## The one functional delta

The pre-SSH display phase is unchanged in module set and load order from run
86 (the same 19 modules, `msm_drm.ko` last). The single change: the `insmod`
of `msm_drm.ko` alone carries
`dsi_display0=qcom,mdss_dsi_rm69220_fhd_plus_120hz_vid_boe:`, the exact token
stock's command line names. No other module gets an option, no module was
added or dropped, and the device tree, command line, guard (`f72a68a4…`),
160 s timer, radio, slot-A rescue partitions and persistent root contents are
unchanged.

## The pre-SSH record

The record line now names the node the driver actually bound, read from the
dmesg captured at that instant:

`usb-init: pre-SSH panel node=<boe|vxn|none> card0=<0|1> dsi1=<0|1> dcs=<none|init-ran> reset=<none|seen> suspend=<clear|suspend-state> brightness=<n|none> boot <boot-id>`

`node=boe` requires the `Successfully bind display panel '...vid_boe '` line,
`node=vxn` the `...vid_vxn ` line, and anything else stays `none`. The
existing boundary fields are unchanged, so the two nodes compare line for
line. `boot_record_lines` accepts only `boe`, `vxn` or `none` in that field,
so a malformed line is refused rather than recorded.

## Host verification

Two serial builds were byte-identical. A diff of the decoded init against the
run-86 init shows only the panel option, the bound-node field and the carrier
reader's size and hash pins, which move because the bundle grew by the
`node=` token in the record contract. `pmos-pid1-guard.sh` is byte-identical
(`f72a68a4…`).

- `init_boot-boe-panel.img`: 8388608 bytes, SHA-256 `f9449ba5590fd5955a85a6b97a0e21775aa34534197981b213bc380fe8378b0f`.
- `vendor_boot_b-boe-panel.img`: 100663296 bytes, SHA-256 `a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3`.
- Decoded cpio 3685376 bytes; one reproducible LZ4 HC-12 frame 2100908/2117632 bytes; stock header and signed tail unchanged.

The verifier's self-test passed: 84 refused image hashes, now including the
run-84 `27c4d895` / `da4651d8` and run-86 `fed40c30` / `1765381c` pairs, which
the verifier rejects outright. Negative fixtures refuse a removed panel
option, the `_vxn` token in its place, the option applied to every module,
and a record line or record contract without the bound-node field.
`test-pmos-boot-record.sh`, `test-pmos-root-contract.sh`,
`test-pmos-self-stage.sh` and `test-pmos-pid1.sh` passed.

Both images fit the approved carriers (`init_boot_a` 8388608 bytes,
`vendor_boot_b` 100663296 bytes) with the same envelope the run-86 pair used.
Nothing was dropped and `recovery_b` / `dtbo_b` were not touched.

## Not measured here

Whether the driver binds the BOE node, and whether the glass lights, is the
physical phase. A kernel hang before the 160 s guard arms is not covered by
that timer and must be recorded as a hang, not as a returned boot.
