---
date: 2026-11-01
run: 89
issue: 253
subsystem: wlan
result: inconclusive
---
# coordinator handoff window too short

Coordinator run 89 booted the installed never-reflash run-87 pair (`init_boot_a
f9449ba5` / `vendor_boot_b a71b3f5f`) once from fastboot with no flash, established
key-only SSH on :22 and on the staged postmarketOS root :2222 (pinned host key
`SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`, fresh keyscan exact), withheld the
host pid1-ack, started host-side capture and proved the handoff (fresh marker
`run89_handoff_1793528040_253e`, ~1 s line latency). `pmos-self-post.sh` reached its
known pre-ack stop at 156.5 s: "independent recovery guard is not armed and
unacknowledged" — the expected boundary, not a radio measurement.

Before the worker session could act on the handed-over boot, the unacknowledged chain
self-returned to fastboot (USB `18d1:4ee2` until 11:15:05 MEZ, `18d1:d00d` from
11:15:16 MEZ). No radio stage ran, so the pinned-chain-before-ack question of #253 is
still open; result stays inconclusive. The measured handoff window between coordinator
proof and the self-return was too short for a worker tick — a coordinator handoff must
pair the boot with an immediately acting worker, or the pre-ack window must be extended
by the chain design before the experiment can run.

Evidence: capture kmsg 165698 bytes, SHA-256
`de7109de61b0770031fdbb6dc99ce5aaa16a1d12ce0af5944366eafbd3520c22`, no kernel fatal;
last lines show the designed shutdown sequence. No partition was written this run
(getvar, one `fastboot reboot`, SSH reads, `/dev/kmsg` markers only); slot-A stock
rescue and installed carriers are identical to the run-88 verified on-device read of
the same installed set. Issue comments 6556590181 and 6556631694; device record
`phone-second-life` a78373a.
