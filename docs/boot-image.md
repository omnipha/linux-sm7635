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
`boot.img` differ from #18. See [INDEX.md](INDEX.md) and `records/` for the SHA set, measured
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
model, not an ABL verdict; see [INDEX.md](INDEX.md) and `records/`.
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
host control, not a boot result; see [INDEX.md](INDEX.md) and `records/`.
The #47 host-only control, `scripts/build-init-boot-self-recovering.sh`, keeps
that closure, UDC wait and gadget path and adds only a pre-`insmod` loading
marker, a `qcom-reboot-reason` bind check and an independent 150 s self-recovery
timer that calls one static arm64 RESTART2 helper. No module, gadget function or
network path is added. `scripts/verify-init-boot-self-recovering.py`, run by
`scripts/verify-bootimg.sh`, fails closed with negative fixtures. It is a host
control, not a boot result; see [INDEX.md](INDEX.md) and `records/`.
The #49 host-only control, `scripts/build-init-boot-eud-softdep.sh`, keeps the
#47 image and adds exactly one `insmod` of the stock `eud.ko`, placed after its
`modules.dep` prerequisites and immediately before `dwc3-msm.ko`, plus read-only
logging of the EUD and `a600000.ssusb` bind state. The 150 s timer, `/run/keep`
escape, helper and gadget path are unchanged.
`scripts/verify-init-boot-eud-softdep.py`, run by `scripts/verify-bootimg.sh`,
rejects a missing or misordered EUD, an unresolved softdep target, a changed old
module order, a removed timer, a bad envelope or tail and every repeated SHA
including `8f8b7331`. It is a host control, not a boot result; see
[INDEX.md](INDEX.md) and `records/`.
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
[INDEX.md](INDEX.md) and `records/`.
The #55 host-only attempt, `scripts/build-stock-config-baseline.sh`, builds the
own `6.1.78` kernel from the read-only captured stock `config.gz`, disabling
only the debug options enabled in the current own build but absent from stock
(`configs/asteroids-stock-config-debug-off.fragment`), keeping the existing USB,
pstore, panic and `sm7635-boot-marker` fragments. The resulting gzip payload
(14,782,792 bytes) misses the signed-tail bound of 13,967,360 bytes, so the
build fails closed, packages no image and records no control SHA. It is a
negative host result, not a boot result; see [INDEX.md](INDEX.md) and `records/`.
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
This is a host control, not a boot result; see [INDEX.md](INDEX.md) and `records/`.
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
This is a host control, not a boot result; see [INDEX.md](INDEX.md) and `records/`.
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
result; see [INDEX.md](INDEX.md) and `records/`.
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
[INDEX.md](INDEX.md) and `records/`.
The #40 host-only control, `scripts/build-init-boot-debug-ramdisk.sh`, copies
the verified stock slot-A `init_boot_a` and replaces only its generic ramdisk
with the existing verified debug gzip newc cpio, updating the ramdisk-size
field and zeroing the gap before the stock signed tail. It does not call
`avbtool` and does not sign. `scripts/verify-init-boot-debug-ramdisk.py`, run
by `scripts/verify-bootimg.sh`, requires the unchanged prefix apart from that
one field, the gzip newc payload, the empty kernel, the unchanged signed tail
from offset 2,121,728 and the fixed 8,388,608-byte size. It is a host control,
not a boot result.
