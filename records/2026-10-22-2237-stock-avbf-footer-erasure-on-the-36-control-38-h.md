---
date: 2026-10-22
issue: omnipha/linux-sm7635#36
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
