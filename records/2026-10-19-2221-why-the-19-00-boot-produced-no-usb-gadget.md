---
date: 2026-10-19
issue: omnipha/ports#3
subsystem: usb
result: inconclusive
source: BOOT.md
---
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
