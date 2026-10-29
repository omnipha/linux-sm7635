---
date: 2026-10-22
issue: omnipha/linux-sm7635#30
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
