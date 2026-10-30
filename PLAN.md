# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Milestones

1. USB shell on the stock kernel: measured.
2. WLAN across one reboot and bootloader start without a host push: measured (runs 64/65).
3. Persistent userdata root: active as #197.
4. Then one function at a time over the open SSH session. Display is next.
   No extra oversight role. This list is the check.

## Active step

- Step: #197 builds the persistent userdata root. Its init and switch_root
  execute before SSH, so this step needs one image. #199 removed the invented
  128 GiB contract maximum; the measured partition is 241421725696 bytes.
- Issue: omnipha/linux-sm7635#197
- Next: verify the pair, then measure PID 1, SSH and WLAN on that root.

## Next (ordered, not issues yet)

1. Cold start of the persistent root without USB host signals: own /run/keep,
   guard and radio start, then MINDSTORMS and SSH without a host push.
2. Display over the open SSH session: identify why /dev/dri is absent, load the
   measured stock module or firmware, and record the working recipe. Build one
   image only after that recipe is measured.
3. Touch, then audio, cameras and modem data. One function per step.

#144 (interactive PTY) and #12 (stock-kernel boot boundary) are not next.
Reopen either only when a measurement shows it blocks the active step.

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
