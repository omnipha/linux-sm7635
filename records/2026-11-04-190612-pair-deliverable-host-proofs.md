---
date: 2026-11-04
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# pair deliverable host proofs

Host-only work for #324 on branch `issue-324-persistent-root-pair-deliverable`,
base `a9617f90`. No phone, USB, adb, fastboot, flash, reboot or partition
access; no image was built or flashed and no userdata was written. The
measured pair `d7bba454…`/`221bfd82…` stays untouched. Result is
inconclusive: three of the six requested host proofs are delivered as
committed fixtures, and the replacement pair itself is blocked for concrete
reasons stated below. Nothing here is a device measurement.

## Delivered host proofs (committed fixtures, all passing on this host)

- `scripts/test-pmos-journal-fsck.sh` (new, synthetic only): strict
  offline pre-mount gate for the journal-free ext4 policy — `dumpe2fs -h`
  allowlist parser (exact field set, `clean` state only, UUID
  `6f6d6e69-…`, features exactly `extent 64bit metadata_csum`, no
  `has_journal`/`needs_recovery`/`FS Error count`), then `e2fsck -fn`
  exact 5-pass clean transcript with empty stderr. Refuses forged
  dirty/error/clean-error/error-count/journal/recovery fixtures and a
  clean-state free-block-count corruption that `e2fsck -fn` exits 0 on
  (`Fix? no` transcript rejected). Every fixture image hash is unchanged
  afterwards; all loops detached, no residue. This is a synthetic-fixture
  gate only, not a production filesystem safety proof and not the live
  `sda13` measurement.
- `scripts/test-pmos-writer-exclusion.sh` (new, synthetic tmpfs only):
  proves the negative — `flock` excludes only cooperating `flock` users
  (an unprivileged non-cooperating writer appended 20 lines under a held
  lock); a read-only bind mount denies writers going through that mount
  (including root, `EROFS`) but protects nothing against writers using the
  still-`rw` original path, and root can remount or `nsenter` around both
  bind mounts and mount namespaces. So kernel-enforced exclusion of
  privileged concurrent writers during reconciliation/`switch_root` is NOT
  demonstrated; the design's exclusion requirement
  (`docs/strategy/persistent-root.md:77-80`) is unmet and must be revised
  (e.g. phase separation with `ro,noload` until a bounded write window)
  before any deployment. Rescue reachability is preserved in every phase
  by construction of the fixture, but that is a fixture property, not a
  device rescue proof.
- RAM-side busybox/tool envelope (manual host probe, not a committed
  fixture): initramfs `bin/busybox` extracted from the verified built
  image is `c2f279d1…` (1981032 bytes, 276 applets); it provides every
  applet the generated scripts invoke except `flock` (which no generated
  script needs — verified by `$BB` token scan). Under `qemu-aarch64` the
  RAM busybox hashes 3 MiB in ~0.05 s and the 846492-byte post in ~0.02 s.
  Cpio 3691047 bytes, LZ4 frame 2105683/2117632 (gap 11949), carrier
  bundle 330824 bytes with 81458040 bytes spare, three payloads
  29356/846492/899 bytes (sum 876747, each within the proposed 1 MiB
  bound). No committed envelope fixture yet; numbers are host-measured,
  not device timings.
- Pair manifest (existing, unchanged): the official dependent-pair
  manifest pins the installed pair — `init_boot_a` 8388608 bytes
  `d7bba454…`, `vendor_boot_b` 100663296 bytes `221bfd82…` —
  re-verified by `test-dependent-pair-manifest.py` (still passing).
- `scripts/test-pmos-baseline-provenance.py` (new, synthetic throwaway
  keys): exercises the review-state design's contract directly against
  the three current baseline payloads derived via
  `build-init-boot-persistent-root.py::runtime_scripts()` (radio 29356 B
  `146ed592…`, post 846492 B `113553dd…`, hook 899 B `3d317a69…`).
  Canonical manifest bounded to 4096 B, exact absolute paths in fixed
  order, `0:0 0700`, baseline seq 0 with null previous. Rollback is a
  NEW higher sequence (2 vs 1) naming predecessor and restored content
  ID, verified by real `ssh-keygen -Y sign/verify` using two separate
  throwaway Ed25519 keys (release vs rollback) with different
  principals, namespaces and domain separators. Rejects missing, empty,
  garbled, wrong-statement, cross-signed or wrong-namespace rollback
  signatures, modified manifest/payload bytes, stale/skipped sequences,
  and payload sizes over 1 MiB (verifies 846492, 900000 and 1048576 B).
  Explicitly prints that synthetic keys do NOT provide an authorized
  device baseline signature, reviewed schema implementation, updater or
  pair; no keys or private data are committed.

## Blockers: the replacement pair cannot be built yet

1. No deployable migration bootstrap exists. The accepted design
   (`docs/strategy/persistent-root.md`) is proposal-only; the image chain
   (`build-init-boot-persistent-root.py`) still pins the three SHA-256s
   with no signature machinery. Any changed image built now would be an
   unverified pin change, which the design itself forbids. Image output
   stays gated; nothing was built.
2. The host model does not implement the reviewed contract. Verified by
   inspection: rollback in `test-persistent-root-migration.py`
   (`plan_rollback`, lines 540-557) is a same-key in-manifest selector
   flip to the immediate predecessor, not the design's separately keyed,
   domain-separated new-generation rollback (design lines 149-157);
   schema, storage layout and bounds all differ. Correction: the prior
   record's "separately authorized rollback" phrasing describes the
   design, not what the model implements.
3. Writer exclusion against privileged actors is unproven (see fixture
   above); deploying reconciliation writes without it would violate the
   design's own gate.
4. The existing `scripts/test-pmos-pid1.sh` `ack` case fails on this host
   (`guard did not confirm the ack`, exit 1, reproduced with `pipefail`);
   diagnosis points to a test/protocol gap (plain `ack` without
   `success-ready` plus ordered record, vs guard requirements), not the
   device — but the post-cutover ACK path is therefore not green on host.

## Verification on this checkout

- `sh scripts/test-pmos-journal-fsck.sh` — exit 0, loops cleaned.
- `sh scripts/test-pmos-writer-exclusion.sh` — exit 0, no mounts or
  directories left behind; with the noted hardening (empty `WORK` at
  entry, fresh-PID-namespace sanity check for the inner run).
- `python3 -B scripts/test-pmos-baseline-provenance.py` (with synthetic
  throwaway keys) — exit 0, then `ruff check --no-cache` and
  `mypy --check-untyped-defs` clean on it.
- `python3 -B scripts/test-persistent-root-migration.py`,
  `test-dependent-pair-manifest.py`, `test-route-cache-pair-manifest.py`
  — all pass (existing, unchanged).
- `shellcheck -S error`, `sh -n` on both new scripts; `git diff --check`
  clean; `records.py index --write` and `check --base origin/main` pass.

## Boundary and next

Host fixtures and measurements only — not installed artifacts, not
device measurement. The unchanged installer's fail-closed boundary is
intact. #324 stays open: the coordinator owns any device acceptance, and
the replacement pair awaits (a) a deployable bootstrap implementation
reconciled with the model, (b) a revised writer-exclusion argument, and
(c) a green host ACK path.
