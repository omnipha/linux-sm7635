---
date: 2026-11-03
run: 101
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: confirmed
---
# Run 101: same-boot panel-parser boundary

Run 101 reused the installed chain without flash. The coordinator handed off a
capture-proven diagnostic session for boot
`9aa0cc5d-7120-49e7-a784-856e4036fcc4`. This worker independently verified the
open session and fresh marker, capture readiness, pinned ED25519 fingerprint,
key-only SSH, matching boot ID, root identity and regular root-owned `0600`
`/run/keep`. No host ACK, host radio recipe, manual remoteproc write, guest
mutation, reboot or session close was performed by this worker.

At uptime 200–289 s the guard was armed with a nonce; no accepted ACK was
observed. The startup trace stopped at `pre check panel record` (157.688 s).
At 247 s `/run/pmos-pre-ssh-panel.record` was absent; the root-owned `0600`,
single-link ordered record had a same-boot panel line at line 3. The root and
`/proc/1/root` device/inode identities agreed; the three persistent hook, post
and radio hashes matched PR #296. No self-post process was listed at that
inspection. The generic self-post trace does not prove the executable path at
launch, and post-exit file hashes do not establish process provenance.

At uptime 289 s, the actual guest BusyBox `dmesg` returned success and included
the same-boot panel line with prefix `[    1.575233][    T1]`. Running the
installed candidate's exact normalization and grep as a read-only pipeline
returned status 1 with no match. A separate read-only caller-aware
normalization returned one line exactly equal to persistent record line 3.
This directly confirms the candidate parser does not recognize the measured
same-boot guest format at that later observation; it is consistent with the
startup trace boundary but does not by itself establish which script opened,
the earlier snapshot status, or every possible cause of its exit. The initial
247 s exploratory command exceeded the shell argument-size limit and its
reported parser result is invalid; only the later streaming test is evidence.

No radio marker, gate success, accepted ACK or WLAN interface was observed in
the recorded same-boot interval. Association, addressing, DNS and internet
were not measured; this is not an autonomous WLAN pass and does not establish
run 100's cause. The capture process stayed alive but readiness disappeared
after the 289 s observation, so guest access stopped. The coordinator reports
capture shutdown around uptime 315 s, return to responsive fastboot, session
closure with slot-A rescue verified, and matching installed Linux carrier
hashes. No second acceptance boot was attempted. The owner-lifted run-100
pstore hold and its possible evidence loss remain as recorded in the issue;
the retained host capture is not a pstore pull.

Next: derive and fixture-test the smallest correction to the measured
caller-prefixed panel boundary, preserving producer failure handling, same-boot
identity, unique evidence and equality to ordered record line 3, existing guard,
nonce, capture and success-ACK interlocks. Do not deploy the earlier #301
experimental parser. The coordinator owns installation, capture, recovery and
any next physical attempt. Two separate fresh autonomous WLAN passes remain
outstanding; host tests and this diagnostic boot do not satisfy acceptance.
