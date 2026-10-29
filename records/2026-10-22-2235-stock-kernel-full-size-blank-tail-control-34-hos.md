---
date: 2026-10-22
issue: omnipha/linux-sm7635#34
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
