# SM7635 modem firmware initialization dependency (issue #85)

Host-only report, existing artifacts only. All paths below are relative to the
read-only build-host reference `~/phone-second-life-data/mb003` unless the path
starts with `initramfs/` or `scripts/` (this repository, `main` @
`c5811e7c695d7bddc532378add605a1de5721900`). No device access, flash, kernel
rebuild or new image was used; every quoted timestamp is a verbatim artifact
line.

## 1. Every kmsg record between "now up" and the DOG fatal (run 34)

Source: `pstore/attempt-20261025-0248-initboot-retrymarker/capture/kmsg.log`
(raw `/dev/kmsg` uapi stream, `level,seq,timestamp_us` format; the captured
session is run 34, image `35866d56`, selftest marker
`sm7635_capture_selftest_1792889636_211395` at kmsg.log:2434). There are
**exactly six kernel records** in the interval; nothing else was logged
between the modem reaching running and the fatal:

| kmsg line | level,seq,monotonic | message |
| --- | --- | --- |
| 2445 | 6,1480,220404698 | `remoteproc remoteproc2: remote processor 4080000.remoteproc-mss is now up` |
| 2448 | 6,1481,220405387 | `qcom_smd_qrtr_probe: SMD QRTR driver probed` |
| 2450 | 3,1482,220406029 | `arm-smmu 3da0000.kgsl-smmu: Couldn't get clock: gpu_cc_hlos1_vote_gpu_smmu` (GPU SMMU, unrelated to MSS) |
| 2452 | 3,1483,260432833 | `qcom_q6v5_pas 4080000.remoteproc-mss: fatal error received: dog_hal_common.c:178:DOG detects stalled initialization, triage with IMAGE OWNER` |
| 2455 | 3,1484,260432865 | `qcom_q6v5_pas 4080000.remoteproc-mss: rproc recovery state: disabled and lead to device crash` |
| 2458 | 6,1485,260432895 | `qcom_q6v5_pas 4080000.remoteproc-mss: Incrementing tid for modem to 1` |

Facts this interval fixes:

- `now up` at 220.404698 s, DOG fatal at 260.432833 s → **40.028 s of silence**
  on the remoteproc/QRTR path after the SMD QRTR probe. This is a modem-image
  internal watchdog (DOG = image-owner side), not a kernel-side remoteproc
  timeout.
- No firmware-load error, no PIL/auth error, no SMD/glink error appears in the
  interval. The kernel-side bring-up completed; whatever stalled was waiting
  for something the kernel log never shows.
- Host-side corroboration (same attempt dir): `stageE-observe.log:1-7` shows
  the modem `running` with `wlan0 absent` and SSH alive through 02:55:18+02:00,
  `stageE-observe.log:8` SSH dead at 02:55:23, `stageE-observe.log:18` crash
  mode (`usb=05c6:900e`) at 02:56:04 — the crash follows the fatal, not the
  start.

Earlier runs agree on the same stall window:

- Run 31, `pstore/attempt-20261024-1924-initboot-modemstart/pstore/console-ramoops-0:1450`:
  `now up` at 2.547 s; `:1484` DOG fatal at 42.579 s (40.03 s later, same
  window), `:1487` `Kernel panic - not syncing: Panicking, remoteproc
  4080000.remoteproc-mss crashed`. Run 31 started the modem from the
  initramfs *without* the capture gate; run 34 from the live session; the
  40 s DOG window is identical in both, i.e. it does not depend on how or when
  the start was issued.
- Run 33, `pstore/attempt-20261025-0102-initboot-fatalstream/capture/kmsg.log:2358`:
  the remoteproc never left `is available` in that stream (guarded start lost);
  no contradiction.
- Stock Android boots (`pstore/console-ramoops-0:6114` and
  `pstore/attempt-20261022-1305-boota-imagesize/pstore/console-ramoops-0:6137`)
  reach `now up` with **no DOG fatal at all** — the stall is specific to the
  minimal-session boots, not to the image or the slot.

## 2. Modem firmware set actually booted, memory regions, PIL prerequisites

- Slot: `getprop.txt:542` `ro.boot.slot_suffix=[_a]`; firmware mount
  `getprop.txt:154` `dev.mnt.blk.vendor.firmware_mnt=[sde6]` (= `modem_a`,
  `by-name.txt:50`).
- Image: `modem.mdt`, header size 6284 bytes — kmsg.log:2441 and stock
  `console-ramoops-0:5257`/`5299` (`Booting fw image modem.mdt, size 6284`).
  The stock boot then loads 27 `modem.bXX` segments by name through the sysfs
  firmware fallback, all found under `/vendor/firmware_mnt/image/` (stock
  `console-ramoops-0:5271-5273` and following; full segment name list
  extractable from that log: b01-b07, b08-b13, b15-b20, b22-b28, b30 — 27
  segments plus the mdt). The exact per-segment file sizes are **not** in any
  host artifact; the `modem_a` partition image itself was never dumped (parts/
  holds only boot/init_boot/vendor_boot/dtbo/recovery/vbmeta sets,
  `parts.sha256`), so the on-disk firmware set is only evidenced by these
  load-log names and the mdt header size. Open point, not a claim.
- Declared memory regions (`dtb/live-fdt.dts`):
  - `mpss_region@8ac00000`, 0xe600000 (235520 KiB) no-map — :269-272
    (phandle 0x77), confirmed by the reserved-mem log line
    `console-ramoops-0:62`.
  - `q6_mpss_dtb_region@99200000`, 0x80000 (512 KiB) no-map — :275-278
    (phandle 0x78), `console-ramoops-0:63`.
  - `linux,cma` (phandle 0x79) — third `memory-region` entry of the node.
  - `remoteproc-mss@04080000` node :6808-6851: compatible
    `qcom,volcano-modem-pas`, `memory-region = <0x77 0x78 0x79>`, six
    interrupts (wdog/fatal/handover/ready/stop-ack/shutdown-ack), glink-edge
    `mpss` with `qcom,modem_qrtr` (channel `IPCRTR`).
- PIL/auth prerequisites: `qcom-scm` convention established
  (kmsg.log:1372-1373), `mdt_loader.ko` loaded (kmsg.log:1380-1382),
  `qcom_q6v5_pas 4080000.remoteproc-mss: assigned reserved memory node
  linux,cma` (kmsg.log:2354). The modem passed PIL auth and reached `now up`
  in every run: any PIL/auth prerequisite was satisfied. Stock fstab confirms
  the mount: `vendor_a` image `etc/fstab.qcom:63` mounts by-name `modem` at
  `/vendor/firmware_mnt` vfat read-only (verified on the mounted stock
  `vendor_a` super extent; see §3 for how it was read).

Conclusion of §2: firmware set, memory regions and PIL path are identical
between the fatal runs and the healthy stock boots. They are excluded as the
stalled dependency.

## 3. Stock services/DT nodes touching the modem; which are absent in our session

Stock `vendor_a` was read read-only from the verified `super-dump/super.img`
(sha256 `7307e9ff…`, same pins as `scripts/build-init-boot-wlan-closure.sh:26-28`)
by loop-mounting the vendor_a extent with the exact offset/size pair that
script uses (:95-96). Everything below is from that mounted image; nothing was
copied out.

Stock modem-touching services (all `class core`, i.e. started by `class_start
core` at `on boot` before the modem remoteproc is started):

| service | definition (stock vendor_a path:line) | binary | role |
| --- | --- | --- | --- |
| `vendor.pd_mapper` | `etc/init/hw/init.target.rc:330`; started early at `etc/init/hw/init.qti.kernel.rc:86` (`on early-boot`) and `init.target.rc:315` (charger path) | `/vendor/bin/pd-mapper` | QRTR protection-domain/service locator (servloc) server; parses `.jsn` domain maps |
| `vendor.per_mgr` | `etc/init/hw/init.target.rc:336` | `/vendor/bin/pm-service` | peripheral-manager QMI service |
| `vendor.per_proxy` | `etc/init/hw/init.target.rc:342` (started when per_mgr is running, :357-358) | `/vendor/bin/pm-proxy` | SSR shutdown proxy |
| `vendor.rmt_storage` | `etc/init/vendor.qti.rmt_storage.rc:7` | `/vendor/bin/rmt_storage` | remote storage (rmtfs) QMI server over QRTR |
| `vendor.tftp_server` | `etc/init/vendor.qti.tftp.rc:11` | `/vendor/bin/tftp_server` | TFTP-over-QRTR (tqftpserv-equivalent) file server |
| `qrtr-ns` | binary `bin/qrtr-ns` present; only SELinux context `etc/selinux/vendor_file_contexts:14` in init configs (started by `init.qti.kernel.sh`/other scripts) | QRTR nameserver |
| `vendor.mdm_launcher` | `etc/init/hw/init.target.rc:353` (oneshot `init.mdm.sh`) | modem helper |
| `vendor.qcrild/qcrild2/3` | `etc/init/qcrilNrd.rc:4-23` (class main, disabled) | qcrilNrd | RIL over QMI |
| `vendor.ril-daemon2/3` | `etc/init/hw/init.qcom.rc:806,813` | rild | RIL |
| `ssgqmigd` | `etc/init/hw/init.qcom.rc:722` | QMI gateway daemon |

Measured stock start order (stock `console-ramoops-0`, same in the
`attempt-20261022-1305` stock-kernel boot): `vendor.pd_mapper` :4336-4337
(5.12 s), `vendor.per_mgr` :4769-4777, `vendor.rmt_storage` :4840-4841,
`vendor.tftp_server` :4842-4845, all **before** `remoteproc3` MSS `now up`
(:6114 at 8.166 s); immediately after `now up`, `rmt_storage` serves the modem
its filesystems: `rmt_storage_open_cb: Processing: Open Request (req_h 0x1)
for /boot/modem_fs1` :6154 and `/boot/modem_fs2` :6155 at 8.22 s, and
`rmt_storage` strings name the partitions it opens (`/boot/modem_fs1`,
`/boot/modem_fs2`, `/boot/modem_fsc`, `/boot/modem_fsg` — binary strings,
`bin/rmt_storage`; the by-name map is `by-name.txt:50-53,35-36`:
`modemst1/modemst2/fsg/fsc`). Stock kernel cmdline also sets
`service_locator.enable=1` (`console-ramoops-0:139`), the same value our
session boots with (kmsg.log:141).

Kernel-side modem touchpoints and their state in our session:

| touchpoint | DT evidence | run-34 state |
| --- | --- | --- |
| `remoteproc-mss@04080000` PAS node | live-fdt.dts:6808-6851 | bound, started, reached running (kmsg.log:2445) |
| glink-edge `mpss` + `qcom,modem_qrtr` (IPCRTR) | :6830-6844 | working: `qcom_smd_qrtr_probe` at kmsg.log:2448 |
| `qcom,smp2p-modem` | :5725-5759 | smp2p.ko loaded in the session supplier phase (run-29 measurement, BOOT.md run-29 section) |
| `qcom,rmtfs_sharedmem@0` (`qcom,sharedmem-uio`, client-id 1) | :6498-6503 | **no driver**: `msm_sharedmem.ko` exists in stock `vendor_dlkm_a` (`lib/modules/msm_sharedmem.ko`, vermagic 6.1.78, alias `of:N*T*Cqcom,sharedmem-uio`) but is in **no** module list of this repo's init (`initramfs/init:40-168`, wlan closure in `scripts/build-init-boot-wlan-closure.sh`); stock boot logs `msm_sharedmem_probe: Device created for client 'rmtfs'` (`console-ramoops-0:2480`); run 34's kmsg contains **zero** `msm_sharedmem` lines |
| smem (`smem_region@81d00000`) | :224-230 | smem.ko loaded (kmsg.log:1360-1361) |

Provably absent from the read-only session init (checked against
`initramfs/init` and every `scripts/build-init-boot-*.sh` module list; the
session runs busybox + dropbear only, `initramfs/init:358-363`): **pd-mapper,
tftp_server, rmt_storage, per_mgr/per_proxy, qrtr-ns, qcrilNrd/rild, and the
msm_sharedmem/rmtfs kernel driver**. The only userspace in the session is the
USB gadget and dropbear.

## 4. Answer to the #86 cross-link questions

(a) **pd-mapper/tqftpserv hypothesis: confirmed as present-and-required in
stock, and absent in our session.** Stock runs pd-mapper (a Qualcomm servloc
rewrite, binary `bin/pd-mapper`, strings `Starting servloc server`, `Parsing
file :%s:`, `.jsn`, `sr_domain`, `sr_service`, `sr_version`) and tftp_server
(a QTI rewrite of tqftpserv, strings `Initializing tftp_server RING buffer`,
rfs folder roots) as `class core` before every stock modem start, and no stock
boot in the artifacts starts the modem without them. Our runs 31/34 started
the modem with none of them and hit the 40 s DOG stall both times. This is
correlation with exact ordering evidence, not yet a causal proof — the causal
proof is the single-variable live run in #86.

(b) **Stock domain-map source: the `.jsn` files under
`/vendor/firmware_mnt/image/` on the `modem_a` partition (vfat, `/dev/block/
sde6`).** Evidence: the stock pd-mapper binary's own search-path strings are
exactly `/vendor/firmware_mnt/image`, `/vendor/firmware_mnt/image/sdx55m`,
`sdx60m`, `sdx65m`, `/vendor/firmware/image`, `/vendor/firmware` (plus the
`.jsn` suffix and the JSON schema keys `soc`, `domain`, `subdomain`,
`provider`, `sr_version`, `sr_service` with `service`/`instance`/
`qmi_instance_id`/`service_data`). The fstab pins that mount (`fstab.qcom:63`).
**That partition image is not among the host dumps** (`parts/` covers only
boot/init_boot/vendor_boot/dtbo/recovery/vbmeta; `super-dump` is the super
partitions, not modem), and no `.jsn` file exists anywhere in the dumped
vendor/system images (only `lib64/libpdmapper.so` references the extension).
So the exact stock `.jsn` content for volcano is **not available host-side**;
obtaining it requires a read-only dump of `modem_a` (or a live stock-session
read of `/vendor/firmware_mnt/image/*.jsn`), both device-gated and outside
this issue. Recorded as an open point; #86 must not substitute a guessed map.

## 5. Ranked candidates

Ranking is by measured evidence weight: what the artifacts show present in
stock before the modem start, absent in our session, and acting inside the
40 s window.

### #1 (most probable): missing rmt_storage/rmtfs remote filesystem service (QMI over QRTR)

- Evidence: stock boots show the modem opening its persistent filesystems via
  rmt_storage **immediately after** `now up` (`console-ramoops-0:6154-6155`,
  8.22 s, ~60 ms after now-up at 8.166 s). A modem that has booted its image
  and then waits ~40 s for its NV/filesystem before declaring itself
  initialized matches the DOG window exactly. In run 34 nothing answers:
  no rmt_storage, no msm_sharedmem/rmtfs device (kmsg.log has zero matches),
  and 40.028 s later the image DOG fires.
- One confirming measurement (one later live run, #86 scope): start the modem
  with a QRTR rmtfs-equivalent answering `/boot/modem_fs1/2` (rmt_storage or
  equivalent serving modemst1/modemst2 via the by-name paths) and watch for
  the DOG fatal disappearing and the modem staying up past +60 s. One
  excluding measurement: if the modem still DOGs with rmtfs answered and
  pd-mapper/tftp also present, the filesystem hypothesis is excluded.

### #2: missing pd-mapper/servloc + tftp_server QRTR service routing (the #86 hypothesis)

- Evidence: stock starts both `class core` before the modem
  (`console-ramoops-0:4336-4337, 4842-4845` before :6114); the pd-mapper
  servloc server is how remoteproc-service clients resolve the modem's
  protection domains; both are absent in run 34. Distinct from #1: servloc
  answers *lookups*, rmt_storage answers *storage*; the DOG is inside the
  modem image, and the artifacts cannot yet say which QMI request is the one
  that times out.
- One confirming measurement: modem start with pd-mapper+tftp_server running
  but **no** rmt_storage; if the modem survives past +60 s, #2 is confirmed
  and #1 downgraded. One excluding measurement: the same run DOGging at ~40 s
  with pd-mapper/tftp present excludes #2 as the single dependency (and points
  at #1).

### #3: missing `msm_sharedmem`/rmtfs kernel device (`qcom,rmtfs_sharedmem@0`)

- Evidence: DT node exists (live-fdt.dts:6498-6503), stock driver creates the
  rmtfs client device (`console-ramoops-0:2480`), the stock module
  `msm_sharedmem.ko` is in vendor_dlkm_a but in no session module list, and
  run 34 shows no sharedmem probe. This is the kernel half of #1; it ranks
  separately because a userspace rmtfs alone cannot work without it.
- One confirming measurement: in the same #86 run, one `insmod msm_sharedmem.ko`
  (stock vendor_dlkm module) before the modem start plus the rmtfs service;
  if `Device created for client 'rmtfs'` appears and the modem survives, the
  dependency chain is confirmed. Excluded if the modem survives without it
  ever probing (pure-QRTR storage path sufficient).

### #4 (excluded by evidence): firmware set / PIL auth / memory regions / SMD-QRTR transport

- All identical and healthy in the fatal runs (§2, kmsg.log:2441-2448); no
  artifact shows any load, auth or transport failure in the window. No live
  measurement needed; excluded on existing evidence.

### Open points (named)

- Whether the DOG timeout is specifically the modem's NV/rmtfs wait or a
  servloc wait cannot be decided from host artifacts; only the #86 single-
  variable runs can.
- The stock volcano `.jsn` domain maps are not on the host (§4b); a pd-mapper
  config derived from stock artifacts is blocked on a `modem_a` read-only
  dump — device-gated, not done here.
- Run 32's own console was lost (`session-lost/evidence.txt:5-6`), so its
  fatal text is unverified; runs 31 and 34 carry the fatal evidence.
- Per-segment `modem.bXX` file sizes and hashes are unknown (no `modem_a`
  dump); only the load-order names and the 6284-byte mdt header are measured.
