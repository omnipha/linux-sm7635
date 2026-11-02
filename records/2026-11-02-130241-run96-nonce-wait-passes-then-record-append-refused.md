---
date: 2026-11-02
run: 96
issue: omnipha/linux-sm7635#271
subsystem: wlan
result: inconclusive
---
# Run 96: the nonce wait works, the nonce is minted, then self-post refuses at the post-cutover boot record append

Issue #271 outcome (C): one named check refuses after the nonce passes. Measured
on boot `3e541430-b528-4f71-82c5-4e3bab877415`, coordinator attempt dir
`~/phone-second-life-data/mb003/pstore/attempt-20261102-1355-nonce-wait-run96/`
(host-only, not in git). This record quotes the captured kmsg directly
(`capture/kmsg.log`, 172398 bytes, SHA-256
`bd1ce32390bd8de719466f9e33087517c765246045786030818b24c7018c810a`).

## Pair and session

Exactly one partition write: `init_boot_a`
`17531039e2c1bb36eac7c5fb2d4c343d53977950cbd2ade0d9dea6f3dd794bdd`
(`init_boot-nonce-wait-271.img`, 8388608 bytes; `flash init_boot_a: verified:
ok` at 12:54:48Z, preflight and postflash hooks PASS). `vendor_boot_b`
`a71b3f5f…` stayed installed; the byte-identical companion output was not
flashed. Stock `boot_a 197aff11…`, `vendor_boot_a 23725940…`, `dtbo_a
759813db…`, `vbmeta_a cc1926d2…` read exact on-device. Key-only SSH on the
staged root (`:2222`, pinned host key), root-only `/run/keep`, `device-op
session open` and `handoff` PASS (marker `run96_handoff_1793624115_271`).
**No pid1-ack was sent**, as required.

## The measurement (outcome C, in order, from kmsg)

1. `pre check guard armed and unacknowledged rc=0` at uptime 156.50.
2. `guard nonce wait 0 rc=0` at 156.50 — exactly one wait line: the nonce was
   already there; **the #270 wait itself executed and passed on iteration 0**.
3. `post check guard armed and unacknowledged rc=0` at 157.51; state snapshot
   shows `guard/nonce present [65 bytes]` — minted about 1.0 s after the wait
   started, consistent with the run-93/94 mint timing.
4. `pre/post check post-cutover contract rc=0` — the guard-copy fallback for
   the absent `/run/pmos-root-contract.sh` worked.
5. `record append entry rc=0`, then **`FAIL: post-cutover boot record append
   refused`** at uptime 157.62; `record_fail` state again shows
   `/run/pmos-root-contract.sh absent`.

No modem/wpss/driver/scan/services stage ran. The refusal is the same
post-cutover append boundary already measured in run 90, now reached after the
nonce wait instead of never getting there. The radio stages remain unmeasured.

## Window and rescue

The session stayed SSH-reachable well past the refusal (uptime 257 s), then the
independent no-ack guard returned the device to responsive fastboot (~13:00Z).
Capture stopped clean (no kernel fatal; designed SCSI shutdown tail). Final
fastboot gate exact (serial `00181152O003821`, slot a, unlocked, pineapple,
`is-userspace: no`); `rescue-verify-close.sh` `RESCUE_VERIFIED`; on-device
hashes at close: stock slot-A set exact, installed `init_boot_a 17531039`,
`vendor_boot_b a71b3f5f` exact. `device-op session close unresponsive` PASS.
Linux stays installed (owner rule); no stock restore, no `userdata` erase, no
Android boot, no second write of 17531039.

## What this fixes and what stays open

Fixed on the phone (both #270 hypotheses): the nonce wait runs and the nonce
appears within its first second, and the contract fallback passes. The one
remaining named refusal before any radio stage is the post-cutover boot record
append when `/run/pmos-root-contract.sh` is absent — the known
`record_fail`-has-no-guard-copy-fallback limit already documented in the #271
host record. The radio chain (modem, wpss, driver, scan, services) is still
unmeasured on the installed persistent-root chain.
