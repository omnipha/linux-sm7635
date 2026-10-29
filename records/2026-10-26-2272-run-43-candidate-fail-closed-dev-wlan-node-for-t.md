---
date: 2026-10-26
run: 43
issue: omnipha/linux-sm7635#124
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Run 43 candidate: fail-closed /dev/wlan node for the registered wlan_hdd_state char device (#124, host-only, 2026-10-26)

**Host result, not a device result.** No flash, reboot or other device operation
was performed. This issue authorizes no flash, no reboot and no device access;
the physical single-variable session is a separately authorized issue filed
later under its own authorization.

**Supervisor ruling (recorded verbatim, #124):**

- The issue's "do NOT start the WPSS helper" is an instruction to the init-side
  node step. The verified evidence (extracted run-42 init, zero `wpss-once`
  occurrences, init ends at `log 'console ready'` + `setsid cttyhack /bin/sh`;
  `scripts/verify-bootimg.sh` describes `bin/wpss-once` as "dormant …
  coordinator may execute once") shows init never starts `/bin/wpss-once`.
  Therefore the requirement is vacuously satisfied: a node phase that creates
  the node only on full verification and otherwise logs the reason, creates no
  node, and attempts nothing further.
- End-to-end fail-closed is provided by the unchanged helper's existing
  `if [ ! -c /dev/wlan ]; then exit 9` precheck — the exact run-42 mechanism.
  No stop-marker, no init abort, no helper modification.
- The issue's own predicted outcome (3) ("a verified node still yields exit 9")
  confirms the coordinator invoking the unchanged helper over SSH is the
  expected flow in every outcome.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-psoc-hold-wlan-node.img` | 8,388,608 | `0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa` |

The only delta from the measured run-42 #120 image
(`8b62520fe6288361fd15faa573587a0d1be1e0788f780c62440677a60b739801`) is one
fail-closed `wlan-node` phase in the session init, placed immediately after the
WLAN closure (`log 'wlan-init: end'`, which follows the single
`qca_cld3_qca6750.ko` insmod) and before `log 'console ready'`:

1. Read `/sys/class/wlan/wlan/dev`. Accept it only as exactly one numeric
   `major:minor` pair (`case "$WLAN_DEVNUM" in ''|*[!0-9:]*|*:*:*|*:|:*)`
   rejects every other form) whose major is the single `qcwlanstate` entry in
   the `Character devices:` section of `/proc/devices`; leading zeros are
   normalized with `$((10#…))` so `0495` and `495` compare equal, and a block
   section entry never matches.
2. Only then `timeout -k 1 2 mknod -m 0600 /dev/wlan c "$WLAN_MAJOR"
   "$WLAN_MINOR"` with the live numbers and verify the result is a character
   device with that exact major:minor (`stat -c '%t:%T'` equals
   `printf '%x:%x'` of the live pair). A failed or mismatched verify removes
   the node.
3. Fail closed otherwise: absent class device, unreadable or unread `dev`,
   malformed number, zero or multiple `qcwlanstate` char majors, a major
   mismatch against sysfs, a pre-existing `/dev/wlan`, a failed `mknod`, or a
   failed post-create verify — each logs its exact reason to kmsg, creates no
   node and attempts nothing further; there is no retry.

No observed number is hard-coded anywhere in the phase (the string `495` does
not appear in it); the numbers come only from the live sysfs node
cross-checked against `/proc/devices`. `bin/wpss-once` is byte-identical to
run-42 (#109): its `/dev/wlan` precheck, the single 25 s-capped ON hold, the
one-shot `wpss_boot=1` write and the 12 s window sample are untouched. The
150 s timer, `/run/keep`, the pinned Dropbear host key and invocation, the
modem hold, the stock INI bind and the 21-module WLAN closure are byte-exact
#120. No kernel change, no config change, no new module; the debug cpio still
carries zero `.ko`.

`scripts/verify-init-boot-psoc-hold-wlan-node.py` first re-verifies the
measured `8b62520f` image through the #120 checker, then requires the
candidate cpio to differ only in `init`, with the init differing only by the
node phase at the enforced position. Its negative fixtures reject a removed,
duplicated, moved (after `console ready` or before the WLAN closure), major-
or minor-hardcoded (495/0), `/proc/devices`-cross-check-stripped,
class-absent-guard-stripped, verify-stripped, mode-loosened or retried node
step; a `/bin/wpss-once` invocation, a `wpss_boot` write or an ON write
injected into init; any trigger change; timer, `/run/keep`, host-key and
marker regressions; the reused run-42 and run-41 images; image envelope,
header, block, gap, tail and size damage; and every prior measured SHA
including unflashed `7c3d915f` and measured `8b62520f`.
`scripts/build-init-boot-psoc-hold-wlan-node.sh` builds twice in series and
fails unless the outputs are byte-identical (verified: two serial builds both
`0f998e29…`). The debug cpio is 3,675,136 B, SHA-256
`2576b14b94656bfb14c0ae77c6e5608a2fd97f2a77a07b12441e1433ba486a0d`; the LZ4
HC-12 frame is 2,097,145 / 2,117,632 B and the 6,266,880 B signed tail from
offset 2,121,728 is unchanged. Both are wired into `scripts/verify-bootimg.sh`:

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-psoc-hold-wlan-node.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted outcomes for the separately authorized single-variable session**
(copied from #124; none is an observed physical outcome):

1. The class node and its device number persist, `/dev/wlan` verifies, the
   unchanged helper's existing node check passes and the unchanged ON writer
   plus the single WPSS write run — whether the hold is accepted,
   `ICNSS_FW_READY` arrives and `wlan0` persists then discriminates the later
   psoc-idle question.
2. The class node or device number is absent, malformed, mismatched, or
   `mknod` fails — the init logs the reason, creates no node and attempts
   nothing further; the unchanged helper then rejects with exit 9 (no node).
   The registration/lifecycle or filesystem path is the next named gap.
3. A verified node still yields exit 9 — the check's filesystem/namespace or
   an intervening removal is the discriminator; stop with no second write.

Never reflash `8b62520f…`, `7c3d915f…`, `0b40ac34…`, `e75c5bd2…`,
`d9d8d2b8…`, `bf2089c4…` or any earlier measured SHA. This #124 handoff does
not authorize any flash. The current reuse authority is the #130 section at
the top of this file: the current device-op rule permits reuse of the unchanged
measured `0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa` on
`init_boot_a` only, through the existing device-op flash path and its normal
preflight and verifier hooks. It is not an owner reflash exception and does not
authorize a ledger edit, force option, or any other SHA or partition. It uses
the #113/#120 preboot capture handoff (including the pinned `[172.16.42.2]:22
ssh-ed25519 …` known-hosts line recorded in the #120 section below, unchanged
here) and the one-session, one-attempt stop rule. The stale #127/run-44
never-reflash contradiction is superseded by that section.
