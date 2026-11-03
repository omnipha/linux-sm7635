---
date: 2026-11-03
run: 102
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: inconclusive
---
# coordinator setup window expired
## Measured setup window

The owner authorized the WLAN-scoped continuation, accepting possible loss of
uncopied run-101 and comparable later pstore where non-overwriting retrieval
is unavailable ([decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6603722440)).
The separately preserved run-101 external console was SHA-256 verified; it is
not a pstore copy. Host backup manifests and all three #306 candidate hashes
and private modes passed, and fastboot identified the expected unlocked device,
slot and product.

Run 102 repeated the installed Linux chain without a partition write. Boot
`a13b2274-b92c-454f-aa5a-20f0a563de00` reached pinned key-only root SSH,
root-only `/run/keep`, pre-armed capture and a fresh capture-proven device-op
handoff. The guard was armed with a nonce and not accepted. A staged-guest
`stat` executable was missing; the check was repeated successfully through
BusyBox, but the setup interval elapsed before installation. An initial
non-disclosing profile equality check returned an inconclusive aggregate result;
it did not isolate missing inputs/tools from unequal bytes and is not proof of
mismatched credentials. No #306 guest files were installed, no host ACK or
manual radio operation occurred, and no WLAN outcome was measured.

Before shutdown same-boot on-device hashes of `boot_a`, `vendor_boot_a`,
`dtbo_a` and `vbmeta_a` matched the verified stock backups; installed
`init_boot_a` and `vendor_boot_b` matched their documented Linux hashes. At
about uptime 316 seconds the unacknowledged boot shut down, the device returned
to responsive fastboot, fresh serial/slot/unlock/product/userspace checks
passed, and the session closed with the rescue verifier. The capture SHA-256 is
`b5946a0a97f4a663540aa1f90090637f820e59efd483ec122c3330296be79c78`.
No partition flash, erase, stock restore or Android boot occurred; Linux stays
installed. No WLAN pass is claimed. See the [coordinator result](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6604093265).

Next pre-stage exact artifacts, private backups and an independently
instrumented, non-disclosing profile comparison, then complete #306 setup
within a new captured, guarded coordinator window. Preserve the existing #294
worker; no new image merely for SHA, no host ACK, radio recipe or guard
weakening. Two autonomous fresh-boot successes remain outstanding.
