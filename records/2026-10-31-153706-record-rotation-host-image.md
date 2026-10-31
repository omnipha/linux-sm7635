---
date: 2026-10-31
issue: omnipha/linux-sm7635#237
subsystem: boot
result: confirmed
---
# Record rotation: host fix, fixtures and successor pair

Phase-1 host-only delivery for #237. No USB, device, flash, reboot, cold start,
or partition write was performed, and no display guess went into the image: the
panel question stays live-session work under the live-recipe rule. The measured
run-83 pair `dd6ce74e` / `e7d55580`, run-79 `a4ee7def` / `6e7c5a2e` and every
earlier measured image remain never-reflash.

The single functional delta closes the run-83 deadlock at its measured cause.
`boot_record_open` in `scripts/pmos-root-contract.sh` no longer fails unconditionally
on a pre-existing record. Before refusing, it now fully validates the prior file:
regular, root-only, mode 0600, link count 1, size within the unchanged 4096-byte
bound, consistent with its own byte count, and whose first line is exactly
`boot <foreign-boot-id>` with a syntactically valid boot ID that differs from the
current boot. Only then the new `boot_record_rotate` moves it with `mv -n` to the
per-boot archive path `.omnipha-boot-record-<foreign-boot-id>` on the same
persistent root, re-verifies the archived bytes, syncs, and opens a fresh record
for the current boot exactly as before. Rotation is refusable, never a bypass:
a symlink, a hard link, a wrong mode or owner, an over-bound file, a hostile or
malformed first line, a same-boot record, a pre-existing or symlinked archive
path, and a wrong or unpinned root are all still refused with the prior record
left byte-identical in place. `boot_record_append` and `boot_record_verify` are
unchanged, so the measured run-66 handoff, the root-only rules and the bound stay
byte-pinned; the guard script is unchanged at `f72a68a4…`.

Host fixtures passed (`test-pmos-boot-record.sh`, loop-backed ext4):

- A complete valid prior foreign record rotated; the new boot opened, appended,
  and both the fresh record and the archived prior record survived a lazy
  detach and `ro,noload` remount readback.
- Every hostile case above refused and left the prior record in place; a valid
  prior record still rotated afterwards on the same root.
- The earlier fixture cases (interrupted-transition survival, stage prefix,
  bounded FAIL lines, symlink/over-bound/wrong-root/foreign-boot refusals)
  are unchanged and green.

`test-pmos-root-contract.sh` (contract, ext4 switch_root ack and timeout cases),
`test-pmos-self-stage.sh` and `test-pmos-pid1.sh` all passed against the changed
contract. The verifier refuses the run-83 hashes and gained mutations for a
forced-overwrite rotation, a removed same-boot guard and a removed rotation;
its self-test passed with 80 refused image hashes.

Two serial builds were byte-identical. Exact candidate IDs, outside Git:

- `init_boot-record-rotation.img`: 8388608 bytes, SHA-256 `27c4d8959ffdb5154aaa11bdf508ec7a1d81fe3cffbaaeb66bfe52b31365b21c`.
- `vendor_boot_b-record-rotation.img`: 100663296 bytes, SHA-256 `da4651d827cad181e55baf1bd9ddb9876fcc271b791c5046362ef056ea69c9c6`.
- Decoded cpio 3682816 bytes; reproducible LZ4 HC-12 frame 2100054/2117632 bytes; stock header and signed tail unchanged.

The coordinator may later flash only this pair to `init_boot_a` and
`vendor_boot_b` and run the one USB-assisted diagnostic boot the issue
describes, which is also what makes the panel reachable for the live display
diagnosis. That measurement, not this record, is the successfulBoot claim.
#237 stays open for the physical result and the guest-only display work.
