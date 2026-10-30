---
date: 2026-10-30
issue: omnipha/linux-sm7635#199
subsystem: userspace
result: confirmed
---
# Measured userdata size accepted by the fail-closed root contract

Host-only: `partition-size:userdata: 0x3835DB3000` is 241421725696 bytes. The #194 maximum of 137438953472 bytes was a constant, not a dependency of a named isolation or recovery guarantee. The only production delta is `ROOT_CONTRACT_MAX_BYTES=241421725696` in `scripts/pmos-root-contract.sh`; the 33554432-byte minimum and both the pre-promotion and post-`switch_root` size checks are unchanged. Larger blocks are still refused.

| file | before SHA-256 | after SHA-256 | delta |
| --- | --- | --- | --- |
| `scripts/pmos-root-contract.sh` | `1930890dab5c7d7b064b6b2d312cc735d5ba5966f186eaf112d9dd01bb519457` | `2e95e9d3bef9b38dc71bd132f7054f0a558208800b8e918a34e7b0ec20a5c94c` | The inclusive maximum only; no identity, ancestry, filesystem, symlink, recovery or switched-root check changed. |
| `scripts/test-pmos-root-contract.sh` | `be81717ee472361d83436329294388a627033021cef9aaecbd9ccf802a1b73e0` | `fa3cc5e2c8abaa1a97bcc1f252cc4d243882569414ea9f256feb65972e26081b` | Sparse loop ext4 fixture with a real 241421725696-byte node, a separate oversize node, explicit 241421725697-byte size-report rejection, and one-byte-under-minimum and post-switch first-sector-over-limit rejection. |

`sh scripts/test-pmos-root-contract.sh` passed: exact measured-size node accepted (ro,noload -> rw promotion, stage, guard, transition, real PID 1 `switch_root`, ack, self-post, radio and teardown); existing wrong filesystem, duplicate/missing/wrong `PARTNAME`, wrong device, symlink, shared mount and recovery negatives still reject. The real oversize block and a one-byte-over-maximum comparison reject. Since loop block nodes are sector-sized, the separate real oversize block is 512 bytes over the maximum; a bounded BusyBox blockdev shim reports 241421725697 bytes for that otherwise valid node and it rejects, as does a one-byte-lower bound against the measured node. After teardown, the switched-root sysfs fallback is tested with no block node and 471526809 sectors (241421726208 bytes); it rejects the first sector over the maximum. The `ext4-timeout` test requests only pinned mock recovery.

`sh scripts/test-pmos-self-stage.sh`, `sh scripts/test-pmos-radio-bringup.sh`, `sh scripts/test-pmos-session-dev.sh`, `sh scripts/test-pmos-pid1.sh` and `sh scripts/test-alpine-session.sh` passed. `git diff --check` and `sh -n` on both changed scripts passed. No image was built or published; no partition, USB, marker, reboot, flash, open session or credential was touched. This removes the #197 host size-gate blocker, not a claim of device acceptance.
