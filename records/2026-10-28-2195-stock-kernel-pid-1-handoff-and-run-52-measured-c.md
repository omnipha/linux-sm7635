---
date: 2026-10-28
run: 52
issue: omnipha/linux-sm7635#145
subsystem: userspace
result: confirmed
source: README.md
---
## Stock-kernel PID-1 handoff and run-52 measured cutover (2026-10-28, #145)

[BOOT.md](BOOT.md#run-52-measured-postmarketos-pid-1-cutover-and-usb-ssh-145-live-session-finding-2026-10-28)
records the run-52 measured cutover on candidate `fef03008…` (true postmarketOS
BusyBox/OpenRC PID 1 on the 256 MiB tmpfs root, guard acked on boot
`e956165d-c9ae-466e-9d1c-e2a76b00ad61`, strict-key USB `:2222` and live
post-cutover console capture; OpenRC `default` with 0 enabled services and
`remoteproc2`/`remoteproc3` left `offline`; coordinator stock rollback pending)
after [the run-51 rejected request](BOOT.md#run-51-measured-request-rejection-145-live-session-finding-2026-10-28);
[the successor design](BOOT.md#bounded-ram-backed-postmarketos-pid-1-handoff-145-successor-host-only-2026-10-28)
describes the `init_boot` candidate from the measured run-43 image:
PID 1 can accept a root-owned, boot-ID-bound request and SHA-pinned volatile
transition only after the old 150 s recovery child has settled. The 134-APK
public archive is staged on a distinct RAM tmpfs with separate private `/run`,
`/dev`, `/proc`, `/sys`, and key-only `:2222`. Before `switch_root` the new
160 s guard is armed independently of `/run/keep`; a strict-key host ack needs
actual new-root PID 1, boot identity, a live second SSH service and heartbeat.
The run-51 candidate `d90b2221…` was physically measured only as a rejected
request: its `/init` sampled `/run/keep` at console-tail entry, before the held
SSH session could create it. That image is refused. The successor builder
`build-init-boot-pid1-handoff.sh` serially reproduces the 8,388,608-byte image
`fef03008…` outside Git, with exact `/init` delta, header, stock-tail and
eager-hold negative checks; the request fixture starts with `/run/keep` absent.
`sh scripts/test-pmos-session-dev.sh`,
`sh scripts/test-pmos-pid1-request.sh` and `sh scripts/test-pmos-pid1.sh` are
isolated **host** fixtures (the x86 PID 1 is native BusyBox, aarch64 userspace
uses QEMU and recovery is mocked). They do **not** establish device PID 1,
AVB acceptance, cold boot, a physical guard result or stock rollback. Only the
coordinator can open a guarded session for #145; the worker continues on the
same issue after a proven handoff, and #145 remains OPEN until a measured
outcome and stock restore. No device operation is performed by these scripts.
