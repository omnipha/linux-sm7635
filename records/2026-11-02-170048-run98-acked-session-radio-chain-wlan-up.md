---
date: 2026-11-02
run: 98
issue: omnipha/linux-sm7635#280
subsystem: wlan
result: confirmed
---
# Run 98: acked live session brings the full radio chain up and reaches the internet; the pinned script refuses as derived, the post-ack variant runs

Measured on the installed never-reflash chain `init_boot_a 2ebdf1db…` +
`vendor_boot_b a71b3f5f…`, boot `04685e77-936d-4fc5-a9fa-20ce3969c570`,
attempt dir `~/phone-second-life-data/mb003/pstore/attempt-20261102-1720-acked-radio-run98/`
(host-only, not in git). No flash, no erase, no cold start, no second ack,
no manual remoteproc write. Session, capture and the WLAN link stayed open
while this was recorded.

## Session (coordinator-proven, independently rechecked by the worker)

Coordinator evidence records `device-op session open` and `handoff` PASS,
marker `run98_handoff_1793636082_280`, and exactly one pid1-ack accepted on
this boot. The worker independently rechecked the same-boot key-only root
SSH `172.16.42.2:2222`, root-only `/run/keep`, PID 1, capture unit
`omnipha-session-capture-4a9909fabff39e08`, and accepted guard. Before the
pinned probe and the successful modem retry, `armed` and `accepted` both
matched the boot ID and `nonce`/`ack` were absent. The other derived stages
rechecked the boot ID and `accepted`; the derived script also checks `armed`
and no `ack`. No prior radio attempt markers existed on this boot.

## Step 1: pinned probe — refusal as derived (issue outcome basis)

`sh /run/radio-bringup/pmos-radio-bringup.sh <boot> modem` (staged copy,
sha256 `f54b3372…`, rechecked in the same SSH command) refused, exit 1:

```
radio-bringup: FAIL modem: PID 1 guard is not armed and unacknowledged on this boot
```

No `modem.attempted` was created; the refusal precedes the capture gate and
every remoteproc write. This confirms the host derivation of
`records/2026-11-02-154929-host-radio-live-session-handoff.md` on the device:
the pinned script cannot start the radio from an acked session.

## Step 2: post-ack variant (PR #282, independently reviewed then measured)

Owner decision 2026-11-02 (issue #280) authorized the derived post-ack
variant. Independent review found it changes exactly the guard check
(armed+accepted+no ack) and the capture gate (fresh marker in this boot
kmsg), preserving all stage-local bounds, one-shot guards, rmtfs/firmware
checks; every stage below was preceded by a host capture selftest
(`session-capture.py selftest`, latency ≈1.1 s) with a fresh per-stage
marker. Derived from the staged copy (sha256 `f54b3372…`) with
`derive-radio-postack.py`; derived sha256 `34a67bb4…`, rechecked on device
before every stage.

- No-marker control: `modem` without a marker refused at the capture gate;
  no attempt marker, remoteproc still offline.
- `modem` (first try): rmtfs backing links restored, then refused at
  `firmware_mnt path already present but not the read-only vfat` — before
  `modem.attempted`. Cause: a persistent, unmounted, EMPTY
  `/vendor/firmware_mnt` directory (run-69 known repair condition,
  verified: directory, 0:700, not in /proc/mounts, empty) was removed with
  `rmdir`. No other repair applied.
- `modem` (after the repair): PASS. remoteproc2 start, `running`, held past
  5 s with `icnss2_qmi: QMI DMS service connected`.
- `wpss`: PASS. Helper exit 0, remoteproc3 `running`, `icnss2: WLAN FW is
  ready`.
- `driver`: `wlan0` and `phy0` already registered after WPSS (driver stage
  untouched, early return).
- `scan`: bounded `iw dev wlan0 scan` exit 0, BSS count 33 (raw scan
  root-only in guest RAM).

## Step 3: services — script refusal, then working RAM-only start

The `services` stage refused at the pristine-archive conf.d hash check
(`unexpected supplicant arguments; no -f supported`): the persistent
`/etc/conf.d/wpa_supplicant` is the script's own earlier output
(`wpa_supplicant_if="wlan0"`), and the runlevel/no-overwrite checks would
also refuse on a configured persistent root. Nothing was deleted or
overwritten. The two transient `/run` helpers (`lease-wrapper.sh`,
`ifquery-wlan`) were reconstructed byte-identically from the staged script's
own `install_service_config`, then the script's exact start sequence ran
(`rc-service -D wpa_supplicant start`, stay-started check). All script
preconditions (service/init.d/lease hashes, runlevel inventory, no fatal
kmsg, :2222 health, OpenRC prerequisites) were verified first. The staged
lease helper `1fbf50af…` was read: pure udhcpc lease handler whose only
extra action is a key-only dropbear on the WLAN address (observed listening
on `<wlan-ip>:22`).

- `wpa_supplicant`: started and stayed started.
- Association (separate check): `iw dev wlan0 link` `Connected to <AP>`,
  2432 MHz, −59 dBm.
- `networking` (separate fresh capture marker, same guarded preconditions):
  `rc-service -D networking start` exit 0, stayed started.
- Address: `inet <addr>/24` on wlan0 via udhcpc (`192.168.178.0/24`).
- Route: `default via <gw> dev wlan0`.
- Gateway ICMP on wlan0 (`ping -I wlan0 -c 2`, exit 0): pass.
- Internet IPv4 ICMP on wlan0 (`1.1.1.1`, same command, exit 0): pass.
- DNS (`nslookup example.com`): pass.

## Evidence and deviations

The capture `kmsg.log` (not in git) contains every per-stage marker
(`run98_{modem,modem_retry,wpss,driver,scan,services,services_manual,network}`),
`radio-bringup: guarded remoteproc2 start`, and `icnss2: WLAN FW is ready`.
The worker's own stage harness, SSH wrapper and the reconstructed services
snippet live in `/tmp/opencode` on the host (not in git). Deviations from the
pinned scripts, all stated above: (1) the post-ack derived script instead of
the pinned copy (owner decision, PR #282); (2) one `rmdir` of the empty
unmounted persistent `/vendor/firmware_mnt`; (3) the services stage was not
used because it refuses its own persisted output; its two RAM helpers and
start commands were replayed by hand with the script's exact bytes. The
`networking` service's lease helper also starts a key-only dropbear on the
WLAN address (`:22`), so the phone now has an additional SSH listener on the
LAN while it stays up.

## Integrity and boundaries

Both remoteprocs still `running`, services started, link up at record time.
No radio-fatal kmsg patterns in the whole boot. Not WLAN acceptance: one
boot only, host-run recipe (the acceptance per PLAN.md stays two fresh
self-starting boots without a host recipe). The guard stays acked; the
session and capture remain open for the coordinator's close.

Next single variable for the strategist: carry this measured live recipe to
the self-starting chain — the failing pre-radio check for self-post remains
the ordered-sequence append (run 97), and the services stage needs a
persistent-root-aware variant instead of the pristine-archive hash checks.
