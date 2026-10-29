---
date: 2026-10-25
issue: omnipha/linux-sm7635#96
subsystem: modem
result: inconclusive
source: README.md
---
## Stock sharedmem + pinned rmtfs init_boot (2026-10-25, #96)

`scripts/build-rmtfs-binary.sh` builds a reproducible static musl aarch64
`rmtfs` from pinned upstream commits (qrtr v1.2, rmtfs v1.3) with the
publish-line, stock-UIO and fs1/fs2-only storage patches;
`scripts/build-init-boot-rmtfs-sharedmem.sh` extends the measured #86
(`8dddb8c7`) init by one phase after the unchanged #86 QRTR phase and before
console ready: it loads the stock `vendor_boot` `msm_sharedmem.ko` as-is
(identical to the `vendor_dlkm_a` provider, never rebuilt), records the
`Device created for client 'rmtfs'` line, links `/boot/modemst1 -> sdf2` and
`/boot/modemst2 -> sdf3` from the measured by-name table (fsc/fsg not exposed,
`-r` keeps the partitions unwritten) and starts rmtfs, logging to `/run`. The
three static services are stored xz-compressed and reconstructed byte-exact
(hash-checked) before the byte-identical #86 phase, because the LZ4 envelope
had only 22,448 B spare. `scripts/verify-init-boot-rmtfs-sharedmem.py`, wired
into `scripts/verify-bootimg.sh`, checks the module and service presence,
ordering, logs, envelope and rejects every measured SHA. Host image, hashes,
predicted outcomes and the rollback gate are in [BOOT.md](BOOT.md). This is not
a physical result.
