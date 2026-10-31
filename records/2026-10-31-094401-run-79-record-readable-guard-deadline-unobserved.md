---
date: 2026-10-31
run: 79
issue: omnipha/linux-sm7635#230
subsystem: boot
result: inconclusive
---
# Run 79: record readable, post-cutover milestones unmeasured

Independent closeout from `sprintberlin/phone-second-life` commit `8c80edd30f8fc5e3d6c3b73ba877afe9a220454d` and its preserved raw evidence. No USB, SSH, flash, reboot, or partition operation was performed here. Record readability is confirmed. The post-cutover milestones and designed deadline return were not observed, so the overall result is inconclusive.

The coordinator's verifier ran from merged `main` `db8747c` and passed for exactly `init_boot-coldstart-record.img` `a4ee7def41e645301f59bdc4dc043c97253a4002d8774016ee3557633b0cb6e3` and `vendor_boot_b-coldstart-record.img` `6e7c5a2e26981fc19c9eba97356d1a52f80e768cb6b9536bc9cb4fd906a8c59e`, refusing 76 hashes including run-78 `3192278b` / `ab3a0e63`. Device-op flash hooks verified writes to `init_boot_a` and `vendor_boot_b` only. There was no userdata write, Android start, stock restore, or cold start. Before the write, diagnostic boot `a50373dd` read exact stock slot-A rescue hashes and the previously installed `init_boot_a 3192278b` / `vendor_boot_b ab3a0e63`.

On diagnostic boot `28e8fa92-0694-4a54-b2b2-64090f0ac9b1`, key-only SSH reached both `:22` and `:2222` with pinned host key `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`. Before cutover, `/run/pmos/.omnipha-boot-record` was a regular root-only 933-byte file (`0:600`) on pinned ext4 `/dev/block/sda13`. It contained the boot ID and the first nine ordered stage lines through the PID 1 request. After the refused cutover, `:2222` read the complete record, now 11 lines: the boot ID plus all ten stage lines, ending in `usb-init: pid1 transition guard armed; exec switch_root to postmarketOS init`.

The first missing post-cutover milestone is at kernel time 156.358425 seconds: `pmos-self-post: FAIL: independent recovery guard is not armed and unacknowledged`. PID 1 remained `/bin/busybox sh /init`; postmarketOS PID 1, radio, and WLAN were therefore not reached. The designed independent 160-second no-ack return was also not observed. USB Linux was still alive at 274.18 seconds uptime, and the coordinator ended the boot manually with `restart2 bootloader` at 2026-10-31T10:37:08+01:00.

Rescue proof comes from the same diagnostic boot, not a cold start. Temporary busybox block nodes read exact stock `boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`, `vbmeta_a cc1926d2…cdffe`, installed `init_boot_a a4ee7def…0cb6e3`, and installed `vendor_boot_b 6e7c5a2e…a8c59e`. An earlier `/dev` node attempt reset its SSH connection and is not hash evidence. The final gate was serial `00181152O003821`, slot `a`, unlocked, product `pineapple`, and fastboot `18d1:d00d`. No rollback was needed. The measured pair is now never-reflash. The coordinator session is closed.
