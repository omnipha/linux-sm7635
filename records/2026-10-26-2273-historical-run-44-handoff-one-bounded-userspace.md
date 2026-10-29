---
date: 2026-10-26
run: 44
issue: omnipha/linux-sm7635#127
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Historical run-44 handoff: one bounded userspace action on the measured run-43 WLAN stack (#127, host-only, 2026-10-26)

**Superseded by #130 above; this section is not current flash authority.**
Run 44 aborted before a partition write. The #127 one-use exception and its
never-reflash-after-flash language below describe the former gate, not the
current `device-op.py` reuse rule. The existing #113/#120 capture and bounded
userspace action procedure remain applicable as restated above.

**Procedure only; no run-44 result is claimed.** The physical coordinator alone
owns one session and one attempt under the standing
`full_autonomy_device_iteration` approval. Run 43 (#126, coordinator record)
flashed `$HOME/sm7635-build/out/init_boot-psoc-hold-wlan-node.img` once and
measured SHA-256 `0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa`:
`/dev/wlan` verified character 495:0 mode 0600; one guarded modem start;
`/bin/wpss-once` exit 0 with node precheck, one 25 s ON hold accepted, one
`wpss_boot=1` write accepted, remoteproc3 running; FW ready received and
`wlan0` persisted from uptime 181 to 264 s, flags `0x1002`,
`operstate=down`, idle-timeout callback count 0. The five-partition stock
rollback and pstore-before-Android were verified. **The former #127 one-use
permission and never-reflash-after-flash rule are superseded by #130 above;
this historical section does not authorize a flash.** The #124 section below
predates this handoff and does not independently authorize a flash. No new
image, SHA, kernel, config, module, timer, modem stack or WLAN-closure change.
The run-43 state is the prerequisite, not the question to repeat.

### Coordinator sequence (all records outside Git)

1. Open a fresh attempt directory outside this repo. Before any flash, verify
   the unchanged candidate's **full** SHA-256 and 8,388,608-byte length, the
   stock parts manifest, recovery-root five-partition hashes against the
   verified stock `boot_a` `197aff11…`, `init_boot_a` `baa33fd4…`,
   `vendor_boot_a` `23725940…`, `dtbo_a` `759813db…`, `vbmeta_a` `cc1926d2…`,
   and a fresh targeted fastboot gate (slot `_a`, unlocked, non-userspace,
   correct platform and `init_boot_a` size). Verify standing approval and that
   this SHA has not yet been flashed for **this** issue. No other partition is
   written for the experiment. Retain all gate results.
2. Before `fastboot reboot`, put the **exact** `[172.16.42.2]:22 ssh-ed25519
   …` known-hosts line from the #120 section below in the attempt directory;
   use strict host-key checking and key-only SSH. Start
   `omnipha/agents/scripts/session-capture.py start` with the attempt directory,
   `--target root@172.16.42.2` and `--known-hosts-file` pointing at that pin;
   verify the listener is running. Prepare `172.16.42.1/24` and both gadget
   links unmanaged. The gadget route cannot be proven live until enumeration:
   after the **one** authorized `init_boot_a` flash and reboot, pin the NCM
   route to `172.16.42.2` on the enumerated link and verify link/route before
   SSH. Do not mistake a preboot route check with no gadget for a failed
   capture listener, or `session-capture.py check` (which needs a boot ID) for
   the preboot gate. The #113/#120 capture/known-hosts order is unchanged.
3. On the earliest key-only SSH acceptance, retain the new boot ID, pin match,
   uptime and `session-capture.py check` showing capture ready for **that**
   boot. Start `session-capture.py selftest <attempt-dir> --marker
   <unique-boot-marker> --timeout 8` **before** writing the unique marker
   to `/dev/kmsg` over the same boot's SSH session. Require the post-start
   live console line, `ok: true` and matching boot ID; only then create
   `/run/keep` strictly before uptime 150 s. Abort on any mismatch, stale
   line, lost link or missed deadline; no early keep or relaxed timer.
4. With continuous kmsg capture retained, check the #101/#106 prerequisites:
   QRTR and rmtfs published, read-only `modem_a` firmware, WPSS offline,
   icnss2 bound and the registered `/dev/wlan` control node. From an offline
   `4080000.remoteproc-mss` only, make **one** guarded, time-bounded
   `remoteproc2/state=start` write over key-only SSH, then verify modem running
   past +60 s, DMS connected and no new fatal/crash. Stop on a failed guard,
   failed write or crash; never restart. Invoke `/bin/wpss-once` **once** only:
   require exit 0 and its one-shot marker, the passed node precheck, one 25 s
   `/dev/wlan ON` hold accepted, one stock `wpss_boot=1` write accepted and
   remoteproc3 running. Wait for `wma_wait_for_ready_event: FW ready event
   received` and verify `/sys/class/net/wlan0` still present, its flags and
   operstate, modem and WPSS running, and
   `hdd_psoc_idle_timeout_callback` count **zero in this boot's captured
   kmsg**. If any prerequisite fails, record it and stop before a userspace
   WLAN action. Do not run the helper, modem write or ON hold again.
5. Record the continuous capture's pre-action offset/time and a read-only
   pre-action sysfs snapshot. Test only the session's own `/bin/busybox`
   `--list` for an `iw` applet and, **only if present**, run its `iw dev` once
   under a short timeout and record exit/stderr and whether it reports a phy
   for `wlan0`. This read-only discovery is not a scan. The unchanged
   run-43 cpio's `/bin/busybox` (SHA-256 `c2f279d1…`) has no `iw` applet and
   no standalone `iw` in the cpio: expect the fallback, but check on this
   boot; do **not** import/install an `iw`, use host `iw` or substitute a
   different driver. Choose exactly **one** of these commands, over the
   already captured SSH session, using the guest's own binary; send both
   stdout and stderr to the attempt record and retain the exit status
   (including timeout 124 or kill 137). A 20 s timeout with 1 s kill grace
   does not cover an unresponsive kernel or a severed SSH link:

   ```sh
   /bin/busybox timeout -k 1 20 /bin/busybox iw dev wlan0 scan 2>&1
   ```

   **Only** when the bounded guest `iw dev` returned a phy for `wlan0`, use
   that scan. Otherwise record `iw` absent, failed or phy absent (including
   its exact error line), and issue **only** the fallback:

   ```sh
   /bin/busybox timeout -k 1 20 /bin/ip link set wlan0 up 2>&1
   ```

   There is no second scan, no scan after the fallback and no interface-up
   after a scan error. An unavailable command or timeout is recorded, not
   retried. Do not interpret `operstate=down` alone as a crash or failed
   scan: an unassociated interface can have no carrier.
6. Immediately capture a read-only post-action snapshot: exit code and
   full stdout/stderr (summarize scan BSSID/frequency lines without publishing
   private identifiers, or quote the named error), `/sys/class/net/wlan0`
   presence, `flags`, `operstate`, remoteproc2/3 states, and the **new** kmsg
   lines since the pre-action offset. Record explicit new counts and verbatim
   evidence for fatal, crash and `hdd_psoc_idle_timeout_callback`; compare
   against this boot's baseline, not a grep of only the post-command tail.
   Save capture/check/selftest, command availability and `iw dev` result,
   chosen command, timeout, start/end uptime, exit, output summary, both
   sysfs snapshots and kmsg span under the attempt directory outside Git.
   If capture drops or the command cannot be observed, report it as
   unmeasured; do not run another action to fill the gap.
7. Decide **once** from that record: (a) the scan returns BSSID/frequency
   results and `wlan0` remains registered with no new fatal/crash/idle line;
   (b) a named command error (including guest `iw` absent or phy absent,
   nl80211 unsupported, timeout or driver rejection) is the next blocker,
   including a successful fallback `ip link up` that is **not** a scan result;
   (c) `wlan0` vanishes or any new fatal/crash/idle-timeout line appears —
   stop immediately, preserve evidence. If the preconditions or capture fail,
   report the gap, not (a). No outcome permits association, credentials,
   `wpa_supplicant`, module reload, icnss2 unbind/bind, WPSS restart, another
   modem write, another scan or a second attempt.
8. The coordinator then returns to stock via the established guarded
   `restart2 bootloader` / fresh fastboot gate / stock `init_boot_a` restore
   path, verifies the **five** stock partition hashes from recovery root,
   pulls pstore **before** booting stock Android, and records the rollback,
   pstore marker, slot and final stock state. No test image remains. A hang
   may require gated recovery; the 150 s userspace timer does not cure a
   kernel hang. The issue stays open until the coordinator records the
   discriminating physical result and rollback, not on this host PR.

`8b62520f…`, `7c3d915f…`, `0b40ac34…`, `e75c5bd2…`, `d9d8d2b8…`,
`bf2089c4…` and all earlier measured SHAs remain never-reflash. The stale
#127 one-use exception for `0f998e29…` is superseded by the current device-op
reuse rule in the #130 section above; that section, not this one, governs the
next reuse.
