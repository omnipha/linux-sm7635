---
date: 2026-10-25
run: 37
issue: omnipha/linux-sm7635#104
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## qca_cld3 probe delivery after run-37 FW_READY: probe WAS delivered and failed inside qca_cld3; no safe in-session retry (#104, host-only, 2026-10-25)


**Host result (this section supersedes the "ordering" reading of run 37 recorded
below):** the run-37 capture shows the qca_cld3 probe callback was delivered on
the FW_READY event and **failed**; `wlan0` is absent because of that failure,
not because neither delivery path ran. The failure is traced with high
confidence to a **named missing input**: the WLAN INI file
`wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini` is unreachable through every
`firmware_class.path` search path in the diagnostic session (stock serves it
from `vendor_a` via `/vendor/firmware`), and that read failure maps to exactly
the observed `-1` (`-EPERM`). No bounded, memory-safe in-session operation
retries the probe in the failed run-37 state (stop rule, same as #99); the
successor single variable is the INI reachability, not ordering and not
observability. All evidence is host-only, from the pinned vendor tree
(NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, read-only) and the run-37/stock
artifacts (`~/phone-second-life-data/mb003/pstore/`, read-only, never
committed). No image, build, flash or device operation.

### The line that answers the open question

`capture/kmsg.log:2486-2488` (monotonic µs timestamps):

```
258601464  icnss2: WLAN FW is ready: 0x480487
258606640  icnss2_qmi: Received DMS MAC: [redacted; private device data]
258608779  icnss2: Driver probe failed: -1, state: 0x4a0487, probe_cnt: 1
```

`Driver probe failed` is printed at exactly two sites in the pinned tree:
`icnss_call_driver_probe` (`main.c:1358-1359`, reached from the FW_READY
handler) and its twin inside `icnss_driver_event_register_driver`
(`main.c:1785-1786`). Run 37 took the first: `qca_cld3_qca6750.ko` loaded at
~1.63 s (`kmsg:2376-2378`) when FW was not ready, so registration only stored
`priv->ops` and parked (below); the print at 258.6 s is necessarily the
FW_READY-branch call at `main.c:1486 → 1335-1372`. The 2.1 ms gap between the
DMS-MAC success line and the failure print is the entire probe attempt
(`probe_cnt: 1`; the retry loop at `main.c:1351-1356` only retries
`-EPROBE_DEFER`). `ICNSS_DRIVER_PROBED` (state bit 3) stayed clear — hence no
netdev.

### (1) Both FW_READY -> probe delivery paths, every early return and gate

Path A — FW_READY when ops are already registered (run 37's path):

- WLFW QMI FW-ready indication `fw_ready_ind_cb` (`qmi.c:2330-2345`) posts
  `ICNSS_DRIVER_EVENT_FW_READY_IND` (`qmi.c:2343`; early return only on a
  spurious/no-txn indication, `qmi.c:2338-2341`). The WLFW server itself is
  found via `wlfw_new_server` (`qmi.c:3205-3231`): when `ICNSS_DEL_SERVER`
  is set it ignores arrival (`3212-3216`); event allocation can return
  `-ENOMEM` (`3222-3223`), else it posts `SERVER_ARRIVE` (`3228`).
  `icnss_driver_event_server_arrive` (`main.c:1111-1318`) rejects `!priv`
  (`1119-1120`), clears `ICNSS_FW_READY`/`ICNSS_FW_DOWN` (`1123-1124`),
  handles Slate wait and double-connect (`1126-1139`) and runs the full
  bring-up handshake (host cap `1184`, device info `1232`, BDF download
  `1262-1269`); any failure returns without a healthy server (`1312-1317`).
  The MSA memory-info/ready requests are **ADRASTEA-only** (`1189-1207`),
  not a WCN6750 probe gate; CE IRQ setup is not called on either probe
  delivery branch. Only then can the firmware send FW_INIT_DONE
  (`qmi.c:2507-2579`: no txn returns at `2519-2522`, bad/absent hang-data
  details still post the indication at `2577-2579`) and FW_READY.
  FW_INIT_DONE (`icnss_driver_event_fw_init_done`, `main.c:1495-1521`)
  returns `-ENODEV` on `!priv` (`1499-1500`), then either arms cold-boot
  calibration (`1511-1515`) or calls the FW_READY handler directly (`1517`).
- Handler `icnss_driver_event_fw_ready_ind` (`main.c:1452-1493`): `-ENODEV`
  without `priv` (`1456-1457`); sets `ICNSS_FW_READY` (`1460`), prints
  "WLAN FW is ready" (`1468`, `kmsg:2486`); `-ENODEV` if `!priv->pdev`
  (`1472-1476`); if `ICNSS_PD_RESTART` is set, diverts to SSR complete
  (`1481-1482`) — otherwise, the delivery branch run 37 took:
  `icnss_setup_dms_mac` (`1484-1485`, return ignored; on this `use-nv-mac`
  board it retries DMS up to 200×50 ms and asserts if no MAC ever arrives,
  `main.c:997-1011` — run 37 got the MAC, `kmsg:2487`), then
  `icnss_call_driver_probe` (`1486`).
- `icnss_call_driver_probe` (`main.c:1335-1372`): **silent no-op** return 0 if
  `!priv->ops || !priv->ops->probe` (`1340-1341`); `-EINVAL` if already probed
  (`1343-1344`); then `ops->probe` (`1352`). None of those gates bit in run 37:
  `ops` was registered at 1.63 s, `PROBED` was clear, and the failure print
  `1358-1359` fired — the callback itself returned `-1`.

Path B — driver registration when FW is already ready:

- `qca_cld3` module load -> `wlan_hdd_register_driver`
  (`wlan_hdd_driver_ops.c:2382-2385`) -> `pld_register_driver` ->
  `pld_ipci_register_driver` (`pld_common.c:303-308`) ->
  `__icnss_register_driver` (`main.c:3331-3376`): `-EAGAIN` if icnss2 not
  probed yet (`3337-3341`), `-EEXIST` if ops already set (`3345-3349`),
  `-EINVAL`/`-ENODEV` on bad dev_info (`3351-3360`), `-EINVAL` without
  probe/remove (`3362-3365`); otherwise posts `REGISTER_DRIVER`.
- Handler `icnss_driver_event_register_driver` (`main.c:1747-1800`): stores
  `priv->ops` (`1756`); if `ICNSS_FW_DOWN` -> `-ENODEV` (`1761-1765`); if
  `!ICNSS_FW_READY` -> **parks** ("FW is not ready yet", `1767-1771`, debug
  print only) — this is what happened at 1.63 s in run 37 and in stock; if FW
  is ready, powers on (`1773`) and calls the same `ops->probe` loop
  (`1778-1783`) with its own failure print (`1785-1786`).

**Answer to the ordering question:** no, run-37's ordering (REGISTER_DRIVER
~255 s before FW_READY) does **not** fall into a window where neither path
delivers. Registration-before-FW_READY is the normal, stock-supported order:
Path A is designed exactly for it, and the capture proves delivery happened —
the `Driver probe failed: -1` line **is** `icnss_call_driver_probe` running.
Run 29's opposite order (registration after FW_READY, Path B's probe loop) also
delivered a probe call and also failed it (`-1`, recorded below at
BOOT.md "Dead end and next single blocker"). Both orderings deliver;
both measured sessions failed inside the qca_cld3 callback. Run 37 removed the
run-29 confounder (modem offline, DMS absent) — the MAC was received — and the
probe still failed, so the blocker is now unambiguously inside the qca_cld3
probe callback, not in icnss2 delivery, not WPSS bring-up, and not DMS/MAC.

### (2) What stock does differently — nothing, in ordering

Stock: icnss2 binds at 2.41 s and `qca_cld3_qca6750` loads at 2.62 s
(`console-ramoops-0:2492-2753`), the `init.vendor.wlan.rc` early-boot
`write /sys/kernel/icnss/wpss_boot 1` fires at 5.16 s
(`console-ramoops-0:4401`), FW_READY at 14.24 s (`:6591`), DMS MAC
(`:6592`), then the HDD probe chain runs (`:6614+`) and succeeds. Run 37 kept
that order (modules at ~1.6 s, trigger at 249.9 s after DMS) and differed only
in the ~245 s delay of the trigger — FW_READY latency after the write matched
stock (run 37: 8.66 s; stock: ~9 s). So the run-37 session init did **not**
invert the stock order; the ordering hypothesis is retired. `wpss_boot_store`
(`main.c:4373-4396`) gates only on `wpss_supported` (`4380`) and parses
`1`/`0` (`4383`); `schedule_work(&wpss_loader)` (`4391`) -> `icnss_wpss_load`
(`main.c:4348-4371`) -> `rproc_boot` (`4366`). Run 36 (the #96 lineage this
session inherits) shows the same early registration and no trigger at all
(`attempt-20261025-1425-initboot-rmtfs-sharedmem/capture/kmsg.log`: closure
modules at ~1.6 s, DMS connected at `:2470`, `stage9-state.txt:21` wpss
offline), so no measured session inverted the order either.

### (3) Line-by-line cross-check; the named missing step

Between `kmsg:2486` and `:2488` there is **no** HDD/QDF error line and no
firmware-load line at all (whole-capture grep). The stock console, in the same
2 ms window of its own boot, shows exactly one relevant line,
`console-ramoops-0:6593`:

```
(NULL device *): loading /vendor/firmware_mnt/image/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini failed with error -13
```

That is the kernel firmware loader's non-`ENOENT` warn
(`drivers/base/firmware_loader/main.c:604-607`); `-13` (`-EACCES`) is stock's
first-path attempt under `/vendor/firmware_mnt/image`, **not** evidence the
file actually exists on `modem_a`. Stock then succeeds on a later search path
(the HDD chain proceeds, `console-ramoops-0:6613+`; an `ENOENT` miss is
`dev_dbg`-only, `main.c:608-610`, silent). The chain from there, all
pinned-tree verified:

- `__hdd_soc_probe` (`wlan_hdd_driver_ops.c:799`) -> `hdd_context_create`
  (`wlan_hdd_main.c:14649`) -> `cfg_parse(WLAN_INI_FILE)`
  (`wlan_hdd_main.c:14682`), where `WLAN_INI_FILE` is
  `"wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini"` (`wlan_hdd_misc.h:44-45`; the
  `qca6750/` prefix comes from `MULTI_IF_NAME`/`DYNAMIC_SINGLE_CHIP`, and the
  chip-named module `qca_cld3_qca6750` measured at `kmsg:2376` confirms it).
- `cfg_parse` -> `qdf_ini_parse` (`qdf_parse.c:149`) -> `qdf_file_read`
  (`qdf_file.c:47-59`) reads the INI **through the kernel firmware loader**
  (`firmware_request_nowarn`, `qdf_file.c:28-35`), i.e. the search paths are
  `firmware_class.path` followed by `/lib/firmware*`
  (`firmware_loader/main.c:473-488`, split on `,` at `491-522`).
- Stock and run 37 share the identical
  `firmware_class.path=/vendor/firmware_mnt/image,/vendor/vm-system/oemvm/boot,/vendor/vm-system/trustedvm/boot,/vendor/firmware`
  (stock `console-ramoops-0:139`, run 37 `kmsg:141`; byte-identical
  extraction). Reads resolve in init's mount namespace
  (`kernel_read_file_from_path_initns`, `main.c:600`).
- **Stock provides `/vendor/firmware` from `vendor_a`.** Raw read-only search
  of the stock super image finds, inside the `vendor_a` extent (offset
  5678039040, `super-wlan-closure.py:32`), directory entries for
  `WCNSS_qcom_cfg.ini` and `wlan_mac.bin` whose symlink targets are
  `/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` (and the `peach_v2`
  twin), plus a `/vendor/firmware` entry — the `Android.mk` install layout
  (`qcacld-3.0/Android.mk:228-229,366-369` symlinks
  `firmware/wlan/qca_cld/<chip>/WCNSS_qcom_cfg.ini` ->
  `/vendor/etc/wifi/<chip>/WCNSS_qcom_cfg.ini`). The read-only `modem_a`
  extraction manifest has **no** `image/wlan/` directory at all, so the first
  `firmware_class.path` entry can never supply the INI on this device.
- **The run-37 diagnostic initramfs never mounts any of the four paths.**
  The wlan-init phase mounts `vendor_a` at `/mnt/vendor`, `system_dlkm_a`,
  `vendor_dlkm_a` similarly (`build-init-boot-wlan-rfkill-payload.py:106-120`,
  inherited unchanged through the frozen #96/#101 inits) and `modem_a` at
  `/vendor/firmware_mnt` (`:143`); `/vendor/firmware` itself is never created
  (run-37 `stage9-wlaninit.txt:4-12` shows the mounts; the later
  `pdmapper` phase binds only `/vendor/firmware_mnt/image` to
  `/lib/firmware`, `build-init-boot-pdmapper-tqftpserv-payload.py:76-79` —
  which by the manifest carries no `wlan/` tree either). So in run 37 the INI
  lookup is `ENOENT` on **every** candidate path — each one silently
  `dev_dbg`-only — exactly matching the total absence of loader lines in the
  run-37 capture where stock has its `-13` line.
- The failed read returns `QDF_STATUS_E_FAILURE` (`qdf_file.c:58`),
  `cfg_parse` propagates it, and `hdd_context_create` converts it with
  `qdf_status_to_os_return` (`wlan_hdd_main.c:14688`), whose `default:`
  branch (`qdf_status.c:91-93`) maps the unmapped `E_FAILURE` to **`-EPERM`**
  — exactly the `-1` in `kmsg:2488`. The `QDF_BUG` guard at `14687` does not
  fire (it triggers only on `E_INVAL`, i.e. file present but empty;
  `qdf_parse.c:184-187`), so no panic — matching the measured clean session.
- Why no `hdd_err("Failed to parse cfg ...")` (`wlan_hdd_main.c:14684`)
  appears in kmsg: QDF traces route through `wlan_log_to_user`
  (`qdf_trace.c:3575-3582`), whose console gate is closed at probe time — the
  logging service flips `is_active` with `console_log_levels = 0` at module
  load (`wlan_logging_sock_svc.c:431-435,490-491`), and the bitmap from the
  (missing) INI is applied only later at `hdd_set_wlan_logging`
  (`wlan_hdd_main.c:14730`). An early INI read failure is therefore silent
  in kmsg inside the driver; stock's visible `-13` line is the kernel
  loader's, not the driver's.
- In icnss2, every failure print on this chain is unconditional
  (`icnss_pr_err`), and the only one that fired is `main.c:1358-1359`. This
  excludes every icnss2-side `-1` source: the DMS/MAC retry-exhaustion assert
  (`main.c:1008-1009`, would print "Unable to get MAC from DMS after retries"
  — absent; MAC received instead) and the QMI `ret = -resp.resp.result` sites
  (`qmi.c:896-899`, `qmi.c:960-962` — absent), plus the return of
  `icnss_setup_dms_mac` is discarded at the call site (`main.c:1485`) anyway.
  The `-1` therefore originates inside the qca_cld3 callback chain
  (`pld_ipci.c:50-70` -> `wlan_hdd_driver_ops.c:775-898`), and the INI read
  is an early, demonstrably unreachable step that maps to exactly `-EPERM`.
- Residual uncertainty, stated honestly: the run-37 record contains no line
  naming the INI (the loader is silent on `ENOENT`, the driver's error line is
  console-gated off), so the INI is a *strongly evidenced* cause (exact errno
  mapping, stock's own loader line in the same window, the verified absence of
  every candidate path in the diagnostic mount layout, and the verified
  presence of the stock layout in `vendor_a`), not a directly measured one.
  A successor session can confirm it decisively (below).
- Run-37 artifacts have **no captured `icnss2/stats` read** like run 29:
  `initramfs/init:37-38` mounts debugfs, and `debug.c:329-341,826-874`
  creates `icnss/stats` with Posted/Processed counters. The `REGISTER_DRIVER`
  and `FW_READY` counts at probe time were not saved; a stats-equivalent
  event-counter read therefore needs a future session. The order is instead
  inferred from the monotonic kmsg timestamps (banner 1.63 s vs FW_READY
  258.6 s) and the registered ops proven by `main.c:1358-1359`, not from a
  run-37 stats snapshot. `stats` counts events but does not timestamp their
  order (`debug.c:329-341`); it could corroborate delivery, not replace the
  kmsg sequence.

### (4) One bounded, memory-safe in-session operation — none exists (documented gap)

Every candidate was vetted against the pinned tree:

- `/dev/wlan` (`wlan_hdd_state`, major seen at `kmsg:2377`): writes accept
  only `OFF|ON|ENABLE|DISABLE|WAIT_FOR_READY|FORCE_DISABLE`
  (`wlan_hdd_main.c:18958-18982,19108-19215`);
  `ON`/`WAIT_FOR_READY` only wait on a completion that a *successful* probe
  would set (`19166-19174`, pure passive wait, times out); `ENABLE` with the
  driver not loaded votes HW power (`18994-19010`), and `FORCE_DISABLE` when
  loaded performs driver-unload teardown (`19012-19021`), not a safe probe
  retry. No write value maps directly to `ops->probe`.
- icnss2 sysfs (`main.c:4419-4435`) and debugfs
  (`debug.c:826-875`): none invoke `icnss_call_driver_probe`. In the
  non-debug build `icnss/stats` is the only debugfs file; if
  `CONFIG_ICNSS2_DEBUG=y` then `fw_debug` exists, but its `test_mode 3`
  reaches `icnss_trigger_recovery` (`debug.c:710`, `main.c:4117-4162`),
  a WPSS SSR, not a safe retry. The pinned
  `volcano_gki_defconfig` sets only `CONFIG_ICNSS2=m`/`CONFIG_ICNSS2_QMI=y`,
  while `volcano_consolidate_defconfig:2` enables `ICNSS2_DEBUG`; the run-37
  record does not establish which optional debug controls were compiled into
  the loaded stock module. Either way a WPSS restart is a second unmeasured
  variable, excluded here.
- Re-posting `REGISTER_DRIVER` is rejected `-EEXIST` (`main.c:3345-3349`;
  run 37's `priv->ops` is still installed — the failed probe does not clear
  it), and clearing it requires `icnss_unregister_driver`, reachable only from
  the qca_cld3 module-exit path (`pld_ipci.c:522-525`) = rmmod.
- The only in-kernel re-delivery of `icnss_call_driver_probe` after a failure
  is SSR: FW down -> `ICNSS_PD_RESTART` -> next FW_READY ->
  `icnss_pd_restart_complete` (`main.c:1394-1449`) -> `icnss_call_driver_probe`
  at `!PROBED` (`1418-1442`). Reaching it requires a WPSS subsystem restart,
  and repeated probe failures there hit `QDF_BUG(probe_fail_cnt < 3)` with
  `+PANIC_ON_BUG` compiled in (`kmsg:2376`,
  `wlan_hdd_driver_ops.c:843-846`) — a panic-terminating mode, not
  memory-safe-by-construction.

Per the stop rule (as in #99): **no single bounded, memory-safe in-session
operation exists** that retries the probe in the failed run-37 state — the
probe already ran, failed, and the state machine does not re-enter it without
a module reload or a WPSS restart, both excluded. The **named missing step**
is instead the WLAN INI file `wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini`, which
the diagnostic session never exposes through `firmware_class.path` while stock
serves it from `vendor_a` via `/vendor/firmware` (section 3). The successor
single variable — for its own issue with its own distinct-SHA image and
fail-closed design, not built here — is making the stock INI (and, because
the stock install is a symlink, its `/vendor/etc/wifi/qca6750/` target)
reachable on one of the existing search paths before the WLAN closure loads,
with predicted discriminating outcomes: (a) the probe passes `cfg_parse` and
the HDD chain continues (new `qca6750:` kmsg lines / `wlan0`) — the INI cause
confirmed; (b) the probe fails again at a later fallible step — the INI cause
confirmed for this step and the new line names the next blocker; (c) an
identical silent `-1` with no new lines — the INI hypothesis weakened,
observability of the QDF ring becomes the successor question. The sysfs
unbind/bind and rmmod/insmod vetoes (#99/PR #100, run 29) stand unchanged.
