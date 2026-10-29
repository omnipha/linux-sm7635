---
date: 2026-10-29
issue: omnipha/linux-sm7635#171
subsystem: userspace
result: inconclusive
source: BOOT.md
---
## Host-only `recovery_b` self-stage payload and init (#171, 2026-10-29)

**Host-only — no flash, partition write, USB session or phone result. #171 stays OPEN for the coordinator-held reboot measurement.** Following `docs/partition-policy.md`, the approved carriers after measured `vendor_boot_b` are `recovery_b`, then `dtbo_b`, then `userdata`. In the read-only host backup and by-name record, `recovery_b` (`/dev/block/sde53`, SHA-256 `6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b`) is 104,857,600 bytes (`>= 100,663,296`), while `dtbo_b` (`/dev/block/sde44`) is 25,165,824 bytes and cannot hold the layout. `recovery_b` is the first carrier that fits, so the 225 GB `userdata` wipe is not spent.

`scripts/build-recovery-b-userspace-payload.sh` and `scripts/build-recovery-b-userspace-payload.py` reuse the #164 payload window unchanged on stock `recovery_b`: the signed prefix `[0, 15616192)` (header v4, LZ4 ramdisk, `AVB0` at `15,613,952` of 2,240 bytes) and terminal 64-byte `AVBf` footer are preserved, the 4,096-byte header (`2d09f260…`) sits at `18,870,272`, and the 23,713,302-byte postmarketOS archive (`7a76a110…`) sits at `[18874368, 42587670)`. Two serial builds under `flock` produce `$WORK/out/recovery_b-userspace.img` (104,857,600 bytes, SHA-256 `41cab142203b4ccf894f7bea24398d21ff959ab72d3473e88379d2780bdc9afd`).

`scripts/pmos-self-stage.sh` changes from the measured #164 script (`356d8792…`) only by switching `PARTNAME=vendor_boot_b` and `PART_SIZE=100663296` to `PARTNAME=recovery_b` and `PART_SIZE=104857600`. The 150 s `/run/keep` guard, 145 s hold wait, 151.01 s handoff settle, 160 s host-owned guard ack, hash pins and fail-closed checks are unchanged; `scripts/build-init-boot-self-stage.sh` builds `$WORK/out/init_boot-self-stage-recovery-b.img` (8,388,608 bytes, SHA-256 `bee02ce1f31d628fd95879fb519d4b131f3d8a3298530d1fc31c390db528f412` on the current local inputs). `scripts/verify-init-boot-self-stage.py` and `scripts/verify-bootimg.sh init-boot-self-stage --fixture` reject `4b83ea24c305d731b168c2e2f12bd0ebd5d4a18de9039eaf8b0e0ca452b464f7`, `1bdb7c2252b3192127aed0a2f8953d928be0f36a00a259582e7a75a98a029f5f`, `fef030081e04d3a90451bb7d64dcfa7668c41dc4248e6e0b1959fdb40efce948`, `baa33fd4…`, `6065f685…`, the old `vendor_boot_b` carrier, and marker-only deltas. Against the unchanged 150 s guard, the measured ~17 s reboot gadget gap plus immediate udev re-addressing leaves over 120 s inside the 145 s `/run/keep` wait; a userspace timer does not cover a kernel hang. No profile or scan data is in Git.
