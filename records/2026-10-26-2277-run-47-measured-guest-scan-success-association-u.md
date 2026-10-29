---
date: 2026-10-26
run: 47
issue: omnipha/linux-sm7635#134
subsystem: wlan
result: confirmed
source: BOOT.md
---
## Run-47 measured guest scan success; association unmeasured (#134, live-session finding, 2026-10-26)

**Measured physical result — the scan stage only.** The physical coordinator
flashed the currently reusable `init_boot_a` image
(`0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa`, 8,388,608
bytes) through the live device-op gate after 16/16 checked backups, the five
recovery-root stock hashes and a fresh fastboot identity/slot/unlock gate, proved
pinned key-only SSH and a fresh capture selftest for the current run-47 boot,
and set `/run/keep` at uptime 14 s. One guarded modem start reached
`running`/DMS and one `/bin/wpss-once` exited 0 with
WPSS running, firmware ready, `wlan0` present and zero fatal/crash/idle
callbacks. **`boot_a`, `vendor_boot_a`, `dtbo_a` and `vbmeta_a` stayed stock; at
the time of this finding stock rollback was NOT yet performed.** No image, kernel,
config, module, timer or partition was changed by the worker.

The worker independently verified the pinned host-key fingerprint
`SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w` for `[172.16.42.2]:22`,
key-only root SSH returning the coordinator's same boot ID, `/run/keep` present
and the RAM tool bundle present. `session-capture.py check` reported `ready:
true` on that boot before the retry scan and again afterward; the coordinator's
same-boot fresh selftest had passed before the handoff.

### The earliest failure was an administratively-down interface, not the driver

| stage | command | exit | measured evidence |
| --- | --- | ---: | --- |
| client load / phy | RAM `iw` (v6.9) | 0 | `Wiphy phy0`; `wlan0` ifindex 16, `type managed`, `wiphy 0`, txpower 0.00 dBm |
| rfkill | `/sys/class/rfkill/rfkill0` | — | `state=1`, `type=wlan` (not blocked) |
| reg domain | `iw reg get` | 0 | global `country 00: DFS-UNSET` (passive-scan bands); `phy#0 (self-managed) country US: DFS-FCC` |
| **scan #1** (coordinator) | 20 s-bounded `iw dev wlan0 scan` | **156** | `command failed: Network is down (-100)`; pre-scan flags `0x1002`, operstate `down` |
| link-up (coordinator) | `ip link set wlan0 up` | 0 | flags `0x1002` → `0x1003`; operstate still `down` |
| **scan #2** (worker, after IFF_UP) | 20 s-bounded `iw dev wlan0 scan` | **0** | empty stderr; 61,340 bytes stdout; **17 BSS** (10 on 2.4 GHz, 7 on 5 GHz); post flags `0x1003`, operstate `down`, carrier `0` |

`-100` is `-ENETDOWN`. Flags `0x1002` are `IFF_BROADCAST|IFF_MULTICAST` **without**
`IFF_UP` (bit `0x1`), i.e. the interface was administratively **down** when scan #1
was issued; `0x1003` adds `IFF_UP`. The retry scan is therefore **not** a second
experiment or a driver retry on a failed attempt — it is the *same* nl80211 scan
request re-issued once after the single user-space precondition that the first
attempt's own error text named, exactly the "easily corrected user-space
dependency" the issue says to fix in-session rather than burning a new boot. No
second modem start, no second `/bin/wpss-once`, no module reload, no interface
recreation and no image change were involved.

Scan #2 exited 0 and reported 17 BSS, so **the stock qca6750 driver does serve a
guest nl80211 scan**. This resolves the #132 "no runnable client" finding and the
run-46 "link-up is not a scan" gap. It does **not** establish that the protected
target was among the 17 BSS: the worker never inspected or matched SSIDs/BSSIDs,
and no profile was read.

### Session safety after the scan

Against the worker's pre-scan continuous-capture offset (160,909 bytes), the host
capture grew 457 bytes / 3 lines with **0** new `fatal`, **0** new `crash` and
**0** new `hdd_psoc_idle_timeout_callback` matches; `remoteproc2` and
`remoteproc3` remained `running`; `wlan0` stayed registered with flags `0x1003`;
`/run/keep` stayed present; SSH and capture remained live at uptime 1,238 s. The
raw scan output was kept in guest RAM at mode `0600` and is not published; no
SSID, BSSID, MAC, credential, private path or raw log appears in this repo.

### What remains unmeasured

Association, address acquisition and reachability are **all unmeasured** — they
require the protected host-local WLAN profile, whose transfer and handling belong
to the coordinator alone. A successful scan is **not** WLAN connectivity, and
`operstate=down`/`carrier=0` before association is expected, not a failure. #134
stays **OPEN**; it is not closed by this finding, and the worker claims no
`PACKAGE_COMPLETE`. The coordinator owns target matching, any profile
provisioning, the remaining bounded stages, session closure, evidence/pstore
preservation before Android, the stock `init_boot_a` restore and the five-hash
proof. The procedure for those stages is the unchanged plan recorded below.
