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

Run 97 (#275) landed in (B) again: the ordered-sequence check still refused the
append and no radio stage ran (records/2026-11-02-145742, correction
records/2026-11-02-150805). Step 5 below therefore binds: the self-post image
budget is spent. Next single variable (#280, open agent-ready): start the pinned
radio chain from ONE pid1-acked live session on the installed init_boot_a
2ebdf1db + vendor_boot_b a71b3f5f chain — no new image, no self-post
instrumentation, no manual remoteproc writes (run 69 recipe). Measure the first
radio stage and name its result; only then revisit the guard design. Do not
build another pre-radio self-post image. (Plan owner, 2026-11-02 16:40.)

Host-only #284 (records/2026-11-02-180959-services-stage-persistent-root-aware.md):
the persistent-root-aware `services` variant accepts its own earlier output and
still refuses foreign conf.d/runlevel/lease/profile state; fixtures replay both
variants. The installed pinned radio script and image pins are byte-identical;
derivations reproduce the variant for the repo script and the run-98 staged copy.
The lease helper's WLAN `:22` listener is an unowned run-66 bundle leftover, not
an established deliberate design. Next single variable: validate the derived
variant in one acked live session, then the self-post/OpenRC ordering that
recreates the `/run` helpers on a fresh boot. No image built.

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
5. Budget: this step has taken the runs 84-96 (more than a week) without one
   radio stage executing; run 96 again died before any radio stage, one append
   check later. #275 (run 97) is the last image whose only job is to get
   self-post past a pre-radio check. If run 97 ends in (B) or (C), the next
   issue is NOT another self-post image: start the radio chain from the acked
   live session with the pinned scripts (run 69 recipe, no manual remoteproc
   writes) on the installed chain, to measure the first radio stage at all,
   then ask whether the guard design should change. Outcome (A)/(D) continues
   as written. (Plan owner, 2026-11-02.)

## Acceptance (from PLAN.md)

Fresh boot: radio chain self-starts, wlan0 associates, address, DNS,
internet; a second boot repeats all of it. No host-run recipe.

## Not this

- No manual remoteproc or radio writes outside the pinned scripts.
- No worker-in-window pre-ack probes; a pre-armed capture observes pre-ack state.
- No image for a question a live session can answer.
