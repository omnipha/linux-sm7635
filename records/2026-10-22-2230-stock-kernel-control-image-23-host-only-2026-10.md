---
date: 2026-10-22
issue: omnipha/linux-sm7635#23
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
