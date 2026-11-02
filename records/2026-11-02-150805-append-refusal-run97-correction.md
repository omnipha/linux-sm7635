---
date: 2026-11-02
run: 97
issue: omnipha/linux-sm7635#275
subsystem: wlan
result: confirmed
supersedes: 2026-11-02-145742-append-refusal-ordered-sequence-check.md
---
# Run 97 correction: outcome B stands; the panel restore never fired, the nonce wait ran once, and the append failed 0.1 s before the diagnostic

Host-only independent re-read of
`~/phone-second-life-data/mb003/pstore/attempt-20261102-1550-append-refusal-run97/`
(not in git): `capture/kmsg.log` (172578 bytes, SHA-256
`4b2292afe9a995c64d41997c8e02640e643e9a075babbc14be90584a16775aee`),
`driver.log`, `verifier.txt`, `flash-init_boot_a.txt`, `session-hashes-pre.txt`,
`session-hashes-close.txt`, `session-close.txt`, `final-gate.txt`. No device
access. The merged record's outcome and integrity statements check out; three
statements are wrong or incomplete and are corrected here.

## Confirmed against the raw files

- Outcome (B): the one new kmsg line names the refusing check, verbatim at
  uptime 157.787 (kmsg 157786937): `append refusal check:
  boot_record_append: ordered sequence check, record plus new line is not a
  prefix of the expected lines; panel record file absent; record line 3 is a
  panel line yes`. Exactly one such line.
- Boot `1a64e6d8-e9b6-4c53-91bb-13ac8401f8f0`; one `flash init_boot_a:
  verified: ok` (driver.log, 14:46:11Z); the capture was armed before the
  `fastboot reboot` (14:46:16Z); handoff proven (`handoff: ok`, `/run/keep`
  root-only, pid1 `init`); no pid1-ack (the string is absent from kmsg).
- `session-hashes-pre/close`: stock `boot_a 197aff11…`, `vbmeta_a cc1926d2…`,
  `dtbo_a 759813db…`, `vendor_boot_a 23725940…` exact; installed `init_boot_a`
  2ebdf1db26193f7f0c3f4c6d42f722008bd1ee2718adf399dfe4927cc3eb9632 and
  `vendor_boot_b a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3`.
  `session close: ok`, `fastboot-gate: ok`; fastboot returned at ~280 s
  (14:51:51Z, driver.log).
- Trace lines: `pre/post check post-cutover contract rc=0`, `pre/post check
  panel record rc=0`, `record append entry rc=0`, state at append entry:
  guard `armed` = this boot id, `nonce` present 65 B, `accepted`/`ack` absent,
  `root-contract.sh` present 14807 B, guard dir 0:700, `/run/keep` present,
  `/run/pmos-root-contract.sh` absent. No modem/wpss/driver/scan/services
  trace or marker line follows the failure; the only `wlan0` line is the
  pre-SSH `wlan-init: wlan0 absent` at 1.72 s.

## Corrections

1. Nonce: the merged record says the nonce was "minted before the wait would
   have mattered". Raw: `guard nonce wait 0` at 156.558 means the nonce was
   ABSENT at the first check; the next line, `post check guard armed and
   unacknowledged`, is 157.562, one `sleep 1` later. Same as run 96 (correction
   2026-11-02-130607): the nonce appeared within about 1.0 s of the wait
   start; the exact mint instant is not observable at 1 s polling.
2. Timing: the append refusal is `FAIL: post-cutover boot record append
   refused` at 157.682 (kmsg 157681571), 0.104 s after `record append entry`
   (157.578). The naming line is at 157.787, 0.105 s LATER, emitted from
   `record_fail`. The merged record's "at uptime 157.78 the append refused"
   is the diagnostic time, not the refusal time.
3. Not stated before: the #276 panel restore did NOT fire. Between `pre check
   panel record` (157.568) and `post check panel record` (157.577) there is
   no `panel record restored from the boot kernel log` line (zero occurrences
   in the capture), so `/run/pmos-pre-ssh-panel.record` stayed absent and the
   ordered-sequence mismatch of run 96 persisted. The restore requires all of
   its conditions: this boot's kernel log contains the panel line
   (`usb-init: usb-init: pre-SSH panel … boot <id>`, present at kmsg line
   2390, uptime 1.498; the kernel ring is 1 MiB, and the capture itself shows
   the same line), a unique value, and equality with record line 3. The
   diagnostic names `record line 3 is a panel line yes`. Which restore
   condition failed is NOT measured: the restore has only a pre/post trace
   and no per-condition line. Candidates not decided here: guest BusyBox
   `dmesg` output not matching the pattern, the line absent from the guest
   ring at 157 s, a ring/format difference, or the line-3 equality. Host
   fixtures passed with the guest `/dev/kmsg` fixture, so a device-vs-fixture
   difference exists; its cause is unknown.

## Outcome and next single variable

Outcome (B) stands: the check refusing inside `boot_record_append` is named
(ordered-sequence check, panel record file absent, record line 3 a panel
line). The #276 hypothesis "restore the panel file from kmsg" is refuted as
implemented on the phone: the restore did not engage. Radio chain: still
unmeasured on the installed chain (no stage ran); not WLAN acceptance; single
boot only.

Next single variable (for the strategist/supervisor queue, not implemented
here): why the kmsg-attested panel restore did not engage in the guest, i.e.
the exact value and shape of what the guest `dmesg` returns for the panel line
versus the regex, versus record line 3 (host-reproducible from this capture's
line 2390 and the record content, which the capture does not contain). The
dossier's own fallback (post-ack radio start from a live session, run-69
recipe) stays the cheaper alternative named in docs/strategy/wlan.md.
