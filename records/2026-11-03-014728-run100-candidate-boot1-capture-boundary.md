---
date: 2026-11-03
run: 100
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: inconclusive
---
# Run 100 candidate boot 1: pre-radio trace boundary

First fresh boot of the PR #296 candidate, no new image; this is not a passing
WLAN boot. The prior setup boot was distinct and closed before this boot. The
physical coordinator installed and verified the candidate using existing backup
and recovery procedures, then started the measurement. This worker did not
flash, reboot, issue a host ACK, run a radio recipe, write remoteproc state or
close the session. The coordinator owns those boundaries. Issue #294 remains
open; no second candidate boot is authorized by the result below.

## Observations

- The coordinator's session-open and fresh-marker handoff named the same boot
  `b2b90876-f13c-4faa-8031-91b8463e53e4`. This worker independently verified the
  open/handoff state, live capture readiness and marker, pinned ED25519 host
  fingerprint, key-only SSH, boot ID, root identity and regular root-owned
  `0600` `/run/keep` on that boot.
- The coordinator's same-boot inspection at uptime 202.61 s recorded the
  expected hashes for radio `a0ea867a...`, gated post `9a8c40ad...`, and hook
  `ac3593d9...`; it also found the separately staged older self-post
  `100be54d...`. At uptime 224.21 s the candidate hook was still present, the
  guard had armed and nonce files but no accepted ACK, the gate state was
  absent, WLAN was absent, and no self-post process was listed. These are
  coordinator observations, not proof of which script opened at launch.
- The captured self-post trace reached `pre check panel record` at uptime
  157.677 s, with no later self-post trace, radio marker or success-gate line
  in that boot's capture. The capture contains the early same-boot panel line.
  The capture itself continued beyond the trace: the coordinator recorded
  fastboot at 01:46:24Z, near the unacknowledged guard deadline. A later SSH
  attempt timed out and capture readiness disappeared. The coordinator
  subsequently closed the unresponsive session at 01:46:46Z with slot-A rescue
  verified. This worker stopped guest access; no current Linux session is
  claimed.
- The coordinator reports no host ACK or host-run radio recipe, no measured
  WLAN or real accepted ACK, and no second boot. Association, address, DNS and
  internet were not measured on this boot. The separately captured setup-boot
  append refusal is not this boot's evidence. `wlan0` absent at 224.21 s is a
  point observation; it does not identify the launcher or every earlier event.

## Offline hypothesis, not a device diagnosis

Both the persistent gated post and staged old post carry the same trace labels.
The correct candidate hook was observed after startup and targets the persistent
post, but neither the trace label nor the staged file's presence proves which
script was opened at launch. An absent gate is also consistent with a prefix
exit before gate initialization. Do not treat the old-script hash alone as
proof of execution or assume an installation race.

The exact pinned #291-derived panel pipeline, retained in #294, ends with
`grep` under BusyBox `sh -eu`. A host-only synthetic replay in
`scripts/test-derive-radio-fresh-boot.py` shows that when the restore branch
runs and no line matches, its assignment exits before the post-check trace;
the older pipeline ends in `sed` and continues on the same synthetic no-match.
The fixture covers raw priority, timestamp, duplicates, conflicts, foreign boot,
record mismatch, missing output and synthetic timestamp-plus-caller formats.
The latter, e.g. `[    1.562660][    T1]`, is not recognized by either current
parser. These are host BusyBox synthetic inputs, not the device's actual
`dmesg` output. A matching line in the earlier `/dev/kmsg` capture does not
prove that the later guest snapshot contained it or had the same formatting.

The actual guest panel-file state, command exit status and exact same-time
`dmesg` format were not captured. A failed producer, no match, pipeline stall,
other process termination, or lost trace remain possible. If the panel file is
absent and no validated matching line can be restored, suppressing the pipeline
exit alone cannot repair the ordered-record append: the unchanged contract
requires the existing panel line in its expected sequence. Do not bypass the
line-3 equality, nonce, capture gate, guard or ACK checks. A caller-format
hypothesis is not sufficient evidence to install an untested successor.

## Verification and next safe step

Host-only checks passed: `python3 -B scripts/test-derive-radio-fresh-boot.py`,
`python3 -B scripts/test-derive-success-gated-ack.py`,
`ruff check --no-cache --ignore EXE001 scripts/test-derive-radio-fresh-boot.py`
(the existing non-executable shebang triggers EXE001),
`mypy --cache-dir /dev/null --check-untyped-defs scripts/test-derive-radio-fresh-boot.py`,
and `git diff --check`. The new fixture reproduces a shell control-flow edge;
it does not fix the candidate or show why the phone stopped.

The next useful question is the actual same-boot guest `dmesg` status and panel
line format at the restore boundary, panel-file metadata, and the identity of
any running self-post process, under a newly coordinator-proven session with
live capture and `/run/keep`. If the same boot is still in progress, do not
interfere with the measurement or run a second post. If no suitable live
session exists, the coordinator owns any separately approved recovery/setup
and capture decision; never reuse a stale boot ID or silently repeat the failed
candidate boot. A fresh boot remains necessary to prove autonomous start and
lasting guard acceptance, twice; a live-session diagnosis does not satisfy it.
The existing recovery limitations in the prior candidate record remain.
