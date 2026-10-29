---
date: 2026-10-21
issue: omnipha/linux-sm7635#18
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Recovery-path boundary after #18 (`attempt-20261021-1717`, host-only, 2026-10-21)

**Observed:** The physical coordinator flashed the #18 single-variable slot-A
chain (`boot_a` `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce`,
`init_boot_a` `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89`,
`vendor_boot_a` `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d`;
all three writes OKAY). After `fastboot reboot` at 17:53:57+02:00, host USB
disconnected and re-enumerated as fastboot `18d1:d00d` within four seconds
(17:54:01) and stayed there through all 45 observations (225s) with no
`18d1:4ee2` gadget, adb or SSH. At 17:59:24, `fastboot reboot recovery` was
issued *while the test chain remained on slot A*; it also returned to fastboot
`18d1:d00d` within four seconds (17:59:28) and remained there for all 12
samples (60s). After restoring stock `boot_a`, `init_boot_a` and `vendor_boot_a`
(18:03:35-18:03:44), the identical `fastboot reboot recovery` succeeded
(`adb` recovery at 18:04:16). On-device block SHA-256 reads in recovery
matched the verified stock backups for `boot_a` (`197aff11…06d4d`),
`init_boot_a` (`baa33fd4…1e3193`), `vendor_boot_a` (`23725940…c1253`), and
unchanged `dtbo_a` (`759813db…e13c992`) and `vbmeta_a` (`cc1926d2…cdffe`);
stock Android then reached `sys.boot_completed=1`. Host-only logs are at
`~/phone-second-life-data/mb003/pstore/attempt-20261021-1717/`.

**Recovery partition resolution and pstore provenance (measured, not inferred):**
`scripts/verify-recovery-boundary.py` (invoked by `scripts/verify-bootimg.sh`)
checks `recovery_a.img` (`0c6767698ebb069064b450b109cde6a1172b478e30000fe852e7d9bc19dbae9e`,
byte-identical to `OrangeFox-R12.0_6.1-Unofficial-Asteroids.img`) and
`recovery_b.img` (`6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b`).
Both are 100 MiB Android boot-header v4 images with **`kernel_size = 0`** and
legacy LZ4-compressed `070701` newc ramdisks at offset 4,096 (`48,350,666` and
`15,609,526` bytes), no DTB and no bootconfig, plus AVBf footers at `48,357,376`
and `15,613,952` (`RSA4096_SHA256`, `flags = 0`, `rollback_index = 1`;
`recovery_b`'s public key matches `vbmeta_a`'s `recovery` chain descriptor at
rollback location 1, while `recovery_a`'s self-signed key differs). Neither
`recovery` partition contains a kernel or DTB: on this header-v4 layout,
booting recovery **requires** the kernel from `boot_a` and the DTB/bootconfig
from `vendor_boot_a`. Every captured recovery-session console (`0134`, `0550`,
`0640`, `1156`) logs `Freeing initrd memory: 57900K` (`59,289,600` bytes =
4 KiB-aligned sum of `8,821,389`-byte `vendor_boot_a` PLATFORM ramdisk +
`2,113,581`-byte `init_boot_a` generic ramdisk + `48,350,666`-byte OrangeFox
`recovery_a` ramdisk + bootconfig = `59,285,811` bytes), whereas normal
Android boot (`1717` and `2026-10-19`) logs `Freeing initrd memory: 10680K`
(`10,936,320` bytes = 4 KiB-aligned sum of `vendor_boot_a` + `init_boot_a` +
bootconfig = `10,935,145` bytes). Therefore:

1. Neither conflicted note was wholly accurate: recovery does **not** run from
   `recovery_a` + `vendor_boot_a` without `boot_a` (`recovery_a` has no kernel),
   and it does **not** use `boot_a` only for a hardware-key menu. On `A059P`,
   ABL's recovery boot path loads `boot_a` (kernel) + `vendor_boot_a` (PLATFORM
   ramdisk, DTB index 9, bootconfig) + `init_boot_a` (generic ramdisk) +
   `recovery_a` (OrangeFox ramdisk appended last, overriding `/init`). Because
   all three flashed slot-A partitions (`boot_a`, `init_boot_a`, `vendor_boot_a`)
   are consumed by both normal boot and `fastboot reboot recovery`, and all
   three were restored together at 18:03:35-18:03:44 before recovery succeeded,
   stage 6 (`fastboot reboot recovery` failing in 4s on the test chain) proves
   the failure is **not** specific to normal-boot userspace or Android-mode
   bootconfig, while keeping all three modified slot-A partitions inside the
   candidate boundary.
2. Why `attempt-20261021-1717` `pstore` differs from `0134`/`0640`/`1156` (and
   why `ramoops` exposes the *previous* boot): Linux `pstore/ramoops` exposes
    the buffer saved by the **previous** kernel session in `/sys/fs/pstore`
   while writing the **current** session's console to the live ring buffer for
   the *next* boot.    In `0134`, `0640` and `1156`, a pre-flash recovery session was booted to
   hash slot-A partitions just before `reboot bootloader`; its `57900K`-initrd
   recovery log (`37.6s`, `35.5s` and `1402.9s` uptime respectively, each
   ending at `Reboot start, reason: reboot,bootloader` immediately before the
   test flash) remained in `ramoops` across the failed test reboot and was read
   back by the post-restore recovery boot. In `1717`, there was **no**
   pre-flash recovery boot: the phone rebooted directly from the ~2.4h stock
   Android session (`10680K` initrd, `Load bootconfig: 1279 bytes 80 nodes`,
   `sys.boot_completed=1` at `[17.764152]`, ending at `[8764.401407]
   BATTERY_CHG: battery_shut_down`) into fastboot at 17:53:22, failed the
   17:53:57 normal test reboot (4s to `18d1:d00d`) and the 17:59:24 test-chain
   recovery reboot (4s to `18d1:d00d`), and then booted stock recovery at
   18:03:44, which mounted `/sys/fs/pstore` and pulled that **intact
   pre-attempt Android console** (`1,073,964` bytes) and `pmsg` (`4,973` bytes).
   **Consequence:** across **all four** attempts (`0134`, `0640`, `1156`,
   `1717`), the post-restore recovery boot did **not** overwrite the attempt
   window before `/sys/fs/pstore` was read — rather, none of the four normal
   test reboots (nor the `1717` stage-6 test-recovery reboot) ever initialized
   or wrote to `ramoops` at `0x81f20000` (which happens at `~0.068s` on stock).
   That proves every tested chain failed **either** before kernel hand-off (in
   XBL/ABL) **or** before the test kernel could initialize and write to that
   `ramoops` reservation.
3. Host xHCI USB enumeration timing (`journalctl -k` on the build/test host)
   across all five failed reboots (`0134` at 01:34:16, `0640` at 06:44:34,
   `1156` at 12:22:09, `1717` normal at 17:53:57, `1717` stage-6 recovery at
   17:59:24) shows a **single** reset cycle (`USB disconnect` at `t = 0s`,
   full-speed `t = +1..2s`, high-speed `18d1:d00d` fastboot at `t = +4.0s`),
   matching the `4.0–5.0s` timing of a direct `adb reboot bootloader` entry into
   ABL (`0640` 06:44:12 -> 06:44:17, `1156` 12:21:35 -> 12:21:39, `1717`
   17:53:22 -> 17:53:27) with no intermediate second reset. This is strongly
   consistent with synchronous ABL rejection into fastboot within the same boot
   cycle, though an immediate post-jump reset before `ramoops` cannot be ruled
   out by USB timing alone.

| tested slot-A chain | `boot_a` / `init_boot_a` / `vendor_boot_a` SHA-256 prefixes | single variable changed | observed normal + recovery result |
| --- | --- | --- | --- |
| #8 (`0134`) | `5e866c54…` / `f4b987ee…` / `bde3a3b3…` | initial 3-image SSH set (built DTBs, duplicate boot ramdisk) | `<5s` return to `18d1:d00d`; no gadget/adb/SSH |
| #10 (`0640`) | `5e866c54…` / `f4b987ee…` / `6078269d…` | `vendor_boot_a`: stock 20-DTB blob (DTBO 65 applies to index 9) | `<5s` return to `18d1:d00d`; not sole cause |
| #14 (`1156`) | `84f7f5ea…` / `f4b987ee…` / `6078269d…` | `boot_a`: stock `CONFIG_CMDLINE` override (no `panic_on_taint`) | `<5s` return to `18d1:d00d`; not sole cause |
| #16 (untested) | `1fdc2570…` / `f4b987ee…` / `6078269d…` | `boot_a`: `ramdisk_size = 0` (generic ramdisk only in `init_boot_a`) | not physically flashed alone; carried into #18 |
| #18 (`1717`) | `116b1662…` / `f4b987ee…` / `6078269d…` | `boot_a`: `#16` empty boot ramdisk + built-in Volcano USB closure | `<5s` return to `18d1:d00d` on both `reboot` and `reboot recovery` |

**Plain non-discrimination statement and exact blocker (#12 Acceptance 2):**
Across all four physical attempts, `init_boot_a` `f4b987ee…`, `vendor_boot_a`
`6078269d…` (after #8), `dtbo_a` and `vbmeta_a` (with `flags = 0` and stock
hash/chain descriptors that none of the unsigned, footerless test images match)
stayed constant, and targeted `getvar` recorded only `serialno`,
`current-slot: a`, `unlocked: yes` and `product: pineapple` (`getvar all` is
not used because it wedged fastboot on `0332`/`0535`). Host-only evidence
**cannot** discriminate between:

- **Regime 1 — Bootloader/AVB or header-format rejection before kernel hand-off:**
  ABL rejects unsigned/footerless `boot_a` and/or `vendor_boot_a` against stock
  `vbmeta_a` (`flags = 0`), or rejects `vendor_boot_a`'s gzip PLATFORM ramdisk /
  unpadded size during both normal and recovery boot.
- **Regime 2 — Pre-`ramoops` kernel failure:**
  ABL hands off to the 6.1.78 `Image.gz` in `boot_a`, which resets before
  `ramoops` initializes at `0x81f20000`. The preserved pre-attempt Android
  console and ~4s return do not rule this out, but the absence of a second
  host USB reset is less consistent with a kernel-triggered restart (which
  normally produces a second disconnect/re-enumeration). No 6.1.78 marker is
  required for this regime. `~0.068s` is stock kernel's observed probe time,
  not a measured upper bound for the test kernel.
- **Regime 3 — Later kernel/init/USB failure:**
  Incompatible with this attempt-specific evidence **if** the 6.1.78 kernel
  actually initialized the same `ramoops` reservation: any subsequent
  console writes should replace the pre-attempt Android console. The host
  verifies DTBO 65 applies to vendor DTB index 9 and supplies
  `0x400000@0x81f20000`; it cannot prove that the kernel reached the driver,
  that ABL passed this DTB, or that the persistent region survived a power
  reset. A late failure with `ramoops` absent/never mounted remains an
  alternative, not a proven rejection verdict.

No new kernel/ramdisk/boot-image build is produced for #12: building another
unauthenticated `{boot_a, init_boot_a, vendor_boot_a}` perturbation without
isolating `{boot_a}` vs `{vendor_boot_a}` vs `vbmeta_a` would be a speculative
blind flash. The **exact blocker** is that neither the 17:53:57 nor 17:59:24
attempt has an ABL AVB accept/reject verdict, boot reason/retry status, or an
attempt-tagged pre-rollback pstore capture. The only captured `getvar` values
were identity, slot, unlocked state and product; an earlier `getvar all`
wedge means it is not a supported fallback. Stock rollback changed all three
slot-A partitions together, so it cannot isolate the kernel-bearing `boot_a`
from the DTB/bootconfig-bearing `vendor_boot_a`. The latter is a **controlled
constant** (`6078269d…`) in the failed #10/#14/#18 sets; those complete SHA
sets must not be repeated. A signed replacement for `vbmeta_a`/`dtbo_a` is
outside the existing slot-A-only approval, and a stock `vbmeta_a` mismatch is
not a verdict on an unlocked/orange device. In particular, the OrangeFox
`recovery_a` key differs from `vbmeta_a`'s recovery chain key, yet recovery
worked after stock rollback; the logs do not prove whether recovery loaded
`recovery_a` or `recovery_b`, so this cannot establish an AVB exception for
the normal boot path.

**Single selected discriminator (measurement, not a new flash plan):** an
attempt-tagged **first bootloader-side hand-off verdict** with partition name
and AVB/retry reason, collected *before* any stock/recovery boot, would directly
separate pre-kernel rejection from kernel entry. An explicit *reject* of
`boot_a` or `vendor_boot_a` proves regime 1. An explicit *accept* without a
6.1.78 marker still leaves regime 2 and loss of the ramoops channel possible.
A 6.1.78 kernel banner/progress marker in a pre-restore capture proves kernel
entry and distinguishes regime 2 if it stops before `/init`, versus regime 3
if `usb-init`/`dropbear` markers precede the failure. The 1717 record already
supplies an attempt-specific **upper bound**: the test kernel did not write to
`ramoops` during either failed window, while no post-test stock/recovery boot
had yet modified the saved pre-attempt Android console. No currently preserved bootloader-side verdict or supported narrow read-only
AVB/reason/retry channel exists; an earlier `getvar all` wedged fastboot.
Thus the remaining boundary between ABL rejection and pre-`ramoops` kernel
failure and the minimal corrective artifact are **unproven**. The exact remaining blocker is a supported,
bounded, attempt-tagged read-only ABL hand-off/verdict channel on slot A,
**before** any recovery boot or stock rollback; a serial/bootloader log
interface is not established from these host records and must not be guessed.
The strategist/coordinator owns any future measurement decision under the
existing slot-A-only boundary and must not repeat a failed full SHA set;
writing `vbmeta_a`/`dtbo_a` needs separate approval and is not a staged
artifact here. This document does not request any physical operation.
Verified stock rollback for the historical attempt was already measured on
all three restored partitions plus unchanged `dtbo_a`/`vbmeta_a`; only the
physical coordinator owns that boundary. The release-image userdata decision
is independent.
