---
date: 2026-10-29
run: 58
issue: omnipha/linux-sm7635#164
subsystem: wlan
result: inconclusive
source: README.md
---
## Run-58 first-boot self-stage and WLAN blocker (2026-10-29, #164)

[BOOT.md](BOOT.md#run-58-first-boot-self-stage-and-wlan-association-blocker-164-live-session-2026-10-29)
records the first live boot of the `4b83ea24…` `init_boot_a` and `1bdb7c22…`
inactive `vendor_boot_b` images. Without a host push, the guest self-staged the
postmarketOS root from the read-only `vendor_boot_b` window, reached guest PID 1
and OpenRC `default/local`, accepted the 160 s guard ack, and held at the modem
marker. With a separate fresh capture marker before each stage, `remoteproc2`
and `remoteproc3` both reached `running` and `wlan0`/phy0 registered; a scan saw
36 BSS (scan only, not connectivity). OpenRC `wpa_supplicant` started on
`-iwlan0` but stayed `SCANNING`, and `networking` stopped with no DHCP lease.
The guest profile matched the protected host input, yet its network did not
appear in 36-, 37- or 30-BSS scans, so no association, address, route, gateway,
DNS or external reachability was reached. A separate host Wi-Fi scan found zero
matches for the same designated network among 27 BSS, consistent with (not proof
that) the network was not observable. The one clean guest reboot was then issued:
the diagnostic USB debug gadget reappeared by itself about 17 s later under new
interface names, but no host IPv4 was observed on them, USB SSH and capture did
not return, and the device was found in bootloader fastboot about 148 s after the
gadget appeared, consistent with the unchanged 150 s recovery timer. Whether the
`vendor_boot_b` self-stage repeated, and WLAN after reboot, are unmeasured
because the worker did not check the new host interface during that window. The
coordinator owns stock restore and the five-hash proof.
