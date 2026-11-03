---
date: 2026-11-03
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: confirmed
---
# Host candidate for the measured caller-prefixed panel boundary

The [run-101 record](2026-11-03-104136-run101-panel-parser-live-boundary.md)
measured a caller-prefixed same-boot panel line that the installed candidate's
parser did not match. This successor is a host-tested correction, not a device
result, not proof of run 100's cause and not a WLAN pass. It does not use the
previous #301 experimental parser. The coordinator closed run 101 after its
unacknowledged guard deadline with rescue verified.

## Scope and safety

`derive-success-gated-ack.py` still requires the exact #291 post and radio
hashes before replacing exactly one panel block. All other prefix bytes and the
gate suffix remain unchanged; the generated hook pins the successor post and
unchanged radio before detached launch. The parser recognizes the observed
priority/timestamp/caller shape and existing no-caller forms. It validates the
canonical lowercase boot-ID shape, requires the snapshot producer and every
pipeline stage to succeed, collects panel-like lines before identity filtering,
requires one distinct normalized line, requires its literal current-boot suffix
and exact equality to ordered record line 3, and preserves exclusive creation,
root-only mode and link checks. A pre-existing panel must independently match
the same successful snapshot and record and have exact safe metadata. Missing,
foreign, conflicting, malformed, unsupported or unsafe evidence refuses before
radio and ACK. Identical copies of the same normalized line remain acceptable.
The unchanged ordered record is still appended and verified after this block;
record line 3 alone is not used as independent panel proof.

An independent host review identified that an earlier in-progress revision
filtered foreign lines before uniqueness, allowing mixed current/foreign
panels. The final candidate collects panel-like lines first; a dedicated fixture
now refuses a current plus foreign boot line before radio or ACK. It also
refuses a mixed unsupported-prefix line rather than silently discarding it.
This conservative policy may refuse benign stale or unusual panel lines; that
is a fail-closed availability limit, not a claim of complete kernel-log history.
BusyBox `dmesg` may return a truncated but successful snapshot without a
truncation indicator; the guard and gate retain their prior bounded evidence
limitations. The candidate does not change recovery before arming, watcher or
kernel failure behavior, deadline races, or the ability of a published ACK to
be accepted after its publisher is interrupted.

## Generated artifacts

No image or private input was used. The following files are in the ephemeral,
mode-`0700` host directory `/tmp/opencode/issue-294-run101.qmsuncag`; each is
host mode `0600`. Re-hash before use or reproduce from the merged source with
`python3 -B scripts/test-derive-success-gated-ack.py <new-empty-external-dir>`.

| File | SHA-256 |
|---|---|
| `radio` | `a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21` |
| `post` | `9f0adb6618524c142f84dee13ffe9871d71fec19653b8c3def8e893ed0ec102f` |
| `hook` | `64c3ffdb483d9746432ef5ffafc13979e6fed420d89c6086186907f013f6477b` |

The coordinator alone may install the reviewed files under existing backup,
rescue and capture procedures: respectively
`/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh`,
`/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh`, and
`/etc/local.d/10-omnipha-self-stage.start`, as root-owned, regular,
non-symlink `0700` files. Backups must remain outside the `*.start` inventory.
Verify destination hashes and private profile equality without disclosing the
profile. The installed persistent-root paths support this successor in principle;
no new image is required merely for the parser change.

## Host verification

Passed:

- `python3 -B scripts/test-derive-success-gated-ack.py` verifies exact input
  pins, one-block replacement, unchanged gate, DNS pin and unsafe-output refusals.
- `sh scripts/test-pmos-success-gated-ack.sh` executes the generated post and
  hook with mocked external evidence. Caller-prefixed restore and identical
  mixed-format lines reach synthetic ACK; no-match, failed/partial producer,
  foreign-only, current-plus-foreign, unsupported mixed prefix, conflicting
  same-boot values, record mismatch, unsafe pre-existing panel and malformed
  boot ID refuse before radio and ACK. Existing stage, pin, nonce, network,
  publication, interruption and replay negatives pass.
- `sh scripts/test-pmos-success-gate-guard.sh` runs the unchanged real guard
  with the exact generated gate suffix and mocked external evidence, including
  early interruption, post-publication interruption and dead watcher.
- `python3 -B scripts/test-success-gate-dns.py` runs the pinned AArch64 probe
  under QEMU in an isolated network namespace;
  `sh scripts/test-pmos-gate-evidence-contract.sh` confirms the existing real
  record contract still refuses failure lines after success.
- Fresh derivation, hook-exit report, radio persistent/post-ACK derivations,
  fresh post, radio bring-up, PID 1, self-stage, boot record, session stage,
  root contract, lease helper and preboot handoff host regressions passed.
  Shell syntax, `shellcheck -S error`, Ruff, mypy and `git diff --check` passed.

These fixtures use synthetic logs, mocked radio/network and, in the combined
post fixture, a mocked record contract; the separate real-contract fixture does
not prove the entire phone chain. They do not prove recovery, WLAN association,
address, DNS, internet, guard acceptance or a lasting boot on the device.

## Coordinator measurement

Use the existing preflight, backup, capture/selftest and recovery procedures.
No host-run radio recipe or competing host ACK is permitted during measurement.
Record panel restore, ordered append, radio stages, association, address, DNS,
internet, real guard acceptance and Linux beyond the deadline separately. A
second fresh boot is allowed only after the first passes and is safely closed
or handed off. Continue the same issue after a proven live handoff; two fresh
self-starting WLAN passes remain outstanding and #294 must remain open.
