---
date: 2026-10-22
issue: omnipha/linux-sm7635#21
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Pre-ramoops marker and pstore panic (#21, host-only, 2026-10-22)

**Single kernel variable:** `configs/asteroids-debug-marker.fragment` is merged
last, after the measured stock command line and the #18 USB closure. It changes
exactly two settings relative to the verified #18 `.config`:

1. `CONFIG_CMDLINE` is the measured stock A059P value with one appended token,
   `sm7635-boot-marker`. With the unchanged `CONFIG_CMDLINE_EXTEND=y`, the
   pinned 6.1.78 `early_init_dt_scan_chosen()` copies `CONFIG_CMDLINE` first
   and then appends the bootloader `bootargs`, so the token ends the built-in
   part of the kernel's effective command line and is printed in the kernel's
   `Kernel command line:` line.
2. `CONFIG_PANIC_TIMEOUT=-1` is restated. It was already `-1` in the stock
   `config.gz` and the #18 build; `kernel/panic.c` initializes `panic_timeout`
   from it, and the `panic=` command-line parameter overrides it. The value is
   therefore present even if the bootloader supplies no `panic=` argument.
   Because it is non-zero, `panic()` reaches `emergency_restart()` without a
   delay instead of staying silent; the kmsg/console dump into the ramoops
   buffer happens before that restart.

**Issue exception — `CONFIG_PSTORE_CONSOLE_SIZE`:** the symbol does not exist
anywhere in the pinned vendor Kconfig tree at
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7` (`fs/pstore/Kconfig` has only
`PSTORE_BLK_CONSOLE_SIZE`, which is a pstore/blk setting and is not selected).
It is also absent from the measured stock `config.gz`. No symbol was added, no
header was redefined and no upstream patch was applied. The 2 MiB console
reservation is instead the stock device-tree value already verified on the #18
chain: after stock DTBO entry 65 is applied to vendor DTB index 9,
`/reserved-memory/ramoops_region` has `reg = <0x0 0x81f20000 0x0 0x400000>`,
`console-size = <0x200000>` and `pmsg-size = <0x200000>`. `fs/pstore/ram.c`
reads `console-size` from that node, so the reservation does not depend on the
missing Kconfig symbol. `CONFIG_PSTORE=y`, `CONFIG_PSTORE_CONSOLE=y` and
`CONFIG_PSTORE_RAM=y` are unchanged.

Nothing else moves. The diff of the #18 `.config` against this build is that
one command-line line. `init_boot.img`, `vendor_boot.img`, the 20 stock DTBs,
the 175-byte bootconfig, both gzip ramdisks and the boot/vendor header command
lines are byte-identical to #18. The boot header command line intentionally
does **not** carry the marker: the marker lives in the kernel so it can only
appear in a console written by this kernel.

| artifact | verified #18 (bytes; SHA-256) | #21 (bytes; SHA-256) |
| --- | --- | --- |
| `.config` | 237,546; `5781d141305c4f27bdc0dd3e69a1136a7e9be3c4fbc538d8b5c11e6f2442cd32` | 237,565; `93acd0920ceadb767625f06a30d992aea0901000e86abec7b61c7e6827f0fa28` |
| `Image` | 41,859,584; `a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29` | 41,859,584; `34fee908da7366f2f174eca4edcc84d732c709067cf81dcba43dfde627dffb13` |
| `Image.gz` | 15,746,316; `9055503e67a1321468fa75608b677eec257c403345a7a6de6709369fb71d5d4a` | 15,746,607; `b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277` |
| `boot.img` | 15,753,216; `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` | 15,753,216; `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| vendor `dtb.img` | 9,419,891; `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` | 9,419,891; **identical** `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| gzip cpio in both ramdisks | 1,672,600; `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` | 1,672,600; **identical** `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The new `boot.img` SHA differs from every previously tested boot
(`5e866c54…`, `84f7f5ea…`, `116b1662…`) and from the untested #16 boot
`1fdc2570…`. Two sequential `scripts/build-bootimg.sh` runs produced the same
SHA set, and `scripts/verify-bootimg.sh` passed on both. The verifier checks
the marker in the fragment, merged config, built `.config` and the IKCONFIG
embedded in the unpacked kernel, checks the NUL-terminated command-line string
inside `Image`, asserts `CONFIG_PANIC_TIMEOUT=-1` and the existing pstore
options, and fails closed if `CONFIG_PSTORE_CONSOLE_SIZE` is either silently
dropped or synthesized while absent from `fs/pstore/Kconfig`. If a future pin
gains the symbol, the same check requires the fragment and the built config to
set it to `2097152`. Every existing geometry, AVB, DTB, ramdisk, recovery and
USB-closure check still passes, including the negative fixtures. Config
comparison against the read-only stock `config.gz`: 5,996 stock and 6,979 built
symbol lines, 5,924 identical, 72 stock-only or changed and 1,055 built-only or
changed. `CONFIG_CMDLINE` now differs from stock by exactly the marker token.

**How a later capture distinguishes kernel entry (contract, not a test
request).** A console is useful only if it is read *before* any later kernel
boot, because the next kernel replaces the ramoops buffer. Parsed marker
counts are the public record; raw pstore stays on the build host.

- **Kernel entry:** the pre-restore console contains the literal token
  `sm7635-boot-marker` (in the `Kernel command line:` line), or the 6.1.78
  banner. The token cannot come from a stock or recovery 6.1.84 session, from
  the boot header or from `vendor_boot`: only this kernel's built-in command
  line carries it. Console text after the banner then localizes the failure.
  `Kernel panic - not syncing` is an early panic; `usb-init` or dropbear
  progress is a later failure. With `panic_timeout` at `-1` a panic restarts
  at once, so the panic text survives only in the ramoops buffer; an
  immediate restart that leaves the buffer intact is expected, and a reset
  with no marker at all still counts as no kernel entry.
- **No kernel entry:** the attempt returns to fastboot or wedges, and the
  pre-restore console is still only the preceding stock or recovery 6.1.84
  session with zero occurrences of `sm7635-boot-marker`. That supports failure
  before this kernel executed, or before it initialized the stock ramoops
  region at `0x81f20000`. It is not, by itself, an AVB accept or reject
  verdict.
- **Invalid:** the console is read only after another kernel has booted. That
  boot can overwrite the attempt buffer, so the absence of the marker then
  proves nothing.

No previously flashed complete set may be repeated. Boots `5e866c54…`,
`84f7f5ea…` and `116b1662…` are burned, and the complete sets that used
`vendor_boot` `bde3a3b3…` or `6078269d…` have failed as wholes. This build
keeps `init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` byte-identical,
which is valid for a host-only artifact; only a physically new `boot.img` SHA
makes a future set new. Whether any slot-A test happens, and the verified
rollback around it, belongs solely to the physical coordinator. No device
operation was performed for #21.
