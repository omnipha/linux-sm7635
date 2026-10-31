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
      The record rotation boots (run 84): staging, cutover and the
      independent no-ack return are measured. What remains is the
      live session measured the panel path: the stock msm_drm module
      gives a DRM device and a running KMS pipeline, but DSI commands
      to the RM69220 panel fail and the backlight stays off. The
      remaining change executes before SSH exists.

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
