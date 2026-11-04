---
date: 2026-11-04
issue: linux-sm7635#324
subsystem: userspace
result: confirmed
---
# pin replacement host design and models

Host-only work for #324: the reviewed migration path that replaces the
run-113 userland hash pins with equivalent provenance-checked
install/update plus rollback, plus host model fixtures for it. No phone,
USB, adb, fastboot, flash, reboot or partition access; the physical
coordinator owns every device decision. Base `f2c20736cdd6a9b669ab`.

## Host artifacts

- `docs/strategy/persistent-root.md` (new, proposal status): the reviewed
  migration design. It traces all current enforcement points of the three
  run-113 pins (`146ed592…` radio, `113553dd…` post, `3d317a69…` hook:
  image-carried session-stage, `persistent_installer()`, generated hook,
  staged radio), states that no userdata-local manifest, verifier or
  hook-last publication can bypass them, and derives that the only real
  cutover is one different, independently verified pre-SSH bootstrap pair
  while the measured pair `d7bba454…`/`221bfd82…` stays installed,
  unchanged and never reflashed. It defines the signed generation
  contract (canonical manifest, Ed25519 release signature, separately
  signed rollback authorization, predecessor binding, sequence and replay
  rules), the anchor inside the verified image, RAM-side verified tools,
  generation storage with atomic selector and journal, the
  deterministic interruption-recovery table, the initial signed baseline
  that must reproduce all three fixed byte sets, no-automatic-repair fs
  policy for the journal-free filesystem, and the one separately
  authorized physical measurement with its preflight. It explicitly does
  not claim fsync simulates power loss, does not authorize any flash or
  erase, and refuses the altered radio `d7b74c24…` in every generation.
- `scripts/test-persistent-root-migration.py` (new, host-only
  non-deployable model): real `ssh-keygen` Ed25519 SSHSIG sign/verify with
  disposable temp keys, fixed namespace and isolated `allowed_signers`;
  strict canonical manifest parsing (47 mutations refused: duplicates,
  unknown keys, traversal, wrong types/bounds/modes/order); immutable
  trust anchor outside the store; denylist enforcement; the policy that a
  userdata manifest keeping the installed boot pins cannot change the
  three files, and that changed pins are accepted only with a separate
  image-principal attestation binding pins and file digests; forward
  install and separately authorized rollback with replay/skip/wrong-
  predecessor/selector-downgrade/unapproved-rollback refusals;
  interruption at 15 install and all rollback cut points boots exactly
  one whole verified generation; 21 slot-corruption cases refused with
  restoration. It prints its own limitation: ordinary host directories,
  no device, ext4, power-cut, pre-SSH image or production installer.
- `scripts/test-derive-radio-persistent.py` (extended): the actual
  unchanged `persistent_installer()` body fails closed on each mismatched
  protected file and each mismatched carrier payload; the old installer
  refuses a newly authorized post/hook generation whether present
  (`untrusted persistent chain file`) or missing with the candidate in
  the carrier (`unpinned carrier payload`, nothing written); an unrelated
  unpinned file and the three protected files survive two full installer
  passes byte-identically with metadata; and both the canonical and
  route-cache generated session-stage stages pin their own hook digest
  exactly once, ahead of the `unexpected local startup hook` refusal.

## Verification

Host tests and static checks, all on this checkout:

- `python3 -B scripts/test-persistent-root-migration.py` (prints its
  limitation, then OK).
- `python3 -B scripts/test-derive-radio-persistent.py` (all passes,
  including the four new ones).
- `python3 -B scripts/test-dependent-pair-manifest.py`,
  `python3 -B scripts/test-route-cache-pair-manifest.py` (unchanged,
  still pass).
- `ruff check --no-cache` and `mypy --check-untyped-defs` clean on both
  touched Python files; `git diff --check` clean.

## Boundary

These are host fixtures and a design, not installed artifacts and not a
device measurement. The unchanged installer's fail-closed boundary stays
intact; no image was built or flashed and no userdata write happened.
Device acceptance for #324 (SSH edit surviving a no-flash reboot,
measured read-write root and journal/fsck policy, rescue after a
reversible root fault, and the migration path proven by its one device
measurement) remains open and coordinator-owned.

## Next

Independent review of `docs/strategy/persistent-root.md`, then the
coordinator's decision on whether and when to build and independently
verify the proposed replacement pair. #311 stays paused behind this
issue.
