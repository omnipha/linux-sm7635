---
date: 2026-11-04
run: 113
issue: linux-sm7635#311
subsystem: wlan
result: inconclusive
---
# run113 route refusal attribution remains inconclusive

## Device evidence and limitation

Run 113 reached the internet success-gate stage after association, address,
default route and gateway passed. At uptime 199.62 s, that stage refused with
`internet route is not wlan0`; no guard ACK was published. The original
measurement is recorded in
`records/2026-11-04-093054-run113-pair-installed-internet-route-gate-refused.md`.

The live `ip route get` output was not preserved in the capture or pstore.
The independently reproduced two-line `dev wlan0` / `cache` parser defect
is a sufficient possible explanation, not evidence that this was the actual
run-113 output or cause. The device attribution therefore remains inconclusive.
See `records/2026-11-04-141023-route-cache-candidate-provenance.md` for the
confirmed host-only boundary.

## Decision and authorization correction

The physical coordinator's decision
([#311 comment](https://github.com/omnipha/linux-sm7635/issues/311#issuecomment-6635134969))
splits the claims above: the host defect is confirmed, device attribution is
inconclusive. No device iteration for #311 is planned now: WLAN and any
route-cache candidate await the reviewed migration path from #324. No live-route
measurement boot, candidate build or candidate flash is authorized before that
architecture exists. The physical coordinator retains all device decisions and
applicable preflight, backup, rescue and capture gates.

The earlier integration record
`records/2026-11-04-113000-route-cache-variant-integration.md` incorrectly
called removal of old post/hook files "human-gated". The supervisor clarified
that `full_autonomy_device_iteration` is standing approval within its scope,
including coordinator-owned removal of old files; no separate ad-hoc human
approval should be inferred for that operation. This does not authorize an
operation in this record, override mission-shift gates or alter the current
hold.

## Status

No device was contacted for this host-only record. The installed measured pair
(`init_boot_a` `d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c`,
`vendor_boot_b` `221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500`)
and existing guard, nonce, ACK and pin checks remain unchanged; no WLAN pass
is claimed. Issue #311 remains open pending its coordinator-owned physical phase.
