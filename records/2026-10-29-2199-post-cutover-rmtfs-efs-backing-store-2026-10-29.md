---
date: 2026-10-29
issue: omnipha/linux-sm7635#155
subsystem: modem
result: inconclusive
source: README.md
---
## Post-cutover rmtfs EFS backing store (2026-10-29, #155)

[BOOT.md](BOOT.md#post-cutover-rmtfs-backing-store-for-the-efs-buffer-155-host-only-2026-10-29)
records the run-54 boundary. The pinned rmtfs process, its QRTR publish and its sharedmem mapping survived
the PID-1 cutover, while `switch_root` deleted the old root's `/dev/uio0` and
`/boot/modemst1`/`/boot/modemst2` links. Whether that deletion caused the
`fs_device_efs_rmts.c:161` fatal is the one hypothesis to test: the pinned
service opens `/boot/modemst*` on demand, while the UIO mapping is already held.
`scripts/pmos-radio-bringup.sh` now checks the pinned rmtfs process, copies its
pre-cutover log, and restores only those missing nodes and links before the
one-shot modem marker. `sh scripts/test-pmos-radio-bringup.sh` fails closed when
any of them is absent or wrong. No new image is built and no modem start is
claimed.
