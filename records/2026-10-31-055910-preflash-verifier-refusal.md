---
date: 2026-10-31
issue: omnipha/linux-sm7635#223
subsystem: boot
result: refuted
run: 76
---
# Run 76: host verifier refuses the cold-start pair before flash

The settled PR #225 pair was not flashed. `verify-init-boot-persistent-root.py --self-test` exits with `init must keep the measured run-66 handoff and change only the root-contract pin` for `init_boot-coldstart-hostfree.img` SHA-256 `becd37846fedd0d4298cf562667fd498f76a5c99e2e68810ca5cacf8c1ee72b4` and `vendor_boot_b-coldstart-hostfree.img` SHA-256 `adb47dc0228cdbb1ba57dd245ecec49386d53bf24c3ab8f72493e709b78aeae8`, using stock init/vendor backups and pinned base `init_boot-mindstorms-wlan.img` SHA-256 `5b5a60d4ceaf1551217874136c0de9a26f6b3ec29f9f586e2b7cdf0d728466d6`. Host manifests passed. No verifier bypass or candidate write.

Before that refusal, unchanged installed diagnostic boot `d09ae982-6598-4c21-87a7-73dca87dee9c` read exact `PARTNAME` hashes: stock `boot_a 197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`, `vendor_boot_a 237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253`, `dtbo_a 759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992`, `vbmeta_a cc1926d2aa8e9c12df6a469111bf87f1e61e70022b84626fabcd014ae33cdffe`, installed `init_boot_a 2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28`, and `vendor_boot_b f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095`. The same unchanged chain then returned to responsive fastboot serial `00181152O003821`, slot a, unlocked. No cold start, stock restore, userdata erase, Android boot, or open session. Evidence: `attempt-20261031-0650-coldstart-hostfree-run76`.
