---
date: 2026-11-02
issue: omnipha/linux-sm7635#280
subsystem: wlan
result: confirmed
---
# Host: post-ack variant of the radio script, derived from the staged copy

Owner decision 2026-11-02: the radio chain starts from the acknowledged live
session; after the ack the guard no longer returns the phone to fastboot, and
a kernel crash then needs a manual restart. Accepted.

Problem (host derivation, record 2026-11-02-154929): the pinned
`pmos-radio-bringup.sh` requires an armed, unacknowledged guard with a nonce
and gates every stage on a nonce-derived marker. The ack writes `accepted`
and deletes `nonce`, so every stage refuses on an acked session.

`scripts/derive-radio-postack.py INPUT OUTPUT` replaces exactly two blocks
and fails closed if either is not found exactly once:

1. guard check: armed == boot ID, accepted == boot ID, no `ack` file
2. `capture_gate`: the fresh host capture marker must be in this boot kmsg

Everything else, including every remoteproc, rmtfs, firmware and one-shot
guard, stays byte-identical. `scripts/test-derive-radio-postack.py` checks
the replaced text, that the untouched tail is identical, that changed input
is refused, and `sh -n` on the output.

Use on the device: derive from the script staged on the phone (the
persistent-root builder patches the repo copy, so derive from
`/run/radio-bringup/pmos-radio-bringup.sh` fetched over the live SSH
session), copy the result into the session's RAM, and run the stages in
order with the capture marker. The repo script, the installed images and the
self-post pins are not changed; no flash.
