# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Milestones

1. USB shell on the stock kernel: measured.
2. WLAN across one reboot without a host push: second self-stage + PID 1 measured (run 64); autoconnect still open pending a visible target (#184).
3. Then one function at a time; the Omnipha slot comes after that.
   No extra oversight role. This list is the check.

## Active step

- Step: measured (run 64) — `pmos-reboot-hold.sh` created root-only `/run/keep`
  over diagnostic `:22` inside 145 s after a clean guest reboot, so the second
  `userdata` self-stage, postmarketOS PID-1 cutover, modem/WPSS/wlan0 and scan
  all repeat without a host push; autoconnect stops at association with the
  designated network absent from both guest and host radios.
- Issue: omnipha/linux-sm7635#184
- Done when: coordinator session close with untouched slot-A rescue baseline
  proof is recorded; WLAN autoconnect is the named first missing line for the
  next run once the designated network is visible.

## Next (ordered, not issues yet)

1. Persistence and cold boot once the second self-stage is observed (depends on active step).
2. Interactive PTY (`ssh -tt`) in the isolated staged guest (#144).
3. Only if a boot regression reappears: reopen the boot-boundary question
   (#12); otherwise leave closed-history alone.

## Done (pointers, newest first)

- Run 64: host reboot-hold over :22 confirmed; second userdata self-stage and postmarketOS PID 1 measured (boot/wlan)
- Run 62: userdata self-stage on first boot; host re-addressing, fresh boot ID
  and diagnostic :22 return after the guest reboot -> records/ (userspace)
- Run 57: OpenRC wpa_supplicant + networking on postmarketOS PID 1 -> records/ (subsystem wlan)
- Run 56: in-session WLAN association and reachability -> records/
- Run 55: modem holds past EFS request -> records/
- Runs 52/49/48: RAM userspace PID 1, USB SSH, guest WLAN -> records/
