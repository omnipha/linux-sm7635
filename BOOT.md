# Temporary boot chain: diagnosis and next attempt

The 2026-10-19 analysis and historical test plan below preceded the failed
2026-10-20 full-chain slot-A attempt. Repository work never performs device
operations. The historical procedure below is not authorization to repeat it.

## 2026-10-20 full-chain attempt and host-only diagnosis (#10)

The authorized physical team confirmed the stock slot-A backups before writing
all three #8 images; the writes returned OKAY, but the reboot returned to
fastboot within seconds without USB networking or SSH. Stock slot-A images were
restored and rechecked on-device; `dtbo_a` was not changed, and stock Android
booted fully afterward. The host-only attempt records are under
`~/phone-second-life-data/mb003/pstore/attempt-20261020-0134/`; do not publish
their contents. The preserved console has one 6.1.84 stock/recovery kernel
marker and zero 6.1.78 baseline markers. The `nt_kmsg` capture has 16 6.1.84
markers and zero 6.1.78 markers; these are not 16 distinct attempt boots.
OrangeFox recovery or subsequent stock boots can overwrite ramoops, so absence
of a 6.1.78 marker does not establish that the bootloader rejected the images.
An OrangeFox recovery header or recovery marker is not evidence of the attempted
kernel either. There is no captured attempt-specific bootloader AVB verdict,
boot reason or retry counter. The older stock property capture reports locked,
green and DTB/DTBO indices 9/65, but predates this attempt; it cannot establish
the verification state during it.

The verified stock `boot_a`, `init_boot_a` and `vendor_boot_a` images each fill
the partition and have an AVB footer and embedded vbmeta. The #8 images have
neither footer nor matching stock hash; `vbmeta_a` chains `boot`, hashes
`init_boot`, `vendor_boot` and the unchanged `dtbo`. On an unlocked device,
missing footers and hash mismatches alone do not prove the reason for the
fastboot return. Stock `boot_a` additionally contains a 16,384-byte AVB0
region between the aligned boot payload and the footer-referenced embedded
vbmeta; the #8 boot image lacks it. Do not treat the header's zero signature
size as proof that these records do not matter. No alternate AVB/vbmeta images
or partition writes are proposed here.

A read-only libfdt application of the actual stock `dtbo_a` entry 65 to the
#8 `vendor_boot.img` base DTB index 9 fails `FDT_ERR_NOTFOUND`: 32 fixup
symbols referenced at 82 sites are absent from that built DTB. The same stock
overlay applies to stock index 9. The separate generated QRD Pro overlay
applies to the built base, but that overlay was *not* in the flashed chain;
checking only its model and board ID was insufficient. This is a concrete
boot-chain incompatibility, not proof of the bootloader's exact failure point.

The host-only correction for #10 copies the SHA-256-pinned stock 20-entry DTB
blob into `vendor_boot` without modifying it. The stock overlay can then apply
to index 9, and the stock overlay supplies the ramoops reservation. The
baseline 6.1.78 kernel, debug ramdisks, vendor command line and bootconfig
remain unchanged. Only `vendor_boot.img` changes from #8. The verifier checks
all 20 DTBs byte-for-byte, applies stock DTBO 65, and checks the resulting
ramoops fields and the stock AVB hash relationship; it does *not* establish
bootloader acceptance. Images and reports stay under `~/sm7635-build/out/`.

If a future physical coordinator authorizes another bounded attempt, isolate
one variable at a time: the DTB-only replacement is the first candidate, *not*
a release or a request to reflash the same #8 set. Before any later stock or
recovery boot can replace the record, correlate the attempt-specific bootloader
AVB result, boot reason, active slot and retry status with preserved kernel
markers, if the physical team can obtain them without additional writes. An
explicit AVB/slot rejection supports a bootloader-side failure; acceptance
without a 6.1.78 marker is inconclusive (very early entry or record loss are
still possible); a 6.1.78 entry establishes kernel hand-off, and its last
recorded progress distinguishes a pre-init hang from a debug-init/USB failure.
If evidence shows AVB rejection, stop before altering vbmeta or signing policy;
if the DTB-compatible set still produces no decisive record, stop rather than
repeating it or changing multiple variables. Physical tests, record capture
and stock slot-A restoration remain exclusively the coordinator's responsibility;
slot B, dtbo, vbmeta and userdata are outside #10.

## 2026-10-19 single-boot analysis

## Why the 19:00 boot produced no USB gadget

The attempt passed `boot.img`
`7cd886a24121c878a62839424b6b7f88840ba7504eb09cd0720eec96cb8ecfe5` to
`fastboot boot`. The bootloader answered `Booting OKAY` after 10.4s, no
`18d1:4ee2` gadget appeared, and the device returned to stock Android on
slot `_a` after about 35s. `Booting OKAY` only means the bootloader accepted
the image. It does not show that a kernel started.

`fastboot boot` replaces the `boot` payload and nothing else. On a header-v4
A/B device the kernel is the only thing that payload contributes. The DTB
blob, the vendor command line and the bootconfig come from the flashed
`vendor_boot`, and the board overlay comes from the flashed `dtbo`. Both
were still the stock slot `_a` images, which the bootloader's own selection
records: `ro.boot.dtb_idx=9` and `ro.boot.dtbo_idx=65`.

Checked against the unpacked stock images:

| selection | source | contents |
| --- | --- | --- |
| DTB index 9 | `vendor_boot_a`, tenth of twenty concatenated DTBs | `Qualcomm Technologies, Inc. Volcano SoC`, `compatible = "qcom,volcano"`, `qcom,msm-id = <0x27c 0x10000>`, `qcom,board-id = <0 0>` |
| DTBO index 65 | `dtbo_a`, entry 65 of 76 | `Qualcomm Technologies, Inc. Volcano QRD Pro`, the live-FDT compatible list, `qcom,board-id = <0x0b 0>`, `qcom,oem-id = <2>` |

So whatever kernel started ran on the stock DTB plus the stock DTBO overlay.
The built `boot.img` carried neither a DTB nor a command line, so the command
line was the stock one. The captured console shows it: it starts with
`console=ttynull` and ends with `rootwait ro init=/init`, and the vendor part
of it is exactly `video=vfb:640x400,bpp=32,memsize=3072000 nosoftlockup
log_buf_len=1M ignore_loglevel printk.devkmsg=on bootconfig`. There is no
`earlycon`, no `keep_bootcon` and no `panic=` in it. `chosen/stdout-path`
names the GENI debug UART, but nothing enables it.

The init path is what keeps the gadget from ever existing. The two stock
ramdisks were unpacked and listed:

| image | ramdisk | contents |
| --- | --- | --- |
| `init_boot_a` | 2113581 bytes, lz4 legacy | the generic ramdisk: `/init` (2747936 bytes), `/system/bin`, `dev` nodes |
| `vendor_boot_a` | 8821389 bytes, lz4 legacy | `first_stage_ramdisk/fstab.qcom` and 324 files under `lib/modules/*.ko`; no `/init` |
| built `boot.img` | 1032027 bytes, gzip | `/init` (the debug shell), `/bin/busybox` |

Header v4 boots the generic ramdisk from `init_boot`, and `fastboot boot`
does not replace `init_boot`. The kernel therefore ran the stock Android `/init` from `init_boot_a`, not
the debug `/init` sitting in the boot ramdisk. The console records that
hand-off at 0.169s: `Run /init as init process`, then `init: init first
stage started!`, then `init: Loading module
/lib/modules/qcom-reboot-reason.ko`. Those modules are the 6.1.84 modules
from the vendor ramdisk, and the baseline kernel is 6.1.78 built without
the stock signing key, so stock init cannot load them.

What happens after that load failure is not established. The only console
captured afterwards is the stock 6.1.84 boot described below, so there is
no record of whether stock init aborted, retried, or rebooted, and the
fallback to slot `_a` is observed only from the outside. The part that is
certain is that the debug initramfs never got control, which is why nothing
enumerated `18d1:4ee2`. Putting a ramdisk in `boot.img` cannot fix it: on
this header the generic ramdisk comes from `init_boot`.

## What the pstore file does and does not show

`~/phone-second-life-data/mb003/pstore/console-ramoops-0` (834645 bytes,
sha256 `c9c49d9244c6531ffb06560ca9c26b24b30786fdd03bc2bce7e193e80b453fd2`)
was pulled from OrangeFox after the attempt. Its first line is `Linux
version 6.1.84-android14-11-gf4b0d69fdf34-ab12786779`, built
`Wed Dec 11 19:19:40 UTC 2024` with Android clang 17.0.2. The baseline
`Image` is 6.1.78 built with Ubuntu clang 17.0.6, so this file is a stock
boot's console, not the failed boot's. `pmsg-ramoops-0` (sha256
`36b2c0669098fa7b10b03e77f7c63a7b1a8cd46431bb220b8e3180dc5aa01bfb`) is the
matching pmsg record. Neither file is committed; both stay on the build
host.

It does establish the capture mechanics. The live FDT reserves ramoops at
`0x81f20000`, size `0x400000`, with `console-size = <0x200000>` and
`pmsg-size = <0x200000>`, and the stock kernel logs `ramoops: using
0x400000@0x81f20000`. The same reservation is what the built kernel needs,
and the 19:00 attempt shows why timing matters: a later stock boot replaced
the console that would have recorded the failure.

## Diagnosability of the baseline kernel

The baseline `.config` already has `CONFIG_PSTORE=y`,
`CONFIG_PSTORE_CONSOLE=y`, `CONFIG_PSTORE_PMSG=y`, `CONFIG_PSTORE_RAM=y`,
`CONFIG_SERIAL_EARLYCON=y` and `CONFIG_SERIAL_QCOM_GENI=y`. No kernel
rebuild is needed for console capture.

The reservation is the gap. `ramoops_region` in `volcano.dtsi` carries
`size = <0x0 0x200000>` and `pmsg-size = <0x200000>` but no `reg`, so no
fixed address, and no `console-size`. The stock values come from
`volcano-arca-common-overlay.dtsi`, which `volcano-qrd-pro-overlay`
includes, and that overlay is applied from `dtbo` rather than from the DTB.
The #5/#8 build tried to add
`reg = <0x0 0x81f20000 0x0 0x400000>` and `console-size = <0x200000>`
to every built DTB, but the unchanged stock `dtbo_a` could not apply to
built index 9. The #10 build instead retains the verified stock DTB blob;
`scripts/verify-bootimg.sh` checks the ramoops reservation after applying
stock overlay 65. That reservation still cannot prove that the attempted
kernel executed or that a later stock boot did not overwrite its console.

`earlycon` needs no address. The stock index-9 DTB has `chosen/stdout-path =
"/soc/qcom,qupv3_0_geni_se@ac0000/qcom,qup_uart@a94000:115200n8"` and the
driver registers `OF_EARLYCON_DECLARE(qcom_geni, "qcom,geni-debug-uart", ...)`,
so a bare `earlycon` follows the stdout path. No UART test points or
voltages were identified, so a USB-TTL adapter is not part of this setup.
`panic=-1` makes `panic()` sit and wait instead of rebooting, which keeps
the ramoops console intact until recovery reads it.

## The corrected images

`scripts/build-bootimg.sh` writes three images to `$WORK/out`. All three
carry the same debug ramdisk, so the generic ramdisk is the debug init
whichever of `boot` or `init_boot` supplies it.

| image | contents |
| --- | --- |
| `boot.img` | header v4, gzipped baseline `Image`, debug ramdisk, command line beginning `console=ttynull` and carrying the stock bootconfig tokens |
| `init_boot.img` | header v4, empty kernel, debug ramdisk, empty command line, matching the stock `init_boot` layout |
| `vendor_boot.img` | header v4 at the stock offsets, the debug ramdisk as its single PLATFORM vendor ramdisk, the DTB blob, vendor command line `earlycon keep_bootcon loglevel=8 log_buf_len=1M ignore_loglevel printk.devkmsg=on panic=-1 bootconfig` |

At the time of the failed attempt the first nine DTBs were copied verbatim
from stock, while index 9 and the following ten Volcano DTBs were replaced by
the pinned 6.1.78 source build. The unchanged stock `dtbo_a` entry 65 cannot
apply to that index 9; see #10 diagnosis above. The current host-only build
instead retains all twenty stock DTBs, including index 9, so the unchanged
stock overlay can supply the ramoops reservation. No `dtbo.img` is produced.

Replacing the vendor ramdisk drops `first_stage_ramdisk/fstab.qcom` and the
324 stock modules from the chain. The debug init never mounts a block
device or loads a module, so it does not need them, and dropping them is
what stops stock init from loading 6.1.84 modules into a 6.1.78 kernel.

## Full-chain caveat

The standing flash gate does **not** authorize any partition writes. This
issue does not authorize any physical execution. The three-image chain below
is superseded historical context, not a procedure to run as part of this issue.

The host `fastboot` is 34.0.5 and its `boot` command downloads a single
image, so it cannot replace `init_boot` and `vendor_boot`. The bounded test
team wrote and restored all three slot-A images; `boot` and `vendor_boot`
partitions are 96MiB each and `init_boot` is 8MiB.

The verified backups are `~/phone-second-life-data/mb003/parts/`, both
slots, recorded in `parts.sha256`. Slot `_a` and slot `_b` are byte
identical for these four partitions:

| backup | sha256 |
| --- | --- |
| `boot_a.img`, `boot_b.img` | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` |
| `init_boot_a.img`, `init_boot_b.img` | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` |
| `vendor_boot_a.img`, `vendor_boot_b.img` | `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` |
| `dtbo_a.img`, `dtbo_b.img` | `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992` |

Only slot `_a` was written during the historical attempt. Slot `_b` remained
untouched and `dtbo` was not written.

The expected USB evidence is the configfs gadget enumerating as
`18d1:4ee2`, with NCM on `usb0` at `172.16.42.2/24` and ECM on `usb1` at
`172.16.43.2/24`. The serial string is the literal `sm7635`. The debug
ramdisk now includes a key-only dropbear sshd listening at `172.16.42.2:22`;
the expected result is both the gadget and an SSH login over NCM. No SSH
observation has been made on the physical device as part of this issue.

The server allows root with the single ed25519 public key from the build
host's `~/.ssh/id_ed25519.pub` (or `$PUBKEY`) packed as
`/root/.ssh/authorized_keys`. Password and PAM authentication are compiled
out; no password or lockscreen exists in the initramfs. Its host key is
generated into RAM on first connection, so it changes on every boot. No
private key is shipped in the ramdisk or committed. The console shell
remains a fallback debug path if the gadget or SSH does not work.

The earlier test plan proposed prompt preservation of ramoops before a later
stock boot could overwrite it; the 2026-10-20 capture instead contains only
stock/recovery 6.1.84 markers. `nt_kmsg` is another host-only source of
kernel evidence, not a guaranteed record of the attempted boot. Any future
physical observation and restoration require the coordinator's separate
bounded authorization. Slot B, dtbo, vbmeta and userdata are not part of
this issue.
