---
date: 2026-10-30
issue: omnipha/linux-sm7635#204
subsystem: boot
result: confirmed
---
# Root contract carrier replay

Host-only replay of the existing merged pair. No image was rebuilt and no USB, flash, reboot, session, or partition operation was performed.

The designated files match their published identities:

- `init_boot`: 8388608 bytes, SHA-256 `2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28`.
- `vendor_boot_b`: 100663296 bytes, SHA-256 `f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095`.
- persistent userdata root: 100663296 bytes, SHA-256 `aa8da109d3bff4657da2b0504e61856744ced3392dafad81707b1aed10bac5a5`.

`scripts/verify-init-boot-persistent-root.py --self-test` passed on those existing images. It rejected the reconstructed omitted bundle, digest and carrier mismatches, `super`, and a weakened hold, guard, or contract. The verified LZ4 HC-12 frame remains 2100017/2117632 bytes. Both new SHAs differ from stock, `ef476d8c`, `5b5a60d4`, and the other 67 refused hashes. No physical boot was attempted.
