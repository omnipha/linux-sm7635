---
date: 2026-11-02
issue: omnipha/linux-sm7635#268
subsystem: wlan
result: confirmed
---
# Host separation of guard nonce timing vs post_root-in-chroot: timing (a) is supported, chroot divergence (b) is refuted; self-post now waits a bounded time for the nonce and falls back to the guard-staged contract

Issue #268, outcome: the host data separates (a) from (b). Host-only, no boot,
no flash, no device action. The installed never-reflash pair (init_boot_a
27a78a22, vendor_boot_b a71b3f5f) was not touched; the phone stayed in
fastboot. Evidence is the host-only attempt dirs of runs 93, 94 and 95 under
`~/phone-second-life-data/mb003/pstore/` (not in git); the files were read
directly.

## What the three captures show

Same cutover shape in all three boots (kmsg kernel seconds):

| run | transition line | self-post nonce-check FAIL | `capture/kmsg.log` |
| --- | --- | --- | --- |
| 93 | 155.861 | 156.439 (`independent recovery guard is not armed and unacknowledged`) | line 2578 |
| 94 | 155.985 | 156.563 (same message) | line 2595 |
| 95 | 155.964 | 156.548 (same message, after `pre check guard armed and unacknowledged` at 156.546) | line 2624 |

So self-post died 0.4–0.6 s after the transition line in every one of these
boots. Only run 95 carries trace lines that name the nonce clause; for runs
93/94 the nonce clause follows by elimination (the message is shared by the
armed, nonce, accepted and ack clauses, but `armed` was present, and
`accepted`/`ack` could not exist before the ack). Same guard script
(`scripts/pmos-pid1-guard.sh`, sha256 f72a68a4…0226d3ad; the staged copy is
10705 bytes, equal to the repo file's size).

Runs 93 and 94 then acked successfully on the same chain:

- Run 94: the driver saw `armed` and started the ack script at 16:41:16Z;
  `ack-r94.txt` says `pid1-ack: accepted on boot ec970efc-…`, ACK_RC=0. The
  ack script's first action is a strict probe that requires
  `/proc/1/root/run/pid1-guard/nonce` to exist, so the nonce existed at that
  moment. Postack evidence at 16:41:18Z reads uptime 159.33 s, so the probe
  ran at uptime ≈157 s (±1 s clock granularity), i.e. at most ≈1–2.5 s after
  the transition line.
- Run 93: `ack-r93.txt` also says accepted (ACK_RC=0) at 15:14:58Z; postack
  evidence at 15:21:09Z reads uptime 528.06 s, so the ack started at uptime
  ≈157 s, again ≈1–2.5 s after the transition line. (The earlier run-93
  record's remark about a failed nonce probe does not match the
  `ack-r93.txt` file on disk; this record relies on the file. It does not
  change the result: either way the nonce existed within seconds in run 94.)

Hence: on this chain the guard watcher mints its nonce within roughly 2 s of
cutover, while self-post asks 0.4–0.6 s after cutover and never asks again.

## (a) timing: supported. (b) divergence: refuted

(b) predicts that the guard's own `post_root` is refused inside its chroot.
The same guard, same image family and same persistent root minted the nonce
in runs 93 and 94, so `post_root` is true inside the chroot on this chain.
Run 95 ran the identical guard script; its self-post trace (156.45–156.54 s)
shows every identity input the guard also checks (pid1 exe hash, pid1/root
identity 2061:2, guard dir 0:700, armed = boot id, contract fallback)
passing.

(a) fits all three boots: the check ran before the guard's first successful
poll. The two scripts differ in one more way that makes this visible: the
watch loop's first `post_root` iteration hashes `/proc/1/exe` and
`/bin/busybox` and runs the ext4 contract branch (≈86 ms in self-post,
measured 156.449→156.535 in run 95), and the nonce is minted only after
that, within the loop.

What the host data does NOT prove: run 95 itself was never read for the
nonce after self-post died (the coordinator's `guard-state.txt` in that
attempt dir is empty: it was read at ≈39 s uptime, before cutover). So
"the guard would have minted the nonce in run 95 within 2 s" is carried over
from runs 93/94, not measured on run 95's own boot. Hence the successor boot
below.

## Fix (not a change to the interlock)

`scripts/pmos-self-post.sh`:

1. Before the unchanged armed-and-unacknowledged check, a wait loop (max 20 s,
   1 s interval) for `guard/nonce` to appear. On every iteration it
   re-asserts `armed == boot id` and `accepted`/`ack` absent; an
   acknowledged guard or changed boot still dies immediately, and a nonce
   that never mints dies after 20 s with the same message. The check
   itself is byte-identical. The wait ends well inside the guard's 160 s
   budget.
2. The post-cutover contract sourcing falls back to `$GUARD/root-contract.sh`
   when `/run/pmos-root-contract.sh` is absent. Measured need: that path was
   absent in run 90 and in run 95's state lines, so with fix 1 alone
   self-post would die at the very next check
   (`post-cutover boot record contract unavailable`). The fallback is the
   same contract file the script already sources for its switched-root check.

## Fixture proof (`scripts/test-pmos-root-contract.sh`, ext4-ack worker, real guard)

- Pre-fix replay: the exact run-95 script is rederived by removing the two
  additions (sha256 3195dee9…24bc6b, the value the test asserts); with the
  nonce planted 4 s after start it FAILS at the nonce check.
- Fixed script, same late nonce: waits (`guard nonce wait 0` trace), passes
  the unchanged check, reaches record append/verify.
- Never-minted nonce: waits the full 20 s, dies with the unchanged message;
  `record append entry` is never reached.
- Contract fallback: with the default path removed (run-95 shape) self-post
  passes the contract check and appends via the guard copy; with the guard
  copy removed too it refuses at the first contract-dependent check
  (fail closed).
- Unchanged: wrong-PARTNAME, acked-guard (still refused immediately),
  trace-free vs traced output and record equivalence.
- Suite green: test-pmos-pid1 (6 cases), test-pmos-boot-record,
  test-pmos-self-stage, test-pmos-radio-bringup, test-pmos-root-contract.
  Pins re-derived: plain self-post 6199649f…c1041d, bundled
  dcfe1cf5…6bce3150 (`SELF_POST_BUNDLE_SHA`).
- Not exercised here: the persistent-root image build/verify scripts need the
  private WLAN profile and artifacts, so the successor image is not built in
  this issue.

## Next single variable (successor issue, not this one)

One boot of an image carrying this self-post (a new init_boot hash; the
installed 27a78a22 stays never-reflash), pre-armed `:2222` capture, no worker
in the pre-ack window. Prediction: the pre-ack self-post passes the nonce
check ≈1–2 s after cutover, appends the post-cutover record and reaches the
radio stages. If the nonce has not minted within 20 s, that kmsg decides the
guard-design question in the dossier (drop pre-ack self-post, start the radio
chain after the ack from the live session: an owner product decision). Not
WLAN acceptance: acceptance stays two fresh self-starting boots per PLAN.md.
