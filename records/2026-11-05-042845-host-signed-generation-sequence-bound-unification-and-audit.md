---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: confirmed
---
# host signed-generation sequence bound, carrier-read and guard-time proposal review

## Sequence bound unification

The host signed-generation prototypes previously diverged:
`verify-root-generation-bundle.py` bounded `sequence` at 2^31 - 1
(`SEQUENCE_MAX`), while the logical model `test-persistent-root-migration.py`
and the synthetic baseline fixture `test-pmos-baseline-provenance.py` accepted
any nonnegative integer. The bound is now unified across all three host
parsers at 0 <= sequence <= 2^31 - 1. Rollback statements likewise enforce
integer 1 <= sequence <= 2^31 - 1.

Reasoning:
1. Manifest v1 is bounded at 4096 bytes; decimal representations up to 10
   digits guarantee that sequence numbers fit well within field and manifest
   caps.
2. Cross-parser divergence allows generation bundles accepted by one prototype
   to be rejected by another. Standardizing on the verifier's 2^31 - 1 bound
   maintains consistency with standard bounded integer representations without
   requiring arbitrary-precision assumptions on potential future target
   verifiers.
3. Sequence exhaustion fails closed: a chain head at 2^31 - 1 cannot be
   extended because any successor would require 2^31, which fails manifest
   validation. There is no wraparound or silent truncation.

Tests added:
- Model, bundle verifier, and provenance parsers test boundary sequences 1, 2,
  2^31 - 2, and 2^31 - 1 as positive cases; negatives cover -1, 2^31,
  2^31 + 1, 2^63, and 2^64.
- Rollback statement builders across all three prototypes reject sequence 0,
  negative values, non-integer types (`0.0`, `True`), and values above
  2^31 - 1.
- `test-root-generation-bundle.py` cross-asserts
  `verifier.SEQUENCE_MAX == model.SEQUENCE_MAX == 2**31 - 1`, checks matching
  rollback statements at boundary values, tests end-of-range transitions near
  2^31 - 1, and verifies that `verify_chain` rejects bundles at or beyond the
  boundary rather than wrapping.

## Read-only carrier-read proposal evaluation

Physical boot 1 remains stopped because carrier verification without block node
creation has not been demonstrated. Review of the installed run-113 image and
host artifacts confirms:
- In `initramfs/init:11-12`, the diagnostic initramfs attempts `mount -t
  devtmpfs devtmpfs /dev 2>/dev/null` and falls back to `mount -t tmpfs
  devtmpfs /dev`. The running diagnostic system therefore uses a `tmpfs`
  fallback `/dev`, which does not auto-populate partition block nodes.
- Stock Android recovery geometry mappings (e.g. `by-name.txt`) mapping
  partitions to `sde27` and `sde51` cannot be assumed as live Linux node paths.
  Run-113 rescue measurements hashed partitions by `PARTNAME` via temporary
  nodes at major:minor `259:11` and `259:35`.
- Existing `carrier_reader()` in
  `scripts/build-init-boot-persistent-root.py:767-771` executes `mknod -m 0400
  "$node" b "$major" "$minor"` if `/dev/block/...` does not exist. This creates
  a node under `/dev` and is unapproved per strategy runbook rules.
- A strictly read-only proposal requires verifying whether existing block nodes
  are already present. If present, the carrier would need to be accessed via a
  single file descriptor opened strictly read-only (`O_RDONLY`), with `fstat`
  confirming device numbers matching the single sysfs `PARTNAME` entry, and
  hashed directly without writing intermediate files to `/run` or disk.
- Point-in-time checks (`blockdev --getro`, checking `/proc/mounts`, or
  pre/post sysfs checks) do not eliminate concurrent write races or prove the
  absence of writers. Any read-only inspection produces a snapshot only.
- If pre-existing block nodes are absent, the read-only carrier check cannot
  proceed; node creation (`mknod`) remains forbidden.

## Guard-time lower bound evaluation

Physical boot 1 was stopped due to the lack of an established same-boot lower
bound on guard arming. Investigation of run-113 artifacts and timing indicates:
- `/run/pid1-guard/armed` records only the random UUID `boot_id`, not an arm
  timestamp.
- In normal autonomous sequencing, the PID 1 transition script arms the guard
  before `exec switch_root`.
- The run-113 `/init` retains the run-66 handoff console tail, where
  `pid1_settle_timer` enforces a 151.01-second delay from `PID1_SETTLE_START`
  before accepting the PID 1 handoff. Both `pid1_settle_timer` and
  `pmos-pid1-guard.sh` sample `/proc/uptime` (`CLOCK_BOOTTIME`).
- In boot `7dec62b0-ddf3-4a37-abe8-0dad251aa25d`, handoff was accepted at
  printk uptime 155.60 s and the guard was armed at printk uptime 156.08 s.
- While `start >= 151.01` holds conditionally on `/proc/uptime` if the boot
  strictly followed the autonomous `/init` settle and transition path,
  `/init` also launches an interactive root shell (`setsid cttyhack /bin/sh &`).
  An unverified actor or alternate path could invoke `pmos-pid1-guard.sh arm`
  earlier.
- More fundamentally, `/run/pid1-guard/armed` provides no cryptographic proof
  of execution lineage or carrier identity for a live session.
- The stop gate stands: without an established, verified same-boot lower bound
  on guard arming and a confirmed read-only carrier check, physical boot 1
  must remain stopped. Physical acceptance remains coordinator-owned.
