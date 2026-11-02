---
date: 2026-11-02
issue: omnipha/linux-sm7635#275
subsystem: wlan
result: confirmed
---
# Host: successor init_boot 2ebdf1db restores the kmsg-attested panel record so the post-cutover append passes

Issue #275 phase 1, host only. No flash, no USB, no boot, no partition write.
The refusing check and its reproduction are in the sibling record
`records/2026-11-02-142315-host-append-refusal-reproduction.md`.

## The image to flash (one init_boot_a write, phase 2 is the coordinator's)

`/home/gregor/sm7635-build/out/init_boot-append-refusal-275.img`, 8388608 bytes:

`2ebdf1db26193f7f0c3f4c6d42f722008bd1ee2718adf399dfe4927cc3eb9632`

Companion output, NOT to be flashed (installed carrier stays byte-identical):
`/home/gregor/sm7635-build/out/vendor_boot_b-append-refusal-275.img`,
100663296 bytes,
`a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3`.

Built with `scripts/build-init-boot-persistent-root.sh` (two serial builds,
byte-identical; verifier `--self-test` negative mutations pass each time, then
a final verifier pass). cpio 3698176 bytes; LZ4 HC-12 frame 2105602/2117632;
gap 12030; stock header and signed tail unchanged. Self-test reports 87 refused
image hashes (run-96 `17531039` is now in the builder's REFUSED set).
`cmp` against the installed carrier is implied by the hash equality above;
the carrier file is never a flash target.

Uniqueness (searched, not guaranteed): `2ebdf1db` is absent from the repo tree
and `git log --all -S`, from the device-op attempted-SHA ledger in
`~/phone-second-life-data/mb003/status.yaml` (4 prior hashes there; 17531039
present as expected), from every `pstore/attempt-*` dir, and from both
refusal sets. It differs from 27a78a22 (run 95), 17531039 (run 96) and every
earlier measured image.

## What changed (self-post only; contract and guard untouched)

`scripts/pmos-self-post.sh` gains a bounded, fail-closed restore before the
post-cutover append, plus a refusal diagnostic:

1. Only if `/run/pmos-pre-ssh-panel.record` is absent and the persistent record
   exists, self-post reads THIS boot's kernel log for the display phase's panel
   line (`usb-init: usb-init: pre-SSH panel … boot <this boot id>`). All
   matches must be byte-identical (conflicting duplicates refuse; BusyBox
   `dmesg` timestamps are tolerated). The line is capped at 400 bytes and must
   end in ` boot <current boot id>`.
2. The kmsg-attested line must equal record line 3 — the expected value stays
   independent of the record under verification, so the ordered-sequence check
   is not weakened into self-consistency. A record line that differs from kmsg
   is refused, never recycled.
3. The file is recreated root-only (umask 077, noclobber, `0:600:1` verified)
   and `trace 'panel record restored from the boot kernel log'` is emitted. Any
   failure leaves the old refusal path intact.
4. `trace_refusal` (trace-only) names the refusing check in kmsg on append
   refusal: root contract, boot id, record file shape, `boot_record_lines`,
   the ordered-sequence check (with panel file presence), or the size
   bound/write. `record_fail` still has no guard-copy fallback (out of scope,
   unchanged); its kmsg line is the diagnostic channel.

Delivery mechanics (same pattern as #271): `pmos-root-contract.sh` is
unchanged (`c76c31ff…`); the guard copy stays byte-identical. The builder's
`without_nonce_wait` transform now also strips the panel-restore block from
the BUNDLE copy, which therefore remains the run-95 plain script
(`fe98c0d2…`, bundle `5e118ffc…`) and the carrier hash is a71b3f5f again. The
fix and the diagnostic travel only in the root-only trace member
`/run/omnipha-self-post-trace.sh`. `TRACE_LINE` now also matches
`trace_refusal` so no diagnostic call leaks into the plain or bundle scripts
(deinstrument asserts `trace_refusal` is gone); the verifier additionally
requires the restore marker in the trace member and its absence from the
bundle self-post.

## Fixtures (host, all green)

- `test-pmos-root-contract.sh`: ext4-ack now replays run 96 — a 12-line
  pre-cutover record with the panel line at position 3, the panel file absent
  after cutover, the panel line published once to this boot's kernel log via
  the guest `/dev/kmsg` node. The pre-fix variant (restore removed) refuses at
  the ordered-sequence check and names it plus the absent panel file, leaving
  the record unchanged; the fixed script restores, appends and verifies, and
  the record keeps the panel line at position 3. A record line 3 that differs
  from kmsg (foreign boot id / different node) is refused and never restored.
  Existing nonce-wait, guard-contract-fallback, ack/timeout and fail-closed
  cases still pass (real BusyBox PID 1 switch_root to loop-backed ext4).
- `test-pmos-boot-record.sh`, `test-pmos-self-stage.sh`,
  `test-pmos-radio-bringup.sh`, `test-pmos-pid1.sh`: pass, exit 0.
- Builder: two serial byte-identical builds; verifier `--self-test` (negative
  mutations) and final verifier pass; 87 refused image hashes.
- `shellcheck -S error scripts/pmos-self-post.sh`: clean; `sh -n` on both
  changed shell scripts: clean; `git diff --check`: clean.
- Not run: `test-pmos-pid1-request.sh` (stale pin, fails identically on clean
  main per the #265 record).

## Coordinator experiment (one boot, phase 2 of #275, standing approval)

Flash only `init_boot_a` with 2ebdf1db after the standing verified-backup,
rescue-hash and bounded-recovery gate; vendor_boot_b a71b3f5f and the stock
slot-A rescue images stay unchanged. Pre-arm the `:2222` capture before the
single reboot; no pid1-ack before the self-post window and no worker racing
the unacknowledged guard; no manual remoteproc/radio writes. The ~160 s no-ack
return is the designed host-reachable boundary; use the preverified
hardware-assisted fastboot path once if it fails, then stop and record.

Prediction: the nonce wait passes as in run 96, then kmsg shows
`self-post-trace: panel record restored from the boot kernel log`,
`record append exit` and `record verify exit`, and at least one radio stage
runs. Report exactly one of:

- (A) append succeeds and at least one radio stage (modem/wpss/driver/scan/
  services) runs: record how far the chain got and whether wlan0 appears;
- (B) a different named check refuses: quote the new
  `self-post-trace: append refusal check: …` kmsg line;
- (C) an earlier guard return or boot failure interrupts before the append:
  record the last trace line and the elapsed wait honestly;
- (D) the append succeeds but no radio stage runs: record the first refusing
  stage.

Not WLAN acceptance: that stays two fresh self-starting boots with
association, address, DNS and internet per PLAN.md. Scan alone is not
connectivity.
