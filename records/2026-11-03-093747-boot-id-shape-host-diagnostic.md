---
date: 2026-11-03
issue: omnipha/linux-sm7635#301
subsystem: wlan
result: confirmed
---
# Host diagnostic: boot ID shape check

Review of the [panel fixture](2026-11-03-084931-panel-format-ordered-host-replay.md)
found that the unchanged `boot_record_id` shell pattern checks expected separator
positions and a hex-or-hyphen character set, but does not forbid extra hyphens
in its wildcard positions. With a synthetic boot-ID input, the host fixture
confirmed that the real function rejects the tested short and non-hex strings,
but accepts `11111111-2222-3333-4444-55555555555-`. This malformed example is
not a valid boot identity; the test records a limitation, not a successful
identity check. The contract function ran only with a synthetic boot source;
the production source was unchanged and no guard or phone ran. No evidence
shows that a kernel boot ID had this malformed shape.

The focused #301 fixture uses synthetic temporary files and models boot source,
root/mount identity, ownership and sync. This finding does not change the
separately documented same-boot panel matching, physical hold decision, run-100
uncertainty or outstanding #294 acceptance. A later reviewed successor should
not infer complete boot-ID validation from the shape check alone.
