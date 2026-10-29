---
date: 2026-10-23
issue: omnipha/linux-sm7635#51
subsystem: usb
result: inconclusive
source: BOOT.md
---
## One peripheral role event after EUD binds (#51, host-only, 2026-10-23)

**Host-only artifact, not a boot or USB result.** No device, adb, fastboot, USB,
flash or userdata operation was performed. The one new image is
`$WORK/out/init_boot-peripheral-mode.img` (8,388,608 bytes, SHA-256
`9f89fe8d614e213de1d197b78b2faf7f88ba190ba66cc41d5e3cd6c144d64af3`).
Two consecutive builds produced byte-identical files. The hash differs from
measured #49 `88c93077…`, #47 `8f8b7331…`, #44 `cdb9458f…`, #42 `3932504a…`,
#40 `f4a00ce3…`, stock `baa33fd4…`, vendor_boot `bde3a3b3…` and
`6078269d…`, and every earlier measured image SHA in the verifier's prior
set. No prior image is reused.

The measured #49 attempt (22) ran its own `/init`, loaded all 127 stock vendor
modules with `eud.ko` immediately before `dwc3-msm.ko`, and by ~11 s reported
EUD and `a600000.ssusb` bound without a UDC or a USB deferred probe. Its
in-image 150 s timer returned the device to fastboot at ~169 s with
`self-recovery -> bootloader` captured in pstore. On stock Android,
`a600000.dwc3` appears around 6.7 s after userspace and Type-C activity,
not when `a600000.ssusb` first binds. The vendor role-switch path needs a
later role event before it creates the DWC3 child; this is a hypothesis about
the minimal own-init, not a measured outcome of the new image.

The #49 `/init` is frozen byte-for-byte as
`initramfs/init-49-eud-softdep` (SHA-256 `8fa9b571b7e957cd64a68ebc5075fa198d8f3c53f5fef9ea065e312310d9bb7b`).
The #49 builder now reads that copy; a separate rebuild produced
`88c93077d5079d4dc81ce723299faab756bf5b52a5af8ebe99c84f68ea9ae0aa`,
byte-identical to the retained #49 artifact. In the new `/init`, after the
module phase and before the unchanged bounded 40 × 0.25 s UDC wait, one
step finds `a600000.ssusb` in `/sys/bus/platform/devices/*` and checks that
it is bound to `msm-dwc3`. If `mode` exists, it logs the current value,
writes exactly `peripheral` once through the discovered path, logs success
or the error text, and logs readback; if missing it logs that and does not
fall back. After the wait it logs UDC names, EUD/glue bind, whether
`a600000.dwc3` exists under glue and is bound, at most 64 `a600000.*`
`devices_deferred` entries, and at most 64 matching `msm-dwc3`/`dwc3`/
`phy`/`repeater` dmesg lines after the module-end marker. These diagnostics
are read-only. A successful attribute write alone is not a child, UDC,
gadget bind, enumeration or SSH success. The 127-module order (list SHA-256
`4f0e151da8a68339d34d7596d73e77f95415faa79b741aaa425572c1fa7caf69`),
150 s `/run/keep` timer, `bin/restart2`, key-only sshd and NCM/ECM path
are unchanged. No extra `.ko`, kernel, DT or gadget function was added.

`build-init-boot-peripheral-mode.sh` rebuilt twice sequentially and its
fail-closed verifier, including negative fixtures, passed on each build.
The 3,487,744-byte newc (SHA-256
`d499d3549cd232fc2b99f0b48be9a3248d354dc0f2b181fe780466409e4c6e53`)
contains zero `.ko`. One Android LZ4 legacy HC-12 block of 1,930,509
bytes (1,930,517-byte frame) starts at offset 4,096; the remaining
187,115-byte gap to offset 2,121,728 is zero. Only the stock init_boot
ramdisk-size header field changes, to 1,930,517; the empty kernel,
8,388,608-byte size and 6,266,880-byte signed stock tail through the
`AVBf` footer are preserved. This does not establish stock AVB acceptance.
Negative fixtures reject a missing or duplicated write, a write before
module completion or EUD/DWC3 loading, the wrong value, a hardcoded SoC
path, a removed or moved timer, a changed module order, a planted `.ko`,
a bad header/frame/gap/tail, a shortened UDC wait or reused measured SHA.
`scripts/verify-bootimg.sh` (155 `OK` checks), `bash -n`, `shellcheck`
and `git diff --check` all passed. Artifacts and test logs remain outside Git.

Contrasting outcomes to distinguish in any separately coordinated physical
measurement: a write error or named PHY/repeater/clock/regulator error would
identify a supplier blocker; an accepted write with a child but no UDC (or
gadget bind failure) would be a different blocker; an accepted write, child,
UDC and bound gadget still requires independent host enumeration and key-only
SSH evidence. If USB/SSH is absent, the 150 s userspace recovery is not a
kernel-hang guarantee; return to fastboot with pstore, a reboot loop and no
return/no log are separate results. **None of these is claimed by host proof.**
#12 and the encrypted-userdata release gate remain untouched.
