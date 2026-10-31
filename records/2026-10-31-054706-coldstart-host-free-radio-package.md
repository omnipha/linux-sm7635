---
date: 2026-10-31
issue: omnipha/linux-sm7635#223
subsystem: boot
result: confirmed
---
# Cold-start host-free radio package

Host-only correction and verification. No USB, device, flash, reboot, SSH, session, partition, scheduling, or power operation was performed. This is not a cold-start measurement.

The earlier host record correctly refuted the unchanged installed run-69 chain. This successor resolves that contradiction without rewriting the persistent userdata root or changing the independent 160-second guard. Guest-owned `/run/keep`, safe reuse of the pinned prior `restart2`, persistent ext4 verification, `switch_root`, and key-only `:2222` remain. Post-cutover radio no longer waits for a host guard ack or a host capture release. It requires the current-boot armed guard, its nonce, and no acceptance or ack file, then publishes one nonce-bound guest marker per modem, WPSS, driver, scan, and services stage. Each marker must be root-only and appear exactly once in this boot's kmsg. The markers are guest self-attestation, not an external host proof.

The recovery contract is unchanged. No host ack still means the independent 160-second deadline requests bootloader return. Radio is attempted inside that budget, but this host package does not prove that modem, WPSS, WLAN association, and SSH all finish before it. If the deadline returns first, that remains designed bounded recovery and the exact first missing radio line must be reported. Display and every excluded function remain untouched.

Two serial builds were byte-identical. Exact new candidate IDs, outside Git:

- `init_boot-coldstart-hostfree.img`: 8388608 bytes, SHA-256 `becd37846fedd0d4298cf562667fd498f76a5c99e2e68810ca5cacf8c1ee72b4`.
- `vendor_boot_b-coldstart-hostfree.img`: 100663296 bytes, SHA-256 `adb47dc0228cdbb1ba57dd245ecec49386d53bf24c3ab8f72493e709b78aeae8`.
- Decoded cpio 3682816 bytes; reproducible LZ4 HC-12 frame 2100063/2117632 bytes; stock header and signed tail unchanged.
- Persistent userdata root remains 100663296 bytes, SHA-256 `aa8da109d3bff4657da2b0504e61856744ced3392dafad81707b1aed10bac5a5`.

The verifier refuses installed `2f73c947…31c28`, `f792174c…11095`, run 72 `3c97c918…bc71a`, run 73 `3eeddb35…6522` and `762566b7…fc4e5d`, plus every earlier measured image. Host tests passed: persistent-root negative mutations, self-stage and reboot-hold, radio stages and nonce-substitution refusals, root-contract ext4 arm/ack/timeout, and PID-1 ack, late, stale, timeout, preplanted, and symlinked recovery cases.

Coordinator handoff under standing `full_autonomy_device_iteration`: write only this new `init_boot_a` and `vendor_boot_b` pair. Do not rewrite userdata or any other partition, and do not reflash any refused image. Then perform the issue's single cold start: complete power-off, one operator power-button press, and no host hold, guard ack, capture release, or push until the boot has had its chance. Record guest-owned keep, self-stage, persistent ext4 verification, armed unacknowledged guard, `switch_root`, postmarketOS PID 1, radio, MINDSTORMS association, and key-only `:2222`, or the exact first missing line. Outcome (a) includes a no-ack 160-second return to responsive fastboot as designed recovery. Outcome (b) stops at the named line. Outcome (c), never enumerating, is the stop boundary. Stop on any unauthorized write, guard-arm refusal, or rescue-path loss. Afterwards read back both new hashes and untouched stock slot-A `boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`, and `vbmeta_a cc1926d2…cdffe`. The coordinator owns that one measurement; this record does not claim it.
