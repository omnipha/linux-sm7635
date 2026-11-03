---
date: 2026-11-03
run: 105
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: inconclusive
---
# Run 105: capture readiness lost before worker SSH

The coordinator reported a no-flash live handoff for boot
`6c9387aa-a39f-4461-b8a3-60123c40bfce`. At the worker's return, the host
session log still showed open and same-boot handoff, the supplied fresh marker
was present in that boot's capture section, capture initially reported ready
and active for the same boot, and the pinned ED25519 fingerprint matched. The
worker's first independent key-only SSH connection timed out before any guest
command completed. The next capture check reported `ready=false` while the
capture service process was still active; its log subsequently reported link
closures. Guest access stopped immediately. The initial ready state and marker
are not proof of continuing transport health, and the current recovery or
session-close outcome must come from the coordinator.

No worker guest command completed. The worker did not verify `/run/keep`, the
current boot over SSH, guard, profiles, installed artifacts, radio, scan,
association, address, DNS, internet or accepted ACK. It did not issue an ACK,
run a radio recipe, mutate the guest, reboot, flash, access USB or close the
session. The captured section did not contain the searched self-post, guest
radio-marker, success-gate, guard or kernel-panic labels; absence in that
bounded capture is not a proof of device state. This is not a WLAN pass.

A later [correction](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6605142724)
reports that an overlapping actor wrote the PR #306 artifacts on run 103 and
then changed the persistent radio script's local-service check; resulting
hashes and durability were not verified. Treat all three installed paths as
unknown, not as the tested candidate or as definitely modified. Before an
autonomous measurement, independently hash them on a newly proven current
session and restore any deviation to the exact reviewed PR #306 artifacts
under the existing capture, backup, recovery, same-boot and deadline rules.
The previous run-104 record did not know this later correction; it is not
proof that run 103 made no persistent write. The reported run-104 manual
association, DHCP and ping were host-assisted, not autonomous acceptance.

The [readiness procedure](2026-11-03-132059-run104-close-next-session-readiness.md)
remains applicable, including safe profile comparison with error distinct from
mismatch and no disclosed profile or nonce. The coordinator owns current
recovery and closure; do not use the stale session. A newly proven live handoff
must return this same context promptly. No new image is justified merely for
these checks. Two independently observed fresh autonomous WLAN passes remain
outstanding, and #294 stays open.
