---
date: 2026-10-30
issue: linux-sm7635#194
subsystem: userspace
result: inconclusive
---
# Host root-type contract fixture and foreign-path block

No image was built or flashed, no partition or USB operation occurred, and the run-66 session was not touched after the correction made #194 host-only again. All existing worktree changes remain. The foreign paths `scripts/pmos-radio-bringup.sh`, `scripts/pmos-self-post.sh`, `scripts/pmos-self-stage.sh`, `scripts/test-pmos-radio-bringup.sh`, `scripts/test-pmos-self-stage.sh`, `scripts/wlan-udhcpc-lease.sh`, and `scripts/__pycache__/` were not edited, reset, stashed, overwritten, or committed.

## Owned-path contract

The #194-owned draft in `scripts/pmos-root-contract.sh` accepts either the measured private 256m tmpfs root or one non-symlink ext4 mount of exactly one `PARTNAME=userdata` block. It requires the block node major:minor to match sysfs, size between 33554432 and 137438953472 bytes, one matching mount with no shared/slave/unbindable propagation, and no duplicate mount of the same source/device. The ext4 root must be `ro,noload` at pin time and only then remounts `rw`; `/run`, `/dev` and `/dev/pts` remain separate tmpfs/devpts mounts. Switched-root checks apply the same identity rule to `/`.

The owned edits wire that contract into `scripts/pmos-session-stage.sh`, `scripts/pmos-session-teardown.sh`, and `scripts/pmos-pid1-transition.sh`. Guard arm verifies a non-tmpfs root before arming and copies the root contract into protected guard state for the post-cutover check. Ack's remote probe uses the same contract for an ext4 switched root. Current owned-path hashes are:

| path | current SHA-256 |
| --- | --- |
| `scripts/pmos-root-contract.sh` | `1930890dab5c7d7b064b6b2d312cc735d5ba5966f186eaf112d9dd01bb519457` |
| `scripts/pmos-session-stage.sh` | `be70a27305145cabc15b70469ae7a0434fab352fb9c3d681943f73d22b92938a` |
| `scripts/pmos-session-teardown.sh` | `dc4f1d2f5fca029836aa7fda12502bf05e0f65d06254630086e126a1aa285ab2` |
| `scripts/pmos-pid1-transition.sh` | `176422c5536025749d9ffdd306df7ff2dfdd213be0674b24bb4fff4775f8b415` |
| `scripts/pmos-pid1-guard.sh` | `2a92fbcfe029ec3be1af8b73d4cd8d0ac317ecd267a9dc9ba9637932207d5da3` |
| `scripts/pmos-pid1-ack.sh` | `230d7aa93f205491acd187c362c6cd7413a65eae1b4af885865ee904f4ff06af` |
| `scripts/test-pmos-root-contract.sh` | `2a2881055411e008d72b3916ffcf8a32001197ef135e31fdc70e7bb98a4ff07b` |

These are owned-path hashes only, not image inputs or a new reviewed image delta. No image hash was added.

## Host-only verification

`sh scripts/test-pmos-root-contract.sh` passed a host-local loop/namespace fixture: one pinned ext4 userdata root was accepted after `ro,noload` identity pinning, promoted to `rw`, staged with separate tmpfs `/run`, tmpfs `/dev` (including the read-only non-symlink `/dev/block/sda13` userdata block node) and private devpts `/dev/pts`; transition and guard arm were exercised with a non-target-host guard failure, switched-root checks accepted the pinned ext4 case, teardown succeeded, and two isolated real-PID-1 `switch_root` subtests (`ext4-ack` and `ext4-timeout`) passed on the loop-backed ext4 root (`ext4-ack` rejected a mutated `PARTNAME=super` over strict key-only SSH before accepting `PARTNAME=userdata`, and `ext4-timeout` verified mock recovery on an unacknowledged ext4 switched root). Duplicate/missing/wrong `PARTNAME`, mismatched block identity, symlinked node, size bounds, unpinned `rw`, missing `noload`, shared propagation, duplicate mount, wrong switched-root source/type, and switched shared propagation were rejected.

`sh scripts/test-pmos-pid1.sh` passed all six existing tmpfs cases: ack, late, stale, timeout, preplanted, symlinked. Shell syntax checks passed for the owned scripts.

The complete acceptance criteria are not delivered because foreign edits remain in paths required by the contract and retained tests:

* `scripts/test-pmos-self-stage.sh` fails before its namespace fixture with `FAIL: session stage pin changed`: the owned stage hash changed as required by #194, but the foreign self-stage script and fixture still pin the old script hashes and the self-post/radio hash chain cannot be updated without touching those paths.
* `scripts/test-pmos-session-dev.sh` reaches teardown and fails `umount: can't unmount /run/pmos/dev: Device or resource busy` after the WLAN service sequence. The foreign `scripts/wlan-udhcpc-lease.sh` change starts a second Dropbear on the guest WLAN address with `/run/dropbear-wlan.pid`; the existing teardown only owns `/run/dropbear-session.pid`. This is a foreign-path test regression and also conflicts with the contract's both-SSH-listener isolation guarantee. No fix was applied to that path.
* The foreign `scripts/pmos-self-stage.sh` auto-creates `/run/keep` at the 145 s deadline, contrary to #194's host-owned hold requirement; `scripts/pmos-self-post.sh` self-releases the capture marker after 30 s, contrary to the host-verified capture requirement. Those paths cannot be corrected here.

Therefore this record is inconclusive: the owned root-type helper and its new fixture pass, and the existing tmpfs PID-1 suite passes, but #194's full cross-script contract, retained self-stage/radio tests, and exact reviewed script/hash delta cannot be completed while the foreign paths must remain untouched. No PR or merge was created and no device acceptance is claimed.
