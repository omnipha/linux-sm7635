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

Run 95 (#265, shift testbootLog 2026-11-02T08:32Z; evidence
phone-second-life-data/mb003/pstore/attempt-20261102-0925-preack-trace-run95/kmsg-r95-final.log)
named the exit point. The contract is NOT the cause (the contract fallback,
pid1/root identity, guard boot id, root identity, `/run/keep` all passed).
Self-post exits at 156.55 s on the `armed and unacknowledged` check, because
`guard/nonce` is ABSENT (armed present, accepted/ack absent). Only the guard
watcher mints the nonce, and only once its own `post_root` is true. So before
the deadline return (~170 s) the guard never minted a nonce while self-post's
own copy of the same switched-root checks passed. Also: `/run/pmos-root-contract.sh`
is absent at that time (the guard copy exists), which is irrelevant until the
nonce check passes.

Next single variable (host first, no boot): why the guard watcher has no
nonce at ~156 s — (a) timing: when did the nonce appear relative to cutover in
the acked runs 93/94 captures (guard loop interval, chroot start), versus
self-post start; (b) `post_root` inside the guard's chroot differs from
self-post's checks (`/proc/1/exe` vs `/bin/busybox` hash, `$STATE/root-identity`
compared against `stat /` inside the chroot). Replay (b) on the host fixture
family. Only if host data cannot separate (a) from (b): one boot with trace-only
guard-loop lines. Do not change the nonce check in self-post to make it pass:
that check is the safety interlock with the guard.

## Order (binding)

1. Done: post-ack reads (runs 93/94) and pre-ack trace (run 95). Mount
   contract and non-mount inputs are eliminated.
2. Host: separate (a) and (b) above from the existing 93/94/95 captures and
   fixtures. Fix in the repo scripts; verify against the fixture family.
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
