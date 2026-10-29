---
date: 2026-10-24
issue: omnipha/linux-sm7635#77
subsystem: modem
result: inconclusive
source: README.md
---
## Modem remoteproc start init_boot (2026-10-24, #77)

`scripts/build-init-boot-modem-start.sh` packages exactly one host-only init_boot
from the measured #75 init. One guarded phase after the supplier phase and before
the existing 12 s bind gate and the single `qca_cld3_qca6750.ko` load reads the
modem `remoteproc2` state with a 2 s timeout and, only while that state is
`offline`, writes `start` once to its `state` file with a 10 s timeout, then
logs the write result and the resulting state. A modem that is already running,
or in any other state, is left untouched. The #75 supplier phase and order, the
corrected read-only mounts, the WLAN and vendor module closures, the 150 s timer
and the USB/key-only SSH path are unchanged. `scripts/verify-init-boot-modem-start.py`
fails closed with negative fixtures and rejects the measured `5a61de0e` SHA; it
is wired into `scripts/verify-bootimg.sh`. The reproducible image and the one
physical-outcome contract are recorded in [BOOT.md](BOOT.md). No physical boot
or WLAN success is claimed.
