---
date: 2026-10-30
run: 64
issue: omnipha/linux-sm7635#184
subsystem: boot
result: confirmed
---
## Run 64: host reboot-hold sets `/run/keep` on `:22` inside 145 s and repeats `userdata` self-stage + postmarketOS PID 1 (#184)

**Measured physical result across two boots on the reused run-62 pair (`init_boot_a` `fcb0ed91…`, `userdata` `ea09444c…`).** Under the 2026-10-30 owner reuse decision, the coordinator flashed only `init_boot_a` and `userdata`, kept the slot-A rescue partitions, `super` and slot B untouched, and opened one held session. The host reboot-hold question is **confirmed**: setting root-only `/run/keep` over pinned diagnostic `:22` via `scripts/pmos-reboot-hold.sh` inside the unchanged 145 s window allowed the second boot to repeat the read-only `userdata` (`sda13`) self-stage, switch to postmarketOS PID 1, accept the host-owned guard ack, and reach `remoteproc2`, `remoteproc3`, `wlan0` and scan without any host archive push. The first missing line on the second boot is **WLAN association** (`wpa_state=SCANNING`, `iw dev wlan0 link` not connected), with the designated network absent from both fresh guest scans and fresh host-radio scans during the measurement window.

### First boot (`2fd4a99a-842b-495e-bf62-f32ad49a6b10`)

| stage | measured result |
| --- | --- |
| hold and self-stage | `/run/keep` mode `0:600`; kmsg at 14.83 s verified diagnostic hold and `:22`, mounted `sda13` read-only without journal, unmounted it, and verified the archive SHA-256 at 15.17 s |
| PID 1 and guard ack | `switch_root` to postmarketOS init at 155.31 s; post-cutover PID 1 waiting line at 155.47 s; host-owned guard ack accepted at 170.49 s; `device-op.py handoff` proven with marker `run64_handoff3_1793343451_858881` |
| modem / WPSS / driver / scan | each preceded by a fresh capture selftest (`ok: true`, ~0.11 s latency); `remoteproc2` and `remoteproc3` reached `running`, `WLAN FW is ready`, `wlan0` present, scan completed (33–38 BSS) |
| services | `pmos-self-post: FAIL: radio bring-up services failed` at 360.54 s while the radio scanned 35–38 BSS without association |

### Clean guest reboot and second boot (`03ebed06-0682-40b0-afef-f0e369d44619`)

| stage | measured result |
| --- | --- |
| clean guest reboot | issued over pinned `:2222` at `2026-10-30T08:01:35+01:00` while capture was live on boot `2fd4a99a…` |
| USB re-addressing, `:22` and capture | host capture reconnected on fresh boot ID `03ebed06-0682-40b0-afef-f0e369d44619` at `2026-10-30T08:02:02+01:00`; diagnostic `172.16.42.2:22` listening at 1.34 s |
| host reboot-hold (`scripts/pmos-reboot-hold.sh`) | `reboot-hold: root-only /run/keep created on boot 03ebed06-0682-40b0-afef-f0e369d44619` inside the 145 s window; guest `pmos-self-stage` verified the hold and `:22` at 30.97 s uptime (note: the attempt's `known_hosts` carried a leading `# 172.16.42.2:22` comment line, so a single-line mode-0600 `known_hosts_plain` pin was used to satisfy the helper's `NR == 1` check) |
| second self-stage (no host push) | `EXT4-fs (sda13): mounted filesystem without journal` at 31.09 s, unmounted at 31.35 s, `copied userspace archive from read-only /dev/block/sda13 (sda13) and verified SHA-256`, staged postmarketOS root and armed PID-1 request at 35.05 s |
| second PID-1 cutover and ack | worker independently verified `:22` boot ID, `0:600` `/run/keep`, `session-capture.py check` and a fresh selftest (`ok: true`, 1.18 s); `switch_root` executed at 155.40 s; `pmos-self-post` logged waiting at 155.55 s; `sh scripts/pmos-pid1-ack.sh` accepted on boot `03ebed06…` at 161.56 s; post-cutover `/proc/1/exe` = `/bin/busybox`, `/` = `20:1` tmpfs, OpenRC `softlevel=default` |
| second-boot modem | fresh selftest (`ok: true`, 0.114 s); guarded `remoteproc2` start at 209.87 s; `remoteproc2=running`, QMI DMS connected |
| second-boot WPSS and driver | fresh selftests (`ok: true`, 0.113 s / 0.114 s); one-shot `wpss_boot=1` + `/dev/wlan` ON hold accepted; `remoteproc3=running`, `WLAN FW is ready`, `wlan0` and `phy0` present |
| second-boot scan | fresh selftest (`ok: true`, 0.114 s); bounded `iw dev wlan0 scan` exit 0, **32 BSS** (scan is not connectivity) |
| second-boot OpenRC services and diagnosis | fresh selftest (`ok: true`, 0.114 s); `wpa_supplicant` service `started` with root-only `/etc/wpa_supplicant/wpa_supplicant.conf` (`0:600`, 1 network block), `wpa_state=SCANNING`, `iw dev wlan0 link` not connected; `networking` service stopped after `udhcpc` made 7 attempts and exited with `No lease` (0 IPv4 addresses and 0 default routes on `wlan0`) |
| target visibility (counts only) | designated SSID had **0 matches** in the 32-BSS stage scan, **0 matches** in 55-entry and 59-entry `wpa_cli scan_results`, and **0 matches** in a 52-BSS directed `iw dev wlan0 scan ssid …`; after `wpa_cli reassociate`, `wpa_state` remained `SCANNING`. Two fresh host-radio `nmcli dev wifi rescan` checks (56 and 48 BSS) also had **0 matches** |
| health and cleanup | 0 `fatal error received:`, 0 `fs_device_efs_rmts.c`, 0 `hdd_psoc_idle_timeout_callback` and 0 `kernel panic` lines across both boots; before ending worker commands, `wpa_supplicant` was stopped and the profile, raw scan and service logs were scrubbed from guest RAM while `/run/keep` (`0:600`), both remoteprocs (`running`), `:2222` and capture remained live on boot `03ebed06…` |

**Conclusion.** The single variable of #184 — host sequencing of `/run/keep` over diagnostic `:22` inside 145 s after a clean guest reboot — is resolved and measured: the second `userdata` self-stage and postmarketOS PID-1 cutover repeat cleanly without any host push. Second-boot WLAN autoconnect stopped at the named first missing line **association** (`wpa_state=SCANNING`, `udhcpc` no lease) because the designated network was absent from both guest and host radios. Under the 2026-10-29/30 owner decisions, Linux stays on the phone between runs and the coordinator owns session close and the untouched slot-A rescue baseline proof.
