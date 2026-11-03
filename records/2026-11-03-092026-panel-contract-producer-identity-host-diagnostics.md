---
date: 2026-11-03
issue: omnipha/linux-sm7635#301
subsystem: wlan
result: confirmed
---
# Host diagnostics: producer failure and pre-existing panel identity

Follow-up to the [panel format replay](2026-11-03-084931-panel-format-ordered-host-replay.md):
the same unprivileged synthetic BusyBox fixture tested two boundaries of the
pinned panel block and the in-memory T1 experiment against the actual ordered
record functions, with the same modeled root, ownership, boot source and sync.
These are observed host-model limitations, not device observations or claims
that guard, nonce, capture or success-gated ACK checks passed.

A synthetic `dmesg` producer was independently verified to emit its fixture
input and exit 23. With no output, both variants exit 1 before the panel
post-check; the separately invoked ordered append/verify refuses unchanged.
With a matching raw line before the error, both variants restore the panel and
the modeled contract appends/verifies: the pipeline's final `grep` masks the
producer status. With matching T1-prefixed output followed by error, only the
in-memory T1 experiment restores and appends; the original fails to match.
A failed producer's output is not valid independent evidence.

A separate synthetic current-boot pre-cutover record contains a foreign-boot
panel at line 3, with the identical foreign panel already present as a safe
regular temporary file. Both blocks skip the restore branch and do not invoke
`dmesg`; the unchanged `boot_record_lines` checks panel syntax and metadata,
but not its boot suffix. Under the modeled dependencies, append and verify
therefore succeed. The fixture explicitly checks the foreign suffix and labels
this as a limitation, not as accepted same-boot evidence. It does not establish
how that panel state could arise on a phone.

A future reviewed successor must evaluate producer status and pre-existing
panel identity, in addition to actual same-boot log format and mixed-format
conflicts, without weakening line-3 order, nonce, capture, guard or ACK gates.
This #301 investigation changes no production parser or guard. The separate
#294 physical acceptance and the retained-context handoff remain outstanding;
the [owner lifted the specific run-100 pstore hold](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6598398647)
after accepting possible loss, and the retained console is not a pstore pull.
No run-100 cause, pstore capture or WLAN success is inferred.

Host checks: `python3 -B scripts/test-derive-radio-fresh-boot.py`,
`ruff check --no-cache --ignore EXE001 scripts/test-derive-radio-fresh-boot.py`,
`mypy --cache-dir /dev/null --check-untyped-defs scripts/test-derive-radio-fresh-boot.py`,
and `git diff --check` passed. No phone, image, deployment, radio, real kernel
log, private capture, privileged namespace or device operation was used.
