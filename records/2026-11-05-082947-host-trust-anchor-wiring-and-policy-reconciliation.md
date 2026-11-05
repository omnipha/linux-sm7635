---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# host trust-anchor wiring and policy reconciliation

## Owner-anchor fail-closed gate

Option A approves embedding two distinct offline Ed25519 public keys (release
and rollback) into the future replacement bootstrap design. The two
role-specific Ed25519 owner public keys are now recorded in
`configs/persistent-root-trust-anchors.json` and pinned by raw-key SHA-256 in
`scripts/persistent_root_trust.py`:

- release, comment `omnipha-sm7635-release-20261105`, fingerprint
  `SHA256:aiUM8xoA0XpncAyFhsf+mVp2h/MqO0ag9byKnaohBJ8`;
- rollback, comment `omnipha-sm7635-rollback-20261105`, fingerprint
  `SHA256:bhAnhbEInLjaSxPUHzjnXjZkGuN0SvA5VkCCVTLfpsA`.

The production check reads only that fixed config, requires the exact role
comment on each line, and fails closed on absent, malformed, duplicated,
swapped, or unapproved anchors. A throwaway key cannot be identified from its
public bytes and cannot pass this gate or become a shippable default. The
private halves stay offline as mode-600 files outside the repository and were
never read, printed, copied or committed.

## Verifier policy reconciliation

The host prototypes (`scripts/test-persistent-root-migration.py` and
`scripts/test-pmos-baseline-provenance.py`) delegate signer-file loading and
signature armor checks to the verifier's strict policy in
`scripts/verify-root-generation-bundle.py`. The unified policy enforces one
canonical single-link regular `ssh-ed25519` line per role with the exact role
principal and namespace, distinct role key blobs pinned once per verification
call (re-checked against the signer file within that call only; no pin persists
across calls or boots), and canonical signature armor in the expected
namespace.

The prototypes differ from the verifier in rules unrelated to the anchors
themselves (full-tuple reissue, the provenance fixture's denylist coverage),
which remain subject to an owner decision. All three sign their chains with
per-run throwaway keys. Owner anchors are consumed only by
`persistent_root_trust.load_owner_anchors` and the verifier's
`verify_owner_bootstrap_baseline` and `verify_owner_chain` entry points, which
verify the release or rollback signature against the anchors from
`load_owner_anchors` and, separately and independently, require the baseline
payloads to equal the hardcoded `BASELINE_DIGESTS` and `BASELINE_SIZES`. The
baseline manifest ID remains caller-supplied and is not pinned anywhere: there
is no recorded binding between one owner key and one baseline. No owner-signed
bundle exists — private keys are offline — so the only positive owner-path test
runs against an explicitly labeled fake loader with throwaway keys. A valid
throwaway-signed chain is refused by the genuine owner entry points. Owner keys
are verified only against the hardcoded fixture principal and namespace
strings; adopting real identities is an open design point of the separately
reviewed cutover, not a settled property of the recorded keys.

## Limits and open questions

- Result is inconclusive because this is host-only scaffolding: no deployable
  bootstrap or replacement pair was built, no image was produced, and no device
  state was changed. Recording the public anchors closes the missing-keys
  blocker, but deployment remains blocked on building and reviewing the
  bootstrap itself.
- The host gate does not touch the installed run-113 pair.
- Physical boot 1 remains stopped and coordinator-owned. The unsecured-pstore
  risk, the read-only carrier gate, and the same-boot guard-time gate remain
  unresolved.
