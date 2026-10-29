---
date: 2026-10-28
issue: omnipha/linux-sm7635#150
subsystem: modem
result: inconclusive
source: BOOT.md
---
## Reproducible post-cutover radio bring-up (#150, host-only, 2026-10-28)

**Host-only reproduction of the run-53 sequence — no device operation, flash, partition write, new image SHA or association claim.** Run 53 already measured RAM postmarketOS PID 1, OpenRC `default/local`, both remoteprocs running, `wlan0`/phy registered and a bounded scan (35 BSS) on the unchanged `fef03008…` image, then closed with verified five-partition stock rollback. Association, address, gateway, DNS and external reachability remain unmeasured. `scripts/pmos-radio-bringup.sh` turns that measured order into one hash-checked script instead of leaving it as session folklore.

1. **Reuse gate (no rebuild):** the live `device-op.py` rule still names the unchanged #145 `init_boot_a` image `fef030081e04d3a90451bb7d64dcfa7668c41dc4248e6e0b1959fdb40efce948` as the only reusable changed image. This script changes nothing inside that image, so no marker rebuild and no new SHA exist. Every older measured SHA stays refused. If the live gate refuses `fef03008…`, stop before any write and report the exact refusal.
2. **Before `switch_root` (`prepare`):** from the diagnostic root, after the #151 stage and while `/run/keep` is present, the script verifies the read-only stock INI at `/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` (SHA-256 `57989aba…`, 2095 B), copies that file into the guest tmpfs and links the stock firmware search path to it, copies the diagnostic `/bin/wpss-once` (SHA-256 `fef7e5da…`, the measured one-shot helper) into guest `/run/radio-bringup`, copies the `qrtr-published`/`rmtfs-published` markers, and copies an init-created `/dev/wlan` node when one exists. `switch_root` would otherwise delete all of these.
3. **After cutover, one stage at a time:** `modem`, `wpss`, `driver` and `scan` first require postmarketOS PID 1, `default/local` started and the PID-1 guard acknowledged for the current boot. `modem` and `wpss` each write one remoteproc state at most once and only from `offline`, and only after a host-injected capture-selftest marker is present in this boot's kmsg. `wpss` bind-mounts the surviving old root's read-only `modem_a` firmware, runs the staged helper exactly once and accepts its measured exit 0 or 10 (10 is only the optional `/dev/wlan` ON hold). `driver` runs one `insmod` of the old-root `qca_cld3_qca6750.ko` (SHA-256 `c2dbdcd1…`) and, only if `wlan0`/phy0 are still absent, exactly one `rmmod` plus one reload; a second reload is refused. `scan` sets `wlan0` up, checks `IFF_UP`, and keeps one 20 s-bounded raw scan root-only at `/run/radio-bringup/scan.raw`.

`sh scripts/test-pmos-radio-bringup.sh` replays this in an isolated tmpfs with a synthetic sysfs and the byte-exact helper from `scripts/build-init-boot-psoc-hold-payload.py`. It proves the pins, the one-shot guards, helper exit 10, the single insmod/reload and the root-only scan. It does **not** prove a device modem start, firmware load, scan or association. No WLAN profile is read or staged by this script.
