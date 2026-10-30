---
date: 2026-10-30
issue: omnipha/linux-sm7635#204
subsystem: boot
result: confirmed
---
# Root contract on vendor_boot_b

Host-only. No USB, flash, reboot, session, or partition operation was performed.

The reconstructed `ef476d8c` image asks init to stage `pmos-root-contract.sh`, but its embedded xz bundle does not contain that script. `bundle_bytes` always packed the older public member list and discarded the extra contract argument. Replaying that image with the complete pinned member at xz preset 9 makes the legacy LZ4 frame 2118229 bytes, 597 bytes above the fixed 2117632-byte envelope. That raw init_boot repair is therefore not a fit.

The complete 18856-byte pinned xz bundle now occupies the backed-up `vendor_boot_b` payload window. Its signed prefix and terminal footer remain stock. Init no longer embeds the bundle: it selects only `PARTNAME=vendor_boot_b`, checks the 100663296-byte carrier, the 4096-byte header digest, and the bundle digest and size, then stages and launches the root contract. The direct `PARTNAME=userdata` ext4 root path, hold, guard, timers, profile, and userdata image are unchanged. `recovery_b` and `dtbo_b` were not needed. Slot-A `boot`, `vendor_boot`, `dtbo`, and `vbmeta` are untouched.

Two serial builds were byte-identical. The new images stay outside Git:

- `init_boot`: 8388608 bytes, SHA-256 `2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28`; LZ4 HC-12 frame 2100017/2117632 bytes.
- `vendor_boot_b`: 100663296 bytes, SHA-256 `f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095`.

Both differ from `ef476d8c`, `5b5a60d4`, stock, and the other refused measured hashes. The verifier fails the reconstructed omission, the old bundle, digest or carrier mismatches, `super`, and a weakened hold, guard, or contract. No physical boot was attempted; #197 owns that measurement.
