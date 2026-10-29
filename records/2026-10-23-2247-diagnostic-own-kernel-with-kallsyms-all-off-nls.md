---
date: 2026-10-23
issue: omnipha/linux-sm7635#60
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Diagnostic own kernel with KALLSYMS_ALL off, NLS not removable (#60, host-only, 2026-10-23)

**Host failure: the rebuilt own 6.1.78 kernel gzips to 14,236,242 bytes, 268,882
bytes over the 13,967,360-byte signed-tail bound. No boot image and no init_boot
image were assembled and no image SHA is recorded.** No device, adb, fastboot,
USB, flash or userdata operation was performed. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. Every previously
measured SHA stays unreused.

The named fragment `configs/asteroids-diagnostic-kallsyms-nls-off.fragment`
contains exactly `CONFIG_KALLSYMS_ALL=n` and `CONFIG_NLS=n`, merged last on top
of the #55 baseline (stock `config.gz` SHA-256
`90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`, the 43-symbol
debug-off fragment, the Gunyah and ksyms link fragments, the USB, pstore and
marker fragments). `make olddefconfig` turns `CONFIG_NLS` back to `y`, because
other symbols that must stay on select it: `USB_GADGET=y` (the unchanged USB
closure), `F2FS_FS=y` (kept on by the issue) and `SCSI_UFSHCD=y`. Making NLS
disappear would require turning off one of those, which the issue forbids. The
resulting `.config` differs from the #55 `.config` in exactly one symbol,
`CONFIG_KALLSYMS_ALL` (`y` to not set); `CONFIG_KALLSYMS`, `EXT4_FS`, `F2FS_FS`,
`ANDROID_BINDER_IPC` and the USB closure (`verify-volcano-usb.py config`) are
unchanged. The build used the pinned vendor commit
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, Ubuntu clang 17.0.6 with
`ARCH=arm64 LLVM=-17 LLVM_IAS=1`, and the #55 gzip framing (zlib level 9,
header `1f 8b 08 00 00 00 00 00 02 03`).

| quantity | bytes |
| --- | ---: |
| #55 `Image-stock-config` | 37,198,336 |
| #60 `Image-diagnostic-kallsyms-nls` | 36,018,688 |
| #55 gzip payload | 14,782,792 |
| #60 gzip payload | 14,236,242 |
| signed-tail bound | 13,967,360 |
| over bound | 268,882 |

Per-symbol measured and estimated deltas against the 268,882-byte shortfall:

| symbol | state | gzip bytes | basis |
| --- | --- | ---: | --- |
| `KALLSYMS_ALL=n` | applied | -546,550 | measured rebuild (#57 estimate 546,197, +353) |
| `NLS=n` | not buildable | (-268,815) | zero-mask recompression of `fs/nls/` on the new Image, 669,180 raw bytes (#57 estimate 275,810) |
| of which CJK codepages 932/936/949/950 | not applied | (-248,629) | zero-mask estimate, 444,940 raw bytes |
| of which `nls_base.o` | not applied | (-1,102) | zero-mask estimate, 7,048 raw bytes |

The figures in parentheses are recompression estimates on the exact new map
bytes, not a build. They exclude second-order kallsyms and BTF shrink. Even if
`NLS` were removable, the estimate leaves the payload 67 bytes over the bound
(268,882 - 268,815). The 49 `NLS_CODEPAGE_*`, `NLS_ISO8859_*`, `NLS_MAC_*` and
`NLS_KOI8_*` charset symbols are separate options; this issue changes only the
two named symbols, so they were not touched. The issue's recorded contingency,
dropping `EXT4_FS` (#57 estimate 329,690 bytes), is not part of this delivery.

Artifacts stay under `$WORK/out` and are not committed:
`Image-diagnostic-kallsyms-nls` SHA-256
`724d8a6b3eac37046941458b83059d00a48ed37fc0f70a9f6a3224c38e86af6a`,
`Image-diagnostic-kallsyms-nls.gz` SHA-256
`37535dd13312e2d2078c344cbf11db32260f0d35c4d3e0b2bf95a214b27b9bb8`,
`.config-diagnostic-kallsyms-nls` SHA-256
`05c70f1a766c7f2d265dc538363445ae581d158a1e60d93313e0c35a0aa2dfd0`. A relink of
the same inputs differs from the built Image in 19 bytes, all inside the
`.notes` build-id.

Command sequence (one build at a time, host only):

```sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-kallsyms-nls.sh
WORK="$HOME/sm7635-build" scripts/report-diagnostic-shortfall.sh
```

`build-diagnostic-kallsyms-nls.sh` fails closed at the bound check, removes any
`boot-diagnostic-kallsyms-nls.img` and writes no boot image, so the
step 3 and step 4 images (stock-prefix signed-tail boot image, and the #53
init_boot with one added `uname -r` line) were not produced. The script also
fails closed if `CONFIG_KALLSYMS_ALL` stays on, if `KALLSYMS`, `EXT4_FS`,
`F2FS_FS`, `ANDROID_BINDER_IPC`, `USB_GADGET` or `SCSI_UFSHCD` is off, or if the
USB closure check fails. `report-diagnostic-shortfall.sh` relinks the build into
scratch outside the repository and the build tree and prints the table above.

Contrasting outcomes defined by the issue: **fit** (not reached) would have
required packaging only the payload and gzip header into the stock `boot_a`
prefix with the stock AVB0, vbmeta and AVBf tail unchanged; **shortfall** (this
result) stops with the numbers above. The phone experiment in the issue is not
available because no new image set exists. This does not unblock #12 and leaves
the encrypted-userdata release gate separate.
