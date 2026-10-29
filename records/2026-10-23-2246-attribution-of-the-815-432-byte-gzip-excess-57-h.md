---
date: 2026-10-23
issue: omnipha/linux-sm7635#57
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Attribution of the 815,432-byte gzip excess (#57, host-only, 2026-10-23)

**Host analysis only. The not-required set can reach the excess; this does not
change the shipped configuration or build an image.** No device, adb, fastboot,
USB, flash or userdata operation was performed. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. No SHA is recorded
and every previously measured SHA stays unreused.

`scripts/analyze-gzip-excess.sh` reads the existing #55 build
(`Image-stock-config` 37,198,336 bytes, `Image-stock-config.gz` 14,782,792
bytes, signed-tail bound 13,967,360 bytes) and reproduces the payload
bit-exactly with zlib level 9 and the fixed stock framing. It relinks the same
inputs into scratch, outside the repository and the build tree. The replay
differs in 20 bytes, all inside the `.notes` build-id. A linker map covers
37,034,789 of the 37,198,336 loaded bytes; the remaining 163,547 bytes are
alignment and linker-script gaps. Decoding the deflate stream attributes
14,713,067 payload bytes to image bytes; 69,707 bytes are deflate block-header
overhead and are not attributed to a group.

The largest in-stream groups are `.BTF` (5,777,934 raw, 1,849,539 gzip),
kallsyms (2,374,536 raw, 1,173,632 in-stream), `.eh_frame` (3,058,212 raw,
731,335 gzip), then `drivers/usb` (527,505), merged strings, `arch/arm64`,
`net/ipv4`, `net/core`, ext4, f2fs and NLS. The script writes the full
per-section, per-directory and per-object tables, plus a classification of
every directory, into its scratch directory. They are generated from the build
tree and are not committed.

The classification uses the USB built-in closure, the symbols evidenced by
`initramfs/init`, the undefined symbols of the 127 stock vendor modules the
measured init loads, and whether an object is referenced from outside its own
group. A directory is required when it contains an object gated by a closure
symbol or one that exports a symbol imported by those modules; that marks the
directory as not wholly removable, not every byte inside it as needed. On that
basis `drivers/usb`, `arch/arm64`, `net/ipv4`, `net/core`, `drivers/hid`,
`drivers/base`, `kernel/sched`, `kernel/trace` and `drivers/clk` are required.
Generated tables are unknown because only part of them is attributable.
`ARM_SCMI_PROTOCOL` is the one candidate that is required outright: the 127
modules import four symbols defined only there. `DEBUG_INFO_BTF` and
`UNWIND_TABLES` stay unknown: all 127 modules carry both `.BTF` and
`.eh_frame`, and the effect of dropping the matching vmlinux data was not
measured. `MEDIA_SUPPORT`, `NLS` and `ZSTD_COMPRESS` stay selected by other
stock options, and DRM, sound, KVM, netfilter, traffic control, IPv6 and BPF
are referenced from objects outside their own directories, so none of those is
counted as removable.

The not-required set is `KALLSYMS_ALL`, `EXT4_FS`, `F2FS_FS` and
`ANDROID_BINDER_IPC`. `KALLSYMS_ALL` is not the whole kallsyms table:
regenerating the #55 symbol list without `--all-symbols` keeps the text
symbols and removes 1,189,640 of 2,374,536 `.rodata` bytes, estimated at
546,197 gzip bytes. The other three are zero-masked recompressions of the
exact map bytes: ext4 with its jbd2 and mbcache dependency at 329,690, f2fs at
275,810 and binder at 57,422. Disabling all four together turns off no closure
symbol. Their individual estimates sum to 1,209,119 bytes and the joint
estimate is 1,210,916 bytes, which is 395,484 bytes above the 815,432-byte
excess. These are recompression estimates, not a rebuilt kernel: they do not
include the second-order kallsyms, BTF and relocation changes a real rebuild
would make. "Not required" means not required by the USB/SSH closure and the
measured own-init only. Any later userdata mount (f2fs, ext4) or Android
userspace (binder) would need these symbols; that use is outside this
measurement and untouched here. Choosing whether to drop any of them is a
separate decision for the owner or coordinator.
