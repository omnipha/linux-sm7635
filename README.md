# linux-sm7635

Kernel source tracking for Qualcomm SM7635 (Snapdragon 7s Gen 3, `volcano`).
The first target is the Nothing Phone (3a) Pro (`asteroids`, A059P). This is
**not** a working Omnipha kernel or image yet.

## Source policy

- Vendor source: [NothingOSS/android_kernel_msm-6.1_nothing_sm7635](https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635), branch `sm7635/v/mr` (Nothing OS 3.x, Android kernel 6.1). This vendor tree is not mainline Linux.
- `main`: documentation and the pinned source reference only. This repository does not contain the kernel tree.
- Builds reference an immutable vendor commit through the APKBUILD source URL. Do not publish a full `upstream` mirror while Nothing maintains the repository.
- A local bare backup may exist on the build host. It is not the published source of truth.
- `omnipha`: not created. Add it only for a tested Omnipha-specific patch that cannot live as a small patch stack in `ports`. Submit feasible changes upstream first.

This differs from `linux-sm61x5` and `linux-sdm670`: those mirror community
mainline trees that can go inactive. Nothing's SM7635 tree is the active,
GPL-published source, so copying its 2.7 GB history adds no porting value yet.
A SoC reference does not imply that another SM7635 handset is supported; each
phone needs its own device tree, firmware and boot test.

## Device layout

- [`omnipha/ports/devices/nothing-asteroids`](https://github.com/omnipha/ports/tree/main/devices/nothing-asteroids): facts and eventual device/kernel APKBUILD.
- [`omnipha/images`](https://github.com/omnipha/images): eventual image definition.
- `device-nothing-asteroids`: future device test/issue repository, after the
  approved `omnipha/agents#2` template. Do not duplicate the kernel there.
- `omnipha/agents` issues: [#2 template](https://github.com/omnipha/agents/issues/2),
  [#3 Laurel pilot](https://github.com/omnipha/agents/issues/3); [ports#1](https://github.com/omnipha/ports/issues/1)
  introduces explicit device repository/maintainer status.

## Build documentation

- [Build baseline](docs/build-baseline.md): pinned vendor source, toolchain and comparison.
- [Boot image](docs/boot-image.md): host-only boot-chain packaging and verification.

## Current state and history

- [status.yaml](status.yaml): measured state per subsystem and one next question.
- [PLAN.md](PLAN.md): ordered next steps, one active issue.
- [INDEX.md](INDEX.md): generated map of all run and work records.
- [records/](records/): one immutable dated file per run, measurement or finding.
- BOOT.md: historical pointer only; its sections live in `records/` (see INDEX.md).

Binding rules from `omnipha/agents` `docs/records-and-lean-files.md`: every
protocol is a NEW dated file in `records/` with front matter. Never append to
an existing record. `status.yaml` (80 lines), `PLAN.md` (150) and this README
(150) stay lean and hold no logs. Regenerate the map and check it:

```sh
python3 scripts/records.py index . --write
python3 scripts/records.py check . --base origin/main
```

Public support claims live only in `omnipha/ports`
`devices/nothing-asteroids/device.yaml`. Held RAM sessions on the stock kernel
are not a release, cold boot or persistent installation.

## License

Upstream Linux kernel is GPL-2.0-only. Do not add proprietary firmware.
