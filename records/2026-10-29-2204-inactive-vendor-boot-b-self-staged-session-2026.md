---
date: 2026-10-29
issue: omnipha/linux-sm7635#164
subsystem: userspace
result: inconclusive
source: README.md
---
## Inactive `vendor_boot_b` self-staged session (2026-10-29, #164)

[BOOT.md](BOOT.md#host-only-inactive-vendor_boot_b-userspace-payload-and-self-staged-session-164-2026-10-29)
records a host-only payload and boot path, not a physical boot result. The
preferred carrier is inactive `vendor_boot_b`; an unused `super` extent is the
unused fallback. `scripts/build-vendor-boot-b-userspace-payload.sh` requires
byte-identical stock `vendor_boot_a`/`vendor_boot_b` (100,663,296 bytes, SHA-256
`23725940…`), keeps the signed prefix and terminal `AVBf` footer, and adds a
4,096-byte header at offset 18,870,272 (SHA-256 `2d09f260…`) plus the
23,713,302-byte archive at 18,874,368 (SHA-256 `7a76a110…`). The built image
reproduced SHA-256 `1bdb7c22…` at the time of writing, valid only while the
builder and inputs are unchanged. `scripts/build-init-boot-self-stage.sh`
rebuilds the measured `fef03008…` handoff with one detached hook and one
root-only script bundle; its SHA is not pinned because it changes while the
bundled scripts are edited. `scripts/pmos-self-stage.sh` probes the live
`PARTNAME=vendor_boot_b` node read-only, waits at most 145 s for `/run/keep`
inside the 150 s recovery window, and pins guest `:2222` to the diagnostic host
key so the host can pre-pin `[172.16.42.2]:2222` with strict-key checking before
its ack. After cutover `scripts/pmos-self-post.sh` waits for the 160 s
host-owned guard ack, then for a fresh host-verified capture marker released
through root-only `/run/self-stage-capture-marker` before each of modem, WPSS,
driver, scan and services. `sh scripts/test-pmos-self-stage.sh` is the host
fixture. No host push of root or a profile, no unattended power-on, no flashing;
the coordinator controls each boot. #164 stays OPEN pending physical
observation.
