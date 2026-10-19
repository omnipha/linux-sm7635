# Upstream tracking

- Source: https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635
- Maintainer: NothingOSS; GPL kernel and devicetree for Phone (3a) and Phone (3a) Pro.
- First target: Nothing Phone (3a) Pro A059P / `asteroids` / `volcano`, measured
  on our `mb003`: `ro.soc.model=SM7635`, stock kernel `6.1.84-android14`.
- Branch for Nothing OS 3.x: `sm7635/v/mr` (upstream head
  `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, observed 2026-10-19).
- Branch `sm7635/b/mr` is newer Nothing OS 4.x and not our stock 3.1 baseline.
- Vendor `v/mr` Makefile reports 6.1.78; `b/mr` reports 6.1.157. The exact
  `Asteroids-V3.1-250112-1904` build used on mb003 was not found in the
  published releases; earliest listed V3.1 release is 250302-1856. Expect
  differences from the on-device 6.1.84 binary.
- DTs: `arch/arm64/boot/dts/vendor/qcom/volcano*.dts{,i}` and
  `volcano-qrd-pro-overlay.dts`. The exact device overlay remains unverified.
- Checked: 2026-10-19, via upstream README, GitHub branch and Makefile, and
  ADB measurements of mb003.
