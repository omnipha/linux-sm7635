---
date: 2026-10-20
issue: omnipha/linux-sm7635#12
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Corrected-chain return to fastboot (#12, 2026-10-20)

**Observed:** The physical coordinator's 06:40 attempt used the #10 chain:
`boot` SHA-256 `5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`,
`init_boot` `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89`,
`vendor_boot` `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d`.
All three slot-A writes returned OKAY; the phone returned to fastboot within
five seconds and stayed there through 45 observations over roughly four
minutes, without gadget, adb or SSH. The unchanged stock `dtbo_a` and all
three restored stock slot-A images matched the verified on-device backup
hashes; stock Android subsequently completed boot on slot A. Host-only
records at `~/phone-second-life-data/mb003/pstore/attempt-20261020-0640/`
include a 1,197,548-byte recovery console (SHA-256
`56d976062bd7e1f6853f0ee2ab389f194964eab5dec224f2e5600abc0049b81e`)
with one stock/recovery 6.1.84 boot banner, zero 6.1.78 baseline banners and
zero dropbear markers. It was collected *after* fallback, verified stock
rollback and an explicit recovery boot, but before Android, so it does not
establish whether the attempted kernel entered.
Only `vendor_boot` differed between the failed #8 and #10 chains: the stock
DTB/DTBO incompatibility fixed in #10 was not the **sole** cause of the same
observed return to fastboot.

**Host-only comparison:** `scripts/verify-bootimg.sh` passed against SHA-pinned
slot-A stock `boot`, `init_boot`, `vendor_boot`, `dtbo` and `vbmeta` references
and the exact failed #10 images. Stock `vbmeta_a` has flags zero and rollback
index zero; it chains `boot` at rollback location 3 and has matching salted
hash descriptors for stock `init_boot`, `vendor_boot` and `dtbo`. Each stock
boot-family image fills its partition and has a footer-referenced embedded
vbmeta with a matching hash of its stock prefix. Stock `boot` also has a
**separate** 16 KiB AVB0 record between its kernel and footer-referenced
vbmeta; it hashes the shorter kernel-only prefix. The regression check now
checks that record's descriptor and hash separately, verifies the zero
verification flags of the stock records, and confirms the test `boot` has
no corresponding separate record. It does not verify signatures or
establish which records the bootloader enforced on the failed attempt. The
stock `vbmeta_a` hash for `dtbo` still matches: no `dtbo` or `vbmeta` change is
proposed.

| relationship | verified stock slot A | failed #10 chain |
| --- | --- | --- |
| boot image | 96 MiB; header v4, kernel at 4096; separate AVB0 at 13,955,072, embedded vbmeta at 13,971,456 | 16 MiB; v4, gzipped 6.1.78 kernel at 4096 and debug ramdisk at 15,101,952; no stock AVB0 record or footer; stock boot hash does not match |
| init_boot | 8 MiB; v4, generic Android LZ4 ramdisk at 4096, embedded vbmeta at 2,121,728 | 1,679,360 bytes; v4, empty kernel, debug gzip generic ramdisk at 4096; shorter than stock hashed prefix, no footer |
| vendor_boot | 96 MiB; v4, one PLATFORM LZ4 ramdisk, DTB at 8,826,880, table at 18,247,680, bootconfig at 18,251,776; embedded vbmeta at 18,255,872 | 11,108,352 bytes; v4, one PLATFORM gzip debug ramdisk, DTB at 1,679,360, table at 11,100,160, bootconfig at 11,104,256; shorter than stock hashed prefix, no footer |
| selection and parameters | stock property capture reports DTB index 9, DTBO entry 65; vendor page 4096, kernel/ramdisk/tags/DTB addresses `0x8000`/`0x1000000`/`0x100`/`0x1f00000` | same geometry; all 20 stock DTBs byte-identical, stock entry 65 applies to index 9 and supplies ramoops; bootconfig matches stock's 175 bytes |

The boot cmdline and vendor cmdline differ from stock (diagnostic earlycon,
`panic=-1`); stock `boot` has no generic ramdisk, while the test places the
debug ramdisk in `init_boot` as required by header v4. The stock 6.1.84
kernel/vendor modules and Android generic ramdisk cannot be assumed compatible
with the 6.1.78 baseline; the test instead replaces both ramdisks with the
same debug payload and never loads the stock vendor modules. Gzip versus LZ4,
smaller image geometry and AVB mismatches are candidate explanations, **not**
a bootloader verdict. A pre-attempt unlocked/orange report supersedes the
older locked/green stock property capture, but does not show what policy was
enforced at hand-off. The preserved pre/post `getvar` records identify slot A
and unlocked state; no attempt-specific AVB accept/reject status, boot reason,
A/B retry counter or supported read-only source for them is established by the
host records. Stock-kernel boot counters in pstore cannot be attributed to
this attempted hand-off. The OrangeFox pmsg boot-recovery reason follows an
explicit recovery request after stock rollback, and its slot-suffix use does
not identify which image the bootloader loaded during the failed attempt.
A successful fastboot write or reboot is not proof of bootloader image
acceptance.

**Single selected diagnostic:** the host-only AVB relationship audit in
`scripts/verify-bootimg.sh`, including the separate stock boot AVB0 record.
It confirms structural divergences, not the boundary at which the device
failed; no supported single-variable image correction follows. No new images
were built or designated for flashing. Do **not** repeat the #8 or #10 SHA
sets or try a multi-variable revision. The current host evidence cannot
distinguish rejection before kernel hand-off from a very early kernel failure
or a later init/USB failure.

**Conditional measurement/rollback handoff (physical coordinator only):**
There is no new test request or flash approval in this diagnosis. If distinct
images are ever independently justified and the existing bounded slot-A gate
is re-evaluated, the coordinator owns the complete test and verified stock
rollback. Before any such test, the coordinator must establish a supported
read-only evidence channel or explicitly accept that the boundary may remain
unknown; a new image SHA alone cannot discriminate it. An attempt-tagged
record should associate image SHAs and a timed first return to fastboot with
any *supported, bounded, read-only* bootloader
AVB decision, slot/retry and boot-reason observations **before** recovery,
stock boot or rollback can erase evidence; do not use a broad or hung probe.
If such a signal is unavailable, record it as unavailable rather than infer
a verdict. An explicit rejection supports failure before hand-off. An
explicit acceptance **without** a test-kernel marker remains inconclusive:
very early failure or lost/overwritten ramoops is still possible. A surviving
6.1.78 kernel marker establishes hand-off; last kernel progress before
`usb-init: starting` supports an early/pre-init failure, while `usb-init`
markers without gadget or SSH support a later init/USB failure. Preserve only
parsed marker counts, timing and structural facts in public reports, not raw
dumps. The coordinator alone decides whether and how to obtain a timely
record and restore/verify the three stock slot-A partitions. No operation on
slot B, `dtbo`, `vbmeta` or `userdata` is in scope. Without a supported
attempt-specific read-only signal or new evidence-backed artifact, stop.
