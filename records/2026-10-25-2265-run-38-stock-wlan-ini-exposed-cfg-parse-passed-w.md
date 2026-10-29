---
date: 2026-10-25
run: 38
issue: omnipha/linux-sm7635#106
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Run 38: stock WLAN INI exposed, cfg_parse passed, wlan0 registered (#106, outcome a, 2026-10-25)

**Measurement source:** the physical coordinator's record
(sprintberlin/phone-second-life commit `c5e7972`, `devices/mb003.md`), with
host-only evidence under
`~/phone-second-life-data/mb003/pstore/attempt-20261025-2148-initboot-wlanini/`
(2026-10-25 21:48–22:04 Europe/Berlin). The distinct-SHA
`init_boot-wlan-ini.img`
(`e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c`, 8,388,608 B,
never flashed before) was flashed to `init_boot_a` only, after the 16/16
manifest, 5/5 on-device stock hash proof and fresh fastboot gate. Key-only SSH
as root on the stock 6.1.84 kernel carried the #106 session marker; the capture
selftest passed on the second attempt (first attempt
`"no fresh marker in capture within timeout"`, retry OK, marker line latency
1.108 s).

**Outcome (a): the INI cause is confirmed.** In-session proof first: the new
wlan-ini phase logged `stock vendor_a bound read-only at /vendor` and
`stock WCNSS_qcom_cfg.ini reachable (sha ok, 2095 B)`
(`capture/kmsg.log:2314-2316`), and an SSH-side read of the resolved chain
returned exactly the pinned target hash
`57989aba…` for `/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` and
`/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini`, with both stock
erofs symlinks (`WCNSS_qcom_cfg.ini` → the vendor path, `wlan_mac.bin` →
`/mnt/vendor/persist/qca6750/wlan_mac.bin`) present at their stock locations
(`stage6-ini-proof.txt`).

One guarded `remoteproc2` start held the modem `running` past +80 s with
`icnss2_qmi: QMI DMS service connected` (`stage9-dms.txt`), then exactly one
`/bin/wpss-once` boot: `remoteproc3` powered up `qca6750/wpss.mdt` (4844 B),
`WLAN FW Initialization done: 0x680483` (`kmsg:2510`) and `WLAN FW is ready:
0x480487` (`kmsg:2511`) — the same FW_READY as run 37. The discriminating
difference: **the run-37 `icnss2: Driver probe failed: -1` line is absent
(whole-capture grep, count 0)**, and the qca_cld3 probe chain continued —
`qca6750:` HDD/WMA bring-up lines run from `kmsg:2515` through `kmsg:2570`
(policy manager, `wma_open`, `htc_wait_target: Target Ready!`, service-ready,
`wma_wait_for_ready_event: FW ready event received`, spectral/regulatory/green
AP), exactly the continuation predicted for outcome (a), and **`wlan0` was
registered**: `/sys/class/net/wlan0` whose address equals the MAC received in
the `icnss2_qmi: Received DMS MAC` line (`kmsg:2512`; address itself is
private device data, redacted), confirmed over
SSH (`stageB-wlan0.txt`, `stageB-live.txt`). `cfg_parse` therefore passed: the
single-variable INI exposure removed the run-37 `-EPERM`.

**Measured next single blocker:** `wlan0` is present but its operstate is
`down`. The capture shows `hdd_psoc_idle_timeout_callback: Psoc idle timeout
elapsed; starting psoc shutdown` (`kmsg:2555`) ~0.81 s after FW ready — with no
interface user (no association work, no wpa_supplicant in the session), the
HDD psoc-idle timer shut the psoc down and the netdev stayed registered but
down. The next single question is therefore the psoc-idle/bring-up path for the
registered interface, not the INI, not WPSS, not the probe delivery, and not
association. No reprobe, module reload or second WPSS attempt was performed.

**Recovery and rollback, verified:** `/bin/restart2 bootloader`, fresh fastboot
gate, stock `init_boot_a` `baa33fd4` Sending/Writing OKAY
(`stageD-restore.txt`), recovery-root on-device SHA-256 exact stock for
boot_a `197aff11`, init_boot_a `baa33fd4`, vendor_boot_a `23725940`, dtbo_a
`759813db`, vbmeta_a `cc1926d2` (`stageE-ondevice-hashes.txt`, 5/5); pstore
pulled before Android (`console-ramoops-0` 135,270 B containing the #106
marker, 1 occurrence); `adb reboot` to `sys.boot_completed=1`, A059P, slot
`_a`, stock kernel 6.1.84, unlocked/orange (`stageF-stock-android.txt`). No
test image remains.

`e75c5bd2` is now measured and **never-reflash**. `d9d8d2b8`, `bf2089c4`,
`8dddb8c7`, `35866d56`, `ae2ccff7`, `4216af26` and all earlier measured SHAs
remain never-reflash without exception.
