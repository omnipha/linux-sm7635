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

Run 93 (#261, records/2026-11-01-151916-run93-postack-mountinfo-matches-fixture.md):
live post-cutover `/proc/1/mountinfo` measured — exactly one `sda13`/`8:13`
mount at `/`, no second same-partition mount, no `/vendor/firmware_mnt`
leftover. The unchanged contract accepts the captured table (now a fixture);
the mount-info divergence hypothesis is refuted. Next single variable: the
non-mount contract inputs at self-post time — the live `/sys/class/block`
PARTNAME walk, the guest `/dev/block/sda13` node stat and `blockdev` size —
captured read-only post-ack, or an instrumented self-post failure exit point.

## Order (binding)

1. Post-ack session read, no window pressure: on the next open session read
   `/proc/1/mountinfo`, `/proc/1/mounts` and the staged contract paths
   (`/run/pmos-root-contract.sh`, `/run/pid1-guard/root-contract.sh`).
   An ack changes no mount; this read needs no pre-ack window.
2. Diff against the #256/#257 fixture; name the one diverging check or the
   missing staging path. Fix it in the repo scripts; verify against the
   fixture family. Host-only, no boot.
3. Validate without a dispatch race: stage the fixed chain on the persistent
   root (if init restages it from the boot image, that fix goes into the one
   image instead), pre-arm the `:2222` capture, one guest reboot. The
   pre-armed capture observes the pre-ack state; no worker races the
   unacknowledged guard.
4. Exactly one image carries the measured working chain. Acceptance per
   PLAN.md: two fresh boots, radio chain self-starts, wlan0 associates,
   address, DNS, internet. No host recipe.

## Acceptance (from PLAN.md)

Fresh boot: radio chain self-starts, wlan0 associates, address, DNS,
internet; a second boot repeats all of it. No host-run recipe.

## Not this

- No manual remoteproc or radio writes outside the pinned scripts.
- No worker-in-window pre-ack probes; a pre-armed capture observes pre-ack state.
- No image for a question a live session can answer.
