---
date: 2026-10-25
issue: omnipha/linux-sm7635#101
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## One-shot WPSS firmware boot session init_boot (#101, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. The measured run-36
(`bf2089c4`) and every previously measured SHA are rejected for reuse. No flash,
boot, remoteproc start, key-only SSH or other device operation was performed;
only the physical coordinator executes the packaged trigger under the standing
`full_autonomy_device_iteration` approval, after the capture selftest.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-wpss-boot.img` | 8,388,608 | `d9d8d2b8268f1fcc8e3212b7943bf62c5a5b4b7e20f258acf80cbc76d5508076` |

### Stock bring-up chain (host-only, from the pinned vendor tree and stock artifacts)

Stock writes `1` to `/sys/kernel/icnss/wpss_boot` from
`/vendor/etc/init/init.vendor.wlan.rc` (`write /sys/kernel/icnss/wpss_boot 1`,
early-boot). `wpss_boot_store` (pinned `vendor/qcom/opensource/wlan/platform/
icnss2/main.c:4373-4396`) gates on `wpss_supported` (true on `qcom,wcn6750`,
`main.c:4896-4900`), parses `1` and `schedule_work(&wpss_loader)` (`main.c:4391`).
The worker `icnss_wpss_load` (`main.c:4348-4371`) reads `qcom,rproc-handle`,
`rproc_get_by_phandle`, and calls `rproc_boot`; on failure logs and `rproc_put`.
`wpss_pas` is `qcom,volcano-wpss-pas` (`qcom_q6v5_pas.c:2850-` match, resource
`volcano_wpss_resource` at `2838-2848`: pas_id 6, `wpss.mdt`), has no
`auto_boot` (registers as `remoteproc3`, stays offline until triggered — measured
run-36 `stage9-state.txt:21`). Stock `console-ramoops-0:4402-4416` shows the
`wpss_boot` write from init.rc powering up `9bb00000.remoteproc-wpss` via
kworker `T231` (the `wpss_loader` work), firmware direct loads failing `-13/-2`
and ueventd serving `/vendor/firmware_mnt/image/qca6750/wpss.mdt` (4844 B,
matches `extraction-manifest.txt:1055`, stock `modem_a` vfat mount);
`:5262` "WLAN FW Initialization done", `:6591` "WLAN FW is ready" ~9 s later.

Prerequisites in the #96 session state (all measured): supplier chain bound
(run-36 kmsg `supplier state: wpss bound`, `ipci gate: wpss bound`),
`remoteproc3` registered (`9bb00000.remoteproc-wpss is available`), icnss2 bound
at `17110040.qcom,wcn6750` (creates the sysfs link and `wpss_boot` attribute),
`remoteproc2` modem `running`, QMI DMS connected at +94 s (run-36 kmsg `2470`),
pd-mapper/tqftpserv/rmtfs published, and the stock WPSS firmware files
`image/qca6750/wpss.{mdt,b00..b10,b12}` (13 files, extraction manifest
`1043-1055`) already on the read-only `modem_a` vfat mount that the #96 wlan-init
phase establishes and the #86 phase bind-mounts read-only at `/lib/firmware`.
Stock has no `wpss` pd-mapper map; pd-mapper is not a WPSS bring-up prerequisite.
The stock recovery timer path stays disarmed (`recovery_disabled`,
no `qcom,wpss-self-recovery` in the stock FDT).

### Single-variable design

The candidate cpio equals the measured #96 image's cpio plus exactly one new
executable file `bin/wpss-once` (`16d4747e98085f4e0479f31ba37e516ab13bf864d263525f46cb2a32f8f55310`,
2390 B, mode 0755); the session `init`, all three static services, the maps, the
127-module order, the recovery timer, the USB/key-only SSH path and the 21-module
WLAN closure are byte-exact. `init` never writes `wpss_boot` or any remoteproc
state. The coordinator runs `/bin/wpss-once` once, only after the guarded
`remoteproc2` start has held past +60 s and QMI DMS has connected (up to +150 s)
— the same state as run 36. The helper is one-shot (`/run/wpss-once.attempted`
marker), rejects arguments or a second run, verifies `remoteproc3` name
`9bb00000.remoteproc-wpss` with state `offline` and `remoteproc2` name
`4080000.remoteproc-mss` with state `running`, requires
`/run/qrtr-services.status=qrtr-published`, `/run/rmtfs.status=rmtfs-published`,
the icnss2 driver bind and the read-only vfat `modem_a` mount in `/proc/mounts`
with all 13 stock `wpss.*` firmware files readable, and only then writes
exactly one `1\n` to `/sys/kernel/icnss/wpss_boot` under
`busybox timeout -k 1 3`, logs before/after remoteproc states to kmsg and exits.
It never writes `0` (unload path, `main.c:144-151`), never writes any
`/sys/class/remoteproc*/state`, never loads or unloads modules, never retries.
The single variable is the stock `wpss_boot=1` write in the measured run-36
state; every other input is pinned by measurement or by hash. If any
prerequisite check fails the helper exits without a write (fail closed) and the
issue records the gap instead.

### Envelope, verifier and gates

Debug cpio 3,670,016 B (zero `.ko`), one LZ4 HC-12 legacy frame 2,095,480 B of
2,117,632 B (21,152 B spare), stock header except the ramdisk-size field, zero
gap, unchanged stock signed tail from offset 2,121,728 (6,266,880 B), fixed
8,388,608-B image. `scripts/verify-init-boot-wpss-boot.py` proves the
byte-exact #96 half and the single-entry delta, rebuilds the cpio and frame,
checks the envelope/prefix/gap/tail/size and rejects, via host-generated
negative fixtures: a changed tail, nonzero kernel size, changed block, wrong
ramdisk-size, nonzero gap and short image; trigger removed, made
non-executable, byte-altered, replaced by the run-36 layout, rewritten to write
a remoteproc state, with the one-shot marker removed, with a weakened
precondition check, or with the write timeout removed; init mutations (the
init itself becoming the trigger, marker reworded in place); and every one of
the 52 prior measured SHAs (explicitly `bf2089c4`, `8dddb8c7`, `35866d56`,
`ae2ccff7`, `4216af26`). Two serial builds produce byte-identical images
(`cmp`). Wired into `scripts/verify-bootimg.sh` with `--self-test` and normal
invocations.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wpss-boot.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes, not observations:** the coordinator flashes the
new `d9d8d2b8…` SHA to `init_boot_a` only, pins `172.16.42.1/24`, passes the
capture selftest, confirms the #96 preconditions, performs the single guarded
`remoteproc2` start, lets the modem hold past +60 s and DMS connect (up to
+150 s), sets `/run/keep` so the 150 s timer stays disarmed for the session
window, then invokes `/bin/wpss-once` once with continuous host capture.
The measured result is recorded above as run 37, outcome (b): FW_READY
reached, `wlan0` absent, qca_cld3 probe ordering named as the next blocker.
(a) `ICNSS_FW_READY` reached and `wlan0` appears (`WLAN FW is ready` kmsg,
`icnss_call_driver_probe` on the FW_READY event, `main.c:1452-1493`) — the
DMS/WPSS dependency is confirmed; next question association/wpa_supplicant.
(b) `ICNSS_FW_READY` reached but `wlan0` absent — the blocker moves inside
`qca_cld3`/the firmware path; record the probe/fatal text verbatim.
(c) WPSS firmware load/fatal (`Failed to boot wpss rproc` / firmware load
error / remoteproc3 crash), the modem losing `running`, or any new fatal —
record verbatim, stop, no second attempt. A reject-exit of the helper without a
write documents a missing precondition and closes the issue on that gap without
a second attempt. Any physical result requires the coordinator's measured
recovery and verified five-partition stock rollback. `d9d8d2b8` and every
previously measured SHA are never-reflash after the run. The run-37 outcome
is recorded above; rollback was still pending in the coordinator's comment.
