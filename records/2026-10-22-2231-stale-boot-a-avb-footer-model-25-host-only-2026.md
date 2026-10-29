---
date: 2026-10-22
issue: omnipha/linux-sm7635#25
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
