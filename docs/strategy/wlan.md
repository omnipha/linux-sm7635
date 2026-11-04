# WLAN strategy

Status: active. Goal: integrate autonomous WLAN into the boot image and
installed chain, with no host recipe or host ACK.

## Measured

- [Run 99](../../records/2026-11-02-192316-run99-persistent-services-acked-session.md)
  reached association, address, DNS and internet through host-directed stages
  after ACK. This is not an autonomous or pre-ACK proof.
- [Run 101](../../records/2026-11-03-104136-run101-panel-parser-live-boundary.md)
  stopped at the pre-radio panel record. In
  [run 106](../../records/2026-11-03-143859-run106-radio-pin-mismatch.md),
  the hook refused an altered radio with two weakened checks before any
  candidate radio stage ran; run 112 removed it.
- [Run 113](../../records/2026-11-04-093054-run113-pair-installed-internet-route-gate-refused.md)
  flashed the verified pair (`init_boot_a d7bba454…`,
  `vendor_boot_b 221bfd82…`), which stays installed and never-reflash. One
  candidate boot autonomously cut over to postmarketOS PID 1 and passed the
  modem, WPSS, driver, scan, service, association, address, route and gateway
  gates; the internet gate refused at `internet route is not wlan0`
  (uptime 199.62 s), no ACK, session closed unresponsive with exact same-boot
  rescue hashes. The run-113 route text itself was not captured.
- Host reproduction with the pinned AArch64 `iproute2-minimal 6.11.0` shows
  a valid route query prints a second `cache` line that the old `NR == 1`
  parser rejects: a demonstrated sufficient cause, not a proven device cause
  ([diagnosis](../../records/2026-11-04-102445-run113-route-cache-diagnosis.md)).
- The route-cache candidate (post `92f6f9cd…`, hook `5bc5b0f4…`) is integrated
  host-only as a separately pinned variant with its own manifest verifier
  ([integration](../../records/2026-11-04-113000-route-cache-variant-integration.md));
  the run-113 installer and the variant installer refuse each other's files,
  so the candidate cannot replace the installed chain in place. No candidate
  image exists. The agents#121 provenance-gate repair is closed and no longer
  a dependency.

## Next single variable

Finish the host deliverable so the coordinator can independently assess it:
enable the candidate build CLI and variant manifest write under the reviewed
separately pinned design, keeping image output disabled until migration
review. Then the physical coordinator alone decides the one-device-step
migration: back up and remove only the two old persistent post/hook files
(matching radio preserved), flash the candidate pair under fresh identity,
rescue, capture and safety gates. The next target measurement is one fresh
autonomous boot through DNS and internet; the candidate must also record the
raw route text on refusal, so the run-113 cause is measured, not assumed.

[#311](https://github.com/omnipha/linux-sm7635/issues/311) remains the single
mission issue. No forged record, weakened check, manual remoteproc/radio or
host ACK. Work through the existing supervisor-controlled worker; no second
physical actor. Real guard, identity, nonce and record checks stay binding.

## Budget and fallback

Budget the host deliverable and one coordinator-gated migration plus at most
one fresh measurement boot. If the route refusal persists on the candidate,
the recorded raw route text names the actual cause; do not spend another boot
on bookkeeping alone. Do not build an image solely to change a hash. Preserve
SSH, backups, capture, guard and recovery, and never bypass a preflight
failure.

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
