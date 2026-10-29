---
date: 2026-10-28
run: 51
issue: omnipha/linux-sm7635#145
subsystem: boot
result: confirmed
source: BOOT.md
---
## Run-51 measured request rejection (#145, live-session finding, 2026-10-28)

The coordinator opened one held stock-kernel session with `init_boot_a` candidate `d90b22212812f022017a9eaaf6af58cce08a5bf08474a024b7ccb6317b51ffb7` on boot ID `4fad89f3-a7ce-4955-80db-bec1d7d8a74d`. The worker independently confirmed pinned key-only USB `:22`, `/run/keep`, >11 GiB available RAM and a fresh capture marker. The 134-APK public archive staged on separate RAM mounts; a second independently pinned, key-only non-PTY `:2222` reached postmarketOS v24.12 / Alpine 3.21.9 while PID 1 still ran diagnostic BusyBox. One current-boot, mode-0600 request was rejected: the image's `/init` sampled `/run/keep` on entry to the console tail at ~3.97 s, before the coordinator could set the hold over USB SSH, permanently setting `PID1_TIMER_SETTLED=failed`. The earlier host fixture had already created `/run/keep` before running the tail and missed this ordering.

Raw host-only capture `kmsg.log` in the run-51 attempt folder has console-ready at byte offset 150701 (line 2447, 3966985 us), `pid1 timer settle failed: diagnostic hold missing` at 150753 (line 2448, 3967158 us), coordinator marker at 151680 (line 2465, 74717233 us), fresh worker marker at 151872 (line 2468, 820272009 us), and `pid1 handoff rejected` at 151936 (line 2469, 821254472 us). No transition, guard arm or postmarketOS PID 1 occurred; distro services and WLAN after cutover were not measured. Guest mounts and second SSH were torn down safely; diagnostic `:22`, PID 1, `/run/keep` and capture remained healthy. The already-running PID 1 cannot re-enable this gate safely in-session, so the coordinator owns capture preservation, stock restoration, five slot-A hash and Android checks. At the time of this finding rollback was pending; #145 stays OPEN. The run-51 image is refused, never a successor candidate.
