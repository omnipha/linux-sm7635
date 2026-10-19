# linux-sm7635

Kernel source tracking for Qualcomm SM7635 (Snapdragon 7s Gen 3, `volcano`).
The first target is the Nothing Phone (3a) Pro (`asteroids`, A059P). This is
**not** a working Omnipha kernel or image yet.

## Source and branches

- Vendor source: [NothingOSS/android_kernel_msm-6.1_nothing_sm7635](https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635), branch `sm7635/v/mr` (Nothing OS 3.x, Android kernel 6.1). This vendor tree is not mainline Linux.
- `main`: documentation and source tracking, no kernel tree.
- `upstream`: planned read-only mirror of the pinned vendor branch. No manual commits.
- `omnipha`: planned port patches, based on the same pinned branch. Not created until a concrete, buildable patch set exists.

The upstream repository is active; do not fork and edit it merely to claim
support. Prefer builds referencing an immutable upstream commit. Once a tested
Omnipha-specific patch is needed, carry it on `omnipha` and submit upstream
when feasible. A SoC directory does not imply that another SM7635 handset is
supported; each phone needs its own device tree, firmware and boot test.

## Device layout

- [`omnipha/ports/devices/nothing-asteroids`](https://github.com/omnipha/ports/tree/main/devices/nothing-asteroids): facts and eventual device/kernel APKBUILD.
- [`omnipha/images`](https://github.com/omnipha/images): eventual image definition.
- `device-nothing-asteroids`: future device test/issue repository, after the
  approved `omnipha/agents#2` template. Do not duplicate the kernel there.
- `omnipha/agents` issues: [#2 template](https://github.com/omnipha/agents/issues/2),
  [#3 Laurel pilot](https://github.com/omnipha/agents/issues/3); [ports#1](https://github.com/omnipha/ports/issues/1)
  introduces explicit device repository/maintainer status.

## Build and release status

No image builds here. The source is very large; use a shallow clone of a
pinned revision for experiments rather than treating this repo as a build
artifact. No `linux-sm7635` package or validated kernel boot exists yet.
The Android source uses GKI plus vendor configuration and DTs under
`arch/arm64/boot/dts/vendor/qcom/`; `volcano-qrd-pro-overlay` is a candidate,
not a verified match for the physical unit. Do not flash a built image without
stock partition backups, correct DTB selection, recovery and SSH-key-only
access in the resulting image.

## License

Upstream Linux kernel is GPL-2.0-only. Do not add proprietary firmware.
