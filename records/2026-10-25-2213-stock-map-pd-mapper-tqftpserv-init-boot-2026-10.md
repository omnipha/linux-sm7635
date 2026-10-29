---
date: 2026-10-25
issue: omnipha/linux-sm7635#86
subsystem: boot
result: inconclusive
source: README.md
---
## Stock-map pd-mapper + tqftpserv init_boot (2026-10-25, #86)

`scripts/build-pdmapper-tqftpserv-binaries.sh` builds two reproducible static
musl aarch64 services from pinned upstream commits (qrtr v1.2, pd-mapper v1.1,
tqftpserv v1.3); `scripts/build-init-boot-pdmapper-tqftpserv.sh` packages them
with six byte-exact `.jsn` maps from the one #89 stock `modem_a` read and the
merged #92 extractor. The run-34 (#83, measured `35866d56`) init is changed
only by a reworded marker and a QRTR-service phase after SSH but before any
coordinator-guarded remoteproc2 start, with `/run` logs/status; no rmtfs or
sharedmem work is bundled. `scripts/verify-init-boot-pdmapper-tqftpserv.py`,
wired into `scripts/verify-bootimg.sh`, checks binary/map contents and
executability, ordering, logs, image envelope and all previously measured
SHAs. The host image, full hashes, predicted physical outcomes and rollback
gate are in [BOOT.md](BOOT.md). This is not a physical result.
