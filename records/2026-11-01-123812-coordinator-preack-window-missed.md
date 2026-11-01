---
date: 2026-11-01
run: 91
issue: omnipha/linux-sm7635#256
subsystem: wlan run 91
result: inconclusive
---
# coordinator preack window missed

Run 91 (#256 live window): the one no-flash boot of the installed run-87 pair
(`init_boot_a f9449ba5` / `vendor_boot_b a71b3f5f`, gate serial 00181152O003821
slot a unlocked pineapple, host manifests 31/31 OK) reached key-only SSH on
:22 (12:28:01Z) and the staged root on :2222 (12:28:58Z) on boot
`d32f0ea4-1d68-45f0-af67-6f85851a30a1`; `/run/keep` root-only, no pid1-ack
was ever issued by the host. The chain self-cutover happened at 12:30:24Z
(kmsg seq 1617/1618, 156 s uptime), `pmos-self-post` then failed with
`independent recovery guard is not armed and unacknowledged` (designed), and
the phone self-returned to fastboot at ~12:33:45Z.

The worker did NOT get the session: the handoff proof was not completed
before the guard deadline. Measured causes (both coordinator-side, not
chain regressions):

1. The port-22 capture target dies at the chain's self-cutover: after
   switch_root the :22 dropbear resets connections, so a capture that only
   lives on :22 loses the console before the marker write. The :2222 staged
   root stays reachable until the guard return.
2. The :2222 capture was only started at 12:32:53Z (SSH needs a port flag;
   the capture target takes `user@host` only, a `-p 2222` wrapper was used).
   The remaining window was shorter than the selftest deadline.

Measured timing budget for the next window on this chain: :2222 answers
~70-110 s after reboot; self-cutover follows at ~156 s uptime; guard return
~160 s after arming. The usable pre-ack worker window from :2222-up to
self-cutover is only ~45-85 s, so the :2222 capture must be pre-armed BEFORE
`fastboot reboot` (its reconnect loop tolerates the device being down) and
the marker+handoff proof must run the moment :2222 answers.

No worker probe ran: `/proc/1/mountinfo` was not captured and the pinned
`pmos-self-post.sh` was not re-invoked. The #256 divergence question
(second sda13/8:118 mount in PID 1 mountinfo) stays open; host fixture
(records/2026-11-01-120601-host-run90-switched-root-fixture-passes.md)
remains the latest measured state.

No flash, no erase, no Android boot, no cold start; no partition written.
Slot-A rescue verified at close (stock boot_a/vendor_boot_a/dtbo_a/vbmeta_a
provenance-identical, installed carriers unchanged), final fastboot gate
serial 00181152O003821 slot a unlocked pineapple userspace no. Linux stays
installed. Raw capture: phone-second-life-data mb003
attempt-20261101-1330-preack-probe-run91 (kmsg.log 330379 bytes, sha256
64cb864adff1068c792d404ba335daaacf64f1ee80b39ebdfd3110610c01b7d1, no fatal).
