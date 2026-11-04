# WLAN strategy

Status: active. Goal: integrate autonomous WLAN into the boot image and
installed chain, with no host recipe or host ACK.

## Measured

- [Run 99](../../records/2026-11-02-192316-run99-persistent-services-acked-session.md)
  reached association, address, DNS and internet through host-directed stages
  after ACK. A firmware mount-point repair was required. This is not an
  autonomous or pre-ACK proof.
- [Run 101](../../records/2026-11-03-104136-run101-panel-parser-live-boundary.md)
  stopped at the pre-radio panel record. In
  [run 106](../../records/2026-11-03-143859-run106-radio-pin-mismatch.md),
  the hook refused an altered radio with two weakened checks before any
  candidate radio stage ran.
- A [host-verified pair](../../records/2026-11-04-052230-verified-pair-manifest.md)
  exists; it is not a measured autonomous boot. The coordinator's unmerged
  [run-112 report](https://github.com/omnipha/linux-sm7635/issues/311#issuecomment-6626446229)
  reports that setup backed up and removed the altered radio and legacy hooks
  from the persistent root; the reviewed replacements are not installed. Two
  flash-gate refusals preceded any write because a successful no-write repeat
  boot did not name a changed image; the host gate repair is tracked at
  [agents#121](https://github.com/omnipha/agents/issues/121).

## Next single variable

First repair the no-write-repeat provenance gate on the host with fail-closed
history tests and preserved per-partition transfer transcripts (agents#121);
that is the direct next step, not another measuring boot. Then the physical
coordinator alone assesses the unchanged host-verified pair and installs its
tested persistent-chain replacements under fresh identity, backup, rescue,
capture and safety gates. The next target measurement is one device-owned
fresh boot that carries the run-99 radio chain through association and
internet without host stage starts. Keep network secrets outside Git; the
changed run-106 radio is untrusted and must not run.

[#311](https://github.com/omnipha/linux-sm7635/issues/311) remains the single
mission issue. No forged record, weakened check, manual remoteproc/radio or
host ACK. Work through the existing supervisor-controlled worker; no second
physical actor. Real guard, identity, nonce and record checks stay binding.

## Budget and fallback

Budget one host gate repair with regression tests, then coordinator review of
the existing pair, and at most one first autonomous measurement if preflight
permits. Do not build an image solely to change a hash. If the pair fails to
reach radio, identify its earliest actual stop and prioritize a host-tested
fix or the smallest equivalent safe boot/service architecture; do not spend
another boot on bookkeeping alone. Preserve SSH, backups, capture, guard and
recovery, and never bypass a preflight failure.

The owner accepted possible loss of uncopied comparable WLAN-session pstore;
host capture is not a pstore copy. [Decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6603722440).
Guard recovery is not guaranteed before arming, after watcher/kernel failure,
or after ACK; do not claim otherwise or weaken an existing interlock.

## Acceptance

One fresh boot without a host-run recipe or host ACK starts the radio,
associates `wlan0`, obtains an address, resolves DNS and reaches the internet;
Linux remains up past the recovery deadline with a genuine success-gated ACK.
A second boot requires a technical reason and coordinator approval per the
[owner correction](https://github.com/omnipha/linux-sm7635/issues/311#issuecomment-6625187736).
Host tests and a host-assisted session are not passes.
