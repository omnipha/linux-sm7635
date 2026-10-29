---
date: 2026-10-20
issue: omnipha/linux-sm7635#16
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Single generic ramdisk in init_boot (#16, 2026-10-20)

**Observed:** The #14 three-image set, with `boot.img` SHA-256
`84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a`,
returned to fastboot within five seconds after the physical coordinator's
bounded slot-A attempt. Stock rollback was verified; recovery pstore contains
only stock/recovery 6.1.84 banners and no attempted-kernel 6.1.78 marker.
Recovery can overwrite pstore. Neither bootloader rejection nor kernel entry
has been measured; USB gadget enumeration and key-only SSH are unproven.

The read-only A059P `parts-a.sha256` and `config.gz` references under
`~/phone-second-life-data/mb003/` were hash-checked before parsing. The stock
boot header v4 has an **empty** generic ramdisk; stock init_boot has a nonzero
one. The failed #14 build duplicated the same 1,672,600-byte gzip cpio in
both images. The local `/usr/bin/mkbootimg` header-v4 implementation writes
`ramdisk_size=0` and no payload when `--ramdisk` is omitted. The first
`mkbootimg` call in `scripts/build-bootimg.sh` now omits that flag; the
`init_boot` call retains it and `vendor_boot` retains the same PLATFORM vendor
ramdisk, DTBs and bootconfig. This is an additive, revertible boot packaging
change: `build-baseline.sh` still merges vendor `consolidate.fragment` and
`pineapple_consolidate.config`, then the measured stock cmdline fragment last.
No kernel source/config, dtbo, vbmeta, or release-image builder was changed.

| header-v4 image | stock A (bytes / generic ramdisk / SHA-256) | failed #14 (bytes / generic ramdisk / SHA-256) | new host build (bytes / generic ramdisk / SHA-256) |
| --- | --- | --- | --- |
| boot | 100,663,296 / 0 / `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` | 16,777,216 / 1,672,600 / `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` | 15,101,952 / 0 / `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` |
| init_boot | 8,388,608 / 2,113,581 / `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` | 1,679,360 / 1,672,600 / `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360 / 1,672,600 / `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| vendor_boot (PLATFORM ramdisk) | 100,663,296 / 8,821,389 / `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` | 11,108,352 / 1,672,600 / `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352 / 1,672,600 / `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |

Boot and init_boot headers are 1,584 bytes in 4,096-byte pages; both boot
kernels start at offset 4,096. Stock boot kernel is 13,949,926 bytes; #14/new
kernel is the unchanged 15,096,553-byte `Image.gz` with SHA-256
`0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c`.
In #14, boot's ramdisk started at 15,101,952; in the new boot that offset is
the end of the image. Init_boot has an empty kernel and retains the exact
1,672,600-byte gzip newc at offset 4,096 (SHA-256
`caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f`).
The vendor DTB still begins at 1,679,360, retains all 20 stock DTBs (index 9
matches stock DTBO entry 65), and both builds retain the 175-byte stock
bootconfig. Stock vendor DTB begins at 8,826,880. The new boot hash also
differs from the earlier failed #10 hash
`5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`.

The verifier reconstructs the *entire* failed #14 boot byte-for-byte by
restoring only boot's ramdisk size field and aligned generic-ramdisk payload;
its SHA-256 matches `84f7f5ea…` exactly. It pins the input `.config`, `Image`,
`Image.gz`, gzip cpio, DTB and both other image hashes to the #14 measurements,
and checks commandlines, embedded IKCONFIG, stock AVB hash relationships,
header geometry, DTBO-65 application and key-only SSH ramdisk content. Small
synthetic fixtures verify that duplicating a gzip newc cpio into boot is
rejected, as are advertised or unadvertised boot ramdisk payloads, a nonempty
init_boot kernel and a changed init_boot cpio. Expected negative output is
`expected verified #14 duplicated ramdisk failure: boot generic ramdisk must be empty`
for the reconstructed #14 image and
`expected duplicated small gzip cpio failure: boot generic ramdisk must be empty`
for the synthetic image. Checking the original failed #14 artifact alone
returns `FAIL: boot generic ramdisk must be empty`; no negative fixture is
silently accepted. Two
sequential host packaging runs yielded the same three image hashes; full
verification, `bash -n`, `shellcheck` and `git diff --check` passed. Artifacts
and reports remain only under `~/sm7635-build/out/`.

**Hypothesis, not observation:** Removing the non-stock boot ramdisk may avoid
an early loader misinterpretation. Structural equivalence establishes only
that the new chain isolates this one variable; it cannot locate the failure
boundary or prove a physical fix. Stock vbmeta's hashes still do not
validate the unsigned test images. No device operation is part of this work.
Any future attempt-specific hand-off measurement and bounded slot-A gate
review belong solely to the physical coordinator; no blind retest is requested.
