---
date: 2026-11-04
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# host parser defect reproduced under QEMU

## Host boundary

The run-113 old awk check strictly required a one-line `ip -4 route get`
reply:
`NR == 1 {for ...} END {exit(NR != 1 || ...)}`.
In a host-isolated dummy-interface namespace under QEMU AArch64, the pinned
session archive's `/sbin/ip` (`iproute2-minimal 6.11.0-r0`, archive SHA-256
`7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26`)
returned:
```
1.1.1.1 from 192.0.2.2 via 192.0.2.1 dev wlan0 uid 0
    cache
```
The old awk rejects this two-line output through the `NR != 1` exit branch,
causing the surrounding success gate to record `internet route is not wlan0`.
`python3 -B scripts/test-success-gate-route-cache.py` reruns that rejection,
the corrected-parser acceptance of the recorded bytes, and its fail-closed
matrix without device access. The original QEMU run stays recorded in
`records/2026-11-04-102445-run113-route-cache-diagnosis.md`.

## Host-only candidate boundary

The separately reviewed host deriver
`scripts/derive-route-cache-gated-ack.py` maps the pinned original post/hook
to candidate post
`92f6f9cdfa3dcdc8854c7481fe01b500591f1b2b1c9908e97c4cdbfc0ae68d0c` and hook
`5bc5b0f4e2820aef8ae11b5b3e1f9264a0c7fe5fc60f8686718fb955b376fc3a`.
`scripts/test-success-gate-route-cache.py` exercises that derived parser with
positive and fail-closed negative cases using the recorded route bytes. It does
not contact a device or establish the physical run-113 output.
