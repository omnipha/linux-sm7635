---
date: 2026-10-21
issue: omnipha/linux-sm7635#18
subsystem: usb
result: inconclusive
source: BOOT.md
---
## Volcano USB driver reachability (#18, host-only, 2026-10-21)

**Path B selected:** `boot.img` alone changes relative to the verified #16
three-image chain. The `init_boot.img` and `vendor_boot.img` payloads and hashes
are unchanged, including both identical gzip debug ramdisks, all 20 stock vendor
DTBs, the 175-byte bootconfig, cmdlines and stock DTBO 65 selection. The new
last-applied `configs/asteroids-volcano-usb-builtin.fragment` only promotes
`=m` drivers to `=y`; it does not alter source DTBs, boot layout or initramfs.
The #16 `Image`, `.config`, `Image.gz` and boot bytes change as expected; no
modules are staged. `CONFIG_USB_DWC3_QCOM=y` matches `qcom,dwc3` but does **not**
match the actual `qcom,dwc-usb3-msm` Volcano wrapper. Kconfig alone is not
proof: the full pinned 6.1.78 `vmlinux` link now succeeds (the source also
needs eight local build-only trace include path fixes to compile the promoted
drivers). The unpacked `Image.gz` IKCONFIG equals the merged `.config`; the
verifier resolves the exact phandle suppliers after applying the SHA-verified
stock DTBO 65 to stock vendor DTB index 9. The public repository contains no
raw stock image, module, DTB, key or build artifact.

| merged board DT binding / dependency | pinned source driver / config | #16 -> #18 location |
| --- | --- | --- |
| `/soc/ssusb@a600000` `qcom,dwc-usb3-msm`; child `snps,dwc3` `dr_mode=otg` | `drivers/usb/dwc3/dwc3-msm-core.c` `USB_DWC3_MSM`; core `USB_DWC3` | `m` -> `y`; `y` -> `y` |
| child `usb-phy` `hsphy@88e3000` `qcom,usb-snps-eusb2-phy`, `ssphy@88e8000` `qcom,usb-ssphy-qmp-dp-combo` | `drivers/usb/phy/phy-msm-snps-eusb2.c` `USB_MSM_EUSB2_PHY`; `phy-msm-ssusb-qmp.c` `USB_MSM_SSPHY_QMP` | `m` -> `y` each |
| HS PHY `usb-repeater`/`dummy-supply`; PMIC parent and SPMI arbiter | `drivers/usb/repeater/repeater-qti-pmic-eusb2.c` `QTI_PMIC_EUSB2_REPEATER`, `USB_REPEATER`; `MFD_SPMI_PMIC`, `SPMI_MSM_PMIC_ARB` | `m` -> `y` each |
| parent clocks/resets (5 GCC clocks, 1 reset); HS/SS PHY GCC, RPMh and fixed clocks | `drivers/clk/qcom/gcc-volcano.c` `SM_GCC_VOLCANO`, `COMMON_CLK_QCOM`; `clk-rpmh.c` `QCOM_CLK_RPMH`; fixed-clock builtin | `m` -> `y` (fixed-clock `y`) |
| parent `USB3_GDSC-supply`, SS PHY `usb3_dp_phy_gdsc-supply`, GCC CX/MX, HS/SS/repeater LDOs | `gdsc-regulator.c` `QCOM_GDSC_REGULATOR`, `rpmh-regulator.c` `REGULATOR_RPMH`, `QCOM_RPMH`, `QCOM_COMMAND_DB` | `m` -> `y` each |
| parent three `interconnects` through aggre1/mc_virt/cnoc_cfg/gem_noc and BCM voter | `drivers/interconnect/qcom/volcano.c` `INTERCONNECT_QCOM_VOLCANO`; `INTERCONNECT_QCOM_BCM_VOTER`, `INTERCONNECT_QCOM_RPMH`, `INTERCONNECT_QCOM_QOS`, `INTERCONNECT_QCOM_DEBUG` | `m` -> `y` each (helpers selected by Kconfig) |
| parent `extcon = <&eud>`; `usb-role-switch`, connector via PMIC GLINK/UCSI | `drivers/soc/qcom/eud.c` `QCOM_EUD`; `QTI_PMIC_GLINK`, `UCSI_QTI_GLINK` | `m` -> `y` each |
| child `iommus`, parent dummy SMMU probe-order phandle; SS PHY portselect pinctrl | `ARM_SMMU`, `ARM_SMMU_QCOM`, `QCOM_IOMMU_UTIL`, `QTI_IOMMU_SUPPORT`; `PINCTRL_VOLCANO`, `PINCTRL_MSM`, `QCOM_SCM`; `QCOM_PDC` for parent IRQs | `m` -> `y` each |

There is **no** direct `power-domains` property on either USB node. The
`dummy-supply` SMMU phandle is a probe-order edge, not a power rail. The
merged overlay adds the eUSB2 repeater phandle and its two regulator supplies.
The built-in closure also promotes link-only providers (RPMh, CRM, SOCINFO,
IPC logging, SMEM/GLINK, Gunyah RM/SHM, minidump/mem-buf, regulator debug and
proxy, regmap debug, hwspinlock and redriver). Without them `ld.lld-17`
reports undefined symbols including `crm_write_bw_vote`,
`devm_regulator_proxy_consumer_register` and `qcom_glink_spss_register`.
The additive fragment is the smallest link-complete `=y` closure found while
keeping the existing debug initramfs, role-switch path and vendor kernel
policy; the exact requested/selected symbol list is checked by
`scripts/verify-volcano-usb.py`. Promoting providers that are `=m` on #16
rather than staging 58+ modules avoids an unproven `modules.dep`/early insmod
sequence and preserves the two other chain images exactly.

| artifact | verified #16 (bytes; SHA-256) | #18 Path B (bytes; SHA-256) |
| --- | --- | --- |
| `.config` | 237,498; `8c00c6f8cd89a6b044a0c7df7c481248786b09e14b12964699ed3ee6da7905d9` | 237,546; `5781d141305c4f27bdc0dd3e69a1136a7e9be3c4fbc538d8b5c11e6f2442cd32` |
| `Image` | 39,971,328; `cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386` | 41,859,584; `a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29` |
| `Image.gz` | 15,096,553; `0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c` | 15,746,316; `9055503e67a1321468fa75608b677eec257c403345a7a6de6709369fb71d5d4a` |
| `boot.img` | 15,101,952; `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` | 15,753,216; `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| vendor `dtb.img` (20 entries) | 9,419,891; `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` | 9,419,891; **identical** `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| gzip cpio in both ramdisks | 1,672,600; `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` | 1,672,600; **identical** `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The boot header remains v4 with empty boot generic ramdisk, 1,584-byte
header in a 4,096-byte page, kernel at byte 4,096, kernel gzip length
15,746,316 and no bytes after the aligned kernel at byte 15,753,216.
Init_boot's empty kernel and generic ramdisk offset 4,096, vendor DTB offset
1,679,360, PLATFORM ramdisk, table and bootconfig offsets remain #16's.
The new boot SHA differs from all previously failed boots `5e866c54…`,
`84f7f5ea…`, and the untested #16 boot `1fdc2570…`. Two sequential
host-only packaging/verification runs produced the same SHA set. Verified
stock `parts-a.sha256` and `config.gz` were read only; the latter measures
`CONFIG_CMDLINE` but cannot establish vendor-module runtime loading.

**Checks:** `scripts/build-baseline.sh` (`Image dtbs`, `vmlinux` link passed),
`build-bootimg.sh` twice (deterministic SHA), `verify-bootimg.sh` twice
(DTBO-65 applied; 22 phandle suppliers; embedded config; 0 `.ko`), and
`compare-baseline.sh` passed. Synthetic fixture output includes
`expected module glue without .ko failure: CONFIG_USB_DWC3_MSM=m has no verified built-in driver; initramfs modules/load path not verified (0 .ko)`
and `expected unpacked zero-.ko initramfs failure: CONFIG_USB_DWC3_MSM=m has no built-in driver and initramfs has 0 .ko files`;
existing duplicate-ramdisk fixture still emits `boot generic ramdisk must be empty`.
Host structural checks do **not** prove that the USB controller binds, that
`/sys/class/udc/a600000.dwc3` appears, or that gadget/SSH is reachable.

**Evidence vs hypothesis:** The old chain could not load the `=m` glue and
PHY/power/clock closure from its zero-`.ko` initramfs. This new chain makes
those objects link-reachable in the unpacked `Image`. Actual probe ordering,
Type-C role, UDC enumeration (`18d1:4ee2`) and key-only Dropbear SSH remain
hypotheses pending separately authorized measurement. The previously observed
five-second return to fastboot predates the `/init` 10-second UDC wait and is
**not** explained by the missing driver closure; no bootloader rejection or
kernel entry has been established. Issue #12 remains blocked on an
attempt-specific discriminator. This work is independent of encrypted
userdata and release-image packaging.

**Physical test gate (not executed or requested by this worker):** Only the
physical-test coordinator may separately review the existing
`humanApprovals.bounded_full_chain_test_slot_a` scope for a bounded slot-A
three-image chain using these exact checked hashes, verified stock rollback
and an attempt-specific, supported read-only kernel-entry measurement path.
No approval here covers `dtbo`, `vbmeta`, `userdata`, slot B or permanent
flashing. Without a supported attempt-specific read-only discriminator, the
boot boundary remains unresolved. No device operation was performed for #18.
