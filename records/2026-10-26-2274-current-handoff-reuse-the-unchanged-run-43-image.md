---
date: 2026-10-26
run: 43
issue: omnipha/linux-sm7635#130
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Current handoff: reuse the unchanged run-43 image for one userspace WLAN action (#130, host-only, 2026-10-26)

**Host verification only; no device operation or WLAN outcome.** Read-only checks
of `$HOME/sm7635-build/out/init_boot-psoc-hold-wlan-node.img` returned exactly
8,388,608 bytes and SHA-256
`0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa`.
The image was not rebuilt or rewritten; no source, kernel, config, module, timer
or host key changes are part of this handoff. Run 43 reached key-only SSH after
writing only `init_boot_a`, measured the persistent `wlan0` stack, and returned
to verified five-partition stock. Run 44 aborted before any partition write and
measured no follow-up action. #127 remains OPEN blocked; #129 remains CLOSED
not-planned and its marker diff is not resumed. #114 stays withdrawn.

Under the **current device-op reuse rule** (`omnipha/agents` `8ef6aa49`), the
changed image from the newest boot that reached key-only SSH and named
`partitionsWritten` can be reused: run 43's `init_boot_a` image above is the
**sole current reusable changed image**. This supersedes the stale #127/run-44
never-reflash contradiction below; it is **not an owner reflash exception**,
does not authorize editing either ledger, and is conditional on the live gate
still agreeing at preflight. Every older measured SHA remains refused, explicitly
including `8b62520fe6288361fd15faa573587a0d1be1e0788f780c62440677a60b739801`,
`0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7`,
and `e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c`.
No other SHA or partition is authorized. If the live device-op gate no longer
permits this exact reuse, stop; do not force the flash or substitute an image.

**Physical coordinator only**, under the standing `full_autonomy_device_iteration`
approval: exactly one session and one attempt, with all records outside Git.

1. Use only the unchanged image above on `init_boot_a`, through the existing
   `device-op.py flash` path with its normal preflight and verifier hooks. Require
   the verified stock five-partition baseline and fresh targeted gate. No force
   option, ledger edit, second SHA, second partition or second attempt. Use the
   existing #113/#120 preboot capture handoff unchanged: pin the known-hosts
   line recorded in #120, start the listener **before** reboot, pin and verify
   the route only **after** gadget enumeration, accept key-only SSH with the
   pinned host key, selftest capture on the new boot, then create `/run/keep`
   strictly before the unchanged 150-second deadline. Stop and name any failed
   gate rather than continuing without capture.
2. Reproduce the measured run-43 prerequisite **once**: from an offline guard,
   one bounded remoteproc2 start; exactly one `/bin/wpss-once` invocation with
   exit 0 and its single ON hold and stock WPSS write; firmware-ready event,
   `/sys/class/net/wlan0` present and the idle-timeout callback count 0 in
   this boot's captured kmsg. Record the states and stop with the named gap if
   any prerequisite fails. No repeat modem or WPSS action, module reload or
   altered timer.
3. Record a pre-action kmsg offset and read-only `wlan0` flags/operstate. Check
   the **guest's** busybox applet list for `iw`; only if present, use bounded
   `iw dev` discovery to confirm a phy for `wlan0`. Then issue **exactly one**
   guest action through the captured session: `iw dev wlan0 scan` only if that
   phy was reported; otherwise `ip link set wlan0 up` once. Bound the chosen
   command to 20 seconds (1-second kill grace); preserve its exit, stdout and
   stderr. No second command on error or timeout, no imported/host `iw`, scan
   after fallback, association, credentials or `wpa_supplicant`.
4. Immediately record command availability/discovery, chosen action, timing,
   exit and output summary, post-action `wlan0` presence, flags, operstate,
   and **new** fatal, crash or `hdd_psoc_idle_timeout_callback` lines against
   the captured pre-action offset. Classify (a) scan results with `wlan0`
   registered and no new fatal/crash/idle line; (b) the named command/driver
   error as the next blocker, including a successful link-up fallback (not a
   scan); or (c) vanished `wlan0` or a new fatal, crash or idle-timeout line.
   Name failed preconditions or lost capture as gaps instead of inventing an
   outcome. Report a kernel hang separately: the userspace timer cannot cover
   it. Preserve the evidence and stop; do not retry.
5. Return via the established guarded stock recovery path, verify **all five**
   stock partition hashes, pull pstore **before** Android and record rollback
   and final stock state. No `boot_a`, `dtbo`, `vbmeta`, slot B or userdata
   change; do not reopen blocked #12 or the metadata-encrypted userdata gate.
   #130 stays OPEN until the coordinator records the discriminating measurement
   and verified rollback; host delivery alone does not close it. #127 is
   resolved by that measurement, not relabeled by this handoff.
