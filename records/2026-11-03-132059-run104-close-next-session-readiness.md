---
date: 2026-11-03
run: 104
issue: omnipha/linux-sm7635#294
subsystem: wlan
result: inconclusive
---
# Run 104 closure and next-session readiness

The [coordinator's close report](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6604686685)
records boot `a4048916-061e-4687-b02d-17f9aacfd686` closed: a proven capture
and pinned SSH window expired before this retained worker was returned; the
phone returned to fastboot and the coordinator verified rescue and installed
carrier hashes. An overlapping actor attempted manual remoteproc starts;
subsequent running states and `wlan0` are contaminated, not autonomous WLAN.
Candidate installation, association, addressing, DNS and reachability were not
verified. The captured external console is not a pstore pull. The owner's
standing accepted risk covers comparable WLAN pstore loss; no renewed decision
is required. The latest local operation status read during this host-only
preparation says session closed with rescue verified. No old-session access,
device operation, guest command, reboot, image, flash or USB action was made.

PR #306 remains the tested host successor, not a device result. Its private,
ephemeral host artifacts were re-hashed and syntax-checked again:

| Host file | SHA-256 | Persistent guest destination |
|---|---|---|
| `/tmp/opencode/issue-294-run101.qmsuncag/radio` | `a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21` | `/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh` |
| `/tmp/opencode/issue-294-run101.qmsuncag/post` | `9f0adb6618524c142f84dee13ffe9871d71fec19653b8c3def8e893ed0ec102f` | `/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh` |
| `/tmp/opencode/issue-294-run101.qmsuncag/hook` | `64c3ffdb483d9746432ef5ffafc13979e6fed420d89c6086186907f013f6477b` | `/etc/local.d/10-omnipha-self-stage.start` |

The directory was mode `0700`, and the three host files were regular, owned by
the host user and mode `0600`. These are ephemeral artifacts, not backups.
Reproduce from the merged generator and verify all three hashes if absent.

## Bounded procedure after a new coordinator-proven handoff

1. The supervisor returns this **same context** immediately with the current
   session-open/handoff proof, new boot ID, attempt/capture directory, fresh
   console marker, target, designated client key and pinned known-hosts file.
   No endpoint, key path, marker or boot identity from a closed attempt is
   reusable evidence. Check read-only operation status for the newest open with
   no later close and successful handoff for that exact boot/marker. Verify the
   current capture `ready.json`, process/unit alive, no `STOP`, expected boot,
   and the marker in that boot's captured section; verify the coordinator's
   fresh-marker selftest, not merely an old marker or a live PID. Check the
   supplied host-key fingerprint against the coordinator pin. Then make one
   bounded, non-PTY SSH connection with `-F /dev/null`, batch/key-only,
   `IdentitiesOnly`, no agent, strict host-key checking, pinned known-hosts,
   no forwarding and a short connection timeout. Verify boot ID, UID 0 and
   regular non-symlink root-owned `0600` `/run/keep`. Recheck boot at every
   guest batch and capture/open state throughout; if either becomes stale,
   stop guest access and report immediately. The coordinator controls capture,
   rescue, session closure and any new boot.
2. Report uptime and the observed guard phase without displaying nonce or ACK
   contents: armed/nonce/accepted/ACK presence, safe metadata, and same-boot
   identity where readable without disclosing the nonce. Record the guard's
   actual arm/deadline evidence if available; do not infer a fresh 160 s budget
   from connection time. The prior no-ACK runs returned near uptime 316 s after
   arming around 156 s; these are observations, not a guarantee for another
   boot. Prioritize installation verification immediately after handoff and avoid
   starting a multistep mutation near the known or uncertain deadline. Never
   race another installer or interrupt an actively running candidate. No host
   ACK, rerun of self-post/local service, manual remoteproc write or substitute
   radio recipe.
3. In one bounded read-only batch, verify the current root, PID 1 root/mount
   identity, regular non-symlink root-owned `0700` metadata and SHA-256 of the
   three installed destinations against the table; also inspect the active
   startup process and its safe stage/refusal/guard evidence. File presence or a
   later path hash is not proof of which executable launched. Record separately
   panel restore and ordered append, each radio stage and gate phase. Never
   print nonce, profile contents, network identifiers, raw scans or private
   logs. The worker owns later in-session diagnosis, not a competing device run.
4. Diagnose the profile comparison rather than conflating errors with a
   mismatch. For `/run/radio-bringup/wpa_supplicant.conf` and
   `/etc/wpa_supplicant/wpa_supplicant.conf`, report only per-path absent,
   symlink, nonregular, empty, unsafe owner/mode/link metadata, unreadable or
   safe. When both are safe, use `/bin/busybox cmp -s` and explicitly classify
   status 0 equal, 1 different, and other status comparison error. If `cmp` is
   missing, test whether BusyBox provides it and use another locally available
   bounded comparison without displaying values; a failed tool is unknown, not
   a mismatch. A host BusyBox 1.37 synthetic check returned 0/1/2 for equal,
   different and missing file; this is not a guest measurement. A missing
   staged profile can result from the post's EXIT scrub, so absence after exit
   does not prove a missing embedded input. Do not replace a different persisted
   profile silently. Only a task-designated host input may be used; transfer it
   over the verified pinned SSH to root-only guest storage only when safely
   needed. If genuinely inaccessible, report `NEEDS_GUEST_INPUT wlan-profile`
   without its value and follow the same-session supervisor provision path;
   do not close or abandon healthy SSH merely for that condition.
5. If installation is not already verified, coordinate the reversible change
   via the issue/state and do not race coordinator setup. With a still-proven
   session, sufficient time and the coordinator's verified backups and recovery
   preflight, use only the table's reviewed files: re-hash host artifacts,
   validate the actual writable persistent root and PID-1 root view, confirm
   safe destination parents and non-symlink paths, and back up existing files
   outside the local.d `*.start` inventory without exposing private data. Stage
   each file on the same filesystem, verify its hash and root `0700` metadata,
   replace the radio and post first and the hook last, synchronize file and
   containing filesystem, then re-read all three paths and hashes. A failed,
   interrupted or unknown write is not installed proof; retain backups and
   report exact state for coordinator recovery. This is persistent-root setup,
   not a command to execute the hook in the current boot. The automatic local.d
   path has already run on a post-cutover setup session, so this installation
   can be verified now but autonomous execution requires a later coordinator-
   authorized fresh boot. No image is justified merely by the new hashes.
6. When automatic radio does run on a future proven session, observe device-
   owned stages and capture; distinguish scan, association, address, DNS,
   gateway/internet and real guard acceptance individually, withholding raw
   scan, AP identity, private addresses and credentials. A scan alone is not
   connectivity, host fixtures are not physical proof, and a host-assisted
   boot cannot be counted as autonomous. Before any separately permitted
   crash-prone work, require fresh capture check and the coordinator's fresh
   console-marker selftest; never manually operate remoteproc or start a host
   radio recipe. If SSH and capture stay healthy, continue bounded, reversible
   diagnosis toward a meaningful milestone despite recoverable tool failures.
   Two independent fresh autonomous passes remain required, the second only
   after the first passes and is safely closed or handed off.

The existing guard cannot guarantee recovery before arming, after watcher or
kernel failure, or after ACK publication; an ACK can still be accepted if its
publisher is interrupted. A conservative panel refusal, OpenRC ordering and
one-shot readiness remain possible. None is evidence of failure or success on
the next boot. Keep #294 open and preserve the same worker context.
