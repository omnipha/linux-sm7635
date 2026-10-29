---
date: 2026-10-27
issue: omnipha/linux-sm7635#142
subsystem: usb
result: inconclusive
source: BOOT.md
---
## Isolated guest /dev and host-only PTY fixture (#142, 2026-10-27)

Run 49/#139 is **CLOSED** after the coordinator's verified five-partition stock
rollback. [PR #141](https://github.com/omnipha/linux-sm7635/pull/141)
records the measured RAM-backed postmarketOS network and key-only **non-PTY**
SSH success, not an interactive terminal: `ssh -tt` failed and a trial `/dev/tty`
creation leaked into the shared diagnostic `/dev` before it was reverted. The
historical run-49 staging instructions below describe the original bind mount,
not the revised script or a new device session.

For #142, the staging script binds only `/proc` and `/sys`; a fresh 1 MiB guest
`/dev` tmpfs supplies verified character nodes `null` (1:3), `zero` (1:5),
`random` (1:8), `urandom` (1:9), `tty` (5:0), and `devpts` mounted with
`newinstance,ptmxmode=0666`. A guest-local `ptmx -> pts/ptmx` points to the
private instance rather than the legacy diagnostic 5:2 node. Missing or wrong
nodes and mismatched mount identities abort staging without a fallback to
outer `/dev`. Teardown refuses shared or unexpected mounts and a live nested
mount, unmounts `dev/pts`, `dev`, `sys`, `proc` in reverse order, and leaves the
diagnostic PID 1, `:22`, gadget and `/run/keep` untouched. A failed stage is
recovered with teardown, not by retrying over partial mounts.

`scripts/test-pmos-session-dev.sh` runs in a host-only private mount/PID/network
namespace with a synthetic diagnostic `:22`, synthetic SSH keys, the hash-pinned
public postmarketOS transport and loopback `172.16.42.2`. It checks fresh and
failed/partial staging, wrong/missing nodes, a shared-`/dev` regression, negative
leakage into diagnostic `/dev`, reverse teardown and live nested-mount refusal.
The real staged Dropbear passes both strict-key non-PTY SSH commands and a forced
`ssh -tt` with a guest slave and `/dev/tty`. This **host fixture** is not evidence
of a device PTY result. There is no new image or physical session for #142.

A future device-side measurement is a separate coordinator-owned session, not an
extension or reopening of run 49. After independently proving a new held boot,
pinned diagnostic key-only SSH, capture, RAM and `/run/keep`, the coordinator
could hand off the two hash-checked scripts and pinned public archive for one
bounded RAM-only stage. Check diagnostic `/dev` before/after, a non-PTY key-only
command first, then one `ssh -tt` with guest `/dev/tty` and `pts` readback; on
any failure, stop, tear down guest mounts in reverse order, and retain the
original diagnostic service. The coordinator alone would close the session
with evidence preservation and verified stock rollback. This is only a plan;
no permission to operate a phone or PTY success on the phone is claimed.
