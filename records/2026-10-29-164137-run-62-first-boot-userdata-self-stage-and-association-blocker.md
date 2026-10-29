---
date: 2026-10-29
run: 62
issue: omnipha/linux-sm7635#176
subsystem: userspace
result: confirmed
---
## Run 62 first boot: `userdata` self-stage, modem/WPSS/wlan0 and association blocker (#176, live session)

**Measured physical result on the first of at most two boots. The `userdata` ext4 carrier works; the first-boot blocker is WLAN association, not the carrier, PID 1 or the ack.** The coordinator wrote only the verified pair `init_boot_a` `fcb0ed91…` and `userdata` `ea09444c…`, opened the session and handed it off. The worker independently rechecked boot ID `4fe15310…`, pinned key-only `:2222` SSH, root-only `/run/keep`, `session-capture.py check` on the same boot and a fresh console-marker selftest. No flash, partition change, repeated ack or session close was performed by the worker.

| stage | measured result |
| --- | --- |
| self-stage | kmsg: ext4 `sda13` mounted without journal, unmounted, `copied userspace archive from read-only /dev/block/sda13 (sda13) and verified SHA-256`; no host archive push |
| PID 1 / ack | post-cutover PID 1 on the handed-off boot, host-owned guard ack accepted; not repeated by the worker |
| modem | fresh capture selftest and marker release; `remoteproc2` `running`, QMI DMS connected, no fatal |
| WPSS | separate fresh selftest; `remoteproc3` `running`, `WLAN FW is ready` present |
| driver | separate fresh selftest; `wlan0` and phy0 registered, both remoteprocs still `running`, no insmod/reload needed |
| scan | separate fresh selftest; bounded scan exit 0, 34 BSS, mode 0600 private raw. Scan is not connectivity |
| target observation | the designated target had 0 matches in the 34-BSS scan, a later 33-BSS scan and a 22-BSS directed scan; five fresh host-radio scans (including 49 BSS) also had 0 matches. Counts only; no SSID/BSSID/profile printed |
| OpenRC | separate fresh selftest; `wpa_supplicant` started with `-iwlan0` (not `p2p0`), one enabled network, `wpa_state=SCANNING`; `networking` stopped with no DHCP lease. The `services` stage reported `radio bring-up services failed` |
| after reassociation | bounded reassociate command accepted; state remained `SCANNING`; SSH and capture stayed healthy. IPv4 addresses on `wlan0`: 0; default routes via `wlan0`: 0 |
| health | `/run/keep` 0:600, both remoteprocs `running`, `wlan0` present, no `fatal error received:`, `fs_device_efs_rmts.c`, `hdd_psoc_idle_timeout_callback` or `kernel panic`; pinned SSH and capture healthy |

**Named first missing line for the first boot:** association (`wpa_state=COMPLETED` and `iw link`), with the designated network not observable from either radio during the measurement window. Address, route, gateway, DNS and external reachability were therefore not established and none is claimed. This is not evidence that the network never broadcasts: the coordinator's preflight had it visible, and position/band/regulatory timing remain possible causes. The guest is on `country 00` and the host also on `country 00`; both scans were fresh rather than cache-only. A recoverable SSH command timeout during polling was diagnosed and the next pinned command succeeded; it was not treated as a lost session.

The next phase is the single clean guest reboot to measure host re-addressing, a fresh boot ID, `:22`, the second `userdata` self-stage, `wlan0` and autoconnect in that order. The coordinator alone owns capture/pstore, stock restore of `init_boot_a` and `userdata`, five-hash proof and Android.
