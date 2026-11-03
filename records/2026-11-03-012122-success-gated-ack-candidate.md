---
date: 2026-11-03
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: inconclusive
---
# Host-tested success-gated ACK candidate; two device boots remain

Issue #294, base `11095930a38932a698eca6ae70be09f3c4ded35a`. The owner chose the
minimal measurable path in the later #294 decision: use the existing same-boot
guard only after WLAN connectivity succeeds, accepting the existing recovery and
evidence limits. That decision supersedes the stop direction, not the findings,
in `2026-11-02-225455-success-gated-ack-owner-review-blockers.md`. No device,
SSH, USB, image build, flash, reboot or device ACK was used here. Host fixtures
are not autonomous-WLAN, physical recovery or lasting-boot proof; the two-boot
PLAN check and issue remain open.

## Candidate and ordering

The generator keeps the exact #291 radio and self-post prefix. The former
launch-refusing hook now checks both persistent script hashes, root ownership,
mode `0700`, regular-file and non-symlink status, then launches the gated post
asynchronously using the existing local.d/setsid mechanism. The prefix retains
its boot/root/guard, ordered boot-record, live nonce and per-stage capture
marker checks, and stops on any unsuccessful `modem -> wpss -> driver -> scan
-> services` stage. No competing host ACK is allowed: it consumes the nonce
needed by the pre-ACK chain.

Only after the prefix returns, the gate checks the same-boot nonce-bound
markers, radio and service health, protected matching WLAN profile, association,
global IPv4 address, one WLAN default route, WLAN-bound gateway and internet
ICMP, and interface-bound DNS. It then rechecks association, address, route and
health. It publishes no ACK on a prior refusal. Its one-shot directory and
repeated identity/nonce checks remain in force. After `all-checks.ok`, it stages
the real `nonce boot-id`, links it without replacement, verifies the linked
inode and guard state, then unlinks the staging name: the resulting single-link
ACK is the irreversible publication point. The unchanged guard alone accepts
it and consumes nonce/ACK. The candidate reports acceptance only after
observing the guard's real accepted file and consumption.

The gate records root-only same-boot stage successes and a refusal reason under
`/run/radio-bringup/success-gate-294`, plus best-effort kmsg lines. Prefix
failures retain the existing coarser evidence. `publication-uncertain` and
`published-awaiting-guard` alone do not prove whether the unlink happened;
inspect the actual link state, `published.ok`, and real guard acceptance. A
pre-publication interruption has no valid candidate ACK; after publication a
valid ACK may still be accepted even if its publisher is interrupted. Missing
acceptance is not evidence of recovery.

## Reproduced artifacts

These files were generated with no private input in the mode-`0700` external
host directory `/tmp/opencode/issue-294-candidate.8sFIsq0J`; the three handoff
files are mode `0600` on the host. The directory is ephemeral and private to the
host user, not a published artifact or backup. The probe was built twice by
`aarch64-linux-gnu-gcc` and required to match its pinned size and digest.

| Artifact | SHA-256 |
|---|---|
| Builder-staged radio | `f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f` |
| Persistent-services radio | `c54c29e1278827bc00faaf506c7ff8e923a8a689a011a2852d5d4b7778d0188d` |
| `fresh-radio.sh` | `a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21` |
| #291 self-post prefix | `c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7` |
| `gated-post.sh` | `9a8c40adce2f84d61e30fd49f6d0f3be5a08d3a57909e9335c3c02f2751ea97b` |
| `gated-hook.sh` | `ac3593d92ab12874caa6f1e5d2dd22b15689ff5244e75a445d5f6ab8c29f830f` |
| Embedded static AArch64 DNS probe | `906a3c3f3f5c7a666f394dff434604a4b6a6bf2d683d8e04e3d947316132fe97` |
| Unchanged real guard used in fixtures | `f72a68a4c3a0e9bb7e72aa88883dcc9087a684985f5af688e34ea13c0226d3ad` |

The gated post is byte-identical to the prior host-only design. The hook is
not: the prior `0d7a9cf5...` hook deliberately refused launch and must not be
used for this experiment. The installed persistent-root staging code permits
exactly the existing local.d hook path and preserves it, so the candidate is
installable in principle without a new init_boot or vendor_boot; no actual
installation or fresh-boot compatibility has been measured.

If the ephemeral artifacts are unavailable, reproduce from the merged
candidate source, on a host with the pinned AArch64 compiler output, with:

```sh
umask 077
D=$(mktemp -d /tmp/opencode/issue-294-reproduce.XXXXXXXX)
python3 -B scripts/test-derive-success-gated-ack.py "$D"
sha256sum "$D/radio" "$D/post" "$D/hook"
```

These files correspond respectively to `fresh-radio.sh`, `gated-post.sh`, and
`gated-hook.sh` above; refuse a hash mismatch. The fixture also creates
synthetic test files in that directory and does not access the private profile.

## Host verification

All passed on 2026-11-03:

- `python3 -B scripts/test-derive-success-gated-ack.py`
- `sh scripts/test-pmos-success-gated-ack.sh`
- `sh scripts/test-pmos-success-gate-guard.sh`
- `python3 -B scripts/test-success-gate-dns.py`
- `sh scripts/test-pmos-gate-evidence-contract.sh`
- `python3 -B scripts/test-derive-radio-fresh-boot.py`,
  `python3 -B scripts/test-derive-radio-persistent.py`,
  `python3 -B scripts/test-derive-radio-postack.py`
- `sh scripts/test-pmos-fresh-post.sh`, `sh scripts/test-pmos-radio-bringup.sh`,
  `sh scripts/test-pmos-pid1.sh`, `sh scripts/test-pmos-self-stage.sh`,
  `sh scripts/test-pmos-boot-record.sh`,
  `sh scripts/test-pmos-session-dev.sh --stage-only`,
  `sh scripts/test-pmos-root-contract.sh`, `sh scripts/test-wlan-udhcpc-lease.sh`,
  and `python3 -B scripts/verify-preboot-capture-handoff.py`
- `sh -n scripts/test-pmos-success-gated-ack.sh scripts/test-pmos-radio-bringup.sh`,
  `shellcheck -S error scripts/test-pmos-success-gated-ack.sh scripts/test-pmos-radio-bringup.sh`,
  `ruff check --no-cache scripts/derive-success-gated-ack.py scripts/test-derive-success-gated-ack.py`,
  `mypy --cache-dir /dev/null --check-untyped-defs scripts/derive-success-gated-ack.py scripts/test-derive-success-gated-ack.py`,
  and `git diff --check`. The generated radio, post and hook also passed `sh -n`.

The host policy-script comparison found pre-existing drift in the separate
`init_device` template validation only; no `new`, `index` or `check` change was
needed for this issue. Both repository and agents record checkers are run for
delivery. No `ports` public claim changed, so no device.yaml PR is warranted.

The hook fixture executes the generated hook and post with synthetic radio,
network and guard evidence: asynchronous launch, missing/changed/wrong-mode or
symlinked pins, all five prefix failures, terminal connectivity failures, and
one synthetic accepted ACK. Other cases cover guard/nonce changes, replay,
competing publication, TERM at six publication boundaries and post-publication
uncertainty. A separate isolated fixture combines the gate suffix with the
unchanged real guard and a mock recovery helper: no ACK at deadline requests
mock recovery when the watcher is healthy; a killed watcher does not. A valid
single-link ACK may be accepted after its publisher is interrupted. The AArch64
DNS probe executes under QEMU in a private network namespace; the real ordered
record contract fixture confirms post-success failure append refusal. These do
not combine real phone radio, OpenRC, guard, network and capture.

An additional fixture runs the exact #291 radio services stage with mocked
OpenRC and synthetic inputs over simulated boot resets. Retained persistent
config and failed/stopped services recreate volatile wrappers and start
supplicant before networking in that model. If both services are reported
already started, the existing early return leaves absent wrappers absent; the
separate gate fixture refuses each missing helper before ACK. This is a
potential fresh-boot refusal, not a demonstrated physical outcome. OpenRC may
start enabled services before local starts the radio; actual recovery from that
ordering, association/DHCP timing and remaining guard-budget margin are
unmeasured. The terminal connectivity checks are one-shot and may refuse a
slow or filtered but otherwise working network. Run 97's pre-radio append
refusal remains unresolved on the phone; the #291 formatting fix is a host
hypothesis, not a device result.

## Coordinator handoff and limits

Under the existing authorization, preflight, verified-backup and recovery
procedures, the physical coordinator should verify the installed-chain identity,
review and re-hash the three host artifacts, and install the following as
root-owned, regular, non-symlink `0700` files, with backups outside the local.d
`*.start` inventory:

| Host artifact | Persistent-root destination |
|---|---|
| `fresh-radio.sh` | `/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh` |
| `gated-post.sh` | `/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh` |
| `gated-hook.sh` | `/etc/local.d/10-omnipha-self-stage.start` |

The coordinator must verify the installed hashes and the private staged and
persisted profiles match without exposing either, pre-arm capture and its
selftest, and use the existing recovery/backup procedures. No host-run radio
recipe, manual remoteproc writes or competing host ACK may occur during the
measured boots. Observe association, address, DNS, internet and real guard
acceptance, then Linux remaining up beyond the guard deadline. Attempt the
second fresh boot only if the first passes and is safely closed or handed off;
record both independently. There is no cold-start authorization here. If a
proven live session is handed back, continue the issue within the mission's
live-session rules rather than treating this host record as acceptance.

Recovery is not guaranteed before guard arming, if the watcher or kernel
fails, or after ACK publication. Failure evidence is volatile/best effort, the
ordered persistent record rejects post-success failure lines, and the unchanged
guard has an acceptance-time deadline race. The surviving bounded kmsg snapshot
cannot establish that earlier fatal lines were not overwritten. The DNS and
ICMP policy can reject working multi-homed, local-resolver or filtered networks.
The owner accepted these limits for this experiment; this candidate does not
repair them or guarantee recovery from every failure.
