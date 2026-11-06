# Persistent-root strategy (#324)

Status: active strategy, not evidence. It authorizes no flash, boot or device
write; the physical coordinator owns every device decision. Measurements live
in `records/`, history in git. The earlier signed-generation / offline-key
design (bootstrap, manifest v1, journal, rollback keys) was superseded by the
owner decision of 2026-11-06 and is removed from this file; see
`git log -- docs/strategy/persistent-root.md` before 2026-11-06 if needed.

## Goal and owner direction

SSH userland edits survive reboot without a partition flash (#324). Owner
direction 2026-11-06 (08:35 and 11:03 Europe/Berlin): remove the radio,
self-post and startup-hook hash pins for mb003. No signed baseline, no
replacement verification layer, no snapshot copy, no abort on mode, owner,
link count or hash of those files. Keep: the altered radio
`d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3` never
runs; USB SSH rescue, PID 1 guard, nonce/ACK and targeted fastboot identity
unchanged. No userdata erase or format.

## Measured so far (device, installed pair `d7bba454…` / `221bfd82…`)

- Item 1 survival: one unpinned marker survived one no-flash reboot, root
  `ext4 rw,relatime,norecovery` on `sda13`
  ([run 116](../../records/2026-11-05-095841-run-116-unpinned-marker-survives-no-flash-reboot.md)).
  One marker, one reboot; carrier hashes were not re-read.
- Item 2 root mode and superblock: read-write, journal-free, `s_state = 0`,
  `METADATA_CSUM`
  ([run 117](../../records/2026-11-05-103554-run117-sda13-superblock-readonly-snapshot.md)).
  The fsck/journal policy stays unmeasured and is not the next variable.
- Item 3 rescue: one induced fault (`os-release` moved away) left `:22`
  reachable, one `mv` restored it
  ([run 121](../../records/2026-11-05-125321-run121-acceptance3-os-release-fault-rescue.md)).
  The `:22`-outage path is unmeasured.
- Item 4 pins: unmeasured on the device. Reason below.

## Item 4 state (host done, device blocked at a tooling gate)

- Host delivery: PR #343 (`b50f6ae`). v2 pair outside Git under
  `~/sm7635-build/out`: `init_boot_a` `f08a71ae…` (8388608 B),
  `vendor_boot_b` `cb7f3a9e…` (100663296 B), manifest `fc78afa1…`
  (full hashes on #324 comment 6684955800). The image retains existing
  radio/post/hook files and installs missing ones; it adds no check.
- Gap 1: the legacy hook and post on the device still embed their pins, so a
  flash alone changes nothing. Minimal fix, stated by the worker on #324
  (comment 6684955800): one explicit overwrite each of
  `/etc/local.d/10-omnipha-self-stage.start` (hook, 356 B, `9ea78229…`) and
  `/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh` (post, 846157 B,
  `bc1e10ab…`). The radio is untouched.
- Gap 2 (the actual stall): the coordinator refuses to flash because
  `mission-handoff.py` knows only the v1 pair manifest and emits an
  `init_boot_a`-only artifact event for the v2 pair (omnipha/agents#129,
  blocked, open since 2026-11-06 12:34Z). Runs 125-129 each ended in a
  read-only refusal with identical findings; the run-128 comment (13:52Z)
  measured nothing new.
- Before a candidate boot, the coordinator must establish the on-disk
  pre-state, prove the altered radio cannot run, and plan any two-file setup
  on the installed chain or another proven non-candidate access path. The
  sequence "flash v2, then boot it to establish radio exclusion" was
  withdrawn (#324, 12:43Z). The coordinator alone decides ordering, backups,
  identity, capture and the flash/reboot measurement; nothing here authorizes
  an operation. A pair event must name both dependent partitions; never flash
  the one named half as a substitute.

## Next single variable

**Resolve the dependent-pair gate without weakening it**, then measure the
edited file on the device. The supervisor's host receipt on agents#129
measures names, sizes and hashes but explicitly does not cover carrier
content or stock provenance; it must not be promoted to that proof. The
consumer recognizes only the older schema/name. Whether to accept schema
`omnipha-sm7635-mb003-unpinned-pair-v1` and name
`mb003-unpinned-pair-v2.manifest.json` alongside the v1 contract is an open
gate decision (agents#129), not an approval.

Direction: an independent party (not the producer) verifies the exact v2 pair
including carrier content and stock provenance; the gatekeeper then decides
on the narrowly bound v2 schema/name; if accepted, agents#129 gets its
fixture-backed repair with positive and mismatch tests. If rejected, assess
compatibility with the existing v1 contract before assuming a rebuild.
Keep fail-closed handling of unknown and alias names and the receipt-only
ACK. Do not waive the consumer gate, flash a single half or invent a
verification receipt. #324 already carries this dependency; do not duplicate
it as a new mission issue.

No new bootstrap, signing, model or wording issue. Do not repeat the withdrawn
flash-then-boot order or the signed-baseline design.

## Budget and fallback

- Budget: one independent provenance verification and one bounded pair-gate
  repair. No further identical read-only preflight refusals while the gate is
  unresolved; each is a repeated run without a new measured fact. If gate
  acceptance or independent provenance is not established by 2026-11-07
  15:00 Europe/Berlin, the plan owner escalates it to the owner as the one
  blocking decision.
- Only the coordinator schedules device work; each boot beyond the first
  candidate boot and its one no-flash reboot needs a technical reason and
  coordinator approval. No candidate-image loop.
- Fallback if gate or provenance cannot be established: stop before flash and
  report the concrete missing decision or proof; look at the v1 contract
  route before building another pair.
- If a candidate boot or the single-file edit check fails: stop, preserve
  evidence, coordinator-led rescue. Run 121 measured `:22` rescue for one
  `os-release` fault only; it is not a general guarantee. Do not reflash the
  measured pair `d7bba454…` / `221bfd82…` without a new technical reason.
- If the root were read-only or an unpinned file did not survive a no-flash
  reboot, persistent PC-style operation would not be a property of the
  installed system. Run 116 saw neither.

## Still open, not this variable

Carrier-hash re-read has no admissible read-only reader (the generated
`carrier_reader()` uses `mknod`, not admissible); fsck/journal policy is
unmeasured; the `:22`-outage rescue is unmeasured. All are coordinator-owned
reads and do not gate item 4.
