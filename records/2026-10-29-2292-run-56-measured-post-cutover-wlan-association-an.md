---
date: 2026-10-29
run: 56
issue: omnipha/linux-sm7635#150
subsystem: wlan
result: confirmed
source: BOOT.md
---
## Run-56 measured post-cutover WLAN association and reachability on postmarketOS PID 1 (#150, live-session finding, 2026-10-29)

**Measured physical result — outcome (a): on the RAM-backed postmarketOS PID 1, the modem, WPSS, `wlan0`, a scan, association with the designated host-local profile, DHCP, gateway, DNS and external reachability were each measured separately and all succeeded in one held session.** The physical coordinator opened the session on the unchanged `fef03008…` `init_boot_a` image (reuse gate, no rebuild) and `device-op.py handoff` proved it. The worker independently rechecked boot ID `9f03247c-5fc8-4d38-9e5b-ac52138b4ad8`, the pinned host key `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`, `/run/keep`, 11,248,564 kB `MemAvailable` and `session-capture.py check` (`ready: true`, same boot). A first selftest attempt failed because the worker wrote the marker before starting `selftest` (it only reads bytes appended after it starts); a second one, with the marker written after the start, returned `ok: true` in 1.1 s. A fresh selftest preceded every crash-prone stage below. The worker did not flash, reboot or change any partition.

| stage | measured outcome |
| --- | --- |
| staging | the pinned 134-APK archive (`7a76a110…`), stage, teardown, guard (`dc37428e…`), transition (`0b85d1dc…`) and radio (`6442f346…`, the merged #158 script) were streamed over `ssh … cat >` (the diagnostic Dropbear has no `sftp-server`, so `scp` without `-O` fails) into root-only RAM and matched on the device; `pmos-session-stage.sh` produced postmarketOS v24.12 / Alpine 3.21.9 on the stock 6.1.84 kernel and a strict-key `:2222` shell |
| `prepare` | one pinned rmtfs process (pid 621) with its UIO mapping and `modemst*` paths; the init-created `/dev/wlan` node was verified and copied |
| PID-1 cutover | one request, guarded switch_root and `pmos-pid1-ack.sh` accepted on attempt 1; afterwards `/proc/1/exe` equals the guest BusyBox (`f35a45f7…`), `/` and `/proc/1/root` are both `20:1`, OpenRC `softlevel=default`, `local` `started` |
| modem | one `modem` stage: rmtfs links restored (`modemst1 modemst2`), `remoteproc2` `running` past 5 s, QMI DMS connected, no `fs_device_efs_rmts.c` / `rmts_get_buffer` line. This reproduces the run-55 EFS result |
| WPSS and `/dev/wlan` | the pre-cutover node `495:0` mode 0600 matched the live `/sys/class/wlan/wlan/dev` and the single character `qcwlanstate` major (the fail-closed check of #158); one helper run exit 0, `remoteproc3` `running`, `WLAN FW is ready`, `wlan0` and phy0 registered |
| `driver` | `wlan0` already registered, so no `insmod` or reload was run |
| scan | link up, one 20 s-bounded scan, exit 0, **44 BSS**. A scan is not connectivity |
| private target match | the profile (174 bytes, one network block) was transferred into root-only guest RAM and its SHA-256 matched the host file; a guest-local comparison printed only counts: **target visible in 2 of 44 BSS** |
| association | one RAM-only `wpa_supplicant` (`-B -q -D nl80211 -O /run/wlan-wpa-ctrl`, never `-K`): `wpa_state=COMPLETED` after 2 polls **and** `iw dev wlan0 link` connected; `operstate=up`, `carrier=1`. This is the stage that ended in reason 14 (MIC failure) in run 53 with the earlier derived profile, so the regenerated profile resolves that credential blocker |
| address | `udhcpc` rc 0, lease obtained; one non-link-local IPv4 on `wlan0`, one default route via `wlan0`, one nameserver |
| gateway | bounded `ping -c 3 -W 2`, rc 0, **3/3** |
| DNS | bounded `nslookup one.one.one.one`, rc 0, 5 answer addresses |
| external network | bounded `ping -c 3 -W 2 1.1.1.1`, rc 0, **3/3**, confirmed again 5 s later with rc 0 |

Two worker mistakes were recoverable diagnostics and are recorded so they are not repeated. First, the Alpine `wpa_supplicant` 2.10 has no `-f` option; the first start printed usage and exited, leaving no daemon, `wlan0` down and nothing associated. The second start without `-f`, with output redirected, is the measured one. Second, `scripts/wlan-udhcpc-lease.sh` defaults to `IP_CMD=/bin/ip`, which does not exist in this root (`/sbin/ip` does). The first `udhcpc` therefore obtained a lease but applied nothing (zero addresses, routes and nameservers); the retry with `IP_CMD=/sbin/ip` is the measured address stage. The script was not changed, because its SHA-256 (`86ebff20…`) is pinned by earlier records.

**Services.** `local` is `started`; `networking` and `wpa_supplicant` OpenRC services are `stopped` because the archive's runlevels enable nothing else. The inputs they need are `/etc/network/interfaces` (absent) and `/etc/wpa_supplicant/wpa_supplicant.conf` (absent); `/etc/deviceinfo` is present. The supplicant and DHCP in this run were started by hand, so running them as OpenRC services is unmeasured.

**Safety.** The host capture stayed live on the same boot with **0** `fatal error`, **0** `kernel panic`, **0** `hdd_psoc_idle_timeout_callback` and **0** EFS lines; `remoteproc2`/`remoteproc3` stayed `running`; `/run/keep`, the pinned original `:22` capture stream and strict-key `:2222` SSH remained healthy to uptime ~1,317 s. Before this record the supplicant was terminated through its control socket and the profile, raw scan and DHCP/reachability output were removed from guest RAM. No identifier, credential or raw log is in Git. The staged runtime and `:2222` were left running for the coordinator, who alone owns pstore, stock `init_boot_a` restore, the five slot-A hashes and Android proof. This proves in-session connectivity on the stock kernel's RAM-backed postmarketOS PID 1, not autoconnect after reboot, persistence, encrypted `/data` or a release image.
