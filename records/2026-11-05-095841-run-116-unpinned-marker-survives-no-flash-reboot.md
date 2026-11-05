---
date: 2026-11-05
run: 116
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# run 116 unpinned marker survives no flash reboot

Source: coordinator measurement comment on #324
(https://github.com/omnipha/linux-sm7635/issues/324#issuecomment-6654794020,
2026-11-05 09:45 UTC), covering run 116 (2026-11-05 09:32-09:44 UTC). This
record transcribes that comment. The raw captures remain outside Git on the
coordinator host and are not copied here or re-verified by this record. No
device action was taken for it.

## Evidence classes

- **Device measurement (coordinator, reported in the comment):** everything
  under "Measured" below.
- **Installed artifacts:** `init_boot_a` `d7bba454…` and `vendor_boot_b`
  `221bfd82…`, reported unchanged. They were not re-read on the device during
  run 116 (see Not measured), so "unchanged" rests on no flash having occurred.
- **Host tests:** none. This record adds no host test and no host claim.

## Measured

- No flash, erase, ACK, radio action, `mknod`, partition hash, stock restore
  or Android in run 116.
- Boot 1 (`e3af385f-1117-4dd6-8435-252c34929847`): capture armed before
  `fastboot reboot` (09:32:08Z) and connected on :22. The marker
  `/root/.omnipha-persist-marker` (98 bytes) was written in one pinned SSH
  call on :2222 at guest uptime about 206 s, sha256
  `136b5c5122e750138e5fa420dda2b0e23233b6c0a3b0dcf2d96ae741b28d2420`, and
  read back identical. Root: `/dev/block/sda13 / ext4 rw,relatime,norecovery`.
  Natural no-ACK guard return to fastboot at 09:37:54Z, targeted identity
  exact.
- Boot 2 (`58c40d9a-2552-48f8-9063-94edca098482`), no flash, capture armed
  before reboot (09:38:36Z): the same file present, 98 bytes, identical
  content and sha256. Root again `ext4 rw,relatime,norecovery` on `sda13`.
  Natural guard return at 09:44:22Z, targeted identity exact (slot a,
  unlocked, product pineapple, userspace no).
- Result as reported: an unpinned file created on the installed root survives
  one no-flash reboot, even though boot 1 ended in the guard's unclean
  bootloader return. The root is read-write.

## #324 acceptance items

- **1 Survival without flash: measured partially.** One marker survived one
  no-flash reboot with identical sha256. Not covered: "installed carrier
  hashes unchanged before/after" (not re-read), and any repeat or clean
  shutdown.
- **2 Read-write root with a defined journal/fsck policy: rw mount observed;
  policy NOT measured.** Mount options were seen on both boots. Journal
  behavior, fsck policy, ext4 features, clean state and error counters were
  not read.
- **3 USB SSH rescue under an induced, reversible root fault: unmeasured.**
- **4 Replacement of the hash pins (provenance-checked update with rollback):
  unmeasured.** No replacement pair exists and none was built.
- **5 Envelope items not re-read on the device: unmeasured in this run.**
  Carrier hashes were not re-read; no other envelope item was re-read either.
  The comment reports targeted fastboot identity exact at both guard returns
  and no write outside the marker, but it reports no re-read of the three
  pinned userland files, guard or nonce state, or the altered radio file.

## Caveats stated by the coordinator, not claimed here

- Carrier hashes were not re-read on the device (no admissible read-only
  reader).
- ext4 features, clean state and error counters were not read.
- The guest has no `sync` binary, so durability rests only on the observed
  survival.
- The marker timestamp is 1970 because the guest clock is unset.
- Process deviation: the background helper script died with its exec shell,
  so the boot-1 write was a direct manual one-call SSH with the same content
  as the script.
- The guard-arm lower bound was not needed per owner instruction (boot-1
  pstore loss accepted, #324 comment 6653556220).

## Consequence for the dossier

The `docs/strategy/persistent-root.md` fallback (root stays read-only, or an
unpinned file does not survive) did not trigger. The pair stays installed and
never-reflash, no replacement pair is built, and #324 stays open. The
dossier's remaining unmeasured items are listed in its "Next single variable"
section.
