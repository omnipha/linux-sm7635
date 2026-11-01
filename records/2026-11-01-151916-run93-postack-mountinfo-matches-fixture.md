---
date: 2026-11-01
issue: omnipha/linux-sm7635#261
subsystem: wlan
result: confirmed
---
# Run 93 post-ack mountinfo: live PID 1 table matches the fixture class; refusal is not in the mount checks

Issue #261 outcome (b), worker-measured on the installed never-reflash run-87
pair (`init_boot_a f9449ba5` / `vendor_boot_b a71b3f5f`), boot
`ee634e28-6754-42d3-a762-34a8edb39132`, coordinator attempt dir
`~/phone-second-life-data/mb003/pstore/attempt-20261101-1610-postack-mountinfo-run93/`
(host-only, not in git). No flash, no partition write, no cold start; read-only
guest commands only (`cat`, `ls`, `sha256sum`, `tail`).

## Session (coordinator-proven, independently rechecked)

Key-only root SSH `172.16.42.2:2222` with the pinned host key (attempt
`kh2222`, mode 600, exact pinned ed25519 line), `ready.json` boot id equals the
handoff boot id, `session-open-r93.txt` "session open: ok", `handoff-r93.txt`
"handoff: ok", marker `run93_handoff_1793545953_261`, `/run/keep` root-only
present, capture `kmsg.log` advancing on the same boot.

## The one pid1-ack

Exactly one host `sh scripts/pmos-pid1-ack.sh ee634e28-… 39132` was invoked
(the single allowed ack; no retry). Its strict pre-ack probe failed before any
write: `cat: can't open '/proc/1/root/run/pid1-guard/nonce': No such file or
directory` → `pid1-ack: strict-key post-cutover probe failed`. No `ack` or
`accepted` file was written by it. So the guard-deadline removal did not land
on this boot; the capture below ran with the deadline still armed. The SSH
session itself stayed healthy (all four reads below succeeded), so per the
issue this was corrected in-course, not a stop condition.

## Captured live post-cutover state (read-only)

`/proc/1/mountinfo` (13 rows, captured 2026-11-01, run 93):

    28 1 8:13 / / rw,relatime - ext4 /dev/block/sda13 rw,norecovery
    29 28 0:21 / /run rw,nosuid,nodev,relatime - tmpfs tmpfs rw,size=8192k,mode=700
    30 28 0:22 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
    31 28 0:18 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sysfs rw
    32 31 0:16 / /sys/kernel/config rw,nosuid,nodev,noexec,relatime - configfs configfs rw
    33 28 0:23 / /dev rw,nosuid,noexec,relatime - tmpfs tmpfs rw,size=10240k,mode=755
    34 33 0:24 / /dev/pts rw,relatime - devpts devpts rw,mode=620,ptmxmode=666
    35 31 0:5 / /sys/kernel/security rw,nosuid,nodev,noexec,relatime - securityfs securityfs rw
    36 31 0:6 / /sys/kernel/debug rw,nosuid,nodev,noexec,relatime - debugfs debugfs rw
    37 31 0:25 / /sys/fs/fuse/connections rw,nosuid,nodev,noexec,relatime - fusectl fusectl rw
    38 31 0:15 / /sys/fs/selinux rw,nosuid,nodev,noexec,relatime - selinuxfs selinuxfs rw
    39 31 0:26 / /sys/fs/pstore rw,nosuid,nodev,noexec,relatime - pstore pstore rw
    40 33 0:27 / /dev/shm rw,nosuid,noexec,relatime - tmpfs shm rw

`/proc/1/mounts` (13 lines): one ext4 root `/dev/block/sda13 / ext4
rw,relatime,norecovery` plus the same tmpfs/proc/sysfs/configfs/devpts/
securityfs/debugfs/fusectl/selinuxfs/pstore/shm children.

Contract paths: `/run/pmos-root-contract.sh` does not exist (designed,
self-stage stages only the guard copy — confirmed again); `/run/pid1-guard/
root-contract.sh` exists, 0700 root, 14807 bytes, sha256
`c76c31ff148ab19ff5b2de6f1e40a036ee6ec275d54b0b5d1eaab0bbf0f06cc6` — equal to
repo `scripts/pmos-root-contract.sh`, same hash as run 90.

`/run/radio-bringup/pmos-self-post.sh` sha256
`5e118ffc4073752afc06eb6f0f2e603f28c2a50f44356ec842039321db5bd81f` — the
same pinned script as run 90, self-consistent.

Boot-record tail (`.omnipha-boot-record`): ends at `usb-init: pid1 transition
guard armed; exec switch_root to postmarketOS init` for this boot; full
captured tail = boot line, diagnostic hold, pre-SSH panel line, the seven
stage/self-stage/radio-bringup lines, and the guard-armed line. Identical shape
to run 90: no post-cutover append ever landed.

## Diff against the #256/#257 run-90 fixture

Outcome (b): PID 1's live mountinfo shows EXACTLY ONE `sda13`/`8:13` mount —
the root at `/`. There is no second same-partition mount: no
`/vendor/firmware_mnt`, no leftover `/run/omnipha-userspace`, no rmtfs/EFS
backing mount. `/proc/1/mounts` likewise has exactly one ext4 root line.
The mountinfo divergence named in outcome (a) is refuted by measurement.

Non-divergent differences from the fixture's 7-row table, each outside every
contract check:

- six additional ordinary virtual filesystems mounted by the postmarketOS
  userspace (`/sys/kernel/security`, `/sys/kernel/debug`,
  `/sys/fs/fuse/connections`, `/sys/fs/selinux`, `/sys/fs/pstore`,
  `/dev/shm`);
- `/dev` carries `nosuid,noexec` and `size=10240k,mode=755` (fixture: no such
  options, `size=1024k`);
- `/run`, `/proc`, `/sys` parentage/ordering details differ in numbering only.

`root_contract_switched_root` (scripts/pmos-root-contract.sh:129-213) reads
only the `/` row (kind, source, opts), the partition-name walk, devnum, block
size bounds, and the mountinfo cross-check whose single rule constrains rows
sharing the root's source or devnum. By construction it ignores other rows'
paths and options. To make that acceptance measured rather than asserted, this
commit adds the exact captured run-93 table as a new fixture to
`scripts/test-pmos-root-contract.sh`: the unchanged contract ACCEPTS it
(identity `ext4 / /dev/block/sda13 rw,relatime,norecovery`, size
241421725696), and a new negative rejects the same table with a hypothetical
second `8:13` mount appended. The run-90 fixture and all existing negatives
are unchanged.

## What remains unmeasured for the run-90 refusal

With the live mount state now measured equal to the accepted fixture class,
the run-90 `boot_record_append` refusal inside `root_contract_switched_root`
cannot have been caused by any mount input. The remaining unmeasured contract
inputs at the refusal moment are:

1. `/sys/class/block/*` at self-post time on the real device (the fixture
   fakes sda13/sda6 uevents; the live walk ran before this capture and no
   `/sys/class/block` snapshot was taken in run 90 or 93);
2. the existence/size/stat of the guest `/dev/block/sda13` node at
   self-post time (same: faked in the fixture, never captured live);
3. `ROOT_CONTRACT_MIN/MAX_BYTES` environment as seen by the self-post shell
   (defaults assumed, never printed);
4. `blockdev --getsize64` output on the real node inside that shell.

Next single variable for a successor issue: capture those inputs in the same
read-only session shape (they are all `cat`/`ls`/`stat`-readable post-ack), or
instrument self-post's failure exit point, before touching any check.

Verification: `sh scripts/test-pmos-root-contract.sh` passes all three
subtests (inner fixture with the new run-93 accept case and new second-mount
negative, ext4-ack, ext4-timeout). Host-only; no boot, no device recovery.

Not WLAN acceptance: acceptance stays two fresh self-starting boots per
PLAN.md.
