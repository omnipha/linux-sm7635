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

- Step: deliver #234's post-cutover record host image and await the coordinator's measured outcome.
- Issue: omnipha/linux-sm7635#234 until the measured closeout PR merges, then none.
- Next: the host pair dd6ce74e / e7d55580 is verified and never-reflash for
  every earlier measured image. The coordinator owns the one diagnostic boot,
  the acknowledged PID 1, and the independent no-ack return. Do not reflash a
  measured pair or schedule a cold start.

## Next (ordered, not issues yet)

1. Strategist selects how to reach an acknowledged recovery guard and observe
   the 160-second fastboot return. Do not treat run 79 as a functional boot.
2. Display, touch, audio, cameras and modem data follow only when their own
   gates are reached. One function per step.

#144 (interactive PTY) and #12 (stock-kernel boot boundary) are not next.
Reopen either only when a measurement shows it blocks the active step.

## Done (pointers, newest first)

- Host #234: bounded post-cutover record, FAIL line and distinct pair dd6ce74e / e7d55580 verified; run-79 and earlier images refused; no re-entered arm tail -> records/2026-10-31-110810-cutover-record-host-image.md
- Run 79: persistent boot record readable through the transition line; self-post refused and 160-second return unobserved; rescue verified -> records/2026-10-31-094401-run-79-record-readable-guard-deadline-unobserved.md
- Host #230: bounded pre-switch_root boot record and distinct pair a4ee7def / 6e7c5a2e verified; run-78 and earlier images refused -> records/2026-10-31-090700-coldstart-boot-record-host-image.md
- Run 78: button-assisted cold start performed but original console and PID 1/radio/WLAN result unmeasured; rescue verified -> records/2026-10-31-075408-run-78-coldstart-observation-incomplete.md
- Host #223: run-66 handoff pinned byte-for-byte and distinct pair 3192278b / ab3a0e63 re-verified on merged main -> records/2026-10-31-061706-coldstart-run66-handoff-verified.md
- Run 76: host verifier refused becd3784 / adb47dc0 before flash; unchanged rescue chain read and fastboot return measured -> records/2026-10-31-055910-preflash-verifier-refusal.md

- Host #223: distinct no-host radio package and unchanged 160-s recovery verified -> records/2026-10-31-054706-coldstart-host-free-radio-package.md
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
