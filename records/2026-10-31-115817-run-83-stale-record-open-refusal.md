---
date: 2026-10-31
run: 83
issue: omnipha/linux-sm7635#234
subsystem: boot
result: refuted
---
# Run 83: stale boot record refused before the cutover

Independent closeout from the physical coordinator's issue comment
`IC_kwDOVPfif88AAAABhf0g8w` and the preserved raw host evidence at
`attempt-20261031-1226-cutover-record-run83/`, cross-checked against
`sprintberlin/phone-second-life` commit `50d40c4f367d0a30f2ef0c78cc8aca63e045165b`.
No USB, SSH, flash, reboot, partition write, or cold start was performed here.
The acknowledged postmarketOS PID 1 and the independent no-ack return were not
measured, so the target capability is refuted for this run.

The merged-main verifier at `39eaae5` passed its self-test for exactly the
successor pair `dd6ce74e47827814c3c0010d6c71f0b9d0874a370cb147bb455e05f018ed6f41`
(init_boot) and `e7d5558037b903de3ab817619ce527319f6b54fb4ec97782e729078c666268fc`
(vendor_boot_b), refusing 78 earlier measured hashes including run-79
`a4ee7def` / `6e7c5a2e`. Device-op flash hooks verified writes to `init_boot_a`
and `vendor_boot_b` only; there was no userdata erase, Android start, stock
restore, or cold start. The pre-write diagnostic boot `cdc85c99` read exact
stock slot-A rescue hashes and the previously installed `a4ee7def` /
`6e7c5a2e`.

On diagnostic boot `893671f0-e8dc-4418-8d86-4c801e6007c6`, key-only SSH on
`:22` and root-only `/run/keep` worked. The boot stopped at kernel 4.509109 s
with `pmos-self-stage: FAIL: pmos-session-stage failed`, surfaced by the
session stage as `pmos-stage: FAIL: boot record open refused`. PID 1 remained
`/bin/busybox sh /init`. There was no `:2222`, no cutover, and no host ack.
The acknowledged PID-1 record, the clean no-ack guest reboot, and the 160-s
return were therefore not observable; the stop rules forbade a second flash
or another boot variant.

The persistent root still carried the complete run-79 record: 1010 bytes,
regular root-only file `0:600:1`, whose first line names boot
`28e8fa92-0694-4a54-b2b2-64090f0ac9b1` rather than the current boot.

Host-side attribution against merged `scripts/pmos-root-contract.sh`: the
refusal is the pre-existence guard in `boot_record_open`, `[ ! -e "$br_record"
] && [ ! -L "$br_record" ] || return 1`. The contract opens a fresh per-boot
record exclusively and refuses to overwrite or reuse an existing one, and the
run-79 file is exactly such a pre-existing record. This is the same fail-closed
rule that the host fixture's pre-existing-record case exercises; it is not the
foreign-boot-ID append/verify rule, which is a separate, later refusal for a
record that already exists. The refusal happened during staging, long before
guard arming or `switch_root`, so neither hypothesis (a) (a re-entered
transition arm tail) nor hypothesis (b) (a mis-settled uptime) is falsified by
this run: the cutover was never reached, and the earlier run-79 timing analysis
(armed 155.806 s + 160 s budget, boot ended at 274.18 s) is unchanged.

Rescue proof comes from the same diagnostic boot: exact stock
`boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`,
`vbmeta_a cc1926d2…cdffe`, and the newly installed carriers
`init_boot_a dd6ce74e…f6ed6f41` and `vendor_boot_b e7d55580…268fc`. The final
gate was fastboot `18d1:d00d`, slot a, unlocked, product pineapple. The
measured pair `dd6ce74e` / `e7d55580` is now never-reflash, as is every earlier
measured image. The coordinator closed the run.

The remaining boundary is host-side, not a new measurement for this issue: the
per-boot record contract must be reconciled with a persistent root that carries
a previous boot's record, and the acknowledged PID 1 plus independent no-ack
return remain unmeasured. That is for a strategist-routed successor; #234 is
closed on this recorded refusal.
