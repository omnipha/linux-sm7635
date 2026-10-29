---
date: 2026-10-24
run: 28
issue: omnipha/linux-sm7635#71
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Bounded icnss2/WPSS bind gate on the run-28 init (#71, host-only, 2026-10-24)

**Host success: one bounded bind gate before the final `qca_cld3_qca6750.ko`
insmod, and one new reproducible stock-envelope init_boot.** No device, adb,
fastboot, USB, flash or userdata operation was performed. No kernel, vbmeta,
dtbo or slot-B artifact changed. The 127-module order, one peripheral write,
UDC wait, NCM+ECM addresses, key-only sshd, 150 s `/run/keep` timer and
`bin/restart2` are unchanged. This section records a host candidate, not a boot
result: the physical coordinator measures it under the standing approval.

### 1. Run-28 evidence and source determination

Run 28 (`attempt-20261024-1032-initboot-wlanrfkill`, image `9291c369…`, pstore
console-ramoops-0, 119,929 bytes) reached key-only SSH at 10:35 and USB
enumeration, then returned to fastboot on the 150 s timer; rollback to stock
`init_boot_a` was verified. Measured facts from that console:

- `system_dlkm_a`, `vendor_a` and `vendor_dlkm_a` all mounted read-only erofs
  (1.532–1.544 s), `modem_a` mounted read-only vfat at `/vendor/firmware_mnt`
  and `qca6750/bdwlan.elf` was present (1.553–1.557 s).
- All 21 closure modules were logged. `qcom_q6v5_pas.ko` loaded at 1.576 s,
  `rfkill.ko` at 1.585 s, `cfg80211.ko` at 1.604 s and `icnss2.ko` at 1.636 s,
  each with no unknown-symbol error. `cfg80211` logged `failed to load
  regulatory.db` with error -2.
- `qca_cld3_qca6750: Loading driver v5.2.1.94A +PANIC_ON_BUG` at 1.691 s, then
  `wlan_pld:pld_register_driver:305:: Fail to register ipci driver` at 1.693 s,
  and the init logged `module qca_cld3_qca6750.ko failed:` at 6.802 s — 5.11 s
  later. `wlan0` was absent.
- At 11.749 s the deferred-probe list still named `9bb00000.remoteproc-wpss`,
  `17110040.qcom,wcn6750`, `3d68024.qcom,gdsc`, `soc:pm3001a-s1j` and the
  adsp/cdsp/mss remoteprocs. No panic occurred.

The stock command line carries `fw_devlink.strict=1`. In the pinned vendor tree
the ipci failure is the last transport in `pld_register_driver`
(`vendor/qcom/opensource/wlan/qcacld-3.0/core/pld/src/pld_common.c:303-307`),
which calls `icnss_register_driver`. `__icnss_register_driver`
(`vendor/qcom/opensource/wlan/platform/icnss2/main.c:3331-3376`) returns
`-EAGAIN` at `:3337-3341` when `icnss_get_plat_priv()` is NULL, and that pointer
is only set at the end of a successful `icnss_probe`
(`icnss2/main.c:5095`). The HDD loader retries only that error, 50 times at
100 ms (`qcacld-3.0/core/hdd/src/wlan_hdd_main.c:20306-20330`), which is the
measured 5.11 s gap. The platform node `qcom,wcn6750`
(`vendor/qcom/proprietary/wlan-devicetree/volcano-qca6750.dtsi:33-38`) names
`qcom,rproc-handle = <&wpss_pas>`, and `wpss_pas` is
`remoteproc-wpss@9bb00000` with `compatible = "qcom,volcano-wpss-pas"`
(`arch/arm64/boot/dts/vendor/qcom/volcano.dtsi`). `adsp_probe`
(`drivers/remoteproc/qcom_q6v5_pas.c:1621-1622`) returns `-EPROBE_DEFER` while
`qcom_scm_is_available()` is false, and the kernel prints `deferred probe
pending` when the default 10 s deferred-probe timeout fires
(`drivers/base/dd.c:306-319`).

Hypothesis, not measured: the ipci registration failed because `icnss2` had not
finished probing while its strict supplier `remoteproc-wpss` was still deferred.
The alternative, a transport or DT mismatch, is not supported by anything in the
log: the `-ENODEV` path at `icnss2/main.c:3356-3360` prints
`not supported by platform driver`, and that text is absent from the run-28
console. Both remain leads until the next measurement.

### 2. The one discriminating variable

The discriminating variable is the platform-driver bind state of
`17110040.qcom,wcn6750` (icnss2) and `9bb00000.remoteproc-wpss` at the moment
`qca_cld3_qca6750.ko` registers its ipci driver. Everything else in the run-28
init is unchanged. Immediately before that one `insmod`, and only for that
module, the init now waits at most 12 s for
`/sys/bus/platform/devices/17110040.qcom,wcn6750/driver` to appear, then logs
exactly one of `ipci gate: wpss bound` or `ipci gate: wpss unbound` and exactly
one of `ipci gate: icnss2 bound after N s` or `ipci gate: icnss2 unbound after
N s`, and then performs the same single stock `insmod`.

Expected outcomes on the next physical measurement:

| observation | lead it supports | next step |
| --- | --- | --- |
| `icnss2 bound` and `module qca_cld3_qca6750.ko loaded`, with `Registering driver` in the wlan dmesg and `wlan0 present` | supplier/probe timing: the platform probe completed inside the wait | keep the gate; the next blocker is whatever the now-visible probe logs |
| `wpss bound` but `icnss2 unbound after 12 s`, and the same ipci failure | timing is not the whole story: the supplier bound but icnss2 still did not probe | the icnss2 probe's own deferred suppliers, not the WLAN stack |
| `wpss unbound` and `icnss2 unbound after 12 s`, same ipci failure | the WPSS remoteproc never leaves deferred state in this environment | the WPSS supplier chain (`qcom_scm`, `aoss_qmp`, smem states, the also-deferred `3d68024.qcom,gdsc` and `soc:pm3001a-s1j`), not the WLAN stack |
| `icnss2 bound` yet the ipci registration still fails, with `not supported by platform driver` or `devinfo is null` in the wlan dmesg | transport/DT mismatch: the device id the module registers does not match the probed platform | the `qcom,wcn6750` compatible and the module's `pld_ipci` device table |

The 150 s timer is unchanged. Run 28 spent 5.35 s to the module-load-end line
and the USB path had already enumerated, so the worst case this gate adds is
12 s, leaving the key-only SSH path its measured margin.

### 3. The image

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `init_boot-ipci-defer.img` | 8,388,608 | `e5b99b7c04b85aee66a0ac295ee1a94a0d5dd208f8c7b0f4112fc0cd3f78fc5d` |

The image keeps the stock prefix apart from the ramdisk-size field, carries one
LZ4 HC-12 legacy frame (1,934,024 bytes) of the 3,497,472-byte debug cpio
(SHA-256 `91e36163…e6d8`) at offset 4096, a zero gap and the unchanged signed
tail from offset 2,121,728. Two separate builds are byte-identical. This SHA
differs from `9291c369`, `2faab7e2`, `995aaca3`, `be946562`, `86402ac6`,
`9f89fe8d`, `88c93077`, `8f8b7331`, `bde3a3b3`, `6078269d` and every earlier
measured image.

`scripts/verify-init-boot-ipci-defer.py` fails closed. Negative fixtures reject
a removed, duplicated, retargeted, lengthened, unbounded or post-insmod bind
gate, a removed WPSS check or gate log line, the run-27 loop-minor regression,
rfkill from the wrong partition, cfg80211 before rfkill, a planted `.ko`, a
removed or lengthened timer, a removed wlan-init marker, envelope or tail
damage, and every repeated prior SHA including `9291c369` and `2faab7e2`.
`scripts/verify-bootimg.sh` runs it. `bash -n`, `shellcheck`,
`python3 -m py_compile` and `git diff --check` are clean.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-ipci-defer.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

Physical measurement of this new SHA is owned solely by the physical
coordinator under the standing `full_autonomy_device_iteration` approval:
`init_boot_a` only, host pins `172.16.42.1/24` first, then verified rollback.
No successful boot is claimed for `e5b99b7c…` until that measurement records
key-only SSH.
