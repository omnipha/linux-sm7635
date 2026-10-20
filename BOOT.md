# Temporary boot chain: diagnosis and next attempt

The 2026-10-19 analysis and historical test plan below preceded failed
2026-10-20 full-chain slot-A attempts. Repository work never performs device
operations. The historical procedure below is not authorization to repeat it.

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

## Stock built-in command line discriminator (#14, 2026-10-20)

Both failed full-chain sets returned to fastboot within five seconds; the
later recovery pstore does not establish whether the test kernel entered.
The #8 and #10 `boot.img` hashes were identical, so they both contained the
same kernel with the `consolidate.fragment` built-in command line, including
`panic_on_taint=0x20`, `page_owner=on`, `page_pinner=on`, `slub_debug=`,
`no_hash_pointers` and `stack_depot_disable=off`. With
`CONFIG_CMDLINE_EXTEND=y`, this could alter early-boot behavior despite the
bootloader's `stack_depot_disable=on`; an early panic remains a hypothesis,
not an observed cause or proof of bootloader acceptance.

The read-only A059P `~/phone-second-life-data/mb003/config.gz` (44,361 bytes,
SHA-256 `90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`)
measures `CONFIG_CMDLINE="console=ttynull stack_depot_disable=on
cgroup_disable=pressure kasan.page_alloc.sample=10 kasan.stacktrace=off
kvm-arm.mode=protected bootconfig ioremap_guard"` and
`CONFIG_CMDLINE_EXTEND=y`. The new `configs/asteroids-stock-cmdline.fragment`
repeats only that measured `CONFIG_CMDLINE`, merged last after the pinned
`gki_defconfig`, `pineapple_GKI.config`, unchanged `consolidate.fragment` and
`pineapple_consolidate.config`. The merge log records the override, so removing
this final fragment restores the original vendor policy. The boot and vendor
image header command lines remain the #10 diagnostic values; only the
kernel's built-in command line changes. The old `panic_on_taint` mask can no
longer be prepended by `CONFIG_CMDLINE_EXTEND`.

A single host-only run of `scripts/build-baseline.sh`, `scripts/build-bootimg.sh`,
`scripts/verify-bootimg.sh` and `scripts/compare-baseline.sh` passed. The
verifier matches the fragment, merged config, built `.config` and IKCONFIG
extracted from the unpacked kernel against the measured stock command line;
it checks the absence of `panic_on_taint` and the removed debug flags from all
three boot-chain image command lines as well. Line-by-line config comparison:
5,996 stock and 6,978 built symbol lines, 5,925 identical, 71 stock-only or
changed and 1,053 built-only or changed; `CONFIG_CMDLINE` is now identical,
not the entire 6.1.78/6.1.84 configuration. `shellcheck`, `bash -n` and
`git diff --check` passed. Host artifacts and comparison logs remain only in
`~/sm7635-build/out/`.

| host artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `.config` | 237,498 | `8c00c6f8cd89a6b044a0c7df7c481248786b09e14b12964699ed3ee6da7905d9` |
| `Image` | 39,971,328 | `cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386` |
| `Image.gz` | 15,096,553 | `0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c` |
| `boot.img` | 16,777,216 | `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` |
| `init_boot.img` | 1,679,360 | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352 | `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| `dtb.img` | 9,419,891 | `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| `initramfs.cpio.gz` | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The new `boot.img` kernel gzip payload is 15,096,553 bytes at offset 4,096.
Its hash differs from both failed sets' `boot.img`
`5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`;
its `Image.gz` differs from the earlier baseline
`159a970903ffbf2012d706099f67703ad6c5d7e31f83441deff363e80eaacc8f`.
The intentionally unchanged `init_boot.img` and `vendor_boot.img` retain the
#10 hashes (and the debug ramdisk, all 20 stock DTBs, vendor command line,
stock DTBO-65 compatibility and bootconfig). This is a distinct **chain**,
not a claim that every component differs: changing those components would
introduce a second variable. The #8 `vendor_boot.img` hash was
`bde3a3b3bc7ea587f195de63de76db5f14f8dfd197d6d3224904f722af18fd31`;
no failed three-image set is repeated. These host-only checks do not prove
physical boot or resolve the AVB/early-kernel boundary. No worker device
operation or new physical test is part of #14; the separately gated physical
coordinator alone decides whether to test a new chain.

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

## 2026-10-20 full-chain attempt and host-only diagnosis (#10)

The authorized physical team confirmed the stock slot-A backups before writing
all three #8 images; the writes returned OKAY, but the reboot returned to
fastboot within seconds without USB networking or SSH. Stock slot-A images were
restored and rechecked on-device; `dtbo_a` was not changed, and stock Android
booted fully afterward. The host-only attempt records are under
`~/phone-second-life-data/mb003/pstore/attempt-20261020-0134/`; do not publish
their contents. The preserved console has one 6.1.84 stock/recovery kernel
marker and zero 6.1.78 baseline markers. The `nt_kmsg` capture has 16 6.1.84
markers and zero 6.1.78 markers; these are not 16 distinct attempt boots.
OrangeFox recovery or subsequent stock boots can overwrite ramoops, so absence
of a 6.1.78 marker does not establish that the bootloader rejected the images.
An OrangeFox recovery header or recovery marker is not evidence of the attempted
kernel either. There is no captured attempt-specific bootloader AVB verdict,
boot reason or retry counter. The older stock property capture reports locked,
green and DTB/DTBO indices 9/65, but predates this attempt; it cannot establish
the verification state during it.

The verified stock `boot_a`, `init_boot_a` and `vendor_boot_a` images each fill
the partition and have an AVB footer and embedded vbmeta. The #8 images have
neither footer nor matching stock hash; `vbmeta_a` chains `boot`, hashes
`init_boot`, `vendor_boot` and the unchanged `dtbo`. On an unlocked device,
missing footers and hash mismatches alone do not prove the reason for the
fastboot return. Stock `boot_a` additionally contains a 16,384-byte AVB0
region between the aligned boot payload and the footer-referenced embedded
vbmeta; the #8 boot image lacks it. Do not treat the header's zero signature
size as proof that these records do not matter. No alternate AVB/vbmeta images
or partition writes are proposed here.

A read-only libfdt application of the actual stock `dtbo_a` entry 65 to the
#8 `vendor_boot.img` base DTB index 9 fails `FDT_ERR_NOTFOUND`: 32 fixup
symbols referenced at 82 sites are absent from that built DTB. The same stock
overlay applies to stock index 9. The separate generated QRD Pro overlay
applies to the built base, but that overlay was *not* in the flashed chain;
checking only its model and board ID was insufficient. This is a concrete
boot-chain incompatibility, not proof of the bootloader's exact failure point.

The host-only correction for #10 copies the SHA-256-pinned stock 20-entry DTB
blob into `vendor_boot` without modifying it. The stock overlay can then apply
to index 9, and the stock overlay supplies the ramoops reservation. The
baseline 6.1.78 kernel, debug ramdisks, vendor command line and bootconfig
remain unchanged. Only `vendor_boot.img` changes from #8. The verifier checks
all 20 DTBs byte-for-byte, applies stock DTBO 65, and checks the resulting
ramoops fields and the stock AVB hash relationship; it does *not* establish
bootloader acceptance. Images and reports stay under `~/sm7635-build/out/`.

This DTB-only candidate was tested as #10's corrected set and returned to
fastboot; it must not be repeated. The #12 assessment above supersedes this
candidate and preserves the unresolved boot boundary. Physical tests, record
capture and stock slot-A restoration remain exclusively the coordinator's
responsibility; slot B, dtbo, vbmeta and userdata remain outside scope.

## 2026-10-19 single-boot analysis

## Why the 19:00 boot produced no USB gadget

The attempt passed `boot.img`
`7cd886a24121c878a62839424b6b7f88840ba7504eb09cd0720eec96cb8ecfe5` to
`fastboot boot`. The bootloader answered `Booting OKAY` after 10.4s, no
`18d1:4ee2` gadget appeared, and the device returned to stock Android on
slot `_a` after about 35s. `Booting OKAY` only means the bootloader accepted
the image. It does not show that a kernel started.

`fastboot boot` supplies only the `boot` payload, not `init_boot` or
`vendor_boot`. For the observed stock header-v4 layout the generic ramdisk
comes from `init_boot`. The DTB blob, vendor command line and bootconfig
come from `vendor_boot`, and the board overlay comes from `dtbo`; those
partition images stayed stock. Stock-boot properties report
`ro.boot.dtb_idx=9` and `ro.boot.dtbo_idx=65`, but are not an
attempt-specific selection record.

Checked against the unpacked stock images:

| selection | source | contents |
| --- | --- | --- |
| DTB index 9 | `vendor_boot_a`, tenth of twenty concatenated DTBs | `Qualcomm Technologies, Inc. Volcano SoC`, `compatible = "qcom,volcano"`, `qcom,msm-id = <0x27c 0x10000>`, `qcom,board-id = <0 0>` |
| DTBO index 65 | `dtbo_a`, entry 65 of 76 | `Qualcomm Technologies, Inc. Volcano QRD Pro`, the live-FDT compatible list, `qcom,board-id = <0x0b 0>`, `qcom,oem-id = <2>` |

Any attempted hand-off would have used the stock DTB and stock DTBO
selection; the supplied `boot.img` carried neither a DTB nor a command line.
The later stock/recovery console starts its command line with `console=ttynull`
and ends with `rootwait ro init=/init`; its vendor part is
`video=vfb:640x400,bpp=32,memsize=3072000 nosoftlockup log_buf_len=1M
ignore_loglevel printk.devkmsg=on bootconfig`. This is consistent with the
stock vendor partition, not a captured attempted-kernel command line. It
has no `earlycon`, `keep_bootcon` or `panic=`; `chosen/stdout-path` names
the GENI debug UART, but nothing enables it in this stock cmdline.

The two stock ramdisks were unpacked and listed:

| image | ramdisk | contents |
| --- | --- | --- |
| `init_boot_a` | 2113581 bytes, lz4 legacy | the generic ramdisk: `/init` (2747936 bytes), `/system/bin`, `dev` nodes |
| `vendor_boot_a` | 8821389 bytes, lz4 legacy | `first_stage_ramdisk/fstab.qcom` and 324 files under `lib/modules/*.ko`; no `/init` |
| built `boot.img` | 1032027 bytes, gzip | `/init` (the debug shell), `/bin/busybox` |

Header v4 gets the generic ramdisk from `init_boot`; `fastboot boot` did
not replace stock `init_boot_a`. Had the 6.1.78 kernel reached init, it
would have received stock Android `/init` and 6.1.84 vendor modules rather
than the debug `/init` in the supplied `boot` ramdisk. Those stock modules
cannot be assumed compatible with the baseline kernel. The available
`Run /init as init process` and module-load messages belong to the
6.1.84 stock/recovery console described below, **not** an established
6.1.78 hand-off. The test kernel's entry and the reason the gadget never
enumerated are unresolved. Putting a ramdisk only in `boot.img` cannot
deliver it as the generic ramdisk in this header-v4 layout.

## What the pstore file does and does not show

`~/phone-second-life-data/mb003/pstore/console-ramoops-0` (834645 bytes,
sha256 `c9c49d9244c6531ffb06560ca9c26b24b30786fdd03bc2bce7e193e80b453fd2`)
was pulled from OrangeFox after the attempt. Its first line is `Linux
version 6.1.84-android14-11-gf4b0d69fdf34-ab12786779`, built
`Wed Dec 11 19:19:40 UTC 2024` with Android clang 17.0.2. The baseline
`Image` is 6.1.78 built with Ubuntu clang 17.0.6, so this file is a stock
boot's console, not the failed boot's. `pmsg-ramoops-0` (sha256
`36b2c0669098fa7b10b03e77f7c63a7b1a8cd46431bb220b8e3180dc5aa01bfb`) is the
matching pmsg record. Neither file is committed; both stay on the build
host.

It does establish the capture mechanics. The live FDT reserves ramoops at
`0x81f20000`, size `0x400000`, with `console-size = <0x200000>` and
`pmsg-size = <0x200000>`, and the stock kernel logs `ramoops: using
0x400000@0x81f20000`. The same reservation is what the built kernel needs,
and the 19:00 capture shows why timing matters: a later stock boot may
replace any attempt-specific console, if the attempt wrote one at all.

## Diagnosability of the baseline kernel

The baseline `.config` already has `CONFIG_PSTORE=y`,
`CONFIG_PSTORE_CONSOLE=y`, `CONFIG_PSTORE_PMSG=y`, `CONFIG_PSTORE_RAM=y`,
`CONFIG_SERIAL_EARLYCON=y` and `CONFIG_SERIAL_QCOM_GENI=y`. No kernel
rebuild is needed for console capture.

The reservation is the gap. `ramoops_region` in `volcano.dtsi` carries
`size = <0x0 0x200000>` and `pmsg-size = <0x200000>` but no `reg`, so no
fixed address, and no `console-size`. The stock values come from
`volcano-arca-common-overlay.dtsi`, which `volcano-qrd-pro-overlay`
includes, and that overlay is applied from `dtbo` rather than from the DTB.
The #5/#8 build tried to add
`reg = <0x0 0x81f20000 0x0 0x400000>` and `console-size = <0x200000>`
to every built DTB, but the unchanged stock `dtbo_a` could not apply to
built index 9. The #10 build instead retains the verified stock DTB blob;
`scripts/verify-bootimg.sh` checks the ramoops reservation after applying
stock overlay 65. That reservation still cannot prove that the attempted
kernel executed or that a later stock boot did not overwrite its console.

`earlycon` needs no address. The stock index-9 DTB has `chosen/stdout-path =
"/soc/qcom,qupv3_0_geni_se@ac0000/qcom,qup_uart@a94000:115200n8"` and the
driver registers `OF_EARLYCON_DECLARE(qcom_geni, "qcom,geni-debug-uart", ...)`,
so a bare `earlycon` follows the stdout path. No UART test points or
voltages were identified, so a USB-TTL adapter is not part of this setup.
`panic=-1` makes `panic()` sit and wait instead of rebooting, which keeps
the ramoops console intact until recovery reads it.

## The corrected images

`scripts/build-bootimg.sh` writes three images to `$WORK/out`. The current
chain carries the generic debug ramdisk only in `init_boot`; `vendor_boot`
still carries the same debug payload as its distinct PLATFORM vendor ramdisk.

| image | contents |
| --- | --- |
| `boot.img` | header v4, gzipped baseline `Image`, empty generic ramdisk, command line beginning `console=ttynull` and carrying the stock bootconfig tokens |
| `init_boot.img` | header v4, empty kernel, debug generic ramdisk, empty command line, matching the stock `init_boot` layout |
| `vendor_boot.img` | header v4 at the stock offsets, the debug ramdisk as its single PLATFORM vendor ramdisk, the DTB blob, vendor command line `earlycon keep_bootcon loglevel=8 log_buf_len=1M ignore_loglevel printk.devkmsg=on panic=-1 bootconfig` |

At the time of the failed attempt the first nine DTBs were copied verbatim
from stock, while index 9 and the following ten Volcano DTBs were replaced by
the pinned 6.1.78 source build. The unchanged stock `dtbo_a` entry 65 cannot
apply to that index 9; see #10 diagnosis above. The current host-only build
instead retains all twenty stock DTBs, including index 9, so the unchanged
stock overlay can supply the ramoops reservation. No `dtbo.img` is produced.

Replacing the vendor ramdisk drops `first_stage_ramdisk/fstab.qcom` and the
324 stock modules from the chain. The debug init never mounts a block
device or loads a module, so it does not need them, and dropping them is
what stops stock init from loading 6.1.84 modules into a 6.1.78 kernel.

## Full-chain caveat

The standing flash gate does **not** authorize any partition writes. This
issue does not authorize any physical execution. The three-image chain below
is superseded historical context, not a procedure to run as part of this issue.

The host `fastboot` is 34.0.5 and its `boot` command downloads a single
image, so it cannot replace `init_boot` and `vendor_boot`. The bounded test
team wrote and restored all three slot-A images; `boot` and `vendor_boot`
partitions are 96MiB each and `init_boot` is 8MiB.

The verified backups are `~/phone-second-life-data/mb003/parts/`, both
slots, recorded in `parts.sha256`. Slot `_a` and slot `_b` are byte
identical for these four partitions:

| backup | sha256 |
| --- | --- |
| `boot_a.img`, `boot_b.img` | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` |
| `init_boot_a.img`, `init_boot_b.img` | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` |
| `vendor_boot_a.img`, `vendor_boot_b.img` | `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` |
| `dtbo_a.img`, `dtbo_b.img` | `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992` |

Only slot `_a` was written during the historical attempt. Slot `_b` remained
untouched and `dtbo` was not written.

The expected USB evidence is the configfs gadget enumerating as
`18d1:4ee2`, with NCM on `usb0` at `172.16.42.2/24` and ECM on `usb1` at
`172.16.43.2/24`. The serial string is the literal `sm7635`. The debug
ramdisk now includes a key-only dropbear sshd listening at `172.16.42.2:22`;
the expected result is both the gadget and an SSH login over NCM. No SSH
observation has been made on the physical device as part of this issue.

The server allows root with the single ed25519 public key from the build
host's `~/.ssh/id_ed25519.pub` (or `$PUBKEY`) packed as
`/root/.ssh/authorized_keys`. Password and PAM authentication are compiled
out; no password or lockscreen exists in the initramfs. Its host key is
generated into RAM on first connection, so it changes on every boot. No
private key is shipped in the ramdisk or committed. The console shell
remains a fallback debug path if the gadget or SSH does not work.

The earlier test plan proposed prompt preservation of ramoops before a later
stock boot could overwrite it; the 2026-10-20 capture instead contains only
stock/recovery 6.1.84 markers. `nt_kmsg` is another host-only source of
kernel evidence, not a guaranteed record of the attempted boot. Any future
physical observation and restoration require the coordinator's separate
bounded authorization. Slot B, dtbo, vbmeta and userdata are not part of
this issue.
