---
date: 2026-10-31
issue: omnipha/linux-sm7635#234
subsystem: boot
result: confirmed
---
# Post-cutover record: host fixture and successor pair

Host-only preparation for #234. No USB, device, flash, reboot, partition write, or cold start was performed. The installed run-79 pair `a4ee7def` / `6e7c5a2e` is untouched and remains never-reflash, as do `3192278b` / `ab3a0e63` and every earlier measured image.

The single functional delta is bounded post-cutover instrumentation of the refused-cutover boundary. `scripts/pmos-root-contract.sh` extends the ordered record with one post-cutover success line, `pmos-self-post: post-cutover PID 1 on boot <BOOT_ID>; guard identity check passed; pid1 identity check passed`, and accepts at most two terminal `pmos-self-post: FAIL:` lines after the transition line. The bound stays 4096 bytes and the root-only rules are unchanged: a symlink, a pre-existing record, a wrong root, an over-bound record, and a record whose boot line names a foreign boot ID are all refused. `boot_record_root /` now validates the switched root through `root_contract_switched_root` on PID 1's mount tables, which is what makes the line committable on the persistent root after cutover. `scripts/pmos-self-post.sh` writes and verifies the success line after the guard identity checks pass and before any radio stage, and its first failure appends one `pmos-self-post: FAIL: <reason> (uptime <kernel seconds>)` line.

The measured run-66 handoff, the 160-second guard arm budget, the pinned `restart2` helper (`fbe14729…`) and the `PID1_SETTLE` semantics are byte-pinned. The guard script is unchanged at `f72a68a4…`.

Host timing analysis of the run-79 record shows the unobserved return is not a guard defect. The guard armed at kernel 155.806 seconds with the 160-second budget, so the deadline was due at about 315.8 seconds. The boot was ended manually at 274.18 seconds, roughly 42 seconds before that deadline. The guard therefore never had a chance to fire, and mechanism (b) is not supported by the timing. Mechanism (a) is also absent from the delivered bytes: the built init sources the transition exactly once and contains no re-entered arm tail (`[ -f "$ROOT/run/pid1-guard/armed" ]` and the `while :; do $BB sleep 60; done` loop are both absent), which the verifier now requires.

Host fixtures passed:

- The complete record, 1147 bytes including the post-cutover success line, survived a lazy-unmount interruption and read back exactly after an `ro,noload` remount.
- A failure at the private proc/sys stage left only the reached prefix; a later transition append was refused and the record was unchanged.
- A refusal after the transition line left that line plus at most two `pmos-self-post: FAIL:` lines with the kernel uptime, and refused the success line and any later non-failure line.
- A symlink, a pre-existing record, an over-bound record, a wrong PARTNAME, and a record copied from a previous boot all refused open, append, or verify.
- The ext4 switched-root self-post fixture committed the post-cutover line on the persistent root after the guard identity checks passed, before the radio stage.

`test-pmos-boot-record.sh`, `test-pmos-root-contract.sh`, `test-pmos-pid1.sh`, and `test-pmos-self-stage.sh` all passed. `verify-init-boot-persistent-root.py --self-test` accepted only the new pair and refused 78 image hashes, including run-79 `a4ee7def` / `6e7c5a2e`, run-78 `3192278b` / `ab3a0e63`, run-76 `becd3784` / `adb47dc0`, run-73 `3eeddb35` / `762566b7`, run-72 `3c97c918`, and every earlier measured image.

Two serial builds were byte-identical. Exact candidate IDs, outside Git:

- `init_boot-cutover-record.img`: 8388608 bytes, SHA-256 `dd6ce74e47827814c3c0010d6c71f0b9d0874a370cb147bb455e05f018ed6f41`.
- `vendor_boot_b-cutover-record.img`: 100663296 bytes, SHA-256 `e7d5558037b903de3ab817619ce527319f6b54fb4ec97782e729078c666268fc`.
- Decoded cpio 3682816 bytes; reproducible LZ4 HC-12 frame 2100057/2117632 bytes; stock header and signed tail unchanged.

The coordinator may later write only this pair and run the one USB-assisted diagnostic boot the issue describes. That measurement, not this record, is the `successfulBoot` claim. #234 stays open.
