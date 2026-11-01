---
date: 2026-11-01
issue: omnipha/linux-sm7635#263
subsystem: wlan
result: confirmed
---
# Run 94 post-ack non-mount inputs: every captured value passes the unchanged contract; the run-90 refusal is not in any post-ack-observable input

Issue #263 outcome (b), measured on the installed never-reflash run-87
pair (`init_boot_a f9449ba5` / `vendor_boot_b a71b3f5f`), boot
`ec970efc-b8fd-4fad-840f-047533609d22`, coordinator attempt dir
`~/phone-second-life-data/mb003/pstore/attempt-20261101-1750-postack-nonmount-run94/`
(host-only, not in git). One no-flash fastboot reboot only; no flash, no
partition write, no cold start.

## Session (coordinator-proven, independently rechecked)

Key-only root SSH `172.16.42.2:2222` with the pinned host key
(SHA256 `fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`, `kh2222`),
`capture-check-r94.json` ready+service true on boot
`ec970efc-b8fd-4fad-840f-047533609d22`, `session-open-r94.txt`
"session open: ok", `handoff-r94.txt` "handoff: ok", marker
`run94_handoff_1793551130_263`, root-only `/run/keep` present,
postmarketOS v24.12 `init` PID 1 on the same boot id. The run-93 session
was closed first with exact rescue verification (manifests 31/31 OK).

Exactly one host pid1-ack, consumed and ACCEPTED
(ack-r94.txt 2026-11-01T16:41:16Z, ACK_RC=0) — the guard-deadline
removal landed on this boot. No second ack was issued.

## Captured live non-mount contract inputs (read-only, `nonmount-inputs-r94.txt`)

1. **`/sys/class/block/*/uevent` PARTNAME walk**: 146 devices (loop0-15,
   ram0-15, sda + sda1-13, sdb + 5, sdc + 5, sdd + 3, sde + sde1-77,
   sdf + 5). Exactly ONE `PARTNAME=userdata` in the whole walk: `sda13`
   (8:13). No loop/ram/disk whole-device carries a PARTNAME; every other
   partition name is distinct (super, metadata, modemst1, …).
2. **Guest `/dev/block/sda13`**: a real root-owned block node
   (`br-------- 1 root root 8,13`, mode 0400, no `stat` applet in the
   guest), `/sys/class/block/sda13/dev` = `8:13`, `/size` =
   `471526808` sectors.
3. **`blockdev --getsize64 /dev/block/sda13`** = `241421725696` bytes —
   present in the guest PATH and equal to the contract maximum.
4. **`/run/pid1-guard`**: `0:700`, contains `guard.sh`, `root-contract.sh`
   (14807 B), `root-identity`, `armed` = boot id AND `accepted` = boot id;
   `nonce` and `ack` absent. This reconciles the run-93 strict-probe
   nonce discrepancy read-only: on an acked boot the guard directory has
   no `nonce` file (run 93's probe failure was the acked-state shape, not
   an anomaly).
5. **`ROOT_CONTRACT_` env** in an interactive root login shell: unset
   (`env | grep '^ROOT_CONTRACT_'` rc=1) — the contract defaults
   33554432..241421725696 apply, and the measured size is an exact fit.

## Host replay (this commit)

`scripts/test-pmos-root-contract.sh` gains a new run-94 case after the
run-93 family: the complete captured 146-device sysfs walk (real names,
devnums and PARTNAMEs, `-` entries reproducing live uevents without
PARTNAME), the real node shape (regular block node 0400 at devnum 8:13,
sysfs size 471526808 sectors) and the measured `blockdev` size via the
same wrapper pattern as the existing oversize case, replayed against a
mount table whose root row carries the captured `8:13`. The UNCHANGED
`root_contract_switched_root` ACCEPTS all of it (identity `ext4 /`,
node `/dev/block/sda13`, size 241421725696, opts
`rw,relatime,norecovery`); a new negative flips `sda6` to a second
`PARTNAME=userdata` and is refused. The whole existing fixture family
including all negatives stays green (inner, ext4-ack, ext4-timeout).
No contract or pinned production script was modified.

## Outcome

Outcome (b): every post-ack-observable non-mount contract input measured
on the live device passes the unchanged contract. Combined with run 93
(mount inputs measured equal), H1 is eliminated for all inputs reachable
after the ack: the run-90 `boot_record_append` refusal lives in
pre-ack/self-post-time state that no post-ack read can see (most
plausibly the self-post-time guard state — run 90 ran pre-ack with an
armed, unacked guard, while this boot is acked with `accepted` present).
Per the issue, this is the stop point: self-post-time instrumentation is
explicitly dossier step 3, not this issue. No check change, no fix.

Not WLAN acceptance: acceptance stays two fresh self-starting boots per
PLAN.md.
