---
date: 2026-10-30
issue: linux-sm7635#194
subsystem: userspace
result: confirmed
---
# Host root-type contract and fixtures complete

Host-only #194 is complete in the clean worktree without building or flashing an image, touching a partition, using USB, or accessing any live session. The host-owned `/run/keep` hold, 145/150 s recovery budget, host-verified capture marker gate, diagnostic `:22`, pinned `:2222`, and `wlan-udhcpc-lease.sh` remain unchanged.

## Coherent root-type contract and script/hash deltas

Together with PR #195 (`26474b5`), `scripts/pmos-root-contract.sh` (`1930890dab5c7d7b064b6b2d312cc735d5ba5966f186eaf112d9dd01bb519457`) defines one root-type rule across stage, teardown, transition, guard, ack, self-post, radio bring-up, and self-stage: the guest root is either the measured private 256m `tmpfs` or one non-symlink `ext4` mount of the single `PARTNAME=userdata` block, pinned `ro,noload` first and promoted `rw` only after its sysfs `PARTNAME`, `major:minor`, size (`33554432..137438953472` bytes), private propagation, and single-mount identity are verified, while `/run`, `/dev` and `/dev/pts` remain separate `tmpfs`/`devpts` mounts.

| script | SHA-256 | required delta |
| --- | --- | --- |
| `scripts/pmos-root-contract.sh` | `1930890dab5c7d7b064b6b2d312cc735d5ba5966f186eaf112d9dd01bb519457` | Shared `root_contract_pinned_userdata`, `root_contract_promote`, `root_contract_stage_root`, and `root_contract_switched_root` checks |
| `scripts/pmos-session-stage.sh` | `be70a27305145cabc15b70469ae7a0434fab352fb9c3d681943f73d22b92938a` | Pin `ro,noload` `userdata` ext4 before `rw` promotion and stage read-only `/dev/block/$part` inside guest `/dev` tmpfs |
| `scripts/pmos-session-teardown.sh` | `dc4f1d2f5fca029836aa7fda12502bf05e0f65d06254630086e126a1aa285ab2` | Permit teardown of either 256m `tmpfs` or pinned `PARTNAME=userdata` `ext4` guest root while preserving child-mount order |
| `scripts/pmos-pid1-transition.sh` | `176422c5536025749d9ffdd306df7ff2dfdd213be0674b24bb4fff4775f8b415` | Validate staged root via `root_contract_stage_root` and pin updated `GUARD_SHA256` |
| `scripts/pmos-pid1-guard.sh` | `2a92fbcfe029ec3be1af8b73d4cd8d0ac317ecd267a9dc9ba9637932207d5da3` | Require `tmpfs` or pinned `userdata` `ext4` at arm and in post-cutover `post_root()` via staged `root-contract.sh` |
| `scripts/pmos-pid1-ack.sh` | `230d7aa93f205491acd187c362c6cd7413a65eae1b4af885865ee904f4ff06af` | Verify post-cutover `/` is `tmpfs` or `root_contract_switched_root`-verified `ext4` before writing ack |
| `scripts/pmos-self-post.sh` | `2d5847f38d6c58e4ac048cfb628dbe8e8b530df8522316d6ce0f1129758ce17a` | Accept `tmpfs` or `$GUARD/root-contract.sh`-verified `ext4` on `/` after cutover and pin `RADIO_SHA` |
| `scripts/pmos-radio-bringup.sh` | `04fe93d76c5048122f1a413457c0e0f1b1abd13f78f3518d8bb12abb18762dd1` | Accept `tmpfs` or `root-contract.sh`-verified `ext4` in `prepare` and post-cutover stages |
| `scripts/pmos-self-stage.sh` | `fec98717681aba52e64344a4dba43f6bdf8907c3f11aaab10e9bfd46530afa92` | Pin updated `STAGE_SHA`, `TRANSITION_SHA`, `GUARD_SHA`, and `RADIO_SHA` with unchanged 145 s host hold wait |

## Host fixture verification

- `sh scripts/test-pmos-root-contract.sh` (`be81717ee472361d83436329294388a627033021cef9aaecbd9ccf802a1b73e0`): pass (`inner`, `ext4-ack` including `pmos-pid1-ack.sh`, `pmos-self-post.sh` and `pmos-radio-bringup.sh` wrong-`PARTNAME` rejection and valid `PARTNAME=userdata` acceptance after real `switch_root`, and `ext4-timeout` guard recovery).
- `sh scripts/test-pmos-self-stage.sh` (`490ecd88b95ce27c6ef1ea66db65da16fb0ff1db956b10f3e13184812d0a619d`): pass (including `test-pmos-reboot-hold.sh`).
- `sh scripts/test-pmos-radio-bringup.sh`: pass.
- `sh scripts/test-pmos-session-dev.sh`: pass.
- `sh scripts/test-pmos-pid1.sh`: pass (`ack`, `late`, `stale`, `timeout`, `preplanted`, `symlinked`).
- `sh scripts/test-alpine-session.sh`: pass.
