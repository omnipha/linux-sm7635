# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Milestones

1. USB shell on the stock kernel: measured.
2. WLAN across one reboot and bootloader start without a host push: measured (runs 64/65).
3. Then one function at a time; the Omnipha slot comes after that.
   No extra oversight role. This list is the check.

## Active step

- Step: measured (run 65) — bootloader start of the installed run-64 chain
  reached read-only `userdata` self-stage, postmarketOS PID 1, guard ack,
  modem/WPSS/wlan0/scan and OpenRC WLAN association, DHCP, gateway, DNS and
  external reachability with no host archive push and no partition write.
- Issue: omnipha/linux-sm7635#191
- Done: coordinator session close landed with untouched slot-A rescue baseline
  proof recorded in the run-65 close record; phone left in fastboot. Mission
  successor selection is separate.

## Next (ordered, not issues yet)

1. Persistence and cold boot design (#183).
2. Interactive PTY (`ssh -tt`) in the isolated staged guest (#144).
3. Only if a boot regression reappears: reopen the boot-boundary question
   (#12); otherwise leave closed-history alone.

## Done (pointers, newest first)

- Run 65: bootloader-start self-stage, postmarketOS PID 1 and OpenRC WLAN reachability measured with no write -> records/ (boot/wlan)
- Run 64: host reboot-hold over :22 confirmed; second userdata self-stage and postmarketOS PID 1 measured (boot/wlan)
- Run 62: userdata self-stage on first boot; host re-addressing, fresh boot ID
  and diagnostic :22 return after the guest reboot -> records/ (userspace)
- Run 57: OpenRC wpa_supplicant + networking on postmarketOS PID 1 -> records/ (subsystem wlan)
- Run 56: in-session WLAN association and reachability -> records/
- Run 55: modem holds past EFS request -> records/
- Runs 52/49/48: RAM userspace PID 1, USB SSH, guest WLAN -> records/
