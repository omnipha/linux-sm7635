# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Active step

- Step: prove the host-owned guard ack is delivered and accepted after the
  self-stage PID-1 handoff (run 61 timed out waiting for it).
- Issue: omnipha/linux-sm7635#173
- Done when: a coordinator-held session shows `pid1-ack: accepted on boot
  <BOOT_ID>` and `pmos-self-post: host-owned guard ack accepted` in capture,
  recorded as a new record.

## Next (ordered, not issues yet)

1. Self-stage repeats across one clean guest reboot on the `recovery_b`
   carrier (depends on active step; relates to closed host prep #171).
2. Host re-addresses the re-enumerated USB gadget within the 150 s guard
   window so SSH returns after reboot (host rule from #169).
3. Interactive PTY (`ssh -tt`) in the isolated staged guest (#144).
4. Only if a boot regression reappears: reopen the boot-boundary question
   (#12); otherwise leave closed-history alone.

## Done (pointers, newest first)

- Run 57: OpenRC wpa_supplicant + networking on postmarketOS PID 1 -> records/ (subsystem wlan)
- Run 56: in-session WLAN association and reachability -> records/
- Run 55: modem holds past EFS request -> records/
- Runs 52/49/48: RAM userspace PID 1, USB SSH, guest WLAN -> records/
