# WLAN strategy

Status: active. Goal: autonomous WLAN on every boot.

## Measured

- Runs 98/99: the installed chain reached WLAN and the internet with host help;
  this does not prove autonomous startup. [Run 99](../../records/2026-11-02-192316-run99-persistent-services-acked-session.md).
- Run 100: the self-start trace stopped before radio; `wlan0` and the success
  ACK were absent, and the phone returned to fastboot. The cause and launched
  script are not proven. [Run 100](../../records/2026-11-03-014728-run100-candidate-boot1-capture-boundary.md).
- A historical caller-prefixed panel line fails the host parser replay. This is
  a possible discriminator, not a diagnosis of run 100. [Replay](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6597114588).

## Next single variable

Host-only #301 is complete ([PR #304](https://github.com/omnipha/linux-sm7635/pull/304)); the retained #294 context is ready for the coordinator's live SSH/capture handoff.
Measure the same-boot startup boundary and actual radio chain; fix the measured
cause, not the host hypothesis. Reuse the installed chain where possible; build
an image only when needed.

The owner accepted possible loss of the uncopied run-100 pstore and lifted that
hold. The retained host capture is not a pstore copy. [Decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6598398647).

## Fallback and boundaries

If the panel check does not explain the observed failure, measure startup and
radio in the live session before changing another pre-radio check. Keep the
existing identity, capture, rescue, nonce, guard and success-ACK interlocks;
no manual remoteproc writes or host substitute ACK. Automatic recovery has known
limits. [Review](../../records/2026-11-02-225455-success-gated-ack-owner-review-blockers.md).

## Acceptance

On two fresh boots without a host-run recipe, the radio starts itself, `wlan0`
associates, receives an address and reaches the internet; Linux remains up past
the recovery deadline. Run the second only after the first passes.
