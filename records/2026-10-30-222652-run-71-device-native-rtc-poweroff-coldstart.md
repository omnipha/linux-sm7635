---
date: 2026-10-30
run: 71
issue: omnipha/linux-sm7635#214
subsystem: boot
result: refuted
---
# Run 71: device-native RTC alarm does not power off the phone

**Contrasting result (d): operator-independence boundary.** The unchanged installed run-69 chain exposes a PMIC RTC and accepts one normal power-off command, but that path does not power the phone off or produce a cold start. This is not an Omnipha release and does not establish a host-free power path.

Measured on diagnostic boot `e325c408-9adc-4a33-8a6c-92bf5c51efb2`, 2026-10-30 22:09Z–22:17Z:

- Pinned key-only SSH, root-only `/run/keep` (`0:600`) and live capture were proven before the command. `rtc0` is `rtc-pm8xxx` on `pmk8550` and exposes a writable `wakealarm`.
- Exactly one `+180` second alarm was accepted: `alarm_IRQ: yes`, alarm time `18:08:51`, recorded at uptime `358.74`. Exactly one BusyBox `poweroff` returned `rc=0` and explicitly remained powered. No second alarm, forced power-off, warm reboot, image change, or partition write was used.
- The host stayed passive through the alarm budget. The same boot was still alive at uptime `568.79` and again at `610.06`, with PID 1 unchanged, USB and SSH present, and `alarm_IRQ: no`. Pstore was empty (`total 0`), so there was no cold start and no cold-start stop line.
- Slot-A rescue hashes were exact on the same boot: `boot_a 197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`, and `vbmeta_a cc1926d2`. Installed `init_boot_a 2f73c947` and `vendor_boot_b f792174c` were also exact. Capture stopped with `kmsg` SHA-256 `06302eb4…ff08c`; the final fastboot gate was slot A, unlocked, pineapple, userspace no.

Public record: sprintberlin/phone-second-life `48b0c84`. Raw evidence: `~/phone-second-life-data/mb003/pstore/attempt-20261030-2300-device-native-rtc-run71/`.

Next gate: #213 remains the owner fallback. Do not repeat this alarm or substitute another power mechanism for the absent cold start.