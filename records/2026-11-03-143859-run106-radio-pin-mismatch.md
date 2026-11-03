---
date: 2026-11-03
run: 106
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: confirmed
---
# Run 106: installed radio pin mismatch and weakened checks

The coordinator handed off a live setup session for boot
`0a89d9ef-594b-4953-bff0-8840a17733bd`. The worker independently checked the
open/handoff status, same-boot ready capture and fresh marker, pinned ED25519
fingerprint, key-only SSH, current boot ID, UID 0 and root-owned `0600`
`/run/keep`. Coordinator-proven rescue and installed carrier hashes from run
105 were prior-boot evidence; a fresh run-106 rescue read was pending when the
worker made its decision. This setup boot is not an autonomous WLAN test.

At uptime 141.72 s, before PID 1 cutover, the staged and persisted non-symlink,
root-owned `0600`, single-link WLAN profiles compared equal using quiet BusyBox
`cmp`; no profile content or digest was disclosed. The persistent post and
local.d hook had expected root-owned `0700`, single-link metadata and exact
PR #306 hashes `9f0adb66...` and `64c3ffdb...`. The persistent radio had safe
metadata but SHA-256
`d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3`, not the
tested `a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21`.
Root and `/proc/1/root` differed at this pre-cutover observation; no write was
attempted.

Capture recorded guard arming at uptime 155.987 s and the existing candidate
hook's `pinned persistent script missing or changed` refusal at 156.460 s.
At 244.55 s, after cutover, root and PID 1 root had the same device/inode,
root was ext4 `rw,norecovery`, guard `armed` and `nonce` existed, and no
candidate post/radio process was listed. At 279.44 s the radio hash remained
the mismatched value; read-only inspection found two `true || fail` lines in
place of checks for post-cutover PID1/default-local and OpenRC service state.
This directly confirms the installed radio cannot be treated as the tested
artifact. The hook refusal is the observed result; the altered script was not
run by this worker.

The worker did not back up or replace the radio: by the latter inspection the
remaining guard time was short or uncertain, and a fresh run-106 rescue read
and verified reversible-backup preflight had not been supplied. Prior runs'
return near uptime 316 s is not a new deadline guarantee. Capture then reported
`ready=false` while its process remained active, and guest access stopped.
The coordinator owns current recovery and closure. No host ACK, radio recipe,
manual remoteproc write, guest mutation, reboot, flash, USB action or session
close was performed by this worker. Panel restoration, ordered post record,
radio stages, scan, association, address, DNS, internet and genuine guard
acceptance were not measured; no autonomous pass is claimed.

Next, on a newly coordinator-proven captured session returned promptly to this
same context, verify the current boot, rescue/backup preflight, writable
persistent root and absence of an active candidate, then back up the altered
file outside the local.d inventory and atomically restore and sync the exact
PR #306 radio. Independently re-hash all three destinations and verify root
`0700`, regular, non-symlink metadata. Do not run the hook or radio manually;
a later coordinator-authorized fresh boot is needed to measure automatic
startup. The original success gate, guard, nonce, capture and recovery
interlocks remain binding. Two independent fresh autonomous WLAN passes remain
outstanding; #294 stays open.
