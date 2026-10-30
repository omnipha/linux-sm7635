---
date: 2026-10-30
run: 69
issue: omnipha/linux-sm7635#204
subsystem: boot
result: confirmed
---
# Run 69: bootloader start and slot-A rescue

Host-only closeout. No USB, SSH, flash, reboot, image, or partition operation was performed here.

The coordinator started the bootloader from second boot `b5171324-06eb-46b9-b538-c518765510d1` and then booted the unchanged installed chain. Fresh diagnostic boot `65c0a7bf-2809-4dd3-a01a-1e2ec91499f4` had root-only `/run/keep`. Capture `STOP` is present. This boot is the rescue-read boot, not another measured postmarketOS PID 1 or WLAN result.

The readback matches stock slot A: `boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`, and `vbmeta_a cc1926d2…cdffe`. Installed `init_boot_a` remains `2f73c947…31c28` and `vendor_boot_b` remains `f792174c…11095`. The full userdata digest was not completed, so no new userdata claim is made. With the earlier first- and second-boot measurements, #204 is complete.
