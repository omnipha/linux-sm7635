---
date: 2026-10-31
run: 78
issue: omnipha/linux-sm7635#223
subsystem: boot
result: inconclusive
---
# Run 78: cold start performed, observation incomplete

Independent closeout from the coordinator's committed report (`sprintberlin/phone-second-life` `0586c1b`, 2026-10-31T08:49:04+01:00) and its preserved raw evidence. No USB, SSH, flash, reboot, or partition operation was performed here. The cold start was performed once. Its functional result is unmeasured, not a success and not an image-gate failure.

The merged-main verifier passed for exactly `init_boot-coldstart-verified.img` `3192278b93812ff14cf7d71d4f8bae60a7e00d178c194155fc336817a6c4bcdf` and `vendor_boot_b-coldstart-verified.img` `ab3a0e6360269d1e56d14626e6849b8249634810895f5270283ed30ebdb4a5a9`. Device-op flash hooks verified writes to `init_boot_a` and `vendor_boot_b` only. There was no other partition write, userdata erase, Android start, or stock restore.

Before the write, diagnostic boot `40e14477-9303-45e7-8b7f-9bff988f2cc3` read the exact stock slot-A rescue hashes and the previously installed `init_boot_a 2f73c947…31c28` / `vendor_boot_b f792174c…11095`. The operator reported the Nothing logo after power off/on at about 08:11 MEZ. USB was absent from 08:07:29 through 08:28:27 MEZ; when it returned, the device enumerated directly as fastboot `18d1:d00d`. Neither the power-on-to-fastboot timeline nor cold-start SSH or WLAN was observed live. A later USB diagnostic boot found `/sys/fs/pstore` empty, so the original cold-start console is lost. Whether that cold start reached `switch_root`, postmarketOS PID 1, radio, or MINDSTORMS is unmeasured.

Rescue proof comes from a separate USB diagnostic boot, not the cold start. Boot `67f5b5e3-4e1b-4517-88c4-c53efc87adb2` reached key-only SSH and, through the exact sysfs major:minor mapping, read stock `boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`, `vbmeta_a cc1926d2…cdffe`, installed `init_boot_a 3192278b…c4bcdf`, and installed `vendor_boot_b ab3a0e63…b4a5a9`. An earlier reader with minor 0 stalled; its output is not hash evidence. The device returned to responsive fastboot at 08:46:31 MEZ. The final gate was the expected serial, slot `a`, unlocked, and product `pineapple`. No rollback was needed. The candidates remain installed and every previously measured image remains never-reflash. The coordinator session is closed.
