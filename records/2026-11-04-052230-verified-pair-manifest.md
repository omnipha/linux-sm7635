---
date: 2026-11-04
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# verified pair manifest

Host-only producer-side repair for the pre-flash handoff defect identified in
run 108: the verified #311 boot candidate couples `init_boot-root-contract-carrier.img`
to `vendor_boot_b-root-contract.img` via an embedded header pin, but the
discovery gate emitted an `init_boot_a`-only event.

## Dependent-pair manifest

Added `scripts/verify-dependent-pair-manifest.py` and wrapped
`scripts/build-init-boot-persistent-root.sh` to publish a machine-readable,
versioned pair declaration (`root-contract-pair.manifest.json`) in the
build output directory.

Key properties:
- Schema: `omnipha-sm7635-dependent-pair-v1`.
- Contains exactly two image entries (`init_boot_a` and `vendor_boot_b`)
  with canonical filenames, exact sizes, and lowercase SHA-256 digests.
- Atomicity: written under the builder lock (`i204-root-contract.lock`)
  to a `.omnipha-new` temporary file, fsynced, and hardlinked without
  silent overwrite. Stale or pre-existing staging files refuse write.
- Pair verification: the manifest is produced only after independent pair
  verification against stock references passes.
- Verification mode: checks parent permissions, non-symlink manifest,
  exact schema, strict 2-image structure, and re-verifies both referenced
  images against the independent persistent-root verifier.

## Settled pair preserved

The existing settled images from run 108 / PR #316 were verified
unchanged without rebuilding:
- `init_boot-root-contract-carrier.img` (8388608 B): `d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c`
- `vendor_boot_b-root-contract.img` (100663296 B): `221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500`

Published manifest:
- `root-contract-pair.manifest.json` (454 B): `c69e4b39078c5073454a8ca1d5200f6e7cd8c4e194808ab41b0d4c5ef3d7698e`

## Host verification

- `python3 -B scripts/test-dependent-pair-manifest.py`: positive verification,
  write under lock, directory target rejection, `--lock-fd` inheritance, and rejections for:
  bad schema, missing schema, extra root keys, empty/single/extra images,
  duplicate partitions, corrupted hashes, corrupt sizes, wrong filenames,
  malformed JSON, unsafe modes (non-0600), symlinks, flipped content in
  init or carrier, stale staging collisions, and misnamed files.
- `ruff check --no-cache --ignore EXE001 scripts/verify-dependent-pair-manifest.py scripts/test-dependent-pair-manifest.py`,
  `mypy --cache-dir /dev/null --check-untyped-defs scripts/verify-dependent-pair-manifest.py scripts/test-dependent-pair-manifest.py`,
  `shellcheck -S error scripts/build-init-boot-persistent-root.sh`, `sh -n`, `git diff --check`.
- All checks pass cleanly on the host.

No phone boot, flash, erase, Android start, stock restore, host ACK,
or radio action occurred. Two fresh autonomous WLAN boots remain unmeasured.
Physical preflight and handoff remain coordinator-owned; the downstream
consumer-side gate is tracked in omnipha/agents#118.
