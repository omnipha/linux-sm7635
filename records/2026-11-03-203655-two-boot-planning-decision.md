---
date: 2026-11-03
run: 4
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# two boot planning decision

Decision recorded unattended per standing instruction (work without waiting
for an answer; record the decision in the issue).

Question board 6607437887 asked whether #311 acceptance is one or two fresh
boots. Concrete answer: **for all host deliverables and planning, the issue
body's criterion is binding: two fresh boots, the second only after a first
full pass and a coordinator-owned safe close/handoff.** The mission-owner
comment 2026-11-03T15:20:01Z and the issue body both scope two passes; the
single-boot note in PR #314's `docs/strategy/wlan.md` edit is worker-authored
and awaits owner confirmation, so it does not lower acceptance.

Bounded reasoning: the acceptance-count uncertainty does not change any work
available now — host integration, real-protocol tests, artifact hashes and
the coordinator preflight handoff are identical under either reading. The
stricter reading is therefore the safe planning default; the coordinator can
relax it later without any rework.

Consequence: `docs/strategy/wlan.md` acceptance is restored to the two-boot
wording (consistent with the issue body and records rules). No device work,
no physical claim.
