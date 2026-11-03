---
date: 2026-11-03
run: 5
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# gated chain host regeneration

Host integration confirmation and artifact validation for issue #311.
Base: `e5fa1dba12cca1ccc4978feae92e5ce25376c39b` (`origin/main`).
No physical phone, USB, adb, fastboot, flash, reboot or device ACK.

## Chain integration and installed carrier compatibility

The repository builder `current_scripts()` in `build-init-boot-persistent-root.py`
bundles the pre-cutover diagnostic chain:
- Staged radio (`f54b3372...`), leased helper pin (`1fbf50af...`), and
  pre-cutover preparation.
- Persistent root staging in `pmos-self-stage.sh` and `pmos-session-stage.sh`
  which:
  1. Mounts the persistent ext4 userdata filesystem from `/dev/block/sda13`.
  2. Verifies the persistent root contract.
  3. Inspects `/etc/local.d/10-omnipha-self-stage.start`: when present as a
     root-owned, regular, non-symlink `0700` file, it is preserved unchanged;
     only when absent does it generate the fallback diagnostic hook.
  4. Defers persistent OpenRC `wpa_supplicant` and `networking` runlevel
     symlinks so they cannot start before the device-owned helper.
  5. Places the protected WLAN profile into `/run/radio-bringup/wpa_supplicant.conf`
     as root-only `0600`.
  6. Arms the PID 1 transition guard with root contract verification before
     `switch_root`.

On unit `mb003`, the carrier `vendor_boot_b` (`a71b3f5f...`) and `init_boot_a`
are already flashed ("never-reflash" policy). The successor WLAN chain does not
require building or flashing a new image pair; it is installed onto the
persistent ext4 userdata filesystem by the coordinator.

## Candidate artifacts for coordinator installation

The candidate files were generated reproducibly without private inputs:
- `/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh` (29,356 bytes):
  SHA-256 `146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14`
- `/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh` (846,492 bytes):
  SHA-256 `113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3`
- `/etc/local.d/10-omnipha-self-stage.start` (899 bytes):
  SHA-256 `3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67`
- Embedded static AArch64 DNS probe (597,840 bytes):
  SHA-256 `906a3c3f3f5c7a666f394dff434604a4b6a6bf2d683d8e04e3d947316132fe97`

These files are staged in `/tmp/opencode/issue-311-handoff/`.
The untrusted run-106 radio (`d7b74c24...`) on the phone must be replaced
with the reviewed `146ed592...` radio; the hook and post must also be
installed to establish the full success-gated chain with `success-ready`
and real ordered-record verification.

## Host verification

All host test suites passed:
- `sh scripts/test-pmos-success-gated-ack.sh`: full generated post and hook
  tested under mocked external evidence; passes all stage refusals,
  atomic no-replace publication, staged inode checks, single-link ACK,
  and same-boot replay refusal.
- `sh scripts/test-pmos-success-gate-guard.sh`: isolated ext4 loop-backed
  guest root; real guard and real contract; verifies that genuine
  readiness and ordered record allow acceptance, while premature ACK,
  tampered/missing records, and foreign nonces trigger recovery.
- `python3 -B scripts/test-derive-success-gated-ack.py`: exact derivation pins,
  compiler output validation, and native 62-packet DNS parser tests pass.
- `python3 -B scripts/test-derive-radio-persistent.py`,
  `python3 -B scripts/test-derive-radio-fresh-boot.py`,
  `python3 -B scripts/test-derive-radio-postack.py`,
  `python3 -B scripts/test-fresh-hook-exit-report.py`.
- `sh scripts/test-pmos-boot-record.sh`, `sh scripts/test-pmos-gate-evidence-contract.sh`.

## Limitations and physical acceptance

Host test passes are not physical WLAN proof. Physical acceptance remains
two fresh autonomous WLAN boots per `docs/strategy/wlan.md` and the binding
decision in `records/2026-11-03-203655-two-boot-planning-decision.md`.
The coordinator alone executes physical preflight, backup verification,
artifact installation, rescue checks, and measurement.
