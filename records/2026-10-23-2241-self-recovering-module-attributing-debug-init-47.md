---
date: 2026-10-23
issue: omnipha/linux-sm7635#47
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Self-recovering, module-attributing debug init (#47, host-only, 2026-10-23)

**Host-only image, not a boot result.** No device, flash, USB or userdata
operation was performed. The stock 6.1.84 kernel and `boot_a`, `vendor_boot_a`,
`dtbo`, `vbmeta` and slot B are unchanged, and the #44 module closure is
unchanged. The one new image is `$WORK/out/init_boot-self-recovering.img`
(8,388,608 bytes, SHA-256
`8f8b733150abc89f5e1769a85bac25583bafd9c8028986c6ae50ba7034c056dd`).
It differs from the measured `cdb9458f…`, `3932504a…`, `f4a00ce3…`, stock
`baa33fd4…` and every earlier measured SHA. Never reflash those earlier images.

The attempt-20 pstore of the #44 image was read before this image was built.
It shows `Run /init as init process`, all 126 `usb-init: module <name> loaded`
lines in the closure order, `usb-init: module load end` at 1.06 s, `udc names:
none`, `no UDC; USB gadget not bound`, exactly 7 deferred-probe entries (the
`a600000.ssusb` entry waits on `88e0000.qcom,msm-eud`) and `console ready`. No
module failed and none hung, so the module list is unchanged from #44 and its
newline-delimited list keeps SHA-256
`57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08`.

 `initramfs/init` is the #44 init, kept byte-for-byte as
 `initramfs/init-44-vendor-modules`, plus exactly three additions and nothing
 removed. The #44 image builder and verifier read the frozen copy, so the
 measured `cdb9458f…` image still rebuilds unchanged.
 Before each `insmod` it logs `usb-init: loading <name>`, so a hang names the
module that did not return. After the module phase and before the UDC wait it
logs whether the `qcom-reboot-reason` platform driver has bound, reported as
`usb-init: qcom-reboot-reason bound` or `usb-init: qcom-reboot-reason not
bound`. Right after `usb-init: starting` it starts a subshell that sleeps 150 s
and then, unless `/run/keep` exists, logs `usb-init: self-recovery ->
bootloader` and calls `/bin/restart2 bootloader`. If that call returns it logs
`usb-init: self-recovery RESTART2 failed; falling back to reboot -f` and runs
BusyBox `reboot -f`. The subshell is backgrounded before the module loop, so a
blocked `insmod` cannot stop it, and a reachable operator disables it with
`touch /run/keep`. The module sequence, the 10 s UDC wait and the gadget and
sshd path are otherwise byte-for-byte the #44 init.

The 150 s budget covers the measured attempt-20 behaviour with margin: the
closure finished in about 1 s and the UDC wait adds 10 s, and the budget stays
far below the 180 s observation window the physical measurement uses. It is a
fixed `sleep`, not a watchdog, so it fires even if init is wedged in one
`insmod`.

`/bin/restart2` is the only new binary. It is a freestanding static aarch64
ELF, built reproducibly from the committed `initramfs/restart2.c` with
`aarch64-linux-gnu-gcc -nostdlib -static` and no dynamic interpreter. It issues
`reboot(2)` with `LINUX_REBOOT_CMD_RESTART2` and accepts only `bootloader` and
`recovery`, so `qcom-reboot-reason` can store the matching PON reason. BusyBox
`reboot` passes no command string and cannot do this. The helper is 872 bytes,
SHA-256
`fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7`; its source
is SHA-256
`6806922e9e5138df25ee13e5f11d4fad555479830436e283b040b6e666133f96`.

The builder reuses the verified debug gzip `caa3eb82…` as a source cpio and
changes only `/init` and the added `bin/restart2`. The resulting 3,485,696-byte
newc carries zero `.ko` and hashes to
`71eae6972aeac3b5be7a5086f8560665719e84133496b23d77a6b034477c3793`.
Stock LZ4 HC level 12 makes one 1,929,803-byte block (1,929,811-byte legacy
frame) at offset 4,096, inside the 2,117,632 bytes before the signed tail. Only
header field `ramdisk_size@12` changes, from 2,113,581 to 1,929,811; the
187,821-byte gap to offset 2,121,728 is zero; all 6,266,880 bytes from the
signed `AVB0` block through the `AVBf` footer are unchanged. The candidate uses
no new kernel, is not signed, and claims no AVB, ABL or device verdict.

`scripts/build-init-boot-self-recovering.sh` produced two byte-identical
candidate runs and kept one image outside Git. `scripts/verify-bootimg.sh`
passed, including the #44 closure-list SHA, the zero-`.ko` check and negative
fixtures that reject an init with no timer, a timer inside or after the module
loop, a timer that ignores `/run/keep`, a missing loading marker, a marker that
follows `insmod`, a removed bind check, a reordered module list, a missing
helper, a helper with an interpreter, a non-aarch64 helper, an altered or
truncated helper, a planted `.ko`, a modified header or signed tail and every
repeated prior SHA, including `cdb9458f…`, `3932504a…`, `f4a00ce3…` and
`baa33fd4…`. `bash -n`, `shellcheck` and `git diff --check` pass. The only next
physical step belongs to the human coordinator under the standing mission-shift
approval; repository work neither performs nor authorizes a flash. This leaves
#12 and the encrypted-userdata release gate untouched.

A later measurement of this one image, flashed only to `init_boot_a` with stock
`boot_a` and `vendor_boot_a` untouched, and observed for at least 180 s before
any button press, distinguishes four outcomes. None is claimed here.

- **Fastboot at about 150 s, pstore shows `loading` and `loaded` lines through
  the end.** Init ran, the closure is readable module by module, and the
  UDC/gadget question is answered from pstore. Later init experiments can rely
  on the same recovery.
- **Fastboot, pstore ends at `loading X`.** Module X hung or crashed the kernel
  path. That module is the blocker, not USB.
- **Own init runs again, pstore shows `qcom-reboot-reason not bound`.** The
  bootloader reason is not honored from this init. The next question is the
  SDAM/PMIC provider chain, and the fallback command has to change, for example
  to `recovery`.
- **No reaction at all.** The kernel hung before the timer could matter. The
  next question is panic and watchdog behaviour on the kernel command line, not
  init.
