# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Milestones

1. USB shell on the stock kernel: measured.
2. WLAN across one reboot without a host push: current gap (#176).
3. Then one function at a time; the Omnipha slot comes after that.
   No extra oversight role. This list is the check.

## Active step

- Step: create the root-only /run/keep hold over diagnostic :22 as soon as the
  gadget and capture return after a reboot, so the proven userdata self-stage
  can repeat and WLAN autoconnect can be measured. Host-side fix; no new image.
- Issue: omnipha/linux-sm7635#176
- Done when: a coordinator-held session shows the second self-stage and WLAN
  autoconnect, or names the next first missing line; recorded as a new record.

## Next (ordered, not issues yet)

1. Persistence and cold boot once the second self-stage is observed (depends on active step).
2. Interactive PTY (`ssh -tt`) in the isolated staged guest (#144).
3. Only if a boot regression reappears: reopen the boot-boundary question
   (#12); otherwise leave closed-history alone.

## Done (pointers, newest first)

- Run 62: userdata self-stage on first boot; host re-addressing, fresh boot ID
  and diagnostic :22 return after the guest reboot -> records/ (userspace)
- Run 57: OpenRC wpa_supplicant + networking on postmarketOS PID 1 -> records/ (subsystem wlan)
- Run 56: in-session WLAN association and reachability -> records/
- Run 55: modem holds past EFS request -> records/
- Runs 52/49/48: RAM userspace PID 1, USB SSH, guest WLAN -> records/
