---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# host measurement runbook deadline inequality and review audit

Host-only follow-up for #324 at merged main commit `32f321b`. No phone, USB,
adb, fastboot, flash, reboot, partition write, userdata erase, or network
operations. The installed run-113 pair `d7bba454…`/`221bfd82…` stays untouched;
the replacement pair remains unbuilt because owner-approved release and
rollback public keys do not exist.

## Review findings and corrections

1. **Deadline inequality in the measurement runbook (`docs/strategy/persistent-root.md`)**:
   - `scripts/pmos-pid1-guard.sh` samples uptime at the moment the watch loop
     starts, truncates it via `awk int()`, and computes `deadline = start + 160`.
     Recovery is requested at the first check where `now >= deadline`.
   - The runbook previously called a conservative lower bound on the arm uptime
     an "upper bound on remaining time". Because `remaining = start + 160 - current`,
     an underestimated `start` underestimates the time left: it is a *lower*
     bound on remaining time (`remaining >= lower_bound_on_start + 160 - current`),
     not an upper bound.
   - The leave-by time is now specified as `(lower_bound_on_start + 160) - margin`,
     requiring `margin >= 1` integer seconds so the session leaves while uptime
     is still strictly below `start + 160`. The runbook stops if no defensible
     same-boot lower bound is established.

2. **PID 1 post-cutover descriptor sweep timing (`docs/strategy/persistent-root.md`)**:
   - Corrected the description of the descriptor sweep in `scripts/test-pmos-pid1.sh`:
     it runs once at the start of `--switched`, after the pre-cutover Dropbear
     service is already running and holds its socket/PID, and before OpenRC
     starts.

3. **Prototype sequence-number policy divergence**:
   - Documented the unreconciled contract difference: `scripts/verify-root-generation-bundle.py`
     bounds `sequence` to `0 <= sequence <= 2**31 - 1` (`SEQUENCE_MAX`), whereas
     `scripts/test-persistent-root-migration.py` accepts any non-negative integer.
   - A host-only Python probe confirmed that both parsers accept valid manifests
     with sequence `2**31 - 1`, and only the bundle verifier refuses `2**31`.
     Neither policy is chosen here pending owner guidance.

4. **Negative check count in prior record**:
   - Noted that `scripts/test-pmos-ram-tool-closure.py` runs exactly 9 negative
     checks through the `rejects()` harness (5 ELF program-header/machine/class/size
     checks, 1 altered BusyBox byte, 2 truncated/extended deb checks, and 1
     end-to-end extraction rejection on an altered deb), all of which pass.

## Host verification

- `python3 -B scripts/test-persistent-root-migration.py` — exit 0.
- `python3 -B scripts/verify-root-generation-bundle.py --self-test` — exit 0.
- `python3 -B scripts/test-pmos-ram-tool-closure.py` — exit 0 (all 9 negatives rejected).
- `ruff check --no-cache` and `mypy --check-untyped-defs --cache-dir=/dev/null` — clean.
- `git diff --check` — clean.
- `python3 scripts/records.py index . --write` — updated generated indexes.
- `python3 scripts/records.py check . --base origin/main` — exit 0.
