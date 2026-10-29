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
	`configs/asteroids-debug-marker.fragment` override with the vendor's
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
