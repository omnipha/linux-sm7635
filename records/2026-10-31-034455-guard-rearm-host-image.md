---
date: 2026-10-31
issue: omnipha/linux-sm7635#220
subsystem: boot
result: confirmed
---
# Guard rearm on persistent root: host fixture and image

Host-only change and verification. No USB, device, flash, reboot, SSH, session, or partition operation was performed. The physical image gate remains unverified; this is a coordinator handoff, not a boot result.

The old guard fixture was first reconstructed with the prior `guard or RESTART2 already exists` precondition. On a staged loop-backed ext4 root with the pinned `/run/pmos/bin/restart2`, it refused exactly at that check and the transition emitted `independent recovery guard not armed` (`NO_ARMED`). This matches the measured run-69 boundary. The new guard accepts only a regular, root-owned, mode-0755, single-link, 872-byte helper with SHA-256 `fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7`; it reuses that helper instead of copying it again. Foreign or modified content, symlink, hard link, unsafe mode, and pre-existing or symlinked guard state still fail closed. Root identity, device model, the independent 160-second deadline, host-ack semantics, and the no-guest-ack behavior are unchanged.

Host tests passed: `test-pmos-root-contract.sh` (old refusal reproduction, reuse validation, refusal matrix, ext4 ack and timeout), `test-pmos-pid1.sh` (ack, late, stale, timeout, preplanted, symlinked), `test-pmos-self-stage.sh`, and shell syntax checks. `test-pmos-pid1-request.sh` was also checked at `origin/main` with these scripts stashed and fails there with `pinned transition script unavailable`; it is an old historical transition-pin fixture, not a new regression. Records CI remains the required repository check.

Two serial reproducible builds were byte-identical. Exact candidate IDs:

- `init_boot-guard-rearm.img`: 8388608 bytes, SHA-256 `3eeddb35eb32b29323f50bab673c7acc36b029373e911eb4d74a3aa180236522`.
- `vendor_boot_b-guard-rearm.img`: 100663296 bytes, SHA-256 `762566b758494c53b0265ce7eee13155c6d06b9cca44f8c5eb75ce7cb8fc4e5d`.
- Decoded bundle: 18964 bytes, SHA-256 `51235e01a40a017a3e3743c98e4d05fd5d9f15311a7aefda3f70f0ac51f22950`; LZ4 HC-12 frame 2100064/2117632 bytes. Stock header and signed tail are unchanged.
- Persistent userdata root unchanged: 100663296 bytes, SHA-256 `aa8da109d3bff4657da2b0504e61856744ced3392dafad81707b1aed10bac5a5`.

Decoded change relative to the installed run-69 chain: only the guard helper reuse/refusal block and its required digest pins changed. The guard SHA is `f72a68a4c3a0e9bb7e72aa88883dcc9087a684985f5af688e34ea13c0226d3ad`; the transition pin changes from `2a92fbcf…` to that digest. Self-stage carries the updated guard/transition pins. The helper itself, recovery deadline, ack protocol, keep behavior, and persistent root contract are unchanged. The guard bundle is carried in both approved carriers, so both image IDs change; no userdata image was built or written. The verifier rejects all previously measured image IDs, including never-reflash run-72 `3c97c918…bc71a`, run-69 `2f73c947…31c28`, and the previous carrier `f792174c…11095`.

Coordinator handoff under standing `full_autonomy_device_iteration`: measure only this new `init_boot_a` and `vendor_boot_b` pair, never `3c97c918…bc71a`; do not rewrite userdata, `boot_a`, `vendor_boot_a`, `dtbo_a`, `vbmeta_a`, or relock. Boot without host-created `/run/keep`, guard ack, or capture release. Record guest keep, self-stage past the former deadline, pinned ext4 root verification, exact arm precondition, armed guard state, `switch_root`, postmarketOS PID 1, and `:2222`. Expected success is host-free PID 1 with an armed guard; without an ack the independent 160-second deadline should return to fastboot, which must be recorded. Stop on wrong root, any arm refusal, missing keep/self-stage, unauthorized write, or missing recovery return. Then roll back exactly to installed `init_boot_a 2f73c947…31c28` and `vendor_boot_b f792174c…11095`, verify readback and untouched stock rescue hashes. The coordinator owns the bounded session and closure; the worker will read committed evidence and record the result separately.
