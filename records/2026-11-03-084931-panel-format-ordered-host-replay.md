---
date: 2026-11-03
issue: omnipha/linux-sm7635#301
subsystem: wlan
result: confirmed
---
# Host replay: caller-prefixed panel and ordered record

The observed format limitation is confirmed on the host, not on run 100. The
coordinator reported a replay of a run-95 guest `dmesg` panel line, timestamp
plus `[T1]` caller, from an existing capture with SHA-256
`168043e3b1fec8bdfd94fad3b083c17529c47dbc7cc25a3d7c1533e0f38aef6e`
([#294 evidence](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6597114588)).
The capture is not committed or independently reread for this test. Run 95
itself stopped at the missing nonce, before panel restoration or append
([run-95 record](2026-11-02-085828-run95-preack-selfpost-guard-nonce-check.md)).

The deterministic fixture in `scripts/test-derive-radio-fresh-boot.py` uses
synthetic timestamps, payload and boot IDs. Its historic-format representative
and prefix-stripped control are:

```text
[    3.000000][    T1] usb-init: usb-init: pre-SSH panel node=boe card0=1 dsi1=1 dcs=none reset=none suspend=clear brightness=0 boot 11111111-2222-3333-4444-555555555555
usb-init: usb-init: pre-SSH panel node=boe card0=1 dsi1=1 dcs=none reset=none suspend=clear brightness=0 boot 11111111-2222-3333-4444-555555555555
```

These are format examples, not the historical line's actual timestamp, boot
identity or contents. The nested `usb-init:` tags model the display value
passed to the init logger. The fixture derives and verifies the exact #291
prefix SHA-256 `c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7`,
then extracts its panel block. The existing gate derivation test independently
reproduced the whole #294 gated post SHA-256
`9a8c40adce2f84d61e30fd49f6d0f3be5a08d3a57909e9335c3c02f2751ea97b`
and checked that the gated post starts with that exact prefix.

## Panel and ordered-record outcomes

The main cases construct a complete synthetic pre-cutover record by calling the
actual `boot_record_open`, `boot_record_append` and `boot_record_verify` with
the panel at line 3. Each removes the temporary panel file before running the
extracted parser in an unconditioned BusyBox `sh -eu` child. The dmesg-like
input supplies independent panel evidence; record line 3 is only an equality
check, not a substitute for that evidence. After the parser, the real contract
attempts and verifies the post-cutover append. For parser exits, a separate
contract attempt confirms refusal with the panel absent; that attempt is not
claimed to have been reached by the candidate.

| Synthetic input | Pinned candidate | T1-only experiment |
|---|---|---|
| Prefix-stripped same-boot control | Restored exact panel; ordered append and verify pass | Same |
| Timestamp plus adjacent T1 caller | Exits 1 before post-check; no restore; separate append and verify refuse unchanged | Restores exact panel; ordered append and verify pass |
| Foreign-boot-only or no panel | Exits before post-check; no restore; separate append and verify refuse unchanged | Same |
| Two distinct recognized same-boot panel values | Continues without restore; append and verify refuse unchanged | Same, including T1-prefixed conflicts |
| Two byte-identical recognized values | Restores and passes: `sort -u` counts one distinct value | Same, including T1-prefixed duplicates |
| Current-boot line differs from persistent line 3 | No restore; append and verify refuse unchanged | Same, including T1-prefixed input |
| Foreign persistent record identity | May restore the current-boot panel; ordered append and verify refuse unchanged | Same |
| Foreign plus valid current-boot line | Foreign line is filtered; the valid line restores and passes | Same for recognized formats |

The historical strategy's phrase "duplicate/conflicting" should not be read as
an observation that every duplicate is rejected: the pinned parser accepts
identical duplicates. It rejects distinct *recognized current-boot* values,
not every line that looks like a panel message. A valid raw line plus a
conflicting T1 line passes the pinned parser because the latter is ignored;
the experiment recognizes both and refuses. Conversely, a valid T1 line plus
a conflicting synthetic T2 line passes the experiment because T2 is ignored.
The latter is a limitation of the experiment, not evidence that T2 occurred on
the device. Malformed and unsupported caller-only cases fail closed; bad record
mode, a hard link, oversize, the tested short or non-hex boot IDs and out-of-order
append also refuse. Refusal assertions compare the record byte-for-byte before
and after. Other malformed boot IDs are not generally excluded: see the
[identity diagnostic](2026-11-03-093747-boot-id-shape-host-diagnostic.md).

[Follow-up host diagnostics](2026-11-03-092026-panel-contract-producer-identity-host-diagnostics.md)
identified two further pre-existing limits, not successful same-boot safety
checks: a producer failure can be masked after matching output, and a pre-existing
foreign-boot panel matching line 3 bypasses the restore branch. Neither finding
proves that this happened on a phone or that the guard ran.

## Experimental normalization and boundary

The fixture tests, **in memory only**, a one-assignment variant that recognizes
the existing formats plus an adjacent `[T1]` caller with leading spaces after
a timestamp, optionally preceded by the already-supported priority prefix.
The replacement changes no other bytes of the extracted block and leaves the
production derivation and #294 pins unchanged. Payload validation, current-boot
suffix, `sort -u`, line-3 equality, no-match `set -e` exit and safe panel file
checks remain as in the pinned block. A no-match-only change would not repair
the ordered append with a panel-at-line-3 record and absent panel file.

This is not a proposed installable successor. A T1-only test cannot establish
that all conflicting panel evidence in an actual later snapshot is recognized;
broadening the grammar without evidence would be speculative. Before deciding
on production parser behavior, the discriminator is the actual same-boot
`dmesg` status, formatting and retention at the restore boundary, panel-file
metadata and launcher identity, measured by the retained #294 context in a
coordinator-proven session. A successor also needs explicit handling of failed
producer status and pre-existing panel identity, in addition to any measured
caller formats and mixed-format conflicts, without weakening order or
interlocks. Changing the prefix would require an independently reviewed successor
and new #294 post/hook pins; the existing gate derivation refuses changed inputs.

## Verification and limits

Passed on the host:

- `python3 -B scripts/test-derive-radio-fresh-boot.py`
- `python3 -B scripts/test-derive-success-gated-ack.py`
- `ruff check --no-cache --ignore EXE001 scripts/test-derive-radio-fresh-boot.py`
- `mypy --cache-dir /dev/null --check-untyped-defs scripts/test-derive-radio-fresh-boot.py`
- `git diff --check`; repo and pinned agents `records.py` copies compare equal.

The unprivileged fixture uses temporary synthetic files and models boot-ID
input, `dmesg`, owner mapping, userdata/mount identity and `sync`; it executes
real BusyBox text processing and the unmodified contract's ordering, mode,
link and size checks. It does not establish mount identity, durability, race
safety, or runtime nonce, guard, capture or ACK behavior. It neither synthesizes
an ACK nor runs radio or the gate. The separate derivation test rebuilds and
checks the pinned gate and DNS parser in temporary files; it does not exercise
the candidate on a phone. Guard, nonce, capture and success-gated ACK source
and pins are unchanged, not newly proven by the panel fixture.

No phone, SSH, USB, image, deployment, boot, flash, radio action, or private
capture was used. The later run-100 guest snapshot, panel state and actual
launcher remain unknown ([run-100 record](2026-11-03-014728-run100-candidate-boot1-capture-boundary.md));
the replay is neither its proven cause nor a post-run pstore pull. After the
[run-101 preservation hold](2026-11-03-023259-run101-preboot-pstore-access-blocker.md),
the [owner accepted possible loss of uncopied run-100 pstore and lifted that hold](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6598398647);
the [coordinator confirmed the decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6598721435).
The retained host console is not pstore. The retained #294 context awaits a
coordinator-proven handoff after #301; #294 physical acceptance is unchanged.
No WLAN or fresh-boot success is claimed, and no public support claim changed.
