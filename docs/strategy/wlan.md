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
  the hook refused a mismatched installed radio with two weakened checks; no
  candidate radio stage ran. The
  [coordinator](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6606847931)
  reports session closure, responsive fastboot and exact same-boot rescue.

## Next single variable

Deliver one device-owned boot/service path that carries the measured run-99
radio chain through association and internet without host stage starts. Turn
its required firmware, modules, helpers, service ordering and secure network
profile provisioning into reproducible image/installed-chain inputs, not
manual live-session repairs. Preserve key-only SSH and safe ownership, pins,
guard, nonce, capture, backups and recovery. Keep network secrets outside Git.
The changed run-106 radio is untrusted and must not be run.

[#311](https://github.com/omnipha/linux-sm7635/issues/311) is a bounded
ordering and real-contract check inside this integration, not the deliverable.
If its ordering fails, implement a different boot/service architecture with
an equivalent real safety proof; do not stop at another host-analysis report.
No forged record, weakened check, manual remoteproc/radio or host ACK. Work
through one existing supervisor-controlled project worker; the physical
coordinator alone owns all device actions and the safety preflight.

## Budget and fallback

Budget one integrated implementation and host-tested batch, then coordinator
review before any device boot. Replay the real guard/record protocol and its
negative cases, and account for run 99's explicit manual deviations. If the
existing contract makes that path unsafe, build the smallest alternative
that preserves guard/recovery and SSH and proves those same safety properties;
a named unsafe dependency alone is not completion. No new boot until identity,
verified backups and rescue, capture, authorization and a safe tested artifact
are established. The altered installed radio must not run; restore or replace
it only via the coordinator's safe plan, with exact hashes and no competing
physical actor. Do not build an image solely to change a hash.

The owner accepted possible loss of uncopied comparable WLAN-session pstore;
host capture is not a pstore copy. [Decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6603722440).
Guard recovery is not guaranteed before arming, after watcher/kernel failure,
or after ACK; do not claim otherwise or weaken an existing interlock.

## Acceptance

One fresh boot without a host-run recipe or host ACK starts the radio, associates
`wlan0`, obtains an address, resolves DNS and reaches the internet. Linux remains
up past the recovery deadline. A further boot requires a specific technical
reason and coordinator authorization. Host tests and a host-assisted session
are not passes.
