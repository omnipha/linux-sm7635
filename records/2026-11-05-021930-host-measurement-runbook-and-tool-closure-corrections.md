---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# host measurement runbook and tool closure corrections

Host-only follow-up for #324 after merging PR #329 at `170b30c0`. No phone,
USB, adb, fastboot, flash, reboot, partition write, or userdata erase.
The installed run-113 pair `d7bba454…`/`221bfd82…` stays untouched; the
replacement pair remains unbuilt because owner-approved release/rollback keys
do not exist.

## Corrections made

1. **Measurement runbook deadline and carrier math (`docs/strategy/persistent-root.md`)**:
   - The PID 1 guard computes `deadline = floor(arm uptime) + 160` on the
     device's `/proc/uptime` clock (`scripts/pmos-pid1-guard.sh`). `/run/pid1-guard/armed`
     contains only the boot ID, not an arm timestamp.
   - Reading `/proc/uptime` over SSH shows current uptime, not arm uptime.
     A remaining window can be derived safely only if a defensible conservative
     same-boot lower bound on arm uptime is known. Historical timing (run 61
     arming around 155.4 s on a different image; run 113 ending around 315 s)
     is not a safe same-boot substitute. If no same-boot lower bound is
     established, stop rather than infer.
   - The run-79 BusyBox temporary block-node read is not an approved safe
     method: node creation is not purely read-only and an earlier attempt
     reset its session. If no genuinely read-only carrier-hash method exists,
     stop.
   - Clarified that guard timeout recovery is an unclean return, not a
     substitute for the coordinator-approved no-flash second boot, and is not
     guaranteed if device identity or `/bin/restart2` checks fail.
   - Reworded boot-2 pstore overwriting from a definitive certainty to a
     preservation risk; the unresolved owner decision on #324 is retained and
     authorizes no boot.
   - Reconciled remaining single-measurement phrasing with the two-boot budget
     and corrected the stale model gap description to match the model's actual
     `inspect_leftovers` and retry-handling behavior.

2. **RAM-side tool closure negative tests and tool resolution (`scripts/test-pmos-ram-tool-closure.py`)**:
   - Replaced digest-only inline checks in `negatives()` with shared checker
     calls (`require_deb`, `require_binary`, and an end-to-end `extract` run on
     an altered deb) exercised through the `rejects()` harness.
   - Resolved host tools (`dpkg-deb` and `qemu-aarch64`) once via `shutil.which`
     to absolute paths and used them consistently in all `run(..., env={})` calls.

3. **PID 1 post-cutover descriptor sweep documentation**:
   - Documented the exact scope of the post-cutover descriptor scan: it runs
     once before OpenRC startup, silently skips unreadable links, passes if
     `/proc/1/fd` is empty or unreadable, and covers only `/dev/loop*`,
     `/dev/block/sda13`, and `/tmp/pmos-pid1.*` targets.

## Host verification

- `python3 -B scripts/test-pmos-ram-tool-closure.py` — exit 0, all 11 negative
  checks rejected via `rejects()`.
- `ruff check --no-cache scripts/test-pmos-ram-tool-closure.py` — clean.
- `mypy --check-untyped-defs --cache-dir=/dev/null scripts/test-pmos-ram-tool-closure.py` — clean.
- `python3 -B scripts/test-persistent-root-migration.py` — exit 0.
- `python3 -B scripts/verify-root-generation-bundle.py --self-test` — exit 0.
- `git diff --check` — clean.
- `python3 scripts/records.py index . --write` — updated generated index.
- `python3 scripts/records.py check . --base origin/main` — exit 0.
