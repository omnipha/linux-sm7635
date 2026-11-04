---
date: 2026-11-04
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# route-cache candidate variant integration

## Boundary measured host-only

The run-113 install chain refuses the route-cache candidate bytes in every
direction: as carrier payload (`unpinned carrier payload`), as pre-installed
post/hook files (`untrusted persistent chain file`), with the pins unchanged.
Replacing the canonical `GATED_POST_SHA`/`GATED_HOOK_SHA` would instead break
historical verification of the settled pair (`d7bba454…`/`221bfd82…`), so the
candidate is integrated as a separately pinned variant, not a pin change.

## Variant module

`scripts/build-init-boot-route-cache-candidate.py` loads two isolated
instances of the canonical builder: one untouched, one rebound to the
candidate pins (`92f6f9cd…`/`5bc5b0f4…`) with `gated_artifacts` composed
through `derive-route-cache-gated-ack.py`, the run-113 image digests added to
its refusal set, and a fresh verifier instance bound to it. The variant
re-derives `runtime_scripts()` and cross-checks it against an independently
computed expectation: candidate post/hook, the session-stage hook pin, the
three installer post/hook pins in the self-stage script, and the transitive
`STAGE_SHA=` self-pin of the session stage. `replace_count` enforces exact
occurrence counts and bounded replacement. Image output stays disabled
(`main` fails closed) pending migration review; only the reviewed derivation
and verification functions exist.

`scripts/verify-route-cache-pair-manifest.py` clones the dependent-pair
manifest logic under a distinct schema
(`omnipha-sm7635-route-cache-pair-v1`), distinct manifest and image
filenames, and a `verified_pair` bound to the variant verifier, refusing
canonical paths before locking and leaving the historical manifest and
images untouched.

## Host fixtures

- `python3 -B scripts/test-derive-radio-persistent.py`: PASS. The run-113
  installer refuses the candidate post/hook as payload and pre-installed
  files; the variant installer refuses the run-113 files, installs the
  candidate on an empty target and repeats idempotently.
- `python3 -B scripts/test-route-cache-pair-manifest.py`: 13 PASS. Schema
  isolation both directions, canonical paths rejected before locking,
  symlink/hardlink/mode/staging/refusal cases, image replacement during
  verification, CLI subprocess and inherited `--lock-fd`.
- `ruff`, `mypy` on all touched scripts: PASS; `git diff --check`: clean.

## Constraint

Deployment needs the coordinator-gated device migration: the unchanged
installer cannot replace the preinstalled run-113 files (fail-closed by
design), so a candidate flash requires human-gated removal of the old
post/hook first, per the live-recipe rule. No image was built; the settled
pair and its manifest verify unchanged.
