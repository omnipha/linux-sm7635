---
date: 2026-10-30
issue: omnipha/linux-sm7635#197
subsystem: userspace
result: confirmed
---
# Persistent userdata root pair

Host-only. The #199 maximum now accepts the measured 241421725696-byte userdata partition, so the pair was built and verified. No partition, USB, flash, reboot, marker, credential, profile, or run-66 session operation was performed. The run-66 session remains open and untouched.

The deterministic root is outside Git at `$WORK/out/userdata-persistent-root.img`: 100663296 bytes, SHA-256 `aa8da109d3bff4657da2b0504e61856744ced3392dafad81707b1aed10bac5a5`. It is a journal-free ext4 filesystem with UUID `6f6d6e69-7068-4170-6d6f-732d726f6f74`, hash seed `6f6d6e69-7068-4173-6565-642d726f6f74`, and timestamp 1767225600. It contains the unpacked pinned archive `7a76a11062615387af5eac8f67b7f672d5f9004decac89529396d442ab3c6e26`; two serial builds were byte-identical. This is not the old 33554432-byte archive carrier `ea09444c`.

The distinct init_boot is outside Git at `$WORK/out/init_boot-persistent-root.img`: 8388608 bytes, SHA-256 `09a3e9f28bd66020d5ff51e48caebd0a9d6517527a8e243db22009d1b540031d`. Its cpio is 3698688 bytes and its LZ4 HC-12 frame is 2116896 of 2117632 bytes, leaving a 736-byte gap. The stock header and signed tail are unchanged. Its only functional delta from installed run-66 `5b5a60d4` is direct `PARTNAME=userdata` ext4 mount, `ro,noload` verification, promotion, and `switch_root`. The measured WLAN lease script and profile remain unchanged. The verifier rejects stock and measured SHAs, including `5b5a60d4` and `fcb0ed91`, marker-only or weakened changes, and `super`.

`sh scripts/test-pmos-root-contract.sh`, `sh scripts/test-pmos-self-stage.sh`, `sh scripts/test-pmos-radio-bringup.sh`, `sh scripts/test-pmos-session-dev.sh`, `sh scripts/test-pmos-pid1.sh`, `sh scripts/test-alpine-session.sh`, and `sh scripts/test-pmos-reboot-hold.sh` passed. A loop-backed namespace fixture also staged and tore down the persistent image twice without a host tarball. Physical flash and measurement remain pending under the coordinator-owned run-66 handoff. No flash or Linux/fastboot end state exists for this pair.
