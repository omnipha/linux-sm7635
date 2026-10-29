---
date: 2026-10-24
issue: omnipha/linux-sm7635#59
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Diagnostic own kernel with EXT4_FS off fits the signed tail (#59, host-only, 2026-10-24)

**Host success: the own 6.1.78 kernel with `CONFIG_KALLSYMS_ALL=n` and
`CONFIG_EXT4_FS=n` gzips to 13,806,454 bytes, 160,906 bytes under the
13,967,360-byte signed-tail bound. The boot image and the init_boot image were
assembled and verified host-only; no device operation was performed.** No adb,
fastboot, USB, flash or userdata operation. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. Every previously
measured SHA stays unreused; all new SHAs below are first measurements.

The named fragment `configs/asteroids-diagnostic-ext4-off.fragment` contains
exactly `CONFIG_EXT4_FS=n`, merged last on top of the delivered #60 baseline
(stock `config.gz` SHA-256
`90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`, the
43-symbol debug-off fragment, the Gunyah and ksyms link fragments, the USB,
pstore and marker fragments, and the #60 `KALLSYMS_ALL`/`NLS` fragment). The
resulting `.config` differs from #60's `.config` (SHA-256
`05c70f1a766c7f2d265dc538363445ae581d158a1e60d93313e0c35a0aa2dfd0`) in exactly
six symbols, `EXT4_FS` and the five symbols selected solely by it:
`EXT4_USE_FOR_EXT2`, `EXT4_FS_POSIX_ACL`, `EXT4_FS_SECURITY` (its sub-options),
`JBD2` and `FS_MBCACHE` (the vendor tree names the meta block cache
`FS_MBCACHE`, not `MBACHE`); all six go `y -> not set`. `CONFIG_KALLSYMS`,
`F2FS_FS`, `ANDROID_BINDER_IPC`, `NLS` and the
`verify-volcano-usb.py config` USB closure are byte-unchanged. The build used
the pinned vendor commit `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, Ubuntu
clang 17.0.6 with `ARCH=arm64 LLVM=-17 LLVM_IAS=1`, and the #55 stock gzip
framing (zlib level 9, header `1f 8b 08 00 00 00 00 00 02 03`).

| quantity | bytes |
| --- | ---: |
| #55 `Image-stock-config` | 37,198,336 |
| #60 `Image-diagnostic-kallsyms-nls` | 36,018,688 |
| #59 `Image-diagnostic-ext4` | 34,986,496 |
| #55 gzip payload | 14,782,792 |
| #60 gzip payload | 14,236,242 |
| #59 gzip payload | 13,806,454 |
| signed-tail bound | 13,967,360 |
| under bound | 160,906 |

Per-symbol measured deltas: `KALLSYMS_ALL=n` measured -546,550 gzip bytes (#60);
`EXT4_FS=n` (with `EXT4_USE_FOR_EXT2`, `EXT4_FS_POSIX_ACL`, `EXT4_FS_SECURITY`,
`JBD2`, `FS_MBCACHE`) measured -429,788 gzip bytes this issue (14,236,242 ->
13,806,454; #57 zero-mask estimate 329,690, so the estimate was 99,098 bytes
conservative). The #57 estimate excluded second-order kallsyms/BTF shrink,
which the measured rebuild includes. `F2FS_FS` (estimate 275,810) was not
needed and stays on.

`scripts/build-diagnostic-signed-tail-payload.py` assembles the boot image in
the measured stock signed-tail layout: a copy of stock `boot_a` (SHA-256
`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`) in which
only the v4 header `kernel_size` field changes (13,949,926 -> 13,806,454), the
gzip payload plus its header replaces the stock kernel payload at offset 4096,
the padding window [13,810,550, 13,955,072) is filled with 144,522 zero bytes,
and every byte from the stock separate 16 KiB `AVB0` record at 13,955,072
through the embedded 2,496-byte signed `AVB0` vbmeta block at 13,971,456 and
the terminal 64-byte `AVBf` footer is byte-identical to stock; 100,663,296-byte
image.

`scripts/verify-diagnostic-signed-tail.py` fails closed: it pins the #60
`.config` reference, re-derives the exact six-symbol config delta, runs the
`verify-volcano-usb.py` config closure, re-decompresses and re-compresses the
payload (stock framing, deterministic level 9), matches the embedded
`IKCONFIG_ST..IKCONFIG_ED` blob against the built config, requires the image to
equal `assemble(stock, payload)` (header field, payload, padding, unchanged
stock tail), and rejects the candidate and payload SHA against every previously
measured SHA (all of `9f89fe8d`, `995aaca3`, `88c93077`, `8f8b7331`,
`55fa78ca`, `5a513998`, `dc990b95`, `13a48ff9`, `37535dd1`, `bde3a3b3`,
`6078269d`, stock `197aff11` and the older line). Its self-test mutates a
header byte, a payload byte, a padding byte, the `AVB0` record, the vbmeta
block and the `AVBf` footer (each rejected), flips `F2FS_FS` off in the config
(rejected) and proves every required prior SHA is rejected.

Artifacts stay under `$WORK/out` and are not committed:

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `Image-diagnostic-ext4` | 34,986,496 | `7be448b91b618cbe1dbda9659dfeeb2d554f702091c39453bfa44497c280377e` |
| `Image-diagnostic-ext4.gz` | 13,806,454 | `d259b744465eb48b2c42ddcedcf89f6d2608638c6b04f3c2c534fa27b66d7738` |
| `.config-diagnostic-ext4` | 225,429 | `c6d8a4e86301d314adc8724b7b3d985d81b9cff2074e0e917ed976a46df3ebd9` |
| `boot-diagnostic-ext4.img` | 100,663,296 | `0ca048d554857b469aadf6a55e6fd70cc1cb51cd72eff8f6f98e451bb595f72b` |
| `init_boot-kernel-banner.img` | 8,388,608 | `cafcabb67a1d79f7877b59a1daff25d92fd8fc6ecb5d5128f44ab8cc17af541c` |

`scripts/build-init-boot-kernel-banner.sh` rebuilds the init_boot image from
the #53 static-address line: the frozen #53 init (`initramfs/init`, SHA-256
`ab2377a6ea4f852e03a24056e4087977f6d9d4c8019868c55e4d552e7b97d05b`, unchanged
in the repository) plus exactly one added diagnostic log line after
`log 'starting'`:
`log "kernel banner: $(uname -r 2>&1) $(/bin/busybox cat /proc/version 2>&1)"`,
so pstore can prove which kernel ran. The 127-module order and list (SHA-256
`4f0e151d…`), single peripheral write, 40x0.25 s UDC wait, 150 s `/run/keep`
timer, `bin/restart2` helper, NCM+ECM functions, key-only sshd, gzip cpio
source and the stock signed tail from offset 2,121,728 are unchanged. The
ramdisk is one Android LZ4 legacy HC-12 block (1,931,151 bytes) of the 3,489,792
-byte debug cpio (zero `.ko`). Two consecutive builds are byte-identical.
`scripts/verify-init-boot-kernel-banner.py` requires the embedded init to be
exactly frozen-#53-plus-that-one-line (a stripped init must pass the full #53
checker and equal the frozen bytes), proves the reproducible builder output,
and rejects every prior SHA; its self-test rejects a removed (which rebuilds
the measured #53 image `995aaca3` and is caught by the SHA guard), duplicated,
moved or reworded banner, a second diagnostic line, a changed module order, a
second role write, a changed gadget function, a removed address log, a timer
change, a planted `.ko`, and envelope, header, block, gap and tail corruptions.

`scripts/verify-bootimg.sh` now also unpacks both new images and runs
`verify-volcano-usb.py board` with the diagnostic config against the new
kernel's embedded IKCONFIG (the LZ4 ramdisk is decoded and gzip-wrapped for the
zero-`.ko` check against the stock board DTB), runs both new fail-closed
verifiers with self-tests, and records both images in the artifact SHA-256
table. Full aggregate run: pass (both `Volcano DTB: ... 22 resolved suppliers;
built-in closure OK` lines, all negative fixtures).

Command sequence (one build at a time, host only):

```sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-kallsyms-nls.sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-ext4.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-kernel-banner.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

The device experiment in the issue (flash `boot_a` with the new own-kernel
image plus the marker init_boot, distinct SHA set) belongs to the physical
coordinator under `full_autonomy_device_iteration`, not to this host-only
delivery. This does not unblock #12 and leaves the encrypted-userdata release
gate separate.
