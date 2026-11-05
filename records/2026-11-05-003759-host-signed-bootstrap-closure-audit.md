---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# host signed bootstrap closure audit

Host-only work (no phone, USB, adb, fastboot, flash, reboot or partition
write; throwaway fixture keys only; the only privileged run was the existing
host loop-image fixture on temporary images). Continues
[2026-11-04-220742](2026-11-04-220742-persistent-root-host-blockers.md) and
[2026-11-04-190612](2026-11-04-190612-pair-deliverable-host-proofs.md). Review
passes were performed by separate model contexts on the working tree; no
earlier record documents them.

## Strategy corrections (`docs/strategy/persistent-root.md`)

- The statement that one boot is the whole budget was wrong and is withdrawn.
  Persistence acceptance needs two coordinator-approved boots under one
  technical reason: boot 1 creates a marker outside the three pinned paths and
  captures the `sda13` mount mode; boot 2 is a reboot without flash and verifies
  the marker and unchanged carrier hashes. Each further boot needs its own
  reason and approval.
- Added a draft guard-window runbook for the installed pair (authorizes
  nothing). Corrected by review against source: the PID 1 guard budget is 160 s
  from arming on the device's boot-relative `/proc/uptime`
  (`scripts/pmos-pid1-transition.sh`, `scripts/pmos-pid1-guard.sh`); arming was
  measured near 155 s of uptime (run 61), so the absolute deadline is near
  315 s after kernel start, not "five minutes" from session open. The 150 s
  initramfs timer is canceled by the installed pair's `/run/keep`. Read-only
  tools only; marker creation is the single intentional write; evidence goes to
  the coordinator host log; no host radio action, ACK, remount, fsck or journal
  replay. Carrier hashes use the recorded run-79 block-node read, with its
  session-reset hazard. Marker absence after the guard's unclean bootloader
  return is ambiguous, not proof of non-persistence. A raw superblock read on a
  mounted filesystem is an observational snapshot only.
- Boot 2 overwrites boot 1's ramoops and the recorded preboot pstore fetch was
  unsupported. Pstore loss stays a separate owner decision on #324; it is not
  accepted or requested here.

## PID 1 fixture FD-9 closure (`scripts/test-pmos-pid1.sh`)

The namespace shell now runs `exec 9>&-` after the loop-descriptor check and
asserts no `/proc/1/fd/9`; the switched PID 1 asserts that no descriptor points
at `/dev/loop*`, `/dev/block/sda13` or the temporary image and that fd 9 is
absent. Result: `sh scripts/test-pmos-pid1.sh` exits 0 with all six cases
(`ack`, `late`, `stale`, `timeout`, `preplanted`, `symlinked`) passing against
the unchanged guard, ACK script and root contract; no `/tmp/pmos-pid1.*`
directory remained. With `exec 9>&-` removed from a temporary copy the pre-cutover
assertion fails (`loop descriptor still open in the namespace init`, exit 1).
The post-cutover `/proc/1/fd` scan passed but was not separately shown to fail
under an injected leak. As before, `success-ready` and the boot record are
fixture-authored, so this is not a device ACK.

## Signed-generation logical model (`scripts/test-persistent-root-migration.py`)

Defects found by review and repaired:

- Staging recognition accepted truncated/corrupt manifest prefixes, corrupt
  unsynced signatures and wrong short payload prefixes. `inspect_stage` now
  requires a fully verified candidate generation and checks member order, sync
  order, exact prefixes and the ready flag against it.
- A second update could start while the previous archive was not durable;
  `update_plan` and `recovery_plan` now require a durable archive.
- `recovery_plan` validated pending state only after writing; it is now
  preflighted by `validate_pending`.
- Archive history was validated only while a journal was pending.
  `validate_archive_history` now checks committed and recovered edges as signed
  successors, attempt numbering and committed reachability on journal-free
  boot, floor check/advance, pending recovery and, after review, inside
  `TrustedFloor.consult` itself so guarded actions refuse history forged after
  plan construction (4 post-plan refusals added). `advance` now consults first.
- `journal_temp` attempts (negative, boolean, float, string) are refused.
- Release/rollback role separation compares actual Ed25519 key material from
  the allowed-signers files at every `verify_entry`.

Suite output: 17 parser vectors; 30 authorization vectors; 22 invalid pending
states refused before writes; 76 guarded cuts (including no-op sync steps); 25
unknown objects refused; 11 corrupt archive histories; 49 forward and 52
rollback publication cuts, each with 1300 recovery cuts. Limits, as printed:
staging is judged only against a caller-supplied verified candidate (a real boot
has no such oracle, so the model is stricter than the strategy table's
"preserve and report" row); `recognized`/`isolated`/`safe_metadata` are
booleans; selector rewind with identical bytes and whole-store rewind are
accepted without an explicitly supplied floor; the signer parser accepts one
single-key Ed25519 line, ignores key comments and does not compare a
`namespaces=` value (`ssh-keygen -n` enforces namespace at verify time), and
does not model certificates, expiry or revocation. No filesystem durability,
concurrency, mount or hardware anti-replay semantics.

## Host-only bundle verifier (`scripts/verify-root-generation-bundle.py`)

Fail-closed prototype: the CLI accepts only `--self-test` (subprocess-tested)
and is wired to no image or write path. It uses real `ssh-keygen -Y` SSHSIG and
checks framed chains against a pinned baseline, distinct decoded key blobs and
exact older-ancestor rollback; the signers file is strictly parsed and pinned in
a scratch copy. Armor is validated before `ssh-keygen` sees it (one BEGIN/END,
70-column wrap, no trailing garbage, duplicates, blank lines, CRLF, spaces,
64-column rewrap), because `ssh-keygen -Y verify` alone accepts trailing garbage
and duplicated signatures; every armor vector is run through `verify_chain` for
both a release and a rollback signature. Policy: the verifier refuses only an
exact full three-payload reissue; partial reissue and trivially altered older
bytes are accepted, so hash comparison is not semantic downgrade prevention and
does not replace rollback authorization. The model accepts a full reissue. This
difference is left for the owner; neither rule is adopted. Principals are fixed
fixture strings, not a general allowed-signers format.

## Pinned diagnostic BusyBox census (`scripts/test-pmos-ram-tool-closure.py`)

Unprivileged fixture; fails closed if the cache is absent and never downloads.
It checks that the cached `busybox-static_1.37.0-7ubuntu1_arm64.deb` equals the
`build-bootimg.sh` pin (`fcf50794…9592`) and contains `usr/bin/busybox`
`c2f279d1…ec02` (1,981,032 bytes), a static AArch64 ELF with no `PT_INTERP` or
`PT_DYNAMIC`. Under host `qemu-aarch64` it lists 276 applets, requires 50
applets from a hand-compiled list (not machine-derived) to be present, and runs
`true`, `false`, `sh`, `sha256sum` and an unknown-applet check. Not proven: the
list is not derived from the scripts; initramfs scripts that call bare names
(e.g. `find`) are not covered; the deb's Ubuntu signature is not verified; the
shipped image's `bin/busybox` is not compared; applet behavior beyond smoke;
the pmOS/Alpine guest BusyBox `f35a45f7…`; anything across `switch_root`; the
verifier or guard on the target.

## Decisions and status of the three items

1. **Signed-migration bootstrap**: model and verifier contracts are
   host-self-tested with throwaway keys. No deployable bootstrap exists: no
   owner-approved keys, no signed baseline, no target-side SSHSIG verifier or
   interpreter in the initramfs (it carries static BusyBox and Dropbear only;
   the verifier here needs CPython and OpenSSH).
2. **Privileged-writer exclusion decision**: `flock`, read-only binds and mount
   namespaces are refuted by `scripts/test-pmos-writer-exclusion.sh` and are
   not to be re-proved. The phase-separated read-only-inspect, bounded-write,
   re-inspect sequence remains a proposal; no mechanism enumerates or excludes
   privileged writers, and diagnostic `:22` and guest `:2222` sessions can
   coexist with a write window. Decision: a transaction write is not
   deployable until a mechanism is demonstrated without weakening rescue.
3. **RAM-side tool closure**: only the diagnostic initramfs BusyBox is mapped
   (above). The guest and cross-`switch_root` closure and a target-side
   verifier closure remain open.

## Blockers

No owner-approved release/rollback public keys exist, so the replacement pair is
not built; the installed `d7bba454…`/`221bfd82…` pair is untouched; no deployable
bootstrap, demonstrated writer exclusion or target-side verifier closure exists.
This record defers the tuple-policy, key and pstore decisions to the owner.

## Verification

- `python3 -B scripts/test-persistent-root-migration.py` — exit 0, PASS
- `python3 -B scripts/verify-root-generation-bundle.py --self-test` — exit 0
- `python3 -B scripts/test-pmos-ram-tool-closure.py` — exit 0
- `sh scripts/test-pmos-pid1.sh` — exit 0, six cases; negative copy exits 1
- `ruff check --no-cache` and `mypy --check-untyped-defs --cache-dir=/dev/null`
  on touched Python files — clean
- `sh -n`, `shellcheck -S error` on `scripts/test-pmos-pid1.sh` — clean
- `scripts/records.py index . --write`, `check . --base origin/main`,
  `git diff --check` — clean
