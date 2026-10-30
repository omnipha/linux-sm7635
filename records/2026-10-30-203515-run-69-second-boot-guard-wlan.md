---
date: 2026-10-30
run: 69
issue: omnipha/linux-sm7635#204
subsystem: boot
result: confirmed
---
# Run 69: second-boot guard and WLAN

Guest reboot returned boot `b5171324-06eb-46b9-b538-c518765510d1`. Pinned key-only SSH, live capture, and root-only `/run/keep` matched. The persistent ext4 root self-staged without a host push. No image, partition, reboot, or session change was made.

The first refusal was `independent recovery guard not armed`. A stale pinned `/run/pmos/bin/restart2` from the first boot blocked a new arm. Removing it allowed the guarded `switch_root` and accepted guard on the same `sda13` root.

The modem stage then needed the surviving rmtfs log visible and an empty persistent `/vendor/firmware_mnt` directory removed. After those repairs, modem, WPSS, `wlan0`, a 31-BSS scan, association, address, route, DNS, gateway, and external reachability passed. Bootloader start and slot-A rescue proof remain coordinator-owned.
