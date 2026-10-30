---
date: 2026-10-30
run: 65
issue: omnipha/linux-sm7635#191
subsystem: boot
result: confirmed
---
# Run 65: session close and slot-A rescue proof

The measured #191 session on boot `3fa41974-d20b-4ea7-9e49-ec4d70b54584` was closed with `device-op.py session close --session-outcome landed` after an executable rescue verifier succeeded. No partition was written, erased or formatted; no stock image was restored and no Android boot occurred.

| check | measured result |
| --- | --- |
| host backup manifests | `parts-a.sha256` and `parts-b.sha256`: 15/15 `OK` |
| on-device rescue partitions | diagnostic Linux boot `79d8c9ec-b545-4625-9f35-f847f35458e4` read `boot_a` `197aff11…`, `vendor_boot_a` `23725940…`, `dtbo_a` `759813db…`, `vbmeta_a` `cc1926d2…`; all match the verified stock backups exactly |
| Linux carrier | `init_boot_a` `fcb0ed91…` unchanged by design; `userdata` `ea09444c…` unchanged |
| final device state | fastboot: serial `00181152O003821`, slot a, unlocked yes, product pineapple, userspace no |

Raw hashes, SSH proofs, capture and verifier live outside the repository at `~/phone-second-life-data/mb003/pstore/attempt-20261030-0854-linux191-bootstart/`.
