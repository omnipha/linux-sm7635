# WLAN — strategy dossier for the active PLAN step

One file per active step. PLAN.md keeps the ladder; this file keeps the how.
Updated with each measured run, merged like any record.

## Measured to work

- Persistent root, run 69 (records/2026-10-30-203515-run-69-second-boot-guard-wlan.md):
  association, address, route, DNS, gateway, internet — after three repairs:
  1. remove the stale pinned `/run/pmos/bin/restart2` before re-arming the guard
  2. keep the surviving rmtfs log visible for the modem stage
  3. remove an empty persistent `/vendor/firmware_mnt` before the firmware bind
- Runs 98/99 (records/2026-11-02-170048-run98-acked-session-radio-chain-wlan-up.md,
  records/2026-11-02-192316-run99-persistent-services-acked-session.md): on the
  installed chain, the host-acked session reached internet; run 99 passed the
  persistent services variant, with no manual remoteproc writes. Neither boot
  proves autonomous startup.
- RAM-staged chain, runs 56/57 (records/2026-10-29-2292, 2294): same recipe
  plus `wpa_supplicant_if="wlan0"` in conf.d (otherwise p2p0 wins and the
  service fails). A failing supplicant does not take down USB SSH.

## Failing on the installed chain

- Run 84 and later boots: remoteproc2/3 stay offline, no wlan0,
  wpa_supplicant fails, self-post.log empty.
- Run 90, #253 (records/2026-11-01-104332-preack-selfpost-record-append-refused.md):
  worker-invoked pre-ack pmos-self-post.sh refuses BEFORE any radio stage —
  the post-cutover boot-record contract path `/run/pmos-root-contract.sh` is
  absent on the persistent root, and the guard's copy
  (`/run/pid1-guard/root-contract.sh`) makes the append refuse inside
  `root_contract_switched_root` although `sda13` PARTNAME=userdata matches.
  No modem/wpss/driver/scan/services stage ran; ordering hypothesis untested
  by the radio itself.
- 2026-11-01: manual modem start outside the pinned scripts crashed the
  kernel to QUSB 05c6:900e (no writes involved). Never repeat; the
  scripted gates exist exactly for this.
- Runs 89/91/92: dispatch-race losses around the 45–85 s pre-ack window
  (capture late, or worker never dispatched); zero new WLAN evidence.
  Never repeat that pattern.

## Current explanation

An acked live session can start the full radio chain, but the #291 candidate
requires an unacknowledged guard and never provides an ACK: without a further
success-gated transition it returns to fastboot. Run 97's pre-radio record
append refusal is still unresolved on the phone; #291's dmesg-format fix is
host-tested only. OpenRC ordering on a fresh boot is unmeasured.

## Next single variable

Complete and test the smallest deployable #294 success-gated candidate from
PR #295, then measure whether the installed chain starts WLAN and stays in
Linux without a host-run recipe. On 2026-11-03 01:30 CET the owner explicitly
chose the existing recovery and evidence mechanisms in issue #294, superseding
the earlier owner-review blocker. Adapt the fixtures and remove the deliberate
launch refusal only for the reviewed candidate: use the real same-boot guard
ACK only after association, address, DNS and internet succeed; publish no ACK
on a prior failure. Preserve the existing nonce, capture and recovery
interlocks, and do not use a competing host ACK during measurement. Avoid a
new image if the installed chain can carry the candidate.

The owner's risk choice does not repair the limits in
`records/2026-11-02-225455-success-gated-ack-owner-review-blockers.md`:
automatic recovery is not guaranteed before guard arming, if the watcher or
kernel fails, or after ACK publication; a published ACK may be accepted even
if its publisher is interrupted. Failure evidence can be volatile and the
strict acceptance-time deadline race remains. Report these limits, not a
guarantee of recovery on every failure. The pre-arm watchdog, watcher
supervisor, durable failure-record redesign and strict deadline change are
not prerequisites for this experiment.

Why this direction: run 84 measured an unacknowledged boot returning to
fastboot (records/2026-10-31-162218-run-84-record-rotation-cutover-noack-return.md).
#291's host-only candidate never ACKs, and an ACK during its pre-ack chain
consumes the nonce and causes later stages to refuse (record
`records/2026-11-02-203443-fresh-boot-candidate.md`). Therefore even two brief
Internet connections before the deadline cannot prove a phone that stays usable on its
own. #293 proposed exactly those two boots and is closed for that reason; do
not dispatch or deploy it. The panel-record dmesg format remains a hypothesis,
not the measured cause of run 97's append refusal.

Budget: finish the existing host candidate and its fixtures, then at most two
coordinator-owned fresh boots of the reviewed candidate, the second only if
the first passes and is safely closed or handed off. No new pre-radio-only
self-post image: that budget was spent in run 97. If the existing chain cannot
carry the candidate, stop with the concrete incompatibility and propose the
smallest reviewed change; do not substitute the four deferred architecture
projects or change the acceptance check. A temporary pre-deadline radio
measurement is not acceptance. (Plan owner, 2026-11-03.)

## Order (binding)

1. Done: the nonce timing and run-97 append refusal are recorded; the budget
   for images whose only purpose is passing a pre-radio check is exhausted.
2. Done: runs 98/99 measured the radio chain, persistent services,
   association, address, DNS and internet in host-acked sessions.
3. Done on host only: #291 derived the persistent fresh-boot hook and radio
   candidate; it cannot maintain a no-host boot because it never acknowledges.
4. #294 derived and fixture-tested the gate, but its hook refuses launch;
   the owner has now accepted the existing recovery/evidence limits for this
   experiment. Complete the deployable candidate and adapt its host fixtures;
   do not treat the prior review request as still blocking it.
5. The coordinator installs the reviewed candidate under existing backup and
   recovery procedures and measures one fresh boot, then a second only when
   the first passes. A merged device record is required for the PLAN check.

## Acceptance (from PLAN.md)

Fresh boot: radio chain self-starts, wlan0 associates, address, DNS,
internet; a second boot repeats all of it. No host-run recipe. Both boots
must remain in Linux beyond the guard deadline; a connection followed by
an automatic return to fastboot is not acceptance.

## Not this

- No manual remoteproc or radio writes outside the pinned scripts.
- No worker-in-window pre-ack probes; a pre-armed capture observes pre-ack state.
- No image for a question a live session can answer.
- No unattended guard ACK except the reviewed, real same-boot success-gated
  protocol; do not claim the existing recovery covers the known failure limits.
- Issue #288: an unowned key-only dropbear listener on WLAN `:22` recurs with
  DHCP. Whether it is deliberate is unproven; the separate owner decision and
  possible removal remain open, and the listener is not a PLAN acceptance test.
