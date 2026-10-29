---
date: 2026-10-25
issue: omnipha/linux-sm7635#96
subsystem: modem
result: inconclusive
source: BOOT.md
---
## Stock sharedmem + pinned rmtfs session init_boot (#96, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. The #86 run already
measured `8dddb8c7…` (outcome (b): same ~40 s DOG with pd-mapper/tqftpserv
published); that SHA, `35866d56…`, `ae2ccff7…`, `4216af26…` and every other
measured SHA are rejected for reuse. No physical access, flash, remoteproc
operation, new `modem_a` read, kernel build, boot_a/dtbo/vbmeta/slot-B or other
modem-touching service change occurred in #96.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-rmtfs-sharedmem.img` | 8,388,608 | `bf2089c4f8a72591b45385829f287d24296fc88918a2b40a226ff4b1fcaede55` |
| `$HOME/sm7635-build/out/rmtfs` | 134,088 | `d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd` |

The rmtfs userspace is a static musl 1.2.5 aarch64 build from pinned upstream
sources (`qrtr` v1.2 `b51ffaf2`, `rmtfs` v1.3) with three explicit patches:
(1) the publish observability line `rmtfs: published QRTR service 14 version 1
instance 0`; (2) the non-Android libudev shared-memory path replaced by direct
sysfs/UIO handling that binds to the stock `qcom,sharedmem-uio` device created
by `msm_sharedmem.ko` (uio name `rmtfs`, `/sys/class/uio/*/maps/map0/{addr,size}`),
the `/dev/mem` fallback removed so it fails closed without the stock module;
(3) the storage table reduced to the partitions the stock binary actually opens
— stock `console-ramoops-0:6154-6155` shows exactly `/boot/modem_fs1` and
`/boot/modem_fs2`, so **only `modemst1` and `modemst2` are exposed; `fsc`/`fsg`
are not opened by the stock service and are not exposed**. Located at runtime by
the measured GPT by-name table (`by-name.txt:52-53`: `modemst1 -> /dev/block/sdf2`,
`modemst2 -> /dev/block/sdf3`): the phase creates the block nodes from
`/sys/class/block/*/dev`, confirms `PARTNAME=modemst1/modemst2` in the uevent,
and links `/boot/modemst1 -> /dev/block/sdf2`, `/boot/modemst2 -> /dev/block/sdf3`.
`rmtfs -r -P -o /boot` runs with the read-only shadow: every modem write lands
in RAM only, the partitions are never written. Both required backing partitions
are named from existing artifacts; none was missing.

The kernel half is the **stock `msm_sharedmem.ko`** — the byte-exact
`vendor_boot_a` ramdisk copy (19,568 B, `e9216dcba1295498bc8e1d17405f971d3dadd587f7c453df53512f0a7c96ac76`,
identical to the `vendor_dlkm_a` provider at the same hash, vermagic
6.1.78-android14-11-maybe-dirty) that the stock `vendor_boot` already
contributes to the combined image at `/lib/modules/msm_sharedmem.ko`. It is
never rebuilt or substituted. The new phase insmods it as-is (its
`modules.dep` prerequisites `qcom-scm`, `gh_rm_drv`, `gh_msgq`, `gh_dbl`,
`gh_arm_drv` are all inside the unchanged 127-module order), then records
whether the sharedmem client device appears (`uio` name `rmtfs`) and whether the
kernel log carries `Device created for client 'rmtfs'`. If the stock module
cannot be loaded as-is, the phase logs the exact insmod error, sets
`/run/rmtfs.status` to `failed` and no rmtfs starts — fail closed, reported,
not worked around.

The LZ4 envelope (2,117,632 B) had only 22,448 B spare and the new rmtfs binary
alone compressed to +56,764 B, so the three static services (pd-mapper,
tqftpserv from #95, rmtfs) are stored **xz-compressed** in the cpio and a
reconstruction step unpacks each one and checks its full SHA-256 against the
pinned binary hash *before* the byte-identical #86 phase runs. The #86 phase is
therefore unchanged as delivered by #95 — it launches the exact #95 binaries —
and the #96 phase (sharedmem insmod, device check, backing links, rmtfs launch)
runs strictly after the #86 phase and before `console ready`, i.e. after SSH is
up and before any remoteproc2 start. All services log to `/run`:
`/run/rmtfs.log`, `/run/rmtfs.status` (`rmtfs-published`/`failed`) plus the
unchanged #95 `/run` logs. The 127-module order, read-only mounts, WPSS
supplier/bind gate, single WLAN load, USB/key-only SSH and the 150 s
self-recovery timer are unchanged.

Two serial builds produced identical images: debug cpio 3,667,456 B (zero
`.ko`), one LZ4 HC-12 legacy frame 2,094,175 B (limit 2,117,632 B; 23,457 B
spare); stock header except the ramdisk-size field, zero gap, same stock signed
tail from offset 2,121,728 (6,266,880 B), fixed 8,388,608-B image.
`verify-init-boot-rmtfs-sharedmem.py` independently decodes and rebuilds
against the run-35 image, proves the exact init/cpio delta and the byte-exact
reconstruction of all three binaries, checks the ordering (recon before the
unchanged #86 phase, rmtfs phase after it and before console ready), the
envelope, prefix, gap, tail and size, and rejects missing/altered/nonexecutable
services, an altered stock module, missing/moved/reordered phases, missing
backing links, a removed QRTR-publish or reconstruction-hash check, an
init-time remoteproc start and all 51 previously measured SHAs (explicitly
8dddb8c7, 35866d56, ae2ccff7, 4216af26). It is wired into `verify-bootimg.sh`.

```sh
WORK="$HOME/sm7635-build" scripts/build-rmtfs-binary.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-rmtfs-sharedmem.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes, not observations:** the physical coordinator
alone (standing `full_autonomy_device_iteration` approval) flashes the **new**
`bf2089c4…` SHA to `init_boot_a` only, pins host `172.16.42.1/24`, passes the
capture selftest (omnipha/agents#16 gate), then over SSH confirms: the
reconstruction log lines, `/dev/uioN` with name `rmtfs` and the kernel
`Device created for client 'rmtfs'` line, `rmtfs` alive with
`rmtfs: published QRTR service` in `/run/rmtfs.log`, `/run/rmtfs.status` =
`rmtfs-published`, and the unchanged #95 services still published — all before
one guarded `echo start > remoteproc2/state` with continuous host capture.
(a) modem holds past +60 s and `wlan0` appears — the rmtfs/sharedmem hypothesis
is confirmed; (b) the same ~40 s DOG recurs with rmtfs published — the
rank-1 candidate is excluded as the single dependency (next candidate = new
issue, no rerun of #96); (c) new fatal text — recorded verbatim. Either result
requires the coordinator's measured Sahara reset/timer recovery and verified
stock rollback of all five partition hashes. `bf2089c4` and every previously
measured SHA are never-reflash after the run. The issue stays open until that
capture-gated single result and rollback proof are recorded.
