---
date: 2026-11-03
run: 101
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: inconclusive
---
# run101 preboot pstore access blocker

The coordinator assessed a new diagnostic session for the open WLAN issue,
not a second passing acceptance boot. No new boot or image flash occurred.
The previously installed and already measured Linux carrier pair was left in
place. No Android boot, partition erase, restore, host ACK or radio command
was issued, and no live worker handoff is claimed.

## Observed preboot boundary

- The phone answered targeted fastboot identity, slot, unlock, product and
  userspace checks. No ready ADB device was present. The stock backup manifests
  verified on the host. The previous run's same-boot rescue and installed carrier
  hashes had matched, and there has been no subsequent partition write; this is
  not a new on-device hash measurement.
- The failed first candidate boot's host console capture passed its recorded
  SHA-256 check. No pstore pull after that boot is recorded, and the existing
  archived pstore predates it. Capture is not a substitute for a pstore pull:
  the present pstore contents and whether any exist remain unknown.
- Read-only `getvar` did not expose pstore or ramoops. Both a pstore fetch and
  a control partition fetch were refused because the bootloader did not provide
  `max-fetch-size`. In the previous run `fastboot reboot recovery` led to a Linux
  setup boot, not recovery ADB. A boot may overwrite pstore; therefore the
  coordinator held at the preboot preservation requirement rather than claiming
  a new session or starting a potentially destructive recovery path.

## Outcome and next discriminator

This is a concrete preservation/access blocker, not a demonstrated WLAN root
cause or failed second acceptance boot. The coordinator recorded the device
operation and left the phone in responsive fastboot with Linux installed. The
same #294 worker context remains relevant after a fresh proven live handoff.
Issue #298 requests a bounded host-only investigation of supported non-
overwriting pstore access or a documented demonstrably non-overwriting route;
it neither authorizes device operations by the worker nor requires a new image
or repeated operator approval. The earlier rescue hashes and host console remain
available but are not newly measured pstore evidence.
