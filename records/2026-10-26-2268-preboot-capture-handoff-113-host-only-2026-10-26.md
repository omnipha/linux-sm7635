---
date: 2026-10-26
issue: omnipha/linux-sm7635#113
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Preboot capture handoff (#113, host-only, 2026-10-26)

**Host-only sequence, not a device result.** No image was built, packaged,
signed, or flashed. The 150 s timer, `/run/keep` semantics, and the 25 s WLAN
hold are unchanged. `0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7`
and every earlier measured SHA remain never-reflash.

Run 40 measured key-only SSH at uptime 120 s. The unchanged recovery deadline
is 150 s, so the residual budget after that measured SSH point is 30 s. The
synthetic gate below uses 1 s to observe capture-ready state, 2 s for the fresh
marker, and 1 s to permit keep. Keep is therefore predicted at uptime 124 s,
with 26 s remaining before the deadline. Those four durations are planning
allowances, not new physical measurements.

| event | simulated time | required evidence |
| --- | ---: | --- |
| capture listener | -4 s | listener is already running |
| gadget route/link | -3 s | `172.16.42.1/24`, link ready |
| preflight | -2 s | both checks pass |
| simulated reboot | 0 s | no reboot before preflight |
| SSH accept | 120 s | this boot's SSH identity |
| capture ready | 121 s | ready state names this boot |
| selftest start | 121 s | marker from this SSH session |
| fresh marker | 122–123 s | line arrives after selftest starts |
| `/run/keep` | 124 s | only after `ok=true` for this boot |

`scripts/verify-preboot-capture-handoff.py` is synthetic and fail-closed. It
rejects a listener or route that becomes ready after reboot, a selftest or keep
at or after 150 s, a marker belonging to another boot, a marker already present
before the selftest starts, keep when selftest did not pass, and a route whose
link is down. Preboot service state alone cannot pass because the ready boot
identity and a post-start line are both required.

Coordinator handoff for a future **separately authorized** session: use a new
attempt directory outside Git and a previously verified, pinned SSH host key.
Before any reboot, start `omnipha/agents/scripts/session-capture.py start` for
that directory with `--target root@172.16.42.2` and `--known-hosts-file` pointing
to the verified file; configure the NCM host address `172.16.42.1/24`, mark both
gadget links unmanaged, and verify the link and route to `172.16.42.2`. Abort if
any preboot check fails. `session-capture.py check` is **not** the preboot gate:
it requires a connected `ready.json` with a boot ID and cannot pass before SSH.

At the earliest key-only SSH acceptance after that reboot, read and retain
`/proc/sys/kernel/random/boot_id` over that same authorized connection. Start
`session-capture.py selftest <attempt-dir> --marker <unique-boot-marker> --timeout 8`
before writing that unique marker to `/dev/kmsg` over the *same boot's* SSH
session. Require `check` to report this boot ID, the selftest result to be
`ok: true` for the same ID, and the marker line to arrive after selftest starts
(`omnipha/agents/scripts/session-capture.py:211-251`). Only then, strictly
before the timer deadline, may that SSH worker create `/run/keep`. An active
preboot service, a stale line or another boot's ID is not a pass. No marker
write, SSH connection, or keep creation is performed by this host-only issue.

This does not prove that a physical gadget link can be ready preboot, or that
SSH acceptance, capture latency, or keep write will fit the 30 s residual. A
future distinct SHA may be vetted and run once only under a separate issue and
the standing approval. If its fresh capture selftest still misses 150 s, stop
and record that measured gap; do not relax the timer or plant early
`/run/keep`.
