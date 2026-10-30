---
date: 2026-10-30
run: 69
issue: omnipha/linux-sm7635#204
subsystem: boot
result: confirmed
---
# Run 69: persistent root and first-boot WLAN

The existing pair booted as `238a6bc2-0c01-471b-9c16-d003e5684449`. Diagnostic SSH, live capture, root-only `/run/keep`, and the installed hashes matched. Slot-A rescue hashes stayed unchanged. No partition was written and the session was not closed.

The staged postmarketOS root was the pinned userdata ext4 filesystem. `pmos-radio-bringup prepare` failed because the persistent root had no `/vendor` directory. Creating that directory allowed prepare, the guarded PID 1 request, and `switch_root` to complete. The guard accepted the switched root.

After fresh capture gates, modem and WPSS reached running, `wlan0` registered, and a bounded scan found 27 BSS entries. The designated network was visible. OpenRC `wpa_supplicant` and `networking` associated, obtained `192.168.178.38/24`, installed the gateway and DNS, and reached the gateway and `1.1.1.1` without loss. The created `/vendor` directory and pinned INI link now persist in userdata. Guest reboot and bootloader-start persistence remain unmeasured.
