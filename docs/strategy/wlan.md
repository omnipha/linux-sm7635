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
success-gated transition it returns to fastboot. The owner chose the minimal
success-gated #294 candidate, now installed and host-tested. On fresh boot
100 the captured self-post trace stopped at the panel-record pre-check; at
224 s wlan0 and the gate state were absent and no ACK was accepted. The guard
returned the phone to fastboot; why the trace stopped or which self-post was
launched is not proven. The synthetic BusyBox panel-pipeline failure in the
run-100 record is a hypothesis, not a device diagnosis. Run 97's pre-radio
record append refusal is still unresolved on the phone; OpenRC ordering on a
fresh boot is unmeasured.

Run 101 did not boot: no post-run-100 pstore pull is recorded, fastboot fetch
is unsupported, and the observed recovery route started Linux and could
overwrite unknown pstore contents. The verified host console is not a pstore
pull (records/2026-11-03-023259-run101-preboot-pstore-access-blocker.md).
The bounded #298 investigation found no demonstrated non-overwriting route or
equivalent (records/2026-11-03-031528-pstore-preservation-host-evidence.md).
Separately, the coordinator replayed an actual historical run-95 guest panel
line with a timestamp and caller prefix: the candidate parser exited under
BusyBox, while the prefix-stripped control passed (#294 comment
https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6597114588).
This is host evidence for a parser limitation, not the actual run-100 guest
snapshot, a pstore pull or proof of the run-100 cause.

## Next single variable

While the physical preservation decision remains open, independently vet and
run the bounded host-only #301: does the candidate preserve the valid panel
record with the historically observed timestamp-plus-caller prefix, while
rejecting foreign-boot, duplicate/conflicting and absent-panel input? Compare
the prefix-stripped control, preserve ordered line-3 equality and all nonce,
capture, guard and success-ACK checks, and document any smallest supported
parser correction or the remaining discriminator. This is a single format
variable, not permission to deploy a speculative fix or a diagnosis of run 100.
The strategist must qualify #301 before the supervisor dispatches it. No
device operation, image, deployment or physical handoff is part of this work.
The coordinator alone assesses any later preservation route against its contract.

After a coordinator-verifiable preservation route or an explicit owner choice
to accept potential evidence loss, continue #294 in its retained context: use
a newly coordinator-proven live capture/handoff to measure the actual same-boot panel
file, dmesg status/format and launch provenance, then make only the smallest
evidence-supported correction. Do not repeat the failed boot as acceptance or
infer its cause from the host fixture. Ultimately measure autonomous WLAN and
lasting Linux on two fresh boots, without a host-run recipe or competing ACK;
the second only after the first passes. The candidate publishes a real
same-boot guard ACK only after association, address, DNS and internet succeed.

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

Budget: #298's one bounded preservation investigation is spent; it did not
find a proven route, which is not proof that none exists. Permit one bounded
host-only #301 format/ordered-record investigation while the distinct physical
hold remains in force; do not expand it into an open-ended search. Then at most
one coordinator-owned diagnostic session under the applicable evidence,
capture and recovery gates, followed by an evidence-led
review before any new acceptance attempt. Run 100 spent the first candidate
boot and failed; the previously budgeted second is not authorized as a passing
repeat. A future corrected candidate still needs two passing fresh boots,
the second only if the first passes and is safely closed or handed off. No new
pre-radio-only self-post image: that budget was spent in run 97.

Fallback: if no non-overwriting path can be demonstrated, stop before boot and
raise an explicit owner decision on preserving the unknown pstore versus
accepting its potential loss; the existing device-iteration approval is not a
pstore-preservation waiver. Do not weaken the interlocks, invent an equivalent
pstore pull, substitute the four deferred architecture projects, or change the
acceptance check. A temporary pre-deadline radio measurement is not acceptance.
(Plan owner, 2026-11-03.)

## Order (binding)

1. Done: the nonce timing and run-97 append refusal are recorded; the budget
   for images whose only purpose is passing a pre-radio check is exhausted.
2. Done: runs 98/99 measured the radio chain, persistent services,
   association, address, DNS and internet in host-acked sessions.
3. Done on host only: #291 derived the persistent fresh-boot hook and radio
   candidate; it cannot maintain a no-host boot because it never acknowledges.
4. Done on host only: #294 enabled and fixture-tested the pinned hook and
   success gate under the owner's accepted recovery/evidence limits. Fresh-boot
   service ordering and readiness within the guard budget remain unmeasured.
5. Run 100 installed and measured the candidate: first boot failed before
   WLAN/ACK, and no second boot was attempted. Run 101 exposed the pstore
   preservation blocker; #298 found no demonstrated non-overwriting route.
   #301 can test the historical panel format on the host without clearing it.
6. Once preservation is verified or the owner explicitly accepts the risk of
   losing the unknown pstore, diagnose #294 with a fresh proven live handoff;
   correct the measured cause before trying acceptance.
   Two passing fresh boots and merged device records remain required.

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
