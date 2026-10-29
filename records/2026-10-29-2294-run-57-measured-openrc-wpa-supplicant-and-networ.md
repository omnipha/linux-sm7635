---
date: 2026-10-29
run: 57
issue: omnipha/linux-sm7635#160
subsystem: userspace
result: confirmed
source: BOOT.md
---
## Run-57 measured OpenRC `wpa_supplicant` and `networking` on postmarketOS PID 1 (#160, live-session finding, 2026-10-29)

**Measured physical result — outcome (a): both OpenRC services stayed started and association, address, gateway, DNS and external reachability each succeeded in one held session.** The physical coordinator opened the session on the unchanged `fef03008…` `init_boot_a` image and `device-op.py handoff` proved it (`run57_handoff_052523_15580`). The worker independently rechecked boot ID `9786417b-4cdc-4fe0-bd22-bf05b25d798d`, the pinned host key `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`, `/run/keep`, 11,246,080 kB `MemAvailable` and `session-capture.py check` (`ready: true`, same boot). A fresh capture selftest preceded every crash-prone stage. The worker did not flash, reboot or change any partition.

| stage | measured outcome |
| --- | --- |
| staging | the pinned 134-APK archive (`7a76a110…`), stage, teardown, guard (`dc37428e…`), transition (`0b85d1dc…`), radio (`79da9f6e…`, the merged #161 script), lease helper (`86ebff20…`) and `restart2` (`fbe14729…`) were streamed over `ssh … cat >` into root-only RAM and matched on the device; `pmos-session-stage.sh` produced postmarketOS v24.12 / Alpine 3.21.9 on the stock 6.1.84 kernel and a strict-key `:2222` shell |
| `prepare` | one pinned rmtfs process (pid 619) with its UIO mapping and `modemst*` paths; the init-created `/dev/wlan` node `495:0` mode 0600 was copied |
| PID-1 cutover | one request, guarded switch_root and `pmos-pid1-ack.sh` accepted on attempt 1; afterwards `/proc/1/exe` equals the guest BusyBox (`f35a45f7…`), OpenRC `softlevel=default`, `local` `started`, no crashed services |
| modem | one `modem` stage: rmtfs links restored (`modemst1 modemst2`), `remoteproc2` `running` past 5 s, QMI DMS connected, no `fs_device_efs_rmts.c` / `rmts_get_buffer` line |
| WPSS and `/dev/wlan` | the copied node matched the live `/sys/class/wlan/wlan/dev` and the single character `qcwlanstate` major; one helper run exit 0, `remoteproc3` `running`, `WLAN FW is ready` |
| `driver` | `wlan0` and phy0 were already registered, so no `insmod` or reload was run |
| scan | link up, one 20 s-bounded scan, exit 0, **40 BSS**. A scan is not connectivity |
| first OpenRC start | `services` enabled only `wpa_supplicant` and `networking` and started them with `rc-service -D`. The supplicant reached `started`, but its init script's `find_wireless` returned the first matching interface, `p2p0`, ahead of `wlan0`; the daemon ran as `/sbin/wpa_supplicant -ip2p0 -c…`. `networking` then ran `udhcpc` five times, reported `no lease, failing` and stayed `stopped`. No hand-started supplicant was used |
| corrected OpenRC start | the first failure was recoverable while SSH and capture stayed healthy. The worker stopped the service through OpenRC, set `wpa_supplicant_if="wlan0"` in the RAM-only `/etc/conf.d/wpa_supplicant` and started it through OpenRC again. The daemon ran as `/sbin/wpa_supplicant -iwlan0 -c…` and reached `wpa_state=COMPLETED` after 2 polls **and** `iw dev wlan0 link` connected; `operstate=up`, `carrier=1` |
| `networking` | one OpenRC `rc-service -D networking start`, rc 0, `started`. `local`, `wpa_supplicant` and `networking` were the only started services; `sshd`, `udev` and `tmpfs` stayed stopped and `rc-status --crashed` was empty |
| address | the service's `udhcpc` applied one non-link-local IPv4 on `wlan0`, one default route through `wlan0` and one nameserver, through the staged wrapper's `IP_CMD=/sbin/ip` |
| gateway | bounded `ping -c 3 -W 2`, rc 0, **3/3** |
| DNS | bounded `nslookup one.one.one.one`, rc 0, 4 answer addresses |
| external network | bounded `ping -c 3 -W 2 1.1.1.1`, rc 0, **3/3**, confirmed again 5 s later with rc 0 |

The first start is the new measured blocker for the merged script: on this radio stack `find_wireless` is not `wlan0`-only, because `p2p0` and `wifi-aware0` also expose `phy80211`. The in-session fix was a guest-RAM `conf.d` assignment, not a script change. The host fixture did not catch it, because its dummy `wlan0` has no `phy80211` and the supplicant started without `-i` there. `scripts/pmos-radio-bringup.sh` now writes `wpa_supplicant_if="wlan0"` to `/etc/conf.d/wpa_supplicant` after checking the archive's initial `conf.d` hash, and the fixtures check both that line and the running `-iwlan0` argument.

**Safety.** The host capture stayed live on the same boot with **0** `fatal error`, **0** `kernel panic`, **0** `hdd_psoc_idle_timeout_callback` and **0** EFS lines; `remoteproc2`/`remoteproc3` stayed `running`; `/run/keep`, the pinned original `:22` capture stream and strict-key `:2222` SSH remained healthy to uptime ~1,867 s. Before this record the raw scan was removed from guest RAM. The profile stays at `/etc/wpa_supplicant/wpa_supplicant.conf`, mode 0600, because the supervised service reads it on a respawn; it is not in Git, logs or this record. The staged runtime and `:2222` were left running for the coordinator, who alone owns pstore, stock `init_boot_a` restore, the five slot-A hashes and Android proof. This proves in-session connectivity through the distro OpenRC services on the stock kernel's RAM-backed postmarketOS PID 1, not autoconnect after reboot, persistence, encrypted `/data` or a release image.
