---
date: 2026-10-22
issue: omnipha/linux-sm7635#36
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
