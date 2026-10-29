---
date: 2026-10-29
issue: omnipha/linux-sm7635#184
subsystem: userspace
result: inconclusive
---
# Run 63 preflight stopped: Qualcomm USB only, no protocol (#184)

Host-side preflight for the reboot-hold measurement reached the device gate and stopped before any image or partition action. `sh scripts/test-pmos-reboot-hold.sh` and `sh scripts/test-pmos-self-stage.sh` passed on `main` `eee4304f`. The retained USB-readdress fixture was started but was interrupted before completion; it was not required once the phone had no usable protocol.

Live USB is only Qualcomm `05c6:f000`, product `VOLCANO-QRD_SN:E4A27071`, serial `00181152O003821`, one USB mass-storage interface. ADB reports no device and fastboot reports no device. No fastboot identity, slot, unlock or partition query was possible. No image was built and no partition was written.

Run 62 remains closed with its verified stock rollback: stock `init_boot_a`, supported `userdata` erase/format, recovery-root stock hashes and Android USB confirmation. Its measured `fcb0ed91`/`ea09444c` pair stays never-reflash. The #184 second-boot hold question is unmeasured. The phone needs one device-side power or bootloader entry before protocol preflight can resume.
