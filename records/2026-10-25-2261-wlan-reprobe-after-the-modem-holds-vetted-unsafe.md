---
date: 2026-10-25
issue: omnipha/linux-sm7635#99
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## WLAN reprobe after the modem holds: vetted unsafe, no image (#99, host-only, 2026-10-25)

**Host result: no safe single reprobe is establishable from the existing
artifacts; per the issue's own stop rule no new init_boot was built, marked or
flashed, and no device operation was performed.** The vetted candidate was the
issue's primary one: a sysfs driver unbind/bind of the icnss2 device bound
during the wlan-init phase. All evidence below is host-only, from the pinned
vendor tree (NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, read-only) and the run-36 artifacts
(`~/phone-second-life-data/mb003/pstore/attempt-20261025-1425-initboot-rmtfs-sharedmem/`).
The #96 marker in `initramfs/init` therefore remains the newest session init;
`bf2089c4…` and every previously measured SHA stay never-reflash.

### Exact binding identity (established)

The icnss2 device bound during wlan-init is the platform device
`17110040.qcom,wcn6750` (live FDT `dtb/live-fdt.dts:26120-26149`,
`compatible = "qcom,wcn6750"`, `use-nv-mac`, `qcom,rproc-handle = <&wpss_pas>`
per `vendor/qcom/proprietary/wlan-devicetree/volcano-qca6750.dtsi:38`,
`wpss_pas = remoteproc-wpss@9bb00000` in
`arch/arm64/boot/dts/vendor/qcom/volcano.dtsi:1248`), bound by driver
`icnss2` (`icnss_driver`, `.driver.name = "icnss2"`,
`vendor/qcom/opensource/wlan/platform/icnss2/main.c:5506-5514`; of-match
`qcom,wcn6750` → `WCN6750_DEVICE_ID`, `main.c:4868-4888`). Measured bound in run
36: `stage10-final-observation.txt:16` (`supplier state: icnss2 bound`) and
kmsg `:2370` (`icnss2: Platform driver probed successfully`, `main.c:5148`).
The sysfs unbind/bind nodes would be
`/sys/bus/platform/drivers/icnss2/unbind` and
`/sys/bus/platform/drivers/icnss2/bind` (standard platform-bus driver
attributes); no existing artifact documents unbinding this device.

### Vetting chain and the three independent blockers

1. **The #96 session state cannot produce any discriminating outcome from an
   icnss2 reprobe.** `wlan0` requires the qca_cld3 probe via
   `icnss_call_driver_probe` (`main.c:1340-1341`), which only runs after
   `ICNSS_FW_READY` (`icnss_driver_event_fw_ready_ind`, `main.c:1452-1493`);
   FW_READY comes from a WLFW QMI indication (`qmi.c:2329-2345`, via server
   arrival `qmi.c:3204-3231`), which requires the WPSS firmware to boot. The
   initial boot trigger in this driver is the `wpss_boot` sysfs attribute
   (`wpss_boot_store` → `schedule_work(&wpss_loader)`, `main.c:4373-4396`);
   its other `rproc_boot` call is WPSS self-recovery (`main.c:2111-2123`).
   Run 36 measured `remoteproc3` (`9bb00000.remoteproc-wpss`) `offline`
   (`stage9-state.txt:21`) and no `WLAN FW is ready` or WPSS firmware-start
   lines in `capture/kmsg.log`, i.e. the WLAN firmware was never initialized
   (the `wpss_boot` write was deliberately removed from these inits). A
   reprobe in that state cannot itself boot WPSS or set FW_READY, so outcome
   (a) is unreachable, and outcome (b)'s "new probe lines" reduce to
   repeating the already-measured platform probe. The candidate cannot test
   the DMS/wlan0 hypothesis at all.
2. **The sysfs unbind path is not memory-safe with the WLAN closure loaded.**
   `icnss_remove` (`main.c:5193-5267`) tears down the devm-allocated `priv`
   (`devm_kzalloc`, `main.c:5022`) and `dev_set_drvdata(NULL)`, but the module
   global `penv` (`main.c:95`, set by `icnss_set_plat_priv` at `main.c:5095`)
   is never cleared — there is no `penv = NULL` anywhere in the tree. The
   WLAN-facing entry points dereference `penv` (e.g. the exported
   `icnss_ce_free_irq` `main.c:3548` and `icnss_ce_request_irq`
   `main.c:3536`, and thermal state `main.c:3161-3179`),
   leaving a freed-memory window between `unbind` returning and `bind`
   re-probing. The driver's supported path for `icnss_remove` is module exit
   (`icnss_exit` → `platform_driver_unregister`, `main.c:5546-5550`), where
   the qca_cld3 client unregisters first — an ordering that cannot hold with
   the 21-module closure pinned loaded and no `rmmod` allowed.
3. **The cycle permanently orphans the already-registered WLAN client driver.**
   `qca_cld3_qca6750.ko` registers `pld_ipci_ops` once at module load
   (`qcacld-3.0/core/pld/src/pld_ipci.c:495-525` via `pld_common.c:303-308`);
   the ops pointer lives only in the old `priv->ops`. `icnss_remove` never
   unregisters it and the fresh `priv` after rebind has `ops == NULL`, so
   `icnss_call_driver_probe` (`main.c:1340-1341`) is a silent no-op even if the
   bind itself succeeds. Without `rmmod`/`insmod` of the WLAN modules —
   explicitly outside this issue after run 29's SSH loss — the WLAN stack can
   never probe after the cycle. The candidate is therefore both unsafe and
   structurally incapable of producing the issue's outcomes.

Boundaries kept: `rmmod`/`insmod` of loaded WLAN or remoteproc modules stays
excluded (run 29 lost SSH after exactly a modem start plus WLAN module reload).
An in-session `echo 1 > …/wpss_boot` would boot WPSS firmware for the first
time in a guarded session — a *second* unmeasured variable, not the vetted
candidate — and is not improvised here.

**Named next single blocker (new issue, not this one):** the DMS/`wlan0`
question is untestable until WPSS firmware bring-up is its own single-variable
experiment (a designed, risk-assessed `wpss_boot`-equivalent before or after
the guarded modem start), because FW_READY — not the icnss2 reprobe — is the
gate in front of the qca_cld3 probe. The modem-holding stack, WLAN closure,
USB/key-only SSH path and recovery timer of the #96 session init are unchanged;
there is no new session marker, no new SHA and nothing to reflash.
