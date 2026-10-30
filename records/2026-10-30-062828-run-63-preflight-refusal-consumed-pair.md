---
date: 2026-10-30
issue: omnipha/linux-sm7635#184
subsystem: userspace
result: inconclusive
---
# Run 63: preflight refusal; no distinct SHA pair, no physical attempt

Operator retry 2026-10-30 07:20 Europe/Berlin after the overnight stall. The
stall was host-side: the handoff was already acknowledged, so no new event
fired; the phone itself is responsive again.

Measured preflight, no write:

- USB `18d1:4e11`, ADB `00181152O003821`, A059P, stock Android slot `_a`,
  `sys.boot_completed=1`, unlocked/orange. `device-op.py adb-check` ok; the
  earlier adb-check failures were a stopped adb server, not a device fault.
  No fastboot device.
- `sh scripts/test-pmos-reboot-hold.sh`, `sh scripts/test-pmos-self-stage.sh`,
  `sh scripts/test-pmos-pid1.sh` and `sh scripts/test-usb-readdress.sh` all
  pass on main `eee4304f6af8ebe7e0bd09ffaa95804a7ed21ae1` (PR #185 merged).
- Backup manifests `parts-a.sha256` and `parts-b.sha256` all verify.
- Run-62 stock rollback remains verified; no new rollback was needed or run.

Stop condition of #184 is met. The only staged pair in the build output
directory is exactly the run-62 pair, confirmed by SHA-256 on disk:
`init_boot-self-stage-userdata.img` `fcb0ed91c83461be1f22df859c2f9b331e72d31a576fcf33876de6c3136c2e0d`
and `userdata-userspace.img`
`ea09444c0ddde87e970d0b27cb8c067a28424da6501eed88bca749729855d4ed`.
Both are in the never-reflash ledger, and #184 forbids reflashing a
byte-identical rebuild and forbids adding a marker to obtain a SHA. No new
candidate image exists, so no flash was attempted, no partition changed, no
reboot and no live session.

Consequence: the hold question cannot be measured under the current
never-reflash constraint without a new image pair, which #184 does not
authorize. The next in-scope step is a host-side artifact source: build the
same self-stage init and deterministic archive from the pinned 23,713,302-byte
archive (SHA-256 `7a76a110...`) and offer the resulting pair through the
artifact gate; if it is byte-identical again, report that as the stop. No
marker-only rebuild, no force override, no additional worker.

Recorded via `device-op.py event` on mb003. No device raw data in this record.
