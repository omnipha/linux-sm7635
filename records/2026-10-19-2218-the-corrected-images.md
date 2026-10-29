---
date: 2026-10-19
issue: omnipha/ports#3
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
