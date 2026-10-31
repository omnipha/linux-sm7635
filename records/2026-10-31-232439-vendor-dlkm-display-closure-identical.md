---
date: 2026-10-31
issue: omnipha/linux-sm7635#246
subsystem: display
result: refuted
---
# vendor_dlkm display closure is byte-identical to the recovery-set modules

Host-only measurement for #246. No USB, adb, fastboot, flash, boot or partition
write was performed; nothing was mounted writable. No image was built. The
installed run-86 pair `init_boot_a fed40c30` / `vendor_boot_b 1765381c`, the
run-84 pair and every earlier measured hash stay never-reflash.

## Question

#246 proposed one variable: the vendor `vendor_dlkm` variant of the display
stack (msm_drm and its dependency closure) instead of the recovery-set ramdisk
modules that run 86 loaded before SSH. Before any image is built, the vendor
modules had to be captured read-only and checked for a loadable-module
mismatch against the session kernel.

## Capture (read-only, pinned inputs)

- `vendor_dlkm_a` read from the pinned super dump
  (`super-dump/super.img`, 9,663,676,416 bytes, SHA-256 `7307e9ff…`, captured
  2026-10-24 from the installed device; super was never rewritten on this
  chain). Logical-partition geometry re-verified with
  `scripts/super-wlan-closure.py`: 14 partitions, 7 slot-A extents, tables
  SHA-256 `6450425f…`; `vendor_dlkm_a` at offset 6,947,864,576, 32,669,696
  bytes, erofs, mounted `ro,loop` and unmounted afterwards. 290 `.ko` files
  under `lib/modules`.
- Recovery-set modules unpacked read-only from the pinned stock
  `vendor_boot_a.img` (SHA-256 `23725940…`, the same PLATFORM ramdisk the
  run-86 carrier carries unmodified): 317 `.ko`, four-block Android legacy
  LZ4, 29,905,920-byte newc cpio. These are exactly the modules run 86 loaded
  from `/lib/modules` before SSH.
- Session kernel (unchanged, from `boot_a`): `6.1.84-android14-11-gf4b0d69fdf34-ab12786779`,
  `CONFIG_DRM_MSM` unset, `CONFIG_MODVERSIONS=y`, `CONFIG_MODULE_FORCE_LOAD`
  unset, `CONFIG_MODULE_SIG_FORCE` unset.

## Result: there is no second variant

All 26 modules of the `vendor_dlkm` `msm_drm.ko` dependency closure are
**byte-identical** (equal SHA-256, equal size) to the recovery-set ramdisk
copies. There is no vendor-only closure member: every `vendor_dlkm` closure
name exists in the recovery set with the same bytes. `dsi-ctrl` is compiled
into `msm_drm.ko` in both; no separate `dsi-ctrl.ko` exists in either source.

| module | bytes | SHA-256 (first 16, both sources) |
|---|---:|---|
| `altmode-glink.ko` | 34,096 | `49ce5b33f3dccac4` |
| `drm_display_helper.ko` | 255,656 | `a99dae982295ab65` |
| `dwc3-msm.ko` | 205,296 | `d5ebd9f24e086720` |
| `fsa4480-i2c.ko` | 39,240 | `cae938fabd5f19ee` |
| `gh_irq_lend.ko` | 25,744 | `ad0609e03c7646f6` |
| `gh_mem_notifier.ko` | 15,712 | `6cbfdd4413fbc3fe` |
| `hdcp_qseecom_dlkm.ko` | 86,072 | `13d6f9d8cc6882b6` |
| `llcc-qcom.ko` | 58,696 | `b1529acaa3424960` |
| `msm_drm.ko` | 4,516,584 | `1deb441cc593fe6e` |
| `msm_ext_display.ko` | 27,496 | `8b1f51b39dbd1f10` |
| `nt_display_notifier.ko` | 12,640 | `c4153d7eaaaab369` |
| `panel_event_notifier.ko` | 16,008 | `65a54631c1539521` |
| `pdr_interface.ko` | 38,480 | `f100a36f3e78ad78` |
| `pmic_glink.ko` | 40,248 | `3a5dfb02a4bcc721` |
| `qcom_glink.ko` | 98,136 | `5b9059b47f0d23e7` |
| `qcom_glink_smem.ko` | 19,848 | `de77ec73d8eea55d` |
| `qcom_smd.ko` | 43,496 | `742d978545ad59dd` |
| `qmi_helpers.ko` | 106,544 | `8fc84ccca0f0e024` |
| `qseecom_proxy.ko` | 16,480 | `9e38bdefa35b6e61` |
| `redriver.ko` | 18,520 | `a355ddeb9a5907dc` |
| `repeater.ko` | 19,072 | `750f74e3c2c2d626` |
| `rproc_qcom_common.ko` | 65,912 | `462f2961a04405fa` |
| `smcinvoke_dlkm.ko` | 274,248 | `5306d2668ed17075` |
| `sync_fence.ko` | 43,416 | `838a3e5fc137ff8b` |
| `ucsi_glink.ko` | 35,080 | `5410ed88dbc412d2` |
| `wcd_usbss_i2c.ko` | 83,448 | `a2fc4a7c8961bb14` |

The `vendor_dlkm` closure has 26 names, the recovery-set `modules.dep` closure
of the same module has 54 (a superset naming extra entries such as
`qti_battery_charger.ko`, `hwmon.ko`, `qti_amoled_ecm.ko`,
`qpnp-amoled-regulator.ko`, `qcom-spmi-wled.ko`). That is dependency-metadata
scope only: run 86 already loaded the superset, and the binaries it executed
are the same bytes this issue proposed to swap in.

## Loadability measurement

Every closure member carries vermagic
`6.1.78-android14-11-maybe-dirty SMP preempt mod_unload modversions aarch64`
(no `version`/`srcversion` fields). The vermagic release string differs from
the 6.1.84 session kernel, yet these exact bytes are measured loadable by it:
run 86 loaded the identical closure in the initramfs before SSH (17 of 19
extra modules accepted, `msm_drm` probed, `Initialized msm_drm 1.4.0`), and
`msm_sharedmem.ko` from the same `vendor_dlkm_a` was loaded as-is earlier.
So the vendor variant is loadable — and useless as a variable, because it is
the same code.

## Why no image was built

The one permitted functional delta was the module set. With both sources
byte-identical, swapping them is a zero delta; a rebuild would reproduce the
never-reflash run-86 pair `fed40c30`/`1765381c`, which host verification must
refuse. Per the issue, this is a decision point for the strategist, not a
second variable: no image, no flash, no physical phase in this issue.

## Outcome and remaining lever

Outcome (c) class, answered by measurement instead of by a boot: the proposed
vendor-variant lever does not exist. The recovery-set and vendor_dlkm module
sets are not merely equivalent at the panel boundary, they are the same
binaries, so run 86's dark-glass boundary applies to both. The remaining lever
is a supply/handoff state the recovery kernel cannot reach; that needs a new
single-variable decision outside this issue. The guard, 160 s timer, radio,
cmdline, slot-A rescue partitions and persistent root contents are untouched.
