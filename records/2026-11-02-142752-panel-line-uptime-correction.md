---
date: 2026-11-02
issue: omnipha/linux-sm7635#275
subsystem: wlan
result: confirmed
supersedes: 2026-11-02-142315-host-append-refusal-reproduction.md
---
# Host correction: run-96 panel line was logged at uptime 1.475 s, not 14.74 s

Host-only re-read of the run-96 `capture/kmsg.log` in
`~/phone-second-life-data/mb003/pstore/attempt-20261102-1355-nonce-wait-run96/`.
The capture SHA-256 is recorded in the run-96 correction record. No device
access.

The sibling host-reproduction record says the panel line was logged at uptime
14.74 s. That is wrong: its kmsg timestamp is `1474870` microseconds, or
**1.474870 s**. The post-cutover append entry is timestamped `157515807`
microseconds, or 157.515807 s. The serialized capture contains 18,920 bytes
between the start of the panel message and the start of the append-entry
message, and one occurrence of the panel prefix.

This correction changes no result: run 96 did not instrument the internal
append refusal, the host fixture reproduces the ordered-sequence mismatch when
the panel file is absent, and the new image's kmsg-attested restore remains a
host-verified candidate. The kernel ring is not guaranteed to retain the
message on a later boot; if unavailable the restore fails closed and the
named append-refusal diagnostic remains the outcome. No WLAN acceptance or
radio-stage execution is claimed.
