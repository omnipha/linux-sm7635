# Temporary boot chain: diagnosis and next attempt

The 2026-10-19 analysis and historical test plan below preceded failed
2026-10-20 and 2026-10-21 full-chain slot-A attempts. Repository work never
performs device operations. The historical procedure below is not authorization
to repeat it.

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

## Stock AVBf footer erasure on the #36 control (#38, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-avbf-footer-erase.sh` starts from the verified #36 image
`boot-avb0-window-erase.img`
(`e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f`,
100,663,296 bytes). It refuses any other source SHA, length or structural
window. After that check it copies the source and zeroes exactly bytes
`[100663232, 100663296)`. It does not call `avbtool`, does not sign, does not
generate another footer and does not alter `vbmeta_a`, the kernel, the signed
vbmeta block or any other byte. The read-only stock `boot_a` reference
(`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`) is used
only to prove the source split and the stock footer fields. Neither image is
copied into Git. The result stays under `$WORK/out`.

The source split, checked before any output is written, is the #23
stock-kernel prefix (`13a48ff9…`, first 13,955,072 bytes), an all-zero
standalone AVB0 window at `[13955072, 13971456)`, and every byte from
13,971,456 onward equal to stock `197aff11…`. That stock tail ends with a
64-byte `AVBf` footer: version 1.0, original size 13,971,456, vbmeta offset
13,971,456, vbmeta size 2,496. The 2,496-byte signed `AVB0` block at that
offset is unchanged. The only change from the already measured Android-booting
`e7fd2022…` image is those terminal 64 bytes, replaced by zeroes.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #36 `boot-avb0-window-erase.img` source | 100,663,296 | `e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f` (unchanged input) |
| stock `boot_a` reference (read-only check) | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-avbf-footer-erase.img` | 100,663,296 | `7c409cdefe9e0f24cbe53e44d5bbab8ff50adadb9fbfb26d64917fe1a6fc4ddf` |

Two consecutive runs produced that same SHA-256. Bytes before offset
100,663,232 are byte-identical to `e7fd2022…`. The final 64 bytes are zero.
The SHA differs from `e7fd2022…`, `db2c635d…`, `6891dc51…`, `13a48ff9…`,
`968625c7…`, `d966172c…`, `5a513998…`, `dc990b95…` and stock `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs and are
not combined with this image.

`scripts/verify-avbf-footer-erase.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless the source SHA and length, prefix, zero AVB0 window,
signed-block identity, stock footer fields, byte equality before offset
100,663,232, the 64 zero footer bytes, the fixed size and the expected SHA all
hold, and the SHA is none of the prior images. Negative fixtures reject a
wrong source SHA or length, a changed prefix, a changed erased AVB0 window, a
changed signed vbmeta block, a one-byte change outside the 64-byte footer, a
nonzero output-footer byte, an incorrect SHA and a repeated prior SHA
(`e7fd2022…`, `db2c635d…`, `6891dc51…`, `13a48ff9…`, `968625c7…`,
`d966172c…`, `5a513998…`, `dc990b95…`, `197aff11…`).

**What a later measurement would distinguish (contract, not a test request).**
A fast return to fastboot, matching `db2c635d…`, would mean the terminal
`AVBf` bytes were necessary for the Android-booting control. A normal Android
boot, matching `e7fd2022…`, would mean those footer bytes are not individually
necessary and the signed vbmeta block or remaining layout is the next
question. A third mode is recorded as such. Neither outcome is an AVB verdict,
an ABL verdict, USB or SSH success, or a result of this host control. Only the
physical coordinator may decide whether to test this one new image alone.
`e7fd2022…` must not be flashed again.

## Stock-kernel standalone AVB0 window erasure (#36, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-avb0-window-erase.sh` starts from the verified #23 control
`boot-stock-kernel.img`
(`13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450`,
13,955,072 bytes), appends exactly 16,384 zero bytes, and then appends the
bytes of the read-only host stock `boot_a` reference
(`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`) from
offset 13,971,456 through the end. It refuses any other source, stock
reference, window or length. It does not call `avbtool`, does not add a
footer and does not sign or alter the signed tail. The stock image is only a
byte source and is never copied into Git. The image stays under `$WORK/out`.

In stock `boot_a`, bytes `[13955072, 13971456)` are the standalone 16,384-byte
`AVB0` record (3,479 nonzero bytes). The signed vbmeta block starts at
13,971,456 and the `AVBf` footer ends the image. The only change from the
already measured stock-tail overlay `968625c7…` is that window, replaced by
zeroes. That overlay is reconstructed in memory by the verifier self-test only
and is never written or packaged.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #23 `boot-stock-kernel.img` input | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` (unchanged prefix) |
| stock `boot_a` reference (tail source) | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-avb0-window-erase.img` | 100,663,296 | `e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f` |

Two consecutive runs produced that same SHA-256. The first 13,955,072 bytes
are byte-identical to `13a48ff9…`. Bytes `[13955072, 13971456)` are all zero.
The 86,691,840 bytes from offset 13,971,456 onward are byte-identical to stock
`197aff11…`. The SHA differs from `968625c7…`, `db2c635d…`, `13a48ff9…`,
`6891dc51…`, `d966172c…`, `5a513998…`, `dc990b95…` and `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs and are
not combined with this image.

`scripts/verify-avb0-window-erase.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless the length, SHA-256, prefix identity, zero window and
signed-tail identity all hold and the SHA is none of the prior images.
Negative fixtures reject a changed prefix byte, one nonzero byte in the erased
window (first and last), a changed signed-tail byte (first and last), a window
of any other size (zero, 12,288, 8,192, 20,480 bytes, and a short image) and a
repeated prior SHA (`968625c7…`, `db2c635d…`, `13a48ff9…`, `6891dc51…`,
`d966172c…`, `5a513998…`, `dc990b95…`, `197aff11…`).

**What a later measurement would distinguish (contract, not a test request).**
A fast return to fastboot, matching `db2c635d…`, would mean erasing the
standalone `AVB0` record is sufficient. A normal Android boot, matching
`13a48ff9…` and its stock-tail overlay, would mean that record is not
sufficient and the remaining full-size variable is the signed vbmeta block or
footer. Absence of a new pstore record stays inconclusive. Only the physical
coordinator may decide whether to test this one image alone.

## Stock-kernel full-size blank-tail control (#34, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-blank-tail-control.sh` starts from the verified #23 control
`boot-stock-kernel.img`
(`13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450`,
13,955,072 bytes) and refuses any other source or length. It copies that
image and appends exactly 86,708,224 zero bytes. It does not call `avbtool`,
does not add a hash footer and does not sign anything. The #32 image
`boot-stock-full-footer.img`
(`6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555`) is a
comparison input only and is not packaged again.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #23 `boot-stock-kernel.img` input | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` (unchanged prefix) |
| `boot-blank-tail.img` | 100,663,296 | `db2c635d5c51aed47cf6a626244bba5be6e6eeb240f0dd2d0ed0e72d85fdff00` |

Two consecutive runs produced that same SHA-256. The first 13,955,072 bytes
are byte-identical to `13a48ff9…`. Every one of the following 86,708,224 bytes
is zero. There is no `AVB0` block and no `AVBf` footer. The image differs from
`6891dc51…` only in that tail: the unsigned metadata is replaced by zeroes.
The SHA differs from `5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`,
`55fa78ca…`, `13a48ff9…`, `d966172c…`, `5a513998…`, `dc990b95…`, `6891dc51…`
and stock `197aff11…`. `init_boot` `f4b987ee…` and `vendor_boot` `6078269d…`
are not inputs and are not combined with this image. The image stays under
`$WORK/out` and is not committed.

`scripts/verify-blank-tail-control.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless the length, SHA-256, prefix identity and zero tail all
hold, and unless the image differs from `6891dc51…` only in that tail.
Negative fixtures reject a changed prefix byte, one nonzero tail byte, a short
image and a repeated prior SHA (`6891dc51…`, `13a48ff9…`, `d966172c…`,
`5a513998…`, `dc990b95…`, `197aff11…`).

## Stock-kernel unsigned full-size footer control (#32, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-stock-full-footer.sh` starts from the verified #23 control
`boot-stock-kernel.img`
(`13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450`,
13,955,072 bytes) and refuses any other source. It copies that image and
applies exactly the existing unsigned footer invocation from
`scripts/build-full-boot-footer.sh`, using the pinned `avbtool` 1.4.0
(SHA-256 `1aa6f2b462aa67aa3fdf488bee83ab517de8ad9d8228c7b45c35267ab2cf6781`):

```sh
python3 "$AVBTOOL" add_hash_footer \
	--image "$candidate" \
	--partition_name boot \
	--partition_size 100663296 \
	--hash_algorithm sha256 \
	--algorithm NONE \
	--salt d41d8cd98f00b204e9800998ecf8427e
```

No signing key is created or stored. The builder refuses another source,
algorithm, salt, partition size or footer placement through
`scripts/verify-stock-full-footer.py` before publishing the candidate. The
image stays under `$WORK/out` and is not committed.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #23 `boot-stock-kernel.img` input | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` (unchanged prefix) |
| `boot-stock-full-footer.img` | 100,663,296 | `6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555` |

Two consecutive runs produced that same SHA-256. The first 13,955,072 bytes
are byte-identical to `13a48ff9…`. The footer references a 448-byte `AVB0`
block at offset 13,955,072. `avbtool info_image` reports algorithm `NONE`,
hash algorithm `sha256`, partition name `boot`, salt
`d41d8cd98f00b204e9800998ecf8427e`, image size 100,663,296, original image
size 13,955,072 and an empty authentication block. The SHA differs from
`5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`,
`13a48ff9…`, `d966172c…`, `5a513998…`, `dc990b95…` and stock `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs and are
not combined with this image.

Against the failed #25 image `d966172c…`, the only structural differences are
the stock kernel payload in place of the debug kernel payload and the hash
descriptor that covers it. The boot header page matches apart from the
little-endian kernel-size field (13,949,926 versus 15,746,607). The 448-byte
`AVB0` block matches after substituting the covered size and digest, and the
final footer matches after substituting the original size and vbmeta offset.
Both use algorithm `NONE` and the same salt.

`scripts/verify-stock-full-footer.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless all of those conditions hold. Negative fixtures reject a
changed prefix byte, algorithm type 1 instead of `NONE`, a different salt, a
footer that points away from offset 13,955,072, a truncated image, a stale
descriptor digest and a repeated prior SHA.

## Stock-kernel image_size header control (#30, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict, not an ABL verdict, and not evidence that the declared reservation
is the physical cause. No test-kernel marker is expected from this stock
payload.

The rejected #29 envelope mixed two variables and is not repeated. Matching
both the debug `image_size` (55,508,992) and the debug decompressed length
(41,859,584) produced a best gzip payload of 13,957,009 bytes, 2,987 past the
stock bound, and packaged nothing. This control changes only the declared
reservation.

`scripts/build-image-size-control.sh` decompresses the gzip payload of the
SHA-pinned stock slot-A `boot_a` reference
(`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`,
100,663,296 bytes) and checks its arm64 header: `text_offset = 0`, flags
`0xa`, three zero reserved words, `ARMd` magic and PE offset `0x40`. It reads
the verified debug `Image.gz`
(`b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277`) only to
confirm its `image_size`, then changes the little-endian field at decompressed
byte 16 from 35,913,728 (`0x2240000`) to 55,508,992 (`0x34f0000`). The
decompressed length stays 35,224,064. No byte is appended, and `code0`,
`code1`, flags, `text_offset` and every other stock kernel byte stay unchanged.

The builder recompresses with deterministic zlib deflate level 9 inside the
stock gzip framing: no filename, zero mtime, OS byte 3 and `XFL` byte 2. The
payload is exactly 13,949,926 bytes, the existing stock kernel-size field, so
the header page is not rewritten. Any other length fails closed. The payload
replaces the stock gzip bytes in a copy of the 100,663,296-byte slot-A image.
The byte immediately after the payload stays the stock zero, and the rest of
the zero-padding window, the separate AVB0 record at 13,955,072, the signed
vbmeta block and the footer are copied unchanged. Nothing is re-signed and no
AVB metadata is added or removed. The image stays under `$WORK/out` and is not
committed.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `boot_a` input | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-image-size.img` | 100,663,296 | `dc990b9517d53431fcaeebb2b0498e6e64d3e7cbbc7e469d3e0bfc73abe00075` |

Two consecutive runs produced that same SHA-256. The decompressed images
differ at bytes 16 through 23 only. The SHA differs from `5e866c54…`,
`84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`, `13a48ff9…`,
`d966172c…`, `5a513998…` and stock `197aff11…`. `init_boot` `f4b987ee…` and
`vendor_boot` `6078269d…` are not inputs and are not combined with this image.

`scripts/verify-image-size-control.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless that eight-byte field is the
only kernel difference, the decompressed length is 35,224,064, the gzip
framing and 13,949,926-byte size match, the boot header page is unchanged, the
AVB record and footer bytes are unchanged, and the salted SHA-256 of the first
13,971,456 bytes differs from the stock descriptor digest. Negative fixtures
reject a second changed kernel byte, an appended zero tail, a payload longer
than 13,949,926 bytes and a decompressed length other than 35,224,064.

## One-byte stock hash-boundary control (#27, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict.

`scripts/build-hash-boundary-control.sh` copies the SHA-pinned stock slot-A
`boot_a` reference (`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`,
100,663,296 bytes) and changes only byte offset 13,954,122 from `0x00` to
`0x01`. That offset is inside the zero padding `[13954022, 13955072)`, after
the gzip payload at `[4096, 13954022)` and before the separate AVB0 record at
13,955,072. It is inside the 13,971,456-byte prefix covered by the chained
hash descriptor. The builder refuses any other source image, a non-zero source
byte at that offset, and any output whose length is not 100,663,296. The image
stays under `$WORK/out` and is not committed.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `boot_a` input | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-hash-boundary.img` | 100,663,296 | `5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b` |

Two consecutive runs produced that same SHA-256. A byte compare against the
stock reference found exactly one difference: offset 13,954,122, `0x00` to
`0x01`. The SHA differs from `5e866c54…`, `84f7f5ea…`, `116b1662…`,
`1fdc2570…`, `55fa78ca…`, `13a48ff9…`, `d966172c…` and stock `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs.

`scripts/verify-hash-boundary-control.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless every byte except that offset
matches stock; the offset is inside the padding window and outside the gzip
payload; the gzip payload, header page, separate AVB0 record, signed vbmeta
block and final footer are byte-identical to stock; `avbtool info_image`
reports the same `SHA256_RSA4096` algorithm, public-key SHA-1
`407b99d1f65947192fb4591e5732bc1b1da9d95a`, image size 100,663,296, original
image size 13,971,456 and descriptor set; and the salted SHA-256 of the first
13,971,456 bytes differs from the stock hash descriptor digest. The negative
fixture changes the last gzip payload byte, outside the padding window, and is
rejected. Further fixtures cover a second padding byte, a different padding
offset, a non-zero source byte, a short image and a repeated prior SHA.

## Stale boot_a AVB footer model (#25, host-only, 2026-10-22)

**This is a model of libavb, not an observed ABL verdict.** Nothing here was
flashed or booted, and the model does not say what ABL does with an unlocked
device. `scripts/verify-post-flash-avb.py`, called by
`scripts/verify-bootimg.sh`, models a fastboot flash as an overlay: the
candidate image replaces the start of the SHA-pinned stock partition image and
the tail is left untouched. It then classifies the result with the same parser
as the stock checks: footer magic and bounds, a well-formed AVB0 record at the
footer-referenced offset, and the separate boot AVB0 record. Negative fixtures
cover a footer pointing into payload bytes, a truncated footer and an intact
footer. Where an earlier image is no longer retained on the host, the
classification is derived from the recorded size and kernel/ramdisk lengths and
is marked as such; the verifier refuses that path if the recorded size could
reach the stock metadata.

Stock `boot_a` is 100,663,296 bytes. Its footer (`AVBf`, last 64 bytes) points
at a vbmeta block at offset 13,971,456 (2,496 bytes). A separate AVB0 record
starts at 13,955,072 and hashes the shorter kernel-only prefix. Every earlier
debug `boot.img` ends at or before 16,777,216 bytes, so the stock footer
survives the overlay but the bytes it references, and the separate AVB0 record,
are now inside the debug payload.

| image | bytes | SHA-256 | footer | vbmeta at footer offset | separate boot AVB0 | predicted post-flash state | evidence |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| boot #8/#10 `5e866c54…` | 16,777,216 | `5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | layout-derived; image bytes not retained |
| boot #14 `84f7f5ea…` | 16,777,216 | `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | byte-verified overlay |
| boot #16 `1fdc2570…` | 15,101,952 | `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | byte-verified overlay |
| boot #18 `116b1662…` | 15,753,216 | `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | layout-derived; image bytes not retained |
| boot #21 `55fa78ca…` | 15,753,216 | `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | byte-verified overlay |
| boot #23 control `13a48ff9…` | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` | valid (stock) | valid | valid | **intact metadata** | byte-verified overlay |
| boot stock `197aff11…` | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` | valid | valid | valid | **intact metadata** | byte-verified overlay |
| init_boot #21 `f4b987ee…` | 1,679,360 | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | valid (stock) | valid (offset 2,121,728) | n/a | **intact metadata** | byte-verified overlay |
| vendor_boot #21 `6078269d…` | 11,108,352 | `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | valid (stock) | valid (offset 18,255,872) | n/a | **intact metadata** | byte-verified overlay |
| boot #25 candidate `d966172c…` | 100,663,296 | `d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131` | valid (new, unsigned) | valid | n/a (replaced) | **intact unsigned footer** | byte-verified overlay |

The model predicts **invalid chained metadata** for `5e866c54…`, `84f7f5ea…`,
`1fdc2570…`, `116b1662…` and `55fa78ca…`. It predicts **intact metadata** for
the #23 control `13a48ff9…`, stock `197aff11…`, and the #21 `init_boot` and
`vendor_boot` overlays. Those two leave their stock footers and vbmeta blocks
untouched; only the stock hash comparison fails, which this model does not
treat as invalid metadata. `55fa78ca…` is recorded as tested and failed in the
`boot_a`-alone configuration (`attempt-20261022-0620-boota-marker`), the same
fastboot fallback as `116b1662…`, not as untested.

The #14 row is byte-verified because the #16 image plus the verified gzip cpio
recreates `84f7f5ea…` exactly, which the #16 verifier already proved. The #8
and #18 rows use the sizes and kernel/ramdisk lengths recorded in this file
(16,777,216 with a 15,097,006-byte kernel and 1,672,600-byte ramdisk; 15,753,216
with a 15,746,316-byte kernel and an empty ramdisk). Both recorded payloads
extend past the stock vbmeta at 13,971,456, so the stale footer points into
payload bytes. The verifier rejects a recorded layout that does not reach that
metadata, so an earlier image cannot silently pass.

**Single change from the verified #21 boot.** `scripts/build-full-boot-footer.sh`
copies `boot.img` `55fa78ca…` and appends one unsigned AVB hash footer with the
pinned `avbtool` 1.4.0 (`add_hash_footer --partition_name boot
--partition_size 100663296 --algorithm NONE`, fixed salt
`d41d8cd98f00b204e9800998ecf8427e`). No signing key is created or stored. The
image is exactly 100,663,296 bytes. The hashed prefix is the 15,753,216-byte
#21 image, the footer-referenced vbmeta is 448 bytes at offset 15,753,216, and
the algorithm is `NONE` with a zero-length authentication block. Kernel bytes,
header page, command line, empty generic ramdisk, `init_boot.img` and
`vendor_boot.img` stay at the #21 hashes. Two consecutive runs produced the
same SHA-256 `d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131`,
which differs from every prior boot and from stock. The candidate stays under
`$WORK/out` and is not committed.

The candidate must not be combined with the #21 marker image or the #23 control
in one flash. Whether any slot-A test happens belongs to the physical
coordinator under the existing slot-A scope. No device operation was performed
for #25.

## Stock-kernel control image (#23, host-only, 2026-10-22)

**Single variable:** the kernel payload. `scripts/build-stock-kernel-control.sh`
copies the verified #21 `boot.img` and replaces only its gzip kernel bytes
with the unmodified gzip payload from the read-only stock slot-A `boot_a`
reference. The kernel-size field and the resulting image length are the only
other bytes that change. The stock kernel is not rebuilt and its bytes are
not copied into Git.

The #21 header page stays byte-identical apart from the little-endian
`kernel_size` at offset 8: header v4, header size 1,584, OS version 0,
signature size 0, empty generic ramdisk and the #21 command line
`console=ttynull stack_depot_disable=on cgroup_disable=pressure
kasan.page_alloc.sample=10 kasan.stacktrace=off kvm-arm.mode=protected
bootconfig ioremap_guard loglevel=6`. The payload starts at offset 4,096 and
the image ends at the next 4,096-byte boundary with zero padding and no AVB
footer or separate AVB0 record. `init_boot.img`, `vendor_boot.img`, the DTB
blob, bootconfig and both debug ramdisks are not inputs to this step and stay
at the verified #21 hashes.

| artifact | verified #21 (bytes; SHA-256) | #23 control (bytes; SHA-256) |
| --- | --- | --- |
| `boot.img` | 15,753,216; `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` | unchanged input; **identical** `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` |
| `boot-stock-kernel.img` | not produced | 13,955,072; `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` |
| embedded gzip payload | 15,746,607; `b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277` | 13,949,926; **identical to stock slot-A payload** `dcbd8ae71b7e6341c3604c35360213b1d40a69ac38672e247772d4af399c3651` |
| decompressed `Image` | 41,859,584 | 35,224,064 (stock 6.1.84; not rebuilt) |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |

The control SHA differs from `55fa78ca…`, `116b1662…`, `84f7f5ea…`,
`5e866c54…` and `1fdc2570…`, and from stock `boot_a` `197aff11…`. Two
sequential runs of `scripts/build-stock-kernel-control.sh` produced the same
control SHA. `scripts/verify-bootimg.sh` still checks the #21 image and the
unchanged `init_boot`/`vendor_boot`/DTB/ramdisk hashes, then
`scripts/verify-stock-kernel-control.py` fails closed unless the control
payload equals the stock slot-A gzip bytes, the header page equals #21 apart
from kernel size, the command line and empty ramdisk match, the image ends on
the aligned kernel with zero padding, both decompressed images share the arm64
`Image` fields (`MZ` branch `0xfa405a4d`, `text_offset = 0`, flags `0xa`,
reserved words zero, `ARMd` magic, PE offset `0x40`), and the control SHA is
none of the prior boots. Negative fixtures cover a changed payload byte, the
#21 payload left in place, dirty padding, appended data, a changed command
line, a nonempty generic ramdisk, a nonzero `text_offset`, different arm64
flags and a repeated prior SHA.

**How a later authorized capture discriminates (contract, not a test
request).** This control is not the unmeasured #21 marker image and must not
be combined with it. A capture is useful only if it is read *before* any later
kernel boot. No device operation was performed for #23.

- **Layout/header rejection:** the control follows the same under-five-second
  return to fastboot as test `boot_a` `116b1662…`. The debug 6.1.78 payload is
  not required for that failure.
- **Kernel-payload failure:** the control gets farther than that fastboot
  return, or leaves a stock 6.1.84 console from the control boot. The debug
  6.1.78 payload remains the isolated variable.
- **No kernel record:** the control fails without a usable new console. That
  still does not prove an AVB accept or reject verdict.
- **Invalid:** another kernel boots before the control attempt's pstore is
  read. The later boot can replace the buffer, so the capture proves nothing.

## Pre-ramoops marker and pstore panic (#21, host-only, 2026-10-22)

**Single kernel variable:** `configs/asteroids-debug-marker.fragment` is merged
last, after the measured stock command line and the #18 USB closure. It changes
exactly two settings relative to the verified #18 `.config`:

1. `CONFIG_CMDLINE` is the measured stock A059P value with one appended token,
   `sm7635-boot-marker`. With the unchanged `CONFIG_CMDLINE_EXTEND=y`, the
   pinned 6.1.78 `early_init_dt_scan_chosen()` copies `CONFIG_CMDLINE` first
   and then appends the bootloader `bootargs`, so the token ends the built-in
   part of the kernel's effective command line and is printed in the kernel's
   `Kernel command line:` line.
2. `CONFIG_PANIC_TIMEOUT=-1` is restated. It was already `-1` in the stock
   `config.gz` and the #18 build; `kernel/panic.c` initializes `panic_timeout`
   from it, and the `panic=` command-line parameter overrides it. The value is
   therefore present even if the bootloader supplies no `panic=` argument.
   Because it is non-zero, `panic()` reaches `emergency_restart()` without a
   delay instead of staying silent; the kmsg/console dump into the ramoops
   buffer happens before that restart.

**Issue exception — `CONFIG_PSTORE_CONSOLE_SIZE`:** the symbol does not exist
anywhere in the pinned vendor Kconfig tree at
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7` (`fs/pstore/Kconfig` has only
`PSTORE_BLK_CONSOLE_SIZE`, which is a pstore/blk setting and is not selected).
It is also absent from the measured stock `config.gz`. No symbol was added, no
header was redefined and no upstream patch was applied. The 2 MiB console
reservation is instead the stock device-tree value already verified on the #18
chain: after stock DTBO entry 65 is applied to vendor DTB index 9,
`/reserved-memory/ramoops_region` has `reg = <0x0 0x81f20000 0x0 0x400000>`,
`console-size = <0x200000>` and `pmsg-size = <0x200000>`. `fs/pstore/ram.c`
reads `console-size` from that node, so the reservation does not depend on the
missing Kconfig symbol. `CONFIG_PSTORE=y`, `CONFIG_PSTORE_CONSOLE=y` and
`CONFIG_PSTORE_RAM=y` are unchanged.

Nothing else moves. The diff of the #18 `.config` against this build is that
one command-line line. `init_boot.img`, `vendor_boot.img`, the 20 stock DTBs,
the 175-byte bootconfig, both gzip ramdisks and the boot/vendor header command
lines are byte-identical to #18. The boot header command line intentionally
does **not** carry the marker: the marker lives in the kernel so it can only
appear in a console written by this kernel.

| artifact | verified #18 (bytes; SHA-256) | #21 (bytes; SHA-256) |
| --- | --- | --- |
| `.config` | 237,546; `5781d141305c4f27bdc0dd3e69a1136a7e9be3c4fbc538d8b5c11e6f2442cd32` | 237,565; `93acd0920ceadb767625f06a30d992aea0901000e86abec7b61c7e6827f0fa28` |
| `Image` | 41,859,584; `a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29` | 41,859,584; `34fee908da7366f2f174eca4edcc84d732c709067cf81dcba43dfde627dffb13` |
| `Image.gz` | 15,746,316; `9055503e67a1321468fa75608b677eec257c403345a7a6de6709369fb71d5d4a` | 15,746,607; `b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277` |
| `boot.img` | 15,753,216; `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` | 15,753,216; `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| vendor `dtb.img` | 9,419,891; `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` | 9,419,891; **identical** `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| gzip cpio in both ramdisks | 1,672,600; `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` | 1,672,600; **identical** `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The new `boot.img` SHA differs from every previously tested boot
(`5e866c54…`, `84f7f5ea…`, `116b1662…`) and from the untested #16 boot
`1fdc2570…`. Two sequential `scripts/build-bootimg.sh` runs produced the same
SHA set, and `scripts/verify-bootimg.sh` passed on both. The verifier checks
the marker in the fragment, merged config, built `.config` and the IKCONFIG
embedded in the unpacked kernel, checks the NUL-terminated command-line string
inside `Image`, asserts `CONFIG_PANIC_TIMEOUT=-1` and the existing pstore
options, and fails closed if `CONFIG_PSTORE_CONSOLE_SIZE` is either silently
dropped or synthesized while absent from `fs/pstore/Kconfig`. If a future pin
gains the symbol, the same check requires the fragment and the built config to
set it to `2097152`. Every existing geometry, AVB, DTB, ramdisk, recovery and
USB-closure check still passes, including the negative fixtures. Config
comparison against the read-only stock `config.gz`: 5,996 stock and 6,979 built
symbol lines, 5,924 identical, 72 stock-only or changed and 1,055 built-only or
changed. `CONFIG_CMDLINE` now differs from stock by exactly the marker token.

**How a later capture distinguishes kernel entry (contract, not a test
request).** A console is useful only if it is read *before* any later kernel
boot, because the next kernel replaces the ramoops buffer. Parsed marker
counts are the public record; raw pstore stays on the build host.

- **Kernel entry:** the pre-restore console contains the literal token
  `sm7635-boot-marker` (in the `Kernel command line:` line), or the 6.1.78
  banner. The token cannot come from a stock or recovery 6.1.84 session, from
  the boot header or from `vendor_boot`: only this kernel's built-in command
  line carries it. Console text after the banner then localizes the failure.
  `Kernel panic - not syncing` is an early panic; `usb-init` or dropbear
  progress is a later failure. With `panic_timeout` at `-1` a panic restarts
  at once, so the panic text survives only in the ramoops buffer; an
  immediate restart that leaves the buffer intact is expected, and a reset
  with no marker at all still counts as no kernel entry.
- **No kernel entry:** the attempt returns to fastboot or wedges, and the
  pre-restore console is still only the preceding stock or recovery 6.1.84
  session with zero occurrences of `sm7635-boot-marker`. That supports failure
  before this kernel executed, or before it initialized the stock ramoops
  region at `0x81f20000`. It is not, by itself, an AVB accept or reject
  verdict.
- **Invalid:** the console is read only after another kernel has booted. That
  boot can overwrite the attempt buffer, so the absence of the marker then
  proves nothing.

No previously flashed complete set may be repeated. Boots `5e866c54…`,
`84f7f5ea…` and `116b1662…` are burned, and the complete sets that used
`vendor_boot` `bde3a3b3…` or `6078269d…` have failed as wholes. This build
keeps `init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` byte-identical,
which is valid for a host-only artifact; only a physically new `boot.img` SHA
makes a future set new. Whether any slot-A test happens, and the verified
rollback around it, belongs solely to the physical coordinator. No device
operation was performed for #21.

## Recovery-path boundary after #18 (`attempt-20261021-1717`, host-only, 2026-10-21)

**Observed:** The physical coordinator flashed the #18 single-variable slot-A
chain (`boot_a` `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce`,
`init_boot_a` `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89`,
`vendor_boot_a` `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d`;
all three writes OKAY). After `fastboot reboot` at 17:53:57+02:00, host USB
disconnected and re-enumerated as fastboot `18d1:d00d` within four seconds
(17:54:01) and stayed there through all 45 observations (225s) with no
`18d1:4ee2` gadget, adb or SSH. At 17:59:24, `fastboot reboot recovery` was
issued *while the test chain remained on slot A*; it also returned to fastboot
`18d1:d00d` within four seconds (17:59:28) and remained there for all 12
samples (60s). After restoring stock `boot_a`, `init_boot_a` and `vendor_boot_a`
(18:03:35-18:03:44), the identical `fastboot reboot recovery` succeeded
(`adb` recovery at 18:04:16). On-device block SHA-256 reads in recovery
matched the verified stock backups for `boot_a` (`197aff11…06d4d`),
`init_boot_a` (`baa33fd4…1e3193`), `vendor_boot_a` (`23725940…c1253`), and
unchanged `dtbo_a` (`759813db…e13c992`) and `vbmeta_a` (`cc1926d2…cdffe`);
stock Android then reached `sys.boot_completed=1`. Host-only logs are at
`~/phone-second-life-data/mb003/pstore/attempt-20261021-1717/`.

**Recovery partition resolution and pstore provenance (measured, not inferred):**
`scripts/verify-recovery-boundary.py` (invoked by `scripts/verify-bootimg.sh`)
checks `recovery_a.img` (`0c6767698ebb069064b450b109cde6a1172b478e30000fe852e7d9bc19dbae9e`,
byte-identical to `OrangeFox-R12.0_6.1-Unofficial-Asteroids.img`) and
`recovery_b.img` (`6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b`).
Both are 100 MiB Android boot-header v4 images with **`kernel_size = 0`** and
legacy LZ4-compressed `070701` newc ramdisks at offset 4,096 (`48,350,666` and
`15,609,526` bytes), no DTB and no bootconfig, plus AVBf footers at `48,357,376`
and `15,613,952` (`RSA4096_SHA256`, `flags = 0`, `rollback_index = 1`;
`recovery_b`'s public key matches `vbmeta_a`'s `recovery` chain descriptor at
rollback location 1, while `recovery_a`'s self-signed key differs). Neither
`recovery` partition contains a kernel or DTB: on this header-v4 layout,
booting recovery **requires** the kernel from `boot_a` and the DTB/bootconfig
from `vendor_boot_a`. Every captured recovery-session console (`0134`, `0550`,
`0640`, `1156`) logs `Freeing initrd memory: 57900K` (`59,289,600` bytes =
4 KiB-aligned sum of `8,821,389`-byte `vendor_boot_a` PLATFORM ramdisk +
`2,113,581`-byte `init_boot_a` generic ramdisk + `48,350,666`-byte OrangeFox
`recovery_a` ramdisk + bootconfig = `59,285,811` bytes), whereas normal
Android boot (`1717` and `2026-10-19`) logs `Freeing initrd memory: 10680K`
(`10,936,320` bytes = 4 KiB-aligned sum of `vendor_boot_a` + `init_boot_a` +
bootconfig = `10,935,145` bytes). Therefore:

1. Neither conflicted note was wholly accurate: recovery does **not** run from
   `recovery_a` + `vendor_boot_a` without `boot_a` (`recovery_a` has no kernel),
   and it does **not** use `boot_a` only for a hardware-key menu. On `A059P`,
   ABL's recovery boot path loads `boot_a` (kernel) + `vendor_boot_a` (PLATFORM
   ramdisk, DTB index 9, bootconfig) + `init_boot_a` (generic ramdisk) +
   `recovery_a` (OrangeFox ramdisk appended last, overriding `/init`). Because
   all three flashed slot-A partitions (`boot_a`, `init_boot_a`, `vendor_boot_a`)
   are consumed by both normal boot and `fastboot reboot recovery`, and all
   three were restored together at 18:03:35-18:03:44 before recovery succeeded,
   stage 6 (`fastboot reboot recovery` failing in 4s on the test chain) proves
   the failure is **not** specific to normal-boot userspace or Android-mode
   bootconfig, while keeping all three modified slot-A partitions inside the
   candidate boundary.
2. Why `attempt-20261021-1717` `pstore` differs from `0134`/`0640`/`1156` (and
   why `ramoops` exposes the *previous* boot): Linux `pstore/ramoops` exposes
    the buffer saved by the **previous** kernel session in `/sys/fs/pstore`
   while writing the **current** session's console to the live ring buffer for
   the *next* boot.    In `0134`, `0640` and `1156`, a pre-flash recovery session was booted to
   hash slot-A partitions just before `reboot bootloader`; its `57900K`-initrd
   recovery log (`37.6s`, `35.5s` and `1402.9s` uptime respectively, each
   ending at `Reboot start, reason: reboot,bootloader` immediately before the
   test flash) remained in `ramoops` across the failed test reboot and was read
   back by the post-restore recovery boot. In `1717`, there was **no**
   pre-flash recovery boot: the phone rebooted directly from the ~2.4h stock
   Android session (`10680K` initrd, `Load bootconfig: 1279 bytes 80 nodes`,
   `sys.boot_completed=1` at `[17.764152]`, ending at `[8764.401407]
   BATTERY_CHG: battery_shut_down`) into fastboot at 17:53:22, failed the
   17:53:57 normal test reboot (4s to `18d1:d00d`) and the 17:59:24 test-chain
   recovery reboot (4s to `18d1:d00d`), and then booted stock recovery at
   18:03:44, which mounted `/sys/fs/pstore` and pulled that **intact
   pre-attempt Android console** (`1,073,964` bytes) and `pmsg` (`4,973` bytes).
   **Consequence:** across **all four** attempts (`0134`, `0640`, `1156`,
   `1717`), the post-restore recovery boot did **not** overwrite the attempt
   window before `/sys/fs/pstore` was read — rather, none of the four normal
   test reboots (nor the `1717` stage-6 test-recovery reboot) ever initialized
   or wrote to `ramoops` at `0x81f20000` (which happens at `~0.068s` on stock).
   That proves every tested chain failed **either** before kernel hand-off (in
   XBL/ABL) **or** before the test kernel could initialize and write to that
   `ramoops` reservation.
3. Host xHCI USB enumeration timing (`journalctl -k` on the build/test host)
   across all five failed reboots (`0134` at 01:34:16, `0640` at 06:44:34,
   `1156` at 12:22:09, `1717` normal at 17:53:57, `1717` stage-6 recovery at
   17:59:24) shows a **single** reset cycle (`USB disconnect` at `t = 0s`,
   full-speed `t = +1..2s`, high-speed `18d1:d00d` fastboot at `t = +4.0s`),
   matching the `4.0–5.0s` timing of a direct `adb reboot bootloader` entry into
   ABL (`0640` 06:44:12 -> 06:44:17, `1156` 12:21:35 -> 12:21:39, `1717`
   17:53:22 -> 17:53:27) with no intermediate second reset. This is strongly
   consistent with synchronous ABL rejection into fastboot within the same boot
   cycle, though an immediate post-jump reset before `ramoops` cannot be ruled
   out by USB timing alone.

| tested slot-A chain | `boot_a` / `init_boot_a` / `vendor_boot_a` SHA-256 prefixes | single variable changed | observed normal + recovery result |
| --- | --- | --- | --- |
| #8 (`0134`) | `5e866c54…` / `f4b987ee…` / `bde3a3b3…` | initial 3-image SSH set (built DTBs, duplicate boot ramdisk) | `<5s` return to `18d1:d00d`; no gadget/adb/SSH |
| #10 (`0640`) | `5e866c54…` / `f4b987ee…` / `6078269d…` | `vendor_boot_a`: stock 20-DTB blob (DTBO 65 applies to index 9) | `<5s` return to `18d1:d00d`; not sole cause |
| #14 (`1156`) | `84f7f5ea…` / `f4b987ee…` / `6078269d…` | `boot_a`: stock `CONFIG_CMDLINE` override (no `panic_on_taint`) | `<5s` return to `18d1:d00d`; not sole cause |
| #16 (untested) | `1fdc2570…` / `f4b987ee…` / `6078269d…` | `boot_a`: `ramdisk_size = 0` (generic ramdisk only in `init_boot_a`) | not physically flashed alone; carried into #18 |
| #18 (`1717`) | `116b1662…` / `f4b987ee…` / `6078269d…` | `boot_a`: `#16` empty boot ramdisk + built-in Volcano USB closure | `<5s` return to `18d1:d00d` on both `reboot` and `reboot recovery` |

**Plain non-discrimination statement and exact blocker (#12 Acceptance 2):**
Across all four physical attempts, `init_boot_a` `f4b987ee…`, `vendor_boot_a`
`6078269d…` (after #8), `dtbo_a` and `vbmeta_a` (with `flags = 0` and stock
hash/chain descriptors that none of the unsigned, footerless test images match)
stayed constant, and targeted `getvar` recorded only `serialno`,
`current-slot: a`, `unlocked: yes` and `product: pineapple` (`getvar all` is
not used because it wedged fastboot on `0332`/`0535`). Host-only evidence
**cannot** discriminate between:

- **Regime 1 — Bootloader/AVB or header-format rejection before kernel hand-off:**
  ABL rejects unsigned/footerless `boot_a` and/or `vendor_boot_a` against stock
  `vbmeta_a` (`flags = 0`), or rejects `vendor_boot_a`'s gzip PLATFORM ramdisk /
  unpadded size during both normal and recovery boot.
- **Regime 2 — Pre-`ramoops` kernel failure:**
  ABL hands off to the 6.1.78 `Image.gz` in `boot_a`, which resets before
  `ramoops` initializes at `0x81f20000`. The preserved pre-attempt Android
  console and ~4s return do not rule this out, but the absence of a second
  host USB reset is less consistent with a kernel-triggered restart (which
  normally produces a second disconnect/re-enumeration). No 6.1.78 marker is
  required for this regime. `~0.068s` is stock kernel's observed probe time,
  not a measured upper bound for the test kernel.
- **Regime 3 — Later kernel/init/USB failure:**
  Incompatible with this attempt-specific evidence **if** the 6.1.78 kernel
  actually initialized the same `ramoops` reservation: any subsequent
  console writes should replace the pre-attempt Android console. The host
  verifies DTBO 65 applies to vendor DTB index 9 and supplies
  `0x400000@0x81f20000`; it cannot prove that the kernel reached the driver,
  that ABL passed this DTB, or that the persistent region survived a power
  reset. A late failure with `ramoops` absent/never mounted remains an
  alternative, not a proven rejection verdict.

No new kernel/ramdisk/boot-image build is produced for #12: building another
unauthenticated `{boot_a, init_boot_a, vendor_boot_a}` perturbation without
isolating `{boot_a}` vs `{vendor_boot_a}` vs `vbmeta_a` would be a speculative
blind flash. The **exact blocker** is that neither the 17:53:57 nor 17:59:24
attempt has an ABL AVB accept/reject verdict, boot reason/retry status, or an
attempt-tagged pre-rollback pstore capture. The only captured `getvar` values
were identity, slot, unlocked state and product; an earlier `getvar all`
wedge means it is not a supported fallback. Stock rollback changed all three
slot-A partitions together, so it cannot isolate the kernel-bearing `boot_a`
from the DTB/bootconfig-bearing `vendor_boot_a`. The latter is a **controlled
constant** (`6078269d…`) in the failed #10/#14/#18 sets; those complete SHA
sets must not be repeated. A signed replacement for `vbmeta_a`/`dtbo_a` is
outside the existing slot-A-only approval, and a stock `vbmeta_a` mismatch is
not a verdict on an unlocked/orange device. In particular, the OrangeFox
`recovery_a` key differs from `vbmeta_a`'s recovery chain key, yet recovery
worked after stock rollback; the logs do not prove whether recovery loaded
`recovery_a` or `recovery_b`, so this cannot establish an AVB exception for
the normal boot path.

**Single selected discriminator (measurement, not a new flash plan):** an
attempt-tagged **first bootloader-side hand-off verdict** with partition name
and AVB/retry reason, collected *before* any stock/recovery boot, would directly
separate pre-kernel rejection from kernel entry. An explicit *reject* of
`boot_a` or `vendor_boot_a` proves regime 1. An explicit *accept* without a
6.1.78 marker still leaves regime 2 and loss of the ramoops channel possible.
A 6.1.78 kernel banner/progress marker in a pre-restore capture proves kernel
entry and distinguishes regime 2 if it stops before `/init`, versus regime 3
if `usb-init`/`dropbear` markers precede the failure. The 1717 record already
supplies an attempt-specific **upper bound**: the test kernel did not write to
`ramoops` during either failed window, while no post-test stock/recovery boot
had yet modified the saved pre-attempt Android console. No currently preserved bootloader-side verdict or supported narrow read-only
AVB/reason/retry channel exists; an earlier `getvar all` wedged fastboot.
Thus the remaining boundary between ABL rejection and pre-`ramoops` kernel
failure and the minimal corrective artifact are **unproven**. The exact remaining blocker is a supported,
bounded, attempt-tagged read-only ABL hand-off/verdict channel on slot A,
**before** any recovery boot or stock rollback; a serial/bootloader log
interface is not established from these host records and must not be guessed.
The strategist/coordinator owns any future measurement decision under the
existing slot-A-only boundary and must not repeat a failed full SHA set;
writing `vbmeta_a`/`dtbo_a` needs separate approval and is not a staged
artifact here. This document does not request any physical operation.
Verified stock rollback for the historical attempt was already measured on
all three restored partitions plus unchanged `dtbo_a`/`vbmeta_a`; only the
physical coordinator owns that boundary. The release-image userdata decision
is independent.

## Volcano USB driver reachability (#18, host-only, 2026-10-21)

**Path B selected:** `boot.img` alone changes relative to the verified #16
three-image chain. The `init_boot.img` and `vendor_boot.img` payloads and hashes
are unchanged, including both identical gzip debug ramdisks, all 20 stock vendor
DTBs, the 175-byte bootconfig, cmdlines and stock DTBO 65 selection. The new
last-applied `configs/asteroids-volcano-usb-builtin.fragment` only promotes
`=m` drivers to `=y`; it does not alter source DTBs, boot layout or initramfs.
The #16 `Image`, `.config`, `Image.gz` and boot bytes change as expected; no
modules are staged. `CONFIG_USB_DWC3_QCOM=y` matches `qcom,dwc3` but does **not**
match the actual `qcom,dwc-usb3-msm` Volcano wrapper. Kconfig alone is not
proof: the full pinned 6.1.78 `vmlinux` link now succeeds (the source also
needs eight local build-only trace include path fixes to compile the promoted
drivers). The unpacked `Image.gz` IKCONFIG equals the merged `.config`; the
verifier resolves the exact phandle suppliers after applying the SHA-verified
stock DTBO 65 to stock vendor DTB index 9. The public repository contains no
raw stock image, module, DTB, key or build artifact.

| merged board DT binding / dependency | pinned source driver / config | #16 -> #18 location |
| --- | --- | --- |
| `/soc/ssusb@a600000` `qcom,dwc-usb3-msm`; child `snps,dwc3` `dr_mode=otg` | `drivers/usb/dwc3/dwc3-msm-core.c` `USB_DWC3_MSM`; core `USB_DWC3` | `m` -> `y`; `y` -> `y` |
| child `usb-phy` `hsphy@88e3000` `qcom,usb-snps-eusb2-phy`, `ssphy@88e8000` `qcom,usb-ssphy-qmp-dp-combo` | `drivers/usb/phy/phy-msm-snps-eusb2.c` `USB_MSM_EUSB2_PHY`; `phy-msm-ssusb-qmp.c` `USB_MSM_SSPHY_QMP` | `m` -> `y` each |
| HS PHY `usb-repeater`/`dummy-supply`; PMIC parent and SPMI arbiter | `drivers/usb/repeater/repeater-qti-pmic-eusb2.c` `QTI_PMIC_EUSB2_REPEATER`, `USB_REPEATER`; `MFD_SPMI_PMIC`, `SPMI_MSM_PMIC_ARB` | `m` -> `y` each |
| parent clocks/resets (5 GCC clocks, 1 reset); HS/SS PHY GCC, RPMh and fixed clocks | `drivers/clk/qcom/gcc-volcano.c` `SM_GCC_VOLCANO`, `COMMON_CLK_QCOM`; `clk-rpmh.c` `QCOM_CLK_RPMH`; fixed-clock builtin | `m` -> `y` (fixed-clock `y`) |
| parent `USB3_GDSC-supply`, SS PHY `usb3_dp_phy_gdsc-supply`, GCC CX/MX, HS/SS/repeater LDOs | `gdsc-regulator.c` `QCOM_GDSC_REGULATOR`, `rpmh-regulator.c` `REGULATOR_RPMH`, `QCOM_RPMH`, `QCOM_COMMAND_DB` | `m` -> `y` each |
| parent three `interconnects` through aggre1/mc_virt/cnoc_cfg/gem_noc and BCM voter | `drivers/interconnect/qcom/volcano.c` `INTERCONNECT_QCOM_VOLCANO`; `INTERCONNECT_QCOM_BCM_VOTER`, `INTERCONNECT_QCOM_RPMH`, `INTERCONNECT_QCOM_QOS`, `INTERCONNECT_QCOM_DEBUG` | `m` -> `y` each (helpers selected by Kconfig) |
| parent `extcon = <&eud>`; `usb-role-switch`, connector via PMIC GLINK/UCSI | `drivers/soc/qcom/eud.c` `QCOM_EUD`; `QTI_PMIC_GLINK`, `UCSI_QTI_GLINK` | `m` -> `y` each |
| child `iommus`, parent dummy SMMU probe-order phandle; SS PHY portselect pinctrl | `ARM_SMMU`, `ARM_SMMU_QCOM`, `QCOM_IOMMU_UTIL`, `QTI_IOMMU_SUPPORT`; `PINCTRL_VOLCANO`, `PINCTRL_MSM`, `QCOM_SCM`; `QCOM_PDC` for parent IRQs | `m` -> `y` each |

There is **no** direct `power-domains` property on either USB node. The
`dummy-supply` SMMU phandle is a probe-order edge, not a power rail. The
merged overlay adds the eUSB2 repeater phandle and its two regulator supplies.
The built-in closure also promotes link-only providers (RPMh, CRM, SOCINFO,
IPC logging, SMEM/GLINK, Gunyah RM/SHM, minidump/mem-buf, regulator debug and
proxy, regmap debug, hwspinlock and redriver). Without them `ld.lld-17`
reports undefined symbols including `crm_write_bw_vote`,
`devm_regulator_proxy_consumer_register` and `qcom_glink_spss_register`.
The additive fragment is the smallest link-complete `=y` closure found while
keeping the existing debug initramfs, role-switch path and vendor kernel
policy; the exact requested/selected symbol list is checked by
`scripts/verify-volcano-usb.py`. Promoting providers that are `=m` on #16
rather than staging 58+ modules avoids an unproven `modules.dep`/early insmod
sequence and preserves the two other chain images exactly.

| artifact | verified #16 (bytes; SHA-256) | #18 Path B (bytes; SHA-256) |
| --- | --- | --- |
| `.config` | 237,498; `8c00c6f8cd89a6b044a0c7df7c481248786b09e14b12964699ed3ee6da7905d9` | 237,546; `5781d141305c4f27bdc0dd3e69a1136a7e9be3c4fbc538d8b5c11e6f2442cd32` |
| `Image` | 39,971,328; `cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386` | 41,859,584; `a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29` |
| `Image.gz` | 15,096,553; `0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c` | 15,746,316; `9055503e67a1321468fa75608b677eec257c403345a7a6de6709369fb71d5d4a` |
| `boot.img` | 15,101,952; `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` | 15,753,216; `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| vendor `dtb.img` (20 entries) | 9,419,891; `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` | 9,419,891; **identical** `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| gzip cpio in both ramdisks | 1,672,600; `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` | 1,672,600; **identical** `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The boot header remains v4 with empty boot generic ramdisk, 1,584-byte
header in a 4,096-byte page, kernel at byte 4,096, kernel gzip length
15,746,316 and no bytes after the aligned kernel at byte 15,753,216.
Init_boot's empty kernel and generic ramdisk offset 4,096, vendor DTB offset
1,679,360, PLATFORM ramdisk, table and bootconfig offsets remain #16's.
The new boot SHA differs from all previously failed boots `5e866c54…`,
`84f7f5ea…`, and the untested #16 boot `1fdc2570…`. Two sequential
host-only packaging/verification runs produced the same SHA set. Verified
stock `parts-a.sha256` and `config.gz` were read only; the latter measures
`CONFIG_CMDLINE` but cannot establish vendor-module runtime loading.

**Checks:** `scripts/build-baseline.sh` (`Image dtbs`, `vmlinux` link passed),
`build-bootimg.sh` twice (deterministic SHA), `verify-bootimg.sh` twice
(DTBO-65 applied; 22 phandle suppliers; embedded config; 0 `.ko`), and
`compare-baseline.sh` passed. Synthetic fixture output includes
`expected module glue without .ko failure: CONFIG_USB_DWC3_MSM=m has no verified built-in driver; initramfs modules/load path not verified (0 .ko)`
and `expected unpacked zero-.ko initramfs failure: CONFIG_USB_DWC3_MSM=m has no built-in driver and initramfs has 0 .ko files`;
existing duplicate-ramdisk fixture still emits `boot generic ramdisk must be empty`.
Host structural checks do **not** prove that the USB controller binds, that
`/sys/class/udc/a600000.dwc3` appears, or that gadget/SSH is reachable.

**Evidence vs hypothesis:** The old chain could not load the `=m` glue and
PHY/power/clock closure from its zero-`.ko` initramfs. This new chain makes
those objects link-reachable in the unpacked `Image`. Actual probe ordering,
Type-C role, UDC enumeration (`18d1:4ee2`) and key-only Dropbear SSH remain
hypotheses pending separately authorized measurement. The previously observed
five-second return to fastboot predates the `/init` 10-second UDC wait and is
**not** explained by the missing driver closure; no bootloader rejection or
kernel entry has been established. Issue #12 remains blocked on an
attempt-specific discriminator. This work is independent of encrypted
userdata and release-image packaging.

**Physical test gate (not executed or requested by this worker):** Only the
physical-test coordinator may separately review the existing
`humanApprovals.bounded_full_chain_test_slot_a` scope for a bounded slot-A
three-image chain using these exact checked hashes, verified stock rollback
and an attempt-specific, supported read-only kernel-entry measurement path.
No approval here covers `dtbo`, `vbmeta`, `userdata`, slot B or permanent
flashing. Without a supported attempt-specific read-only discriminator, the
boot boundary remains unresolved. No device operation was performed for #18.

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
