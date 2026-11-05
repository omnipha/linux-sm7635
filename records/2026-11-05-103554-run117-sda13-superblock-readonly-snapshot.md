---
date: 2026-11-05
run: 117
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# run 117 sda13 superblock read-only snapshot

Source: coordinator measurement run 117 (2026-11-05 10:27-10:36 UTC), on the
installed, unchanged pair `init_boot_a` `d7bba454…` / `vendor_boot_b`
`221bfd82…` (no flash, no erase, no userdata change, no ACK, no radio, no
`mknod`, no marker write, no stock restore, no Android boot). This is the
coordinator-owned next variable named by the run-116 record: a read-only
read of the `sda13` ext4 features, state and error counters. Private raw
data: `~/phone-second-life-data/mb003/pstore/attempt-20261105-1125-run117-superblock-324/`
(host only, not in Git).

## Measured (device)

- Boot `53bf9af3-bff3-47f5-8d5b-78401cb4002d`, one no-flash `fastboot reboot`
  of the installed pair (10:27:59Z), host capture armed before the reboot.
- Two read-only superblock snapshots of `/dev/block/sda13` through the
  already-existing mode-400 block node over pinned key-only SSH `:2222`,
  taken by BusyBox `dd` (1024 B at offset 1024), base64 over SSH, decoded and
  hashed on the host. The pre-cutover (guest uptime 8 s, diagnostic hold) and
  post-cutover (uptime 194 s, PID 1 `init`, guard armed same boot, not
  accepted, no ACK) snapshots are byte-identical:
  sha256 `88c1849c9d2f9b9dc0513e6fa02d471e14c618390a22a45584d7fc343616a9fd`.
- Decoded superblock: magic `0xef53`; `s_state = 0` (not marked clean, the
  filesystem has not been cleanly unmounted); error behavior
  `s_error_behavior = 1` (continue); `s_error_count = 0`; feature flags
  `compat=0x28` (EXT_ATTR, DIR_INDEX), `incompat=0x2c2`
  (FILETYPE, EXTENTS, 64BIT, FLEX_BG), `ro_compat=0x46b`
  (SPARSE_SUPER, LARGE_FILE, HUGE_FILE, DIR_NLINK, EXTRA_ISIZE,
  METADATA_CSUM).
- Same-boot kernel log (host capture, not pstore): `EXT4-fs (sda13): mounted
  filesystem without journal`; `warning: mounting unchecked fs, running
  e2fsck is recommended`; `re-mounted`; post-cutover `/proc/mounts` root
  `/dev/block/sda13 / ext4 rw,relatime,norecovery`; PID-1 mountinfo root
  `ext4` `8:13` `rw,norecovery`.
- The run-116 marker `/root/.omnipha-persist-marker` (98 B, sha256
  `136b5c51…`) is still present on this third boot of the pair, read
  read-only, not rewritten.
- Natural no-ACK guard return to fastboot (kernel uptime ~315 s); targeted
  fastboot identity after return exact: serial `00181152O003821`, slot a,
  unlocked, product `pineapple`, is-userspace no. Host stock backup
  manifests parts/parts-a/parts-b verified after the run.

## Not measured (stay open)

- Carrier hashes `init_boot_a` / `vendor_boot_b` and slot-A rescue hashes were
  NOT re-read on the device in run 117.
- The `METADATA_CSUM` ro_compat flag is set; the effect of a read-only
  mounted filesystem carrying it on future writable transactions is not
  established by this snapshot.
- Offline journal/fsck policy and clean-unmount behavior remain unmeasured
  (the dossier's offline read-only `e2fsck -fn` path stays separate); no
  journal exists, so there is no replay question on this filesystem.
- The success-gate internet refusal and autonomous radio stages on this boot
  were observed only in the host capture; run 117 performed no WLAN
  acceptance and no ACK.
- Acceptance items 3 (rescue under induced root fault), 4 (hash-pin
  replacement) and 5 (envelope re-read) remain unmeasured.

## Deviations (coordinator process, all recorded on the host status log)

- Preboot pstore pull was omitted; per the owner decision
  (#324 comment 6653556220) no pstore evidence is claimed.
- The first SSH read connected during the pre-cutover diagnostic hold because
  the read script did not fail closed on a missing guard state; its snapshot
  is valid as a pre-cutover observation and happens to be byte-identical to
  the post-cutover one.
- A second read-only probe was executed after a recorded "stop further guest
  probes" note (same constraints, no write); the stop note is therefore
  superseded by that measured action.
- Host-side guard-deadline arithmetic used an arm-time assumption from other
  boots, which the runbook forbids as a lower bound. No deadline-dependent
  claim is made in this record; the boot ended in the observed natural
  guard return and identity was re-verified after it.

## Consequence for the dossier

`docs/strategy/persistent-root.md` next-variable item 1 is now partially
measured: final root mount mode read-write plus filesystem features, state
and error counters from a read-only superblock read. Remaining for item 1:
the semantics of `METADATA_CSUM` on this journal-free rw-mounted root for
writable transactions, carrier-hash re-read via an admissible reader, and
the offline fsck/journal policy. The pair stays installed and
never-reflash; #324 stays open.
