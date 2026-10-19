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

- The baseline itself was not a boot test. The boot image below packages that
  kernel; it was unpacked locally and was not flashed or booted.
- No modules or vendor DLKM were built.
- Source is 6.1.78; the measured device kernel is 6.1.84.
- Toolchain is Ubuntu clang 17.0.6, not Android clang 17.0.2 build 10087095.
- `CONFIG_MODULE_SIG_ALL` and `CONFIG_TRIM_UNUSED_KSYMS` differ from the device.
- One local, uncommitted cast in the build worktree is required for host tools.

## Boot image (2026-10-19)

`scripts/build-bootimg.sh` reads the baseline artifacts already in
`$WORK/out` and writes `boot.img`, `Image.gz` and `initramfs.cpio.gz` there.
`scripts/verify-bootimg.sh` unpacks `boot.img` with `unpack_bootimg` and
compares its header with the read-only stock `boot_a.img`, cross-checking the
stock `vendor_boot_a.img` and `dtbo_a.img` layouts. Neither script writes to
the phone.

```sh
sudo apt-get install mkbootimg python3 cpio gzip curl file fakeroot
WORK="$HOME/sm7635-build" scripts/build-bootimg.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

The build is reproducible: the cpio is generated with `--reproducible`, all
mtimes are forced to epoch 0, and `gzip -n` omits name and timestamp. Two
consecutive runs produce byte-identical `boot.img` and `initramfs.cpio.gz`.
`mkbootimg` is Ubuntu `1:34.0.5-12build1`. The arguments match the stock
header fields, not the stock payload:

| field | stock and built |
| --- | --- |
| boot header | v4, 1584 bytes, signature size 0, empty cmdline |
| page size | 4096 (stored in `vendor_boot`; boot v4 has no page field) |
| base / kernel / ramdisk / tags | `0`, `0x8000`, `0x1000000`, `0x100` |
| DTB load address | `0x1f00000` |
| kernel payload | gzip, like stock `boot_a.img` (stock is 13949926 bytes gzipped) |

Stock `boot_a.img` carries a gzipped kernel and an empty ramdisk. The built
`boot.img` carries the gzipped baseline `Image` plus the debug ramdisk,
because this is the image a later temporary boot would pass to fastboot.
Stock `init_boot_a.img` keeps the first-stage ramdisk separate and is not
replaced. Stock `vendor_boot_a.img` is documented but not rebuilt: the
built `boot.img` is self-contained, so a new `vendor_boot` is not part of
this step.

Stock `vendor_boot` layout, from the unpacked reference: header v4 (2128
bytes, page size 4096), one PLATFORM vendor-ramdisk fragment of 8821389
bytes (unnamed), a 9419891-byte DTB blob, one 108-byte ramdisk-table entry
and a 175-byte bootconfig (`androidboot.usbcontroller=a600000.dwc3` and
related tokens). The stock kernel cmdline is empty; the stock vendor cmdline
is `video=vfb:640x400,bpp=32,memsize=3072000 nosoftlockup log_buf_len=1M
ignore_loglevel printk.devkmsg=on bootconfig`.

### DTB and DTBO selection

Stock `vendor_boot` stores twenty concatenated base SoC DTBs, in this order:
Cliffs, Cliffs 7, Cliffs7P, CliffsP, Pineapple v2, Pineapple, PineappleP SG V2,
PineappleP v2, PineappleP, Volcano, Volcano6, Volcano6I FP1–FP4, Volcano6IP
FP1–FP4, Volcano6P. Their root `qcom,board-id` is `<0 0>`. The board overlay
is not in that blob. It is entry 65 of stock `dtbo_a.img` (76 entries,
version 0 table): model `Qualcomm Technologies, Inc. Volcano QRD Pro`, the
live-FDT compatible list, `qcom,board-id = <0x0b 0>`, and `qcom,oem-id = <2>`.

The board identity comes from `volcano-qrd-pro-overlay.dtbo` in
`$WORK/out`, the #1 comparison match, which `verify-bootimg.sh` checks
against stock DTBO entry 65 by model, board-id and oem-id (all three equal).
The non-Pro overlay differs by model and `qcom,oem-id = <1>` and is not
selected. No `dtbo.img` is produced and the stock partitions are not
modified: on this device the board overlay lives in the dtbo partition, which
a temporary `fastboot boot` of the built image does not replace.

### Initramfs

`initramfs/init` plus one downloaded binary, packed as root-owned newc cpio
and `gzip -n -9`:

| path | source |
| --- | --- |
| `/init` | `initramfs/init`, mode 0755 |
| `/bin/busybox` | Ubuntu resolute `busybox-static` 1:1.37.0-7ubuntu1 arm64, static |
| `/bin/{sh,ip,…}` | symlinks to `busybox` for the applets `/init` uses |
| `/sbin/init` | symlink to `../bin/busybox` |
| `/dev/{console,null,kmsg,ptmx}` | character nodes created under `fakeroot` |

The package URL and sha256 are pinned in `scripts/build-bootimg.sh`
(`fcf50794…`). `BUSYBOX_DEB` can point at a local copy of that exact package.
Nothing from the package or the device reference is committed.

`/init` mounts proc, sysfs, devtmpfs and configfs, then creates configfs gadget
`g1` (`idVendor=0x18D1`, `idProduct=0x4EE2`, USB 2.0). It links `ncm.usb0` and
`ecm.usb0`, binds the first UDC, and assigns `172.16.42.2/24` to `usb0` and
`172.16.43.2/24` to `usb1`. The fixed serial string is the literal `sm7635`,
not a device serial. It then opens a root shell on the console with
`setsid cttyhack`.

### USB gadget and sshd blocker

The baseline config has `CONFIG_USB_CONFIGFS_NCM=y`, `CONFIG_USB_F_NCM=y`,
`CONFIG_USB_CONFIGFS_ECM=y` and `CONFIG_USB_F_ECM=y`. `CONFIG_USB_CONFIGFS_RNDIS`
is not set, and `CONFIG_USB_F_RNDIS` is absent. RNDIS would require a kernel
rebuild, which this packaging step does not do. NCM is the function a host
should use; ECM is present because it is already built in.

Dropbear is not included. Ubuntu resolute has `dropbear-bin` only for amd64,
and the arm64 Ports index has no `dropbear` or `dropbear-bin` package. The
arm64 OpenSSH server is dynamically linked and is not a key-only initramfs
sshd. No SSH key is generated or stored. The serial shell is the documented
debug path until an arm64 static dropbear can be built and a key is supplied
outside this repository.

### Recorded hashes

Built on 2026-10-19 with the pinned busybox package; `scripts/verify-bootimg.sh`
reported all checks OK. Stock hashes are identifiers of the read-only
reference, not files in git.

| file | sha256 |
| --- | --- |
| `$WORK/out/boot.img` | `7cd886a24121c878a62839424b6b7f88840ba7504eb09cd0720eec96cb8ecfe5` |
| `$WORK/out/initramfs.cpio.gz` | `c4f7dbee6d3770b0991b891f6f9a7d9b3685ed3dec3d28cbddfdc0f6b9b50244` |
| `$WORK/out/Image.gz` | `159a970903ffbf2012d706099f67703ad6c5d7e31f83441deff363e80eaacc8f` |
| `$WORK/out/Image` | `b289b9f19171db2b110c51e98f883cf1c824c8374983c9e95e51d9194df7140f` |
| stock `boot_a.img` | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` |
| stock `vendor_boot_a.img` | `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` |
| stock `dtbo_a.img` | `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992` |
