---
date: 2026-10-31
run: 72
issue: omnipha/linux-sm7635#216
subsystem: boot
result: confirmed
---
# Run 72: guest-owned keep reached, guard unarmed

Negative/partial physical result of the image from merged PR #217 (`4c9c975`). This record was written from the coordinator's host evidence. No USB, SSH, flash, reboot, or partition operation was performed here. The image gate is not physically verified and no host-free boot success is claimed. No button-assisted cold start is scheduled.

The shift artifact is `artifact:93a2e5703bc0e78a8aaa7560572323089fc05048d0993edacd270b124ce9c8f2`, recorded at 2026-10-31T02:38:00Z for `omnipha/linux-sm7635#216`. `successfulBoot` is false. Run 72 wrote only `init_boot_a` `3c97c918ed085d6d72530f00bba81c053130c184d351f372a10ac11b616bc71a`. `vendor_boot_b` stayed `f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095`. `3c97c918` was flashed once and is now never-reflash; any successor image or direction belongs to the strategist, not this issue.

Measured on diagnostic boot `94f9fca5-1db2-4a4f-9718-d3cd784c5dfe`, without a host-created `/run/keep`, guard ack, or capture:

- The guest created a regular root-only empty `/run/keep` (`0:600:1`).
- Self-stage verified that hold and diagnostic `:22` at 4.02 seconds, before the former 145-second host-hold deadline.
- Pinned persistent ext4 `sda13` was mounted and its root contract verified at `/run/pmos`.
- Persistent key-only `:2222` opened and the guest public key matched the diagnostic host key.
- At 155.28 seconds the PID 1 handoff was accepted, then refused: `independent recovery guard not armed`. `/run/pmos/run/pid1-guard` was absent and the recorded guard state was `NO_ARMED`. Diagnostic PID 1 and SSH remained. This is the named unarmed-guard stop condition.

Hypothesis, not measured: the unchanged guest transition still requires a guard armed by the prior host-assisted path, so guest-owned keep alone does not arm it. This record does not select or build a successor.

Rollback is verified. `init_boot_a` was restored to `2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28` by a device-op verified flash. Diagnostic boot `84966722-7735-400c-abf9-dd684665f0b9` read stock `boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`, `vbmeta_a cc1926d2…cdffe`, restored `init_boot_a 2f73c947…31c28`, and unchanged `vendor_boot_b f792174c…11095`. The final fastboot gate confirmed the pinned device identity, slot `a`, and unlocked state. Host manifests `parts.sha256`, `parts-a.sha256`, and `parts-b.sha256` were OK. Pstore was empty and dmesg was clean. There was no userdata erase, Android boot, or other partition write.
