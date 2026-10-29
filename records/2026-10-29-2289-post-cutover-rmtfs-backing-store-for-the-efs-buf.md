---
date: 2026-10-29
issue: omnipha/linux-sm7635#155
subsystem: modem
result: inconclusive
source: BOOT.md
---
## Post-cutover rmtfs backing store for the EFS buffer (#155, host-only, 2026-10-29)

**Host-only diagnosis and one fail-closed script delta — no device operation, flash, partition write, new image SHA or modem-start claim.** Run 54 is closed and its image is never reflashed. Its capture (`attempt-20261028-2354-initboot-pid1-run54/capture/kmsg.log`) shows the measured #96 rmtfs environment before cutover and the fatal after it:

| input | before cutover (capture line) | after `switch_root` |
| --- | --- | --- |
| `pd-mapper`, `tqftpserv`, `rmtfs` processes and QRTR publish | `kmsg.log:2422-2424` reconstructed the three binaries; `:2434-2435` and `:2446` launched and published pd-mapper/tqftpserv; `:2454-2455` launched rmtfs pid 628 and recorded its QRTR publish | processes survive, because they are not children of the switched PID 1. `scripts/pmos-radio-bringup.sh` previously proved only a copied `/run/rmtfs.status` marker (`:56-57`) plus a `ps` name match |
| `/dev/uio0` from stock `msm_sharedmem.ko` | `kmsg.log:2449-2451`: `Device created for client 'rmtfs'`, module loaded, `/dev/uio0` ready | the kernel module and the rmtfs mapping survive. The device node lives in the old root's devtmpfs, which `scripts/pmos-pid1-transition.sh:166` `switch_root` deletes; the guest `/dev` is a separate tmpfs |
| read-only `modemst1`/`modemst2` backing | `kmsg.log:2453`: `/boot/modemst1 -> sdf2`, `/boot/modemst2 -> sdf3` | same deletion. The pinned rmtfs opens `/boot/modemst1` and `/boot/modemst2` only when the modem requests storage, so the copied status file does not prove the backing store is reachable |
| read-only `modem_a` firmware | `kmsg.log:2313` mounted it; `:2485` then showed `modem.mdt` error -2 | fixed by the #154 bind. The corrected start at `:2500-2504` reached `now up`, then `:2512` recorded `fs_device_efs_rmts.c:161 EFS rmts_get_buffer api failed` |

The one change is in `scripts/pmos-radio-bringup.sh`, before the existing one-shot modem marker. `prepare` now requires exactly one process whose executable matches the pinned #96 rmtfs (`d66204e7…`), whose own `/run/rmtfs.log` records both the stock UIO map and the QRTR publish, whose `/proc/<pid>/maps` holds `/dev/uio0`, and whose own root still has readable `sdf2`/`sdf3` nodes linked from `/boot/modemst1` and `/boot/modemst2`. It copies that log and PID into guest RAM, because `switch_root` removes the old `/run`. The post-cutover `modem` stage checks that same PID, the copied log and the live mapping, then recreates only a missing `/dev/uio0`, `/dev/block/sdf2`, `/dev/block/sdf3` or `/boot/modemst*` link inside that surviving process root from the live sysfs numbers. A wrong PARTNAME, unreadable node, missing mapping, missing log or non-pinned executable fails before `modem.attempted` is written. The copied status files alone do not pass. No second rmtfs is started and the modem is not started by the host fixture.

**This is a hypothesis, not a measured cause.** The capture proves the fatal and the pre-cutover state, not the rmtfs side of the failed request: the run-54 rmtfs log is not in the host capture, and a running rmtfs already holds its UIO mapping and QRTR socket, so the deleted nodes may not be what failed `rmts_get_buffer`. What the host change guarantees is that the first request no longer depends on an unverified, deleted path, and that the one session records the first missing line if the fatal returns. In that session the worker reads the guest-side rmtfs process and the copied `/run/radio-bringup/rmtfs.log` after the single guarded start, so a repeat of `fs_device_efs_rmts.c:161` can be attributed to a named rmtfs input instead of being guessed.

`sh scripts/test-pmos-radio-bringup.sh` covers the existing radio stages plus the missing-UIO, missing-prepared-PID, missing-publish-log, missing-UIO-mapping, wrong-PARTNAME, unreadable-backing, non-pinned-executable and missing-firmware refusals, then one positive restore of the deleted UIO node, block node and both backing links. It proves the host ordering only. It does not claim the modem stays up past the EFS request; that remains the one coordinator-held measurement, and #155 stays open for it.
