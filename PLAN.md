# Plan

Limit 150 lines. Ordered steps only. Results go into `records/`, never here.
One active step, one active issue. Later steps are not pre-created issues.

## Milestones

1. USB shell on the stock kernel: measured.
2. WLAN across one reboot and bootloader start without a host push: measured (runs 64/65).
3. Persistent userdata root: measured through guest reboot; cold start remains.
4. Then one function at a time over the open SSH session. Display is next.
   No extra oversight role. This list is the check.

## Active step

- Step: record the installed-chain boundary before the button-assisted cold start.
- Issue: omnipha/linux-sm7635#223
- Next: the installed run-69 chain is the identity-preserving start, but it
  cannot produce guest keep, safe guard re-arm, and no-host radio. No image
  was built. The coordinator alone owns the one scheduled cold start.

## Next (ordered, not issues yet)

1. Resolve the recorded run-69 pre-SSH gap before claiming a host-free cold
   start: guest keep, safe guard re-arm, then radio without host ack/capture.
   The coordinator owns the one scheduled button-assisted measurement.
2. Display over the open SSH session: identify why /dev/dri is absent, load the
   measured stock module or firmware, and record the working recipe. Build one
   image only after that recipe is measured.
3. Touch, then audio, cameras and modem data. One function per step.

#144 (interactive PTY) and #12 (stock-kernel boot boundary) are not next.
Reopen either only when a measurement shows it blocks the active step.

## Done (pointers, newest first)

- Host #223: unchanged installed chain refuted for the full no-host cold-start sequence; no image built -> records/2026-10-31-044608-coldstart-installed-chain-host-boundary.md
- Run 73: host-free guard rearm, postmarketOS PID 1, 160-s deadline return and exact rollback -> records/2026-10-31-040929-guard-rearm-run73.md
- Host #220: persistent-root guard rearm image built and verified -> records/2026-10-31-034455-guard-rearm-host-image.md
- Run 72: guest keep and persistent root reached; PID 1 refused on NO_ARMED, rollback verified -> records/2026-10-31-024827-run-72-guest-keep-partial-guard-unarmed.md
- Host #216: guest-owned keep init_boot built and verified; carrier unchanged -> records/2026-10-31-015710-guest-owned-keep-host-image.md
- Run 71: device-native RTC alarm accepted but no power-off or cold start; result (d) -> records/2026-10-30-222652-run-71-device-native-rtc-poweroff-coldstart.md
- Run 70: no host-free cold-start power path; result (d), no boot or partition write -> records/2026-10-30-212551-run-70-coldstart-host-free-power-boundary.md

- Run 69: bootloader start returned diagnostic Linux and exact slot-A rescue hashes -> records/2026-10-30-204752-run-69-bootloader-start-rescue.md
- Run 69: guest reboot reached accepted guard, persistent PID 1 and WLAN -> records/2026-10-30-203515-run-69-second-boot-guard-wlan.md
- Run 69: persistent ext4 root, postmarketOS PID 1 and first-boot WLAN measured -> records/2026-10-30-195754-run-69-persistent-root-first-boot.md
- Host #204: existing vendor_boot_b carrier pair replayed without rebuild -> records/2026-10-30-191204-root-contract-carrier-replay.md
- Host #204: pinned raw contract exceeds the fixed init_boot envelope by 597 bytes -> records/2026-10-30-184802-init-boot-root-contract-envelope-overflow.md
- Host #204: rejected carrier attempt moved the bundle to vendor_boot_b -> records/2026-10-30-183749-root-contract-vendor-boot-carrier.md
- Run 67: persistent-root boot reached diagnostic SSH but not self-stage -> records/2026-10-30-170925-run-67-persistent-root-self-stage-absent.md
- Host #197: deterministic persistent ext4 root and distinct direct-root init_boot verified -> records/2026-10-30-162851-persistent-userdata-root-pair.md
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
