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
- [x] WLAN comes back after a reboot: association, address, DNS, internet.
- [x] postmarketOS becomes PID 1 without the laptop holding the boot.

## Now

- Step: Display works.
      Check: a picture is on the panel, driven by this kernel,
      and it is still there after a reboot.
      Run 88 exercised the BOE-bound chain live
      (records/2026-11-01-021249-boe-bound-live-rails-reset-dcs-glass-dark.md):
      rails enabled, reset GPIO 12 claimed and power-cycled, extdvdd
      GPIO 161 driven high, DCS 0x11/0x29 accepted. Reads stayed empty
      and actual_brightness zero; the glass stayed dark. BOE and _vxn
      DT nodes name the same rails, reset GPIO and sequence, so panel
      node selection is refuted as the remaining lever. No picture means
      no reboot check. The next single variable is pre-SSH panel
      power-on/reset before the cont-splash handoff or a supply state
      this userspace cannot reach; no successor issue is invented here.

## Then, in order

- [ ] Cold start works.
      Check: power off, USB unplugged, one power press, and the phone
      reaches Linux, persistent root, radio and WLAN with no laptop.
      The phone returns itself to fastboot when nobody acknowledges it.
      One observed attempt, then stop. It does not block the display.
- [ ] Touch works. Check: input events from the panel.
- [ ] Audio works. Check: sound out of the speaker.
- [ ] Cameras work. Check: a frame from each sensor.
- [ ] Mobile data works. Check: an address over the modem, no WLAN.

## Not this

- No image built to answer a question the running SSH session can answer.
- No new issue for bookkeeping, a verifier quirk, or a repeated hash.
- No step started while the one above it is still open.
