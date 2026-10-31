---
date: 2026-10-31
issue: omnipha/linux-sm7635#216
subsystem: boot
result: confirmed
---
# Guest-owned keep host image

Host-only image delta. No USB, flash, reboot, SSH, session, or partition operation was performed.

The installed run-69 carrier stays byte-identical:

- `init_boot`: 8388608 bytes, SHA-256 `3c97c918ed085d6d72530f00bba81c053130c184d351f372a10ac11b616bc71a`; LZ4 HC-12 frame 2100064/2117632 bytes.
- `vendor_boot_b`: 100663296 bytes, SHA-256 `f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095`.
- persistent userdata root unchanged: 100663296 bytes, SHA-256 `aa8da109d3bff4657da2b0504e61856744ced3392dafad81707b1aed10bac5a5`.

The only decoded `/init` difference from the independently rebuilt installed image `2f73c947…31c28` is five lines immediately before launching `pmos-self-stage.sh`. If `/run/keep` is absent, init creates a regular root-only file (owner 0, mode 600, one hard link) and verifies it before launch. A pre-existing keep, symlink, failed create/protect, or failed verification stops the hook before self-stage. The carrier bundle, scripts, guard, ack, capture, radio, timers, stock header, and signed tail are unchanged.

Two serial builds were byte-identical. The verifier rejected removed keep creation, mode 644, acceptance of a pre-existing keep, and keep creation after self-stage. Removing the five lines reconstructed the installed `2f73c947…31c28` image, which the verifier refused. Existing self-stage and reboot-hold fixtures passed. Both images stay outside Git. No physical boot was attempted.

Coordinator measurement handoff: flash only `init_boot_a` with `3c97c918…bc71a`. Do not flash or rewrite `vendor_boot_b`, userdata, or slot A. Boot without creating `/run/keep`, writing a guard ack, or releasing a capture marker. Expected evidence is the guest-owned-keep kmsg line, self-stage past the former hold deadline, persistent ext4 root, postmarketOS PID 1, and an armed guard. Stop on a missing keep line, self-stage failure, wrong root, unarmed guard, or any partition write beyond this init_boot. Then verify rollback to `init_boot_a 2f73c947…31c28` and unchanged `vendor_boot_b f792174c…11095`; stop if either readback differs. WLAN and the button-assisted cold start are outside this measurement.
