---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# persistent root self-heal, host rescue fixture, fsck policy and carrier-reader candidate

Host-only work for the coordinator successors in #324 comments 6656161100
(run 118) and 6656429896 (run 119). No boot, flash, reboot, remount of a
device, adb, fastboot, USB, session or userdata change. The installed pair
`init_boot_a` `d7bba454…` / `vendor_boot_b` `221bfd82…` is untouched and
never-reflash. Nothing here is a device measurement.

## Source reading (not measured)

Read from `current_scripts()` of `scripts/build-init-boot-persistent-root.py`
applied to `scripts/pmos-session-stage.sh`, plus `pmos-self-stage.sh`,
`pmos-pid1-transition.sh` and `pmos-root-contract.sh`. Generated session-stage
line numbers below are from that generation.

- Order in the persistent session-stage: `root_contract_pinned_userdata`
  (line 57), then `root_contract_promote` (line 58, `mount -o remount,rw`,
  `pmos-root-contract.sh:398`), then `boot_record_open` (line 71), then the
  `usr/lib/os-release` check (lines 124-125). The root is therefore promoted
  read-write before that check, not after it.
- Run 119 assumed the root stays `ro,noload` until the cutover. The code does
  not support that for this fault: a missing `os-release` makes session-stage
  `die` after the promotion. The resulting mount mode, diagnostic `:22`
  reachability and deadline behavior after that failure are not measured. The
  PID 1 guard is armed only at `pmos-pid1-transition.sh:155`, so by the code
  it is not armed on this failure. The 150 s init timer only tests for
  `/run/keep` when it wakes, and the hold file already exists, so it ends
  without action. By the code, no guard or timer would then be active, which
  would make "same-boot guard evidence" impossible for this fault path; that is
  unmeasured. Whether a remount is needed for a rescue is therefore open, not
  established.
- The generator line for the session-stage call is
  `scripts/build-init-boot-persistent-root.py:528`; it emits a line of the
  generated self-stage, not of the source file.
- Rewritten on every pass that reaches them: `/etc/inittab` (lines 187-188),
  `/etc/shadow` (201-202), `authorized_keys` (196-200). `/sbin/init` and the
  `local` runlevel link are created only if absent (line 184 for `init`); a
  wrong or broken existing link is not replaced and fails the check.
  `usr/lib/os-release` and `/sbin/openrc` are only checked, never recreated.
  The ephemeral `session_host_key` is deleted and regenerated, and deferred
  `wpa_supplicant`/`networking` runlevel links are removed. So not every
  required file self-heals.
- Self-heal of `inittab` content is not proof the boot completes.

## Host fixture

`scripts/test-pmos-rescue-restore.sh` runs in a private mount namespace on a
fresh 32 MiB image and a verified loop, with the masks `compat=0x28`,
`incompat=0x2c2`, `ro_compat=0x46b` read from the superblock and no journal.
Result on this host (e2fsprogs 1.47.2): pass, exit 0, no loop or temporary
directory left behind.

- `e2fsck -fn` only (never `-y`/`-p`), image hash unchanged by each run, clean
  before, after the clean-unmount interruption case, and after the restore.
- The read-only mount denies a write. One rename out changes exactly the
  target pathname; the file content is unchanged and every other path, type,
  symlink target and content stays the same. Renaming it back restores the
  logical tree. Directory and filesystem metadata may still differ.
- The interruption case is a clean unmount between fault and restore. It is
  not a power-loss test.
- Control: a copy with `s_state = 0` is detected through `dumpe2fs` as
  `not clean`. On this host (e2fsprogs 1.47.2) `e2fsck -fn` exited 0 with a
  clean-looking transcript for it. The script accepts either outcome and only
  checks that the image is unchanged, so the exit-0 result is a host
  observation. `e2fsck -fn` alone is not a sufficient clean gate.
- `scripts/test-pmos-journal-fsck.sh` still passes. Neither fixture is wired
  into CI (the only workflow is the records check).

## Host process note

While probing the fixture setup, an ad-hoc command on the build host mounted a
scratch image over `/tmp` by mistake, which shadowed the host's `/tmp`
directory. It was undone with a lazy unmount; afterwards no scratch loop was
listed and `/tmp` showed the root filesystem again. No device, no real
partition and no tracked data were involved. The committed fixture runs in a
private mount namespace, checks its mount target and loop before every mount
operation, and only touches its own image and verified loop.

## Draft policy (proposed, not deployed)

The root has no journal, so there is no replay question. Inspect offline and
read-only: `dumpe2fs -h` state and error fields plus `e2fsck -fn`, and refuse a
dirty, error-marked, unknown or ambiguous state instead of repairing it. No
`fsck -y`/`-p`, replay, format or cleanup. Run 117's `s_state = 0` is a
mounted snapshot, so it is neither offline consistency nor a shutdown policy.
`METADATA_CSUM` means metadata checksums, not file-content protection or
durability.

## Candidate carrier-hash reader (named, not applied)

A small audited reader that would open a carrier block node
`O_RDONLY|O_NOFOLLOW`, check `fstat` major:minor against sysfs and the exact
size, and stream the bytes over the diagnostic link for host hashing, with no
`mknod`, no `/run` writes and no fastboot fetch. It is a proposal, not an
existing script. The blocker is that the diagnostic `/dev` is a tmpfs without
partition nodes: only the userdata node is evidenced (run 117 read it), no
carrier node is, and the existing generated `carrier_reader()`
(`scripts/build-init-boot-persistent-root.py:747-790`) uses `mknod` and `/run`
files, which is not admissible. Without an approved way to obtain a node, the
candidate cannot run. Also open: concurrent writers, same-boot guard
conditions, and cost. Not approved and not run.

## Draft rescue checklist (not executable)

Needs owner approval of the full fault and restore plan and of any remount,
path identity checks, an expected mount mode, and a fail-closed stop. For the
`os-release` fault the code suggests no guard is armed, so same-boot guard
evidence would not exist and a separately approved timeout protocol would be
needed. No commands are given and none are authorized.

## Still open

Acceptance 1 stays partial. Acceptance 3 (rescue under an induced fault),
pin replacement (4) and the envelope re-read (5) remain unmeasured, as do the
carrier hashes. Physical items return to the coordinator.
