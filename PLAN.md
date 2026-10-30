# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Milestones

1. USB shell on the stock kernel: measured.
2. WLAN across one reboot and bootloader start without a host push: measured (runs 64/65).
3. Then one function at a time; the Omnipha slot comes after that.
   No extra oversight role. This list is the check.

## Active step

- Step: #197 host image phase unblocked by #199: fail-closed contract accepts
  the measured 241421725696-byte userdata partition and still rejects larger
  blocks. No image, marker or partition write in #199.
- Issue: omnipha/linux-sm7635#197
- Next: build and verify the persistent-root pair under the corrected contract
  before its existing physical gates.

## Next (ordered, not issues yet)

1. Persistence and cold boot design (#183).
2. Interactive PTY (`ssh -tt`) in the isolated staged guest (#144).
3. Only if a boot regression reappears: reopen the boot-boundary question
   (#12); otherwise leave closed-history alone.

## Done (pointers, newest first)

- Host-only #199: measured-size fail-closed root-contract maximum and fixtures -> records/2026-10-30-150709-root-contract-measured-userdata-maximum.md
- Host #197: persistent direct-root pair refused by the closed #194 size gate -> records/ (userspace)
- Host-only #194: pinned ext4 userdata root or measured 256m tmpfs accepted across stage, teardown, transition, guard, ack, self-post, radio and self-stage fixtures -> records/ (userspace)
- Host-only #194: pinned ext4 userdata root accepted in loop fixture; full contract blocked by foreign paths -> records/ (userspace)
- Run 65: bootloader-start self-stage, postmarketOS PID 1 and OpenRC WLAN reachability measured with no write -> records/ (boot/wlan)
- Run 64: host reboot-hold over :22 confirmed; second userdata self-stage and postmarketOS PID 1 measured (boot/wlan)
- Run 62: userdata self-stage on first boot; host re-addressing, fresh boot ID
  and diagnostic :22 return after the guest reboot -> records/ (userspace)
- Run 57: OpenRC wpa_supplicant + networking on postmarketOS PID 1 -> records/ (subsystem wlan)
- Run 56: in-session WLAN association and reachability -> records/
- Run 55: modem holds past EFS request -> records/
- Runs 52/49/48: RAM userspace PID 1, USB SSH, guest WLAN -> records/
