---
date: 2026-10-31
run: 84
issue: omnipha/linux-sm7635#237
subsystem: boot
result: confirmed
---
# run 84: record rotation boots, cutover acks, no-ack return is independent

Physical result for #237 on the record-rotation successor pair. Attempt dir
`~/phone-second-life-data/mb003/pstore/attempt-20261031-1640-record-rotation-run84/`
(host-only, not in git). Device record: sprintberlin/phone-second-life@950b505
devices/mb003.md. The prior coordinator tick died while watching the no-ack
return; this tick only re-verified identity and recorded the already-measured
result (no additional device writes).

Merged-main verifier (83d6803) accepted exactly the successor pair
`init_boot 27c4d895` / `vendor_boot_b da4651d8` (80 refused hashes, including
run-83 `dd6ce74e`/`e7d55580` and run-79). Only `init_boot_a` and
`vendor_boot_b` were written, via device-op verified hooks. No other partition,
no userdata erase, no Android boot, no cold start, no second flash, no third
boot variant.

Boot `e17dac48-e09e-4d81-b81a-c56584a40b1c`: key-only SSH on `:22` and `:2222`
with the same pinned host key, root-only `/run/keep` (`0:600:1`). Rotation is
verified on-device: the run-79 record (1010 bytes, boot `28e8fa92`) is archived
root-only as `.omnipha-boot-record-28e8fa92-0694-4a54-b2b2-64090f0ac9b1` and a
fresh 933-byte record names `e17dac48`. The run-83 `boot record open refused`
deadlock is closed.

Cutover with exactly one host pid1-ack: `accepted on boot e17dac48`;
postmarketOS PID 1 `/sbin/init` (v24.12) measured; guard `armed` + `accepted`
for the same boot; the post-cutover record (1010 bytes, `0:600:1`) ends in the
`switch_root` line.

Clean guest reboot with no host ack: fresh boot `32b8a77d` came up with
root-only `/run/keep` and an armed guard while the host stayed passive (no
restart2). The device returned independently to responsive fastboot
`18d1:d00d` (USB watch `18d1:4ee2` until 17:10:47, `18d1:d00d` from 17:10:52
local; final gate serial `00181152O003821`, slot a, unlocked, pineapple). The
exact 160 s deadline interval was not separately timed and stays approximate.

Radio/WLAN on this chain: `wlan0` absent, OpenRC `wpa_supplicant` failed,
`networking` stopped; USB net up. Display diagnosis was not measured because
the guarded chain returned to fastboot before the read-only collection; the
panel question stays live-session work.

Rescue path verified, no restore performed: the same boot read stock `boot_a
197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`, `vbmeta_a cc1926d2`
exactly, plus installed `init_boot_a 27c4d895` / `vendor_boot_b da4651d8`
exactly. Host backup manifests parts/parts-a/parts-b fully OK. `27c4d895` and
`da4651d8` are measured and never-reflash. Linux stays installed per owner
rule.
