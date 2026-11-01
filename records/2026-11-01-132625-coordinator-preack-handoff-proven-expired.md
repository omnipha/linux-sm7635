---
date: 2026-11-01
run: 92
issue: omnipha/linux-sm7635#256
subsystem: wlan run 92
result: inconclusive
---
# coordinator preack handoff proven, expired before worker return

Run 92 (#256 pre-ack probe) implemented the measured run-91 budget: the
:2222 capture was pre-armed BEFORE `fastboot reboot` (reconnect loop,
pinned host key, port wrapper) and connected 24 s after the reboot with
proven boot id `6d719708-374b-4850-94cd-9ff1b44b3a0e`. Key-only SSH on
:2222, root-only `/run/keep`, no pid1-ack was ever issued (per #256).
`device-op.py session open` ok and `device-op.py handoff` ok with fresh
capture marker `run92_handoff_1793538470_256` at 13:07:53Z — the handoff
itself was proven, which closes the run-91 coordinator-side selftest gap.

The retained worker `ses_e690aff06ffe0H1l55Q74U0nAY` was never dispatched:
the unacknowledged-guard deadline (~13:10Z) passed with no worker dispatch
and no pid1-ack. The chain ended the boot by itself (designed boundary, no
chain regression): kmsg stopped at 13:12:57Z inside the designed SCSI
shutdown sequence, no kernel fatal; the pre-armed capture then logged
repeated SSH exit 255 / link closed from 13:14:08Z until stopped.

No worker probe ran: `/proc/1/mountinfo` was not captured and the pinned
`pmos-self-post.sh` was not re-invoked. The #256 divergence question stays
open exactly as in run 91; the next coordinator-owned window must deliver
the worker INTO the proven window, not just prove the handoff.

No flash, no erase, no Android boot, no cold start; no partition written.
Only fastboot getvar queries, one `fastboot reboot`, SSH reads and
`/dev/kmsg` marker writes. Slot-A rescue and installed run-87 carriers
(`init_boot_a f9449ba5` / `vendor_boot_b a71b3f5f`) bit-identical to the
run-88 verified on-device read; `rescue-verify-close.sh` RESCUE_VERIFIED;
final fastboot gate serial 00181152O003821 slot a unlocked pineapple
userspace no. Linux stays installed. Raw capture: phone-second-life-data
mb003 attempt-20261101-1450-preack-probe-run92 (kmsg.log 164842 bytes,
sha256 e74e2f00f68ca49df5f5f6bc1d3202584c7e4f1aefaefc341ee3315f3f8c5e78,
no fatal).
