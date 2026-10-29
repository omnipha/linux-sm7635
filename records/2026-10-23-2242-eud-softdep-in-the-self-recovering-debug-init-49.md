---
date: 2026-10-23
issue: omnipha/linux-sm7635#49
subsystem: usb
result: inconclusive
source: BOOT.md
---
## EUD softdep in the self-recovering debug init (#49, host-only, 2026-10-23)

**Host-only image, not a boot result.** No device, flash, USB or userdata
operation was performed. The stock 6.1.84 kernel and `boot_a`, `vendor_boot_a`,
`dtbo`, `vbmeta` and slot B are unchanged. The one new image is
`$WORK/out/init_boot-eud-softdep.img` (8,388,608 bytes, SHA-256
`88c93077d5079d4dc81ce723299faab756bf5b52a5af8ebe99c84f68ea9ae0aa`).
It differs from the measured `8f8b7331…`, `cdb9458f…`, `3932504a…`, `f4a00ce3…`,
stock `baa33fd4…`, both vendor_boot sets (`bde3a3b3…`, `6078269d…`) and every
earlier measured SHA. Never reflash those earlier images.

The attempt-21 pstore of the #47 image was read before this image was built.
It shows own `/init`, all 126 modules loaded before 1 s, `qcom-reboot-reason
bound`, `udc names: none` at about 11 s and `a600000.ssusb` deferred. The host
saw no USB network or SSH, and the device returned to fastboot at about 166 s
without a button press. The late timer marker did not survive pstore, so the
150 s path is consistent with the return but not directly proven.

The stock vendor `modules.softdep` says `softdep dwc3_msm pre: phy-generic
phy-msm-snps-hs phy-msm-ssusb-qmp eud`. The #44 closure calculator silently
skipped a softdep target that was not itself in the closure, which dropped
`eud.ko` even though it is present in the vendor ramdisk and named by
`modules.load.recovery`. Its `modules.dep` prerequisites are all already in the
126-module closure. Two other softdep targets, `qcom_tlmm_vm_irqchip` and
`phy_msm_snps_hs`, have no `.ko` in the vendor ramdisk and no enabled driver in
the stock `config.gz`; the new calculator accepts exactly those two as
unavailable and rejects any other unresolved target. `eud.ko` is checked to be
an aarch64 ELF with no prerequisite outside the old closure.

`initramfs/init` is the #47 init, kept byte-for-byte as
`initramfs/init-47-self-recovering`, plus exactly two additions and nothing
removed. The #47 image builder and verifier read the frozen copy, so the
measured `8f8b7331…` image still rebuilds unchanged. The module list inserts
`eud.ko` immediately before `dwc3-msm.ko` and changes nothing else, so the old
126 modules keep their order and SHA-256
`57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08`; the new
127-line list is SHA-256
`4f0e151da8a68339d34d7596d73e77f95415faa79b741aaa425572c1fa7caf69`.
The single existing `insmod` loop loads it. After the 10 s UDC wait and the
`udc names` line, and before the gadget path, init logs whether
`88e0000.qcom,msm-eud` is bound to the `msm-eud` driver, whether
`a600000.ssusb` is bound to `msm-dwc3`, and every `devices_deferred` line for
`a600000.ssusb` with its supplier reason. The 150 s timer, the `/run/keep`
escape, the `bin/restart2` helper, the key-only sshd and the NCM/ECM path are
unchanged. An `insmod` success is not a bind or a USB success.

The builder reuses the verified debug gzip `caa3eb82…` and changes only
`/init`. The resulting 3,485,696-byte newc carries zero `.ko` and hashes to
`5db0a7d4c4b9ab123c5437c9e5de771d40ce7b95474403c87f93c7f208a37467`.
Stock LZ4 HC level 12 makes one 1,929,933-byte block (1,929,941-byte legacy
frame) at offset 4,096, inside the 2,117,632 bytes before the signed tail. Only
header field `ramdisk_size@12` changes, from 2,113,581 to 1,929,941; the
187,691-byte gap to offset 2,121,728 is zero; all 6,266,880 bytes from the
signed `AVB0` block through the `AVBf` footer are unchanged. The candidate uses
no new kernel, is not signed, and claims no AVB, ABL or device verdict.

`scripts/build-init-boot-eud-softdep.sh` produced two byte-identical candidate
runs and kept one image outside Git. `scripts/verify-bootimg.sh` passed.
`scripts/verify-init-boot-eud-softdep.py` rejects an init with no timer, a timer
inside or after the module loop, a timer that ignores `/run/keep`, a missing or
misplaced loading marker, a removed reboot-reason bind check, a removed EUD
read-only check, a missing `eud.ko`, a duplicated `eud.ko`, `eud.ko` placed
before its prerequisites or after `dwc3-msm.ko`, a changed order of the old 126
modules, a missing, dynamic or altered helper, a planted `.ko`, a modified
header or signed tail, a closure whose softdep names an unresolved target, a
changed `dwc3_msm` softdep edge, an `eud.ko` with a prerequisite outside the
closure, an absent or non-aarch64 `eud.ko`, and every repeated prior SHA,
including `8f8b7331…`, `bde3a3b3…`, `6078269d…`, `cdb9458f…`, `3932504a…`,
`f4a00ce3…` and `baa33fd4…`. `bash -n`, `shellcheck` and `git diff --check`
pass. The only next physical step belongs to the human coordinator under the
standing mission-shift approval; repository work neither performs nor
authorizes a flash. This leaves #12 and the encrypted-userdata release gate
untouched.

A later measurement of this one image, flashed only to `init_boot_a` with stock
`boot_a`, `vendor_boot_a`, `dtbo_a`, `vbmeta_a` and slot B untouched, and
observed for at least 180 s before any button press, distinguishes three
outcomes. None is claimed here.

- **EUD binds, `a600000.ssusb` binds and a UDC exists.** Only then assess the
  gadget bind and key-only SSH. A flash that returns is not boot success.
- **EUD binds but `a600000.ssusb` or the UDC stays absent.** Record the new
  supplier and deferred state and contrast it with the stock sequence. Stop
  this branch; do not add more modules or force a USB role.
- **EUD `insmod` or bind fails.** Record the exact error and stop to investigate
  the provider. Do not infer an AVB rejection.

If no USB or SSH appears, observe at least 180 s without touching the device.
Fastboot at about 150 to 180 s plus a captured pstore supports the bounded
init-level recovery; if the device does not return, do not assume the timer
covers a kernel hang. A reboot into itself is a distinct failure. Never repeat
this SHA after a negative test.

# Temporary boot chain: diagnosis and next attempt

The 2026-10-19 analysis and historical test plan below preceded failed
2026-10-20 and 2026-10-21 full-chain slot-A attempts. Repository work never
performs device operations. The historical procedure below is not authorization
to repeat it.
