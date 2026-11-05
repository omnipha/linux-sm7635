---
date: 2026-11-05
run: 121
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# run 121 acceptance 3 os-release fault rescue

Source: coordinator measurement comment on #324
(https://github.com/omnipha/linux-sm7635/issues/324#issuecomment-6658397654,
2026-11-05 12:49 UTC, run 121 2026-11-05 13:38-13:47 MEZ). This record
transcribes that comment. The raw captures stay outside Git on the
coordinator host (`attempt-20261105-1330-run121-acceptance3-324`) and are not
copied or re-verified here. No device action was taken for this record; the
work below is host-only. Nothing here closes #324.

## Device measurement (coordinator, reported in the comment)

- Installed pair unchanged and never-reflash: `init_boot_a`
  `d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c`,
  `vendor_boot_b` `221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500`.
  No flash, erase, remount, fsck, `mknod`, ACK or pins.
- Boot 1 `2715838f` (normal boot, capture armed before the reboot):
  `/run/keep` 0:600. One SSH call on `:22`: one
  `mv /run/pmos/usr/lib/os-release -> os-release.disabled`. `sda13` was
  already `rw,relatime,norecovery` at `/run/pmos`. The renamed file is the
  329-byte `os-release`.
- Fault boot `01776fa8`: `pmos-self-stage: FAIL: pmos-session-stage failed`
  in kmsg at 5.035 s. Diagnostic `:22` answered from ~6 s and stayed
  reachable to at least 207 s, PID 1 `init`, `/run/keep` present, `sda13` at
  `/run/pmos` `rw`. `/run/pid1-guard` absent: the guard was never armed. No
  `:2222` in the fault boot; session-stage died before guest SSH started.
- Rollback over `:22` with exactly one `mv`: `os-release` restored, 329 B,
  sha256 `efc600e4…`, `ID="postmarketos"`. Then `sync`, then `restart2
  bootloader`, fastboot gate exact: serial `00181152O003821`, slot a,
  unlocked, `pineapple`, userspace no. Host manifests `parts`, `parts-a`,
  `parts-b` verified OK. No partition written.
- First `restart2` call ran without `/bin/sync` (absent in the BusyBox path);
  the fault persisted into the fault boot anyway. The rollback was secured
  with `busybox sync`.

## Host tests (this worktree, not the device)

- The coordinator re-ran `scripts/test-pmos-rescue-restore.sh` from
  `origin/main 4088cb2` via `git show`, with the worker worktree untouched:
  exit 0. It is the synthetic disposable-image fixture, not a device
  measurement.
- The supervisor independently re-ran the same script from `origin/main
  4088cb2` this tick: exit 0.

## Host change in this change set (not a device result)

`scripts/test-pmos-baseline-provenance.py`: the synthetic fixture's manifest
parser now refuses the altered-radio digest `d7b74c24…` at each of the three
pinned entries (`manifest denylisted digest`), as the model and the verifier
already did. This closes the parser gap that
`docs/strategy/persistent-root.md` named for item 4's host leg. It uses
throwaway keys, builds no image or replacement pair, and changes no model or
verifier. It is not a measurement of item 4.

## #324 acceptance items

- **3 Rescue under an induced, reversible root fault: measured for this one
  fault.** A missing `usr/lib/os-release` stops session-stage fail-closed;
  key-only `:22` stays reachable and one `mv` over `:22` restores the file;
  no flash was needed. This covers one fault on the installed chain only.
- **1 Survival without flash: partial, unchanged.** No new claim here.
- **2 Read-write root with defined journal/fsck policy:** the fsck policy is
  still a host-only proposal, unmeasured on the device. No fsck or journal
  action ran on the device in run 121.
- **4 Replacement of the hash pins: unmeasured.** No replacement pair exists
  and none was built.
- **5 Envelope items not re-read on device: unmeasured.** Carrier hashes were
  not re-read: no read-only path existed (readable nodes absent, none
  created). Rescue state rests on host manifests, fastboot identity and the
  untouched write list.

## Limits kept visible (from the coordinator comment, not restated as measured)

- The `:22`-outage recovery path is unmeasured; no rescue path without
  diagnostic SSH is validated. A board note (12:42:05Z) asked to validate a
  rollback path without diagnostic SSH before any fault boot; it reached the
  coordinator only after the boot, and run 121 followed the `:22` path.
- Other files' faults, `:22` loss, and power-loss behavior are unmeasured.
- Host capture (`:2222`, `kmsg.log` sha256 `065beb74…`, 164158 B) covers boot
  1 only. The fault-boot stage error is evidenced via `dmesg` over `:22`,
  not via capture.
- No pstore pull (`max-fetch-size` missing); the loss stays covered by the
  recorded owner decision (2026-11-05, #324 comment 6653556220). The comment
  reports the fault-boot `/sys/fs/pstore` as empty; no pstore evidence is
  claimed.
- `device-op session open/close` was not used; operations are recorded as
  `device-op event` / `fastboot-gate` and `note-evidence`.
- The run-119 question about the post-failure mount mode is answered for
  this fault: `sda13` stayed `rw` at `/run/pmos` through the fault boot. A
  remount was not needed for this one rescue. This is one measured fault,
  not a general rule.

## Consequence for the dossier

Acceptance 3 is measured for this one `os-release` fault on the installed
chain; the `:22`-outage gap and every other fault class stay open. The
strategy sections below are updated, not the model. #324 stays open.
