---
date: 2026-10-26
issue: omnipha/linux-sm7635#116
subsystem: boot
result: inconclusive
source: README.md
---
## Capture-gated psoc-idle hold rerun (2026-10-26, #116)

Superseded for execution by #120: the run-41 candidate `7c3d915f…` was never
flashed, and its `-R` host key cannot be pinned before the reboot. It remains
never-reflash; use the #120 pinned host-key image instead.

`scripts/build-init-boot-psoc-hold-capture.sh` rebuilds the measured run-40 #109
session `init_boot` with exactly one change, the session marker reworded to the
#116 capture-gated rerun, so the image gets a SHA-256 distinct from the measured
`0b40ac34` image and from every earlier measured SHA. The single 25 s-capped
`/dev/wlan` `ON` hold, the one-shot WPSS trigger and its single `wpss_boot=1`
write, the 150 s timer and the `/run/keep` semantics are byte-exact.
`scripts/verify-init-boot-psoc-hold-capture.py`, wired into
`scripts/verify-bootimg.sh`, fails closed on a prior measured SHA, a removed,
duplicated, re-capped or moved hold, an altered or retargeted `ON` write, a
second WPSS write, any timer or `/run/keep` change and image-envelope damage,
and the build script requires two serial builds to be byte-identical. The
physical run is owned by the physical coordinator and follows the #113 preboot
capture handoff exactly; predicted outcomes (a)/(b)/(c)/(d) and the handoff are
in [BOOT.md](BOOT.md). This is not a physical result.
