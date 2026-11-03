# WLAN strategy

Status: active. Goal: autonomous WLAN on every boot.

## Measured

- [Run 99](../../records/2026-11-02-192316-run99-persistent-services-acked-session.md)
  reached WLAN and the internet using host-directed stages after ACK; it does
  not prove autonomous, unacknowledged startup.
- [Run 101](../../records/2026-11-03-104136-run101-panel-parser-live-boundary.md)
  stopped at the pre-radio panel record; a caller-prefixed line was rejected.
  [Run 105](../../records/2026-11-03-134121-run105-handoff-capture-loss.md)
  lost capture before the worker could inspect the guest.
- [Run 106](../../records/2026-11-03-143859-run106-radio-pin-mismatch.md)
  stopped at the hook's radio pin: the installed radio has two weakened checks
  and differs from the tested artifact. No candidate radio stage ran. The
  [coordinator](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6606847931)
  reports the session closed, responsive fastboot and exact same-boot rescue.

## Next single variable

Measure the first **device-started, pre-ACK radio stage**, not another panel,
record or hook refusal. Repeated attempts have stopped in front of that target;
#294's fixed candidate/ordered-precheck approach has not measured it. First,
use one bounded host-only investigation to determine whether panel and ordered
record bookkeeping can be moved after the automatic radio observation while
remaining mandatory before the real ACK. Keep the radio script and all guard,
nonce, boot identity, capture, backup and recovery interlocks unchanged. Test
both success and failure against the real guard/record contract; a mock-only
pass is insufficient. Do not bypass, forge or weaken a check.

If the host test proves that ordering safe, the coordinator may arrange one
captured diagnostic boot: the device must start the exact tested radio itself;
record the first stage entered and its actual result, or the exact refusal.
Do not run a radio recipe, start remoteprocs manually or supply a host ACK.
The installed altered radio must not run: under a proven session and verified
backup/recovery, restore and re-hash the exact tested artifact first. A setup
boot or host-assisted observation is not an autonomous WLAN pass.

## Budget and fallback

Budget: one host-only ordering investigation, then at most one diagnostic
boot for a new radio-stage fact. If the real contract ties that ordering to
safety, or another pre-radio layer stops the diagnostic, stop and identify the
specific dependency and cheaper host-side fix; do not repeat measuring boots
or build an image merely for a new hash. Preserve the same worker context until
the supervisor reconciles its closed assignment; do not start a second worker.

The owner accepted possible loss of uncopied comparable WLAN-session pstore;
host capture is not a pstore copy. [Decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6603722440).
Known guard recovery limits remain; this is not permission to weaken them.

## Acceptance

On two fresh boots without a host-run recipe, the radio starts itself, `wlan0`
associates, receives an address and reaches the internet; Linux remains up past
the recovery deadline. Run the second only after the first passes.
