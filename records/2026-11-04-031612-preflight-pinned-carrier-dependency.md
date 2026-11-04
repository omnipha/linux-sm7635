---
date: 2026-11-04
run: 108
issue: linux-sm7635#311
subsystem: wlan
result: inconclusive
---
# preflight pinned carrier dependency

Run 108, 2026-11-04: the coordinator stopped the #311 artifact before
boot or flash. The submitted event declares only `init_boot_a`, while
PR #316 delivers a dependent pair: init `d7bba454…` and `vendor_boot_b`
`221bfd82…`. The merged pair passed its host verifier, but the new init
pins carrier header `41ac1259…`; the host image matching the last directly
measured installed `vendor_boot_b` (`a71b3f5f…`, run 106) has header
`4e01f560…`. Isolated flashing would not exercise the verified pair.
The generated event's companion image hashes also are not the full-size
stock rescue backup hashes. This is an artifact handoff/schema issue,
not a failed phone boot; it is routed to
[omnipha/agents#118](https://github.com/omnipha/agents/issues/118).

Read-only preflight on November 4 found the intended device in fastboot,
slot a and unlocked; its product was pineapple. Host stock-backup
manifests passed. The last direct on-device rescue and carrier hashes are
from run 106, not a new measurement. The most recent run-106 pstore read
preceded the subsequent session loss; a post-return copy is not proven.
The owner accepted this mission-scoped possible loss when a non-overwriting
retrieval is unavailable, but mandatory pre-boot capture remains subject
to [omnipha/agents#112](https://github.com/omnipha/agents/issues/112).

No new phone boot, flash, erase, Android start, stock restore, host ACK or
radio action occurred. The artifact receipt is not an attempt; it remains
pending until an actual measured result and verified rescue. The altered
run-106 radio must not run. Two autonomous WLAN passes remain unmeasured.
A fresh image hash alone does not resolve either issue.
