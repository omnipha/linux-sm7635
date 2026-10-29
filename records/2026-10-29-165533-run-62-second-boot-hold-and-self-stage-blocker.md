---
date: 2026-10-29
run: 62
issue: omnipha/linux-sm7635#176
subsystem: userspace
result: confirmed
---
## Run 62 second boot: host re-addressing, fresh boot ID and `:22` return; self-stage stops at the missing `/run/keep` hold (#176, live session)

**Measured physical result of the one clean guest reboot, after the first-boot result in [the run-62 first-boot record](2026-10-29-164137-run-62-first-boot-userdata-self-stage-and-association-blocker.md).** Host re-addressing, a fresh boot ID, key-only diagnostic SSH and console streaming all came back without a host push. The **first missing line is the second self-stage from `userdata`**, with the exact guest text `pmos-self-stage: FAIL: diagnostic hold not set before self-recovery deadline`. The `userdata` ext4 carrier itself is not implicated: it was already proven on the first boot and was never reached on the second.

Immediately before the reboot the worker rechecked boot `4fe15310…`, root-only `/run/keep`, `remoteproc2`/`remoteproc3` both `running`, `wlan0` present, `wpa_state=SCANNING`, capture `ready: true` on the same boot, and a fresh passing console-marker selftest. One `busybox sync; busybox reboot` was issued over pinned `:2222` at 17:51:32 (+01:00); SSH closed by the remote host. The read-only host observer was started just before it. No flash, partition write or session close was performed by the worker.

| step, in the issue's order | measured result on the second boot |
| --- | --- |
| host re-addressing | the installed udev helper ran by itself at 16:51:51Z on the re-enumerated `18d1:4ee2` gadget, logged `result=added` for the NCM `172.16.42.1/24` address (while the interface was still named `usb0`) and for the ECM `172.16.43.1/24` address on the new `enx…` name. The observer reported both new interfaces with `helper_ran=yes` and `removed=no`; ECM `address_added=yes`. The NCM `address_added=no` is a name-tracking artifact of the helper acting before the `usb0`→`enx…` rename, not a missing address: the address was present on `enx…` afterwards. This is the #169/#170 fix working on-device |
| fresh boot identity | capture reconnected by itself with a new boot ID `8d66b476-07a8-40ae-b189-1afe624b44e3` (exactly one new `connected` marker) and `ready: true` |
| `:22` | the new boot's kmsg logs `usb-init: sshd listening at 172.16.42.2:22 (public key only)` plus the listener check, and the pinned-key capture authenticated over that port and streamed. Key-only diagnostic SSH returned without any host-side key or address repair |
| second self-stage from `userdata` | **failed at the hold gate.** kmsg: `pmos-self-stage: FAIL: diagnostic hold not set before self-recovery deadline` at 145.32 s uptime, then `usb-init: self-recovery -> bootloader` at 150.20 s. No `EXT4-fs (sda13)` mount line and no archive-copy line exist on this boot, so the read-only `userdata` mount and hash-verified copy were not reached |
| `wlan0`, autoconnect | unmeasured after reboot, not failed. There is no `pmos-self-post` line, no post-cutover PID 1 and no second-boot modem/WPSS stage, so `wlan0`, association, address, route, gateway, DNS and external reachability were never exercised |

**Named cause and next change.** `/run/keep` was created by the host on the first boot; nothing created it on the second. `scripts/pmos-self-stage.sh` waits for an existing root-only hold and dies at the unchanged 145 s deadline, and the independent 150 s recovery then returns to fastboot. The worker's own polling watched for the later `:2222` listener, which only appears after a successful self-stage, so it observed the deadline instead of setting the hold in time. The diagnostic `:22` and capture were already usable roughly 20–30 s after the reboot, well inside the window. The smallest fix is therefore **operational/host-side, not a new image**: create the root-only hold over the already-pinned diagnostic `:22` as soon as the gadget and capture return after a reboot, before waiting for `:2222`. No new SHA and no reflash is justified by this result; `fcb0ed91…` and `ea09444c…` stay measured never-reflash, and a different experiment needs a separately justified variable.

The worker's last device observation is bootloader fastboot (`18d1:d00d`), read-only `getvar` confirming the same unit, slot `a`, unlocked, `is-userspace: no`. Nothing was flashed and no partition was changed. The coordinator owns session closure, capture/pstore preservation, stock `init_boot_a` restore, the supported stock `userdata` restore, the five slot-A hash proof and Android `boot_completed`. #176 stays OPEN; this is not PACKAGE_COMPLETE and not WLAN success. No profile, scan dump, credential or private address is in this record.
