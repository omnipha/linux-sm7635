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

## Current explanation

The radio chain runs as self-post before the guard ack. Recent boots ack
first (or self-post never runs), so the pinned bring-up refuses by design
and nothing starts the radio.

## Next single variable

Host-only #256 fixture (records/2026-11-01-120601-host-run90-switched-root-fixture-passes.md):
the pinned contract ACCEPTS the exact run-90 post-cutover state — the live
refusal is not reproducible host-side, so the next single variable is the live
PID 1 mountinfo itself. In the live window: capture `cat /proc/1/mountinfo`
before re-invoking the pinned `pmos-self-post.sh` with
`PMOS_ROOT_CONTRACT=/run/pid1-guard/root-contract.sh`, diff against the host
fixture, and fix only the measured divergence (likely a second sda13 mount
invisible in /proc/1/mounts). Only if the append then completes and the radio
chain works pre-ack, record the recipe and integrate exactly this into one
image. One boot per change.

## Acceptance (from PLAN.md)

Fresh boot: radio chain self-starts, wlan0 associates, address, DNS,
internet; a second boot repeats all of it. No host-run recipe.

## Not this

- No manual remoteproc or radio writes outside the pinned scripts.
- No image for a question a live session can answer.
