---
date: 2026-10-31
issue: omnipha/linux-sm7635#223
subsystem: boot
result: confirmed
---
# Cold-start run-66 handoff preserved and re-verified

Host-only repair and re-verification. No USB, device, flash, reboot, SSH, session, partition, scheduling, or power operation was performed. This is not a cold-start measurement and does not schedule one.

The run-76 refusal was reproduced and explained without touching the device. The coordinator's verifier ran from `/home/gregor/github_repos/omnipha/linux-sm7635` checked out on the stale branch `records/run69-second-boot-guard-refused` (commit `3b5c3a5`), not merged `main`. Re-running that stale checkout's `scripts/verify-init-boot-persistent-root.py --self-test` against the saved PR #225 pair (`becd3784…e72b4` / `adb47dc0…aeae8`), stock backups, and pinned run-66 base `5b5a60d4…8466d6` reproduces `FAIL: init must keep the measured run-66 handoff and change only the root-contract pin` exactly. The identical command on merged `main` (this tree, `ab299cff`) accepts the same pair. The run-76 gate therefore used a pre-#225 verifier with the pre-#225 pinned script digests; the pair itself keeps the measured run-66 handoff.

Two hardening changes keep this class of mismatch visible on every future build, without weakening any run-66 pin:

- `expected_init` now requires the post-hook init tail, the measured run-66 PID-1 handoff including its `151.01` settle timer, to contain the old transition pin exactly once and carries that tail through byte-for-byte; only the pinned transition digest is replaced.
- The self-test adds two negatives: any change to the run-66 settle timer and any alteration of the `PID1_SHA256` pin are refused with the same INIT_MSG.

The post-cutover observation line is reworded to `cold-start post-cutover PID 1 on boot <id>; independent recovery guard remains unacknowledged` so the successor pair is distinct, keeping guest-owned keep, safe prior-`restart2` guard re-arm, the persistent ext4 root contract, key-only `:2222`, nonce-bound guest radio markers, and the unchanged independent 160-second no-ack recovery.

Two serial builds were byte-identical. Exact new candidate IDs, outside Git:

- `init_boot-coldstart-verified.img`: 8388608 bytes, SHA-256 `3192278b93812ff14cf7d71d4f8bae60a7e00d178c194155fc336817a6c4bcdf`.
- `vendor_boot_b-coldstart-verified.img`: 100663296 bytes, SHA-256 `ab3a0e6360269d1e56d14626e6849b8249634810895f5270283ed30ebdb4a5a9`.
- Decoded cpio 3682816 bytes; reproducible LZ4 HC-12 frame 2100059/2117632 bytes; stock header and signed tail unchanged.
- Persistent userdata root unchanged: 100663296 bytes, SHA-256 `aa8da109d3bff4657da2b0504e61856744ced3392dafad81707b1aed10bac5a5`.

Verified in this tree: the merged `verify-init-boot-persistent-root.py --self-test` accepts the new pair, refuses installed `2f73c947…31c28` / `f792174c…11095`, run-72 `3c97c918…bc71a`, run-73 `3eeddb35…6522` / `762566b7…fc4e5d`, the refused run-74 `867330e5…0030` and run-76 `becd3784…e72b4` / `adb47dc0…aeae8` candidates, and every earlier measured image (72 refused hashes). Host stock manifests `parts.sha256`, `parts-a.sha256`, and `parts-b.sha256` all verified. Isolated fixtures passed: self-stage/reboot-hold, radio nonce-bound marker stages, root-contract ext4 arm/ack/timeout, and PID-1 ack, late, stale, timeout, preplanted, and symlinked cases.

Coordinator handoff under standing `full_autonomy_device_iteration`: run the verifier from merged `main` at commit `ab299cff` or later for this pair, never from a stale worktree. Write only this new `init_boot_a` and `vendor_boot_b` pair; do not rewrite userdata or any other partition and do not reflash any refused image. Then perform the issue's single button-assisted cold start with no USB host signals until the boot has had its chance, and record each ordered observation line or the exact first missing line, with outcome (a), (b), or (c) and the rescue readback proof as in the issue. The coordinator owns that one measurement; this record does not claim it.
