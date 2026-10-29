---
date: 2026-10-26
run: 43
issue: omnipha/linux-sm7635#130
subsystem: boot
result: inconclusive
source: README.md
---
## Current run-43 image reuse handoff (2026-10-26, #130)

[BOOT.md](BOOT.md) records a read-only recheck of the measured run-43 image
(`0f998e29…`, 8,388,608 bytes). Under the current device-op rule this is the
sole reusable changed image from the newest boot that reached key-only SSH;
#127's run-44 one-use/never-reflash language below is historical, and run 44
aborted before any partition write. The physical coordinator owns exactly one
session and one attempt through `device-op.py flash` on `init_boot_a` only, with
normal preflight and verifier hooks; no force or ledger edit. Every older
measured SHA remains refused. No new image, SHA, kernel, config, module or timer
change. #130 stays open until the coordinator records the measurement and stock
rollback; this host handoff claims no device result.
