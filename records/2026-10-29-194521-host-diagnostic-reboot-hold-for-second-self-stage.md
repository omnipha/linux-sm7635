---
date: 2026-10-29
issue: omnipha/linux-sm7635#184
subsystem: userspace
result: confirmed
---
# Host diagnostic reboot-hold so the second userdata self-stage can repeat

Host-only contract for the run-62 second-boot miss. Run 62 reached
postmarketOS PID 1 from the read-only `userdata` archive, then one clean guest
reboot returned host addressing, a fresh boot ID and diagnostic `:22`. The
second self-stage died at 145.32 s with `diagnostic hold not set before
self-recovery deadline` because the host waited for `:2222`, which only exists
after a successful self-stage. No guest script, timer or image changes here.

`scripts/pmos-reboot-hold.sh EXPECTED_NEW_BOOT_ID PINNED_KNOWN_HOSTS_22
CLIENT_KEY` requires `REBOOT_HOLD_CAPTURE_DIR` and
`REBOOT_HOLD_CAPTURE_TOOL` (the coordinator's `session-capture.py`). The
pre-reboot boot ID comes from `REBOOT_HOLD_PRE_BOOT_ID`, or from the first
`# connected` line in that capture. It uses one strict key-only SSH to
diagnostic `:22` (BatchMode, public key only, no agent, pinned `known_hosts`
of exactly one ed25519 line for `172.16.42.2` or `[172.16.42.2]:22`). It
requires a healthy capture check on the expected boot, a diagnostic PID 1,
one `:22` listener and an uptime below 145 s, then creates a non-symlink
root-only `/run/keep` (0600, owner 0) and confirms it. It refuses a wrong
boot, the pre-reboot boot, a stale or wrong host key, a symlink hold, a late
boot and an unhealthy capture. It never connects to `:2222` and logs no key
material.

`--arm` with `REBOOT_HOLD_PRE_BOOT_ID` is the form armed before the reboot.
It polls only the capture file until a different boot ID appears, then runs
the same helper and retries a failed attempt until its 240 s limit. It does
not touch `:22` while the old boot is still current.

Coordinator sequence, unchanged guest contract:

1. First boot stays as run 62: the existing hold is created by hand, the
   self-stage and host-owned ack complete, and radio work continues while
   SSH and capture stay healthy.
2. Before the one guest reboot, arm `REBOOT_HOLD_PRE_BOOT_ID=<current boot>
   REBOOT_HOLD_CAPTURE_DIR=<attempt> REBOOT_HOLD_CAPTURE_TOOL=<session-capture.py>
   scripts/pmos-reboot-hold.sh --arm <known_hosts :22> <client key>`.
3. After re-addressing, the helper must report the root-only hold on the new
   boot inside 145 s. The guest then repeats the self-stage with no host push.
4. First-boot hold creation is unchanged. The 145 s hold wait and 150 s
   self-recovery are unchanged.

`sh scripts/test-pmos-reboot-hold.sh` proves the hold over a real sshd on
`:22` at a simulated 28 s, then the unchanged self-stage wait loop. Wrong
boot, pre-reboot boot, stale client key, wrong host key, a `:2222` pin, a
symlink hold, a 145 s late helper, and a stale or stopped capture all fail
closed. The same fixture runs from `sh scripts/test-pmos-self-stage.sh`.
`sh scripts/test-pmos-pid1.sh` and `sh scripts/test-usb-readdress.sh` still
pass. No image was built and the measured `fcb0ed91`/`ea09444c` pair is not
rebuilt or reflashed.
