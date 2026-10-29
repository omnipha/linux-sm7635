---
date: 2026-10-24
run: 24
issue: omnipha/linux-sm7635#67
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Stock WLAN closure load from super on the run-24 init (#67, host-only, 2026-10-24)

**Host success: the frozen run-24 init (initramfs/init, the #53 line) gains one
wlan-init phase that mounts the stock super logical partitions read-only and
insmods the measured stock WLAN module closure, and one new init_boot image was
assembled and verified host-only.** No device, adb, fastboot, USB, flash or
userdata operation was performed. Stock `boot_a`, `vendor_boot_a`, `dtbo`,
`vbmeta` and slot B are unchanged. The 127-module load order, the single
`peripheral` role write, the 40 × 0.25 s UDC wait, the NCM+ECM addresses
172.16.42.2/24 and 172.16.43.2/24, the key-only sshd, the 150 s `/run/keep`
timer and `bin/restart2` are unchanged. Every previously measured SHA stays
unreused; the new image SHA below is a first measurement.

### 1. The stock WLAN closure, measured from the slot-A super dump

The input is the coordinator's slot-A `super` dump (9,663,676,416 bytes, SHA-256
`7307e9ff…d8c`, matching the on-device `super` hash). Its LP metadata (magic
`0PLA` v10.2, tables SHA-256 `6450425f…a251`, identical in all six metadata
slots) names 14 logical partitions with seven single linear slot-A extents and
empty slot B. The three partitions this phase uses:

| partition | byte offset | bytes | filesystem |
| --- | ---: | ---: | --- |
| `vendor_dlkm_a` | 6,947,864,576 | 32,669,696 | erofs |
| `vendor_a` | 5,678,039,040 | 1,269,284,864 | erofs |
| `system_dlkm_a` | 4,797,235,200 | 11,804,672 | erofs |

`vendor_a/lib/modules` is a symlink to `/vendor_dlkm/lib/modules`, so every
vendor module lives in `vendor_dlkm_a`. The closure is computed from that
partition's `modules.dep` and `modules.load` for the five targets
`qcom_q6v5_pas.ko`, `qca_cld3_qca6750.ko`, `icnss2.ko`,
`cnss_plat_ipc_qmi_svc.ko` and `qrtr-smd.ko`, topologically ordered with
`modules.load` as the tie-break. The first target is the WPSS remoteproc
driver: the live FDT gives `qcom,wcn6750` a `qcom,rproc-handle` to
`remoteproc-wpss@9bb00000` (`compatible = "qcom,volcano-wpss-pas"`),
`qcom_q6v5_pas.ko` carries the matching `of:N*T*Cqcom,volcano-wpss-pas`
alias, and the measured stock console registers `9bb00000.remoteproc-wpss`
at 2.346 s, before `icnss2` probes at 2.399 s. With `fw_devlink.strict=1` on
the stock command line the icnss2 probe defers until that supplier binds, so
it belongs to the closure even though `modules.dep` does not name it. Nothing
in `modules.blocklist` names any of them (it names only `qca_cld3_kiwi`, a
module this device does not load); `modules.softdep` names `qcom_q6v5_pas`
once, as a `pre:` of the unrelated audio module `q6_notifier_dlkm`, which is
not in this closure. The closure list SHA-256 is `c4268566…af73`.

| # | module | bytes | source | status |
| ---: | --- | ---: | --- | --- |
| 1 | `qmi_helpers.ko` | 106,544 | `drivers/soc/qcom/qmi_encdec.c`, `qmi_interface.c` | already in the 127-module recovery closure |
| 2 | `qcom_ramdump.ko` | 24,736 | `drivers/soc/qcom/qcom_ramdump.c` | new, from `vendor_dlkm_a` |
| 3 | `qcom_pil_info.ko` | 18,408 | `drivers/remoteproc/qcom_pil_info.c` | new, WPSS remoteproc closure |
| 4 | `qcom_glink.ko` | 98,136 | `drivers/rpmsg/qcom_glink_native.c` | already loaded |
| 5 | `qcom_glink_smem.ko` | 19,848 | `drivers/rpmsg/qcom_glink_smem.c` | already loaded |
| 6 | `qcom_smd.ko` | 43,496 | `drivers/rpmsg/qcom_smd.c` | already loaded |
| 7 | `rproc_qcom_common.ko` | 65,912 | `drivers/remoteproc/qcom_common.c` | already loaded |
| 8 | `pdr_interface.ko` | 38,480 | `drivers/soc/qcom/pdr_interface.c` | already loaded |
| 9 | `qcom_sysmon.ko` | 45,384 | `drivers/remoteproc/qcom_sysmon.c` | new, WPSS remoteproc closure |
| 10 | `qcom_q6v5.ko` | 28,264 | `drivers/remoteproc/qcom_q6v5.c` | new, WPSS remoteproc closure |
| 11 | `qcom_q6v5_pas.ko` | 129,560 | `drivers/remoteproc/qcom_q6v5_pas.c:2919` (`qcom,volcano-wpss-pas`) | new, WPSS remoteproc supplier of icnss2 |
| 12 | `rfkill.ko` | 63,817 | `net/rfkill/core.c` | new, from `system_dlkm_a` |
| 13 | `cfg80211.ko` | 2,143,864 | `net/wireless/` | new, from `vendor_dlkm_a` |
| 14 | `qrtr-smd.ko` | 17,648 | `net/qrtr/smd.c` | new, from `vendor_dlkm_a` |
| 15 | `cnss_plat_ipc_qmi_svc.ko` | 49,448 | `vendor/qcom/opensource/wlan/platform/cnss_utils/` | new, from `vendor_dlkm_a` |
| 16 | `wlan_firmware_service.ko` | 93,336 | `vendor/qcom/opensource/wlan/platform/cnss_utils/` | new, from `vendor_dlkm_a` |
| 17 | `cnss_nl.ko` | 15,832 | `vendor/qcom/opensource/wlan/platform/cnss_genl/cnss_nl.c` | new, from `vendor_dlkm_a` |
| 18 | `cnss_prealloc.ko` | 20,400 | `vendor/qcom/opensource/wlan/platform/cnss_prealloc/` | new, from `vendor_dlkm_a` |
| 19 | `icnss2.ko` | 406,320 | `vendor/qcom/opensource/wlan/platform/icnss2/` | new, from `vendor_dlkm_a` |
| 20 | `cnss_utils.ko` | 33,288 | `vendor/qcom/opensource/wlan/platform/cnss_utils/cnss_utils.c` | new, from `vendor_dlkm_a` |
| 21 | `qca_cld3_qca6750.ko` | 17,065,984 | `vendor/qcom/opensource/wlan/qcacld-3.0/` | new, from `vendor_dlkm_a` |

The 20 vendor_dlkm modules total 20,464,888 bytes; with `rfkill.ko` the phase
loads 20,528,705 bytes. `rfkill.ko` is not in the `vendor_dlkm` closure because
`modules.dep` never names it, but `cfg80211.ko` declares `depends=rfkill` in its
`.modinfo` and imports seven `rfkill_*` symbols, and the stock console loads it
from `system_dlkm` (`…/kernel/net/rfkill/rfkill.ko`, 63,817 bytes, vermagic
`6.1.84-android14-11-gf4b0d69fdf34-ab12786779`) before cfg80211 runs. It is
therefore loaded immediately before `cfg80211.ko`, from the same super image,
rather than guessed.

Two cross-checks narrow the closure. Nine of the twenty vendor_dlkm names
(`qmi_helpers`, `qcom_ramdump`, `qcom_glink`, `qcom_glink_smem`, `qcom_smd`,
`rproc_qcom_common`, `pdr_interface`, `cfg80211`, `qrtr-smd`) also ship in the
stock `vendor_boot_a` recovery ramdisk, and all nine are byte-identical
(SHA-256) to the `vendor_dlkm_a` copies, so loading from either source is the
same stock binary. The measured stock console cross-checks the names: it shows
`q6v5_pdev`/`9bb00000.remoteproc-wpss` registering at 2.346 s,
`icnss2 17110040.qcom,wcn6750` probing at 2.399 s, `cnss_plat: CNSS Platform
IPC QMI Service is started` at 2.504 s, `qca_cld3_qca6750: Loading driver
v5.2.1.94A` at 2.605 s and `qca6750/wpss.*` firmware loads at 5.04-5.29 s on
this device, and `qrtr-smd`/`qrtr-mhi`/`cnss_plat_ipc_qmi_svc` are its measured
QMI transport set.

Unknowns, recorded rather than guessed:

- **The modem partition firmware.** The measured stock console serves
  `qca6750/bdwlan.elf` and `qca6750/wpss.*` from `/vendor/firmware_mnt/image`,
  which is the `modem_a` partition (`/dev/block/sde6`), not part of `super`.
  This image does not mount it and ships no firmware; the `wlan-init:` firmware
  name log records what the kernel actually requests.
- **The captured `config.gz` says `# CONFIG_QRTR is not set`** while
  `qrtr-smd.ko` declares `depends=qrtr` and the stock kernel loads it, so the
  trimmed config does not describe the built-in provider set. `qrtr.ko` itself
  is already in the 127-module recovery closure and is loaded before this phase.

### 2. The wlan-init phase

The phase is inserted into the frozen run-24 init immediately before
`log 'console ready'`, after the unchanged module load, role write, UDC wait,
gadget, address and listener steps. It:

1. creates `/dev/block/sda6` from `/sys/class/block/sda6/dev` if the node is
   missing, then requires `blockdev --getsize64` to return exactly
   9,663,676,416;
2. hashes five pinned 4 KiB pages of `sda6` (the LP geometry page, the LP
   metadata page and the first page of each of the three extents, each carrying
   the erofs magic) and skips every mount if any page differs;
3. maps each verified extent read-only through a loop device and mounts it
   `erofs -o ro,nosuid,nodev,noexec`, falling back to
   `ext4 -o ro,noload,nosuid,nodev,noexec` only if erofs fails;
4. walks the 21-module list in the order above, skips a module that is already
   present under `/sys/module`, and otherwise `insmod`s it from `vendor_dlkm_a`
   (or from the pinned `system_dlkm_a` path for `rfkill.ko`), logging
   `wlan-init: module <name> loaded`, `loaded (already present)` or
   `failed: <err>` (a module whose file is absent is logged as
   `failed: missing <path>`) with the log count capped at 64;
5. logs whether `/sys/class/net/wlan0` exists and whether `iw dev` is available
   in busybox, then scans `dmesg` for `icnss2|cnss_plat|qca_cld3|bdwlan` lines
   and for firmware-load names, each capped at 64, logging names only.

Every step is time-bounded: 2 s (+ 1 s kill grace) for the size check, each
page hash and each `losetup`; 3 s for each mount and for the `dmesg` scan; 2 s
(+ 1 s kill grace) for each `insmod`.

### 3. Timer-budget arithmetic

The 150 s `/run/keep` timer is unchanged. The measured anchors are the run-24
console reaching `console ready` at 1.415 s
(`attempt-20261023-1624-initboot-staticaddress`) and the stock WLAN sequence
(`attempt-20261022-1305-boota-imagesize`): `icnss2` probed at 2.399 s,
`qca_cld3_qca6750: Loading driver` at 2.605 s, `qca6750/bdwlan.elf` served at
5.734 s and `WLAN FW Initialization done` at 5.748 s — about 3.35 s of
WLAN-specific work once the drivers are resident. The worst case the new bounds
allow is 3 s for the size check, 15 s for the five page hashes, 9 s for the
three loop setups, 24 s for the three erofs mounts and their ext4 fallbacks, 63
s for the twenty-one module loads and 4 s for the dmesg scan: 118 s, which still
leaves 32 s of the 150 s budget for the unchanged USB and SSH path. The measured
sequence needs far less than that, so the timer constant is not raised.

### 4. The image

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `init_boot-wlan-closure.img` | 8,388,608 | `2faab7e2d4069d5f908e292d0a5d17e0be86a09ce91efc9e6aececfb0c6872bf` |

The image keeps the stock `init_boot_a` prefix apart from the ramdisk-size
field, carries one Android LZ4 legacy frame (LZ4 HC level 12, 1,933,289 bytes,
one block) of the debug cpio at offset 4096, a zero gap, and the stock signed
tail unchanged from offset 2,121,728. The debug cpio is 3,494,912 bytes, SHA-256
`b27a58cd…cdaf1`, and contains zero `.ko` files: every module is read from the
stock partitions at boot. Two consecutive builds are byte-identical.

`scripts/verify-init-boot-wlan-closure.py` fails closed. Its negative fixtures
reject a wrong WLAN module order, a planted `.ko`, a removed mount, a writable
mount flag, a removed or lengthened timer, a changed sshd, a changed address, a
changed gadget function, a second role write, a changed 127-module order,
removed or duplicated wlan-init markers, a bad envelope or tail, and every
repeated prior SHA including `995aaca3`, `be946562` and `86402ac6`.
`scripts/verify-bootimg.sh` runs it. `bash -n`, `shellcheck`,
`python3 -m py_compile` and `git diff --check` are clean.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wlan-closure.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

### 5. Predicted pstore outcomes

For the physical coordinator, flashing `init_boot_a` = `2faab7e2…` only, with
stock `boot_a`, `vendor_boot_a`, `dtbo`, `vbmeta` and slot B untouched:

1. **SSH plus every WLAN marker through `WLAN FW Initialization done`.** The
   stock `icnss2`/`qca_cld3` driver reaches firmware initialization on the stock
   kernel with no kernel or DT change; the next step is IP configuration over
   SSH, not a new image.
2. **`icnss2` probes but no QMI or firmware marker follows.** The first blocker
   is the QMI/firmware path — expected if the unmounted `modem_a` firmware is
   what the driver needs.
3. **Module load stops at a named module.** The capped `wlan-init: module
   <name> failed:` line names it; the first blocker is version or closure.
4. **The partitions mount but no module matches.** The `failed: missing`
   lines name the absent path; the first blocker is module identification.
5. **The existing USB/SSH path regresses.** No SSH, or the gadget markers
   disappear; that is an integration bug and the experiment stops.
