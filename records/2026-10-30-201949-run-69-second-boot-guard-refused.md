---
date: 2026-10-30
run: 69
issue: omnipha/linux-sm7635#204
subsystem: boot
result: refuted
---
# Run 69: second boot keeps the persistent root, but the independent guard refuses PID 1

**Measured physical result of one clean guest reboot.** The installed set was not rewritten: `init_boot_a 2f73c947`, `vendor_boot_b f792174c`, and existing persistent `userdata aa8da109` stayed in place. First boot `238a6bc2` had already reached postmarketOS PID 1 and external WLAN reachability. After a concurrent capture selftest, one `busybox reboot -f` was issued over pinned `:2222`; the SSH call returned exit 124 when the session dropped.

| stage | measured result |
| --- | --- |
| USB return and capture | gadget `18d1:4ee2` returned; capture reconnected at `2026-10-30T21:13:49+01:00` on fresh boot `b5171324-06eb-46b9-b538-c518765510d1` |
| diagnostic hold | root-only `/run/keep` (`0:600`) created over pinned `:22` at 95 s uptime, inside the 145 s window; no host archive push |
| unchanged root | self-stage mounted read-only `/dev/block/sda13`, verified its root contract, and the live root was `/dev/block/sda13` ext4 |
| first missing line | `usb-init: pid1 transition refused: independent recovery guard not armed`; diagnostic SSH stayed up and PID 1 remained `/bin/busybox sh /init` |
| WLAN on second boot | not reached: `wlan0` absent, OpenRC `wpa_supplicant`, `networking` and `local` stopped, no guard acceptance |

The armed host helper exited silently when the old capture link dropped (`ssh-exit`, exit 255). A direct retry of the same hold helper set `/run/keep`; no second reboot was issued. A fresh console marker and `device-op.py handoff` passed for boot `b5171324` on pinned `:2222`. The bootloader start is not in scope because this guest reboot did not return healthy PID 1 and WLAN. No stock restore, userdata erase, Android boot, or additional partition write occurred. Raw evidence stays outside Git at `~/phone-second-life-data/mb003/pstore/attempt-20261030-2037-vendor-carrier-run69/`.
