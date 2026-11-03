---
date: 2026-11-03
run: 5
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# gated chain host regeneration

Host artifact regeneration and fixture checks for issue #311.
Base: `e5fa1dba12cca1ccc4978feae92e5ce25376c39b` (`origin/main`).
No physical phone, USB, adb, fastboot, flash, reboot or device ACK.

## Builder integration gap

Source inspection of `build-init-boot-persistent-root.py::current_scripts()`
shows that it bundles the older staged radio (`f54b3372...`) and an ungated
post, not the generated gated radio, post and hook. The derived self-stage
preserves an existing root-owned `0700` hook based on metadata, not content,
or creates the older hook if absent. The derived session stage defers the two
WLAN runlevel links. None of this establishes that a current carrier installs
the reviewed chain, nor that a particular carrier is currently installed.
A final image/carrier pair and its builder/verifier self-test remain outstanding.
Do not install or boot this incomplete chain as a physical handoff.

## Host-derived candidate artifacts

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

All host test suites passed, with the fixture boundaries stated:
- `sh scripts/test-pmos-success-gated-ack.sh`: full generated post and hook
  tested under mocked external evidence **and a mocked guard**; passes all
  stage refusals, atomic no-replace publication, staged inode checks,
  single-link ACK, and same-boot replay refusal.
- `sh scripts/test-pmos-success-gate-guard.sh`: isolated ext4 loop-backed
  guest root; real guard and real contract; verifies that genuine readiness
  and ordered record allow acceptance, while premature ACK, tampered/missing
  records, and foreign nonces trigger recovery. This fixture executes only
  the **generated gate suffix**, not the full generated post; the preceding
  radio stages are not executed.
- `python3 -B scripts/test-derive-success-gated-ack.py`: exact derivation pins,
  compiler output validation, and native 62-packet DNS parser tests pass.
- `python3 -B scripts/test-derive-radio-persistent.py`,
  `python3 -B scripts/test-derive-radio-fresh-boot.py`,
  `python3 -B scripts/test-derive-radio-postack.py`,
  `python3 -B scripts/test-fresh-hook-exit-report.py`.
- `sh scripts/test-pmos-boot-record.sh`, `sh scripts/test-pmos-gate-evidence-contract.sh`.
- `ruff check --no-cache --ignore EXE001` and `mypy --check-untyped-defs` on
  the generator and its test; `shellcheck -S error` and `sh -n` on the two
  gate fixtures; `git diff --check`.

No single host fixture yet executes the full generated post together with the
real guard and the real ordered-record contract; the two above cover those
halves separately. Combining them faces a concrete obstacle: the generated
post's PID-1 identity check (`sha256sum /proc/1/exe` equal to
`sha256sum /bin/busybox`) requires the real guest BusyBox binary, while
mocking the radio/network evidence invoked through `$BB` requires wrapping
`/bin/busybox`; the real guard independently compares the same hashes, so a
wrapped BusyBox forces guard recovery. A combined fixture therefore needs a
different interception design (for example a private PATH-visible tool
directory that the post's prefix is derived to use, or a synthetic netns with
real `ping`), not a merge of the two existing harnesses. A real candidate
image/carrier pair from the final chain has not been built or verified on
this host. The installed builder still bundles the pre-cutover diagnostic
chain by design; the generated gated chain is installed onto the persistent
root by the coordinator.

## Limitations and physical acceptance

Host test passes are not physical WLAN proof. Physical acceptance remains
two fresh autonomous WLAN boots per `docs/strategy/wlan.md` and the binding
decision in `records/2026-11-03-203655-two-boot-planning-decision.md`.
The coordinator alone executes physical preflight, backup verification,
artifact installation, rescue checks, and measurement.
