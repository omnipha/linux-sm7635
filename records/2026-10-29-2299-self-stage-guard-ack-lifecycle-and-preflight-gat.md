---
date: 2026-10-29
issue: omnipha/linux-sm7635#173
subsystem: userspace
result: inconclusive
source: BOOT.md
---
## Self-stage guard-ack lifecycle and preflight gate (#173, host-only, 2026-10-29)

**Host-only negative result — the merged guard-ack contract works in the isolated fixture; no guest code or image is changed. #173 stays OPEN for the coordinator-held measurement.** Run 61 (`bee02ce1…` / `41cab142…`, never reflash, rolled back to verified stock) self-staged from `recovery_b`, accepted the PID-1 handoff at 155.23 s and started `pmos-self-post.sh` as postmarketOS PID 1 at 155.54 s, then logged `FAIL: host-owned guard ack not seen before the guard deadline` at 305.78 s (+150.24 s). The SCSI cache sync that precedes the return to fastboot follows at 315.65 s, which is the 160 s guard armed at 155.39 s (155.39 + 160 = 315.39 s) acting as designed. The run-61 attempt record contains only the `:22` `known_hosts` line (`172.16.42.2 ssh-ed25519 …`) and the pre-cutover `run61_handoff_…` marker at 42.01 s; it contains no `[172.16.42.2]:2222` `known_hosts` pin and no `scripts/pmos-pid1-ack.sh` invocation after the 155.54 s cutover.

| step | owner | command / file | contract |
| --- | --- | --- | --- |
| 1. pre-cutover pin | host | one mode-0600 line `[172.16.42.2]:2222 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA2ioqI4txcs3PSJWvcgSd/qBuDuCC50OIvIpKsjrjql` | `pmos-self-stage.sh` replaces the ephemeral `:2222` key with the diagnostic host key and logs that public key; `pmos-pid1-ack.sh` refuses any `known_hosts` file without that exact `[172.16.42.2]:2222` entry |
| 2. cutover and nonce | guest | `pmos-pid1-guard.sh` -> `/run/pid1-guard/nonce` | armed for 160 s before `switch_root`; issues the 64-hex nonce only after `/proc/1/exe` and `/` are the new tmpfs root |
| 3. post-cutover ready line | guest | `pmos-self-post: post-cutover PID 1 on boot <BOOT_ID>; waiting for the host-owned guard ack` | emitted after OpenRC `default/local` is started; waits at most 150 s for a mode-0600, 37-byte `/run/pid1-guard/accepted` matching `<BOOT_ID>` with `nonce` and `ack` removed |
| 4. host ack | host | `sh scripts/pmos-pid1-ack.sh "$BOOT_ID" "$KNOWN_HOSTS_2222" "$CLIENT_KEY"` (working directory arbitrary; `PATH` has `ssh`, `timeout`, `awk`, `stat`, `id`, `sleep`) | connects to `root@172.16.42.2:2222` with strict host-key checking, checks new-root PID 1, boot ID, Dropbear and an advancing heartbeat, writes `$nonce $id` to `/proc/1/root/run/pid1-guard/ack` mode 0600, and requires `accepted` to equal `$BOOT_ID` |

`sh scripts/test-pmos-pid1.sh` exercises the merged `pmos-pid1-guard.sh`, `pmos-pid1-ack.sh` and the `pmos-self-post.sh` wait loop across six isolated cases: `ack` (accepted; wrong host key, client key and boot ID rejected), `late` (ack emitted while `pmos-self-post` is already waiting is accepted by both the guard and the post-cutover waiter), `stale` (an ack written or run after the guard deadline is never accepted: the guard records no `accepted`, `pmos-self-post` does not proceed, and `pmos-pid1-ack.sh` exits non-zero), `timeout`, `preplanted` and `symlinked`. No image is rebuilt because a marker-only SHA change is forbidden; `bee02ce1…`/`41cab142…` and `4b83ea24…`/`1bdb7c22…` remain never-reflash, so any new physical session requires a separately justified guest change rather than a re-run of the measured pair. For that session, the coordinator must wait for the `pmos-self-post: post-cutover PID 1 on boot <BOOT_ID>; waiting for the host-owned guard ack` kmsg line, run `sh scripts/pmos-pid1-ack.sh "$BOOT_ID" "$KNOWN_HOSTS_2222" "$CLIENT_KEY"`, and require both `pid1-ack: accepted on boot <BOOT_ID>` and `pmos-self-post: host-owned guard ack accepted on boot <BOOT_ID>` in the capture before handing off or releasing a stage marker.
