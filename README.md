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
The #55 host-only attempt, `scripts/build-stock-config-baseline.sh`, builds the
own `6.1.78` kernel from the read-only captured stock `config.gz`, disabling
only the debug options enabled in the current own build but absent from stock
(`configs/asteroids-stock-config-debug-off.fragment`), keeping the existing USB,
pstore, panic and `sm7635-boot-marker` fragments. The resulting gzip payload
(14,782,792 bytes) misses the signed-tail bound of 13,967,360 bytes, so the
build fails closed, packages no image and records no control SHA. It is a
negative host result, not a boot result; see [BOOT.md](BOOT.md).
The #71 host-only control, `scripts/build-init-boot-ipci-defer.sh`, keeps the
measured #69 init (`9291c369…`, never reflash) and adds exactly one bounded bind
gate before the final `qca_cld3_qca6750.ko` insmod: run 28 showed
`pld_register_driver:305:: Fail to register ipci driver` because `__icnss_register_driver`
returns `-EAGAIN` while icnss2 has not finished probing behind the strict
`fw_devlink` supplier `9bb00000.remoteproc-wpss`. The gate waits at most 12 s for
`/sys/bus/platform/devices/17110040.qcom,wcn6750/driver`, then logs the WPSS and
icnss2 platform-bind state before the one stock insmod. Everything else,
including the 21-module closure, mounts, 150 s timer and USB/SSH path, is
unchanged. `scripts/verify-init-boot-ipci-defer.py` is wired into
`scripts/verify-bootimg.sh` with fail-closed negative fixtures, including a
removed, duplicated, retargeted or unbounded gate and a repeated `9291c369` SHA.
This is a host control, not a boot result; see [BOOT.md](BOOT.md).
The #69 host-only control, `scripts/build-init-boot-wlan-rfkill.sh`, fixes the
measured run-27 `vendor_a` and `system_dlkm_a` mount failures: the stock kernel's
`loop.max_part=7` means loop device minors cannot equal loop indexes. It derives
loop major:minor from `/sys/block/loopN/dev`, probes erofs/ext4 magic and mounts
the same three verified super extents read-only. `system_dlkm_a` supplies the
SHA-pinned `rfkill.ko` before `cfg80211.ko`; `vendor_a` is mounted read-only,
and the firmware directory is supplied separately by the measured by-name
`modem_a` (`/dev/block/sde6`, vfat), mounted read-only at
`/vendor/firmware_mnt`. The unchanged 21-module order and capped logging expose
mount, firmware, module and wlan results. The frozen run-24 init, timer and
stock image envelope are otherwise unchanged. `scripts/verify-init-boot-wlan-rfkill.py`
is wired into `scripts/verify-bootimg.sh` with fail-closed negative fixtures,
including absent rfkill, guessed loop minors and a repeated `2faab7e2` SHA.
This is a host control, not a boot result; see [BOOT.md](BOOT.md).
The #67 host-only control, `scripts/build-init-boot-wlan-closure.sh`, starts
from the frozen run-24 #53 init and adds exactly one `wlan-init` phase before
`console ready`: it checks `/dev/block/sda6` against the measured super size and
the pinned logical-partition metadata, mounts `vendor_dlkm_a`, `vendor_a` and
`system_dlkm_a` read-only, and `insmod`s the 21-module dependency-ordered stock
WLAN closure (the 20-module `vendor_dlkm` closure of `qcom_q6v5_pas`,
`icnss2`, `qca_cld3_qca6750`, `cnss_plat_ipc_qmi_svc` and `qrtr-smd`, plus
`rfkill.ko` from `system_dlkm`) with per-module result lines and capped read-only
`wlan0`/`iw`/`dmesg`/firmware-name logging. The 127-module order, the single
`peripheral` write, the 40 × 0.25 s UDC wait, the 150 s `/run/keep` timer,
`bin/restart2`, the NCM+ECM functions and the key-only sshd are unchanged, and
no `.ko` enters `init_boot`. `scripts/verify-init-boot-wlan-closure.py`, run by
`scripts/verify-bootimg.sh`, fails closed with negative fixtures and rejects
every repeated SHA including `995aaca3`. It is a host control, not a boot
result; see [BOOT.md](BOOT.md).
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

## Read-only `modem_a` domain-map handoff (2026-10-25, #88, #92)

`docs/modem-a-acquisition-and-extraction.md` records the physical coordinator's
single read-only `modem_a` acquisition for #89 and the fail-closed host
extractor. The acquisition ran once: 367,001,600 bytes, SHA-256
`08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`, quarantined
outside Git, device unchanged. #92 corrected the #88 tooling against that dump
(4096-byte FAT16 sectors, the LFN short-name checksum mask bug, the stock
`sr_version` object form) and extracted six validated `.jsn` under `image/`.
`scripts/extract-modem-domain-maps.py` reads only a supplied FAT image, lists
and hashes every `.jsn`, validates the evidenced pd-mapper schema, and derives
a JSON config only from validated data. `scripts/test-modem-domain-map-extraction.sh`
exercises it with synthetic non-stock, non-flashable fixtures, including a
4096-byte-sector FAT16 fixture and the LFN case that aborted the stock run.
The independent `msm_sharedmem.ko`/rmtfs evidence from #85 stays separate from
the #86 pd-mapper/tftp variable.

The first `fastboot boot` of the earlier single `boot.img` returned
`Booting OKAY` but never enumerated the gadget. A header-v4 boot takes its
generic ramdisk from `init_boot` and its DTB and vendor command line from
`vendor_boot`, neither of which that attempt replaced. Its later stock
pstore does not establish whether the attempted kernel entered. [BOOT.md](BOOT.md)
records the evidence and the historical procedure. All four three-image attempts returned to fastboot, including #18's
recovery-path attempt before stock rollback; the physical coordinator alone
may authorize any future bounded test of a new evidence-backed set. Nothing in this
repository flashes or boots the phone.

## One-shot WPSS firmware boot init_boot (2026-10-25, #101)

`scripts/build-init-boot-wpss-boot.sh` derives a distinct image from the measured
#96 session without changing its init or services; only a dormant, coordinator-
invoked `/bin/wpss-once` helper is added. It checks the modem/DMS session's
stock prerequisites and performs one bounded stock `wpss_boot=1` write after
modem hold and DMS connection are confirmed by the physical coordinator.
`scripts/verify-init-boot-wpss-boot.py`, wired into `scripts/verify-bootimg.sh`,
proves the exact cpio delta, signed envelope and new SHA with negative fixtures.
The full hash, trigger spec and predicted outcomes are in [BOOT.md](BOOT.md).
Host-only; not a physical result.

## Stock sharedmem + pinned rmtfs init_boot (2026-10-25, #96)

`scripts/build-rmtfs-binary.sh` builds a reproducible static musl aarch64
`rmtfs` from pinned upstream commits (qrtr v1.2, rmtfs v1.3) with the
publish-line, stock-UIO and fs1/fs2-only storage patches;
`scripts/build-init-boot-rmtfs-sharedmem.sh` extends the measured #86
(`8dddb8c7`) init by one phase after the unchanged #86 QRTR phase and before
console ready: it loads the stock `vendor_boot` `msm_sharedmem.ko` as-is
(identical to the `vendor_dlkm_a` provider, never rebuilt), records the
`Device created for client 'rmtfs'` line, links `/boot/modemst1 -> sdf2` and
`/boot/modemst2 -> sdf3` from the measured by-name table (fsc/fsg not exposed,
`-r` keeps the partitions unwritten) and starts rmtfs, logging to `/run`. The
three static services are stored xz-compressed and reconstructed byte-exact
(hash-checked) before the byte-identical #86 phase, because the LZ4 envelope
had only 22,448 B spare. `scripts/verify-init-boot-rmtfs-sharedmem.py`, wired
into `scripts/verify-bootimg.sh`, checks the module and service presence,
ordering, logs, envelope and rejects every measured SHA. Host image, hashes,
predicted outcomes and the rollback gate are in [BOOT.md](BOOT.md). This is not
a physical result.

## Stock-map pd-mapper + tqftpserv init_boot (2026-10-25, #86)

`scripts/build-pdmapper-tqftpserv-binaries.sh` builds two reproducible static
musl aarch64 services from pinned upstream commits (qrtr v1.2, pd-mapper v1.1,
tqftpserv v1.3); `scripts/build-init-boot-pdmapper-tqftpserv.sh` packages them
with six byte-exact `.jsn` maps from the one #89 stock `modem_a` read and the
merged #92 extractor. The run-34 (#83, measured `35866d56`) init is changed
only by a reworded marker and a QRTR-service phase after SSH but before any
coordinator-guarded remoteproc2 start, with `/run` logs/status; no rmtfs or
sharedmem work is bundled. `scripts/verify-init-boot-pdmapper-tqftpserv.py`,
wired into `scripts/verify-bootimg.sh`, checks binary/map contents and
executability, ordering, logs, image envelope and all previously measured
SHAs. The host image, full hashes, predicted physical outcomes and rollback
gate are in [BOOT.md](BOOT.md). This is not a physical result.

## Fail-closed /dev/wlan node for the registered char device (2026-10-26, #124)

`scripts/build-init-boot-psoc-hold-wlan-node.sh` derives a new distinct-SHA
image from the measured `8b62520f…` run-42 #120 image with exactly one init
phase, after the WLAN closure and before console ready. It reads the live
`/sys/class/wlan/wlan/dev` numeric major:minor, requires the major to match the
single `qcwlanstate` character-device major in `/proc/devices`, then creates
`/dev/wlan` mode 0600 with a bounded `mknod` and verifies its exact character
major:minor. On any failure it logs the reason, leaves no node and attempts
nothing further. `bin/wpss-once` stays byte-exact, including the fail-closed
`/dev/wlan` exit-9 precheck; init itself never starts the helper. The builder
requires two serial byte-identical images; the verifier is wired into
`scripts/verify-bootimg.sh` and rejects missing, hardcoded or misplaced node
steps, all earlier SHAs and regressions of the #120 invariant. Full SHA and the
three predicted outcomes for a separately authorized single-variable physical
session are in [BOOT.md](BOOT.md). Host-only; no device result or flash
permission.

## Pinned Dropbear host key for the preboot capture handoff (2026-10-26, #120)

`scripts/build-init-boot-psoc-hold-capture-hostkey.sh` packages a protected
Dropbear ed25519 private key (default input
`$HOME/.omnipha/sm7635/dropbear_ed25519_host_key`, mode `0400`, never in Git)
with the unflashed #116 session init, replacing the RAM-generated `dropbear -R`
key with `dropbear -r /etc/dropbear/dropbear_ed25519_host_key`. The public key
and the `[172.16.42.2]:22` known-hosts line are pinned in [BOOT.md](BOOT.md) and
printed by the verifier before reboot. The key file is mode `0600` in the cpio;
the single 25 s-capped `/dev/wlan` ON hold and the one-shot WPSS trigger, 150 s
timer and `/run/keep` semantics are byte-exact #109. The builder requires two
serial byte-identical builds, and `scripts/verify-bootimg.sh` checks the pinned
public key, exact cpio delta, committed-private-key rejection, -R regression,
missing/unpinned key, timer and keep regressions, and distinct SHA including the
unflashed `7c3d915f…` candidate. This is host-only; #116 owns the single
physical rerun with the new SHA and unchanged outcomes (a)/(b)/(c)/(d) and
one-attempt stop rule. Never reflash `7c3d915f…`, `0b40ac34…` or any earlier
measured SHA.

## Capture-gated psoc-idle hold rerun (2026-10-26, #116)

Superseded for execution by #120: the run-41 candidate `7c3d915f…` was never
flashed, and its `-R` host key cannot be pinned before the reboot. It remains
never-reflash; use the #120 pinned host-key image instead.

`scripts/build-init-boot-psoc-hold-capture.sh` rebuilds the measured run-40 #109
session `init_boot` with exactly one change, the session marker reworded to the
#116 capture-gated rerun, so the image gets a SHA-256 distinct from the measured
`0b40ac34` image and from every earlier measured SHA. The single 25 s-capped
`/dev/wlan` `ON` hold, the one-shot WPSS trigger and its single `wpss_boot=1`
write, the 150 s timer and the `/run/keep` semantics are byte-exact.
`scripts/verify-init-boot-psoc-hold-capture.py`, wired into
`scripts/verify-bootimg.sh`, fails closed on a prior measured SHA, a removed,
duplicated, re-capped or moved hold, an altered or retargeted `ON` write, a
second WPSS write, any timer or `/run/keep` change and image-envelope damage,
and the build script requires two serial builds to be byte-identical. The
physical run is owned by the physical coordinator and follows the #113 preboot
capture handoff exactly; predicted outcomes (a)/(b)/(c)/(d) and the handoff are
in [BOOT.md](BOOT.md). This is not a physical result.

## Reproducible postmarketOS RAM userspace for a held stock-kernel session (#139, host-only, 2026-10-27)

[BOOT.md](BOOT.md#reproducible-postmarketos-userspace-for-a-held-stock-kernel-usb-session-139-host-only-2026-10-27)
prepares a RAM-only postmarketOS v24.12 / Alpine v3.21 aarch64 userspace for one
coordinator-held stock-kernel USB-SSH session. `scripts/build-alpine-session.py`
installs the real `postmarketos-base=38-r3` closure — **134** hash-pinned APKs
locked in `scripts/alpine-session-packages.lock` — from three signed APKINDEX
archives with `apk.static --initdb --no-scripts --no-network`, never executing
package scripts. It verifies per-APK SHA-256/index size, 390 aarch64 ELF/musl
closure entries, and packs a byte-reproducible 23,713,302-byte transport
(`7a76a110…`), root password locked, no key/firmware/profile/credential staged.
`scripts/test-alpine-session.sh` fails closed on duplicate/missing/corrupt
inputs, an incomplete lock, wrong-arch ELF and missing libs, and runs a chroot
smoke of `/bin/sh`, `apk`, `iw`, `wpa_supplicant` and Dropbear from the produced
tarball under QEMU+bwrap. The builder's own `apk add` of the frozen set is the
dependency gate (it exits non-zero if any provider is absent). A separate manual
host loopback chroot proved a real key-only Dropbear shell into that postmarketOS
userland with an independent kernel/userland identity (synthetic keys, torn down
afterward); that is host mechanics, not the phone. `scripts/pmos-session-stage.sh` / `-teardown.sh` stage and remove it
reversibly under guest RAM, keeping the diagnostic PID 1, gadget and pinned
`:22` SSH intact and starting a **second** key-only Dropbear on `:2222`. This is
host preparation, not a phone result, image, own-kernel test, persistence path or
release; the coordinator owns the live session and stock rollback.

## Run-58 first-boot self-stage and WLAN blocker (2026-10-29, #164)

[BOOT.md](BOOT.md#run-58-first-boot-self-stage-and-wlan-association-blocker-164-live-session-2026-10-29)
records the first live boot of the `4b83ea24…` `init_boot_a` and `1bdb7c22…`
inactive `vendor_boot_b` images. Without a host push, the guest self-staged the
postmarketOS root from the read-only `vendor_boot_b` window, reached guest PID 1
and OpenRC `default/local`, accepted the 160 s guard ack, and held at the modem
marker. With a separate fresh capture marker before each stage, `remoteproc2`
and `remoteproc3` both reached `running` and `wlan0`/phy0 registered; a scan saw
36 BSS (scan only, not connectivity). OpenRC `wpa_supplicant` started on
`-iwlan0` but stayed `SCANNING`, and `networking` stopped with no DHCP lease.
The guest profile matched the protected host input, yet its network did not
appear in 36-, 37- or 30-BSS scans, so no association, address, route, gateway,
DNS or external reachability was reached. A separate host Wi-Fi scan found zero
matches for the same designated network among 27 BSS, consistent with (not proof
that) the network was not observable. The one clean guest reboot was then issued:
the diagnostic USB debug gadget reappeared by itself about 17 s later under new
interface names, but no host IPv4 was observed on them, USB SSH and capture did
not return, and the device was found in bootloader fastboot about 148 s after the
gadget appeared, consistent with the unchanged 150 s recovery timer. Whether the
`vendor_boot_b` self-stage repeated, and WLAN after reboot, are unmeasured
because the worker did not check the new host interface during that window. The
coordinator owns stock restore and the five-hash proof.

## Inactive `vendor_boot_b` self-staged session (2026-10-29, #164)

[BOOT.md](BOOT.md#host-only-inactive-vendor_boot_b-userspace-payload-and-self-staged-session-164-2026-10-29)
records a host-only payload and boot path, not a physical boot result. The
preferred carrier is inactive `vendor_boot_b`; an unused `super` extent is the
unused fallback. `scripts/build-vendor-boot-b-userspace-payload.sh` requires
byte-identical stock `vendor_boot_a`/`vendor_boot_b` (100,663,296 bytes, SHA-256
`23725940…`), keeps the signed prefix and terminal `AVBf` footer, and adds a
4,096-byte header at offset 18,870,272 (SHA-256 `2d09f260…`) plus the
23,713,302-byte archive at 18,874,368 (SHA-256 `7a76a110…`). The built image
reproduced SHA-256 `1bdb7c22…` at the time of writing, valid only while the
builder and inputs are unchanged. `scripts/build-init-boot-self-stage.sh`
rebuilds the measured `fef03008…` handoff with one detached hook and one
root-only script bundle; its SHA is not pinned because it changes while the
bundled scripts are edited. `scripts/pmos-self-stage.sh` probes the live
`PARTNAME=vendor_boot_b` node read-only, waits at most 145 s for `/run/keep`
inside the 150 s recovery window, and pins guest `:2222` to the diagnostic host
key so the host can pre-pin `[172.16.42.2]:2222` with strict-key checking before
its ack. After cutover `scripts/pmos-self-post.sh` waits for the 160 s
host-owned guard ack, then for a fresh host-verified capture marker released
through root-only `/run/self-stage-capture-marker` before each of modem, WPSS,
driver, scan and services. `sh scripts/test-pmos-self-stage.sh` is the host
fixture. No host push of root or a profile, no unattended power-on, no flashing;
the coordinator controls each boot. #164 stays OPEN pending physical
observation.

## Run-57 OpenRC `wpa_supplicant` and `networking` (2026-10-29, #160)

[BOOT.md](BOOT.md#run-57-measured-openrc-wpa_supplicant-and-networking-on-postmarketos-pid-1-160-live-session-finding-2026-10-29)
records one coordinator-held stock-kernel session on the unchanged `fef03008…`
image. On the RAM-backed postmarketOS PID 1 the merged `scripts/pmos-radio-bringup.sh`
brought up the modem (no EFS fatal), WPSS, `/dev/wlan` and `wlan0`, and a scan saw
40 BSS. The first `rc-service -D wpa_supplicant start` chose `p2p0` instead of
`wlan0`, so `networking` found no lease and stayed stopped. Setting
`wpa_supplicant_if="wlan0"` in the RAM-only `conf.d` and starting both services
through OpenRC again associated (`COMPLETED` plus a connected `iw link`) and DHCP,
gateway (3/3), DNS and external reachability (3/3, repeated) each succeeded.
Capture stayed clean. This is in-session connectivity only; reboot autoconnect,
persistence and release images remain separate. Coordinator rollback and Android
proof are pending, and the `p2p0` interface selection is the next host-script fix.

## OpenRC `networking` + `wpa_supplicant` staging (2026-10-29, #160)

[BOOT.md](BOOT.md#host-only-openrc-networking--wpa_supplicant-staging-on-the-unchanged-session-image-160-2026-10-29)
records the host-only `services` stage of `scripts/pmos-radio-bringup.sh`. Using the
unchanged `fef03008…` image, it stages a root-only `/etc/network/interfaces`, the
profile from standard input at `/etc/wpa_supplicant/wpa_supplicant.conf` (guest RAM,
never in Git or logs) and a `wlan0`-only `ifquery` wrapper, enables only
`wpa_supplicant` and `networking`, and starts them with `rc-service -D`. It refuses
other enabled services, a missing profile, a changed supplicant argument list or
`/bin/ip`, and a repeat in the same boot. `sh scripts/test-pmos-radio-bringup.sh` and
`sh scripts/test-pmos-session-dev.sh` cover it. Nothing here is a phone result; the
services on the real post-cutover WLAN path are one pending coordinator-held
measurement, and #160 stays open for it.

## Run-56 post-cutover WLAN association and reachability (2026-10-29, #150)

[BOOT.md](BOOT.md#run-56-measured-post-cutover-wlan-association-and-reachability-on-postmarketos-pid-1-150-live-session-finding-2026-10-29)
records one coordinator-held stock-kernel session on the unchanged `fef03008…`
image. On the RAM-backed postmarketOS PID 1 the merged `scripts/pmos-radio-bringup.sh`
brought up the modem (no EFS fatal), WPSS, `/dev/wlan` and `wlan0`; a scan saw 44
BSS; the designated host-local profile associated (`COMPLETED` plus a connected
`iw link`) and DHCP, gateway (3/3), DNS and external reachability (3/3, repeated)
each succeeded. Capture stayed clean. Two hand-start pitfalls (no `-f` in the
Alpine supplicant, `IP_CMD=/sbin/ip` for the lease helper) are recorded. This is
in-session connectivity only, with the supplicant and DHCP started by hand; OpenRC
`networking`/`wpa_supplicant` services, persistence and release images remain
separate. Coordinator rollback and Android proof are pending.

## Run-55 post-cutover EFS buffer hold (2026-10-29, #155)

[BOOT.md](BOOT.md#run-55-measured-post-cutover-modem-hold-past-the-efs-request-155-2026-10-29)
records one coordinator-held stock-kernel session: the merged rmtfs script
restored only the two lost `/boot/modemst*` backing links, then one guarded
modem start reached `now up` and remained `running` past +73 s with QMI DMS
connected, no EFS fatal and live key-only SSH/capture. WPSS and WLAN were not
started. Run 55 is closed after coordinator-verified five-partition stock
rollback and Android; #155 is closed.

## Post-cutover rmtfs EFS backing store (2026-10-29, #155)

[BOOT.md](BOOT.md#post-cutover-rmtfs-backing-store-for-the-efs-buffer-155-host-only-2026-10-29)
records the run-54 boundary. The pinned rmtfs process, its QRTR publish and its sharedmem mapping survived
the PID-1 cutover, while `switch_root` deleted the old root's `/dev/uio0` and
`/boot/modemst1`/`/boot/modemst2` links. Whether that deletion caused the
`fs_device_efs_rmts.c:161` fatal is the one hypothesis to test: the pinned
service opens `/boot/modemst*` on demand, while the UIO mapping is already held.
`scripts/pmos-radio-bringup.sh` now checks the pinned rmtfs process, copies its
pre-cutover log, and restores only those missing nodes and links before the
one-shot modem marker. `sh scripts/test-pmos-radio-bringup.sh` fails closed when
any of them is absent or wrong. No new image is built and no modem start is
claimed.

## Reproducible post-cutover radio bring-up (2026-10-28, #150)

[BOOT.md](BOOT.md#reproducible-post-cutover-radio-bring-up-150-host-only-2026-10-28)
records `scripts/pmos-radio-bringup.sh`, the hash-checked reproduction of the
run-53 radio order. Before `switch_root` it stages the read-only stock WLAN INI
(`57989aba…`), the measured one-shot WPSS helper (`fef7e5da…`) and the service
markers into the guest tmpfs. After cutover it runs one guarded modem start, one
WPSS trigger (copying `/dev/wlan` before cutover or deriving it fail-closed from
`/sys/class/wlan/wlan/dev` and the single character `qcwlanstate` major in
`/proc/devices`), one `qca_cld3` insmod with at most one reload, and one 20 s-bounded
scan, each gated on the current boot, `/run/keep` and a fresh capture marker.
`sh scripts/test-pmos-radio-bringup.sh` checks those pins, the fail-closed
`/dev/wlan` derivation and negative fixtures, and the one-shot guards in an
isolated tmpfs. No new image is built: the unchanged `fef03008…` image stays
the only reusable changed image. This is a host script, not a device result;
WPSS/wlan0 after the #155 rmtfs fix and association/reachability with the
regenerated profile remain unmeasured and await the coordinator-held session.

## Post-cutover `default/local` host fixture and reuse review (2026-10-28, #150)

[BOOT.md](BOOT.md#host-only-review-and-reuse-gate-for-post-cutover-defaultlocal-and-radio-diagnosis-150-2026-10-28)
records the host-only preparation for the #150 coordinator-held session. The
live `device-op.py` reuse rule leaves the unchanged #145 `init_boot_a` candidate
`fef03008…` as the only reusable changed image, and #151 changes only a script
staged over SSH into RAM, so no new image is built. `sh scripts/test-pmos-pid1.sh`
now stages the #151 `default/local` link into its isolated BusyBox `switch_root`
fixture, runs OpenRC `sysinit` → `boot` → `default` in the switched root and
asserts `local` started with nothing crashed, across the ack, timeout,
preplanted and symlinked guard cases. This is a host fixture only; on-device
`local` startup, radio state and WLAN after cutover remain unmeasured and #150
stays open for the coordinator-held session.

## Host-only OpenRC service diagnosis and RAM fixture (2026-10-28, #149)

[BOOT.md](BOOT.md#host-only-openrc-runlevel-inventory-and-minimal-ram-only-defaultlocal-fixture-149-2026-10-28)
traces run-52's empty `default` runlevel to `apk.static --no-scripts` in the
134-APK `7a76a110…` public archive: 67 OpenRC service scripts were present,
but no runlevel was enabled. The #145 stage supplied BusyBox `/sbin/init` and
its three-line OpenRC inittab without populating a runlevel; run 52 reached
`softlevel=default` with 0 services started and 0 failed, not an init failure.
A minimal RAM-only stage now enables only `default/local`, after rejecting any
pre-enabled runlevel, missing `local` script/configuration or unexpected startup
hook. `scripts/test-alpine-session.sh` checks the pinned hook/service inventory
and negative inputs; `scripts/test-pmos-session-dev.sh` tests the actual OpenRC
`sysinit` → `boot` → `default` sequence with `local` started and rejects the
missing network/deviceinfo and incompatible guest `/dev` prerequisites in
isolated host namespaces. The archive, image, pinned transition/guard, inittab,
USB control, key-only SSH and guest-private `/dev` remain unchanged. This is a
host fixture only; device service/WLAN startup after cutover and USB continuity
with the new runlevel remain unmeasured and require a separate issue/session.

## Stock-kernel PID-1 handoff and run-52 measured cutover (2026-10-28, #145)

[BOOT.md](BOOT.md#run-52-measured-postmarketos-pid-1-cutover-and-usb-ssh-145-live-session-finding-2026-10-28)
records the run-52 measured cutover on candidate `fef03008…` (true postmarketOS
BusyBox/OpenRC PID 1 on the 256 MiB tmpfs root, guard acked on boot
`e956165d-c9ae-466e-9d1c-e2a76b00ad61`, strict-key USB `:2222` and live
post-cutover console capture; OpenRC `default` with 0 enabled services and
`remoteproc2`/`remoteproc3` left `offline`; coordinator stock rollback pending)
after [the run-51 rejected request](BOOT.md#run-51-measured-request-rejection-145-live-session-finding-2026-10-28);
[the successor design](BOOT.md#bounded-ram-backed-postmarketos-pid-1-handoff-145-successor-host-only-2026-10-28)
describes the `init_boot` candidate from the measured run-43 image:
PID 1 can accept a root-owned, boot-ID-bound request and SHA-pinned volatile
transition only after the old 150 s recovery child has settled. The 134-APK
public archive is staged on a distinct RAM tmpfs with separate private `/run`,
`/dev`, `/proc`, `/sys`, and key-only `:2222`. Before `switch_root` the new
160 s guard is armed independently of `/run/keep`; a strict-key host ack needs
actual new-root PID 1, boot identity, a live second SSH service and heartbeat.
The run-51 candidate `d90b2221…` was physically measured only as a rejected
request: its `/init` sampled `/run/keep` at console-tail entry, before the held
SSH session could create it. That image is refused. The successor builder
`build-init-boot-pid1-handoff.sh` serially reproduces the 8,388,608-byte image
`fef03008…` outside Git, with exact `/init` delta, header, stock-tail and
eager-hold negative checks; the request fixture starts with `/run/keep` absent.
`sh scripts/test-pmos-session-dev.sh`,
`sh scripts/test-pmos-pid1-request.sh` and `sh scripts/test-pmos-pid1.sh` are
isolated **host** fixtures (the x86 PID 1 is native BusyBox, aarch64 userspace
uses QEMU and recovery is mocked). They do **not** establish device PID 1,
AVB acceptance, cold boot, a physical guard result or stock rollback. Only the
coordinator can open a guarded session for #145; the worker continues on the
same issue after a proven handoff, and #145 remains OPEN until a measured
outcome and stock restore. No device operation is performed by these scripts.

## Isolated guest device and PTY host fixture (2026-10-27, #142)

`scripts/pmos-session-stage.sh` now mounts a guest-only RAM tmpfs for `/dev`, creates
and verifies minimal character nodes (including guest-local `tty`), and mounts a
private `devpts` with `/dev/ptmx` linked to its instance. It never binds the
diagnostic `/dev`. Teardown checks mount types and filesystem identities, refuses
unknown/live nested mounts, and unmounts in reverse order. Run
`scripts/test-pmos-session-dev.sh` on a host with passwordless sudo for an
isolated mount/PID/network namespace and the pinned public userspace archive:
the fixture covers fresh and partial/failed stage, missing/wrong nodes, a
shared-`/dev` negative case, unchanged diagnostic service and device nodes, and
both key-only non-PTY commands and `ssh -tt` in the staged userland. This is a
**host PTY result only**. Run 49/#139 closed after verified five-partition stock
rollback; the on-device `ssh -tt` defect remains unmeasured. A new device-side
result requires a separately coordinator-proven held session and rollback; see
[BOOT.md](BOOT.md#isolated-guest-dev-and-host-only-pty-fixture-142-2026-10-27).

## Run-49 live-session staged postmarketOS shell/service + WLAN connectivity finding (2026-10-27, #139)

[BOOT.md](BOOT.md#run-49-measured-staged-postmarketos-shell-service-and-wlan-connectivity-139-live-session-finding-2026-10-27)
records a measured physical result in the coordinator-held run-49 session: after
the on-device-tested staging fix (chroot-local `devpts` replacing the failed nested
`dev/pts` bind), the pinned 23.7 MiB postmarketOS/Alpine userspace staged into
guest RAM, and a host-reached key-only shell confirmed UID 0 inside
`/run/pmos`, postmarketOS v24.12 / Alpine 3.21.9 identity and the same running
stock 6.1.84 kernel — the real staged shell/service milestone, distinct from a
chroot smoke test. From that runtime, in the same held session, the full
WLAN chain was measured separately: guarded modem start (rc 0, running past
+60 s, DMS connected), one `/bin/wpss-once` (rc 0, WPSS running, FW ready),
`wlan0` link-up, a 20 s-bounded `iw` scan (25 BSS, no identifier published), a
private target match (9 BSS), `wpa_supplicant` association (`COMPLETED` **and**
a connected `iw link`), bounded `udhcpc` DHCP (rc 0, one IPv4, default route,
two nameservers), and gateway/DNS/external reachability each rc 0 (3/3, 3/3,
confirmed twice). Continuous capture stayed live with no new fatal/crash/idle
callback; the supplicant was terminated and all private guest RAM scrubbed
before ending worker activity, while the staged runtime and `:2222` were left
alive for the coordinator. Interactive PTY (`ssh -tt`) is **not** proven: the
shared bind-mounted diagnostic `/dev` lacks `/dev/tty`, and creating one leaked
into the outer namespace, so it was reverted and PTY left as a successor task —
non-PTY key-only command shells are the measured service surface. This proves
an ephemeral RAM-only distribution userspace and WLAN connectivity on the
measured stock kernel, **not** persistence, autoconnect after reboot, or a
release image. At the time of that measured finding, the coordinator still
owned the pending stock `init_boot_a` restore, five-hash proof, pstore
preservation and stock Android verification; #139 has since closed after
verified five-partition stock rollback.

## Run-48 live-session WLAN connectivity finding (2026-10-26, #137)

[BOOT.md](BOOT.md#run-48-measured-guest-wlan-connectivity-in-one-held-session-137-live-session-finding-2026-10-26)
records a measured stock-kernel guest WLAN chain in one pinned-key, captured USB-SSH
session on the unchanged run-43 image: one guarded modem start and one WPSS
trigger reached FW ready and `wlan0`; `iw` scanned after IFF_UP (exit 0, 20
BSS), with the complete raw scan and boot ID retained privately outside Git.
The protected target matched 7 BSS privately. `wpa_supplicant` reached
`COMPLETED` with a connected `iw link`; bounded `udhcpc` applied an IPv4 lease,
default route and DNS; bounded gateway ping (3/3), DNS lookup and external
ping (3/3) each succeeded. Continuous capture stayed live with no new
fatal/crash/idle callback across the chain. This proves in-session WLAN
connectivity, not autoconnect after reboot. The coordinator still owns the
pending stock `init_boot_a` restore, five-hash proof, pstore preservation and
stock Android verification; #137 remains OPEN until that closure is recorded.

## Run-47 live-session WLAN scan finding (2026-10-26, #134)

[BOOT.md](BOOT.md#run-47-measured-guest-scan-success-association-unmeasured-134-live-session-finding-2026-10-26)
records a measured guest `iw` scan success in one held, captured, pinned-key SSH
session on the unchanged run-43 image. The first scan returned `-ENETDOWN`
(exit 156) because `wlan0` was administratively down (flags `0x1002`); after one
safe link-up (flags `0x1003`), one 20 s-bounded retry returned exit 0 with 17 BSS
(10 at 2.4 GHz, 7 at 5 GHz) and zero new fatal/crash/idle capture lines. The
worker did not inspect SSIDs/BSSIDs or touch a profile. This proves the stock
nl80211 driver serves scans, **not** target visibility, association, DHCP or
network access. Run 47 later returned to verified five-partition stock and
#134 was closed as superseded by #137. The earlier host-only [handoff plan](BOOT.md#planned-live-session-wlan-handoff-scan-through-connectivity-134-host-only-2026-10-26)
prepares one bounded, coordinator-owned live-session handoff on the **unchanged**
run-43 image (`0f998e29…`) from the #132 inventory. It host-verifies the cached
Alpine v3.21 aarch64 bundle (`iw`/`wpa_supplicant`/`wpa_cli` + musl/libnl): APK
and per-file SHA-256, the musl interpreter and dependency closure, and QEMU smoke
loads through the bundled loader (`iw version 6.9`, `wpa_supplicant v2.10`, exit 0)
— proving **loading only**, not a guest scan. It inventories guest DHCP tooling
without touching a WLAN profile (`udhcpc` present; run-43 cpio ships **no**
`/etc/udhcpc/default.script`, so the hash-checked, synthetic-tested lease helper
is transferred into RAM). The host-only plan documents fail-closed preboot
readiness for the protected profile/client/DHCP without printing secrets, plus
root-only RAM transfer, a 20 s-bounded scan and conditional bounded
association/address/reachability with per-stage stop rules. The new measured
scan above is a separate live result; it does **not** close #134 until the
coordinator records the remaining per-stage outcome and verified rollback.

## Host-only guest scan-client diagnosis (2026-10-26, #132)

[BOOT.md](BOOT.md#run-46-guest-scan-client-diagnosis-132-host-only-2026-10-26)
separates the measured run-46 link-up fallback from a reproducible host
inventory of the unchanged run-43 image, stock ramdisks and read-only
`vendor_a` mount. The BusyBox `iw` applet and standalone `iw` are absent;
Android `/vendor` Wi-Fi binaries are present but not directly usable without
the Android runtime/services. It identifies an independently packaged arm64
`iw` with musl/libnl dependencies and a separate, authorization-gated
RAM-only delivery option; no scan, new image or device operation is performed.

## Current run-43 image reuse handoff (2026-10-26, #130)

[BOOT.md](BOOT.md) records a read-only recheck of the measured run-43 image
(`0f998e29…`, 8,388,608 bytes). Under the current device-op rule this is the
sole reusable changed image from the newest boot that reached key-only SSH;
#127's run-44 one-use/never-reflash language below is historical, and run 44
aborted before any partition write. The physical coordinator owns exactly one
session and one attempt through `device-op.py flash` on `init_boot_a` only, with
normal preflight and verifier hooks; no force or ledger edit. Every older
measured SHA remains refused. No new image, SHA, kernel, config, module or timer
change. #130 stays open until the coordinator records the measurement and stock
rollback; this host handoff claims no device result.

## Historical run-44 handoff (2026-10-26, #127)

Superseded by #130 above. The following describes the former #127 procedure,
not the current reuse gate: it proposed one further `init_boot_a` flash under
the standing `full_autonomy_device_iteration` approval to ask whether the
stock driver serves one bounded userspace nl80211 action while `wlan0` is
registered (`operstate=down`). No new image, SHA, kernel, config, module or
timer change. `scripts/verify-run44-session-plan.py` checks the synthetic
handoff fail-closed: preboot listener and pinned host key before the one
authorized flash, post-enumeration NCM route, key-only SSH, capture selftest
and `/run/keep` before the unchanged 150 s deadline, reproduction of the
run-43 state (one guarded modem start, one `/bin/wpss-once` with exit 0 and
idle-callback count 0), exactly one 20 s time-bounded action using the
session's own busybox (`iw dev wlan0 scan` only if the guest `iw dev` reports
a phy; otherwise a single `ip link set wlan0 up`), post-action sysfs/kmsg
evidence with new fatal/crash/idle-timeout counts, and the stock rollback
with pstore pulled before stock Android. Timeouts and fallback outcomes are
recorded, never retried. It proves no physical result; the current coordinator
handoff is recorded in [BOOT.md](BOOT.md). #127 remains OPEN blocked until the
#130 coordinator measurement resolves it.

## Preboot capture handoff (2026-10-26, #113)

`scripts/verify-preboot-capture-handoff.py` checks the host-only launch order
against the unchanged 150 s recovery deadline. The listener and gadget route
must be ready before the simulated reboot. At the measured run-40 SSH point of
uptime 120 s, the synthetic sequence has a 30 s residual budget; it permits
`/run/keep` at 124 s only after a marker from that boot passes selftest. The
negative fixtures reject late capture, late selftest or keep, another boot's
marker, a stale pre-selftest marker, keep without a passing selftest, and a
down link. This authorizes no image and proves no physical session. The
coordinator handoff is recorded in [BOOT.md](BOOT.md).

## Capture-gated retry session init_boot (2026-10-25, #83)

`scripts/build-init-boot-retry-marker.sh` packages exactly one host-only session
init_boot: the byte-exact measured #81 init (`ae2ccff7`) with only the session
marker reworded to the single #83 capture-gated retry log, after the armed 150 s
self-recovery timer and before the module phase. That one string change forces a
SHA-256 distinct from the measured `ae2ccff7` image of run 33 and from every
other measured SHA. The boot init starts no remoteproc, never creates
`/run/keep`, and adds no `rmmod` or reload; the supplier phase and order, the
bounded WPSS/icnss2 bind gate, the read-only mounts, the single stock WLAN load,
the module closures, the RESTART2 helper and the USB/key-only SSH path are
unchanged. Run 33 lost the fatal text because capture readiness was never proven
before the guarded start, so the coordinator runs the merged capture tooling's
`selftest --marker ... --timeout` until a live console line reaches the host
capture before the one guarded `remoteproc2` start. The 150 s userspace timer
does not cover the expected kernel panic.
`scripts/verify-init-boot-retry-marker.py` fails closed and proves the decoded
`/init` delta against the rebuilt `ae2ccff7` image is exactly the marker string;
its negative fixtures reject a missing, duplicated, moved, reworded or renumbered
marker, the reused #81 and #79 marker texts, the rebuilt measured `ae2ccff7`
image and its SHA, early keep, an init-time remoteproc start, the reused
#75/#77/#79/#81 inits, timer regressions, `rmmod`/`modprobe` and every reused
measured SHA including `ae2ccff7`, plus a host-only simulated-clock timer test,
and it is wired into `scripts/verify-bootimg.sh`. The reproducible image and the
predicted outcomes are recorded in [BOOT.md](BOOT.md). No physical boot, `wlan0`,
modem or fatal text is claimed.

## Live fatal-stream session init_boot (2026-10-25, #81)

`scripts/build-init-boot-live-fatal-stream.sh` packages exactly one host-only
session init_boot: the byte-exact measured #75 init plus exactly one #81
session-only log after the armed 150 s self-recovery timer and before the
module phase. The marker is the only delta and forces a SHA-256 distinct from
the reused measured `4216af26` session image of run 32 and from every other
measured SHA. The boot init starts no remoteproc, never creates `/run/keep`,
and adds no `rmmod` or reload; the supplier phase and order, the bounded
WPSS/icnss2 bind gate, the read-only mounts, the single stock WLAN load, the
module closures, the RESTART2 helper and the USB/key-only SSH path are
unchanged. Run 32 showed the polled capture loses the fatal line before the USB
link dies, so the coordinator opens a persistent host-side `dmesg -w` stream
during the modem-off baseline and keeps it running through one guarded
`remoteproc2` start. The 150 s userspace timer does not cover the expected
kernel panic. `scripts/verify-init-boot-live-fatal-stream.py` fails closed with
negative fixtures (marker removal, duplication, move, rewording or the #79 text,
early keep, init-time remoteproc start, the reused #75/#77/#79 inits, timer
regressions, `rmmod`/`modprobe` and every reused measured SHA including
`4216af26`) plus a host-only simulated-clock timer test, and is wired into
`scripts/verify-bootimg.sh`. The reproducible image and the predicted outcomes
are recorded in [BOOT.md](BOOT.md). No physical boot, `wlan0`, modem or fatal
text is claimed.

## Modem remoteproc start init_boot (2026-10-24, #77)

`scripts/build-init-boot-modem-start.sh` packages exactly one host-only init_boot
from the measured #75 init. One guarded phase after the supplier phase and before
the existing 12 s bind gate and the single `qca_cld3_qca6750.ko` load reads the
modem `remoteproc2` state with a 2 s timeout and, only while that state is
`offline`, writes `start` once to its `state` file with a 10 s timeout, then
logs the write result and the resulting state. A modem that is already running,
or in any other state, is left untouched. The #75 supplier phase and order, the
corrected read-only mounts, the WLAN and vendor module closures, the 150 s timer
and the USB/key-only SSH path are unchanged. `scripts/verify-init-boot-modem-start.py`
fails closed with negative fixtures and rejects the measured `5a61de0e` SHA; it
is wired into `scripts/verify-bootimg.sh`. The reproducible image and the one
physical-outcome contract are recorded in [BOOT.md](BOOT.md). No physical boot
or WLAN success is claimed.

## WPSS supplier init_boot (2026-10-24, #75)

`scripts/build-init-boot-wpss-supplier.sh` packages exactly one host-only
init_boot from the measured #71 init. A single bounded phase before the first
`qca_cld3_qca6750.ko` load insmods stock `/lib/modules/smp2p.ko`, then
`pinctrl-spmi-gpio.ko`, then `qti-fixed-regulator.ko`, guarded against repeats,
and logs each result plus WPSS, regulator and icnss2 bind state. The existing
12 s bind gate, read-only mounts, WLAN closure, 150 s timer and USB/key-only SSH
path are unchanged. `scripts/verify-init-boot-wpss-supplier.py` fails closed
with negative fixtures and rejects the measured `e5b99b7c` SHA; it is wired
into `scripts/verify-bootimg.sh`. The reproducible image and the one
physical-outcome contract are recorded in [BOOT.md](BOOT.md). No physical boot
or WLAN success is claimed.

## Run-29 live WLAN diagnosis (2026-10-24, #73)

The run-29 coordinator session over key-only SSH on the measured
`e5b99b7c…` init_boot measured the WPSS supplier chain directly: the absent
`smp2p` provider of the `slave-kernel` smem-state supplier kept
`9bb00000.remoteproc-wpss` deferred, and the fixed PMIC pinctrl/regulator
chain kept icnss2 deferred behind it. Volatile loads of the stock
`/lib/modules/smp2p.ko`, `pinctrl-spmi-gpio.ko` and `qti-fixed-regulator.ko`
bound WPSS, `soc:pm3001a-s1j` and icnss2, and `wpss_boot=1` brought the WPSS
firmware up (`WLAN FW Initialization done`) — but `wlan0` was never observed:
icnss2 failed its driver probe on an unavailable DMS MAC service while the
modem remoteproc was offline. A modem start and WLAN-driver retry lost SSH
before the result could be read. No new image was built or verified for #73;
the next blocker needs a coordinator-restored live session. See
[BOOT.md](BOOT.md) for the full fact/hypothesis separation.

## License

Upstream Linux kernel is GPL-2.0-only. Do not add proprietary firmware.
