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
corrected #10 chain was also physically tested and returned to fastboot. The #12 host-only verifier checks the separate stock boot AVB0 hash record and
`recovery_a`/`recovery_b` header-v4/AVB relationships (`scripts/verify-recovery-boundary.py`);
it records the `attempt-20261021-1717` stage-6 recovery fallback and `ramoops`
provenance, states the plain non-discrimination finding between ABL rejection
and pre-`ramoops` kernel failure, and does not authorize repeating any failed
image set.
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
The #21 host-only rebuild changes only the kernel's built-in command line,
appending one `sm7635-boot-marker` token and keeping `CONFIG_PANIC_TIMEOUT=-1`.
Pinned vendor 6.1.78 has no `CONFIG_PSTORE_CONSOLE_SIZE` symbol, so the 2 MiB
console reservation is the stock DT `ramoops_region` value checked by the
verifier rather than a new Kconfig assignment. Only `Image`, `Image.gz` and
`boot.img` differ from #18. See [BOOT.md](BOOT.md) for the SHA set, measured
outcomes and the kernel-entry measurement contract.
The #23 host-only control, `scripts/build-stock-kernel-control.sh`, copies the
verified #21 `boot.img` and swaps in only the unmodified gzip kernel payload
from the read-only stock slot-A `boot_a` reference (new kernel size and image
length only). `scripts/verify-stock-kernel-control.py`, run by
`scripts/verify-bootimg.sh`, proves the payload byte-identity and the #21
layout invariants. It is not a physical result and does not replace the #21
marker image.
The #25 host-only step, `scripts/verify-post-flash-avb.py`, models a fastboot
flash as an overlay on the SHA-pinned stock partition and classifies the
resulting footer, footer-referenced vbmeta and separate boot AVB0 record. It
predicts invalid chained metadata for every earlier debug `boot.img` and intact
metadata for the #23 control, stock `boot_a`, `init_boot` and `vendor_boot`.
`scripts/build-full-boot-footer.sh` then makes one full-partition-size copy of
the #21 `boot.img` with an unsigned `avbtool` hash footer. This is a libavb
model, not an ABL verdict; see [BOOT.md](BOOT.md).
The #32 host-only control, `scripts/build-stock-full-footer.sh`, starts from
the verified #23 `boot-stock-kernel.img` and applies that same unsigned footer
invocation. `scripts/verify-stock-full-footer.py`, run by
`scripts/verify-bootimg.sh`, requires the unchanged 13,955,072-byte prefix, the
448-byte `AVB0` block at that offset with algorithm `NONE`, and a difference
from the #25 image only in the kernel payload and resulting hash descriptor.
It is a host control, not a boot result.
The #34 host-only control, `scripts/build-blank-tail-control.sh`, copies that
same #23 prefix and appends exactly 86,708,224 zero bytes. It does not call
`avbtool` and does not sign. `scripts/verify-blank-tail-control.py`, run by
`scripts/verify-bootimg.sh`, requires the 100,663,296-byte image, the unchanged
prefix, an all-zero tail and a difference from the #32 image only in that tail.
It is a host control, not a boot result.
The #36 host-only control, `scripts/build-avb0-window-erase.sh`, copies that
#23 prefix, appends exactly 16,384 zero bytes and then the stock `boot_a` bytes
from offset 13,971,456 onward. It does not call `avbtool` and does not sign.
`scripts/verify-avb0-window-erase.py`, run by `scripts/verify-bootimg.sh`,
requires the 100,663,296-byte image, the unchanged prefix, the zero window and
the byte-identical signed tail. It is a host control, not a boot result.
The #38 host-only control, `scripts/build-avbf-footer-erase.sh`, copies that
verified #36 image and zeroes exactly its terminal 64-byte `AVBf` footer. It
does not call `avbtool` and does not sign. `scripts/verify-avbf-footer-erase.py`,
run by `scripts/verify-bootimg.sh`, requires the unchanged bytes before offset
100,663,232, 64 zero bytes at the end and the fixed 100,663,296-byte size. It
is a host control, not a boot result.
The #42 host-only control, `scripts/build-init-boot-lz4-debug-ramdisk.sh`,
copies the verified stock slot-A `init_boot_a` and replaces only its generic
ramdisk with one Android LZ4 legacy frame of the cpio unpacked from the
verified debug gzip. The frame uses LZ4 HC level 12, one block, and fits
before the unchanged signed tail. It does not call `avbtool` and does not
sign. `scripts/verify-init-boot-lz4-debug-ramdisk.py`, run by
`scripts/verify-bootimg.sh`, requires the unchanged prefix apart from the
ramdisk-size field, the single LZ4 block, the empty kernel, the unchanged
signed tail from offset 2,121,728 and the fixed 8,388,608-byte size. It is a
host control, not a boot result.
The #44 host-only control, `scripts/build-init-boot-vendor-modules.sh`, reuses
the #42 LZ4 HC-12 envelope with a debug cpio whose `/init` `insmod`s the 126-module
stock vendor closure from the unchanged `vendor_boot_a` ramdisk before the UDC
wait. No `.ko` enters `init_boot`. `scripts/verify-init-boot-vendor-modules.py`,
run by `scripts/verify-bootimg.sh`, fails closed with negative fixtures. It is a
host control, not a boot result; see [BOOT.md](BOOT.md).
The #47 host-only control, `scripts/build-init-boot-self-recovering.sh`, keeps
that closure, UDC wait and gadget path and adds only a pre-`insmod` loading
marker, a `qcom-reboot-reason` bind check and an independent 150 s self-recovery
timer that calls one static arm64 RESTART2 helper. No module, gadget function or
network path is added. `scripts/verify-init-boot-self-recovering.py`, run by
`scripts/verify-bootimg.sh`, fails closed with negative fixtures. It is a host
control, not a boot result; see [BOOT.md](BOOT.md).
The #49 host-only control, `scripts/build-init-boot-eud-softdep.sh`, keeps the
#47 image and adds exactly one `insmod` of the stock `eud.ko`, placed after its
`modules.dep` prerequisites and immediately before `dwc3-msm.ko`, plus read-only
logging of the EUD and `a600000.ssusb` bind state. The 150 s timer, `/run/keep`
escape, helper and gadget path are unchanged.
`scripts/verify-init-boot-eud-softdep.py`, run by `scripts/verify-bootimg.sh`,
rejects a missing or misordered EUD, an unresolved softdep target, a changed old
module order, a removed timer, a bad envelope or tail and every repeated SHA
including `8f8b7331`. It is a host control, not a boot result; see
[BOOT.md](BOOT.md).
The #51 host-only control, `scripts/build-init-boot-peripheral-mode.sh`, starts
from the frozen #49 init (`initramfs/init-49-eud-softdep`, so `88c93077…` still
rebuilds) and adds exactly one step after the module phase: it finds
`a600000.ssusb` under `/sys/bus/platform/devices/`, logs the `mode` attribute and
its value, writes `peripheral` once and logs the result and readback, before the
unchanged bounded UDC wait. EUD/glue bind checks move after the wait with capped
read-only `a600000.dwc3`, `devices_deferred` and `dmesg` logging. Modules, the
150 s timer, helper, sshd and NCM/ECM path are unchanged.
`scripts/verify-init-boot-peripheral-mode.py`, run by `scripts/verify-bootimg.sh`,
fails closed with negative fixtures. It is a host control, not a boot result; see
[BOOT.md](BOOT.md).
The #53 host-only control, `scripts/build-init-boot-static-address.sh`, starts
from the frozen #51 init (`initramfs/init-51-peripheral-mode`, so `9f89fe8d…`
still rebuilds) and stops discarding the two `ip link set` and two `ip addr add`
results in the gadget branch. It logs each result, then read-only `ip addr` and
`ip route` output capped at 32 lines, and one bounded read-only listener check
for `172.16.42.2:22` capped at 64 lines. The 127-module order, the single
`peripheral` write, the 40 × 0.25 s UDC wait, the 150 s `/run/keep` timer,
`bin/restart2`, the NCM+ECM functions and the key-only sshd are unchanged.
`scripts/verify-init-boot-static-address.py`, run by `scripts/verify-bootimg.sh`,
rejects a missing or duplicated address log, a discarded address result, a
removed, moved or lengthened timer, a changed module order, a second role write,
a changed gadget function, a planted `.ko`, a bad envelope or tail and every
repeated SHA including `9f89fe8d`. It is a host control, not a boot result; see
[BOOT.md](BOOT.md).
The #40 host-only control, `scripts/build-init-boot-debug-ramdisk.sh`, copies
the verified stock slot-A `init_boot_a` and replaces only its generic ramdisk
with the existing verified debug gzip newc cpio, updating the ramdisk-size
field and zeroing the gap before the stock signed tail. It does not call
`avbtool` and does not sign. `scripts/verify-init-boot-debug-ramdisk.py`, run
by `scripts/verify-bootimg.sh`, requires the unchanged prefix apart from that
one field, the gzip newc payload, the empty kernel, the unchanged signed tail
from offset 2,121,728 and the fixed 8,388,608-byte size. It is a host control,
not a boot result.

The first `fastboot boot` of the earlier single `boot.img` returned
`Booting OKAY` but never enumerated the gadget. A header-v4 boot takes its
generic ramdisk from `init_boot` and its DTB and vendor command line from
`vendor_boot`, neither of which that attempt replaced. Its later stock
pstore does not establish whether the attempted kernel entered. [BOOT.md](BOOT.md)
records the evidence and the historical procedure. All four three-image attempts returned to fastboot, including #18's
recovery-path attempt before stock rollback; the physical coordinator alone
may authorize any future bounded test of a new evidence-backed set. Nothing in this
repository flashes or boots the phone.

## License

Upstream Linux kernel is GPL-2.0-only. Do not add proprietary firmware.
