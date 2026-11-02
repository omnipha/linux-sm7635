---
date: 2026-11-02
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: refuted
---
# Host-only success-gated ACK design; intact recovery/evidence contract refuted

Issue #294, base `8b031dba7bdb82cd5cd187050b62b24a6f0000ec`. No device, SSH,
USB, flash, image build or device ACK was performed. This is a design and host
fixture finding, not device proof or WLAN/lasting-boot acceptance. The intact
installed chain **cannot meet the issue's complete independent recovery and
failure-evidence requirements without an owner-reviewed redesign**. Do not
request the reviewed fresh-boot measurement yet. PLAN.md is unchanged.

## Measured #291 base and non-deployable derived artifacts

The input is the exact #291 chain: builder-staged radio `f54b3372…`, persistent
services derivation, fresh radio derivation and fresh self-post derivation.
The #294 generator requires the exact input hashes and leaves that entire
prefix byte-identical. It appends a bounded gate, pins both outputs in the
hook, and requires a newly built probe to match its recorded digest. The
output hook **unconditionally refuses launch pending owner review**, before
its pin checks or any self-post execution. Therefore these are host design
artifacts, not an installable unattended-ACK candidate.

| Artifact | SHA-256 |
|---|---|
| Unchanged #291 fresh radio | `a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21` |
| Unchanged #291 fresh self-post prefix | `c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7` |
| Derived #294 self-post plus gate | `9a8c40adce2f84d61e30fd49f6d0f3be5a08d3a57909e9335c3c02f2751ea97b` |
| Derived launch-refusing hook | `0d7a9cf5cf705d96a60ad00dd5d3e8e0daba5b6463ee68310591d781807d3ac7` |
| Embedded static AArch64 DNS probe (597840 bytes) | `906a3c3f3f5c7a666f394dff434604a4b6a6bf2d683d8e04e3d947316132fe97` |
| Unchanged real guard used in fixtures | `f72a68a4c3a0e9bb7e72aa88883dcc9087a684985f5af688e34ea13c0226d3ad` |
| Unchanged digest-pinned mock recovery helper | `e112e65f2e9a6dc28531b45eda218284e4afb152dc3a02b588f7a25255cce2d1` |

Generator: `scripts/derive-success-gated-ack.py`. The pinned probe was built
reproducibly twice with host `aarch64-linux-gnu-gcc` 15.2.0, static glibc,
`-Os -s -fno-ident -Wl,--build-id=none`. Compiler/linker/libc changes refuse
the build. Generator outputs must be new, distinct, non-alias files outside
the repository; input/output hard-link aliases and existing outputs refuse.

## Ordering and the real ACK protocol

1. The exact #291 self-post performs its boot/root/guard identity checks,
   ordered boot-record append/verify, and nonce-bound capture markers before
   `modem -> wpss -> driver -> scan -> services`. A nonzero radio stage stops
   the prefix before the appended gate. The installed radio still has the
   measured guard and capture interlocks; they are not relaxed. Its services
   early return is possible, so markers alone are not stage-success evidence.
2. Only after the prefix returns successfully, the gate creates a root-only
   one-shot `success-gate-294` directory in the same-boot `/run` tmpfs. It
   rereads the boot ID, PID 1/root identity, guard dir, armed file, and exact
   live 64-hex nonce; `accepted`, `ack`, the host staging path and the gate
   staging path must all be absent. The guard process is not changed.
3. The gate rechecks all five nonce-derived markers exactly once in a bounded
   protected kmsg snapshot, radio identities/state and process/service health,
   OpenRC runlevel and own-output/profile configuration, and the pinned radio.
4. Terminal checks, each bounded and with fresh guard revalidation, are:
   strict `iw dev wlan0 link` association; a sane non-tentative global wlan0
   IPv4 address; exactly one default route via wlan0; gateway ICMP bound to
   wlan0; `1.1.1.1` route and ICMP bound to wlan0; and a real A answer from
   the first resolver, routed via wlan0 and queried through a socket bound
   with `SO_BINDTODEVICE=wlan0`. Association, address and default route must
   remain unchanged during the final health check. These are explicit
   conservative checks, not a general Internet/unrestricted-network claim:
   single-packet ICMP, one IPv4 resolver and one direct A answer are the
   proposed probe policy. They may refuse a working multi-homed, filtered
   ICMP or local-resolver network; a private A answer is not sinkhole proof.
5. Only after every check succeeds, the gate writes `nonce boot-id` to a new
   root-only `0600` file in the guard directory. Atomic no-replace `ln` links
   it to `ack` (two links, which the guard cannot accept), verifies the same
   inode/content/live nonce, then removes the staging link. At this single
   unlink the ACK becomes valid single-link and **publication is the
   irreversible commit point**. A competing ACK is never overwritten.
6. The gate waits at most 15 seconds for the guard's own `accepted=boot-id`,
   absence of nonce/ACK, and matching file metadata. The guard alone accepts
   and consumes the nonce; the gate does not write `accepted`, alter its
   deadline or request recovery. A valid ACK is at most one per boot: the
   one-shot directory, atomic publication, nonce consumption and live guard
   checks all stop replay or concurrent publication.

The installed guard's actual acceptance predicate remains the content,
regular-file/mode/link/size, current nonce, boot ID and switched-root checks;
it does not independently know about radio success. This design supplies
that evidence only through the pinned persistent script and its own checks.
It cannot authenticate that publisher inside the existing guard, so the
coordinator must not run any competing host ACK during a future measurement.

## Evidence and every defined transition failure path

Root-only `0600`, single-link files in `success-gate-294` name the boot ID,
stage, result, phase and reason. `started` precedes checks; each
`nonce-and-radio-markers`, `radio-health`, `services`, `association`,
`address`, `route`, `gateway`, `internet`, `dns`, `final-health` and
`all-checks` pass creates `<stage>.ok`. Refusal creates `refusal` naming the
exact failed stage/reason. A best-effort kmsg line has the same fields.
`published.ok` is created only after single-link publication and
`accepted.ok` only after guard acceptance and nonce/ACK consumption. Phases
are `before-publication`, `publication-uncertain`,
`published-awaiting-guard`, and `guard-accepted`. Kmsg snapshots are capped
at 1048576 bytes; read errors, NUL, metadata changes, size overage and grep
errors refuse, with no giant `execve` argument. Oversize, read error and
fatal text before/after the 128 KiB argument limit are fixture-tested.

| Failure | Designed outcome and evidence |
|---|---|
| Any prefix guard, record, capture or radio-stage refusal | Prefix stops before gate/publication. Only the existing coarse self-post stage line is guaranteed by this design; see evidence blocker below. Live guard recovery remains independent. |
| Invalid/stale nonce, wrong boot/root/armed state, malformed or replayed marker | Refuse at `nonce-and-radio-markers`; no ACK publication. |
| Radio/process/service/config/profile/SSH/fatal-kmsg failure | Refuse at `radio-health` or `services` with exact check; no ACK. |
| Partial association/address/route or any failed ICMP/DNS/final recheck | Stop at the first named terminal check, create refusal file/kmsg, no ACK; do not substitute a BSS count or service status for success. |
| Replay, same-boot rerun, pre-existing/competing/stale ACK or staging path | One-shot or live guard check refuses; existing ACK/evidence is not overwritten. A fresh boot with an old nonce is rejected by the real guard through its deadline. |
| Interrupted before single-link publication | Traps record phase/reason where possible; no valid ACK is published. SIGKILL cannot guarantee a trap line, but incomplete state remains unaccepted by the intact guard. |
| Interrupted after single-link publication | The ACK may still be consumed. Evidence must say published/uncertain, never recovery. This is success-path commitment, not a failed radio path. |
| Guard acceptance wait times out or guard is late/dead | Gate reports `acceptance not confirmed; ACK may still be consumed`; it never invents acceptance or recovery. A healthy live guard at its own deadline still requests bootloader. A dead watcher cannot; see blocker. |

## Independent blockers requiring owner review

1. **Pre-guard recovery is not bounded.** The installed hook itself creates
   `/run/keep`, so the 150 s one-shot init timer no longer recovers; the
   independent 160 s guard is armed only around uptime 155 s. Self-stage
   failure/hang before that arm can leave diagnostic PID 1 indefinitely.
   Runs 72 and 83 measured refused transitions/staging remaining in the
   diagnostic system; run 51 measured a rejected handoff retaining it. A
   post-cutover gate cannot fix that pre-arm interval. Smallest redesign:
   keep the guest hold but add a separate, monotonic pre-arm watchdog that
   requests the pinned bootloader recovery unless a valid armed guard takes
   over, with fixtures for early/late arm and hold races. This executes
   before switch_root and needs a reviewed image/owner decision.
2. **The one userspace watcher is not supervised and its evidence is dropped.**
   Killing only the fixture's exact real watch after nonce mint produced no
   acceptance or mock bootloader request after its budget. A stalled watcher,
   helper return/identity change or kernel failure likewise has no independent
   fallback. `armed`/`nonce` do not prove liveness. Guard stderr, including
   deadline and recovery-return reasons, is redirected to `/dev/null`; the
   fixture's `recovery-request` file is not production evidence. Smallest
   redesign: independent supervisor plus explicit reason-coded recovery
   evidence to an authorized capture/persistent sink. Do not add another
   same-process watchdog. Owner must choose this safety guarantee versus
   explicitly accepting the existing healthy-kernel/live-watcher/helper
   assumption; host fixtures cannot establish device recovery universally.
3. **Post-radio refusal evidence is not durable in the installed contract.**
   The real `pmos-root-contract.sh` verifies the normal post-cutover success
   line but refuses a later `pmos-self-post: FAIL:` append, with or without
   the panel file. `record_fail` also lacks the guard-contract fallback. Gate
   `/run` files and kmsg are volatile/best-effort; reboot can erase them.
   Exact radio `fail()` stderr is suppressed by the null-redirected hook, so
   early stages currently expose only a coarse self-post stage failure.
   Smallest reviewed evidence redesign: bounded root-only same-boot failure
   records in an authorized persistent format with rotation, plus sanitized
   stage-qualified radio failure publication and guard reason logging. Do
   not append after the success line in the existing ordered record or bypass
   its verification. If volatile capture is accepted instead, the owner must
   explicitly relax durable-every-path evidence, not the recovery guard.

Additional explicit limits: a clean bounded dmesg read cannot reveal fatal
messages already overwritten by kernel-ring wrap, and this BusyBox interface
provides no reliable short-read/truncation indicator. The gate's check of the
surviving snapshot is therefore not proof that no earlier fatal occurred.
The deadline is checked at the start of each guard iteration, not immediately
before acceptance; strict exclusion of every ACK crossing that boundary would
require changing the guard's acceptance-time check. No host fixture here
claims that the within-iteration device race is resolved.

## Host verification and measurement decision

All passed on 2026-11-02:
`python3 -B scripts/test-derive-success-gated-ack.py`,
`sh scripts/test-pmos-success-gated-ack.sh`,
`sh scripts/test-pmos-success-gate-guard.sh`,
`python3 -B scripts/test-success-gate-dns.py`, and
`sh scripts/test-pmos-gate-evidence-contract.sh`. They exercise the exact
prefix and generated gate, success/partial/refusal, invalid/replayed/late,
one-shot/retry, competing publishers, six interruption boundaries, real guard
success and mock deadline recovery, real dead-watcher behavior, and possible
post-publication acceptance after publisher interruption. The actual AArch64
probe ran under QEMU in a private dummy-wlan0 network namespace: valid UDP,
25 valid/malformed/refused responses, wrong source address/port, device bind
and a 4.03 s timeout passed, with no external packets. Native parser checks
passed two valid and 60 malformed packets. The real evidence-contract fixture
confirmed post-success refusal. These are host mocks/emulation, not physical
radio, device recovery or autonomous boot proof.

Existing fixtures also passed: fresh/persistent/postack derivations,
fresh-post, radio-bringup, all six pid1 guard cases, self-stage, boot-record,
session-dev stage-only, root-contract, wlan lease and preboot capture model.
Shell `sh -n`, `shellcheck -S error`, Ruff, mypy and `git diff --check` passed.
The historical `test-pmos-pid1-request.sh` stale pin was not changed or used
as evidence.

A fresh-boot measurement of this gate **must not be requested now**. Although
the persistent-root script paths could carry it without a new pinned image,
the hook deliberately refuses launch because the full #294 recovery/evidence
acceptance cannot be met by the intact installed chain. The owner must first
choose and review the pre-arm supervisor, watcher supervision/evidence and
post-success failure-evidence trade-offs above; the pre-arm supervisor and
strict deadline acceptance would require a changed reviewed image. Do not
silently install the host gate, use the host ACK path, or run the closed #293
brief-unacknowledged-boot experiment as a substitute.
