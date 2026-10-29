---
date: 2026-10-29
issue: omnipha/linux-sm7635#169
subsystem: usb
result: inconclusive
source: README.md
---
## Host re-address of a renamed diagnostic gadget (2026-10-29, #169)

[BOOT.md](BOOT.md#host-re-address-of-a-re-enumerated-diagnostic-gadget-169-host-only-2026-10-29)
records the host-only fix for the run-58 reboot window. The installed rule asked a `net` event for `ATTR{../manufacturer}`. That path is the intermediate `net` directory, so the existing helper never ran when the gadget returned under `enx…` names; no address was added or removed. `scripts/90-omnipha-usb-net.rules` keeps the same single helper and matches the USB ancestor (`omnipha`, `18d1:4ee2`). `scripts/omnipha-usb-addr` still addresses only `cdc_ncm` and `cdc_ether` on that gadget and appends the interface, driver, address and result to `/run/omnipha-usb-addr.log`. `scripts/observe-usb-addr.sh` is a bounded read-only record of whether that address was added and whether anything removed it. `sh scripts/test-usb-readdress.sh` injects a synthetic `cdc_ncm` interface under a new name in a private namespace and checks that the address lands, stays, and is not applied to an unrelated interface. The 150 s guest guard is unchanged; host setup uses the measured roughly 17 s registration gap, leaving well over 100 s. No new image exists: the measured `4b83ea24…` and `1bdb7c22…` pair stays never-reflash, and no fresh flash is justified by this host-only change.
