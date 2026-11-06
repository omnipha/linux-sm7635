# Plan

Goal: the Nothing Phone (3a) Pro boots Linux on its own and is usable.
Usable means: it powers on without the laptop, reaches the network,
shows a picture, takes touch, plays sound, and the cameras work.

One active step. A step is done only when its check passes on the phone.
Results, hashes and run logs go into `records/`, never here.
Do not open the next step's issue before the active step is done or
blocked by a measurement.

## Done

- [x] Linux boots and answers over USB SSH.
- [x] The root filesystem survives a reboot (userdata, not RAM).
- [x] postmarketOS becomes PID 1 without the laptop holding the boot.

## Now

- Step: persistent PC-style root operation (#324). Check that SSH userland
      edits survive reboot without a partition flash, including the radio,
      self-post and startup-hook files. Owner direction 2026-11-06: remove
      those three hash pins for mb003. Do not replace them with a signed
      baseline. The known altered radio file must never run. USB SSH rescue,
      guard and identity checks stay. The physical coordinator owns device
      measurements.
- Fresh-boot WLAN (#311) stays open but is not a prerequisite for this step.
      WLAN and any route-cache candidate await the #324 reviewed migration path;
      no live-route measurement boot, candidate build or flash before it exists.
      Its verified fresh boot must reach DNS and internet, publish a genuine
      success-gated ACK and remain up past the recovery deadline without a
      host-run radio recipe or host ACK. A second boot needs a technical reason
      and coordinator approval. History: docs/strategy/wlan.md.

## Then, in order

- [ ] Display works.
      Check: a picture is on the panel, driven by this kernel,
      and it is still there after a reboot.
      Boundary so far: BOE-bound and vendor closures enable the same
      rails, reset and DCS writes, and the glass stays dark
      (records/2026-11-01-021249-boe-bound-live-rails-reset-dcs-glass-dark.md).
      Next single variable: pre-SSH panel power-on/reset before the
      splash handoff, or a supply state this userspace cannot reach.
- [ ] Cold start works.
      Check: power off, USB unplugged, one power press, and the phone
      reaches Linux, persistent root, radio and WLAN with no laptop.
      The phone returns itself to fastboot when nobody acknowledges it.
      One observed attempt, then stop. It does not block the steps above.
- [ ] Touch works. Check: input events from the panel.
- [ ] Audio works. Check: sound out of the speaker.
- [ ] Cameras work. Check: a frame from each sensor.
- [ ] Mobile data works. Check: an address over the modem, no WLAN.

## Not this

- No image built to answer a question the running SSH session can answer.
- No new issue for bookkeeping, a verifier quirk, or a repeated hash.
- No candidate-image flash loop; no userdata erase without independent owner approval.
- No later step started while the current step is still open, except the
  retained #311 worker and its existing host-only checkpoint.
- No manual remoteproc or radio writes outside the measured scripts;
  the 2026-11-01 manual modem start crashed the whole kernel.
