---
date: 2026-10-27
issue: omnipha/linux-sm7635#142
subsystem: usb
result: inconclusive
source: README.md
---
## Isolated guest device and PTY host fixture (2026-10-27, #142)

`scripts/pmos-session-stage.sh` now mounts a guest-only RAM tmpfs for `/dev`, creates
and verifies minimal character nodes (including guest-local `tty`), and mounts a
private `devpts` with `/dev/ptmx` linked to its instance. It never binds the
diagnostic `/dev`. Teardown checks mount types and filesystem identities, refuses
unknown/live nested mounts, and unmounts in reverse order. Run
`scripts/test-pmos-session-dev.sh` on a host with passwordless sudo for an
isolated mount/PID/network namespace and the pinned public userspace archive:
the fixture covers fresh and partial/failed stage, missing/wrong nodes, a
shared-`/dev` negative case, unchanged diagnostic service and device nodes, and
both key-only non-PTY commands and `ssh -tt` in the staged userland. This is a
**host PTY result only**. Run 49/#139 closed after verified five-partition stock
rollback; the on-device `ssh -tt` defect remains unmeasured. A new device-side
result requires a separately coordinator-proven held session and rollback; see
[BOOT.md](BOOT.md#isolated-guest-dev-and-host-only-pty-fixture-142-2026-10-27).
