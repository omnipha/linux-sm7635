---
date: 2026-10-20
issue: omnipha/linux-sm7635#10
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
