---
date: 2026-10-29
run: 58
issue: omnipha/linux-sm7635#164
subsystem: wlan
result: confirmed
source: BOOT.md
---
## Run-58 first-boot self-stage and WLAN association blocker (#164, live session, 2026-10-29)

**Measured physical result — first boot self-staged; association and DHCP not proven; the one clean guest reboot was then issued and USB SSH did not return (see the reboot section below).** The coordinator wrote the already-built `4b83ea24…` `init_boot_a` and `1bdb7c22…` inactive `vendor_boot_b` images and handed off one held boot. The worker independently rechecked boot ID `b833491d-fa76-43de-8758-763fad4f016e`, pinned key-only guest SSH on `:2222` (fingerprint `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`), root-only `/run/keep`, and same-boot `session-capture.py check` (`ready: true`). PID 1 was guest BusyBox in the new tmpfs root, OpenRC `default/local` was started and the host-owned 160 s guard ack had been accepted. The post-cutover hook held at the modem marker; the archive had already been self-staged from the read-only `vendor_boot_b` window without a host push. The worker did not flash, touch partitions or close the session; the single guest reboot described below followed this first-boot measurement.

| stage | measured result |
| --- | --- |
| modem | a fresh console marker passed capture selftest before release; `remoteproc2` reached `running` past the 5 s hold and QMI DMS connected without a fatal |
| WPSS | a separate fresh marker passed capture selftest; `remoteproc3` reached `running`, `WLAN FW is ready` appeared and `wlan0` and phy0 registered |
| driver | a separate fresh marker passed; `wlan0` and phy0 were already present, so the stage left them untouched |
| scan | a separate fresh marker passed; the bounded scan returned 36 BSS. This is **not** association or connectivity |
| OpenRC services | a separate fresh marker passed; `wpa_supplicant` started with `-iwlan0`, but remained `SCANNING`. `networking` tried DHCP and stopped with `udhcpc: no lease, failing`. The private staging copy of the profile was removed; the root-only OpenRC config stayed in guest RAM. USB SSH and capture remained healthy |
| bounded diagnosis | the guest OpenRC profile was byte-identical to the protected host input, with one enabled WPA-PSK network. The measured target did not appear in the initial 36-BSS raw scan, a later completed 37-BSS scan, or one directed `iw` scan returning 30 BSS. A directed supplicant reassociation also stayed `SCANNING`. No address, route, gateway, DNS or external reachability was established; none is claimed |

**Association branch before the reboot:** the designated network was not observed. After the phone-side scans above, the build host's own Wi-Fi radio (`wlp0s20f3`) was rescanned and its 27-BSS result contained zero matches for the same protected profile's SSID (counts only; no SSID, BSSID or signal printed). That is consistent with the network not being observable from either radio, but it is not proof that it was not broadcasting: position, band, regulatory-domain or profile causes were not excluded. Association, DHCP, address, route, gateway, DNS and external reachability were not measured and none is claimed. Do not treat scan results as connectivity.

**Reboot phase (one clean guest reboot, measured 2026-10-29).** Immediately before it the worker rechecked boot `b833491d…`, `/run/keep`, `remoteproc2` and `remoteproc3` both `running`, and capture `ready: true` with a fresh passing selftest. One `busybox reboot` was then issued over pinned `:2222` at 09:49:20 (+01:00). Host-side evidence:

| time (+01:00) | host observation |
| --- | --- |
| 09:49:20 | SSH closed by the guest; capture `link closed`, boot ID null; capture never reconnected (every retry `ssh-exit 255`) |
| 09:49:22 | USB disconnect of the first-boot gadget (`enxea73140d8537`/`enxbec2213d4215` unregistered, `172.16.42.1` withdrawn) |
| 09:49:24 | new full-speed USB device (early stage) |
| 09:49:39 | new high-speed `18d1:4ee2` "SM7635 USB debug": the diagnostic gadget is back, with new CDC NCM/Ether interfaces `enx5ec440cb6dc2`/`enx46b3b6e58925` (different MAC-derived names). NetworkManager only renamed them; the journal shows no address configuration |
| 09:52:07 | USB disconnect, 148 s after the gadget appeared |
| 09:52:12 | `18d1:d00d` "Android": fastboot. A read-only `fastboot getvar` showed the same device, `current-slot: a`, `is-userspace: no`, `unlocked: yes`. Nothing was flashed |

What this establishes: after a guest reboot the device's diagnostic USB debug gadget reappeared without any host push, and the device was then found in bootloader fastboot about 148 s after that gadget appeared. Those observations are consistent with (but do not prove) the unchanged 150 s `/run/keep` recovery timer firing with no hold created; the timer itself was not observed. **USB SSH did not return by itself.** The first missing line is host-side IPv4 setup on the re-created interface: no `172.16.42.1/24` address or link-up was observed on the new `enx5ec440cb6dc2`, so neither the capture nor the worker could reach `:22`.

What it does **not** establish, and what the worker got wrong: whether the guest self-stage from `vendor_boot_b` repeated, whether `:22` or the WLAN came back, and whether the guest would have answered had the host been configured. The worker kept probing the old address and interface name for 180 s and never checked the new interface during the roughly 148 s window, so that was not tested. No guest kmsg exists after the reboot because the capture could not connect. Reboot autoconnect, WLAN return, address, route, gateway, DNS and external reachability after reboot are therefore **unmeasured**, not failed. Repeating this needs a coordinator-held session in which the host brings the new interface up with `172.16.42.1/24` and creates the hold within the first 150 s, so the guest can be queried before the recovery timer expires.

The worker last observed the device in bootloader fastboot and did not flash, reboot again or write any partition. The coordinator owns stock `init_boot_a`/`vendor_boot_b` restore, the five slot-A hash proof and Android boot. This record contains no profile contents, scan dump, identifier or address.
