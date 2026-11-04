---
date: 2026-11-04
issue: linux-sm7635#311
subsystem: wlan
result: inconclusive
---
# pair producer verified consumer gate still open

Coordinator run, 2026-11-04 ~06:2x UTC: the producer delivery event for
the #311 physical gate was processed (supervisor tick 74f80fb2, event
`sm7635-handoff-311-verified-pair-manifest-31ea4fe`). The worker is idle
at `AWAITING_PHYSICAL_RESULT`; PR #319 is merged as `31ea4fe` and publishes
the fail-closed dependent-pair declaration.

Independent coordinator checks on the host (read-only, no build, no
rebuild): `scripts/verify-dependent-pair-manifest.py verify …` on the
published `root-contract-pair.manifest.json` (`c69e4b39…`) passes and
re-binds the unchanged pair — init_boot_a `d7bba454…` (8388608 B) and
vendor_boot_b `221bfd82…` (100663296 B), both 0600 and settled. All three
stock host backup manifests (parts, parts-a, parts-b) pass. A fresh
read-only device gate at 06:21 UTC confirms fastboot serial
`00181152O003821`, slot a, unlocked, product `pineapple`, userspace no,
and the expected partition sizes; no fresh on-device rescue or carrier
hash was read.

No boot or flash was started, for two measured-contract reasons. First,
the coordinator consumer at `omnipha/agents@4195496` still emits the #311
candidate as a one-partition `init_boot_a` artifact event that omits the
pinned vendor carrier; the explicit positive pair consumer remains open at
[omnipha/agents#118](https://github.com/omnipha/agents/issues/118) (PR
#119 quarantine-only), and the producer event text is not a substitute for
that gate. Second, the pre-boot pstore capture after the run-106
SSH/capture loss is not established; the owner's mission-scoped loss
decision is recorded, but the contract reconciliation stays open at
[omnipha/agents#112](https://github.com/omnipha/agents/issues/112).

Neither candidate hash appears in the 72 recorded attempts, the device
flash SHA ledger, or the committed refusal registry. The altered run-106
radio (`d7b74c24…`) must not run. No erase, Android boot, stock restore,
host ACK or radio action occurred. Linux remains installed; the artifact
receipt stays pending until a measured pair attempt lands. Raw private
evidence: `~/phone-second-life-data/mb003/pstore/hostcheck-20261104-pair-coordinator/`.
