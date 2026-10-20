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
match. Applying the built QRD Pro overlay to the built base with `fdtoverlay`
succeeds in the #10 host-only comparison, but this pairing is not present in
the attempted chain: the actual stock `dtbo_a` overlay cannot apply to that
built base. The Kbuild composite also combines the built base and built board
overlay. Camera, display and other vendor DTBO sets under
`vendor/qcom/proprietary` are not part of `make dtbs` and were not built.

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

The original single-boot packaging is documented here for provenance;
the current three-image debug chain with SSH is described below.

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

Stock `boot_a.img` carries a gzipped kernel and an empty ramdisk. The
original single-boot `boot.img` carried the gzipped baseline `Image` plus
the debug ramdisk, but it was **not** self-contained on header v4: that
attempt did not replace the stock generic ramdisk in `init_boot_a` or the
vendor ramdisk and DTBs in `vendor_boot_a`. The historical three-image
correction is described below.

## Boot chain fix (2026-10-19)

The first temporary-boot attempt exposed a header-v4 layout mismatch:
`fastboot boot` supplied `boot` alone; any test-kernel hand-off would have
received the generic ramdisk from stock `init_boot_a` (the 2747936-byte
Android `/init`), while the vendor ramdisk, DTB blob and command line
would have come from stock `vendor_boot_a` (`first_stage_ramdisk/fstab.qcom`,
324 modules, no `/init`), and the board overlay from stock `dtbo_a` entry
65. There was no USB gadget; the captured `/init` and stock module-load
messages are from a later 6.1.84 stock/recovery console, not evidence
that the 6.1.78 kernel reached init or loaded those modules. The test
kernel's entry and fallback cause are unresolved. [BOOT.md](BOOT.md) has
the distinction and the host-only evidence limits.

`scripts/build-bootimg.sh` now also writes `init_boot.img` (header v4,
empty kernel, the debug ramdisk, matching the stock `init_boot` layout) and
`vendor_boot.img` (header v4 at the stock offsets, the debug ramdisk as its
single PLATFORM vendor ramdisk, a DTB blob, and the vendor command line
`earlycon keep_bootcon loglevel=8 log_buf_len=1M ignore_loglevel
printk.devkmsg=on panic=-1 bootconfig`).

The failed #8 DTB blob kept the stock twenty-entry layout. The first nine
Cliffs and Pineapple DTBs were copied verbatim from read-only `vendor_boot_a`;
index 9 and the other ten Volcano DTBs were built from the vendor source and
had the ramoops reservation added directly. The stock `dtbo_a` entry 65
cannot resolve those built DTBs' missing symbols. In the #10 host-only build,
all twenty stock DTBs are copied verbatim instead, retaining the stock
`dtb_idx=9` selection and allowing the stock overlay to supply its ramoops
reservation. The bootconfig still keeps the stock
`androidboot.usbcontroller=a600000.dwc3` tokens.

The panic policy is `panic=-1`: on panic the kernel waits instead of
rebooting, so the ramoops console survives until OrangeFox reads
`/sys/fs/pstore`. `earlycon` follows `chosen/stdout-path`, which points at
the GENI debug UART the driver registers an earlycon for. No UART test
points were identified, so no serial adapter is part of this setup.

Built 2026-10-19, `scripts/verify-bootimg.sh` all checks OK:

| file | sha256 |
| --- | --- |
| `$WORK/out/boot.img` | `f1406364c3e393cb0a779edfdf4da657eb69169bfc54f5b379cd462c4a5653d3` |
| `$WORK/out/init_boot.img` | `65fc21c462e681bf046c10d3dbe55ac6c8de3fdab975a70b2fb423358a31123f` |
| `$WORK/out/vendor_boot.img` | `93e7625f003ce1b67792d32fdc302b7f903eeb61fbc9d1a44396d0e73e7a2afd` |
| `$WORK/out/dtb.img` | `abf5c3cc2da1be67f1be064bd5e05168f771ec42c9d7a7a42f26b530b07fb7da` |
| `$WORK/out/Image.gz` | `159a970903ffbf2012d706099f67703ad6c5d7e31f83441deff363e80eaacc8f` |
| `$WORK/out/initramfs.cpio.gz` | `c4f7dbee6d3770b0991b891f6f9a7d9b3685ed3dec3d28cbddfdc0f6b9b50244` |
| stock `init_boot_a.img` | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` |

Nothing was flashed and no phone was booted.

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
This identity check alone did not test overlay compatibility; #10 also applies
the actual stock entry 65 to the selected base. The non-Pro overlay differs
by model and `qcom,oem-id = <1>` and is not selected. No `dtbo.img` is produced
and the stock partitions are not modified: on this device the board overlay
lives in the dtbo partition, which a temporary `fastboot boot` of the built
image does not replace.

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

### USB gadget and original sshd blocker

The baseline config has `CONFIG_USB_CONFIGFS_NCM=y`, `CONFIG_USB_F_NCM=y`,
`CONFIG_USB_CONFIGFS_ECM=y` and `CONFIG_USB_F_ECM=y`. `CONFIG_USB_CONFIGFS_RNDIS`
is not set, and `CONFIG_USB_F_RNDIS` is absent. RNDIS would require a kernel
rebuild, which this packaging step does not do. NCM is the function a host
should use; ECM is present because it is already built in.

Dropbear was not included at that point. Ubuntu resolute has `dropbear-bin`
only for amd64, and the arm64 Ports index has no `dropbear` or `dropbear-bin`
package. The arm64 OpenSSH server is dynamically linked and is not a
key-only initramfs sshd. The serial shell was the documented debug path
until the static dropbear build below (2026-10-19) resolved this blocker.

### SSH-capable debug initramfs (2026-10-19)

`scripts/build-bootimg.sh` now uses two pinned sources (nothing from either
source is checked into this repo):

| input | source | sha256 | license |
| --- | --- | --- | --- |
| static arm64 busybox | Ubuntu resolute `busybox-static` 1:1.37.0-7ubuntu1 arm64 (`BUSYBOX_DEB`) | `fcf50794faf920455895d7ef103d1c54b9ebf7f18d2e52982dbf3903b7769592` | GPL-2.0-only, Ubuntu package copyright file |
| dropbear 2026.94 source | `https://matt.ucc.asn.au/dropbear/releases/dropbear-2026.94.tar.bz2` (`DROPBEAR_TARBALL`) | `e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81` | MIT-style (`LICENSE`), bundled LibTomCrypt public domain, LibTomMath public domain; all three notices packed in the ramdisk |

Dropbear is cross-built from source with `aarch64-linux-gnu-gcc`
(`--enable-static --disable-zlib --disable-syslog --disable-lastlog
--disable-wtmp --disable-utmp --disable-pututline --disable-pututxline`),
with `DROPBEAR_SVR_PASSWORD_AUTH=0` and `DROPBEAR_SVR_PAM_AUTH=0` in
`localoptions.h`. `file` confirms ARM aarch64 and statically linked; the
build and verification scripts check the version under `qemu-aarch64`.
The ramdisk carries the binary and the public notices, but no host private
key. Its host key is generated at first connection into `/etc/dropbear`
(`-R`) and is ephemeral; the SSH host fingerprint changes each boot.

The only login is root with the `ssh-ed25519` public key read from
`$PUBKEY` (default `~/.ssh/id_ed25519.pub`) at build time; the file is
validated as a single ed25519 public key and packed as root-owned
`/root/.ssh/authorized_keys` with mode 0600. The build will fail if the
input is missing or malformed. `initramfs/init` keeps the NCM/ECM gadget
and starts dropbear bound to `172.16.42.2:22`. There is no password or
lockscreen authentication path. Both images containing a generic ramdisk
(`boot.img`, `init_boot.img`) and the vendor ramdisk in `vendor_boot.img`
are byte-identical. `scripts/verify-bootimg.sh` unpacks the ramdisk, checks
the binary, license notices, public key, startup bind address and matching
ramdisks. Built on the host only; no physical boot or SSH measurement.
Two consecutive builds with the same public key produced identical images;
`verify-bootimg.sh` passed against the unpacked images and read-only stock
references. Final hashes (artifacts are outside this repository):

| file | sha256 |
| --- | --- |
| `$WORK/out/boot.img` | `5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb` |
| `$WORK/out/init_boot.img` | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `$WORK/out/vendor_boot.img` | `bde3a3b3bc7ea587f195de63de76db5f14f8dfd197d6d3224904f722af18fd31` |
| `$WORK/out/initramfs.cpio.gz` | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

### #10 full-chain diagnosis and host-only DTB correction (2026-10-20)

The failed #8 physical attempt and the distinction between evidence and
hypotheses are recorded in [BOOT.md](BOOT.md). These are parsed structural
facts from SHA-256-verified read-only stock slot-A backups versus the #8 images;
no backup or raw capture is published. `$WORK/out/bootimg-verify.txt` and
`$WORK/out/issue-10-verify.log` are host-only verification references, not
public attachments.

| field | verified stock | failed #8 set | #10 host-only set |
| --- | --- | --- | --- |
| `boot` bytes | 100663296 | 16777216 | 16777216 |
| `init_boot` bytes | 8388608 | 1679360 | 1679360 |
| `vendor_boot` bytes | 100663296 | 10387456 | 11108352 |
| boot/init vendor page size and kernel/ramdisk/tags/DTB load addresses | 4096; `0x8000` / `0x1000000` / `0x100` / `0x1f00000` | same | same |
| header version / boot+init header bytes / vendor header bytes | 4 / 1584 / 2128 | same | same |
| kernel gzip bytes, offset | 13949926 at 4096 | 15097006 at 4096 | same as #8 |
| `boot` ramdisk bytes | 0 | 1672600 | same as #8 |
| `init_boot` ramdisk bytes, offset | 2113581 at 4096 (LZ4 legacy) | 1672600 at 4096 (gzip) | same as #8 |
| vendor ramdisk bytes, offset | 8821389 at 4096 (LZ4 legacy) | 1672600 at 4096 (gzip) | same as #8 |
| vendor DTB bytes, offset | 9419891 at 8826880 | 8696042 at 1679360 | 9419891 at 1679360 |
| vendor ramdisk table / bootconfig offsets | 18247680 / 18251776 | 10379264 / 10383360 | 11100160 / 11104256 |
| OS version/patch-level field | 0 | 0 | 0 |

The boot and init_boot cmdlines are empty in stock; #8/#10 boot has a
169-byte diagnostic cmdline and init_boot remains empty. The vendor cmdline
changes from 113 to 101 bytes for earlycon and panic diagnostics. Both vendor
ramdisk tables have one 108-byte, unnamed PLATFORM fragment at ramdisk offset
zero with zero board IDs. All three bootconfig payloads are byte-identical to
the 175-byte stock payload (SHA-256
`2411fccec1d3e10a7cefe916abd38cf81d4deb5f93f510dce675b1ec91796457`).
The gzip/LZ4 difference is not proof of bootloader rejection. The stock kernel
is 6.1.84; the baseline kernel is 6.1.78 and is not binary-identical.

Stock DTB index 9 is 435290 bytes (2818 nodes, 11993 properties); #8 index 9
is 358368 bytes (2504 nodes, 9697 properties). Indices 0–8 matched stock.
The unchanged stock `dtbo_a` entry 65 is 209313 bytes at offset 18486288
in a 76-entry table. Its 143 fixup symbols all resolve against stock index 9;
32 symbols referenced at 82 sites across 29 fragments are missing from #8
index 9. Applying stock DTBO 65 to #8 index 9 in memory returned
`FDT_ERR_NOTFOUND`; applying it to the stock index 9 succeeded. The generated
QRD Pro overlay is 28629 bytes and applies to the generated base but was not
packed in the flashed `dtbo`. The #10 correction copies the verified stock
20-DTB blob verbatim into `vendor_boot`; the new verifier rejects drift in any
entry and runs `fdtoverlay` on stock entry 65 and selected index 9, checking
the overlaid ramoops reservation. This is a reproducible fix for the observed
DTB/DTBO incompatibility, not evidence that it caused the fastboot return.

Each stock partition is full-sized and has an `AVBf` footer at size minus 64.
The footer records original image sizes of 13971456 (`boot`), 2121728
(`init_boot`) and 18255872 (`vendor_boot`), with embedded vbmeta at those
offsets (2496, 832 and 640 bytes respectively). Stock `boot` additionally
has a 16384-byte AVB0 region at the aligned payload boundary, distinct from
the footer-referenced vbmeta. The generated images lack these structures.
Stock `vbmeta_a` (SHA-256
`cc1926d2aa8e9c12df6a469111bf87f1e61e70022b84626fabcd014ae33cdffe`)
has a boot chain descriptor (rollback location 3) and hash descriptors for
`dtbo`, `init_boot` and `vendor_boot` (flags zero); its root and stock embedded
salted SHA-256 hashes match the stock image prefixes. The generated prefixes
do not match. The automated checker validates the stock hashes, bounds and
links but does not cryptographically validate signatures or infer bootloader
policy; the older locked/green property capture does not describe the attempt.
Do not conflate a missing footer with the cause, or treat this artifact set as
a flash approval.

Host-only build and `scripts/verify-bootimg.sh` passed after the DTB change:

| artifact | sha256 |
| --- | --- |
| `$WORK/out/boot.img` (unchanged from #8) | `5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb` |
| `$WORK/out/init_boot.img` (unchanged from #8) | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `$WORK/out/vendor_boot.img` | `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| `$WORK/out/dtb.img` | `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |

The old set fails the new equality check against stock DTBs; the new set
passes the full verifier, including stock overlay application. The verifier's
AVB check is structural/hash-only; it does not validate signatures or prove
that the bootloader accepts an unlocked-device mismatch. All images and
logs remain outside Git. No physical operation was performed for #10.

### #12 corrected-chain physical result and host-only boundary audit

The corrected #10 image set above was tested once under the separate physical
coordinator's slot-A approval on 2026-10-20, and returned to fastboot within
five seconds despite successful writes. Stock rollback was verified and stock
Android booted. The attempt's host-only recovery pstore contains only a later
stock 6.1.84 kernel banner; neither rejection nor attempted-kernel hand-off
can be inferred. The #10 DTBO correction was not the sole cause of the return.
`BOOT.md` separates these observations from AVB and early-kernel hypotheses
and specifies the conditional measurement/rollback boundary. The current
`verify-bootimg.sh` now also checks the separate 16-KiB stock boot AVB0
record's salted kernel-prefix hash and the stock zero verification flags,
without claiming signature verification or bootloader acceptance. The host
verifier passes on the unchanged #10 artifacts; **no new images were built,
verified for flash, or submitted for another test**. See the host-only
`$WORK/out/bootimg-verify.txt` report; no raw capture or device data is
published. A supported attempt-specific read-only verdict is not present in
the preserved records, so the failure boundary remains unresolved.

### Recorded hashes (before the sshd update)

Built on 2026-10-19 with the pinned busybox package; `scripts/verify-bootimg.sh`
reported all checks OK. Stock hashes are identifiers of the read-only
reference, not files in git.

| file | sha256 |
| --- | --- |
| `$WORK/out/boot.img` (superseded by the boot-chain fix below) | `7cd886a24121c878a62839424b6b7f88840ba7504eb09cd0720eec96cb8ecfe5` |
| `$WORK/out/initramfs.cpio.gz` | `c4f7dbee6d3770b0991b891f6f9a7d9b3685ed3dec3d28cbddfdc0f6b9b50244` |
| `$WORK/out/Image.gz` | `159a970903ffbf2012d706099f67703ad6c5d7e31f83441deff363e80eaacc8f` |
| `$WORK/out/Image` | `b289b9f19171db2b110c51e98f883cf1c824c8374983c9e95e51d9194df7140f` |
| stock `boot_a.img` | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` |
| stock `vendor_boot_a.img` | `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` |
| stock `dtbo_a.img` | `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992` |
