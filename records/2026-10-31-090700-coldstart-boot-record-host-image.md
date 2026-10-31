---
date: 2026-10-31
issue: omnipha/linux-sm7635#230
subsystem: boot
result: confirmed
---
# Cold-start boot record: host fixture and successor pair

Host-only preparation for #230. No USB, device, flash, reboot, partition write, or cold start was performed. The installed run-78 pair `3192278b` / `ab3a0e63` is untouched and remains never-reflash, as do all earlier measured images.

The single functional delta is a bounded boot record on the already-pinned persistent ext4 userdata root. `scripts/pmos-root-contract.sh` gains `boot_record_open`, `boot_record_append`, and `boot_record_verify`. The record is a regular, single-link, root-owned mode-0600 file at `$ROOT/.omnipha-boot-record`, created with `O_EXCL`, rejected if it pre-exists or is a symlink, capped at 4096 bytes, and `sync -f`-committed at each append and before the transition. The injected session-stage opens it only after the pinned writable root is verified and writes the boot ID plus the already-emitted hold line; later appends are the existing unpacked-root, private-device, SSH, staged, persistent-mount, key, radio-prepare, and PID 1 request lines, in that order. The transition appends and verifies its final line immediately before `exec switch_root`. `ROOT_CONTRACT_KIND` must be ext4 and the mount must be read-write pinned userdata; a wrong root refuses.

Host fixtures passed:

- (a) A complete record (1010 bytes: boot ID plus 10 ordered stage lines) survived a lazy-unmount interruption and read back exactly after `ro,noload` remount.
- (b) A simulated failure at the private proc/sys stage left only the boot ID and the two reached stage lines; a later transition append was refused and the record was unchanged.
- (c) A symlink, pre-existing record, over-bound record (4401 bytes), and wrong PARTNAME all refused open, append, or verify.
- (d) The injected session-stage open/hold block wrote the boot ID and hold line first; the remaining ordered lines then verified exactly.

`test-pmos-boot-record.sh`, `test-pmos-root-contract.sh`, `test-pmos-pid1.sh`, and `test-pmos-self-stage.sh` all passed. The merged `verify-init-boot-persistent-root.py --self-test` accepted only the new pair, with 76 refused image hashes including run-78 `3192278b` / `ab3a0e63`, run-76 `becd3784` / `adb47dc0`, run-73 `3eeddb35` / `762566b7`, run-72 `3c97c918`, and every earlier measured image. Host stock manifests `parts.sha256`, `parts-a.sha256`, and `parts-b.sha256` all verified.

Two serial builds were byte-identical. Exact candidate IDs, outside Git:

- `init_boot-coldstart-record.img`: 8388608 bytes, SHA-256 `a4ee7def41e645301f59bdc4dc043c97253a4002d8774016ee3557633b0cb6e3`.
- `vendor_boot_b-coldstart-record.img`: 100663296 bytes, SHA-256 `6e7c5a2e26981fc19c9eba97356d1a52f80e768cb6b9536bc9cb4fd906a8c59e`.
- Decoded cpio 3682816 bytes; reproducible LZ4 HC-12 frame 2100057/2117632 bytes; stock header and signed tail unchanged.

The measured run-66 handoff, persistent root, guest-owned `/run/keep`, guard re-arm, post-cutover radio path, and 160-second no-ack recovery are unchanged. The coordinator may later write only this pair and use one normal USB-assisted diagnostic boot to prove the record is readable and the independent deadline still returns responsive fastboot; that is not a cold start. The button-assisted cold start remains separately scheduled. #230 stays open.
