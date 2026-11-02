---
date: 2026-11-02
issue: omnipha/linux-sm7635#265
subsystem: wlan
result: confirmed
---
# Instrumented pre-ack self-post: trace-only host image for dossier step 3 (awaiting the one live boot)

Issue #265 host-only phase (steps 1-3). No flash, no USB, no boot and no
partition write was performed for this record. The installed never-reflash
run-87 pair `init_boot_a f9449ba5` / `vendor_boot_b a71b3f5f` stays
installed and untouched; every earlier measured hash stays never-reflash.

## Step 1: trace-only instrumentation of `scripts/pmos-self-post.sh`

The pinned script gains one `trace()` helper that emits one structured line
through the existing `log()` path (self-post.log + /dev/kmsg) at every point
the issue names: script `start`, inside the OpenRC wait loop (`openrc wait
enter`/`exit`), `pre`/`post` around every guard/identity/`/run/keep`/contract
check, at `record_fail` entry, and at `boot_record_append` /
`boot_record_verify` entry and exit, e.g.
`pmos-self-post: self-post-trace: record append entry rc=0`. Because the
run-94 acked-state read showed that no post-ack read can see self-post-time
state, `record_fail` entry additionally dumps the guard-directory shape
(`trace_state`: present/absent, type, owner:mode:links:size and value of
`armed`, `nonce`, `accepted`, `ack`, `root-identity`, the guard dir mode and
the boot id, `/run/keep` and the default contract path, plus uptime) —
read-only `stat`/`cat` only. `guest_marker` gains one entry trace per stage.

`diff` shows added trace lines only: `build-init-boot-persistent-root.py`
now mechanically strips the marked `# trace-begin`/`# trace-end` block and
every leading-whitespace `trace`/`trace_state` statement line and requires
the result to be byte-identical to the previously pinned script
(`fe98c0d2…`), so no check, ordering, permission or content logic changed.

## Step 2: extended fixture family

- `sh scripts/test-pmos-root-contract.sh` (real BusyBox PID-1 `switch_root`
  to loop-backed userdata ext4) now runs the instrumented script beside a
  derived trace-free copy at the three current pass/fail points: the
  wrong-PARTNAME refusal inside the switched-root/guard identity check, the
  run-94 acked-guard shape (`accepted` present, `nonce`/`ack` absent) refused
  at the armed-and-unacknowledged check, and the valid pre-ack run through
  append/verify up to the missing radio script. At each point the traced
  output, with every `self-post-trace:` line removed, must equal the
  trace-free output byte-for-byte; the persisted boot record must also be
  identical for the pre-ack run, and asserted trace points name the exact
  last-reached marker (the check that refuses) and the first absent one.
  `inner`, `ext4-ack` and `ext4-timeout` all pass.
- `build-init-boot-persistent-root.py` / `verify-init-boot-persistent-root.py
  --self-test` gained negatives refusing: any non-trace byte (umask change,
  a weakened wait bound, a disarmed guard check), a check hidden behind a
  trace line, a removed or duplicated trace block, and any drift of the
  trace-free script from `fe98c0d2…`. 85 refused image hashes.
- `test-pmos-self-stage.sh` passes with its guest-marker extraction updated
  to the traced function plus an asserted no-op trace stub.
  `test-pmos-pid1.sh`, `test-pmos-boot-record.sh`,
  `test-pmos-radio-bringup.sh` pass unchanged. `test-pmos-pid1-request.sh`
  fails with "pinned transition script unavailable" (its stale
  `SCRIPT_SHA=0b85d1dc…` no longer matches the current
  `pmos-pid1-transition.sh` `e1dba713…`), identically on the clean base;
  not caused by this change and not touched here.

## Step 3: one new `init_boot` only

The bundle that carries `pmos-self-post.sh` lives in the installed
`vendor_boot_b a71b3f5f`, which must stay installed. The successor image
therefore carries the instrumented script as one extra root-only
(`/run/omnipha-self-post-trace.sh`, mode 0700) cpio member inside `init_boot`
itself; the decoded init's self-stage hook verifies its SHA-256 and moves it
over `/run/pmos-self-post.sh` before creating `/run/keep`, i.e. before
`pmos-self-stage.sh` stages it into the guest. The vendor_boot_b carrier
output is rebuilt byte-identical (`a71b3f5f`) and is NOT flashed.

- `init_boot-preack-trace.img`: 8388608 bytes, SHA-256
  `27a78a225a840040f5e88b36f0ff75367caef3412ea26ac17ac83e24b4c23ce0`
  (built twice, byte-identical; stock header and signed tail unchanged;
  LZ4 HC-12 frame 2104221/2117632).
- `vendor_boot_b` carrier rebuilt byte-identical: `a71b3f5f` (stays
  installed; not flashed).

## Coordinator handoff (one flash of `init_boot_a` only)

Under the standing `full_autonomy_device_iteration` approval: flash only
`init_boot_a 27a78a22…` after the standing verified-backup/fastboot gate;
pre-arm the `:2222` capture BEFORE one `fastboot reboot` (run-92/94
pattern); NO pid1-ack until the pre-ack window has been observed — the
trace must be captured in the automatic fresh-boot condition (armed,
unacknowledged guard). If the no-ack deadline self-returns the device, the
pre-armed kmsg/capture holds the evidence. Guest phase is read-only: pull
the full pre-ack kmsg trace and `self-post.log`, identify the last reached
trace point and the first absent one; the guard shape at self-post time is
in the `trace_state` lines themselves. No manual remoteproc/radio writes, no
re-run of `pmos-self-post.sh` by hand, no reflash of any never-reflash SHA.

Outcome (a)-(d) per the issue; the fix (if any) is the next issue, not this
one. Not WLAN acceptance: acceptance stays two fresh self-starting boots per
PLAN.md.
