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
`consolidate.fragment`, `pineapple_consolidate.config`, the additive
`configs/asteroids-stock-cmdline.fragment` override and the additive
`configs/asteroids-volcano-usb-builtin.fragment` closure with the vendor's
`scripts/kconfig/merge_config.sh -m -r -y`, then `make olddefconfig`,
`make -j8 Image dtbs` (`ARCH=arm64 LLVM=-17 LLVM_IAS=1 HOSTCC=gcc`).
All artifacts and logs stay under `$WORK/out`, **outside this repo**. The
script makes local build-only fixes for a const-qualifier warning in vendor
`tools/lib/bpf/libbpf.c` and out-of-directory `TRACE_INCLUDE_PATH` defines in
eight vendor trace headers (required by host GCC 15 and clang 17).
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
initramfs into header-v4 `boot.img`, `init_boot.img` and `vendor_boot.img`
(page size 4096, stock load offsets). It does not flash or boot the phone.
Install the extra host tools, then:

```sh
sudo apt-get install mkbootimg python3 cpio gzip curl file fakeroot \
    gcc-aarch64-linux-gnu libc6-dev-arm64-cross qemu-user
WORK="$HOME/sm7635-build" scripts/build-bootimg.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

The initramfs is a gzip newc cpio with a static arm64 busybox, a static
arm64 dropbear SSH server, and a configfs USB gadget. NCM is the network
function; ECM is the second function because the baseline has
`CONFIG_USB_CONFIGFS_RNDIS` unset. Only root with the host's ed25519 public
key can log in; set `PUBKEY` to override the build-time input
`~/.ssh/id_ed25519.pub`. No private key is embedded. Details, hashes,
licenses and the vendor_boot layout are in [UPSTREAM.md](UPSTREAM.md).
Images stay under `$WORK/out`. Verification now pins the read-only slot-A
`boot`, `init_boot`, `vendor_boot`, `dtbo` and `vbmeta` reference hashes, checks
stock AVB descriptors and the ramdisk table/bootconfig, and applies the actual
stock DTBO entry 65 to the selected vendor DTB. It does not establish AVB
acceptance or physical boot. The #10 build retains all 20 stock
DTBs (not just the first nine), since the #8 built index 9 cannot resolve the
stock overlay. Only `vendor_boot.img` differs from the failed #8 set. The
corrected #10 chain was also physically tested and returned to fastboot. The
#12 host-only verifier checks the separate stock boot AVB0 hash record; it does
not identify the failed boot boundary or authorize repeating either image set.
The #14 host-only rebuild changes only the kernel's built-in command line to
the measured stock A059P value: `boot.img` differs, while `init_boot.img` and
`vendor_boot.img` retain the #10 hashes. Verification checks the merged config,
built config and unpacked kernel against the read-only stock `config.gz` and
rejects `panic_on_taint` and contradictory debug flags. The #16 host-only
packaging change removes only the duplicated generic ramdisk from `boot.img`;
`init_boot.img` keeps the debug generic ramdisk and `vendor_boot.img` keeps its
PLATFORM vendor ramdisk, both byte-identical to #14. The verifier rejects
synthetic duplicate-ramdisk fixtures and pins the other components to #14.
The #18 Path B build now adds the built-in Volcano USB glue and supplier closure
without changing either debug ramdisk, DTB or `init_boot`/`vendor_boot` image.
The host verifier checks the merged board DT-to-driver binding, embedded kernel
config and zero-module initramfs; it does not establish physical boot or SSH.
See [BOOT.md](BOOT.md) for the SHA set, measured outcomes and diagnostic limits.

The first `fastboot boot` of the earlier single `boot.img` returned
`Booting OKAY` but never enumerated the gadget. A header-v4 boot takes its
generic ramdisk from `init_boot` and its DTB and vendor command line from
`vendor_boot`, neither of which that attempt replaced. Its later stock
pstore does not establish whether the attempted kernel entered. [BOOT.md](BOOT.md)
records the evidence and the historical procedure. Both later three-image
attempts returned to fastboot; the physical coordinator alone may authorize
any future bounded test of a new evidence-backed set. Nothing in this
repository flashes or boots the phone.

## License

Upstream Linux kernel is GPL-2.0-only. Do not add proprietary firmware.
