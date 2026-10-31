---
date: 2026-10-31
issue: omnipha/linux-sm7635#243
subsystem: display
result: confirmed
---
# Pre-SSH panel: host image for the bootloader-handoff test

Host-only delivery for #243. No USB, flash, boot or partition write was
performed. The installed run-84 pair `init_boot_a 27c4d895` /
`vendor_boot_b da4651d8` and every earlier measured hash stay never-reflash.

## The one functional delta

The run-84 init loads 127 stock modules and then starts the key-only `:22`
dropbear. The #240 live session (boot `07f16bc0`) loaded the stock `msm_drm`
closure afterwards, over SSH, and measured the panel boundary there: DCS
writes accepted while the command engine reported suspend, DCS reads empty,
`actual_brightness` zero.

This pair adds, in the initramfs and before `dropbear` starts, one extra
`insmod` loop over the 19 stock modules that the `modules.dep` closure of
`msm_drm.ko` names and that the run-84 init does not already load:

`qti_battery_charger.ko`, `panel_event_notifier.ko`, `hwmon.ko`,
`qti_amoled_ecm.ko`, `qseecom_proxy.ko`, `smcinvoke_dlkm.ko`,
`hdcp_qseecom_dlkm.ko`, `sync_fence.ko`, `nt_display_notifier.ko`,
`llcc-qcom.ko`, `msm_ext_display.ko`, `drm_display_helper.ko`,
`gh_mem_notifier.ko`, `gh_irq_lend.ko`, `altmode-glink.ko`, `fsa4480-i2c.ko`,
`qpnp-amoled-regulator.ko`, `qcom-spmi-wled.ko`, `msm_drm.ko` last.

`qti_battery_charger.ko` is included because `modules.dep` lists it as a
dependency of `panel_event_notifier.ko`, which `msm_drm.ko` needs; the live
session's kernel already had that driver built in, which is why the session
only had to load 14 modules. No module was dropped to fit, no new driver was
added, and the device tree, cmdline, guard (`f72a68a4…`), 160 s timer, radio,
slot-A rescue partitions and persistent root contents are unchanged.

## The pre-SSH record

Right after the display load and still before SSH exists, the init writes one
line to kmsg and to a root-only `/run/pre-ssh-panel.record`:

`usb-init: pre-SSH panel card0=<0|1> dsi1=<0|1> dcs=<none|init-ran> reset=<none|seen> suspend=<clear|suspend-state> brightness=<n|none> boot <boot-id>`

`card0`/`dsi1` come from `/sys/class/drm`, `brightness` from
`panel0-backlight/actual_brightness`, and `dcs`/`reset`/`suspend` from the
dmesg captured at that instant. The session stage copies that file to
`/run/pmos-pre-ssh-panel.record` and appends it to the persistent boot record
as its own line, immediately after the hold line and before any SSH line.
`boot_record_lines` reads it back from that file, so the line is part of the
verified record and survives the cutover.

## Host verification

Two serial builds were byte-identical. A diff of the decoded init against the
installed run-84 init shows only the display phase above plus the carrier
reader's size and hash pins, which move because the bundle grew by the panel
record line. `pmos-pid1-guard.sh` is byte-identical (`f72a68a4…`).

- `init_boot-pre-ssh-panel.img`: 8388608 bytes, SHA-256 `fed40c3073663b9bc5ff29e35e09ae1afdb8568cadf27e09c7e956f284c33c2d`.
- `vendor_boot_b-pre-ssh-panel.img`: 100663296 bytes, SHA-256 `1765381ce0f2753aea208896342424ab5db7489c426d457a259f3398827cb587`.
- Decoded cpio 3684864 bytes; one reproducible LZ4 HC-12 frame 2100761/2117632 bytes; stock header and signed tail unchanged.

The verifier's self-test passed and refuses the installed `27c4d895` /
`da4651d8` pair and the 80 earlier measured hashes. `test-pmos-boot-record.sh`,
`test-pmos-root-contract.sh`, `test-pmos-self-stage.sh` and `test-pmos-pid1.sh`
passed.

Both images fit the approved carriers (`init_boot_a` 8388608 bytes,
`vendor_boot_b` 100663296 bytes) with the same envelope the run-84 pair used.
Nothing was dropped and `recovery_b` / `dtbo_b` were not touched.

## Not measured here

Whether the glass lights, and which panel boundary the pre-SSH line records,
is the physical phase. A kernel hang before the 160 s guard arms is not
covered by that timer and must be recorded as a hang, not as a returned boot.
