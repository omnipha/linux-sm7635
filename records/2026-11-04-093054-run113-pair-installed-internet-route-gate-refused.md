---
date: 2026-11-04
run: 113
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# run113 pair installed internet route gate refused

## Measurement

The coordinator independently verified the dependent-pair manifest under the
producer lock and the three stock backup manifests, then wrote precisely
`init_boot_a` (`d7bba454…`) and `vendor_boot_b` (`221bfd82…`). Each transfer
has `Sending` and `Writing OKAY` in a private transcript. The only candidate
boot was `7dec62b0-ddf3-4a37-abe8-0dad251aa25d`. It reached pinned key-only
SSH, pre-armed capture and a fresh device-op handoff. On this boot, the four
slot-A stock rescue hashes and both installed carrier hashes matched their
verified references. The reviewed hook, radio and self-post files were
installed with their pinned digests and root-only executable permissions.

The candidate autonomously cut over to postmarketOS PID 1 and ran its
pre-ACK modem, WPSS, driver, scan and service stages. The actual success gate
reported association, address, route and gateway pass, then refused the
internet stage with `internet route is not wlan0` at uptime 199.62 s. Its
trace showed the guard armed and nonce present with accepted and ACK absent;
no host radio recipe or host ACK was invoked. This is a measured boundary,
not an autonomous internet or DNS success and not evidence for why the route
selection was wrong. Raw network identifiers remain private.

The captured shutdown began around uptime 315 s and SSH was lost. Targeted
fastboot identity then answered; the coordinator closed the session
`unresponsive` through the rescue verifier. No stock restore, Android boot,
userdata erase or further partition flash occurred; Linux remains installed.
The attempted non-overwriting preboot pstore fetch was unsupported, and the
mission-scoped accepted loss risk applied; the missing prior pstore is not
claimed as captured.

## Next

Keep issue #311 and its retained worker context. Diagnose the route selection
at the failing internet gate against the captured same-boot trace without
bypassing the success gate, guard, host-key pins or rescue conditions. One
verified fresh autonomous WLAN boot remains unmeasured. Coordinator record:
`sprintberlin/phone-second-life@d8b19cc`. Private raw evidence is outside Git.
