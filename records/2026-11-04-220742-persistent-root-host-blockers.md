---
date: 2026-11-04
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# persistent root host blockers

Host-only work for #324 on branch `issue-324-provenance-bootstrap`,
merged with `origin/main` at `777f8a1`. No phone, USB, adb, fastboot, flash,
reboot or partition access; no image built; no userdata written. The measured
pair `d7bba454…`/`221bfd82…` stays untouched. Result stays inconclusive: the
replacement pair remains blocked; the failing host PID 1 ack case is fixed by a
rewritten fixture that now passes.

## What was delivered

1. `scripts/test-persistent-root-migration.py` rewritten as a host-only
   signed-generation model plus restored legacy regression coverage:
   - Real `ssh-keygen -Y sign/verify` with separate release and rollback
     Ed25519 keys, distinct principals, namespaces and domain separators.
     Rollback is a new higher-sequence generation bound to the current
     predecessor and restored content, not a same-key selector flip.
   - A `TrustedFloor` synthetic external floor: refuses selector downgrade,
     whole-store rewind, same-bytes rewind and a signed fork lacking the
     checkpoint; a dual-key rollback advances it. Printed caveat is honest:
     it is consulted read-side only — `reconcile`/`update_plan` still write
     on a rewound store before any floor check, and no trusted monotonic
     anchor exists on the device.
   - Signature-verification failures are never cached (only successes are),
     with a spy test proving repeated negative checks really execute
     `ssh-keygen`.
   - No-journal selector/fixed mismatch refused; 17 parser vectors, 30
     authorization vectors, 14 corruption refusals, interruption sweeps
     (49 forward and 52 rollback publication cuts, 650 recovery cuts each),
     9 collision refusals; restored legacy coverage: run-113 pin cross-check
     against builder sources (11 vectors), image-attestation policy (24
     refusals), trust-anchor placement (6 overlaps, 7 store-local forgeries),
     32 tree and 11 selector mutations.
   - Known asserted gaps remain: clean boot ignores leftover temp objects
     and trusts a `recognized` boolean; a recovered transition cannot be
     retried; selector rewind with identical bytes and whole-store rewind
     are accepted without the external floor.
   - Verified: `python3 -B scripts/test-persistent-root-migration.py` exit 0, `ruff check --no-cache` clean, `mypy
     --check-untyped-defs` clean.
2. `scripts/test-pmos-pid1.sh` rewritten so the `ack`/`late` cases satisfy
   the unchanged guard on an isolated ext4 root: ordered boot record through
   the real `pmos-root-contract.sh` functions, fixture-authored
   `success-ready`, loop-backed ext4 instead of tmpfs, and
   `root_contract_switched_root` validation after cutover. An earlier run of
   this rewritten fixture (before the final hardening edits) passed all six
   cases. The fixture's host driver was then hardened: single verified loop
   configured atomically via `LOOP_CONFIGURE` with kernel-verified backing
   identity, image descriptor held open across the child, no recursive
   delete of mounted content (fresh-image emptiness asserted instead),
   fail-closed cleanup that only removes the image after detach is
   confirmed, explicit `LOOP_CLR_FD` fallback, bounded child timeout, and an
   audit-fixed operator-precedence bug in the loop-flag check plus FD-9
   closure after verification.
   - Result after the final hardening edits: `sh scripts/test-pmos-pid1.sh`
     exit 0, all six cases (`ack`, `late`, `stale`, `timeout`, `preplanted`,
     `symlinked`) passed against the unchanged production guard, ACK script
     and root contract; no leaked loop device or `/tmp/pmos-pid1.*`
     directory afterwards. One intermediate run, made before an indentation
     slip in the embedded loop-flag check was fixed, failed with `loop
     descriptor or backing image mismatch`; that was a fixture defect, not a
     production one. Two fixture runs used host loop images only; the
     physical phone was never touched. `ack` and `late` still rely on
     fixture-authored `success-ready` and boot-record lines (written through
     the real contract functions), synthetic `/sys` block files and
     fixture-made device nodes, so this shows the guard accepts a valid
     ordered record and rejects the negative cases, not that production
     self-post or the gate emits that evidence. Static checks: `sh -n`,
     `shellcheck -S error`, `git diff --check` clean.
3. `docs/strategy/persistent-root.md` revised and reconciled with
   `origin/main` `777f8a1`: defensible threat boundary (no untrusted
   privileged writer during the bounded write window; disconnecting SSH is
   not exclusion; `flock`/`ro` bind/`nsenter` refuted by the committed
   fixture), candidate read-only-inspect → bounded-write → re-inspect
   sequencing explicitly labeled unproven, realistic replay limits of the
   floor-less model, and honest host-fixture boundaries. The owner decision
   on the two trust-anchor keys and the next single device variable come
   from `777f8a1` and are preserved.

## Remaining blockers (unchanged in substance)

- No owner-approved release/rollback public keys exist, so no replacement
  pair can be built (owner decision recorded on #324; PR #327 comment).
- No deployable pre-SSH signed-migration bootstrap exists reconciled with
  the model.
- Privileged-writer exclusion during the bounded write window remains
  unproven; only phase separation is proposed, not demonstrated.
- Verified RAM-side tool closure across `switch_root` is unmapped.

## Verification on this checkout

- `python3 -B scripts/test-persistent-root-migration.py` — exit 0.
- `ruff check --no-cache`, `mypy --check-untyped-defs` on the model — clean.
- `sh -n`, `shellcheck -S error` on `test-pmos-pid1.sh` — clean;
  `git diff --check` clean.
- `sh scripts/test-pmos-pid1.sh` — exit 0, six cases pass (host loop image
  only; no phone, USB, adb, fastboot or partition operation).

Boundary: host tests and documentation only. Nothing here is an installed
artifact or a device measurement. #324 stays open; the coordinator owns all
device acceptance.
