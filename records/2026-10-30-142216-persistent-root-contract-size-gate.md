---
date: 2026-10-30
issue: omnipha/linux-sm7635#197
subsystem: userspace
result: refuted
---
# Persistent root blocked by the closed #194 size gate

Host-only. No partition, USB, flash or run-66 session operation was performed. The hypothesis that the installed run-66 init can switch directly to a persistent `PARTNAME=userdata` ext4 root under the closed #194 contract is refuted before an image pair is published.

`scripts/pmos-root-contract.sh` (`1930890dab5c7d7b064b6b2d312cc735d5ba5966f186eaf112d9dd01bb519457`) accepts an ext4 root only when `blockdev --getsize64` reports `33554432..137438953472` bytes. The host reference for the same phone reports `partition-size:userdata: 0x3835DB3000`, which is `241421725696` bytes. That is `103982772224` bytes above the unchanged maximum, so `root_contract_pinned_userdata` returns failure before promotion, staging or `switch_root`.

The same gate is reached after switching: `root_contract_switched_root` derives the size from the block node or from `sysfs size * 512` and applies the same maximum. A filesystem whose own superblock is smaller does not change the partition size returned by `blockdev`. The measured 32 MiB archive carrier worked because its scripts checked only a minimum image size; the #194 root-type contract adds the upper bound. Raising that bound would change the closed contract rather than consume it, so no distinct init_boot is accepted.

The unpacked postmarketOS filesystem itself is not the blocker. A deterministic 100,663,296-byte ext4 image can be built from archive `7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26`, and a direct-root init fits the 8,388,608-byte envelope. Neither is a flash candidate while the required root check rejects the measured partition. No new image SHA is published.
