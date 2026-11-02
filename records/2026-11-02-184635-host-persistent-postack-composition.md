---
date: 2026-11-02
issue: omnipha/linux-sm7635#286
subsystem: wlan
result: confirmed
---
# Host-only #286: post-ack persistent radio variant composed, hashes pinned, fixtures replayed; live run deferred

Worker phase of #286, base `4fb6bd9016f411049f01b0cde16615b3c1034129`
(== origin/main). No device contact, no image, no flash. Live run awaits the
coordinator-proven acked session per mission-shifts.md.

## Composition (all hashes computed twice, independent runs)

| Variant | SHA-256 |
|---|---|
| run-98 staged (builder `current_scripts()`) | `f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f` |
| staged + postack (run 98 used) | `34a67bb43090f5ad21f5490ccdb9594fbff5ce12b3375fa6ebcd2a65233579ee` |
| staged + persistent (#284) | `c54c29e1278827bc00faaf506c7ff8e923a8a689a011a2852d5d4b7778d0188d` |
| **staged + persistent + postack (live target)** | `71c7b15d8c5507354268c9e0ccc49279b1e46c4e6a7fd5689bc6e21ef572202d` |

Derivation order: `derive-radio-persistent.py` then `derive-radio-postack.py`.
The two derivations commute (both orders byte-identical); all four variants
pass `sh -n`. Composed output keeps `LEASE_SHA=1fbf50af…`,
`own_digest()`, `armed and acknowledged on this boot`; no
`unacknowledged` guard remains. Outputs live in `/tmp/opencode/run99/`
(outside Git).

## Test change

`scripts/test-derive-radio-persistent.py` now pins the composed hash,
asserts commutation, the lease pin and the post-ack guard marker. Installed
`pmos-radio-bringup.sh` (`7ef63826…`), the committed persistent variant
(`58476d77…`), all image pins and the nonce interlock are byte-identical.

## Fixtures (all pass, host-only, this host)

- `test-derive-radio-persistent.py`, `test-derive-radio-postack.py`
- `test-pmos-radio-bringup.sh` (both variants; own-output replay, foreign
  conf.d/runlevel/profile refusals, capture-gate and nonce negatives)
- `test-pmos-session-dev.sh --stage-only` (real OpenRC guest)
- `test-pmos-self-stage.sh`, `test-pmos-boot-record.sh`,
  `test-pmos-root-contract.sh`, `test-wlan-udhcpc-lease.sh`

## Live recipe for the returned session (not yet run)

Coordinator: one boot of installed `init_boot_a 2ebdf1db…` +
`vendor_boot_b a71b3f5f…` (never-reflash), pre-armed `:2222` capture,
key-only SSH handoff, exactly one pid1-ack, session held open. Worker then,
over pinned SSH only, after independently rechecking boot ID, capture,
accepted guard and staged hash `f54b3372…`:

1. Transfer `/tmp/opencode/run99/staged-persistent-postack.sh` to a root-only
   RAM path; recheck sha256 `71c7b15d…` on device before every stage.
2. Run ONLY the pinned derived chain, in order, each with a fresh capture
   selftest marker: `prepare` (if present as a stage), `modem`, `wpss`,
   `driver` (wlan0), `scan`, `services` (WLAN profile on stdin, never in
   argv/logs), then measure association, DHCP, DNS, external reachability.
3. If `services` refuses (expected candidate: `/run` helper recreation gap,
   own-output check, foreign-state check), record the exact refusing check
   and stop there. No hand-replay of RAM helpers — the refusal IS the result.
4. Outcome A/B/C per issue #286. Known run-98 deviation to expect: empty
   unmounted `/vendor/firmware_mnt` may need one `rmdir` before `modem`.

Not WLAN acceptance: one host-assisted boot. Issue stays open;
`AWAITING_PHYSICAL_RESULT` until the coordinator hands off the acked session.
