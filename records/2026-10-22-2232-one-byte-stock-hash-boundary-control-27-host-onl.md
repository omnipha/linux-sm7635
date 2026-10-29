---
date: 2026-10-22
issue: omnipha/linux-sm7635#27
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
