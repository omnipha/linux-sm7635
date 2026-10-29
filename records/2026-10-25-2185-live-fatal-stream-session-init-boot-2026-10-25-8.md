---
date: 2026-10-25
issue: omnipha/linux-sm7635#81
subsystem: boot
result: inconclusive
source: README.md
---
## Live fatal-stream session init_boot (2026-10-25, #81)

`scripts/build-init-boot-live-fatal-stream.sh` packages exactly one host-only
session init_boot: the byte-exact measured #75 init plus exactly one #81
session-only log after the armed 150 s self-recovery timer and before the
module phase. The marker is the only delta and forces a SHA-256 distinct from
the reused measured `4216af26` session image of run 32 and from every other
measured SHA. The boot init starts no remoteproc, never creates `/run/keep`,
and adds no `rmmod` or reload; the supplier phase and order, the bounded
WPSS/icnss2 bind gate, the read-only mounts, the single stock WLAN load, the
module closures, the RESTART2 helper and the USB/key-only SSH path are
unchanged. Run 32 showed the polled capture loses the fatal line before the USB
link dies, so the coordinator opens a persistent host-side `dmesg -w` stream
during the modem-off baseline and keeps it running through one guarded
`remoteproc2` start. The 150 s userspace timer does not cover the expected
kernel panic. `scripts/verify-init-boot-live-fatal-stream.py` fails closed with
negative fixtures (marker removal, duplication, move, rewording or the #79 text,
early keep, init-time remoteproc start, the reused #75/#77/#79 inits, timer
regressions, `rmmod`/`modprobe` and every reused measured SHA including
`4216af26`) plus a host-only simulated-clock timer test, and is wired into
`scripts/verify-bootimg.sh`. The reproducible image and the predicted outcomes
are recorded in [BOOT.md](BOOT.md). No physical boot, `wlan0`, modem or fatal
text is claimed.
