---
date: 2026-10-30
issue: omnipha/linux-sm7635#204
subsystem: boot
result: refuted
---
# Init_boot root-contract envelope overflow

Host-only. No image was written and no USB, flash, reboot, session, or partition operation was performed.

The reconstructed `ef476d8c` bundle is 17568 bytes and unpacks seven older scripts plus the private profile. `pmos-root-contract.sh` is absent. The first drop is `build-init-boot-self-stage.py` `bundle_bytes`: it packs only its fixed public member list, so the contract passed by the persistent-root builder never enters the xz archive. The old init does pin and launch that missing member.

Replacing only that archive member with the current pinned contract keeps every measured script, profile, guard, timer, header, signed tail, `MAX_FRAME`, `TAIL_OFFSET`, HC-12 level, and frame format. The contract is 7486 bytes and the complete uncompressed tar is 92160 bytes. XZ preset 6 produces 18856 bytes and an LZ4 frame of 2118237 bytes. Preset 9, the smallest measured result, stays 18856 bytes and produces 2118229 bytes. The fixed envelope is 2117632 bytes, so the smallest frame is 597 bytes over. No init_boot SHA was produced.

The pinned contract therefore cannot be added inside the existing init_boot envelope without dropping or weakening a measured member. `vendor_boot_b`, `recovery_b`, and `dtbo_b` are rejected by the current gate, and no such image is published here. #197 remains blocked on this host stop.
