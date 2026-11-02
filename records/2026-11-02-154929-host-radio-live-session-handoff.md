---
date: 2026-11-02
issue: omnipha/linux-sm7635#280
subsystem: wlan
result: confirmed
---
# Host handoff: the installed radio script refuses an acked guard before the modem stage; one live probe must confirm outcome C

Issue #280 phase 1, host only. No device, USB, boot, image build or partition
access. This record prepares the one no-flash live session on installed
`init_boot_a 2ebdf1db26193f7f0c3f4c6d42f722008bd1ee2718adf399dfe4927cc3eb9632`
and `vendor_boot_b a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3`.
Neither image may be reflashed. No production script, guard, nonce interlock,
self-post instrumentation or automation changes.

## Host finding: run 69's post-ack ordering no longer applies

Run 69 used a radio script that required an acknowledged guard
(`records/2026-10-30-203515-run-69-second-boot-guard-wlan.md`). Commit
`8731609` deliberately inverted that contract for the host-free cold start:
every current non-`prepare` radio stage requires `armed` for this boot, a
regular `nonce`, and no `accepted` or `ack`
(`scripts/pmos-radio-bringup.sh:165-169`). A successful ack writes `accepted`,
then deletes `nonce` and `ack` before the guard exits
(`scripts/pmos-pid1-guard.sh:108-115`). Run 94 measured exactly that acked
shape (`records/2026-11-01-165231-run94-nonmount-inputs-all-pass.md:44-49`).

The installed staged radio script is the persistent-root derivative of this
same source. Run 90 measured its SHA-256 as
`f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f`
(`records/2026-11-01-104332-preack-selfpost-record-append-refused.md:21-23`);
the unchanged carrier is the source of that staged member. Its armed-and-
unacknowledged gate precedes the capture gate, attempt marker and the only
remoteproc start. Consequently, on the acked session its first refusal is
predicted verbatim as:

```
radio-bringup: FAIL modem: PID 1 guard is not armed and unacknowledged on this boot
```

That is issue outcome (C), not (A) or (B): the chain cannot start from the
acked live session. The three run-69 operational repairs cannot change this
ordering. Re-running self-post is not an alternative: it has the same guard
requirement, and run 97 already measured its earlier ordered-sequence append
refusal. `prepare` is diagnostic-init-only, not a post-cutover radio stage.
Do not recreate a nonce, manufacture a marker, alter a script or manually
write remoteproc state to evade the refusal.

## Coordinator handoff: one boot, one ack, session stays open

Under standing `full_autonomy_device_iteration`, the physical coordinator
owns this phase. Use the established run-93/94 procedure, not a new device
mechanism:

1. Verify the host backup manifests and current responsive fastboot identity;
   record the planned no-flash boot of the exact installed pair above. Check
   the stock slot-A rescue hashes and never-reflash ledger. No flash, erase,
   Android boot or cold start.
2. Create a fresh attempt directory and mode-600 single-entry `kh2222` for the
   pinned guest key. Pre-arm the `:2222` capture with the existing
   `session-capture.py start` before one `fastboot reboot` of the installed
   chain. Do not dispatch a worker into the pre-ack guard window.
3. Require `capture/ready.json` on the new boot ID, key-only root SSH with the
   pinned known-hosts file, root-only `/run/keep`, the expected PID 1 and a
   fresh capture check. Open the session with `device-op.py session open`,
   then prove `device-op.py handoff` using this attempt directory, boot ID and
   a fresh marker, exactly as runs 93/94 did.
4. Wait until guard `armed` equals that boot ID. Invoke the repo's pinned
   `sh scripts/pmos-pid1-ack.sh EXPECTED_BOOT_ID ATTEMPT/kh2222 CLIENT_KEY`
   exactly once, with the coordinator's designated key. Require `accepted`
   for the same boot ID. A failed strict probe is not a retry license.
5. Re-read the stock and installed hashes read-only and run the capture check.
   Keep the successful session and capture open. Return this same issue and
   context with boot ID, host `172.16.42.2`, port `2222`, attempt/capture path,
   known-hosts path, handoff marker and the one-ack result. Do not run the
   radio experiment or close the session in this phase.

If the one ack does not succeed, report that coordinator result rather than
representing the session as acked; do not issue a second ack. The worker must
not treat an unacked session as the requested experiment.

## Worker live probe: pinned script only, bounded and reversible

After independently rechecking the supplied boot ID, key-only SSH, pinned host
key, advancing capture, root-only `/run/keep`, PID 1 and the acked guard state
(`armed` and `accepted` name this boot; `nonce` and `ack` are absent), verify
that `/run/radio-bringup/pmos-radio-bringup.sh` hashes to the measured pinned
value above. Then make exactly one attempt, with no marker:

```sh
sh /run/radio-bringup/pmos-radio-bringup.sh PROVEN_BOOT_ID modem
```

Replace `PROVEN_BOOT_ID` with the independently rechecked current boot ID. Capture stdout,
stderr and exit status without printing any secret. The missing marker is
intentional: the guard gate must refuse before `capture_gate`; no valid
nonce-derived marker can exist after the ack. This invocation performs no
manual remoteproc write outside the pinned script.

Report exactly one outcome:

- (C) the predicted guard refusal, or another named pre-radio refusal: quote
  the first error and stop the radio experiment. Do not retry, run `prepare`,
  re-run self-post or change the interlock in this session.
- (B) a named radio stage fails after the guard gate: name the stage and first
  error, preserving the pinned-script logs in root-only guest RAM.
- (A) stages run: record modem, WPSS, driver and wlan0 separately, then scan,
  association, address, DNS and internet separately. Never infer association
  or connectivity from a scan. One boot is not two-boot WLAN acceptance.

If (C) is measured, the issue acceptance as written is not met; the named
in-session blocker is the result for the plan owner's deferred guard-design
decision. The coordinator closes only after that measured result, using fresh
rescue hashes, capture stop and the existing bounded session-close path.

## Host verification

`scripts/test-pmos-radio-bringup.sh` now replays the exact consumed-nonce
acked state: `accepted` present, `nonce` absent, no marker supplied. The
unchanged radio script refuses at the armed-and-unacknowledged gate and does
not create `modem.attempted`; the existing accepted-with-nonce negative and
all positive stage fixtures remain green. No production bytes changed.
