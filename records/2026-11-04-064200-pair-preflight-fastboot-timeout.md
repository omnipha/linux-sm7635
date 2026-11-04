---
date: 2026-11-04
run: 109
issue: linux-sm7635#311
subsystem: wlan
result: inconclusive
---
# pair preflight fastboot timeout

Coordinator run, 2026-11-04 06:30-06:41 UTC: read-only recheck of the
pending #311 artifact during consumer-gate repair. No boot, flash, erase,
Android start, stock restore, radio action or host ACK.

Verified on host: unchanged PR #319 pair and manifest under the build lock
(init_boot_a d7bba454..., vendor_boot_b 221bfd82..., manifest c69e4b39...);
all three stock backup manifests pass.

Initial targeted fastboot gate passed (expected serial, slot a,
unlocked, product pineapple, userspace no, sizes init_boot_a 0x800000 and
vendor_boot_b 0x6000000). A later repeated gate and targeted serialno and
current-slot queries timed out while USB still enumerated 18d1:d00d and
fastboot devices listed the expected serial; cause unproven. Targeted
response must be re-proven before any write.

The typed artifact event still permits init_boot_a-only isolation and
would mismatch the last directly measured installed vendor_boot_b a71b3f5f
(the pinned new carrier header differs), so no isolation flash occurred;
agents#118 remains the typed pair repair. Post-run106 pstore remains
uncollected (agents#112). Receipt was acknowledged and the artifact stays
pending until a measured attempt. Raw private evidence remains outside Git.
