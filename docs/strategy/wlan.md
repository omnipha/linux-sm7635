# WLAN — strategy dossier for the active PLAN step

One file per active step. PLAN.md keeps the ladder; this file keeps the how.
Updated with each measured run, merged like any record.

## Measured to work

- Persistent root, run 69 (records/2026-10-30-203515-run-69-second-boot-guard-wlan.md):
  association, address, route, DNS, gateway, internet — after three repairs:
  1. remove the stale pinned `/run/pmos/bin/restart2` before re-arming the guard
  2. keep the surviving rmtfs log visible for the modem stage
  3. remove an empty persistent `/vendor/firmware_mnt` before the firmware bind
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

The radio chain runs as self-post before the guard ack. Recent boots ack
first (or self-post never runs), so the pinned bring-up refuses by design
and nothing starts the radio.

## Next single variable

Run 95 (#265) named the exit point: self-post exits at 156.55 s on the
`armed and unacknowledged` check because `guard/nonce` is absent.

Step 2 done on the host (#268,
records/2026-11-02-094850-host-guard-nonce-timing-vs-chroot.md): (a) timing
confirmed, (b) chroot divergence refuted. All three captures (93/94/95) show
self-post dying 0.4–0.6 s after the transition line; the acked runs 93/94
prove the same guard minted the nonce at uptime ≈157 s, ≈1–2.5 s after
cutover (the ack's strict probe requires the nonce). Self-post asked too
early, once. Run 95 itself has no post-cutover nonce read (its guard-state
capture predates cutover), so the 2 s mint on that boot is inferred, not
measured.

Fix merged with #268: self-post waits up to 20 s for the nonce (re-asserting
armed/accepted/ack each second; the check itself is unchanged), and sources
the post-cutover contract from the guard copy when `/run/pmos-root-contract.sh`
is absent (the measured run-90/95 shape, otherwise the very next check would
die). Fixtures replay the exact run-95 script failing on a late nonce and the
fixed script passing; never-minted nonce still refuses after 20 s.

Next single variable (dossier step 3, #271): ONE boot of the host-verified
init_boot 17531039 carrying this self-post (27a78a22 stays never-reflash;
installed vendor_boot_b a71b3f5f stays), pre-armed `:2222` capture, no
worker racing the pre-ack guard. Builder/carrier mismatch found and fixed:
records/2026-11-02-114833-host-nonce-wait-initboot.md. Prediction: nonce check
passes ≈1–2 s after cutover, post-cutover record appends, radio stages run.
If the full 20 s actually elapses without a nonce, that kmsg decides the
guard-design question; an earlier guard return is not an elapsed 20 s wait.

Run 96 (#271, records/2026-11-02-130607-run96-correction.md): the nonce wait
passed (nonce minted within ~1 s), the contract fallback passed, then
`boot_record_append` refused. Dossier step 4 (#275): the refusal is the
ordered-sequence check, because the pre-SSH panel file stays on the outer
initramfs `/run` and `boot_record_lines` omits the persisted panel line
(records/2026-11-02-142315-host-append-refusal-reproduction.md). Fix in the
trace member only: restore the panel file from this boot's kernel log (must
equal record line 3), name any refusing check in kmsg. Image 2ebdf1db, carrier
a71b3f5f unchanged: records/2026-11-02-142315-host-append-refusal-panel-record-initboot.md.
One boot next; not WLAN acceptance.

## Order (binding)

1. Done: post-ack reads (runs 93/94) and pre-ack trace (run 95). Mount
   contract and non-mount inputs are eliminated.
2. Done: #268 separated (a)/(b) on the host (timing) and fixed self-post
   (bounded nonce wait + guard-contract fallback) with fixtures.
3. Validate once with a pre-armed `:2222` capture, one guest reboot, no
   worker racing the unacknowledged guard.
4. Exactly one image carries the measured working chain. Acceptance per
   PLAN.md: two fresh boots, radio chain self-starts, wlan0 associates,
   address, DNS, internet. No host recipe.
5. Budget: this step has taken the runs 84-95 (more than a week) without one
   radio stage executing. If step 2 does not separate (a)/(b) on the host, the
   cheaper path is to drop the pre-ack self-post and start the radio chain
   after the ack from the live session (run 69 recipe), then ask whether the
   guard design itself should change.

## Acceptance (from PLAN.md)

Fresh boot: radio chain self-starts, wlan0 associates, address, DNS,
internet; a second boot repeats all of it. No host-run recipe.

## Not this

- No manual remoteproc or radio writes outside the pinned scripts.
- No worker-in-window pre-ack probes; a pre-armed capture observes pre-ack state.
- No image for a question a live session can answer.
