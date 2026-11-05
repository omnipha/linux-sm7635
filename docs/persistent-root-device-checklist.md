# Persistent writable root: per-device suitability and limits

This checklist and its host test organize evidence; neither establishes facts,
authorizes device actions, replaces the coordinator's gates, nor proves a
persistent-root implementation safe. Apply it independently to each device:
reported information and another device's measurements are not device-specific
proof. Missing, ambiguous, stale, or contradictory evidence is a stop.

## Reusable checklist

For each target, record the source, date, device and limits for every claim.
Classify it as **measured**, **reported**, **open**, or **refuted**. A measured
claim must name evidence from that same target; a test of the form below checks
that a reference is present, not that its content is true.

- [ ] **Root carrier:** Identify the installed root filesystem and underlying
  storage and its relationship to the boot artifacts. Record filesystem type,
  root mount and relevant partition identities, installed artifact digests and
  an admissible way to verify them. A reported partition name is not proof of
  the installed writable root. Do not assume this device uses mb003's layout.
- [ ] **Persistence and filesystem policy:** Measure an unpinned SSH edit
  across a no-flash reboot and identify the carrier before and after; record
  mount options, filesystem features, clean/error state and an independently
  verified journal/fsck policy. A mounted superblock snapshot is not an offline
  integrity check, clean-shutdown proof or general durability proof.
- [ ] **USB-SSH rescue:** Identify and verify key-only USB SSH, including its
  availability after an induced, reversible root fault. Ordinary SSH on a
  healthy root is not that rescue test. Keep credentials outside the repo.
- [ ] **Guard:** Record the target's guard, same-boot armed and unacknowledged
  state, conservative deadline and safe return path. If the guard state or a
  defensible same-boot deadline is unknown, stop; do not infer it from a
  different boot or relax guard/ACK requirements.
- [ ] **Userdata:** No erase or format without explicit owner approval for
  that device and action. An unlock that may wipe data is not an exception.
  Approval for an erase or format does not satisfy the other gates or
  authorize an operation in this repository.
- [ ] **Capture and operations:** Arm host capture before each reboot; one
  SSH call for the one marker write; reads fail closed and happen only after
  the guard is confirmed for that boot; no `mknod`. Stop on an unknown or
  ambiguous condition. These are planning constraints, not permission to
  boot, connect or write.

## Basis and limits of the carried-over rules

[Run 116](../records/2026-11-05-095841-run-116-unpinned-marker-survives-no-flash-reboot.md)
reports capture armed before both reboots, a single pinned SSH call for its
98-byte marker write, and no `mknod`. The marker survived one no-flash reboot;
carrier hashes were not re-read. The
[correction record](../records/2026-11-05-103703-run-116-record-correction-two-wording-flaws.md)
limits the envelope claims: the comment does not report a guard/nonce re-read
or establish the absence of every other write.

[Run 117](../records/2026-11-05-103554-run117-sda13-superblock-readonly-snapshot.md)
reports capture armed before reboot, no marker write and no `mknod`; its
post-cutover read had a same-boot armed guard. Its first read was **before**
guard confirmation because the script did not fail closed. Therefore
fail-closed, after-confirmation reads above are a requirement for future
planning, not a claim that every run-117 read complied. Run 117's mounted
superblock snapshot did not establish the offline fsck policy. These results
are specific to mb003 and do not measure mb005.

## First target: mb005

Source: the OnePlus 8 Pro (`instantnoodlep`, SM8250) seed in
[`omnipha/agents` at `9c8a27a7eeba4fd3266c6a9d7f71836cad9a3d47`](https://github.com/omnipha/agents/blob/9c8a27a7eeba4fd3266c6a9d7f71836cad9a3d47/docs/knowledge/oneplus-instantnoodlep.seed.json),
updated 2026-11-04. Its classifications are retained:

- **Measured, K1:** USB `18d1:4ee8`, configuration `midi`, interfaces
  `01:01:00` and `01:03:00`; ADB listed no device and there was no shell
  access. This is not a USB-SSH rescue measurement.
- **Reported, K2/K5:** the pmaports package dependencies and `deviceinfo`
  declaration, including `rootfs partition super`. A declaration is not an
  installed carrier or writable-root measurement.
- **Open, K11/K12:** fastboot presence, unlock state, slot and product
  variables are untested; unlocking may wipe userdata. USB SSH and WLAN SSH
  bring-up are untested; key-only SSH is a target, not a measured result.
- The seed does not establish a guard, a filesystem policy, marker survival,
  or rescue under a root fault for mb005. These remain open.

The following is a machine-readable **screening fixture**, not a device
instruction or an approved plan. The test reads it from this document. It
must remain blocked while the evidence is reported or open. `operations` is
empty because no device operations are proposed here.

```json
{
  "device": "mb005",
  "evidence": {
    "root_carrier": {"status": "reported", "device": "mb005", "source": "omnipha/agents@9c8a27a:K5", "detail": "deviceinfo declares rootfs partition super"},
    "usb_ssh_rescue": {"status": "open", "device": "mb005", "source": "omnipha/agents@9c8a27a:K12", "detail": "USB SSH untested"},
    "guard": {"status": "open", "device": "mb005", "source": "omnipha/agents@9c8a27a", "detail": "guard not established by seed"},
    "filesystem_policy": {"status": "open", "device": "mb005", "source": "omnipha/agents@9c8a27a", "detail": "writable-root filesystem policy not established by seed"},
    "marker_persistence": {"status": "open", "device": "mb005", "source": "omnipha/agents@9c8a27a", "detail": "no marker-survival measurement in seed"}
  },
  "plan": {"userdata_action": "none", "owner_approval": null, "operations": []}
}
```

## Host test and scope

Run `python3 -B scripts/test-persistent-root-device-checklist.py`. The test
checks the fixture and exercises synthetic positive and negative cases for
device-specific evidence, destructive-action approval, capture ordering,
single-call marker writes, same-boot guard confirmation before reads, and
`mknod` refusal. It models declarations only: it does not verify evidence,
implement a live guard, issue commands, or authorize a session. A synthetic
pass does not mean any real device is suitable. In particular mb005 remains
blocked by its reported/open evidence; #324's unmeasured acceptance items
remain open. The installed mb003 pair remains untouched and never-reflash.
