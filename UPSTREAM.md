# Upstream tracking

- Policy (2026-10-19): reference the active vendor repository by immutable
  commit. Do not publish an Omnipha `upstream` mirror unless Nothing removes,
  freezes, or stops maintaining this source, or an Omnipha patch branch becomes
  necessary. A local bare backup on the build host is sufficient until then.
- Source: https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635
- Maintainer: NothingOSS; GPL kernel and devicetree for Phone (3a) and Phone (3a) Pro.
- First target: Nothing Phone (3a) Pro A059P / `asteroids` / `volcano`, measured
  on our `mb003`: `ro.soc.model=SM7635`, stock kernel `6.1.84-android14`.
- Branch for Nothing OS 3.x: `sm7635/v/mr` (upstream head
  `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, observed 2026-10-19).
- Branch `sm7635/b/mr` is newer Nothing OS 4.x and not our stock 3.1 baseline.
- Vendor `v/mr` Makefile reports 6.1.78; `b/mr` reports 6.1.157. The exact
  `Asteroids-V3.1-250112-1904` build used on mb003 was not found in the
  published releases; earliest listed V3.1 release is 250302-1856. Expect
  differences from the on-device 6.1.84 binary.
- DTs: `arch/arm64/boot/dts/vendor/qcom/volcano*.dts{,i}` and
  `volcano-qrd-pro-overlay.dts`. The exact device overlay remains unverified.
- Checked: 2026-10-19, via upstream README, GitHub branch and Makefile, and
  ADB measurements of mb003.

## Baseline build (2026-10-19)

Tested on Ubuntu resolute x86-64, 8 cores, using the local bare cache
`~/github_repos/omnipha/linux-sm7635.git` (not a network fetch) and read-only
device references `~/phone-second-life-data/mb003/config.gz` and
`dtb/live-fdt.dtb`. Nothing was flashed and the phone was not booted.

```sh
sudo apt-get install git make clang-17 lld-17 llvm-17 gcc g++ flex bison \
    bc libssl-dev libelf-dev dwarves device-tree-compiler rsync cpio python3
VENDOR_CACHE="$HOME/github_repos/omnipha/linux-sm7635.git" \
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-baseline.sh
WORK="$HOME/sm7635-build" scripts/compare-baseline.sh
```

The script checks out `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, applies one
local cast in `tools/lib/bpf/libbpf.c` so host `resolve_btfids` builds under
`-Werror` with GCC 15 or clang 17, merges the pineapple consolidate fragment
chain, then runs `make -j8 ARCH=arm64 LLVM=-17 LLVM_IAS=1 HOSTCC=gcc Image dtbs`.
Artifacts stay in `$WORK/out` and are not committed.

| artifact | sha256 |
| --- | --- |
| `Image` (39971328 bytes) | `b289b9f19171db2b110c51e98f883cf1c824c8374983c9e95e51d9194df7140f` |
| `.config` (237437 bytes) | `acee1959e6ab3b4fcdf72ef708d5a13957c714e6b34a3a9ccfc5cb916c04d1cc` |
| `volcano-qrd-pro-overlay.dtbo` | `f463a7ef578263bbe4ecc373be1dab3da1a731d3cac6d423e6698dbe0cf11274` |
| `volcano-volcano-qrd-pro-overlay.dtb` (368015 bytes) | `1c8251e52a013e0b7b9cb6d21b45a640f26b966a9984db5474d7b7c112fb111d` |

Compiler recorded in the built config: `Ubuntu clang version 17.0.6 (23ubuntu7)`.
The device config records `Android (10087095, +pgo, +bolt, +lto, -mlgo, based on
r487747c) clang version 17.0.2`. That exact prebuilt was not available to this
host, so the baseline is reproducible with the pinned Ubuntu toolchain, not a
bit-for-bit reproduction of the stock kernel.

### Board identification

The live FDT root is `model = "Qualcomm Technologies, Inc. Volcano QRD Pro"` and
`compatible = "qcom,volcano-qrd", "qcom,volcano", "qcom,volcanop-qrd",
"qcom,volcanop", "qcom,qrd"`, with `qcom,msm-id = <0x280 0x10000>, <0x281
0x10000>, <0x27c 0x10000>` and `qcom,board-id = <0x0b 0x00>`. Comparing those
root properties, not filenames, `scripts/compare-baseline.sh` marks exactly one
built file: `volcano-qrd-pro-overlay.dtbo` (`qcom,oem-id = <2>`). The non-Pro
`volcano-qrd-overlay.dtbo` has the same compatible list and differs by model
and `qcom,oem-id = <1>`.

`volcano.dtb` is the base SoC (`msm-id` 0x27c only, model "Volcano SoC").
Kbuild's composite `volcano-volcano-qrd-pro-overlay.dtb` applies that overlay
but its root model/compatible stay the base SoC's, so it is not the identity
match. Applying the same overlay with standalone `fdtoverlay` fails to resolve
the overlay's symbolic phandle targets even though the base DTB contains
`__symbols__`; the Kbuild composite is the usable combined blob. Camera,
display and other vendor DTBO sets under `vendor/qcom/proprietary` are not part
of `make dtbs` and were not built.

### Config comparison

Merge method: `scripts/kconfig/merge_config.sh -m -r -y` over
`arch/arm64/configs/gki_defconfig`,
`arch/arm64/configs/vendor/pineapple_GKI.config` (this sets
`CONFIG_ARCH_VOLCANO=y`; volcano is built as the pineapple target),
`arch/arm64/configs/consolidate.fragment` and
`arch/arm64/configs/vendor/pineapple_consolidate.config`, followed by
`make olddefconfig`. The `gki` variant's KMI trimming needs a full
kernel-platform workspace and the `android/abi_gki_aarch64_qcom` symbol list,
which this standalone tree does not contain, so it was not applied.

Against the on-device config (5996 symbols, Linux/arm64 6.1.84): 5921 identical,
75 device-only or changed lines, 1054 built-only or changed lines (a symbol
with different values appears in both lists). The built config has 6975
symbols. Notable changed settings are `CONFIG_MODULE_SIG_ALL=y`,
`CONFIG_TRIM_UNUSED_KSYMS=y` and `CONFIG_UNUSED_KSYMS_WHITELIST`; the built
config has both of the first two unset. `CONFIG_CMDLINE` and
`CONFIG_LOCALVERSION` also differ, as do the toolchain-generated
`CONFIG_CC_VERSION_TEXT`, `CONFIG_CLANG_VERSION` and `CONFIG_LLD_VERSION`.
Both sides set `CONFIG_LOCALVERSION_AUTO=y`, `CONFIG_ARCH_VOLCANO=y`, `CONFIG_DEBUG_INFO_BTF=y`
and the same SELinux options checked. The large built-only set is mostly debug,
test and SoC options that `olddefconfig` fills in and the device's trimmed
config omits. The full symbol diff is `$WORK/out/comparison.txt`.

### Limitations

- Not a boot test and not a packaged boot image. No modules, vendor DLKM,
  initramfs or `dtbo.img` were built.
- Source is 6.1.78; the measured device kernel is 6.1.84.
- Toolchain is Ubuntu clang 17.0.6, not Android clang 17.0.2 build 10087095.
- `CONFIG_MODULE_SIG_ALL` and `CONFIG_TRIM_UNUSED_KSYMS` differ from the device.
- One local, uncommitted cast in the build worktree is required for host tools.
