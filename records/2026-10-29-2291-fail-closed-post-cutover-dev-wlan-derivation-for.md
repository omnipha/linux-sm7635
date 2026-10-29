---
date: 2026-10-29
issue: omnipha/linux-sm7635#150
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Fail-closed post-cutover `/dev/wlan` derivation for the WPSS stage (#150, host-only, 2026-10-29)

**Host-only script delta — no device operation, flash, partition write, new image SHA or WPSS/WLAN claim.** Run 55 (`fef03008…`, rollback and Android verified, #155 closed) measured the modem holding past the EFS request after cutover; WPSS, `/dev/wlan`, `wlan0`, association and reachability were not attempted. The merged `wpss` stage already copied an init-created `/dev/wlan` (`prepare`) or derived one, but its derivation accepted any `qcwlanstate` row in `/proc/devices` (including the block section) and left a failed node behind on a numbers mismatch. It now refuses a non-character path at `/dev/wlan` without replacing it, matches the `/sys/class/wlan/wlan/dev` major against exactly one `qcwlanstate` row in the `Character devices:` section, removes the node on a failed `mknod` or numbers/type mismatch, and reports the derived numbers. All checks run before the one-shot `wpss.attempted` marker and the single helper invocation. `driver`, `scan`, the pinned helper (`fef7e5da…`) and the measured exit 0/10 handling are unchanged. No profile is read or staged.

`sh scripts/test-pmos-radio-bringup.sh` adds a non-character `/dev/wlan`, a missing class device, a block-section or mismatched `qcwlanstate` major (each refused before arming), and a positive derivation of `495:0` mode `0600` followed by the helper exit 10 path. This proves host ordering only; the post-cutover WPSS start, `wlan0`, the proven-profile association chain, DHCP, gateway, DNS and external reachability remain one coordinator-held measurement.
