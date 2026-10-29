---
date: 2026-10-24
run: 27
issue: omnipha/linux-sm7635#69
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## WLAN rfkill and firmware mounts on the corrected run-27 init (#69, host-only, 2026-10-24)

**Host success: one corrected wlan-init stage fixes the measured run-27 mount
failures and packages one distinct, reproducible stock-envelope init_boot.**
No device, adb, fastboot, USB, flash or userdata operation was performed. No
kernel, vbmeta, dtbo or slot-B artifact changed. The 127-module order, one
peripheral write, UDC wait, NCM+ECM addresses, key-only sshd, 150 s `/run/keep`
timer and `bin/restart2` are unchanged.

### 1. Run-27 evidence and source determination

Run 27 (`attempt-20261024-0836-initboot-wlanclosure`, image `2faab7e2…`) mounted
`vendor_dlkm_a` read-only EROFS and loaded 18 of 21 closure modules, with SSH
held. It then logged `mount vendor_a read-only: failed` and `mount
system_dlkm_a read-only: failed`, followed by `rfkill.ko failed: missing …`.
The stock cmdline contains `loop.max_part=7`, so each loop device consumes eight
minors. The old init created `/dev/loop8`, `/dev/loop9` and `/dev/loop10` with
minor equal to index. Device 8 aliased loop1, while 9 and 10 hit loop1 partition
slots, explaining the two failures. The measured by-name table places `super` on
`/dev/block/sda6` and `modem_a` on `/dev/block/sde6`; it has no `vendor_a` or
`system_dlkm_a` entries. Primary LP metadata confirms both missing filesystems
are linear extents inside that one super device:

| source | block device | byte offset | bytes | probed type |
| --- | --- | ---: | ---: | --- |
| `system_dlkm_a` | super `/dev/block/sda6` | 4,797,235,200 | 11,804,672 | erofs |
| `vendor_a` | super `/dev/block/sda6` | 5,678,039,040 | 1,269,284,864 | erofs |
| `vendor_dlkm_a` | super `/dev/block/sda6` | 6,947,864,576 | 32,669,696 | erofs |
| firmware | by-name `modem_a` `/dev/block/sde6` | whole partition | measured stock partition | vfat |

Host read-only mounts of the pinned super dump verify all three extents as
erofs. `system_dlkm_a` contains `rfkill.ko` (63,817 bytes, SHA-256
`773ddddb360d8de4212da9a327124e97f5b8fe94626a82e44fdcfb689adabb47`). `vendor_a`
does not contain `bdwlan.elf`; its `firmware_mnt` entry is a mountpoint. The
stock recovery command mounts by-name `modem_a` read-only vfat at
`/vendor/firmware_mnt`, which is the stock path
`/vendor/firmware_mnt/image/qca6750/bdwlan.elf`. No second super loop is used.

### 2. The single wlan-init change

The frozen run-24 init and the existing 21-module closure order remain. The
stage now:

1. derives each loop node's major:minor from `/sys/block/loopN/dev`, rather than
   guessing minor equals index;
2. probes each super extent (erofs magic `e2e1f5e0` at byte 1024, otherwise ext4
   magic `53ef` at byte 1080, otherwise skips) and mounts `system_dlkm_a`,
   `vendor_a` and `vendor_dlkm_a` read-only with matching options;
3. probes by-name `sde6` for `PARTNAME=modem_a` and a FAT signature, then mounts
   it read-only vfat at `/vendor/firmware_mnt` and logs whether
   `qca6750/bdwlan.elf` is present;
4. `insmod`s `rfkill.ko` from the pinned system_dlkm path before `cfg80211.ko`,
   then keeps the existing closure, per-module results, wlan interface check,
   capped wlan dmesg and firmware-name log.

No `.ko` enters init_boot. The 150 s timer is unchanged.

### 3. The image

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `init_boot-wlan-rfkill.img` | 8,388,608 | `9291c369ec78b081c6445b3ee85431fa9a01e2e757a59337cfd165eca741c2f3` |

The image keeps the stock prefix apart from ramdisk size, carries one LZ4 HC-12
legacy frame (1,933,841 bytes) of the 3,496,960-byte debug cpio (SHA-256
`9f1bf645…a6db`) at offset 4096, a zero gap and the unchanged signed tail from
offset 2,121,728. Two consecutive builds are byte-identical. This SHA differs
from `2faab7e2`, `995aaca3`, `be946562`, `86402ac6`, `9f89fe8d`, `88c93077`,
`8f8b7331` and every earlier measured image.

`scripts/verify-init-boot-wlan-rfkill.py` fails closed. Negative fixtures reject
the run-27 minor guess, an assumed filesystem, a removed mount, a second super
loop, rfkill from the wrong partition, rfkill absent, cfg80211 before rfkill,
an unprobed or moved firmware mount, a planted `.ko`, timer changes, marker
changes, envelope or tail damage, and every repeated prior SHA including
`2faab7e2`. `scripts/verify-bootimg.sh` runs it. `bash -n`, `shellcheck`,
`python3 -m py_compile` and `git diff --check` are clean.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wlan-rfkill.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

Physical measurement of this new SHA is owned solely by the physical
coordinator under the standing `full_autonomy_device_iteration` approval:
`init_boot_a` only, host pins `172.16.42.1/24` first, then verified rollback.
