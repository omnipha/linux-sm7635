---
date: 2026-11-01
issue: omnipha/linux-sm7635#256
subsystem: wlan
result: confirmed
---
# Host run-90 switched-root fixture passes; live divergence needs /proc/1/mountinfo

Host-only Phase 1 of #256 on the run-90 refusal. `scripts/test-pmos-root-contract.sh`
gains a fixture matching the measured run-90 post-cutover state
(records/2026-11-01-104332-preack-selfpost-record-append-refused.md): a single
`/dev/block/sda13 / ext4 rw,relatime,norecovery` root in the PID 1 mount table
plus the private `/proc`, `/sys`, `/run`, `/dev`, `/dev/pts`, `/sys/kernel/config`
children that `pmos-session-stage.sh` mounts, and a guest `/dev/block/sda13`
block node with the measured 241421725696-byte size.

Result: `root_contract_switched_root` (scripts/pmos-root-contract.sh, unchanged,
sha256 `c76c31ff…bbf0f06cc6`) ACCEPTS that state. Every check after the recorded
`sda13` PARTNAME match passes with the measured layout: the single-userdata
partition count (rejects a second `PARTNAME=userdata` block), devnum,
block-node stat, size bounds, options (`rw` with `norecovery` accepted), and
the mountinfo cross-check including its single-mount rule (rejects a second
same-partition mount such as `/vendor/firmware_mnt`). The unchanged
`pmos-self-post.sh` (`fe98c0d2…8ca8b9f3d301f772bab6233e410bab`) also completes
its post-cutover `boot_record_append`/`boot_record_verify` on a real
loop-backed switched root in the `ext4-ack` subtest.

So the live run-90 refusal is NOT reproduced by the recorded run-90 state
against the pinned scripts: no check in `root_contract_switched_root` returns 1
on the fixture, and no host-side fix is warranted — changing any single check
now would be a blind mutation, not a measured fix. Per the issue's alternative
branch, the live divergence is elsewhere and the exact additional probe for the
live window is:

    ssh :2222 'cat /proc/1/mountinfo'   # capture before re-invoking self-post

to be diffed against this fixture's `/run/run90/mountinfo` (commit adds it in
`scripts/test-pmos-root-contract.sh`). The most likely divergence class the
probe discriminates: a second mount of `sda13` or `8:118` in PID 1's real
mountinfo (the single-mount rule is the only check the fixture can reject while
`/proc/1/mounts` still shows exactly one ext4 root line), e.g. the rmtfs/EFS
backing mount on `/vendor/firmware_mnt` or a leftover `/run/omnipha-userspace`
self-stage remnant. The default contract path `/run/pmos-root-contract.sh`
being absent on the guest is confirmed as designed-not-staged by
`pmos-self-stage.sh` (only the guard copy at `/run/pid1-guard/root-contract.sh`
exists), so the documented `PMOS_ROOT_CONTRACT=/run/pid1-guard/root-contract.sh`
override — already measured in run 90 — remains the correct invocation; the
issue's alternative of staging the contract at the default path would instead
feed self-post a host-side file, so it is not the divergence from run 69 (run 69
predates the boot-record code entirely and never exercised these checks).

All verification host-only: `sh scripts/test-pmos-root-contract.sh` passes all
three subtests (inner fixture, ext4-ack, ext4-timeout) with the new run-90
fixture and both new negatives. No image build, no flash, no device contact.
