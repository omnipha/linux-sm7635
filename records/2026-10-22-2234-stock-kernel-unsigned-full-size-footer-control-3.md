---
date: 2026-10-22
issue: omnipha/linux-sm7635#32
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
