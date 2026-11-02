---
date: 2026-11-02
run: 95
issue: omnipha/linux-sm7635#265
subsystem: wlan
result: confirmed
---
# Run 95: the automatic pre-ack self-post exits at the armed-and-unacknowledged check because `guard/nonce` is absent

Issue #265 outcome (a), H2 confirmed for one named check. Measured on boot
`f0d1050e-3a19-4eb1-b0ba-ad03a16eeb70`, coordinator attempt dir
`~/phone-second-life-data/mb003/pstore/attempt-20261102-0925-preack-trace-run95/`
(host-only, not in git). The record reads the files themselves
(`kmsg-r95-final.log` and `capture/kmsg.log`, both 170411 bytes and
byte-identical by `cmp`), not the coordinator summary.

## Pair and session

Exactly one partition write: `init_boot_a`
`27a78a225a840040f5e88b36f0ff75367caef3412ea26ac17ac83e24b4c23ce0`
(the #266 trace-only image; `flash init_boot_a: verified: ok`). `vendor_boot_b`
`a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3` stayed
installed (read back unchanged in `session-hashes-close.txt`); stock
`boot_a 197aff11…`, `vbmeta_a cc1926d2…`, `dtbo_a 759813db…`,
`vendor_boot_a 23725940…` read exact. Key-only SSH on the staged root,
`handoff: ok`, `/run/keep` root-only, PID 1 `init` on the same boot id,
capture armed before the single `fastboot reboot`. The pid1-ack was never
taken (pre-ack window observed as designed): the `pid1-ack` string does not
occur in the kmsg, and the guard directory read `armed` only.

## The trace (kernel seconds, from `kmsg-r95-final.log`)

| kmsg time | trace point |
| --- | --- |
| 155.484 | `usb-init: pid1 handoff accepted` |
| 155.964 | `usb-init: pid1 transition guard armed; exec switch_root` |
| 156.395 | `self-post-trace: start rc=0` (the hook did run the script) |
| 156.435 – 156.435 | OpenRC wait enter and exit, rc=0 (no wait needed) |
| 156.447 | `pid1 exe identity passed` |
| 156.449 – 156.450 | `root mounts not all tmpfs; guard contract fallback entered`, `guard contract sourced` |
| 156.535 | `root mount table or guard contract passed` (`root_contract_switched_root` PASSED) |
| 156.537 – 156.541 | `pid1 root identity`, `guard armed boot id`, `guard root identity` all passed |
| 156.543 | `post check switched-root and guard identity rc=0` |
| 156.543 – 156.545 | `pre`/`post check run keep rc=0` |
| 156.546 | `pre check guard armed and unacknowledged rc=0` — **last reached** |
| 156.548 | `FAIL: independent recovery guard is not armed and unacknowledged` |
| 156.549 | `record_fail entry` |

First absent trace points: `post check guard armed and unacknowledged`, then
`pre check post-cutover contract`, `record append entry`/`exit`, `record
verify entry`/`exit`, and every radio-stage marker. `boot_record_append` and
`boot_record_verify` were never reached, so the run-90 refusal inside
`boot_record_append` is NOT what stops the automatic chain: the chain stops
~12 ms of script time earlier, at the check in
`scripts/pmos-self-post.sh`:

```
[ -f "$GUARD/armed" ] && ... [ "$(cat armed)" = "$boot" ] &&
[ -f "$GUARD/nonce" ] && [ ! -L "$GUARD/nonce" ] &&
[ ! -e "$GUARD/accepted" ] && [ ! -e "$GUARD/ack" ] || die ...
```

## Self-post-time guard state (the trace's own `state` lines, not a re-invocation)

Identical at script start (156.396–156.411) and at `record_fail` entry
(156.550–156.563):

- `guard/armed`: present, regular file `0:600:1:37`, value = boot id
  `f0d1050e-…` (matches)
- `guard/nonce`: **ABSENT**
- `guard/accepted`: absent; `guard/ack`: absent
- `guard/root-identity`: present `0:600:1:7`, value `2061:2`
- `guard/root-contract.sh`: present `0:700:1:14807`; `guard/guard.sh`:
  present `0:700:1:10705`
- guard dir mode `0:700`
- `/run/keep`: present, regular, empty, `0:600:1:0`
- `/run/pmos-root-contract.sh`: **absent** (the run-90 observation again; the
  guard copy is the one the script sources; irrelevant until the nonce check
  passes, but it will matter at the following `contract=` step)
- uptime `156.40` at start, `156.55` at fail

So the guard was armed and unacknowledged, but its nonce had not been
minted when self-post asked for it, and it was not minted for the rest of the
window.

## Why the nonce is absent (reading of the pinned guard, no check changed)

`scripts/pmos-pid1-guard.sh` `watch()` creates `armed` first, then loops once
per second and only writes `nonce` after its own `post_root` is true.
`post_root` requires `/proc/1/exe` to hash like `/bin/busybox`, `stat -Lc
%d:%i /proc/1/root` and `stat -c %d:%i /` to equal the staged
`root-identity` (`2061:2`), and the single-root mount test or the contract
fallback. Self-post evaluated its own copy of the same identity and
contract checks at 156.45–156.54 and every one passed, and `armed` and
`root-identity` were visible in the guard directory. Two separable readings
remain and are NOT decided by this boot: (a) timing — the guard's
one-second poll plus chroot start had not yet run a `post_root` that
succeeded when self-post asked (script start is only ~0.43 s after the
transition line), and the nonce was still absent as of `record_fail`; (b) a
`post_root` input that differs inside the guard's chroot from self-post's
view. The kmsg carries no guard-loop line, so this is the next variable and
belongs to a separate dossier-step issue, not to this one.

## Designed return

No ack was taken. At kernel 315.94–316.00 s the kmsg shows the SCSI-cache
sync (`Synchronizing SCSI cache` on sdf/sde/sdd/sda). The transition armed a
160-second budget at 155.96 s (deadline ~315.96 s), so these lines are at the
guard deadline; the kmsg itself carries no explicit "returned to fastboot"
line, and the coordinator's readback of boot `f0d1050e` shows that boot was
reachable before the deadline. The coordinator reports the device returned to
responsive fastboot at about +170 s, and `guard-state.txt` shows `armed` only
with no `nonce`, `accepted` or `ack`. A `smcinvoke_adci_` hung-task warning
appears at 242.66 s, before the deadline; it is unrelated to the self-post
exit and was not investigated. The capture's `ssh failure` lines after 09:30
are the link closing at the return. Coordinator-side: the device-op
session closed with rescue verification (slot-A rescue hashes exact) and the
final fastboot gate matched; `init_boot_a 27a78a22` stays installed and is
never-reflash.

## Outcome

Outcome (a): the trace stops at a named check. H2 is confirmed for the
`armed and unacknowledged` check (nonce absent at self-post time), not for
`boot_record_append`; H3 (non-invocation) and H4 are refuted for this boot.
No check, timing or content logic was modified and no fix is made here: the
nonce check is the safety interlock with the guard and must not be loosened
to make self-post pass. The next single variable (guard `post_root` timing
versus inside-chroot divergence) is a separate issue. Not WLAN acceptance:
acceptance stays two fresh self-starting boots per PLAN.md.
