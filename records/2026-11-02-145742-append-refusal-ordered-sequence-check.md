---
date: 2026-11-02
run: 97
issue: omnipha/linux-sm7635#275
subsystem: wlan
result: confirmed
---
# Run 97 (#275) outcome B: the append is refused by the ordered-sequence check; the refusing check is now named in kmsg

Coordinator record for the one authorized boot of
`init_boot-append-refusal-275.img` (8388608 B,
`2ebdf1db26193f7f0c3f4c6d42f722008bd1ee2718adf399dfe4927cc3eb9632`),
issue omnipha/linux-sm7635#275, standing approval
`full_autonomy_device_iteration`. Exactly one partition write
(`init_boot_a`, 14:46Z); `vendor_boot_b a71b3f5f` stayed installed, the
byte-identical companion was not flashed; stock `boot_a`/`vendor_boot_a`/
`dtbo_a`/`vbmeta_a` untouched. No erase, no Android boot, no cold start, no
manual remoteproc/radio write, no pid1-ack.

## Measured (boot 1a64e6d8, pre-armed :2222 capture, handoff proven)

- Key-only SSH :22/:2222 with root-only `/run/keep`; session open, handoff
  marker `run97_handoff_1793630802_275` on the console.
- The trace lines added by #276 all fired before the failure: post-cutover
  contract rc=0 (pre and post), panel record rc=0 (pre and post),
  `record append entry`, guard nonce present (65 B, minted before the wait
  would have mattered), guard `root-contract.sh` present (14807 B), guard
  dir 0:700 with matching boot id, `/run/keep` present,
  `/run/pmos-root-contract.sh` absent.
- At uptime 157.78: `FAIL: post-cutover boot record append refused`, then the
  new kmsg line naming the refusing check:
  `append refusal check: boot_record_append: ordered sequence check, record
  plus new line is not a prefix of the expected lines; panel record file
  absent; record line 3 is a panel line yes`.
- No modem/wpss/driver/scan/services stage ran; `wlan0` absent. The
  independent no-ack guard returned the device to responsive fastboot at
  ~280 s (14:51:51Z), as designed.

## Interpretation (measured, no speculation)

The #276 diagnostics work: the refusal is now attributable. The append
refuses because the existing record plus the new line is not a prefix of the
expected lines, and the reason the sequence does not match is a panel-line
shape problem: record line 3 is a panel line while the panel record file is
absent. That is the next single variable for the worker; the radio chain
stays unmeasured.

## Integrity

On-device hashes on the same boot, exact: stock `boot_a 197aff11`,
`vendor_boot_a 23725940`, `dtbo_a 759813db`, `vbmeta_a cc1926d2`; installed
`init_boot_a 2ebdf1db`, `vendor_boot_b a71b3f5f`. Session close `landed`
with the rescue verifier; final fastboot gate exact (serial
00181152O003821, slot a, unlocked, pineapple, is-userspace no). No rollback
needed; Linux stays on the phone per owner rule.

Raw evidence (device data, outside Git):
`~/phone-second-life-data/mb003/pstore/attempt-20261102-1550-append-refusal-run97/`.
Device file entry: sprintberlin/phone-second-life@9844072 (mb003 run 97).
