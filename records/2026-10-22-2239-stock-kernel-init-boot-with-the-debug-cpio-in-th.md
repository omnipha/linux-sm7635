---
date: 2026-10-22
issue: omnipha/linux-sm7635#42
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Stock-kernel init_boot with the debug cpio in the stock LZ4 envelope (#42, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict, not an ABL verdict, and not evidence that the debug userspace
runs. The only kernel evidenced to run remains the stock 6.1.84 kernel; this
image does not change it.

`scripts/build-init-boot-lz4-debug-ramdisk.sh` starts from the verified stock
slot-A `init_boot_a`
(`baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193`,
8,388,608 bytes) and the cpio unpacked from the verified debug gzip
`$WORK/out/initramfs.cpio.gz`
(`caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f`,
1,672,600 bytes). The unpacked cpio is 3,481,088 bytes and hashes to
`2998685ec31696017828f92934e867b47fe14df375c259d37e98b40f3dd52ee7`. The gzip
bytes themselves are not reused. The builder refuses any other source, gzip,
length or structure. It does not call `avbtool`, does not sign and does not
rebuild a kernel. Both inputs are read-only and neither is copied into Git.
The image stays under `$WORK/out`.

The only change is the generic ramdisk. The builder compresses the unpacked
cpio with LZ4 HC level 12 through host `liblz4.so.1` 1.10.0 into exactly one
Android LZ4 legacy frame: magic `02 21 4C 18`, one 4-byte little-endian
compressed size, then one LZ4 block. The same level reproduces the stock
compressed block exactly. The frame is 1,927,750 bytes, with a 1,927,742-byte
block, inside the 2,117,632 bytes before the signed tail. The header v4 page
stays byte-identical apart from the little-endian ramdisk-size field at offset
12, which changes from 2,113,581 to 1,927,750. The kernel-size field stays 0.
The frame replaces the stock LZ4 generic ramdisk at offset 4,096. The 189,882
bytes from offset 1,931,846 to the original vbmeta offset 2,121,728 are zeroes.
Every byte from 2,121,728 through the terminal `AVBf` footer is copied
unchanged: the 832-byte signed `AVB0` block and the footer (version 1.0,
original size 2,121,728, vbmeta offset 2,121,728, vbmeta size 832).

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `init_boot_a` input | 8,388,608 | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` (unchanged) |
| debug `initramfs.cpio.gz` input | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` (unchanged) |
| unpacked debug cpio | 3,481,088 | `2998685ec31696017828f92934e867b47fe14df375c259d37e98b40f3dd52ee7` |
| `init_boot-lz4-debug-ramdisk.img` | 8,388,608 | `3932504af4a962d39d4c44def68eb9bd0c9a87e79d415279b40ed2e432243527` |

Two consecutive runs produced that same SHA-256. The SHA differs from stock
`baa33fd4…`, from the measured gzip debug `init_boot` `f4a00ce3…`, from the
earlier debug `init_boot` `f4b987ee…`, and from every prior boot SHA
(`5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`,
`968625c7…`, `db2c635d…`, `13a48ff9…`, `6891dc51…`, `d966172c…`,
`5a513998…`, `dc990b95…`, `e7fd2022…`, `7c409cde…`, `197aff11…`,
`7cd886a2…`, `f1406364…`) and from both vendor_boot sets (`bde3a3b3…`,
`6078269d…`). `boot`, `vendor_boot`, `dtbo`, `vbmeta` and slot B are not
inputs and are not changed.

`scripts/verify-init-boot-lz4-debug-ramdisk.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless the stock prefix matches
apart from the ramdisk-size field, the kernel is empty, the payload is one
Android LZ4 legacy frame at offset 4,096 whose single HC level-12 block
decompresses to the cpio inside `caa3eb82…`, the gap is zero, the signed tail
is byte-identical, the size is 8,388,608 and the SHA is the expected value and
none of the prior images. Negative fixtures reject a changed tail byte, a
second changed header field, a gzip payload, a modern LZ4 frame, more than one
LZ4 block, a block that decompresses to a different cpio, a short image, a
moved tail offset and every repeated prior SHA, including `baa33fd4…`,
`f4a00ce3…` and `f4b987ee…`.

**What a later measurement would distinguish (contract, not a test request).**
Only the physical coordinator may flash this one image, and only to
`init_boot_a`. Stock `boot_a` and stock `vendor_boot_a` stay unwritten.
`f4a00ce3…` and every earlier measured SHA stay unrestored as a test image.
Before any Android boot, capture pstore from the recovery session this boot
enters, or from Android if Android boots. Roll back to verified stock either
way.

- **Own init reached:** pstore or the running system shows the debug
  `usb-init` marker, or key-only SSH answers on the debug address. That would
  be the first own userspace on the stock kernel.
- **Android boots with no debug marker:** the stock kernel ignored or did not
  execute this ramdisk. The next question is ramdisk selection, not the
  compression.
- **Recovery again, or fastboot fallback:** matching the gzip result means
  compression was not the cause. A new fastboot fallback means this envelope
  loses the known-good boot. Roll back; do not combine it with a custom kernel.

None of those outcomes is claimed here, and none of them is an AVB verdict or
an ABL verdict. This does not close #12 and does not touch userdata.
