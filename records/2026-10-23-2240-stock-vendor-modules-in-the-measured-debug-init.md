---
date: 2026-10-23
issue: omnipha/linux-sm7635#44
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Stock vendor modules in the measured debug init (#44, host-only, 2026-10-23)

**Host-only image, not a boot result.** No device, flash, USB or userdata
operation was performed. The stock 6.1.84 kernel and `boot_a`, `vendor_boot_a`,
`dtbo`, `vbmeta` and slot B are unchanged. The one new image is
`$WORK/out/init_boot-vendor-modules.img` (8,388,608 bytes, SHA-256
`cdb9458f515bce3f1059f89cab0d7a78945f20e73f3cb7b34645c15646aab42a`).
It is different from measured `3932504a…`, `f4a00ce3…`, stock `baa33fd4…`
and all prior SHAs. Never reflash those earlier measured images.

Stock `vendor_boot_a` SHA-256 `23725940…` contains one PLATFORM fragment,
8,821,389 bytes of Android legacy LZ4 with four blocks. It decompresses to a
29,905,920-byte newc cpio with 317 arm64 `.ko` under `lib/modules`, plus
`modules.dep`, `modules.softdep`, `modules.load` (110 names) and
`modules.load.recovery` (314 names). The generic debug cpio has no `lib` or
`.ko`; the stock recovery cpio has no `lib/modules`. The kernel's
`init/initramfs.c` unpacks the concatenated initrd in one pass, with a later
entry able to overwrite an earlier path. The host checker verifies all vendor
module and metadata paths survive concatenation in both normal and recovery
orders, independent of which archive supplies `/init`. The measured #42
console records `Freeing initrd memory: 57716K`, which equals the 4 KiB-aligned
sum of vendor ramdisk (8,821,389) + #42 generic ramdisk (1,927,750) + stock
recovery ramdisk (48,350,666) + bootconfig (175), then `Run /init as init
process` and `usb-init: starting`. Normal stock Android's `10680K` matches
vendor + stock generic + bootconfig. This demonstrates that the unchanged
vendor ramdisk contributes `lib/modules` to the same rootfs as our own init;
no modules are copied into `init_boot`.

The stock `modules.load` entries and six USB additions from
`modules.load.recovery` (`phy-generic.ko`, `phy-msm-ssusb-qmp.ko`,
`phy-msm-snps-eusb2.ko`, `dwc3-msm.ko`, `repeater.ko`,
`repeater-qti-pmic-eusb2.ko`) yield a deterministic 126-module closure from
`modules.dep` and the applicable softdep `pre` edges. `dwc3-msm.ko` has 33
listed dependencies; the closure adds only 16 names outside `modules.load`:
`qmi_helpers.ko`, `phy-generic.ko`, `phy-msm-ssusb-qmp.ko`, `repeater.ko`,
`phy-msm-snps-eusb2.ko`, `repeater-qti-pmic-eusb2.ko`, `redriver.ko`,
`qcom_glink.ko`, `qcom_glink_smem.ko`, `qcom_smd.ko`, `rproc_qcom_common.ko`,
`pdr_interface.ko`, `pmic_glink.ko`, `ucsi_glink.ko`, `wcd_usbss_i2c.ko`,
 `dwc3-msm.ko`. The priority-stable topological sequence embedded in the frozen
 #44 init, `initramfs/init-44-vendor-modules`, is independently computed by
 `scripts/vendor-module-closure.py`; its newline-delimited list has SHA-256
 `57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08`.
The vendor `.ko` vermagic version prefix differs from the stock 6.1.84 kernel;
stock boot logs show vendor modules loaded under that kernel. Runtime module
acceptance and UDC creation remain unmeasured for this image.

Before the UDC wait, init uses BusyBox `insmod /lib/modules/<name>` exactly
once per closure entry, sends each name plus success or the exact loader
stderr via `usb-init:` kmsg, and continues after failure. It records all UDC
names; if none appears, it logs up to 64 deferred-probe entries from debugfs.
If a UDC appears, the existing NCM/ECM gadget path reports bind success or
its exact write error. The key-only sshd and console remain.

The builder reuses the verified debug gzip `caa3eb82…` only as a source cpio,
replacing only its executable `/init` and emitting zero `.ko`. The resulting
3,484,160-byte newc hashes to
`89ab93ffb30073eb65af81da27434d6934580f4fd59101893a6990dcaf55ba12`.
Stock LZ4 HC level 12 creates one 1,929,210-byte block (1,929,218-byte
legacy frame) at offset 4,096. Only header field `ramdisk_size@12` changes
from 2,113,581 to 1,929,218; the 188,414-byte gap to offset 2,121,728 is
zero; all 6,266,880 bytes from the signed `AVB0` block through `AVBf` footer
are unchanged. The candidate uses no new kernel or copied `.ko`, is not
signed, and does not claim an AVB/ABL or device verdict.

`scripts/build-init-boot-vendor-modules.sh` produced two byte-identical
candidate runs and retained one image outside Git. `scripts/verify-bootimg.sh`
passed, including the vendor-rootfs proof, image envelope, closure order,
zero-`.ko` check and negative fixtures rejecting an image without the load
path, a planted `.ko`, modified header/tail, corrupted block and repeated
measured SHA. `bash -n`, `shellcheck` and `git diff --check` pass. The only
next physical step belongs to the human coordinator under the standing
mission-shift approval; repository work neither performs nor authorizes a
flash. This leaves #12 and the encrypted-userdata release gate untouched.
