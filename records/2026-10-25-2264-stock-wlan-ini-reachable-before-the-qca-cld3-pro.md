---
date: 2026-10-25
issue: omnipha/linux-sm7635#106
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Stock WLAN INI reachable before the qca_cld3 probe (#106, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. The measured run-37
(`d9d8d2b8`), run-36 (`bf2089c4`) and every previously measured SHA are rejected
for reuse. No flash, boot, remoteproc start, key-only SSH, module reload or other
device operation was performed; only the physical coordinator executes the
packaged trigger under the standing `full_autonomy_device_iteration` approval,
after the capture selftest.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-wlan-ini.img` | 8,388,608 | `e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c` |

### (1) The exact file set the probe needs at `cfg_parse` (confirmed from host artifacts)

The pinned vendor tree (NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, read-only) fixes the probe's read:
`__hdd_soc_probe` → `hdd_context_create` → `cfg_parse(WLAN_INI_FILE)`
(`wlan_hdd_main.c:14682`), where `WLAN_INI_FILE` is
`"wlan/qca_cld/" PREFIX "WCNSS_qcom_cfg.ini"` (`wlan_hdd_misc.h:44-45`) with
`PREFIX = DYNAMIC_SINGLE_CHIP "/"` = `qca6750/` — matching the chip-named module
`qca_cld3_qca6750.ko` measured at run-37 `kmsg:2376`. `cfg_parse` reads it
through the kernel firmware loader (`qdf_file.c:28-59`:
`firmware_request_nowarn(&fw, path, NULL)` at `:56`), whose search order is the
four `firmware_class.path` entries followed by `/lib/firmware*`
(`firmware_loader/main.c:473-488`, split on `,` at `:491-522`). A failed read
returns `QDF_STATUS_E_FAILURE` (`qdf_file.c:58`), which
`qdf_status_to_os_return`'s `default:` branch maps to `-EPERM`
(`qdf_status.c:91-93`) — exactly the run-37 `-1` (`kmsg:2488`).

Read-only extraction of the measured `vendor_a` extent
(`super.img` @ offset 5678039040, erofs) with `dump.erofs` proves the stock
install layout, matching `qcacld-3.0/Android.mk:228-229,366-369`
(`TARGET_FW_DIR := firmware/wlan/qca_cld/$(LOCAL_CHIP_NAME)`,
`TARGET_CFG_PATH := /vendor/etc/wifi/$(LOCAL_CHIP_NAME)`, and the
`symlink-file` of `$(TARGET_CFG_PATH)/WCNSS_qcom_cfg.ini` at
`$(TARGET_FW_PATH)/WCNSS_qcom_cfg.ini`):

- `/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini` — erofs symlink (43 B),
  target `/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini`.
- `/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` — erofs regular file, **2095 B,
  SHA-256 `57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4`**
  (header `gDot11Mode=0`); this is the symlink's target, present in the same
  partition, so the chain is closed on `vendor_a` alone.
- The `/vendor/firmware` directory entry itself is present in `vendor_a`
  (stock serves the INI from it; the run-37 initramfs never created it, per
  #104 §3).

**`wlan_mac.bin` is excluded, per the issue's condition.** Its stock twin at
`/firmware/wlan/qca_cld/qca6750/wlan_mac.bin` is a symlink (40 B) whose target
is `/mnt/vendor/persist/qca6750/wlan_mac.bin` — the **persist** partition, not
`vendor_a`, so it is not in the existing host artifacts and cannot be exposed by
this change. More importantly the probe chain reads it only at
`hdd_initialize_mac_address` (`wlan_hdd_main.c:15780-15801`), *after*
`hdd_platform_wlan_mac` (`:15680-15736`), and the latter succeeds on this
`use-nv-mac` board via the DMS MAC already received in run 37 (`kmsg:2487`);
`hdd_update_mac_config` (the `wlan_mac.bin` reader, `:15800`) is reached only if
the platform MAC path fails, which it did not. So no discriminating line between
`cfg_parse` and the next fallible step reads `wlan_mac.bin`. The INI and its
`vendor_a` target are the complete file set for this step.

### (2) The single change and why it is single-variable against #101

The measured #101 session init (run-37 `d9d8d2b8`) mounts `vendor_a` read-only at
`/mnt/vendor` in its unchanged wlan-init phase, but never creates
`/vendor/firmware`, so the stock INI is `ENOENT` on every `firmware_class.path`
entry (#104 §3). The candidate adds **one bounded, read-only bind** inside that
same wlan-init phase, after the `vendor_a` mount and **immediately before** the
`modem_a` vfat mount and `wlog "module load begin"` (i.e. before the 21-module
WLAN closure insmods `qca_cld3_qca6750.ko` and its probe can run):

```
mkdir -p /vendor
mount --bind /mnt/vendor /vendor
mount -o remount,bind,ro /vendor   # read-only, fail-closed
# then: sha256 of /vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini
#       must equal the pinned 57989aba… (2095 B) — logged, never modified
```

This is one read-only mount inside the session init — nothing else. Because the
stock firmware entry and the symlink target are both inside the already-mounted
`vendor_a` root, one bind exposes both ends of the stock layout at their stock
absolute paths. The kernel firmware loader therefore finds the INI through the
existing `/vendor/firmware` entry of `firmware_class.path` (the path is already
set identically in stock and run 37; it is not edited), and the absolute symlink
resolves to the real `vendor_a` file. The bind is remounted read-only and the
phase only writes to tmpfs mountpoints and `/dev/kmsg`; it never writes
`vendor_a`, never loads or unloads a module, and writes no remoteproc or icnss2
state. The bind precedes the `modem_a` vfat mount, so the existing
`/vendor/firmware_mnt` mount covers the stock `firmware_mnt` directory entry and
the later read-only `/vendor/firmware_mnt/image` → `/lib/firmware` bind is
unchanged.

Single-variable against the measured #101 init: the candidate cpio equals the
run-37 `d9d8d2b8` cpio with **only** the `init` entry changed, and that init is
byte-for-byte the run-37 init with the one INI phase inserted and the session
marker reworded. Everything the issue pins is unchanged: the modem-holding stack
(recon/qrtr/rmtfs phases, pd-mapper/tqftpserv/rmtfs binaries), the 21-module
WLAN closure and its load order, the one-shot WPSS trigger `bin/wpss-once`
(`16d4747e…`, byte-exact), the USB/key-only SSH path and the armed 150 s
recovery timer. No second variable: the change touches no partition, no module,
no remoteproc and no service — it exposes one already-mounted stock filesystem
through the already-present search path, before the closure loads.

### (3) Envelope, verifier and gates

Debug cpio 3,671,040 B (zero `.ko`), one LZ4 HC-12 legacy frame 2,095,841 B of
2,117,632 B (21,791 B spare), stock header except the ramdisk-size field, zero
gap, unchanged stock signed tail from offset 2,121,728 (6,266,880 B), fixed
8,388,608-B image. `scripts/verify-init-boot-wlan-ini.py` proves the byte-exact
run-37 half and the single-init delta, rebuilds the cpio and frame, checks the
envelope/prefix/gap/tail/size and rejects, via host-generated negative fixtures:
a changed tail, nonzero kernel size, changed block, wrong ramdisk-size, nonzero
gap, short image; the INI phase removed, duplicated, moved after the closure,
its bind made writable, its bind retargeted, its SHA pin removed; the marker
removed; and the run-37 layout or SHA reused; plus every prior measured SHA
(explicitly `d9d8d2b8`, `bf2089c4`, `8dddb8c7`, `35866d56`, `ae2ccff7`,
`4216af26`). Two serial builds produce byte-identical images (`cmp`). Wired into
`scripts/verify-bootimg.sh` with `--self-test` and normal invocations.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wlan-ini.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

### Predicted physical outcomes (not observations)

The physical coordinator flashes the new `e75c5bd2…` SHA to `init_boot_a` only,
pins `172.16.42.1/24` on the NCM link, and passes the capture selftest
(omnipha/agents#16 gate) first. Then confirm the #101 precondition exactly
(sharedmem client present, rmtfs on QRTR, pd-mapper + tqftpserv published), one
guarded `remoteproc2` start, modem held past +60 s, DMS connect allowed up to
+150 s, then the single one-shot WPSS trigger (`/bin/wpss-once`) with continuous
host-side capture through the probe window. Record `wlan0`, the `icnss2` probe
line, and every new `qca6750:`/HDD/firmware-loader line. Recovery stays the
measured path: armed timer to fastboot, then verified five-partition stock
rollback. The new SHA becomes measured/never-reflash on first flash. No module
reload, no second WPSS attempt, no second variable, no partition writes.

- **(a)** the probe passes `cfg_parse` and the HDD chain continues — new
  `qca6750:` kmsg lines or `wlan0` — the INI cause is confirmed.
- **(b)** the probe fails again at a later fallible step — the INI cause is
  confirmed for this step and the new line names the next blocker.
- **(c)** an identical silent `-1` with no new lines — the INI hypothesis is
  weakened and QDF-trace observability becomes the successor question.

Any physical result requires the coordinator's measured recovery and verified
five-partition stock rollback. `e75c5bd2`, `d9d8d2b8` and every previously
measured SHA are never-reflash after the run. The measured result is recorded
above as run 38, outcome (a): `cfg_parse` passed and `wlan0` was registered,
operstate down after the psoc-idle timeout; the stock rollback is verified.
