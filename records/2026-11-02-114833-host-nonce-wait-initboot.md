---
date: 2026-11-02
issue: omnipha/linux-sm7635#271
subsystem: wlan
result: confirmed
---
# Host: successor init_boot 17531039 carries the #270 nonce wait on the installed a71b3f5f carrier (one init_boot_a write, awaiting the one live boot)

Issue #271 phase 1, host only. No flash, no USB, no boot and no partition
write. Nothing here is a device measurement; the nonce mint time on run 95's
boot stays inferred (see the #268 record). The installed never-reflash pair
(init_boot_a 27a78a22, vendor_boot_b a71b3f5f) was not touched.

## The image to flash

`~/sm7635-build/out/init_boot-nonce-wait-271.img` (outside Git), 8388608 bytes:

`17531039e2c1bb36eac7c5fb2d4c343d53977950cbd2ade0d9dea6f3dd794bdd`

Companion output, NOT to be flashed (installed carrier stays):
`~/sm7635-build/out/vendor_boot_b-nonce-wait-271.img`, 100663296 bytes,
`a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3`, byte-
identical (`cmp`) to the installed carrier rebuild.

Built by the existing `scripts/build-init-boot-persistent-root.sh` (two serial
builds, byte-identical, builder self-test with negative mutations, verifier),
then re-verified against the installed carrier with
`verify-init-boot-persistent-root.py`. Hash is stable across three builds of
the same tree. Stock header and signed tail unchanged; LZ4 HC-12 frame
2104309/2117632 (gap 13323).

## Defect found and fixed before this image existed

The unmodified builder at origin/main (1af42f2) produced init_boot
`5da3d8f56ee4eb925635abb487bb1ee8f59a84698656b993c0685df0773aed20` with a NEW
carrier `399bf518…`. The #270 change had re-pinned `SELF_POST_BUNDLE_SHA`
(5e118ffc to dcfe1cf5), so the fixed self-post entered the vendor_boot_b
bundle. The init pins the carrier's header and bundle digests, and every
mismatch ends the hook with `exit 0`: against the installed a71b3f5f the
reader exits before staging anything (verifier on that pair: `FAIL: carrier is
not the pinned vendor_boot_b root-contract image`), no `/run/keep`, no
self-stage, and the old self-recovery would return to fastboot at about 150 s.
That image would also have needed a second partition write. It was never
flashed and is not a candidate; `5da3d8f5` and `399bf518` were host-built only
and are discarded.

Correction (scripts only, no interlock change): the nonce-wait loop and the
guard-contract fallback are removed from the bundle copy by an exact
`without_nonce_wait` transform (each block must occur exactly once, result
pinned to the run-95 plain script `fe98c0d2…`), so the bundle self-post is the
run-95 `5e118ffc…` again and the carrier is a71b3f5f. The fix travels only in
the existing root-only trace member `/run/omnipha-self-post-trace.sh`, which the
init hook moves over `/run/pmos-self-post.sh` before `/run/keep` and
self-stage. The builder and verifier now require the carrier digest to equal
the installed a71b3f5f, and refuse the run-95 init 27a78a22.

## Reconciliation of hashes (searched, not guaranteed)

17531039 is absent from the repo and its history, from the device-op
attempted-SHA ledger, every `pstore/` attempt dir and both builder/verifier
refusal sets. It differs from every flashed image, so this is a new image, not
a repeat of 27a78a22. Absence in searched records is observed, not proven.

## What differs from the flashed run-95 image 27a78a22

Independent in-memory comparison:

- Header: only the ramdisk size field. Signed tail: identical.
- cpio: 55 entries, identical names; all entries except `init` and the trace
  member are byte-identical.
- `init`: exactly one line differs, the SHA-256 pin of the trace member.
- Trace member: the 11-line nonce-wait loop (with its
  `trace "guard nonce wait $i"` line) plus the one contract-fallback line.
  Nothing else; the guard script is unchanged (f72a68a4…) and the check itself
  is byte-identical. The wait is bounded at 20 sleeps and re-asserts armed,
  accepted and ack each second.
- Hook order: bundle `mv` of `pmos-self-post.sh`, then the trace-member `mv`
  over it, then `touch /run/keep`, then self-stage.

## Fixtures (host, all green on this tree)

`test-pmos-pid1.sh`, `test-pmos-boot-record.sh`, `test-pmos-self-stage.sh`,
`test-pmos-radio-bringup.sh`, `test-pmos-root-contract.sh` (real BusyBox PID 1
switch_root; run-95 replay fails on a late nonce, fixed script waits and
passes, never-minted nonce refuses after 20 s, fallback and fail-closed cases).
Builder self-test: 85 refused image hashes. Not run: `test-pmos-pid1-request.sh`
(stale pin, fails identically on clean main per the #265 record).

## Known limits (not changed, by scope)

- `record_fail` still has no guard-copy fallback: with
  `/run/pmos-root-contract.sh` absent, a failure after the wait (including a
  never-minted nonce) is evidenced in kmsg and `self-post.log`, not in the
  persistent boot record.
- This is the first boot in which the radio stages can run pre-ack. The
  userspace guard cannot cover a kernel crash; recovery relies on the
  coordinator's preflighted path.
- `deinstrument` strips whole lines that start with `trace `; it does not
  detect extra statements after a trace call on the same line. Pre-existing,
  not widened here.

## Coordinator experiment (one boot, phase 2 of #271)

Flash only `init_boot_a` with 17531039 after the standing verified-backup,
rescue-hash and recovery-path gate; `vendor_boot_b a71b3f5f` and stock slot-A
images unchanged. Pre-arm the `:2222` capture before the single reboot. No
pid1-ack before the pre-ack window ends and no worker racing the guard.
Prediction: kmsg shows `guard nonce wait N` lines at about 156.5 s, the nonce
check passes, the post-cutover record appends, and at least one radio stage
runs. Report exactly one of:

- (A) wait lines, check passes, record appends, a radio stage runs;
- (B) the full 20 s wait expires without nonce (guard state armed/accepted/
  ack/nonce and timing);
- (C) another check refuses after the nonce passes (name it);
- (D) self-post never runs / no SSH (last trace line).

If the ~160 s no-ack return or any failure ends the window earlier, record
that boundary as an early end and inconclusive about a full 20 s; an early
self-return is not an elapsed wait. Not WLAN acceptance: that stays two fresh
self-starting boots per PLAN.md.
