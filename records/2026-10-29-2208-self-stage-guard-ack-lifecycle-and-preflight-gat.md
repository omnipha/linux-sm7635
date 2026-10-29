---
date: 2026-10-29
issue: omnipha/linux-sm7635#173
subsystem: userspace
result: inconclusive
source: README.md
---
## Self-stage guard-ack lifecycle and preflight gate (2026-10-29, #173)

[BOOT.md](BOOT.md#self-stage-guard-ack-lifecycle-and-preflight-gate-173-host-only-2026-10-29)
records the host-only guard-ack reproduction after run 61. The merged `pmos-pid1-guard.sh`, `pmos-pid1-ack.sh` and `pmos-self-post.sh` contract has no code defect: run 61 pinned only `:22` (`172.16.42.2`) and handed off at 42.01 s, before the 155.54 s `switch_root`, with no `[172.16.42.2]:2222` `known_hosts` pin or post-cutover `pmos-pid1-ack.sh` run. `sh scripts/test-pmos-pid1.sh` now also proves that an ack emitted while the `pmos-self-post` waiter is running is accepted before the deadline (`late`) and that an ack written or run after the deadline is never accepted alongside wrong-boot/key/preplanted/symlinked inputs (`stale`). No guest script or image is changed and no marker-only SHA is created (`bee02ce1…`/`41cab142…` and `4b83ea24…`/`1bdb7c22…` stay never-reflash); the coordinator preflight/ready gate now requires the post-cutover waiting line, `pmos-pid1-ack.sh` acceptance and the `pmos-self-post` accepted line before releasing stage markers. #173 stays open for the coordinator-held measurement.
