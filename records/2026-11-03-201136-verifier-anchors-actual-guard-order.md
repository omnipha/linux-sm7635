---
date: 2026-11-03
run: 2
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# verifier anchors actual guard order

Scope: host-only #311 integration alignment in `verify-init-boot-persistent-root.py`.
Aligns persistent-root image self-test assertions and negative mutation checks
with the merged additive guard's separate `success_ready` and `ordered_record`
call sites.

## Finding and fix

In PR #312, the guard interlock was updated to check `if ! success_ready; then`
followed by `ordered_record || recover` before writing `$STATE/accepted`.
`verify-init-boot-persistent-root.py` had retained an earlier combined-check
assertion string `if ! success_ready || ! ordered_record; then`.

This follow-up updates the verifier's presence assertions and negative mutation
cases to match the actual separated guard statements:
1. `guard.index(b"if ! success_ready; then") < guard.index(b"ordered_record || recover") < guard.index(b'> "$STATE/accepted"')`
2. Separate negative mutation checks refusing removal of either `success_ready`
   or `ordered_record`.

## Checks

- `python3 -B` AST and assertion self-test: passes cleanly with exact builder
  output (`current_scripts()`).
- `ruff check --no-cache scripts/verify-init-boot-persistent-root.py`: passes.
- `python3 scripts/records.py check . --base origin/main`: passes.
- No physical device access; coordinator handoff remains pending.
