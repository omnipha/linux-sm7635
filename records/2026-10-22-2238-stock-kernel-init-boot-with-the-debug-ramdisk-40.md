---
date: 2026-10-22
issue: omnipha/linux-sm7635#40
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Stock-kernel init_boot with the debug ramdisk (#40, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict, not an ABL verdict, and not evidence that the debug userspace
runs. The only kernel evidenced to run remains the stock 6.1.84 kernel; this
image does not change it.

`scripts/build-init-boot-debug-ramdisk.sh` starts from the verified stock
slot-A `init_boot_a`
(`baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193`,
8,388,608 bytes) and the existing verified debug ramdisk
`$WORK/out/initramfs.cpio.gz`
(`caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f`,
1,672,600 bytes). It refuses any other source, ramdisk, length or structure.
It does not call `avbtool`, does not sign and does not rebuild a kernel. Both
inputs are read-only and neither is copied into Git. The image stays under
`$WORK/out`.

The only change is the generic ramdisk. The header v4 page stays
byte-identical apart from the little-endian ramdisk-size field at offset 12,
which changes from 2,113,581 to 1,672,600. The kernel-size field stays 0.
The debug gzip bytes replace the stock LZ4 generic ramdisk at offset 4,096.
Because the debug ramdisk is shorter, the 445,032 bytes from offset 1,676,696
to the original vbmeta offset 2,121,728 are zeroes instead of the tail of the
stock ramdisk. Every byte from 2,121,728 through the terminal `AVBf` footer is
copied unchanged: the 832-byte signed `AVB0` block and the footer (version
1.0, original size 2,121,728, vbmeta offset 2,121,728, vbmeta size 832).

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `init_boot_a` input | 8,388,608 | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` (unchanged) |
| debug `initramfs.cpio.gz` input | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` (unchanged) |
| `init_boot-debug-ramdisk.img` | 8,388,608 | `f4a00ce3a1926f9b54eaa958158691efaabe90a9ea715d2bac3d424095f2f948` |

Two consecutive runs produced that same SHA-256, and a second invocation of
the builder produced it again. The SHA differs from stock `baa33fd4…`, from
the earlier debug `init_boot` `f4b987ee…`, and from every prior boot SHA
(`5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`,
`968625c7…`, `db2c635d…`, `13a48ff9…`, `6891dc51…`, `d966172c…`,
`5a513998…`, `dc990b95…`, `e7fd2022…`, `7c409cde…`, `197aff11…`) and from
both vendor_boot sets (`bde3a3b3…`, `6078269d…`). `boot`, `vendor_boot`,
`dtbo`, `vbmeta` and slot B are not inputs and are not changed.

`scripts/verify-init-boot-debug-ramdisk.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless the stock prefix matches
apart from the ramdisk-size field, the ramdisk bytes are the verified gzip
newc cpio, the kernel is empty, the gap is zero, the signed tail is
byte-identical, the size is 8,388,608 and the SHA is the expected value and
none of the prior images. Negative fixtures reject a changed tail byte (first
vbmeta byte, a byte inside the block, the last block byte, a later tail byte
and both footer ends), a second changed header field (os version, header
version, header size, command line, header padding and magic), a non-gzip
ramdisk, a plain cpio, a gzip that is not newc, a short image and every
repeated prior SHA, including `baa33fd4…` and `f4b987ee…`.

**What a later measurement would distinguish (contract, not a test request).**
Only the physical coordinator may flash this one image, and only to
`init_boot_a`. Stock `boot_a` and stock `vendor_boot_a` stay unwritten, and
`7c409cde…`, `e7fd2022…`, `db2c635d…`, `6891dc51…` and the earlier
custom-kernel sets must not be flashed again.

- **Own init reached:** pstore or the running system shows the debug
  `usb-init` marker, or key-only SSH answers on the debug address. That would
  be the first own userspace on the kernel already shown to boot.
- **Android still boots with no debug marker:** the stock kernel ignored or
  did not execute this ramdisk. The layout is then the next question, not
  another kernel.
- **Fastboot fallback:** this ramdisk or its size change is enough to lose the
  known-good boot. Roll back; do not combine it with a custom kernel.

None of those outcomes is claimed here, and none of them is an AVB verdict or
an ABL verdict. This does not close #12 and does not touch userdata.
