---
date: 2026-10-30
run: 70
issue: omnipha/linux-sm7635#197
subsystem: boot
result: confirmed
---
# Run 70: no host-free cold-start power path exists on VMWARE006

**Contrasting result (d): operator-independence boundary.** The #197 gate asks for one cold start of the unchanged installed run-69 chain with USB detached or the host port off, after a full power off. Before any power cycle, the coordinator measured the available power paths and stopped at the boundary: the station cannot turn the phone fully off and back on without a device-side action. A warm `fastboot reboot` was explicitly rejected as a substitute.

Measured on VMWARE006, 2026-10-30 21:24Z:

- The phone is at USB `3-2`, directly on the `00:14.0` xHCI root hub: `18d1:d00d`, serial `00181152O003821`, fastboot, slot A, unlocked. There is no intervening switchable hub and `uhubctl` is not installed. `port/disable`, `authorized` and `power/control` gate USB data/pm, not a proven VBUS power-cycle/power-on path for the phone.
- `fastboot --help` offers only `devices`, `getvar` and `reboot`/`reboot bootloader` as basics. No power-off/cold-start command exists. `fastboot reboot` is a warm start and is not a valid cold-start measurement. The bootloader also does not support partition fetch, so on-device hashes cannot be read while remaining in fastboot.
- No operator was asked to press a button, no phone restart/power-off was issued, no partition write occurred, no image or guard changed, and no host hold/ack/capture/push occurred. Since no cold boot happened, there is no new pstore/boot-ID/PID1/WLAN claim. The first stopped line is therefore not measured; the measured boundary precedes boot, at power control.

Rescue state at the stop: all `parts.sha256`, `parts-a.sha256` and `parts-b.sha256` host backups verify. The immediately preceding run-69 close read the untouched on-device rescue hashes on diagnostic boot `65c0a7bf` exactly (`boot_a 197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`, `vbmeta_a cc1926d2`, installed `init_boot_a 2f73c947` and `vendor_boot_b f792174c`). No write has occurred since that read, and the fresh fastboot gate at 21:16Z still matches the same serial/slot/unlocked identity. This is retained rescue evidence, not a fresh on-device hash claim. The phone remains in fastboot with the unchanged run-69 chain installed.

Raw host evidence: `~/phone-second-life-data/mb003/pstore/attempt-20261030-2218-coldstart-nohost-run70/` (`stage0-preflight.txt`, `stage1-power-path.txt`, `stage2-backup-manifests.txt`).

Next gate: the host-free power boundary must be resolved by a measured cold-start power path (operator rule, an independent power/watchdog carrier, or switchable-USB hardware) before another cold-start attempt. Do not manufacture a new image SHA or substitute a warm reboot for this missing power path.
