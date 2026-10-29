---
date: 2026-10-23
issue: omnipha/linux-sm7635#53
subsystem: usb
result: inconclusive
source: BOOT.md
---
## Static USB address logging on the enumerated gadget (#53, host-only, 2026-10-23)

**Host-only artifact, not a boot, USB or SSH result.** No device, adb, fastboot,
USB, flash or userdata operation was performed. The one new image is
`$WORK/out/init_boot-static-address.img` (8,388,608 bytes, SHA-256
`995aaca380225be1b865493230164ecc49c5c958b50560d3851010bf3294e5f9`).
Two consecutive builds produced byte-identical files. The hash differs from
measured #51 `9f89fe8d…`, #49 `88c93077…`, #47 `8f8b7331…`, #44 `cdb9458f…`,
#42 `3932504a…`, #40 `f4a00ce3…`, stock `baa33fd4…`, vendor_boot `bde3a3b3…`
and `6078269d…`, and every earlier measured image SHA in the verifier's prior
set. No prior image is reused.

The measured #51 attempt (23) ran its own `/init`, accepted one `peripheral`
write, created `a600000.dwc3`, bound the NCM+ECM gadget and enumerated on the
host as `18d1:4ee2` for about 148 seconds. The host saw link carrier on both
interfaces, but its DHCP failed and no route to `172.16.42.2` existed; SSH
timed out. The #51 init ran `ip link set` and `ip addr add` for `usb0` and
`usb1` and discarded every result, so the pstore could not show whether the
device configured `172.16.42.2/24` and `172.16.43.2/24`. That is the only
question this image adds logging for. It does not assign any host address.

The #51 `/init` is frozen byte-for-byte as
`initramfs/init-51-peripheral-mode` (SHA-256
`995d9c84289502f77b8fb893e748524bcef84db07d1f2dd74cb403a017601263`).
The #51 builder and verifier now read that copy; a separate rebuild produced
`9f89fe8d614e213de1d197b78b2faf7f88ba190ba66cc41d5e3cd6c144d64af3`,
byte-identical to the retained #51 artifact. The new `/init` changes only the
gadget branch after `gadget bound`: the two `ip link set up` and two
`ip addr add` commands no longer discard their output and each result is
logged, then read-only `ip addr show dev usb0`, `ip addr show dev usb1` and
`ip route` are logged at most 32 lines. After the unchanged key-only sshd it
adds one read-only listener check for `172.16.42.2:22`, at most 64 lines, from
`ss -ltn` or `netstat -ltn` when present and otherwise from the dropbear
process list plus the `172.16.42.2:22` line of `/proc/net/tcp`. The 127-module
order (list SHA-256
`4f0e151da8a68339d34d7596d73e77f95415faa79b741aaa425572c1fa7caf69`), the single
`peripheral` write, the 40 × 0.25 s UDC wait, the 150 s `/run/keep` timer
(still started before the module phase, budget unchanged), `bin/restart2`, the
NCM+ECM functions and the key-only sshd command are unchanged. No extra `.ko`,
kernel, DT or gadget function was added.

`build-init-boot-static-address.sh` rebuilt twice sequentially and its
fail-closed verifier, including negative fixtures, passed on each build. The
3,489,280-byte newc (SHA-256
`767316300effaff75c8b8af331325b3f203bc0894c7a8547d0dc2f3def609d22`)
contains zero `.ko`. One Android LZ4 legacy HC-12 block of 1,931,104 bytes
(1,931,112-byte frame) starts at offset 4,096; the remaining 186,520-byte gap
to offset 2,121,728 is zero. Only the stock init_boot ramdisk-size header
field changes, to 1,931,112; the empty kernel, 8,388,608-byte size and
6,266,880-byte signed stock tail through the `AVBf` footer are preserved.
This does not establish stock AVB acceptance. Negative fixtures reject a
missing or duplicated address log, an address or link command that still
discards its result, missing or lengthened network or listener diagnostics,
a removed, moved or lengthened timer, a changed module order, a second role
write, a changed gadget function, a planted `.ko`, a bad header/frame/gap/tail
and every reused measured SHA including `9f89fe8d…`. `scripts/verify-bootimg.sh`
(157 `OK` checks), `bash -n`, `shellcheck` and `git diff --check` all passed.
Artifacts and test logs remain outside Git.

Contrasting outcomes to distinguish in any separately coordinated physical
measurement, none of which is claimed by this host proof:

- **Both addresses are logged and sshd listens on `172.16.42.2:22`.** The host
  can then assign `172.16.42.1/24` to the NCM interface and attempt the
  existing key. Create `/run/keep` only after login. This image assigns no
  host address.
- **An address command fails, or sshd is not listening on that address.**
  Record the exact error and stop. The next question is that failure, not
  another role or module change.
- **Addresses and the listener are present but SSH still times out.** That
  separates the device configuration from the host path. Stop this branch.
- **No usable USB.** Observe at least 180 seconds. Fastboot at about 150 to
  180 seconds with a captured pstore means the timer still returns the device;
  a userspace timer does not cover a kernel hang. No return, no log, or a
  reboot into itself is a separate result. Never repeat this SHA after a
  negative test.

#12 and the encrypted-userdata release gate remain untouched.
