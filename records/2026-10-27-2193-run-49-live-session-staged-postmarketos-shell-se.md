---
date: 2026-10-27
run: 49
issue: omnipha/linux-sm7635#139
subsystem: wlan
result: confirmed
source: README.md
---
## Run-49 live-session staged postmarketOS shell/service + WLAN connectivity finding (2026-10-27, #139)

[BOOT.md](BOOT.md#run-49-measured-staged-postmarketos-shell-service-and-wlan-connectivity-139-live-session-finding-2026-10-27)
records a measured physical result in the coordinator-held run-49 session: after
the on-device-tested staging fix (chroot-local `devpts` replacing the failed nested
`dev/pts` bind), the pinned 23.7 MiB postmarketOS/Alpine userspace staged into
guest RAM, and a host-reached key-only shell confirmed UID 0 inside
`/run/pmos`, postmarketOS v24.12 / Alpine 3.21.9 identity and the same running
stock 6.1.84 kernel — the real staged shell/service milestone, distinct from a
chroot smoke test. From that runtime, in the same held session, the full
WLAN chain was measured separately: guarded modem start (rc 0, running past
+60 s, DMS connected), one `/bin/wpss-once` (rc 0, WPSS running, FW ready),
`wlan0` link-up, a 20 s-bounded `iw` scan (25 BSS, no identifier published), a
private target match (9 BSS), `wpa_supplicant` association (`COMPLETED` **and**
a connected `iw link`), bounded `udhcpc` DHCP (rc 0, one IPv4, default route,
two nameservers), and gateway/DNS/external reachability each rc 0 (3/3, 3/3,
confirmed twice). Continuous capture stayed live with no new fatal/crash/idle
callback; the supplicant was terminated and all private guest RAM scrubbed
before ending worker activity, while the staged runtime and `:2222` were left
alive for the coordinator. Interactive PTY (`ssh -tt`) is **not** proven: the
shared bind-mounted diagnostic `/dev` lacks `/dev/tty`, and creating one leaked
into the outer namespace, so it was reverted and PTY left as a successor task —
non-PTY key-only command shells are the measured service surface. This proves
an ephemeral RAM-only distribution userspace and WLAN connectivity on the
measured stock kernel, **not** persistence, autoconnect after reboot, or a
release image. At the time of that measured finding, the coordinator still
owned the pending stock `init_boot_a` restore, five-hash proof, pstore
preservation and stock Android verification; #139 has since closed after
verified five-partition stock rollback.
