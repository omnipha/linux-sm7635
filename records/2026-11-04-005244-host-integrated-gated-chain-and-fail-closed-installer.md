---
date: 2026-11-04
run: 6
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# host integrated gated chain and fail closed installer

Host-only continuation of run 5 for issue #311: the full generated
self-post now runs inside the isolated guard fixture, and the
persistent-root builder carries and installs the reviewed gated chain
with fail-closed staging. No phone, USB, adb, fastboot, flash, reboot or
device ACK. Base `e5fa1dba12cca1ccc4978feae92e5ce25376c39b`.

## Combined full-post fixture

`scripts/test-pmos-success-gate-guard.sh` gained `full-success`,
`full-radio-fail` and `full-invalid`. The full cases execute the
canonical generated post (SHA-256
`113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3`)
derived in-suite from the builder staged radio base through the pinned
derivation chain, after replacing only its `BB=/bin/busybox` line with
the fixture tool path; the rewrite is asserted byte-exact and
reversible. PID 1, the real guard (watcher and `mock-arm`) and
`/bin/busybox` remain real; guard, ordered-record, nonce/ACK and marker
file operations pass through unchanged. Mocked boundaries are dmesg kmsg
replay (synthetic same-boot panel line, marker publication), rmtfs and
daemon process evidence, selected pinned hashes, `pidof`, `ping`, the
DNS probe answer (real probe bytes pinned, not executed) and the radio
stage invocations. The pinned fresh radio is present but its stages are
not executed in the combined fixture. `full-success` shows real guard
acceptance with nonce and ACK consumption and per-stage marker tokens;
both failure cases publish no readiness or ACK, leave the nonce intact
and reach mock recovery at the real deadline. The 40 prior gate/guard
cases also pass with the adapted fixture scaffolding.

## Builder carrier wiring and fail-closed installer

`build-init-boot-persistent-root.py` gained `runtime_scripts()`: it
derives the reviewed gated artifacts from the unchanged staged base
(radio `146ed592…`, post `113553dd…`, hook `3d317a69…`, DNS probe
`906a3c3f…`, all fail-closed pins) and routes the active
`pmos-radio-bringup.sh` carrier member and the self-stage `RADIO_SHA`
pin to the gated radio. The carrier bundle now carries the three gated
artifacts and no longer ships `pmos-self-post.sh` in the carrier. The
initramfs retains a traced diagnostic post with the older radio pin,
but the installer does not copy it into the guest or launch it. The ext4
self-stage splices `persistent_installer()`: after the session stage
promotes userdata, it rechecks `$GUEST` with the real root contract as
read-write userdata, verifies parent
directories and the payload directory, rejects nested mounts and any
chain parent or directory on a foreign device, rejects foreign
local.d `*.start` hooks (the stock `99-shutdown-pbsplash.stop` ships
in the pinned archive, runs only in the OpenRC `local` stop path and
is inert before the ACK), staging-path collisions, unpinned payloads
and untrusted existing files (any content that is not exactly the
pinned digest, including the legacy old-chain hook), then installs
each missing file by staging `0600`, re-verifying the staged digest,
hardening to `0700`, publishing with a no-replace hardlink
(`ln -T`, verified using the pinned run-66 initramfs BusyBox and the
postmarketOS archive BusyBox under QEMU), verifying both paths as the
same `0700` inode with link count two, then removing the staging name
and re-verifying the final single-link file. The session stage
hook check is now content-pinned (`0:0:700:1` plus the gated hook
digest), replacing the metadata-only acceptance. The parent gate permits
`0700`/`0755`, with `0775` only for `$GUEST/etc`: the pinned archive
and derived ext4 image actually use `0:0:0775` for `/etc`. The sourced
contract is checked as a regular, non-symlink file before use.

Decision recorded on the issue: an existing legacy hook is refused, not
silently migrated; the coordinator owns the one-time physical
replacement of any pre-existing hook before the first gated boot.

## Built and verified pair

Two serial locked builds under `build-init-boot-persistent-root.sh`
were byte-identical and passed the verifier self-test (88 refused image
hashes, negative mutations OK):

- `init_boot-root-contract-carrier.img` (8388608 bytes):
  `d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c`
- `vendor_boot_b-root-contract.img` (100663296 bytes):
  `221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500`
- cpio 3698176 bytes; LZ4 HC-12 frame 2105683/2117632 (gap 11949)

Outputs live outside Git in `~/sm7635-build/out`. Nothing was flashed.

## Host verification

- `sh scripts/test-pmos-success-gate-guard.sh` (all cases including the
  three full-post cases).
- `python3 -B scripts/test-derive-radio-persistent.py` (runtime overlay
  pins, runlevel reconciliation, legacy-hook and foreign-startup-hook
  refusals, installer fixture: atomic install, idempotence, read-only
  root, missing contract, dangling and valid-target contract symlinks,
  parent metadata including `0775` only for `/etc`, nested mounts,
  symlinks, hardlinks,
  staging collisions, publish races and unpinned payloads). The fixture
  models root/group ownership and device metadata via a `stat` wrapper,
  redirects mountinfo input, and stubs the root-contract call. Real mode,
  link-count, inode and digest operations underpin the checks; the two
  publish-race variants are injected. It is not a real mounted-userdata
  installer test.
- `test-derive-radio-fresh-boot.py`, `test-derive-success-gated-ack.py`,
  `test-derive-radio-postack.py`, `test-fresh-hook-exit-report.py`,
  `sh scripts/test-pmos-boot-record.sh`,
  `sh scripts/test-pmos-gate-evidence-contract.sh`,
  `sh scripts/test-pmos-radio-bringup.sh`.
- `ruff check --no-cache scripts/build-init-boot-persistent-root.py scripts/verify-init-boot-persistent-root.py scripts/test-derive-radio-persistent.py`
  and `mypy --check-untyped-defs` clean on the three touched Python
  files; `shellcheck -S error scripts/test-pmos-success-gate-guard.sh`,
  `sh -n`, `git diff --check`.
- Two locked serial builds byte-identical plus
  `verify-init-boot-persistent-root.py --self-test` and final verify.

## Limitations and physical acceptance

Host results are not physical WLAN proof. A BusyBox redirection in the
full-post fixture means the executed post differs from the installed
bytes by exactly that one line; the installed chain itself is
digest-pinned. Physical acceptance stays the binding two fresh
autonomous WLAN boots per `docs/strategy/wlan.md` and
`records/2026-11-03-203655-two-boot-planning-decision.md`, coordinator
owned: preflight, backup verification, installation of this pair,
legacy-hook/run-106 replacement check, rescue checks and measurement.
The untrusted run-106 radio (`d7b74c24…`) must never run.
