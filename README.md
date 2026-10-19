# linux-sm7635

Kernel source tracking for Qualcomm SM7635 (Snapdragon 7s Gen 3, `volcano`).
The first target is the Nothing Phone (3a) Pro (`asteroids`, A059P). This is
**not** a working Omnipha kernel or image yet.

## Source policy

- Vendor source: [NothingOSS/android_kernel_msm-6.1_nothing_sm7635](https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635), branch `sm7635/v/mr` (Nothing OS 3.x, Android kernel 6.1). This vendor tree is not mainline Linux.
- `main`: documentation and the pinned source reference only. This repository does not contain the kernel tree.
- Builds reference an immutable vendor commit through the APKBUILD source URL. Do not publish a full `upstream` mirror while Nothing maintains the repository.
- A local bare backup may exist on the build host. It is not the published source of truth.
- `omnipha`: not created. Add it only for a tested Omnipha-specific patch that cannot live as a small patch stack in `ports`. Submit feasible changes upstream first.

This differs from `linux-sm61x5` and `linux-sdm670`: those mirror community
mainline trees that can go inactive. Nothing's SM7635 tree is the active,
GPL-published source, so copying its 2.7 GB history adds no porting value yet.
A SoC reference does not imply that another SM7635 handset is supported; each
phone needs its own device tree, firmware and boot test.

## Device layout

- [`omnipha/ports/devices/nothing-asteroids`](https://github.com/omnipha/ports/tree/main/devices/nothing-asteroids): facts and eventual device/kernel APKBUILD.
- [`omnipha/images`](https://github.com/omnipha/images): eventual image definition.
- `device-nothing-asteroids`: future device test/issue repository, after the
  approved `omnipha/agents#2` template. Do not duplicate the kernel there.
- `omnipha/agents` issues: [#2 template](https://github.com/omnipha/agents/issues/2),
  [#3 Laurel pilot](https://github.com/omnipha/agents/issues/3); [ports#1](https://github.com/omnipha/ports/issues/1)
  introduces explicit device repository/maintainer status.

## Build baseline (2026-10-19)

An arm64 `Image`, the Volcano SoC DTBs and QRD Pro board overlay DTBO build
from pinned vendor commit `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`.
This is a **standalone baseline**, not a bootable kernel package: no mixed GKI
workspace, external modules, camera/display/audio overlays, partition image,
flashing or phone boot test is included. The vendor source is kernel 6.1.78;
mb003 runs 6.1.84 and is not binary-identical.

On Ubuntu resolute x86-64, with the local bare cache already present:

```sh
sudo apt-get install git make clang-17 lld-17 llvm-17 gcc g++ flex bison \
    bc libssl-dev libelf-dev dwarves device-tree-compiler rsync cpio python3
VENDOR_CACHE="$HOME/github_repos/omnipha/linux-sm7635.git" \
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-baseline.sh
WORK="$HOME/sm7635-build" scripts/compare-baseline.sh
```

The build script checks out the vendor commit from the local cache (no network
fetch) into `$WORK/src`, merges `gki_defconfig`, `pineapple_GKI.config`,
`consolidate.fragment` and `pineapple_consolidate.config` with the vendor's
`scripts/kconfig/merge_config.sh -m -r -y`, then `make olddefconfig`,
`make -j8 Image dtbs` (`ARCH=arm64 LLVM=-17 LLVM_IAS=1 HOSTCC=gcc`).
All artifacts and logs stay under `$WORK/out`, **outside this repo**. The
script makes a local cast-only fix for a const-qualifier warning in vendor
`tools/lib/bpf/libbpf.c` (required by host GCC 15 and clang 17 with `-Werror`).
It uses Ubuntu clang 17.0.6 (23ubuntu7), not the device's Android clang
17.0.2 build 10087095/r487747c: it is reproducible with the listed toolchain,
not a bit-for-bit reproduction of the stock kernel. One build at a time.

The comparison script defaults to read-only `~/phone-second-life-data/mb003`
`config.gz` and `dtb/live-fdt.dtb` (override with `DEVICE_CONFIG` /
`DEVICE_FDT`). It compares config symbol lines and root DT model/compatible;
full deltas are saved in `$WORK/out/comparison.txt`. These private references
and the generated report are never committed.

See [UPSTREAM.md](UPSTREAM.md) for tested hashes, config differences, board DT
identification and limitations. No flash or boot test was done.

## Boot image (2026-10-19)

`scripts/build-bootimg.sh` packages the baseline `Image` and a minimal
initramfs into header-v4 `boot.img` (page size 4096, stock load offsets).
It does not flash or boot the phone. Install the extra host tools, then:

```sh
sudo apt-get install mkbootimg python3 cpio gzip curl file fakeroot
WORK="$HOME/sm7635-build" scripts/build-bootimg.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

The initramfs is a gzip newc cpio with a static arm64 busybox and a configfs
USB gadget. NCM is the network function; ECM is the second function because
the baseline has `CONFIG_USB_CONFIGFS_RNDIS` unset. There is no dropbear:
Ubuntu resolute publishes no arm64 dropbear package, so the image ends in a
key-free serial shell. Details, hashes and the vendor_boot layout are in
[UPSTREAM.md](UPSTREAM.md). Images stay under `$WORK/out`.

## License

Upstream Linux kernel is GPL-2.0-only. Do not add proprietary firmware.
