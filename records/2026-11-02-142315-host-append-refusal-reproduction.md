---
date: 2026-11-02
issue: omnipha/linux-sm7635#275
subsystem: wlan
result: confirmed
---
# Host: the absent-contract run-96 refusal is the ordered-sequence check, caused by the panel record lost at switch_root

Host only. No device access; the run-96 capture and parts under
`~/phone-second-life-data/mb003/` were read, never modified or committed.

## Reproduction on the unchanged contract (before any fix)

The real `scripts/pmos-root-contract.sh` (`c76c31ff…`, unchanged in this issue)
was driven in a throwaway root with only `boot_record_root` satisfied by the
fixture. Twelve pre-cutover appends were made with the run-96 panel line as
record line 3, exactly as the shipped stage produces it
(`build-init-boot-persistent-root.py` panel preservation block):

```
pre-cutover-ok lines=12
panel-absent: REFUSED
panel-present: ACCEPTED
```

The only difference between the two runs is the presence of
`/run/pmos-pre-ssh-panel.record`. The refusal is inside
`boot_record_append`'s ordered-sequence case at `pmos-root-contract.sh:323-337`:
`boot_record_lines` rebuilds the expected record from the panel FILE. With the
file absent, `br_all` lacks the panel line that the persisted record already
contains, so `br_all != br_next` and the FAIL-only fallback rejects the
non-FAIL post-cutover line.

## Why the panel file is absent after cutover (host fixture, not inference)

1. The display phase writes the panel line and logs it to this boot's kernel
   log (run-96 capture kmsg line 2393, `usb-init: usb-init: pre-SSH panel
   node=boe card0=1 dsi1=1 dcs=none reset=none suspend=clear brightness=0 boot
   3e541430-…`, uptime 14.74).
2. The stage appends it to the persistent record and copies it to
   `/run/pmos-pre-ssh-panel.record` on the OUTER initramfs `/run`.
3. `switch_root` (pmos-pid1-transition.sh) leaves that outer `/run` behind; the
   guest `/run` is its own tmpfs. Only `guard.sh` and `root-contract.sh` are
   copied into the guest guard directory (`pmos-pid1-guard.sh:182-189`), not the
   panel record. `boot_record_lines` then omits line 3 from the expectation.

The existing ext4-ack fixture never caught this because it builds its
pre-cutover record from the REPO base `pmos-session-stage.sh`, which has no
panel block; the panel block is added only by the image builder. The run-96
shape is now exercised in `test-pmos-root-contract.sh`.

## What is measured vs inferred

- Measured (host): the ordered-sequence check refuses exactly on this shape and
  accepts with the file restored; run 96 reached `record append entry` and then
  refused (correction record 2026-11-02-130607).
- Not measured on the phone: which individual `return 1` fired in run 96
  (the function was not instrumented there). This host reproduction is the only
  demonstrated mechanism consistent with the capture; `boot_record_root` had
  already passed the same checks at 156.49, and runs 93/94 eliminated the
  non-mount inputs. The new image names the refusing check in kmsg so a live
  run cannot leave this ambiguous again.
- The pre-SSH panel line is independently attested in THIS boot's kernel log,
  so restoring it does not make the ordered-sequence check tautological: the
  record line must equal the kmsg-attested line, not vice versa.
