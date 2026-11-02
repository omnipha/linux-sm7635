---
date: 2026-11-02
run: 99
issue: omnipha/linux-sm7635#286
subsystem: wlan
result: confirmed
---
# Run 99: acked live session runs the persistent-root services stage successfully — outcome (A)

Measured on the installed never-reflash chain `init_boot_a 2ebdf1db…` +
`vendor_boot_b a71b3f5f…`, boot `345e6611-7d56-47bb-8d81-015153b15c01`,
attempt dir `~/phone-second-life-data/mb003/pstore/attempt-20261102-2010-persistent-radio-run99/`
(host-only, not in git). No flash, no erase, no cold start, no second ack,
no manual remoteproc write. Session and capture open while this was recorded.

## Session and preflight (coordinator-proven, independently rechecked)

Coordinator evidence: session open + `handoff: ok`, capture unit
`omnipha-session-capture-39def847bc2ceb57` ready, marker
`run99_handoff_1793646242_286`, exactly one pid1-ack accepted on this boot
(`ack-r99.txt`, ACK_RC=0). Worker independently rechecked over pinned key-only
root SSH `172.16.42.2:2222` (known-hosts fingerprint verified as
`SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`): boot_id match,
root-only `/run/keep` (0:600), PID 1 `init` (postmarketOS, OpenRC default,
`local` started), guard `armed`+`accepted` = this boot, `nonce`/`ack` absent,
no prior radio attempt markers, staged script sha256 `f54b3372…` exact.
Pre-cutover prepare evidence: kmsg lines 2571/2591 (self-stage then
switch_root) plus staged artifacts verified (wpss-once `fef7e5da…`, lease
helper `1fbf50af…`, INI link + `57989aba…`, rmtfs log with QRTR publish).
`prepare` was not re-run: it is a pre-cutover stage
(records/2026-11-02-154929 §"prepare is diagnostic-init-only").

## Derived variant

The composed persistent post-ack variant (record
2026-11-02-184635, sha256 `71c7b15d8c5507354268c9e0ccc49279b1e46c4e6a7fd5689bc6e21ef572202d`)
was transferred over pinned SSH to root-only
`/run/radio-bringup/pmos-radio-bringup-persistent-postack.sh` (0:700,
`sh -n` pass, hash rechecked on device before every stage). The staged
pinned script and image pins are untouched.

## Chain (fresh capture selftest marker before every stage; latencies 0.65–0.67 s)

- `modem` (first): refused `firmware_mnt path already present but not the
  read-only vfat` before `modem.attempted` — the run-98/69 empty unmounted
  `/vendor/firmware_mnt` again. Verified (dir, 0:700, not mounted, empty) and
  repaired with one `rmdir` (run-98 known repair). No other repair applied.
- `modem` (retry): PASS. rmtfs pid 670 backing links restored ("none needed"),
  remoteproc2 `running`, held past 5 s, QMI DMS connected.
- `wpss`: PASS. Helper exit 0, remoteproc3 `running`, WLAN FW ready.
- `driver`: `wlan0`/`phy0` already registered after WPSS; untouched.
- `scan`: PASS. exit 0, BSS count 26 (raw scan root-only in guest RAM).
- `services`: **PASS — the persistent variant works on device.** It did NOT
  take the "already running" early return: OpenRC `wpa_supplicant` then
  `networking` were installed and started by the stage. It accepted its own
  persisted output on the persistent root (`/etc/network/interfaces`,
  conf.d files verified as the stage's own digest — conf.d/wpa_supplicant is
  the own-output form, not the pristine hash — plus runlevel entries
  `local`/`wpa_supplicant`/`networking` only), matched the persisted
  root-only WLAN profile against stdin without overwrite, recreated both
  `/run` tmpfs helpers (`ifquery-wlan`, `lease-wrapper.sh`, own digests,
  0:700) and the busybox symlinks, then started both services (-D), each
  staying started. Same-boot retry guard engaged (`services.attempted`).

## Post-services measurements (separate read-only checks)

- Association: `iw dev wlan0 link` Connected (AP identity withheld),
  2412 MHz, −59 dBm.
- Address: non-link-local IPv4 /24 on wlan0 (udhcpc); default route via wlan0.
- Gateway ICMP on wlan0: pass. Internet IPv4 ICMP (1.1.1.1) on wlan0: pass.
- DNS (`nslookup example.com`): pass.
- Final health: remoteproc2/3 both `running`, wpa_supplicant + networking
  `started`, no radio-fatal kmsg patterns in the boot, `:2222` SSH and
  capture healthy at record time. The lease helper started its known
  unowned key-only dropbear listener on `<wlan-ip>:22` (run-66 bundle
  behavior, record 2026-11-02-180959 §":22 listener") — session teardown
  must account for it.

## Outcome (A) and the remaining gap

Per issue #286: outcome **(A)** — all stages pass including services with
its own persisted output accepted. This resolves the #284 open question:
the persistent services variant is not host-fixture-only; it works on the
installed chain in an acked session, and the /run helper recreation "gap"
does not block this path because the stage itself recreates the helpers
before `ifup`. Discriminated from outcome (B): no stage refused after the
known firmware_mnt repair.

Remaining fresh-boot self-start gap (who starts it without a host): on a
fresh boot nothing yet runs this stage before OpenRC networking — the
natural candidate remains a persistent-root self-post stage between the
guard ack and OpenRC `networking` (as #284 named). Run 97's failing
pre-radio self-post check (ordered-sequence append) still stands.

Not WLAN acceptance: one host-assisted boot; PLAN.md acceptance stays two
fresh self-starting boots without a host recipe. Session and capture remain
open for the coordinator's close.
