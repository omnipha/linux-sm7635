---
date: 2026-11-03
run: 1
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# preack guard interlock host integration

Scope: host-only #311 integration against exact current sources. Real
unchanged guard plus additive marker, real generated gate, real ordered
boot-record contract; hardware, radio, network, panel log and DNS behavior
is simulated. This is not physical autonomous WLAN acceptance.

## Safety contract change

The unchanged guard accepted any correct current-nonce ACK before bookkeeping.
The new additive guard keeps every existing identity, timeout, recovery and
ACK check, and additionally requires a root-owned 0600 single-link
`/run/pid1-guard/success-ready` containing exactly `<nonce> <boot>\n`.
Readiness is compared against the guard-internal nonce/boot state, and the
guard re-verifies the real ordered record with the pinned root contract
before accepting.

A premature correct ACK without readiness enters recovery immediately and is
never accepted later if readiness appears afterwards. Ready, nonce and boot
values are never inferred across companion states. The guard no longer needs
a weaker caller and the updated rejection message reflects recovery as the
required outcome, not only deadline expiry.

The real generated gate publishes readiness only after radio, evidence,
services, association, address, route, gateway, Internet, DNS and final
health pass, plus re-verification of the pinned ordered boot record. Ready
and ACK use atomic no-replace publication, staged inode verification and
single-link commit. Competing ACK or readiness staging refuses the publisher.

## Ordered delivery

- OpenRC WLAN services are deferred pre-cutover so `wpa_supplicant` and
  `networking` cannot start before device-owned radio/helpers/profile are
  ready.
- The installed/radio persistent derivation recreates helpers and service
  checks on replay instead of accepting already-started services.
- Current derived artifact hashes:
  - generated success-gated post: `113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3`
  - generated hook: `3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67`
  - fresh radio input: `146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14`
  - fresh post input: `db82eb4b0efd2b5f94f4665e3ed2c4e766c488816862118bda773d74588695b0`
  - integrated toolchain uses session `69333abbc3efa21b451b73fd83f5a4ff694fe94502a36fa8d80ef024fb44e80e`
    and self-stage `16ec12565a1fcaf36515fb646fbbf3ab2d576ba90c6687611d9bd058dd43e412`.
- The run-106 altered radio remains untrusted and was not run or staged as a
  deployable candidate.

## Host evidence

Focused host fixtures, isolated and with mocked external evidence:

- `sh scripts/test-pmos-success-gate-guard.sh`: real guard, generated gate,
  real ordered-record contract; success and real-readiness acceptance; all
  premature/readiness/record/panel/contract/staging/recovery/deadline cases
  pass. The fixture states its synthetic panel/network/process evidence.
- `sh scripts/test-pmos-success-gated-ack.sh`: full generated artifact and all
  positive/negative/refusal/interruption/publication cases pass.
- `sh scripts/test-pmos-radio-bringup.sh`: host-only radio/openrc/profile
  coverage passes, including recreated helpers and replay/refusals.
- `python3 -B scripts/test-derive-success-gated-ack.py`: exact generated
  post/hook and DNS-parser safety pass.
- `python3 -B scripts/test-derive-radio-persistent.py`,
  `test-derive-radio-fresh-boot.py`, `test-derive-radio-postack.py`,
  `test-fresh-hook-exit-report.py`: derivation/panel boundaries pass.
- `sh scripts/test-pmos-boot-record.sh`: ordered rotation/remount/refusal
  cases pass.
- `sh scripts/test-pmos-gate-evidence-contract.sh`: real contract success
  verification and later-failure refusal pass.
- `ruff` (excluding historical EXE001 executable-bit state), the recorded strict
  derivation/generator shell syntax checks and `git diff --check` clean. New
  `mypy --check-untyped-defs` on the touched generator and test reports no
  issues; existing builder/verifier modules keep their prior annotations.

## Limitations

Host tests cannot establish physical association, address, DNS, Internet or
post-deadline WLAN stability on the target. Marker forgeability and evidence
capture remain inside the same root trust domain. Device measurement needs a
coordinator-controlled preflight, same-boot proofs, exact restoration of the
tested artifacts, backups/rescue and live capture; no device action was taken
here. One successful fresh autonomous WLAN boot is the corrected acceptance
target; a second boot needs a technical reason plus coordinator approval.
