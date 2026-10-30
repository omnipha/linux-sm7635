---
date: 2026-10-30
run: 67
issue: omnipha/linux-sm7635#197
subsystem: boot
result: refuted
---
# Run 67: persistent-root self-stage did not start

`init_boot_a ef476d8c` and `userdata aa8da109` were written once. Boot `d58d462d` reached key-only diagnostic `:22` and a root-only host `/run/keep`, but stayed on the initramfs with PID 1 `init`.

The unpacked `/run/omnipha-self-stage` directory contained the older scripts and profile, not `pmos-root-contract.sh`. No self-stage log, ext4 mount, postmarketOS PID 1, or `:2222` appeared. This pair is not a successful persistent-root boot and must not be repeated unchanged.

Rescue proof on diagnostic boot `9b21eebc` with previously measured `init_boot 5b5a60d4` read stock `boot_a 197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`, and `vbmeta_a cc1926d2`. `userdata aa8da109` remains. The phone was left in fastboot, slot A, unlocked. No stock restore, userdata erase, or Android boot.
