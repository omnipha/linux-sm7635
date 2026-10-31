---
date: 2026-10-31
run: 77
issue: omnipha/linux-sm7635#223
subsystem: boot
result: refuted
---
# run 77 verifier race pre flash stop

## Measured finding

Run 77 corrected the run-76 refusal cause and then stopped at the pre-flash verifier gate a second time, without any candidate write. The merged `origin/main` verifier at `ab299cf` (`sha256 ab033d47…bf67`) verified the unchanged PR #225 pair `init_boot becd3784…e72b4` and `vendor_boot_b adb47dc0…aeae8` with a passing self-test (72 refused hashes, stock header/tail, signed tail unchanged). The run-76 failure trace had instead loaded the verifier from the stale root worktree on branch `records/run69-second-boot-guard-refused`, whose `scripts/` differs from `origin/main` (missing renamed helper module); the coordinator event also never passed the candidate paths. The refusal was therefore a host checkout error, not a property of the pair.

Before the reserved flash, the assigned #223 worker began editing `build-init-boot-persistent-root.py` and `verify-init-boot-persistent-root.py` in the shared issue-223 worktree (branch `coldstart-verifier-run66-preservation`, four modified scripts, worktree no longer clean). The repeat self-test with the same five image arguments then failed with `init must keep the measured run-66 handoff and change only the root-contract pin`, so the settled-verifier precondition was gone and no `init_boot_a`/`vendor_boot_b` write, boot or cold start was attempted. No verifier bypass, no run-66 pin weakening, no operator image-SHA request and no reflash of refused hashes.

## Device and rescue state (unchanged, measured)

Diagnostic boot `1d3bdaea-36c1-4e5e-85c6-1b0861c76814` of the unchanged installed chain (`init_boot_a 2f73c947`, `vendor_boot_b f792174c`) reached key-only SSH uid=0 on `172.16.42.2:22` with pinned host key `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`, set guest-owned root-only `/run/keep` (`0:700`) and read exact `PARTNAME`-mapped hashes: stock `boot_a 197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`, `vbmeta_a cc1926d2`; installed `init_boot_a 2f73c947`, `vendor_boot_b f792174c`. Host backup manifests `parts.sha256`, `parts-a.sha256`, `parts-b.sha256` all OK. `/bin/restart2 bootloader` returned the phone to fastboot `00181152O003821`, slot `a`, unlocked, `is-userspace: no`, product `pineapple`, `init_boot_a 0x800000`, `vendor_boot_b 0x6000000`. No stock restore, no `userdata` erase, no Android boot, no open session. Raw evidence: `~/phone-second-life-data/mb003/pstore/attempt-20261031-0610-coldstart-corrected-verifier-run77/` and sprintberlin/phone-second-life@3953968 `devices/mb003.md`.

## Next step

The existing #223 worker finishes the verifier/build-contract repair in its own tree (no coordinator write while it is dirty). When its repair is merged or the worktree is synchronized and clean, the coordinator reruns the same full preflight on the settled candidate and, only if the verifier passes, performs the single scheduled cold start with the existing stop rules and readback proof. No new SHA is requested.
