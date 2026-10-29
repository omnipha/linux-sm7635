---
date: 2026-10-29
run: 55
issue: omnipha/linux-sm7635#155
subsystem: modem
result: confirmed
source: BOOT.md
---
## Run-55 measured post-cutover modem hold past the EFS request (#155, 2026-10-29)

**Measured physical result — the modem stayed `running` past the EFS request that killed run 54; SSH and capture stayed healthy. No WPSS, WLAN, scan, association or reachability was attempted. The coordinator's stock rollback was later verified and #155 is closed.** The physical coordinator opened the held session on the unchanged `fef03008…` `init_boot_a` image and handed it off with a live key-only `:22` SSH and a fresh console marker. The worker independently rechecked boot ID `e8d56a15-742b-4c52-a015-f1d1cc190b89`, the pinned host key `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`, `/run/keep`, 11,243,332 kB `MemAvailable` and a live capture for that boot. Both remoteprocs were `offline`.

The SHA-pinned 134-APK archive (`7a76a110…`), stage script, guard (`dc37428e…`), transition (`0b85d1dc…`), radio script (`f9c46dee…`) and `restart2` (`fbe14729…`) were streamed into root-only RAM and hash-checked on the device. Staging produced postmarketOS v24.12 / Alpine 3.21.9 on the same stock 6.1.84 kernel and a strict-key `:2222` shell. `prepare` found exactly one pinned rmtfs process, pid 628, holding the mapped `/dev/uio0` and readable `/boot/modemst1 -> sdf2` and `/boot/modemst2 -> sdf3` links, and copied its log and PID into guest RAM. One guarded PID-1 request and the strict-key acknowledgment succeeded on this boot. Post-cutover readback showed the same boot ID, the guard accepted, OpenRC `default` with `local` started and no crashed services.

A fresh capture selftest preceded the single `modem` stage. The script reported that the surviving rmtfs still held its mapped UIO and QRTR service and that it restored only the two `/boot/modemst*` links inside that process root; the `sdf2`/`sdf3` block nodes and `/dev/uio0` were still present, so nothing else was recreated. It then wrote `start` once from `offline`. The capture shows `remoteproc2` booting `modem.mdt` (6284 bytes) and `now up` (`kmsg.log:2479-2483`), the SMD QRTR probe (`:2487`) and `icnss2_qmi: QMI DMS service connected` (`:2491`). A readback 73 s after `now up` still showed `remoteproc2` `running`, `remoteproc3` `offline` and no `wlan0`. The capture contains no `fatal error`, no `fs_device_efs_rmts.c` and no `rmts_get_buffer` line, and a marker written after the hold reached the host capture in 0.441 s. The session was left running for the coordinator. This measures the EFS-request boundary only; it is not a WLAN or connectivity result, and no second modem start is authorized.
