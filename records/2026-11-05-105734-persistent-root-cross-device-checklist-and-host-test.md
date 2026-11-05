---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# persistent root cross device checklist and host test

Host-only delivery. No device action of any kind: no boot, flash, reboot,
adb, fastboot, USB or session action, no userdata change. The installed pair
`d7bba454…` / `221bfd82…` is untouched and never-reflash, no replacement pair
was built, no gate was loosened, and #324 stays open.

## What was added

- `docs/persistent-root-device-checklist.md`: a reusable per-device
  suitability and limits checklist for a persistent writable root, covering
  root carrier, persistence and filesystem policy, USB-SSH rescue path,
  guard, explicit owner approval before userdata erase/format, and capture
  and operation constraints. Reported evidence and evidence from another
  device are not measured proof for the target.
- `scripts/test-persistent-root-device-checklist.py`: a host test that reads
  the document's mb005 JSON screening fixture. It models device-specific
  measured-evidence requirements and rejects missing, malformed, reported,
  open, refuted, unknown or wrong-device evidence. It also tests explicit,
  device- and action-matched erase/format approval; capture before each
  reboot; one SSH call for the marker; fail-closed reads after same-boot guard
  confirmation; and refusal of `mknod` and unknown operations. The positive
  fixture is synthetic. A pass is not a device measurement, live guard,
  authorization or proof of persistent-root safety.

## First target: mb005, reported vs measured

Source: `docs/knowledge/oneplus-instantnoodlep.seed.json` in
`omnipha/agents` at commit `9c8a27a7eeba4fd3266c6a9d7f71836cad9a3d47`
(version 1, updated 2026-11-04). The seed was read from that commit; no
physical-device evidence was read for this delivery.

- **Measured** (seed K1): USB `18d1:4ee8`, configuration midi, interfaces
  `01:01:00` and `01:03:00`; ADB lists no device; no shell access.
- **Reported** (K2/K5): pmaports package dependencies and `deviceinfo`,
  including its declared `super` rootfs partition. This is not an installed
  writable-root measurement.
- **Open** (K11/K12): fastboot presence, unlock state, slot and product
  variables are untested and unlock may wipe user data; USB SSH and WLAN SSH
  bring-up are untested. The seed does not establish a guard, filesystem
  policy, marker survival or fault-rescue result.

The document's screening fixture therefore remains blocked. Its plan has no
operations and no erase or format. It does not assign an owner approval or
claim a pass for mb005.

## Carried-over rules and their limits

- Capture armed before reboot: run 116 (both boots) and run 117; see
  `records/2026-11-05-095841-run-116-unpinned-marker-survives-no-flash-reboot.md`
  and `records/2026-11-05-103554-run117-sda13-superblock-readonly-snapshot.md`.
- One pinned SSH call for the run-116 marker write; run 117 wrote no marker.
- Reads fail closed and only after same-boot guard confirmation. This is a
  future planning requirement, not a claim that run 117 achieved it: its
  first read connected during the pre-cutover diagnostic hold because its
  read script did not fail closed on a missing guard state.
- No `mknod`: runs 116 and 117 report none; run 117 used an already-existing
  mode-400 block node. These are mb003 observations, not mb005 measurements.

## Verification and limits

`python3 -B scripts/test-persistent-root-device-checklist.py` exercises the
mb005 fixture and synthetic positive and negative cases. Scoped Ruff and mypy
check the test script. The screening code checks the presence of evidence
references, not the truth or freshness of their contents; it cannot prove a
real device suitable. #324 acceptance items unmeasured in the cited records
stay unmeasured. This is not a public support claim.
