## Run 41 candidate: capture-gated rerun of the bounded HDD psoc-idle ON hold (#116, host-only, 2026-10-26)

**Host result, not a device result.** The physical coordinator owns the one
`init_boot_a` run, capture and verified five-partition stock rollback; none was
performed by this change. The single tested variable stays the #109 hold. The
150 s timer, the `/run/keep` semantics and the 25 s WLAN hold are unchanged,
and `0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7` with every
earlier measured SHA stays never-reflash.

Run 40 flashed the #109 image once but started the host capture listener only
after reboot, so the fresh capture selftest never ran, `/run/keep` was never
written and the unchanged 150 s timer returned the device to fastboot before the
guarded session. #113 (merged `92bbe47a`) then pinned the preboot capture
handoff that repairs that ordering without touching the timer. This image exists
only so that handoff can be applied to the same untested hold under a SHA that
has never been flashed.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-psoc-hold-capture.img` | 8,388,608 | `7c3d915f3c8554d8a551b33f1b1caf162d410c0f629fae75425f29112c2fedf0` |

The only delta from the measured run-40 #109 image is the session log line in
`init`, reworded from `session #109: one bounded /dev/wlan ON hold with the
single WPSS trigger` (79 B) to `session #116: capture-gated rerun of the #109
single bounded /dev/wlan ON hold` (85 B). `bin/wpss-once` is byte-identical to
#109: it still rejects a missing `/dev/wlan`, arms exactly one background
`timeout -k 1 25 ... printf "ON             " >/dev/wlan` before the single
`wpss_boot=1` write, waits on that writer and reads `wlan0` flags and operstate
after the existing 12 s window. The stock INI phase, the modem-holding stack,
the 21-module WLAN closure, the USB/key-only SSH path, the armed `sleep 150`
self-recovery timer and the single `/run/keep` test inside it are byte-exact
#109. The debug cpio carries zero `.ko` and is 3,672,064 B, SHA-256
`19f579b482f79894eb5ff210ee7037f65cb08ed06a922ba69d26b040f699bc61`; the LZ4
HC-12 frame is 2,096,169 / 2,117,632 B and the 6,266,880 B signed tail from
offset 2,121,728 is unchanged.

`scripts/verify-init-boot-psoc-hold-capture.py` first re-verifies the measured
`0b40ac34` image through the #109 checker, then requires the candidate's cpio to
differ from it by exactly that marker and the candidate's trigger to equal the
#109 trigger. It rejects every prior measured SHA, a removed, duplicated,
re-capped (the `timeout -k 1 25` bound raised) or moved 25 s hold, a removed or
moved hold wait, an altered, removed or retargeted `/dev/wlan` `ON` write, a
removed precheck or window sample, a second WPSS write, an injected
association, module reload or extra `/dev/wlan` write, a lengthened, shortened
or removed 150 s timer, a disabled or early `/run/keep`, a removed, duplicated
or reworded marker, the marker regressed to the #109 or #106 wording, the
reused run-39 and run-38 images, and tail, header, block, gap and size damage.
`scripts/build-init-boot-psoc-hold-capture.sh` builds the image twice in series
and fails unless the two outputs are byte-identical. The verifier is wired into
`scripts/verify-bootimg.sh`:

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-psoc-hold-capture.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Coordinator handoff (one run, `init_boot_a` only, this SHA only).** Under the
standing approval `full_autonomy_device_iteration`, follow the #113 handoff
above exactly and add nothing:

1. Use a new attempt directory outside Git and a previously verified, pinned SSH
   host key. Before any `fastboot reboot`, start
   `omnipha/agents/scripts/session-capture.py start` for that directory with
   `--target root@172.16.42.2` and `--known-hosts-file` pointing at the verified
   file; configure the NCM host address `172.16.42.1/24`, mark both gadget links
   unmanaged, and verify the link and the route to `172.16.42.2`. Abort if any
   preboot check fails. `session-capture.py check` is not the preboot gate.
2. Flash `7c3d915f3c8554d8a551b33f1b1caf162d410c0f629fae75425f29112c2fedf0` to
   `init_boot_a` only, after the verified five-partition stock rollback and the
   fresh fastboot gate, and reboot once. The SHA becomes never-reflash on first
   flash. Never flash `0b40ac34…`, `e75c5bd2…`, `d9d8d2b8…`, `bf2089c4…` or any
   earlier measured SHA.
3. At the earliest key-only SSH acceptance, read and retain
   `/proc/sys/kernel/random/boot_id` over that same connection. Start
   `session-capture.py selftest <attempt-dir> --marker <unique-boot-marker>
   --timeout 8` and only then write that unique marker to `/dev/kmsg` over the
   same boot's SSH session. Require `check` to report this boot ID, the
   selftest result to be `ok: true` for the same ID, and the marker line to
   arrive after the selftest starts. Only then, strictly before the unchanged
   150 s deadline, may that SSH worker create `/run/keep`.
4. Then exactly one guarded session under the #101/#106 preconditions: modem
   held, QMI DMS connected, `/bin/wpss-once` invoked exactly once, with
   continuous capture from FW_READY through the idle window. Record the writer's
   result, `wlan0` existence, flags, operstate and the whole timer/next-error
   line sequence. Pull pstore before Android and confirm the five stock
   partition hashes after rollback.

**Predicted outcomes (not yet observed):**

| outcome | discriminator | interpretation |
| --- | --- | --- |
| (a) | `wlan0` stays registered and its operstate leaves `down`, or the `hdd_psoc_idle_timeout_callback` shutdown line is absent throughout the captured window | the idle timer was the blocker |
| (b) | the timer is held off but `wlan0` stays `down` with a newly named line | the timer is retired; that line is the next single blocker, and no second variable is added |
| (c) | the same `hdd_psoc_idle_timeout_callback` shutdown still fires | the hold did not take; record the negative result |
| (d) | the fresh capture selftest still misses the 150 s bound | stop, record the measured gap, and do not relax the timer, plant early `/run/keep` or authorize a second attempt |

No outcome authorizes a second attempt or a second variable. Do not bring
`wlan0` up, associate, reload a module, unbind/bind icnss2 or restart WPSS.

## Preboot capture handoff (#113, host-only, 2026-10-26)

**Host-only sequence, not a device result.** No image was built, packaged,
signed, or flashed. The 150 s timer, `/run/keep` semantics, and the 25 s WLAN
hold are unchanged. `0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7`
and every earlier measured SHA remain never-reflash.

Run 40 measured key-only SSH at uptime 120 s. The unchanged recovery deadline
is 150 s, so the residual budget after that measured SSH point is 30 s. The
synthetic gate below uses 1 s to observe capture-ready state, 2 s for the fresh
marker, and 1 s to permit keep. Keep is therefore predicted at uptime 124 s,
with 26 s remaining before the deadline. Those four durations are planning
allowances, not new physical measurements.

| event | simulated time | required evidence |
| --- | ---: | --- |
| capture listener | -4 s | listener is already running |
| gadget route/link | -3 s | `172.16.42.1/24`, link ready |
| preflight | -2 s | both checks pass |
| simulated reboot | 0 s | no reboot before preflight |
| SSH accept | 120 s | this boot's SSH identity |
| capture ready | 121 s | ready state names this boot |
| selftest start | 121 s | marker from this SSH session |
| fresh marker | 122–123 s | line arrives after selftest starts |
| `/run/keep` | 124 s | only after `ok=true` for this boot |

`scripts/verify-preboot-capture-handoff.py` is synthetic and fail-closed. It
rejects a listener or route that becomes ready after reboot, a selftest or keep
at or after 150 s, a marker belonging to another boot, a marker already present
before the selftest starts, keep when selftest did not pass, and a route whose
link is down. Preboot service state alone cannot pass because the ready boot
identity and a post-start line are both required.

Coordinator handoff for a future **separately authorized** session: use a new
attempt directory outside Git and a previously verified, pinned SSH host key.
Before any reboot, start `omnipha/agents/scripts/session-capture.py start` for
that directory with `--target root@172.16.42.2` and `--known-hosts-file` pointing
to the verified file; configure the NCM host address `172.16.42.1/24`, mark both
gadget links unmanaged, and verify the link and route to `172.16.42.2`. Abort if
any preboot check fails. `session-capture.py check` is **not** the preboot gate:
it requires a connected `ready.json` with a boot ID and cannot pass before SSH.

At the earliest key-only SSH acceptance after that reboot, read and retain
`/proc/sys/kernel/random/boot_id` over that same authorized connection. Start
`session-capture.py selftest <attempt-dir> --marker <unique-boot-marker> --timeout 8`
before writing that unique marker to `/dev/kmsg` over the *same boot's* SSH
session. Require `check` to report this boot ID, the selftest result to be
`ok: true` for the same ID, and the marker line to arrive after selftest starts
(`omnipha/agents/scripts/session-capture.py:211-251`). Only then, strictly
before the timer deadline, may that SSH worker create `/run/keep`. An active
preboot service, a stale line or another boot's ID is not a pass. No marker
write, SSH connection, or keep creation is performed by this host-only issue.

This does not prove that a physical gadget link can be ready preboot, or that
SSH acceptance, capture latency, or keep write will fit the 30 s residual. A
future distinct SHA may be vetted and run once only under a separate issue and
the standing approval. If its fresh capture selftest still misses 150 s, stop
and record that measured gap; do not relax the timer or plant early
`/run/keep`.

## Run 40 capture/recovery ordering gap (#111, host-only, 2026-10-26)

**Stop: neither proposed image ordering repair preserves bounded unattended
self-recovery if capture never becomes ready.** No successor image was built,
verified for flashing, or flashed; the psoc-idle discriminator remains untested.
The run-40 `0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7`
image and all earlier measured SHAs remain never-reflash. This is the issue's
explicit documented-gap outcome, not outcome (a), (b), (c), or a claim that the
single #109 WLAN hold failed. No physical device operation was performed for
#111.

### Evidence and ordering proof

- Run-40 host record at `~/phone-second-life-data/mb003/pstore/
  attempt-20261026-0043-initboot-psochold/record-run40.py:19-26`: the #109
  image was flashed once, key-only SSH first succeeded at uptime 120 s, but
  the device returned to fastboot before capture readiness or selftest. There
  was no guarded modem start, `/bin/wpss-once`, or `/dev/wlan` ON write. The
  separate capture check returned `ready: false`, `boot_id: null`
  (`stage7-capture-check.txt:1`); the host capture only began at 00:50:36
  (`capture/capture.log:1`), after the 00:47:05 reboot
  (`stage4-reboot-t0.txt:1`). Pstore contains the #109 marker and the expected
  early `wlan0 absent`, with no fatal line (`stage9-discriminator.txt:1-2`).
  The five-partition stock rollback and stock Android boot completion are
  recorded at `record-run40.py:21`. This is consistent with expiration of the
  untouched 150 s timer; it is not proof of a WLAN failure or a new kernel
  failure.
- The run-40 session init arms the background `sleep 150` immediately after
  `log 'starting'` and before the module phase; at expiry it tests for
  `/run/keep`, calls `/bin/restart2 bootloader` if absent, and falls back to
  `reboot -f` (`initramfs/init:27-40`, frozen timer constant at
  `scripts/build-init-boot-eud-softdep-payload.py:26,32-40`). `/run/keep` is
  deliberately not created by init: only a verified key-only SSH worker may
  create it after the host link and *fresh capture selftest* are proven (the
  #83 section below, "only after key-only SSH, the host link and the capture
  `selftest` are verified"); early-keep and disabled-timer fixtures at
  `scripts/verify-init-boot-live-fatal-stream.py:223-229`. The capture
  selftest itself waits for a new console marker sent over that boot's SSH
  connection, not for a preboot host-service state
  (`omnipha/agents/scripts/session-capture.py:211-251`); hence it cannot pass
  before this session has booted and armed the timer.
- **Keep before the timer window:** creating `/run/keep` in init before the
  timer, or setting it over SSH before the capture selftest, disables the only
  userspace recovery path even when capture never becomes ready. If the gate
  remains failed, the file persists until reboot and the timer's
  `if [ ! -e /run/keep ]` is false at expiry. This is unbounded, not a
  repair. The early/unconditional keep negative fixtures above reject it.
- **Arm only after the capture gate:** moving the 150 s timer into a
  post-selftest SSH action means it is never armed in the exact run-40 failure
  case (`ready: false`, no selftest); an unattended initramfs would then have
  no time bound to reach fastboot. Existing timer-placement fixtures reject
  moving it after even the module loop
  (`scripts/verify-init-boot-eud-softdep.py:159-163`). Moving it later but
  *before* the capture gate leaves the timer-before-gate race intact. A
  separate always-armed watchdog would be a new recovery mechanism, not one
  of the two ordering-only deltas requested by #111.

Starting host capture earlier, fixing the host route before reboot, or requiring
its service to be active preboot can reduce the run-40 setup delay, but cannot
establish the **fresh, boot-specific** capture selftest before the timer is
armed. Leaving the timer unchanged while trying that scheduling improvement
would preserve bounded recovery, but would not implement either requested
ordering repair or guarantee the selftest completes within 150 s (SSH first
arrived at uptime 120 s in run 40). It is not substituted for a vetted image
repair. The pinned vendor tree remains
NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`: the unchanged #109
`/dev/wlan` ON handler waits for driver load then stops the **separate** HDD
psoc-idle timer (`vendor/qcom/opensource/wlan/qcacld-3.0/core/hdd/src/
wlan_hdd_main.c:19163-19184,14132-14136`). That 25 s-capped one-shot WLAN
variable (`scripts/build-init-boot-psoc-hold-payload.py:39-84,111-128`)
never ran in run 40 and cannot repair the session's 150 s recovery gate.
The userspace timer also cannot recover a kernel panic (see the #83 section's
"The 150 s userspace timer does not cover the expected kernel panic"); this
gap makes no stronger recovery claim.

**Disposition:** do not flash `0b40ac34…` again and do not package a cosmetic
new SHA, move/disable the timer, plant early keep, or change the WPSS trigger.
A different, explicitly scoped and independently bounded capture/recovery
mechanism would require a new issue and proof; #111 stops at this host-only
ordering gap, with no physical session or rollback to perform.

## Run 39 candidate: bounded HDD psoc-idle ON hold (#109, host-only, 2026-10-25)

**Host result, not a device result:** run 38 proved `wlan0` registered with
operstate `down`, then `hdd_psoc_idle_timeout_callback` printed "Psoc idle
timeout elapsed; starting psoc shutdown" (`~/phone-second-life-data/mb003/
pstore/attempt-20261025-2148-initboot-wlanini/capture/kmsg.log:2555`). FW_READY
was at `kmsg:2511` (258.329777 s), the HDD ready event at `:2547`
(258.854835 s), and the timeout at `:2555` (259.141096 s). The stock 6.1.84
binary is not bit-identical to the pinned 6.1.78 vendor source; the source
analysis below is a mechanism hypothesis to test, not a physical observation.
The physical coordinator owns capture, one guarded session and verified
five-partition stock rollback; none was performed by this PR.

Pinned NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, under
`vendor/qcom/opensource/wlan/qcacld-3.0/` in the read-only external checkout:

- `core/hdd/src/wlan_hdd_driver_ops.c:813-826` starts HDD, creates vdevs,
  then marks the driver loaded and completes the start. The **arm site** for
  the run-38 initial idle window is `core/hdd/src/wlan_hdd_main.c:17685-17702`:
  `hdd_psoc_create_vdevs` creates the `wlan%d` STA
  (`:17441-17456`) and starts `hdd_psoc_idle_timer_start` at `:17700` for
  mission mode. Timer creation passes **`hdd_psoc_idle_timeout_callback`**
  (`:14663-14665`); `hdd_psoc_idle_timer_start` reads the config and queues
  the delayed work (`:14109-14129`). The default is **250 ms**, the non-emulated,
  non-system-suspend branch of `core/hdd/inc/hdd_config.h:193-201,222-228`.
  A nonzero `current_pcie_gen_speed` can override to 100 ms (`main.c:14120-14126`),
  not a knob in this session. The callback logs before `pld_idle_shutdown`
  (`main.c:14284-14307`), and shutdown only stops modules when
  `hdd_is_any_interface_open` is false (`:14151-14178`). The ~286 ms from HDD
  ready to the shutdown print is compatible with a 250 ms default, but no
  direct runtime read of `iface_change_wait_time` was recorded in run 38.
- **Interface-up path:** `ip link set wlan0 up` invokes HDD `.ndo_open`
  (`main.c:6779`), `hdd_open`/`__hdd_open` (`:5377-5442`), which stops the
  timer via `hdd_trigger_psoc_idle_restart` (`:5427`, `:14238-14252`) and
  marks `DEVICE_IFACE_OPENED` (`:5442`); the idle-shutdown guard reads that
  bit (`:10193-10215`). An open STA requires adapter bring-up but not
  association; carrier/TX queues are enabled only on association
  (`:5443-5449`), so `operstate` may still report `down` even if the psoc
  survives. The run-38 session issued no interface-up before the ~250 ms
  deadline; doing this after a distant SSH check would not vet this window.
- **Userspace hold (the single tested variable):** `/dev/wlan` exists in the
  measured run-38 module load (`kmsg:2401`, `wlan_hdd_state` major initialized).
  Its `ON` write is a recognized value (`main.c:18958-18981,19121-19134`),
  waits for `cds_is_driver_loaded` if the probe is still in progress
  (`:19163-19174`; completion at `driver_ops.c:824-826`), then calls
  `hdd_psoc_idle_timer_stop` (`main.c:19179-19184`, `:14132-14136`) rather
  than bringing up another interface. The `ON` path does not perform a WLAN
  module reload, association or WPSS restart. `WAIT_FOR_READY` returns before
  the stop (`main.c:19176-19184`); `ENABLE`/`DISABLE`/`FORCE_DISABLE` have
  other state-changing paths (`:19135-19157,19186-19207`), so only `ON` is
  chosen. The hold must be scheduled *before* the ~250 ms post-vdev window,
  not after `/bin/wpss-once` has slept 12 s.
- **INI config path:** `gInterfaceChangeWait` is parsed into
  `iface_change_wait_time` (`core/hdd/inc/hdd_config.h:203-228` and
  `main.c:14571-14572`); **0 disables the idle timer** (`main.c:14111-14116`).
  The stock `vendor_a` file `/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` was
  extracted read-only from the measured super image at offset 5678039040:
  2095 bytes, SHA-256 `57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4`.
  It has **no `gInterfaceChangeWait` entry** (file absent in this repo;
  stock path and SHA confirmed run 38 `stage6-ini-proof.txt:1-5`). Adding a
  key would modify stock INI delivery and is not a config value already
  present; no file or kernel change is part of this test. Stopping the timer
  on `ON` is therefore a single variable relative to run 38. The
  `hdd_psoc_idle_timer_start` re-arms on last interface-down, recovery,
  system resume and other mode transitions (`main.c:5569-5573,14305-14307`,
  `driver_ops.c:943-945`, `power.c:2409-2413`); no such transition is added.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-psoc-hold.img` | 8,388,608 | `0b40ac3434b790653e04f8c48b6e035ed0b47bce982a6435e7fc0ef2c0004fe7` |

The only run-38 cpio changes are the session marker and `bin/wpss-once`:
this remains the one-shot stock WPSS trigger and adds one guarded, bounded
`/dev/wlan` `ON` write. The trigger first requires the control char device,
then arms one background write (`timeout -k 1 25 ... printf "ON             "
>/dev/wlan`) immediately before issuing the sole `wpss_boot=1` write. The
writer parks in the driver's `ON` handler, which waits for the probe
completion (`main.c:19163-19174`) and then calls `hdd_psoc_idle_timer_stop`
(`:19179-19184`), i.e. the stop is queued the moment HDD reaches
`cds_set_driver_loaded(true)` (`driver_ops.c:824`) rather than after the
~250 ms window. The trigger records the WPSS-write result, waits on the
writer (fail on timeout), then reads `wlan0` flags and operstate after the
existing 12 s window. The 15-byte payload fully fills the vendor's
`copy_from_user(buf, sizeof(buf))` 15-byte stack buffer
(`main.c:18958-18981`) instead of risking a short read. The single ON write
is concurrent only with the *existing* WPSS boot: the WPSS write and HDD
probe advance normally while the ON writer waits. Capturing whether `ON` is
accepted and whether the idle callback still fires discriminates a
failed/raced hold from a successful one. The modem-holding services, stock
INI exposure, WLAN module closure, SSH path and 150 s self-recovery timer
remain byte-exact #106.

`scripts/verify-init-boot-psoc-hold.py` reconstructs the measured run-38
image, checks the exact two cpio deltas, one-shot gate/order, decompressed and
recompressed LZ4 frame, full stock header except ramdisk size, all-zero gap,
unchanged 6,266,880-byte signed tail, no `.ko`, bounded image size, and the
SHA blacklist (including run-38 `e75c5bd2`, run-37 `d9d8d2b8`, run-36
`bf2089c4` and all older measured images). Negative fixtures remove,
duplicate or move the hold or its wait; change the ON write; remove the gate
or window sample; add a second WPSS write, association or module reload;
alter the INI phase, marker, cpio block, tail, header, gap or image size. Two
serial builds are byte-identical. The verifier is wired into
`scripts/verify-bootimg.sh`:

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-psoc-hold.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes (not yet observed):** after the same #101/#106
capture selftest and modem/DMS preconditions, the coordinator flashes only
this new `init_boot_a` SHA (never reflash it after first use), holds the modem,
invokes `bin/wpss-once` exactly once and continuously captures FW_READY through
the idle window. Record the writer's result, `wlan0` existence, flags,
operstate and the entire timer/next-error line sequence; confirm five stock
partition hashes after rollback. Do not bring `wlan0` up, associate, reload a
module or restart WPSS as a second variable.

| outcome | discriminator | interpretation |
| --- | --- | --- |
| (a) | `wlan0` stays registered, operstate leaves `down` **or** the `hdd_psoc_idle_timeout_callback` shutdown line is absent throughout the captured window | idle timer was the blocker; `operstate=down` alone can still reflect unassociated carrier |
| (b) | `ON` hold accepted, idle shutdown absent, but `wlan0` remains `down` with a new named line | timer retired; record the next single blocker, do not add a second variable |
| (c) | the same `hdd_psoc_idle_timeout_callback` shutdown still fires | hold did not take; record the negative result, no second attempt |

## Run 38: stock WLAN INI exposed, cfg_parse passed, wlan0 registered (#106, outcome a, 2026-10-25)

**Measurement source:** the physical coordinator's record
(sprintberlin/phone-second-life commit `c5e7972`, `devices/mb003.md`), with
host-only evidence under
`~/phone-second-life-data/mb003/pstore/attempt-20261025-2148-initboot-wlanini/`
(2026-10-25 21:48–22:04 Europe/Berlin). The distinct-SHA
`init_boot-wlan-ini.img`
(`e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c`, 8,388,608 B,
never flashed before) was flashed to `init_boot_a` only, after the 16/16
manifest, 5/5 on-device stock hash proof and fresh fastboot gate. Key-only SSH
as root on the stock 6.1.84 kernel carried the #106 session marker; the capture
selftest passed on the second attempt (first attempt
`"no fresh marker in capture within timeout"`, retry OK, marker line latency
1.108 s).

**Outcome (a): the INI cause is confirmed.** In-session proof first: the new
wlan-ini phase logged `stock vendor_a bound read-only at /vendor` and
`stock WCNSS_qcom_cfg.ini reachable (sha ok, 2095 B)`
(`capture/kmsg.log:2314-2316`), and an SSH-side read of the resolved chain
returned exactly the pinned target hash
`57989aba…` for `/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` and
`/vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini`, with both stock
erofs symlinks (`WCNSS_qcom_cfg.ini` → the vendor path, `wlan_mac.bin` →
`/mnt/vendor/persist/qca6750/wlan_mac.bin`) present at their stock locations
(`stage6-ini-proof.txt`).

One guarded `remoteproc2` start held the modem `running` past +80 s with
`icnss2_qmi: QMI DMS service connected` (`stage9-dms.txt`), then exactly one
`/bin/wpss-once` boot: `remoteproc3` powered up `qca6750/wpss.mdt` (4844 B),
`WLAN FW Initialization done: 0x680483` (`kmsg:2510`) and `WLAN FW is ready:
0x480487` (`kmsg:2511`) — the same FW_READY as run 37. The discriminating
difference: **the run-37 `icnss2: Driver probe failed: -1` line is absent
(whole-capture grep, count 0)**, and the qca_cld3 probe chain continued —
`qca6750:` HDD/WMA bring-up lines run from `kmsg:2515` through `kmsg:2570`
(policy manager, `wma_open`, `htc_wait_target: Target Ready!`, service-ready,
`wma_wait_for_ready_event: FW ready event received`, spectral/regulatory/green
AP), exactly the continuation predicted for outcome (a), and **`wlan0` was
registered**: `/sys/class/net/wlan0` whose address equals the MAC received in
the `icnss2_qmi: Received DMS MAC` line (`kmsg:2512`; address itself is
private device data, redacted), confirmed over
SSH (`stageB-wlan0.txt`, `stageB-live.txt`). `cfg_parse` therefore passed: the
single-variable INI exposure removed the run-37 `-EPERM`.

**Measured next single blocker:** `wlan0` is present but its operstate is
`down`. The capture shows `hdd_psoc_idle_timeout_callback: Psoc idle timeout
elapsed; starting psoc shutdown` (`kmsg:2555`) ~0.81 s after FW ready — with no
interface user (no association work, no wpa_supplicant in the session), the
HDD psoc-idle timer shut the psoc down and the netdev stayed registered but
down. The next single question is therefore the psoc-idle/bring-up path for the
registered interface, not the INI, not WPSS, not the probe delivery, and not
association. No reprobe, module reload or second WPSS attempt was performed.

**Recovery and rollback, verified:** `/bin/restart2 bootloader`, fresh fastboot
gate, stock `init_boot_a` `baa33fd4` Sending/Writing OKAY
(`stageD-restore.txt`), recovery-root on-device SHA-256 exact stock for
boot_a `197aff11`, init_boot_a `baa33fd4`, vendor_boot_a `23725940`, dtbo_a
`759813db`, vbmeta_a `cc1926d2` (`stageE-ondevice-hashes.txt`, 5/5); pstore
pulled before Android (`console-ramoops-0` 135,270 B containing the #106
marker, 1 occurrence); `adb reboot` to `sys.boot_completed=1`, A059P, slot
`_a`, stock kernel 6.1.84, unlocked/orange (`stageF-stock-android.txt`). No
test image remains.

`e75c5bd2` is now measured and **never-reflash**. `d9d8d2b8`, `bf2089c4`,
`8dddb8c7`, `35866d56`, `ae2ccff7`, `4216af26` and all earlier measured SHAs
remain never-reflash without exception.

## Stock WLAN INI reachable before the qca_cld3 probe (#106, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. The measured run-37
(`d9d8d2b8`), run-36 (`bf2089c4`) and every previously measured SHA are rejected
for reuse. No flash, boot, remoteproc start, key-only SSH, module reload or other
device operation was performed; only the physical coordinator executes the
packaged trigger under the standing `full_autonomy_device_iteration` approval,
after the capture selftest.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-wlan-ini.img` | 8,388,608 | `e75c5bd260477b0c4bc4b93d528324ec95dc1f8f01e93e551262522bcef2918c` |

### (1) The exact file set the probe needs at `cfg_parse` (confirmed from host artifacts)

The pinned vendor tree (NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, read-only) fixes the probe's read:
`__hdd_soc_probe` → `hdd_context_create` → `cfg_parse(WLAN_INI_FILE)`
(`wlan_hdd_main.c:14682`), where `WLAN_INI_FILE` is
`"wlan/qca_cld/" PREFIX "WCNSS_qcom_cfg.ini"` (`wlan_hdd_misc.h:44-45`) with
`PREFIX = DYNAMIC_SINGLE_CHIP "/"` = `qca6750/` — matching the chip-named module
`qca_cld3_qca6750.ko` measured at run-37 `kmsg:2376`. `cfg_parse` reads it
through the kernel firmware loader (`qdf_file.c:28-59`:
`firmware_request_nowarn(&fw, path, NULL)` at `:56`), whose search order is the
four `firmware_class.path` entries followed by `/lib/firmware*`
(`firmware_loader/main.c:473-488`, split on `,` at `:491-522`). A failed read
returns `QDF_STATUS_E_FAILURE` (`qdf_file.c:58`), which
`qdf_status_to_os_return`'s `default:` branch maps to `-EPERM`
(`qdf_status.c:91-93`) — exactly the run-37 `-1` (`kmsg:2488`).

Read-only extraction of the measured `vendor_a` extent
(`super.img` @ offset 5678039040, erofs) with `dump.erofs` proves the stock
install layout, matching `qcacld-3.0/Android.mk:228-229,366-369`
(`TARGET_FW_DIR := firmware/wlan/qca_cld/$(LOCAL_CHIP_NAME)`,
`TARGET_CFG_PATH := /vendor/etc/wifi/$(LOCAL_CHIP_NAME)`, and the
`symlink-file` of `$(TARGET_CFG_PATH)/WCNSS_qcom_cfg.ini` at
`$(TARGET_FW_PATH)/WCNSS_qcom_cfg.ini`):

- `/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini` — erofs symlink (43 B),
  target `/vendor/etc/wifi/qca6750/WCNSS_qcom_cfg.ini`.
- `/etc/wifi/qca6750/WCNSS_qcom_cfg.ini` — erofs regular file, **2095 B,
  SHA-256 `57989aba51e98e3c608350bbff78b24b9613242cdf39cd1b8f1e0141659377d4`**
  (header `gDot11Mode=0`); this is the symlink's target, present in the same
  partition, so the chain is closed on `vendor_a` alone.
- The `/vendor/firmware` directory entry itself is present in `vendor_a`
  (stock serves the INI from it; the run-37 initramfs never created it, per
  #104 §3).

**`wlan_mac.bin` is excluded, per the issue's condition.** Its stock twin at
`/firmware/wlan/qca_cld/qca6750/wlan_mac.bin` is a symlink (40 B) whose target
is `/mnt/vendor/persist/qca6750/wlan_mac.bin` — the **persist** partition, not
`vendor_a`, so it is not in the existing host artifacts and cannot be exposed by
this change. More importantly the probe chain reads it only at
`hdd_initialize_mac_address` (`wlan_hdd_main.c:15780-15801`), *after*
`hdd_platform_wlan_mac` (`:15680-15736`), and the latter succeeds on this
`use-nv-mac` board via the DMS MAC already received in run 37 (`kmsg:2487`);
`hdd_update_mac_config` (the `wlan_mac.bin` reader, `:15800`) is reached only if
the platform MAC path fails, which it did not. So no discriminating line between
`cfg_parse` and the next fallible step reads `wlan_mac.bin`. The INI and its
`vendor_a` target are the complete file set for this step.

### (2) The single change and why it is single-variable against #101

The measured #101 session init (run-37 `d9d8d2b8`) mounts `vendor_a` read-only at
`/mnt/vendor` in its unchanged wlan-init phase, but never creates
`/vendor/firmware`, so the stock INI is `ENOENT` on every `firmware_class.path`
entry (#104 §3). The candidate adds **one bounded, read-only bind** inside that
same wlan-init phase, after the `vendor_a` mount and **immediately before** the
`modem_a` vfat mount and `wlog "module load begin"` (i.e. before the 21-module
WLAN closure insmods `qca_cld3_qca6750.ko` and its probe can run):

```
mkdir -p /vendor
mount --bind /mnt/vendor /vendor
mount -o remount,bind,ro /vendor   # read-only, fail-closed
# then: sha256 of /vendor/firmware/wlan/qca_cld/qca6750/WCNSS_qcom_cfg.ini
#       must equal the pinned 57989aba… (2095 B) — logged, never modified
```

This is one read-only mount inside the session init — nothing else. Because the
stock firmware entry and the symlink target are both inside the already-mounted
`vendor_a` root, one bind exposes both ends of the stock layout at their stock
absolute paths. The kernel firmware loader therefore finds the INI through the
existing `/vendor/firmware` entry of `firmware_class.path` (the path is already
set identically in stock and run 37; it is not edited), and the absolute symlink
resolves to the real `vendor_a` file. The bind is remounted read-only and the
phase only writes to tmpfs mountpoints and `/dev/kmsg`; it never writes
`vendor_a`, never loads or unloads a module, and writes no remoteproc or icnss2
state. The bind precedes the `modem_a` vfat mount, so the existing
`/vendor/firmware_mnt` mount covers the stock `firmware_mnt` directory entry and
the later read-only `/vendor/firmware_mnt/image` → `/lib/firmware` bind is
unchanged.

Single-variable against the measured #101 init: the candidate cpio equals the
run-37 `d9d8d2b8` cpio with **only** the `init` entry changed, and that init is
byte-for-byte the run-37 init with the one INI phase inserted and the session
marker reworded. Everything the issue pins is unchanged: the modem-holding stack
(recon/qrtr/rmtfs phases, pd-mapper/tqftpserv/rmtfs binaries), the 21-module
WLAN closure and its load order, the one-shot WPSS trigger `bin/wpss-once`
(`16d4747e…`, byte-exact), the USB/key-only SSH path and the armed 150 s
recovery timer. No second variable: the change touches no partition, no module,
no remoteproc and no service — it exposes one already-mounted stock filesystem
through the already-present search path, before the closure loads.

### (3) Envelope, verifier and gates

Debug cpio 3,671,040 B (zero `.ko`), one LZ4 HC-12 legacy frame 2,095,841 B of
2,117,632 B (21,791 B spare), stock header except the ramdisk-size field, zero
gap, unchanged stock signed tail from offset 2,121,728 (6,266,880 B), fixed
8,388,608-B image. `scripts/verify-init-boot-wlan-ini.py` proves the byte-exact
run-37 half and the single-init delta, rebuilds the cpio and frame, checks the
envelope/prefix/gap/tail/size and rejects, via host-generated negative fixtures:
a changed tail, nonzero kernel size, changed block, wrong ramdisk-size, nonzero
gap, short image; the INI phase removed, duplicated, moved after the closure,
its bind made writable, its bind retargeted, its SHA pin removed; the marker
removed; and the run-37 layout or SHA reused; plus every prior measured SHA
(explicitly `d9d8d2b8`, `bf2089c4`, `8dddb8c7`, `35866d56`, `ae2ccff7`,
`4216af26`). Two serial builds produce byte-identical images (`cmp`). Wired into
`scripts/verify-bootimg.sh` with `--self-test` and normal invocations.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wlan-ini.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

### Predicted physical outcomes (not observations)

The physical coordinator flashes the new `e75c5bd2…` SHA to `init_boot_a` only,
pins `172.16.42.1/24` on the NCM link, and passes the capture selftest
(omnipha/agents#16 gate) first. Then confirm the #101 precondition exactly
(sharedmem client present, rmtfs on QRTR, pd-mapper + tqftpserv published), one
guarded `remoteproc2` start, modem held past +60 s, DMS connect allowed up to
+150 s, then the single one-shot WPSS trigger (`/bin/wpss-once`) with continuous
host-side capture through the probe window. Record `wlan0`, the `icnss2` probe
line, and every new `qca6750:`/HDD/firmware-loader line. Recovery stays the
measured path: armed timer to fastboot, then verified five-partition stock
rollback. The new SHA becomes measured/never-reflash on first flash. No module
reload, no second WPSS attempt, no second variable, no partition writes.

- **(a)** the probe passes `cfg_parse` and the HDD chain continues — new
  `qca6750:` kmsg lines or `wlan0` — the INI cause is confirmed.
- **(b)** the probe fails again at a later fallible step — the INI cause is
  confirmed for this step and the new line names the next blocker.
- **(c)** an identical silent `-1` with no new lines — the INI hypothesis is
  weakened and QDF-trace observability becomes the successor question.

Any physical result requires the coordinator's measured recovery and verified
five-partition stock rollback. `e75c5bd2`, `d9d8d2b8` and every previously
measured SHA are never-reflash after the run. The measured result is recorded
above as run 38, outcome (a): `cfg_parse` passed and `wlan0` was registered,
operstate down after the psoc-idle timeout; the stock rollback is verified.

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

## Run 37: WPSS FW_READY reached, wlan0 absent (#101, outcome b, 2026-10-25)

**Measurement source:** the physical coordinator's #101 comment at
2026-10-25T17:38:43Z (run 37), with host-only evidence under
`~/phone-second-life-data/mb003/pstore/attempt-20261025-1832-initboot-wpssboot/`
(`capture/kmsg.log:2466-2488`). The distinct-SHA
`init_boot-wpss-boot.img` (`d9d8d2b8268f1fcc8e3212b7943bf62c5a5b4b7e20f258acf80cbc76d5508076`)
was flashed to `init_boot_a` only after the 16/16 manifest, 5/5 on-device
stock hash proof and fresh fastboot gate. Capture selftest passed in 1.336 s;
key-only SSH and the single guarded `remoteproc2` start held the modem with no
DOG fatal. DMS connected before the one-shot `/bin/wpss-once` invocation; all
preconditions were green.

**Outcome (b):** `remoteproc3` (`9bb00000.remoteproc-wpss`) powered up, booted
`qca6750/wpss.mdt` (4844 B), and became `running`. `icnss2` logged
`WLAN FW Initialization done: 0x680483` and `WLAN FW is ready: 0x480487`:
`ICNSS_FW_READY` was reached. WPSS and modem remained `running` through the
full +90 s observation window without fatal or SSH loss, but `wlan0` was
absent. The coordinator measured `qca_cld3_qca6750` loading ~255 s before
FW_READY and not receiving that event; the next single blocker is inside
**qca_cld3 driver registration/probe ordering**, not WPSS firmware bring-up.
No reprobe, module reload or second WPSS attempt was performed. This outcome
does not establish an association/`wpa_supplicant` question yet.

`d9d8d2b8` is now measured and **never-reflash**. `bf2089c4`, `8dddb8c7`,
`35866d56`, `ae2ccff7`, `4216af26` and all earlier measured SHAs remain
never-reflash without exception. The coordinator has since completed the stock
`init_boot_a` rollback (`baa33fd4`), verified by recovery-root on-device
SHA-256 of all five slot-A partitions (`status.yaml:361`) and a reboot into
stock Android A059P slot `_a`; no test image remains. Rollback is the physical
coordinator's operation and is recorded here, not performed by this work.

**Correction from the run-37 capture (`#104` vetting, above):** the outcome-(b)
narrative here said the coordinator measured qca_cld3 "not receiving that
event" and named **driver registration/probe ordering** as the next blocker.
The kmsg line `capture/kmsg.log:2488`
(`icnss2: Driver probe failed: -1, state: 0x4a0487, probe_cnt: 1`) shows the
probe callback **was** delivered on FW_READY and failed inside qca_cld3;
ordering is not the blocker. See the `#104` section above for the corrected,
cited analysis and the remaining named next blocker.

## WLAN reprobe after the modem holds: vetted unsafe, no image (#99, host-only, 2026-10-25)

**Host result: no safe single reprobe is establishable from the existing
artifacts; per the issue's own stop rule no new init_boot was built, marked or
flashed, and no device operation was performed.** The vetted candidate was the
issue's primary one: a sysfs driver unbind/bind of the icnss2 device bound
during the wlan-init phase. All evidence below is host-only, from the pinned
vendor tree (NothingOSS `android_kernel_msm-6.1_nothing_sm7635` @
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, read-only) and the run-36 artifacts
(`~/phone-second-life-data/mb003/pstore/attempt-20261025-1425-initboot-rmtfs-sharedmem/`).
The #96 marker in `initramfs/init` therefore remains the newest session init;
`bf2089c4…` and every previously measured SHA stay never-reflash.

### Exact binding identity (established)

The icnss2 device bound during wlan-init is the platform device
`17110040.qcom,wcn6750` (live FDT `dtb/live-fdt.dts:26120-26149`,
`compatible = "qcom,wcn6750"`, `use-nv-mac`, `qcom,rproc-handle = <&wpss_pas>`
per `vendor/qcom/proprietary/wlan-devicetree/volcano-qca6750.dtsi:38`,
`wpss_pas = remoteproc-wpss@9bb00000` in
`arch/arm64/boot/dts/vendor/qcom/volcano.dtsi:1248`), bound by driver
`icnss2` (`icnss_driver`, `.driver.name = "icnss2"`,
`vendor/qcom/opensource/wlan/platform/icnss2/main.c:5506-5514`; of-match
`qcom,wcn6750` → `WCN6750_DEVICE_ID`, `main.c:4868-4888`). Measured bound in run
36: `stage10-final-observation.txt:16` (`supplier state: icnss2 bound`) and
kmsg `:2370` (`icnss2: Platform driver probed successfully`, `main.c:5148`).
The sysfs unbind/bind nodes would be
`/sys/bus/platform/drivers/icnss2/unbind` and
`/sys/bus/platform/drivers/icnss2/bind` (standard platform-bus driver
attributes); no existing artifact documents unbinding this device.

### Vetting chain and the three independent blockers

1. **The #96 session state cannot produce any discriminating outcome from an
   icnss2 reprobe.** `wlan0` requires the qca_cld3 probe via
   `icnss_call_driver_probe` (`main.c:1340-1341`), which only runs after
   `ICNSS_FW_READY` (`icnss_driver_event_fw_ready_ind`, `main.c:1452-1493`);
   FW_READY comes from a WLFW QMI indication (`qmi.c:2329-2345`, via server
   arrival `qmi.c:3204-3231`), which requires the WPSS firmware to boot. The
   initial boot trigger in this driver is the `wpss_boot` sysfs attribute
   (`wpss_boot_store` → `schedule_work(&wpss_loader)`, `main.c:4373-4396`);
   its other `rproc_boot` call is WPSS self-recovery (`main.c:2111-2123`).
   Run 36 measured `remoteproc3` (`9bb00000.remoteproc-wpss`) `offline`
   (`stage9-state.txt:21`) and no `WLAN FW is ready` or WPSS firmware-start
   lines in `capture/kmsg.log`, i.e. the WLAN firmware was never initialized
   (the `wpss_boot` write was deliberately removed from these inits). A
   reprobe in that state cannot itself boot WPSS or set FW_READY, so outcome
   (a) is unreachable, and outcome (b)'s "new probe lines" reduce to
   repeating the already-measured platform probe. The candidate cannot test
   the DMS/wlan0 hypothesis at all.
2. **The sysfs unbind path is not memory-safe with the WLAN closure loaded.**
   `icnss_remove` (`main.c:5193-5267`) tears down the devm-allocated `priv`
   (`devm_kzalloc`, `main.c:5022`) and `dev_set_drvdata(NULL)`, but the module
   global `penv` (`main.c:95`, set by `icnss_set_plat_priv` at `main.c:5095`)
   is never cleared — there is no `penv = NULL` anywhere in the tree. The
   WLAN-facing entry points dereference `penv` (e.g. the exported
   `icnss_ce_free_irq` `main.c:3548` and `icnss_ce_request_irq`
   `main.c:3536`, and thermal state `main.c:3161-3179`),
   leaving a freed-memory window between `unbind` returning and `bind`
   re-probing. The driver's supported path for `icnss_remove` is module exit
   (`icnss_exit` → `platform_driver_unregister`, `main.c:5546-5550`), where
   the qca_cld3 client unregisters first — an ordering that cannot hold with
   the 21-module closure pinned loaded and no `rmmod` allowed.
3. **The cycle permanently orphans the already-registered WLAN client driver.**
   `qca_cld3_qca6750.ko` registers `pld_ipci_ops` once at module load
   (`qcacld-3.0/core/pld/src/pld_ipci.c:495-525` via `pld_common.c:303-308`);
   the ops pointer lives only in the old `priv->ops`. `icnss_remove` never
   unregisters it and the fresh `priv` after rebind has `ops == NULL`, so
   `icnss_call_driver_probe` (`main.c:1340-1341`) is a silent no-op even if the
   bind itself succeeds. Without `rmmod`/`insmod` of the WLAN modules —
   explicitly outside this issue after run 29's SSH loss — the WLAN stack can
   never probe after the cycle. The candidate is therefore both unsafe and
   structurally incapable of producing the issue's outcomes.

Boundaries kept: `rmmod`/`insmod` of loaded WLAN or remoteproc modules stays
excluded (run 29 lost SSH after exactly a modem start plus WLAN module reload).
An in-session `echo 1 > …/wpss_boot` would boot WPSS firmware for the first
time in a guarded session — a *second* unmeasured variable, not the vetted
candidate — and is not improvised here.

**Named next single blocker (new issue, not this one):** the DMS/`wlan0`
question is untestable until WPSS firmware bring-up is its own single-variable
experiment (a designed, risk-assessed `wpss_boot`-equivalent before or after
the guarded modem start), because FW_READY — not the icnss2 reprobe — is the
gate in front of the qca_cld3 probe. The modem-holding stack, WLAN closure,
USB/key-only SSH path and recovery timer of the #96 session init are unchanged;
there is no new session marker, no new SHA and nothing to reflash.

## One-shot WPSS firmware boot session init_boot (#101, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. The measured run-36
(`bf2089c4`) and every previously measured SHA are rejected for reuse. No flash,
boot, remoteproc start, key-only SSH or other device operation was performed;
only the physical coordinator executes the packaged trigger under the standing
`full_autonomy_device_iteration` approval, after the capture selftest.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-wpss-boot.img` | 8,388,608 | `d9d8d2b8268f1fcc8e3212b7943bf62c5a5b4b7e20f258acf80cbc76d5508076` |

### Stock bring-up chain (host-only, from the pinned vendor tree and stock artifacts)

Stock writes `1` to `/sys/kernel/icnss/wpss_boot` from
`/vendor/etc/init/init.vendor.wlan.rc` (`write /sys/kernel/icnss/wpss_boot 1`,
early-boot). `wpss_boot_store` (pinned `vendor/qcom/opensource/wlan/platform/
icnss2/main.c:4373-4396`) gates on `wpss_supported` (true on `qcom,wcn6750`,
`main.c:4896-4900`), parses `1` and `schedule_work(&wpss_loader)` (`main.c:4391`).
The worker `icnss_wpss_load` (`main.c:4348-4371`) reads `qcom,rproc-handle`,
`rproc_get_by_phandle`, and calls `rproc_boot`; on failure logs and `rproc_put`.
`wpss_pas` is `qcom,volcano-wpss-pas` (`qcom_q6v5_pas.c:2850-` match, resource
`volcano_wpss_resource` at `2838-2848`: pas_id 6, `wpss.mdt`), has no
`auto_boot` (registers as `remoteproc3`, stays offline until triggered — measured
run-36 `stage9-state.txt:21`). Stock `console-ramoops-0:4402-4416` shows the
`wpss_boot` write from init.rc powering up `9bb00000.remoteproc-wpss` via
kworker `T231` (the `wpss_loader` work), firmware direct loads failing `-13/-2`
and ueventd serving `/vendor/firmware_mnt/image/qca6750/wpss.mdt` (4844 B,
matches `extraction-manifest.txt:1055`, stock `modem_a` vfat mount);
`:5262` "WLAN FW Initialization done", `:6591` "WLAN FW is ready" ~9 s later.

Prerequisites in the #96 session state (all measured): supplier chain bound
(run-36 kmsg `supplier state: wpss bound`, `ipci gate: wpss bound`),
`remoteproc3` registered (`9bb00000.remoteproc-wpss is available`), icnss2 bound
at `17110040.qcom,wcn6750` (creates the sysfs link and `wpss_boot` attribute),
`remoteproc2` modem `running`, QMI DMS connected at +94 s (run-36 kmsg `2470`),
pd-mapper/tqftpserv/rmtfs published, and the stock WPSS firmware files
`image/qca6750/wpss.{mdt,b00..b10,b12}` (13 files, extraction manifest
`1043-1055`) already on the read-only `modem_a` vfat mount that the #96 wlan-init
phase establishes and the #86 phase bind-mounts read-only at `/lib/firmware`.
Stock has no `wpss` pd-mapper map; pd-mapper is not a WPSS bring-up prerequisite.
The stock recovery timer path stays disarmed (`recovery_disabled`,
no `qcom,wpss-self-recovery` in the stock FDT).

### Single-variable design

The candidate cpio equals the measured #96 image's cpio plus exactly one new
executable file `bin/wpss-once` (`16d4747e98085f4e0479f31ba37e516ab13bf864d263525f46cb2a32f8f55310`,
2390 B, mode 0755); the session `init`, all three static services, the maps, the
127-module order, the recovery timer, the USB/key-only SSH path and the 21-module
WLAN closure are byte-exact. `init` never writes `wpss_boot` or any remoteproc
state. The coordinator runs `/bin/wpss-once` once, only after the guarded
`remoteproc2` start has held past +60 s and QMI DMS has connected (up to +150 s)
— the same state as run 36. The helper is one-shot (`/run/wpss-once.attempted`
marker), rejects arguments or a second run, verifies `remoteproc3` name
`9bb00000.remoteproc-wpss` with state `offline` and `remoteproc2` name
`4080000.remoteproc-mss` with state `running`, requires
`/run/qrtr-services.status=qrtr-published`, `/run/rmtfs.status=rmtfs-published`,
the icnss2 driver bind and the read-only vfat `modem_a` mount in `/proc/mounts`
with all 13 stock `wpss.*` firmware files readable, and only then writes
exactly one `1\n` to `/sys/kernel/icnss/wpss_boot` under
`busybox timeout -k 1 3`, logs before/after remoteproc states to kmsg and exits.
It never writes `0` (unload path, `main.c:144-151`), never writes any
`/sys/class/remoteproc*/state`, never loads or unloads modules, never retries.
The single variable is the stock `wpss_boot=1` write in the measured run-36
state; every other input is pinned by measurement or by hash. If any
prerequisite check fails the helper exits without a write (fail closed) and the
issue records the gap instead.

### Envelope, verifier and gates

Debug cpio 3,670,016 B (zero `.ko`), one LZ4 HC-12 legacy frame 2,095,480 B of
2,117,632 B (21,152 B spare), stock header except the ramdisk-size field, zero
gap, unchanged stock signed tail from offset 2,121,728 (6,266,880 B), fixed
8,388,608-B image. `scripts/verify-init-boot-wpss-boot.py` proves the
byte-exact #96 half and the single-entry delta, rebuilds the cpio and frame,
checks the envelope/prefix/gap/tail/size and rejects, via host-generated
negative fixtures: a changed tail, nonzero kernel size, changed block, wrong
ramdisk-size, nonzero gap and short image; trigger removed, made
non-executable, byte-altered, replaced by the run-36 layout, rewritten to write
a remoteproc state, with the one-shot marker removed, with a weakened
precondition check, or with the write timeout removed; init mutations (the
init itself becoming the trigger, marker reworded in place); and every one of
the 52 prior measured SHAs (explicitly `bf2089c4`, `8dddb8c7`, `35866d56`,
`ae2ccff7`, `4216af26`). Two serial builds produce byte-identical images
(`cmp`). Wired into `scripts/verify-bootimg.sh` with `--self-test` and normal
invocations.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wpss-boot.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes, not observations:** the coordinator flashes the
new `d9d8d2b8…` SHA to `init_boot_a` only, pins `172.16.42.1/24`, passes the
capture selftest, confirms the #96 preconditions, performs the single guarded
`remoteproc2` start, lets the modem hold past +60 s and DMS connect (up to
+150 s), sets `/run/keep` so the 150 s timer stays disarmed for the session
window, then invokes `/bin/wpss-once` once with continuous host capture.
The measured result is recorded above as run 37, outcome (b): FW_READY
reached, `wlan0` absent, qca_cld3 probe ordering named as the next blocker.
(a) `ICNSS_FW_READY` reached and `wlan0` appears (`WLAN FW is ready` kmsg,
`icnss_call_driver_probe` on the FW_READY event, `main.c:1452-1493`) — the
DMS/WPSS dependency is confirmed; next question association/wpa_supplicant.
(b) `ICNSS_FW_READY` reached but `wlan0` absent — the blocker moves inside
`qca_cld3`/the firmware path; record the probe/fatal text verbatim.
(c) WPSS firmware load/fatal (`Failed to boot wpss rproc` / firmware load
error / remoteproc3 crash), the modem losing `running`, or any new fatal —
record verbatim, stop, no second attempt. A reject-exit of the helper without a
write documents a missing precondition and closes the issue on that gap without
a second attempt. Any physical result requires the coordinator's measured
recovery and verified five-partition stock rollback. `d9d8d2b8` and every
previously measured SHA are never-reflash after the run. The run-37 outcome
is recorded above; rollback was still pending in the coordinator's comment.

## Stock sharedmem + pinned rmtfs session init_boot (#96, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. The #86 run already
measured `8dddb8c7…` (outcome (b): same ~40 s DOG with pd-mapper/tqftpserv
published); that SHA, `35866d56…`, `ae2ccff7…`, `4216af26…` and every other
measured SHA are rejected for reuse. No physical access, flash, remoteproc
operation, new `modem_a` read, kernel build, boot_a/dtbo/vbmeta/slot-B or other
modem-touching service change occurred in #96.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-rmtfs-sharedmem.img` | 8,388,608 | `bf2089c4f8a72591b45385829f287d24296fc88918a2b40a226ff4b1fcaede55` |
| `$HOME/sm7635-build/out/rmtfs` | 134,088 | `d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd` |

The rmtfs userspace is a static musl 1.2.5 aarch64 build from pinned upstream
sources (`qrtr` v1.2 `b51ffaf2`, `rmtfs` v1.3) with three explicit patches:
(1) the publish observability line `rmtfs: published QRTR service 14 version 1
instance 0`; (2) the non-Android libudev shared-memory path replaced by direct
sysfs/UIO handling that binds to the stock `qcom,sharedmem-uio` device created
by `msm_sharedmem.ko` (uio name `rmtfs`, `/sys/class/uio/*/maps/map0/{addr,size}`),
the `/dev/mem` fallback removed so it fails closed without the stock module;
(3) the storage table reduced to the partitions the stock binary actually opens
— stock `console-ramoops-0:6154-6155` shows exactly `/boot/modem_fs1` and
`/boot/modem_fs2`, so **only `modemst1` and `modemst2` are exposed; `fsc`/`fsg`
are not opened by the stock service and are not exposed**. Located at runtime by
the measured GPT by-name table (`by-name.txt:52-53`: `modemst1 -> /dev/block/sdf2`,
`modemst2 -> /dev/block/sdf3`): the phase creates the block nodes from
`/sys/class/block/*/dev`, confirms `PARTNAME=modemst1/modemst2` in the uevent,
and links `/boot/modemst1 -> /dev/block/sdf2`, `/boot/modemst2 -> /dev/block/sdf3`.
`rmtfs -r -P -o /boot` runs with the read-only shadow: every modem write lands
in RAM only, the partitions are never written. Both required backing partitions
are named from existing artifacts; none was missing.

The kernel half is the **stock `msm_sharedmem.ko`** — the byte-exact
`vendor_boot_a` ramdisk copy (19,568 B, `e9216dcba1295498bc8e1d17405f971d3dadd587f7c453df53512f0a7c96ac76`,
identical to the `vendor_dlkm_a` provider at the same hash, vermagic
6.1.78-android14-11-maybe-dirty) that the stock `vendor_boot` already
contributes to the combined image at `/lib/modules/msm_sharedmem.ko`. It is
never rebuilt or substituted. The new phase insmods it as-is (its
`modules.dep` prerequisites `qcom-scm`, `gh_rm_drv`, `gh_msgq`, `gh_dbl`,
`gh_arm_drv` are all inside the unchanged 127-module order), then records
whether the sharedmem client device appears (`uio` name `rmtfs`) and whether the
kernel log carries `Device created for client 'rmtfs'`. If the stock module
cannot be loaded as-is, the phase logs the exact insmod error, sets
`/run/rmtfs.status` to `failed` and no rmtfs starts — fail closed, reported,
not worked around.

The LZ4 envelope (2,117,632 B) had only 22,448 B spare and the new rmtfs binary
alone compressed to +56,764 B, so the three static services (pd-mapper,
tqftpserv from #95, rmtfs) are stored **xz-compressed** in the cpio and a
reconstruction step unpacks each one and checks its full SHA-256 against the
pinned binary hash *before* the byte-identical #86 phase runs. The #86 phase is
therefore unchanged as delivered by #95 — it launches the exact #95 binaries —
and the #96 phase (sharedmem insmod, device check, backing links, rmtfs launch)
runs strictly after the #86 phase and before `console ready`, i.e. after SSH is
up and before any remoteproc2 start. All services log to `/run`:
`/run/rmtfs.log`, `/run/rmtfs.status` (`rmtfs-published`/`failed`) plus the
unchanged #95 `/run` logs. The 127-module order, read-only mounts, WPSS
supplier/bind gate, single WLAN load, USB/key-only SSH and the 150 s
self-recovery timer are unchanged.

Two serial builds produced identical images: debug cpio 3,667,456 B (zero
`.ko`), one LZ4 HC-12 legacy frame 2,094,175 B (limit 2,117,632 B; 23,457 B
spare); stock header except the ramdisk-size field, zero gap, same stock signed
tail from offset 2,121,728 (6,266,880 B), fixed 8,388,608-B image.
`verify-init-boot-rmtfs-sharedmem.py` independently decodes and rebuilds
against the run-35 image, proves the exact init/cpio delta and the byte-exact
reconstruction of all three binaries, checks the ordering (recon before the
unchanged #86 phase, rmtfs phase after it and before console ready), the
envelope, prefix, gap, tail and size, and rejects missing/altered/nonexecutable
services, an altered stock module, missing/moved/reordered phases, missing
backing links, a removed QRTR-publish or reconstruction-hash check, an
init-time remoteproc start and all 51 previously measured SHAs (explicitly
8dddb8c7, 35866d56, ae2ccff7, 4216af26). It is wired into `verify-bootimg.sh`.

```sh
WORK="$HOME/sm7635-build" scripts/build-rmtfs-binary.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-rmtfs-sharedmem.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes, not observations:** the physical coordinator
alone (standing `full_autonomy_device_iteration` approval) flashes the **new**
`bf2089c4…` SHA to `init_boot_a` only, pins host `172.16.42.1/24`, passes the
capture selftest (omnipha/agents#16 gate), then over SSH confirms: the
reconstruction log lines, `/dev/uioN` with name `rmtfs` and the kernel
`Device created for client 'rmtfs'` line, `rmtfs` alive with
`rmtfs: published QRTR service` in `/run/rmtfs.log`, `/run/rmtfs.status` =
`rmtfs-published`, and the unchanged #95 services still published — all before
one guarded `echo start > remoteproc2/state` with continuous host capture.
(a) modem holds past +60 s and `wlan0` appears — the rmtfs/sharedmem hypothesis
is confirmed; (b) the same ~40 s DOG recurs with rmtfs published — the
rank-1 candidate is excluded as the single dependency (next candidate = new
issue, no rerun of #96); (c) new fatal text — recorded verbatim. Either result
requires the coordinator's measured Sahara reset/timer recovery and verified
stock rollback of all five partition hashes. `bf2089c4` and every previously
measured SHA are never-reflash after the run. The issue stays open until that
capture-gated single result and rollback proof are recorded.

## Stock-map pd-mapper + tqftpserv session init_boot (#86, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. Run 34 already
measured `35866d56…` and verified rollback; that SHA, `ae2ccff7…`,
`4216af26…`, `bde3a3b3…`, `6078269d…` and every other measured SHA are
rejected for reuse. No physical access, flash, remoteproc operation, new
`modem_a` read, kernel build, boot_a/dtbo/vbmeta/slot-B or rmtfs/sharedmem
change occurred in #86.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-pdmapper-tqftpserv.img` | 8,388,608 | `8dddb8c714dce40c2795c95103236d8af9cfdc8ef00aaa6b6723055e41de09d1` |
| `$HOME/sm7635-build/out/pd-mapper` | 199,008 | `40acf0b06856205cb6cb9d53084afe5f6619fd1330c13242be1464b1dede3f43` |
| `$HOME/sm7635-build/out/tqftpserv` | 132,592 | `4eacb4ae30fe9c1ee3078bf140bd391c0179c2e8599461c67636d26006313965` |

The binaries are static musl 1.2.5 aarch64, compiled from pinned upstream
sources with one explicit post-publish log line each (`pd-mapper: published
QRTR service ...` and `tqftpserv: published QRTR service ...`): `qrtr` v1.2 (`b51ffaf22707b6000ecfb894c5b750f3bb7843b2`),
`pd-mapper` v1.1 (`5ecd2fe926aca7abfe40724177f63b942cff3947`) and
`tqftpserv` v1.3 (`b31de6db4f31d09119293203d39636b827f16321`), with
liblzma from xz 5.6.4. The host build verifies source tarball hashes,
cross-builds twice, checks ELF static/aarch64/size/sha and smoke-tests
tqftpserv under qemu-aarch64. It does not import firmware from Git.

`modem_a` is the single already-pinned #89 read (367,001,600 B,
`08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`).
The six `.jsn` are re-extracted read-only by #92's merged extractor under
`~/phone-second-life-data/mb003/acquire/attempt-20261025-0632-modem-a/issue-86-maps`;
manifest `verdict=PASS`, `synthetic=false`, `jsn_under_image=6`,
`jsn_outside_image=0`, all six #89-recorded SHA-256s checked before packaging.
The **byte-exact** `image/{adspr,adsps,adspua,battmgr,cdspr,modemr}.jsn` are
included at `etc/pd-mapper/` in the cpio. Upstream pd-mapper consumes those
individual stock map files (not the extractor's aggregate JSON) via its
non-Android `/lib/firmware` search. At runtime the new init compares the
stock read-only-mounted `modem_a` map files byte-for-byte with the cpio
copies and checks their recorded hashes before it bind-mounts the stock
firmware image at `/lib/firmware` read-only. No upstream example map is used.

The new `/init` equals the decoded run-34 #83 `/init` with the session
marker reworded and one new phase *after* the key-only SSH/listener block
and *before* `console ready`. It starts `/bin/pd-mapper` and
`/bin/tqftpserv -d` in the background only when the stock maps and both
executables are available, logs launch and PID lines to kmsg and
`/run/pd-mapper.log` + `/run/tqftpserv.log`, then waits at most 5 s for
both explicit QRTR publish lines and live PIDs before writing
`/run/qrtr-services.status` (`qrtr-published` or `failed`). Missing/mismatched
maps, mount, binaries or publish lines fail closed. The physical coordinator
must check the processes, the logs, and QRTR publication before proceeding.
The publish line itself is the evidence of a successful QRTR bind; its absence
after 5 s is a hard stop. No init-time remoteproc2 start or
`/run/keep` creation is added. The 127-module order, corrected read-only
mounts, WPSS supplier/bind gate, single WLAN load, USB/key-only SSH and the
150 s self-recovery timer are unchanged. Kernel QRTR nameserver is already
in `qrtr.ko`, no separate qrtr-ns service added. The 150 s userspace timer
cannot protect against the expected kernel panic.

Two serial builds produced identical images: debug cpio 3,838,464 B,
SHA-256 `9cc1a1996604d72fd42b3e2321ad1ad2f0c28c0b2abe6a63636364638ad7539a`,
zero `.ko`; one LZ4 HC-12 legacy frame 2,095,184 B (limit 2,117,632 B;
22,448 B spare); stock header except ramdisk-size field, zero gap, same
stock signed tail from offset 2,121,728 through terminal AVBf (6,266,880
B), fixed 8,388,608-B image. `verify-init-boot-pdmapper-tqftpserv.py`
independently decodes and rebuilds against the run-34 image, proves exact
init/cpio delta, executable ELF and config bytes, ordering and `/run` logs,
checks the signed-tail/prefix/frame/size, and rejects missing/altered
binaries/maps, missing/moved phase or marker, init-time remoteproc control,
and all 50 previously measured SHAs. It is wired into `verify-bootimg.sh`.

```sh
WORK="$HOME/sm7635-build" scripts/build-pdmapper-tqftpserv-binaries.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-pdmapper-tqftpserv.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes, not observations:** The physical coordinator
alone (standing `full_autonomy_device_iteration` approval) flashes the **new**
SHA to `init_boot_a` only, pins host `172.16.42.1/24`, proves the capture
selftest on a live console line, confirms both services running and QRTR
publication in their `/run` logs/status, then issues one guarded remoteproc2
start with continuous host capture. If modem stays up beyond +60 s and
`wlan0` appears, the pd-mapper/tqftp hypothesis is supported. If the same
~40 s DOG recurs despite both QRTR services running, this pair is not the
single missing dependency; rmtfs/sharedmem is a *separate* successor
experiment, not a second run in #86. If the fatal text differs, record it
rather than forcing either interpretation. Either result requires the
coordinator's measured Sahara reset/timer recovery and **verified stock
rollback of all five partition hashes**. The issue stays open until that
capture-gated single result and rollback proof are recorded.

## Capture-gated retry session init_boot (#83, host-only, 2026-10-25)

**Host result:** one session init_boot candidate built and verified; no physical
boot, `wlan0` result, modem result or fatal text is claimed. The measured #81
session image (`ae2ccff7`) is consumed by run 33 and must never be reflashed,
like the measured #79 image (`4216af26`), the #77 image (`560c98e5`) and the #75
image (`5a61de0e`). This issue performed no device access, flash, USB, modem
control, kernel rebuild, DTBO/vbmeta/slot-B change or userdata work. This branch
(`issue-83-retry-marker`) is based on the head of PR #82,
`issue-81-live-fatal-stream` at `99e4e53`, so the diff against that base is only
the #83 marker change; `main` (`c5811e7`) does not yet contain the #81/#82 work
and is not rebased onto.

### Facts, separated from the hypothesis

Run 33 (#81, coordinator-flashed `ae2ccff7…`, `init_boot_a` only) measured over
key-only SSH on the stock 6.1.84 kernel with the #81 init: a modem-off baseline
with `remoteproc2` offline and `wlan0` absent, `/run/keep` set by the SSH worker,
and one guarded `remoteproc2` start reaching `running` in ~1 s with `wlan0`
absent through +30 s. SSH died between +30 s and +35 s and the device entered
crash mode `05c6:900e` at +65 s — the same stalled-initialization boundary as
run 32. The fatal text was **not captured for the third time**: the
session-capture service never became ready (`accept-new` host-key handling vs
`BatchMode`) and the fallback `/dev/kmsg` stream did not advance past its old
backlog, so end-to-end capture readiness was never proven before the guarded
start. Recovery is measured (Sahara reset plus the 150 s timer to fastboot,
pstore pulled before Android, verified stock rollback). The host-side capture
blocker is fixed and merged (omnipha/agents#16, `07cba236`): verified host-key
provisioning, classified SSH errors and a mandatory
`selftest --marker ... --timeout` that proves a live console line reaches the
host capture before any crash-prone step.

The **one discriminating variable** in this image is the session marker and
nothing else. The decoded `/init` is the exact measured #81 init (`ae2ccff7`)
with only the marker log line reworded, `session #83: capture-gated retry -
selftest marker proves a live console line before the guarded start`, in place
of the #81 line, at the same position immediately after the armed 150 s
self-recovery timer and before the module phase. That single string change
forces a SHA-256 distinct from the measured `ae2ccff7` image and from every
other measured SHA. Everything else is unchanged: the three-module supplier
phase and order, the 12 s bounded WPSS/icnss2 bind gate, the corrected read-only
super and firmware mounts, the single stock WLAN load, the 21-module WLAN closure
and the 127-module vendor closure, the RESTART2 helper, the peripheral/UDC path
and the USB key-only SSH path. The timer is armed before any risky step and is
not extended; the init never creates `/run/keep` — only the SSH worker may, and
only after key-only SSH, the host link and the capture `selftest` are verified.
No init-time remoteproc start, no `rmmod` and no module reload is added.

The coordinator flashes this image to `init_boot_a` only (stock
boot_a/vendor_boot_a/dtbo_a/vbmeta_a), pins `172.16.42.1/24` and marks both
gadget links unmanaged **before** the reboot. After key-only SSH verifies and
`/run/keep` is set, the coordinator runs the merged capture tooling's
`selftest --marker ... --timeout` until it proves a live console line reaches the
host capture. **Only then** one guarded `remoteproc2` start (only if `offline`),
with the continuous capture running through the expected loss. Recovery from a
repeat of the run-33 failure mode is measured: Sahara reset plus timer-to-
fastboot, pstore pulled before Android, verified stock rollback.

**The 150 s userspace timer does not cover the expected kernel panic.** Run 31
showed the stalled-initialization fatal ends in a kernel panic and crash mode; a
userspace `sleep`-based RESTART2 timer cannot run in that state and must not be
represented as protection against it. Crash recovery stays coordinator-owned
(host-side Sahara reset, measured in runs 32 and 33).

### Predicted physical outcomes

A later physical measurement could distinguish exactly these outcomes. None of
them authorizes a second start, a restart or a module reload inside #83;
physical measurement is separate and coordinator-gated.

| observed outcome | interpretation |
| --- | --- |
| The stream captures the complete fatal text with its preceding lines | The fatal text names the stalled subsystem; the successor issue targets that dependency specifically. |
| `wlan0` appears before +40 s | The WLAN driver question is answered; the modem stall becomes a separate, lower-priority track. |
| The stream dies with no fatal line and the modem stays running past +60 s | The crash boundary moved; re-baseline before any new variable. |

Stop when one is recorded live: the complete fatal text with its preceding
lines; `wlan0` present; or a named icnss2/QMI probe failure with the modem still
running at +60 s.

### Reproducible host artifact

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-retry-marker.img` | 8,388,608 | `35866d569e3aabe62698bad924ab0cd649f0bf89cafdf41e520af7964b10f466` |

Two independent serial invocations of `scripts/build-init-boot-retry-marker.sh`
each built and compared two byte-identical candidates. Both invocations gave the
same SHA above, distinct from the measured `ae2ccff7` #81 image and from every
previously recorded measured SHA (including `4216af26`, `560c98e5`, `5a61de0e`,
`e5b99b7c`, `9291c369`, `2faab7e2`, `995aaca3`, `be946562`, `86402ac6`,
`9f89fe8d`, `88c93077`, `8f8b7331`, `bde3a3b3` and `6078269d`). The stock
`init_boot_a` prefix differs only at the ramdisk-size field; one LZ4 HC-12 legacy
block (1,934,339 bytes) carries a 3,498,496-byte debug cpio (SHA-256
`7531c17fc871bdcfccc1f61067801f1200d27d9d611b5a537523bffc458eecbb`), with no
`.ko` embedded, a zero gap and the unchanged stock signed tail from offset
2,121,728 (6,266,880 bytes). The vendor_boot suppliers stay pinned by full
SHA-256, size and stock ramdisk identity.

`scripts/verify-init-boot-retry-marker.py` fails closed. It rebuilds the
measured #81 image (`ae2ccff7`) in memory from the frozen inputs and proves that
the decoded `/init` delta is exactly the one session log line (the #83 marker
substituting the #81 marker, −84/+109 bytes) and nothing else. Negative fixtures
reject a missing, duplicated, moved, reworded, renumbered or second session
marker, the reused #81 and #79 marker texts, the rebuilt measured `ae2ccff7`
image and its reused SHA, a `/run/keep` created before the timer or before
verified SSH, an init-time remoteproc start (including the #77 phase
reintroduced), any `rmmod` or `modprobe`, a removed, shortened, lengthened or
disabled 150 s timer, a missing, duplicated, reordered or unbounded supplier
phase, a removed or lengthened bind gate, a truncated or repeated WLAN load,
envelope or tail damage, the reused measured #75, #77, #79 and #81 inits, and
every reused measured SHA including `ae2ccff7`. A host-only simulated-clock test
of the extracted timer proves both outcomes: with no SSH/keep the timer runs
`RESTART2 bootloader` (and the `reboot -f` fallback) at 150 s, and with verified
SSH the worker's keep exists before the deadline. Aggregate `verify-bootimg.sh`
passed (exit 0; 182 `: OK` lines including the #83 negative fixtures).

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-retry-marker.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Integration note (#91, 2026-10-25):** PR #84 merged into the
`issue-81-live-fatal-stream` branch, not `main`; this section, the builder and
the verifier are carried to `main` byte-identical by issue #91 after #82/#87/#90
merged. Nothing above is re-measured or altered by that integration. The image
was subsequently flashed once (run 34) and the physical outcome — the capture
selftest proving a live console line in 0.884 s before the single guarded
`remoteproc2` start, the complete DOG fatal text captured live from
`qcom_q6v5_pas 4080000.remoteproc-mss` at ~+41 s with `wlan0` absent through
+30 s, Sahara recovery and verified stock rollback — is already recorded in
issue #83; `35866d56` is measured and must never be reflashed. The successor
analysis is [docs/modem-fw-init-dependency.md](docs/modem-fw-init-dependency.md)
(#85/#87). The #91 integration performed no device access, flash, USB, modem
control, kernel rebuild, DTBO/vbmeta/slot-B change or userdata work, and only
re-ran the host-only selftest and aggregate verification against the existing
`35866d56` artifact.

## Live-session init_boot for the continuous fatal-text stream (#81, host-only, 2026-10-25)

**Host result:** one session init_boot candidate built and verified; no physical
boot, `wlan0` result, modem result or fatal text is claimed. The measured #79
session image (`4216af26`) is consumed by run 32 and must never be reflashed,
like the measured #77 image (`560c98e5`) and the measured #75 image
(`5a61de0e`). This issue performed no device access, flash, USB, modem control,
kernel rebuild, DTBO/vbmeta/slot-B change or userdata work. PR #80 (the #79
record) is unmerged and untouched; this branch is based on `main` at `c5811e7`.

### Facts, separated from the hypothesis

Run 32 (#79, coordinator-flashed `4216af26…`, `init_boot_a` only) measured over
key-only SSH on the stock 6.1.84 kernel: a >71 s modem-off baseline with
`remoteproc2` offline, `wlan0` absent, stable dmesg, `icnss2` probed OK at
1.43 s, `qca_cld3` v5.2.1.94A loaded and no named icnss2/QMI probe failure.
One guarded `remoteproc2` start reached `running` in ~1 s; `wlan0` stayed
absent at +1/+11/+31 s with no new probe lines. SSH died ~33-40 s after the
start (the known stalled-initialization boundary, matching the run-31 pstore
`Dog_hal_common.c:178: DOG detects stalled initialization, triage with IMAGE
OWNER` fatal) and the device entered crash mode. The worker capture was polled,
so no fatal line was read before the link died; crash recovery via host-side
Sahara reset and the 150 s timer worked without a button press, stock
`init_boot_a` rollback was hash-proven on all five slot-A partitions, and stock
Android reached `boot_completed=1`. The pstore console pulled before Android
held only a later stock Android console: the crash console of the guarded-start
fatal was overwritten, so **no new pstore read can name the stalled
subsystem — the name must come from a live capture**.

The **one discriminating variable** in this image is the session marker and
nothing else. The decoded `/init` is the exact measured #75 init (`5a61de0e`
stack) plus one log line, `session #81: fatal-stream run - host dmesg -w opened
before the guarded start`, placed immediately after the armed 150 s
self-recovery timer and before the module phase. This forces a SHA-256 distinct
from the reused `4216af26` session image and from every other measured SHA.
Everything else is unchanged: the three-module supplier phase and order, the
12 s bounded WPSS/icnss2 bind gate, the corrected read-only super and firmware
mounts, the single stock WLAN load, the 21-module WLAN closure and the
127-module vendor closure, the RESTART2 helper, the peripheral/UDC path and the
USB key-only SSH path. The timer is armed before any risky step and is not
extended; the init never creates `/run/keep` — only the SSH worker may, and
only after key-only SSH and the host link are verified. No init-time remoteproc
start, no `rmmod` and no module reload is added.

The coordinator flashes this image to `init_boot_a` only (stock
boot_a/vendor_boot_a/dtbo_a/vbmeta_a), pins `172.16.42.1/24` and marks both
gadget links unmanaged **before** the reboot, and opens a persistent host-side
`ssh root@172.16.42.2 "dmesg -w"` stream (optionally a second stream polling
`wlan0` every 5 s) **during the modem-off baseline**, writing every line to a
host file outside the repo and keeping the stream running through one guarded
`remoteproc2` start and the expected SSH loss. Note the wall-clock of the last
received line. The continuous stream should capture the fatal text as it is
emitted, before the USB death that ended the polled run-32 capture. Recovery
from a repeat of the run-32 failure mode is measured: Sahara reset plus
timer-to-fastboot, pstore pulled before Android, verified stock rollback.

**The 150 s userspace timer does not cover the expected kernel panic.** Run 31
showed the stalled-initialization fatal ends in a kernel panic and crash mode;
a userspace `sleep`-based RESTART2 timer cannot run in that state and must not
be represented as protection against it. Crash recovery stays coordinator-owned
(host-side Sahara reset, measured in run 32).

### Predicted physical outcomes

A later physical measurement could distinguish exactly these outcomes. None of
them authorizes a second start, a restart or a module reload inside #81;
physical measurement is separate and coordinator-gated.

| observed outcome | interpretation |
| --- | --- |
| The stream captures the complete fatal text with its preceding lines | The fatal text names the stalled subsystem; the successor issue targets that dependency specifically. |
| `wlan0` appears before +40 s | The WLAN driver question is answered; the modem stall becomes a separate, lower-priority track. |
| The stream dies with no fatal line and the modem stays running past +60 s | The crash boundary moved; re-baseline before any new variable. |

Stop when one is recorded live: the complete fatal text with its preceding
lines; `wlan0` present; or a named icnss2/QMI probe failure with the modem
still running at +60 s.

### Reproducible host artifact

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-live-fatal-stream.img` | 8,388,608 | `ae2ccff760b47efd1663fea6d6e614e2e1523ccdfcd258612354b2ceb4baf47e` |

Two independent serial invocations of `scripts/build-init-boot-live-fatal-stream.sh`
each built and compared two byte-identical candidates. Both invocations gave the
same SHA above, distinct from every previously recorded measured SHA (including
the reused `4216af26`, `560c98e5`, `5a61de0e`, `e5b99b7c`, `9291c369`,
`2faab7e2`, `995aaca3`, `be946562`, `86402ac6`, `9f89fe8d`, `88c93077`,
`8f8b7331` and the vendor_boot `bde3a3b3`/`6078269d`). The stock `init_boot_a`
prefix differs only at the ramdisk-size field; one LZ4 HC-12 legacy block
(1,934,326 bytes) carries a 3,498,496-byte debug cpio (SHA-256
`36da887f499dcfb394515586cce82ccefa48b1ca5bce8c603a3861beb8abe580`), with no
`.ko` embedded, a zero gap and the unchanged stock signed tail from offset
2,121,728 (6,266,880 bytes). The vendor_boot suppliers stay pinned by full
SHA-256, size and stock ramdisk identity.
`scripts/verify-init-boot-live-fatal-stream.py` fails closed; negative fixtures
reject a missing, duplicated, moved, reworded or second session marker, the
reused #79 marker text, a `/run/keep` created before the timer or before
verified SSH, an init-time remoteproc start (including the #77 phase
reintroduced), any `rmmod` or `modprobe`, a removed, shortened, lengthened or
disabled 150 s timer, a missing, duplicated, reordered or unbounded supplier
phase, a removed or lengthened bind gate, a truncated or repeated WLAN load,
envelope or tail damage, the reused measured #75, #77 and #79 inits, and every
reused measured SHA including `4216af26`. A host-only simulated-clock test of
the extracted timer proves both outcomes: with no SSH/keep the timer runs
`RESTART2 bootloader` (and the `reboot -f` fallback) at 150 s, and with
verified SSH the worker's keep exists before the deadline. Aggregate
`verify-bootimg.sh` passed (exit 0; 176 `: OK` lines including the #81 negative
fixtures).

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-live-fatal-stream.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

## One guarded modem remoteproc start before the WLAN probe (#77, host-only, 2026-10-24)

**Host result:** one init_boot candidate built and verified; no physical boot or
`wlan0` result is claimed. The physical coordinator restored stock `init_boot_a`
(SHA prefix `baa33fd4`) after run 30; the measured #75 image (`5a61de0e`) and
the measured #71 image (`e5b99b7c`) must not be reflashed. This issue performed
no device access, flash, USB, modem control, kernel rebuild, DTBO/vbmeta/slot-B
change or userdata work.

### Facts, separated from the hypothesis

Run 30 (#75, merged PR #76) measured over key-only SSH that the three supplier
modules loaded in order and that WPSS, the regulator and `icnss2` were bound at
~1.589 s, with the ipci gate reporting `icnss2` bound after 0 s and
`qca_cld3` v5.2.1.94A loaded. `wlan0` was absent at 63 s and at 73 s uptime.
That is the #75 outcome "both bind, `wlan0` absent": loading the suppliers before
the probe is **not** the WLAN blocker. Stock `init_boot_a` was then restored and
verified.

The only remaining lead comes from the separate run 29 (recorded by merged PR
#74) and stays a **hypothesis, not a measurement**: after the same supplier chain
and `wpss_boot=1`, `icnss2` logged `DMS QMI connection not established`,
`Unable to get MAC from DMS after retries` and a probe failure of `-1` while the
modem remoteproc `remoteproc2` (`4080000.remoteproc-mss`) read `offline`. The
later attempt to start that modem and reload the WLAN module lost SSH before any
read-back, so its outcome is **unmeasured**. Nothing here establishes that the
modem supplies the DMS service, or that `wlan0` follows.

The **one discriminating variable** in this image is whether starting that modem
remoteproc exactly once, before the single stock WLAN probe, is sufficient for
`wlan0` to appear. The #75 init is changed only inside the final
`qca_cld3_qca6750.ko` branch, after the unchanged supplier phase and the
unchanged 12 s icnss2 bind gate and before the single existing insmod. The new
phase logs `modem start phase begin`, skips with a logged reason when
`/sys/class/remoteproc/remoteproc2` is absent, and otherwise reads the remoteproc
`name` and `state` (each with a 2 s timeout). It writes `start` exactly once to
`/sys/class/remoteproc/remoteproc2/state` (10 s timeout, errors clipped to 160
bytes) only when the state reads `offline`; a `running` modem and every other
state are left untouched and logged as skipped. It then logs the resulting state.
No `rmmod`, module reload, stop, restart or any other remoteproc write is added.
The corrected read-only super/firmware mounts, 21-module WLAN closure and order,
127-module vendor closure, 150 s self-recovery timer, RESTART2 helper,
peripheral/UDC path and USB key-only SSH are unchanged. The phase adds at most
20 s (three 2 s reads and one 10 s write, each with 1 s kill grace) on top of
the existing 12 s gate; the 150 s timer is not extended. The exact
decoded `/init` delta against #75 is this one phase and nothing else.

### Predicted physical outcomes

A later physical measurement could distinguish exactly these outcomes. None of
them authorizes another variable inside #77; physical measurement is separate and
coordinator-gated, with the existing self-recovery and stock rollback procedure.

| observed outcome | interpretation |
| --- | --- |
| The modem remoteproc fails to start or stays offline | The logged `modem start write failed` or `modem state after start` line names the first blocker; no inference about DMS or `wlan0` follows. |
| The modem reaches `running` but `wlan0` stays absent | Starting the modem before the probe was not sufficient; the DMS/MAC explanation stays an unmeasured hypothesis, and the existing WLAN probe/dmesg logs are the next evidence. |
| `wlan0` appears | The single pre-probe modem start was sufficient in that physical run; preserve the observed record. |

### Reproducible host artifact

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-modem-start.img` | 8,388,608 | `560c98e5909af99921122610f4ce1b1899030685b32ae1b7d32991181f628749` |

Two independent serial invocations of `scripts/build-init-boot-modem-start.sh`
each built and compared two byte-identical candidates. Both invocations gave the
same SHA above, distinct from all previously recorded measured SHAs (including
`5a61de0e`, `e5b99b7c`, `9291c369`, `2faab7e2`, `995aaca3`, `be946562`,
`86402ac6`, `9f89fe8d`, `88c93077`, `8f8b7331`, `bde3a3b3`, `6078269d`). The
stock `init_boot_a` prefix differs only at the ramdisk-size field; one LZ4 HC-12
legacy block (1,934,557 bytes) carries a 3,500,032-byte debug cpio (SHA-256
`b3cfceff84bb036fa29ee2af2fd74b2284d62280d1b388d7ffc9fc89a3c3a53e`), with no
`.ko` embedded, a
zero gap and the unchanged stock signed tail from offset 2,121,728 (6,266,880
bytes). The vendor_boot suppliers stay pinned by full SHA-256, size and stock
ramdisk identity. `scripts/verify-init-boot-modem-start.py` fails closed;
negative fixtures reject a missing, duplicated, moved, unguarded, retargeted or
unbounded modem start, a stop, a restart or any other remoteproc write, any
`rmmod`, a repeated WLAN or remoteproc module load, supplier/gate/timer
regressions, envelope or tail damage, and every reused measured SHA including
`5a61de0e`. Aggregate `verify-bootimg.sh` passed (exit 0).

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-modem-start.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

## WPSS supplier phase before the WLAN probe (#75, host-only, 2026-10-24)

**Host result:** one init_boot candidate built and verified; no physical boot or
`wlan0` result is claimed. The physical coordinator restored stock `init_boot_a`
(SHA prefix `baa33fd4`) after run 29; the measured #71 image (`e5b99b7c`)
must not be reflashed. This issue performed no device access, flash, USB,
modem control, kernel rebuild, DTBO/vbmeta/slot-B change or userdata work.

### Facts and discriminating variable

Run 29 (#73, merged PR #74) observed over key-only SSH that `smp2p.ko` was
present in the stock vendor_boot ramdisk but unloaded, leaving WPSS deferred on
`slave-kernel`. Volatile `insmod /lib/modules/smp2p.ko` bound WPSS to
`qcom_q6v5_pas`. The icnss2 device then remained deferred behind the
`soc:pm3001a-s1j` fixed regulator; volatile
`insmod /lib/modules/pinctrl-spmi-gpio.ko` followed by
`insmod /lib/modules/qti-fixed-regulator.ko` bound that regulator and icnss2.
A subsequent stock WLAN load and `wpss_boot=1` brought the WPSS firmware up,
but `wlan0` was not observed and icnss2 reported DMS MAC lookup failure. The
later modem start and WLAN reload lost SSH before post-retry read-back: their
outcome is **unmeasured** and not replicated here.

The **one discriminating variable** in this image is whether loading the three
measured supplier modules *before the first stock WLAN probe* is sufficient
for WPSS and icnss2 to bind and for `wlan0` to appear without a WLAN reload.
The #71 init is changed only inside the final `qca_cld3_qca6750.ko` branch:
its single supplier phase attempts `smp2p.ko`, then `pinctrl-spmi-gpio.ko`,
then `qti-fixed-regulator.ko`, each from stock `/lib/modules/`, guarded by
`/sys/module/<name>` and file readability, with a 2 s insmod timeout and 1 s
kill grace. Each module is logged as already present, loaded, missing or failed
(with errors clipped to 160 bytes). Immediately afterward the phase logs
WPSS (`9bb00000.remoteproc-wpss`), regulator (`soc:pm3001a-s1j`) and icnss2
(`17110040.qcom,wcn6750`) platform driver bind states. The unchanged #71 gate
then waits at most 12 s for icnss2 bind, logs WPSS and icnss2 again, and
performs the *single* existing qca_cld3 insmod. No `rmmod`, module reload or
remoteproc control is added. The corrected read-only super/firmware mounts,
21-module WLAN closure and order, 127-module vendor closure, 150 s self-recovery
timer, RESTART2 helper, peripheral/UDC path and USB key-only SSH are unchanged.
The supplier loads consume at most 9 additional seconds; the prior 12-second
gate and 150-second timer are not extended. The exact decoded `/init` delta
against #71 is this one phase and nothing else.

**Hypothesis, not a host measurement:** this pre-probe supplier chain could let
the two platform probes complete on first load. It does not establish that
DMS provides a MAC, that modem is needed, or that WLAN creates an interface.
A later physical measurement could distinguish exactly these outcomes:

| observed outcome | interpretation |
| --- | --- |
| A supplier module fails to load | Its named `supplier … failed` log identifies the first blocker; no inference about `wlan0` follows. |
| WPSS or icnss2 remains unbound | The supplier/bind chain still fails; the phase and gate logs identify which platform device remains unbound. |
| WPSS and icnss2 both bind but `wlan0` stays absent | Supplier binding alone was insufficient; check the existing WLAN probe/dmesg logs, without assuming the DMS/modem explanation. |
| `wlan0` appears | First-load supplier ordering was sufficient in that physical run; preserve the observed record. |

**No outcome authorizes another variable inside #75.** Physical measurement is
separate and coordinator-gated, with the existing self-recovery and stock
rollback procedure; no additional image or module retry is part of this issue.

### Reproducible host artifact

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-wpss-supplier.img` | 8,388,608 | `5a61de0e39d4cc8f985d38f0be2e39ce3054cae3b94a5fc64df9617f93e563ed` |

Two independent serial invocations of `scripts/build-init-boot-wpss-supplier.sh`
each built and compared two byte-identical candidates. Both invocations gave
the same SHA above, distinct from all 45 recorded measured SHAs (including
`e5b99b7c`, `9291c369`, `2faab7e2`, `995aaca3`, `be946562`, `86402ac6`,
`9f89fe8d`, `88c93077`, `8f8b7331`, `bde3a3b3`, `6078269d`). The stock
`init_boot_a` prefix differs only at ramdisk size; one LZ4 HC-12 legacy block
(1,934,271 bytes) carries a 3,498,496-byte debug cpio (SHA-256
`b057cab6888953d1fd437556bd7f50df4832b5fdd23e3c96a48b054885d1a03d`),
with no `.ko` embedded, a zero gap and the unchanged stock signed tail from
offset 2,121,728 (6,266,880 bytes). The vendor_boot suppliers are pinned by
full SHA-256, size and stock ramdisk identity. The verifier rejects envelope,
header, gap, signed-tail, module-order, gate and timer regressions; negative
fixtures reject missing, duplicated, reordered or unbounded supplier loads,
missing already-loaded guards, any `rmmod`, repeated WLAN/remoteproc insmod,
modem control, and each reused measured SHA. Aggregate `verify-bootimg.sh`
passed (exit 0; 171 `: OK` lines including the #75 negative fixtures).

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wpss-supplier.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

## Live WPSS supplier diagnosis and WLAN dead end (run 29, #73, 2026-10-24)

**Measured over key-only SSH on the coordinator's existing `e5b99b7c…` session,
not from a new image:** the missing `smp2p.ko` load kept
`9bb00000.remoteproc-wpss` deferred. Volatile module loads cleared the WPSS
and icnss2 supplier chains, and WPSS firmware initialized, but `wlan0` was
never observed. The session's SSH link disappeared during a subsequent WLAN
driver retry. No new image was built or verified: no end-to-end WLAN sequence
worked, and packaging a candidate while the coordinator has not restored or
ended the session is not warranted. The coordinator owns the pending verified
stock `init_boot_a` rollback. No partition write, flash, USB diagnostic, kernel
rebuild, or userdata action was performed by this worker.

### Observed supplier chain

- Before intervention, `/sys/kernel/debug/devices_deferred` reported
  `9bb00000.remoteproc-wpss platform: wait for supplier slave-kernel` (the
  adsp/cdsp/mss remoteprocs reported the same reason). The device-tree
  `soc/qcom,smp2p-wpss/slave-kernel` node had `qcom,entry-name`, while
  `/sys/bus/platform/devices/soc:qcom,smp2p-wpss/driver` was absent.
  `/lib/modules/smp2p.ko` was present but `lsmod` did not list `smp2p`.
  `insmod /lib/modules/smp2p.ko` returned 0; the WPSS platform device gained
  a `qcom_q6v5_pas` driver symlink, `remoteproc3` became available, and all
  four remoteprocs disappeared from `devices_deferred`. This establishes the
  absent **smp2p** provider of `slave-kernel` as the immediate WPSS blocker,
  not `qcom_scm`, `qcom_aoss`, or the unrelated deferred GPU GDSC.
- `17110040.qcom,wcn6750` then remained deferred as `supplier
  soc:pm3001a-s1j not ready`; the fixed regulator itself reported `wait for
  supplier s1j_enable_default`. Its PMIC pinctrl supplier lacked a driver.
  `insmod /lib/modules/pinctrl-spmi-gpio.ko` followed by
  `insmod /lib/modules/qti-fixed-regulator.ko` returned 0. The fixed regulator
  bound to `reg-fixed-voltage`, icnss2 bound to `17110040.qcom,wcn6750`, and
  both disappeared from `devices_deferred`.
- The first stock WLAN module load at boot had already failed while icnss2 was
  unbound. The subsequent `insmod
  /mnt/vendor_dlkm/lib/modules/qca_cld3_qca6750.ko` returned 0 after icnss2
  bound. The WPSS remoteproc was still `offline`, and there was no `wlan0`.
  `echo 1 > /sys/bus/platform/devices/17110040.qcom,wcn6750/wpss_boot`
  returned 0; `remoteproc3/state` read `running`. Dmesg reported
  `Booting fw image qca6750/wpss.mdt`, `remote processor
  9bb00000.remoteproc-wpss is now up`, `QMI Server Connected`, and `WLAN FW
  Initialization done`. `icnss2/stats` then recorded one `SERVER_ARRIVE`,
  one `FW_READY`, one `FW_INIT_DONE`, and one `REGISTER_DRIVER` event.

### Dead end and next single blocker

After FW initialization, `/sys/class/net/` still had no `wlan0`. Dmesg
repeated `icnss2_qmi: DMS QMI connection not established`, then logged
`icnss2: Unable to get MAC from DMS after retries` and `Driver probe failed:
-1`. At that point `4080000.remoteproc-mss` (`remoteproc2`) was `offline`.
`echo start > /sys/class/remoteproc/remoteproc2/state` returned 0 and its
state became `running`. A following `rmmod qca_cld3_qca6750; insmod
/mnt/vendor_dlkm/lib/modules/qca_cld3_qca6750.ko` returned 0 for both
commands, but SSH timed out before the requested post-retry observations and
remained unreachable on subsequent key-only attempts. No claim is made about
whether the modem supplied DMS, whether `wlan0` appeared after SSH was lost,
or what caused the link loss.

**Hypothesis, not measurement:** the unavailable DMS QMI service prevents the
required NV MAC lookup and WLAN probe; the modem remoteproc was offline at
the time of the failure. The pinned vendor icnss2 source has a `use-nv-mac`
DT property for this platform, and `icnss_setup_dms_mac()` retries DMS then
fails the probe if no MAC is provided. Starting the modem might supply DMS,
but its `running` state alone does not establish that. The **next single
blocker** is a coordinator-restored key-only live session in which DMS/MAC
availability and `wlan0` are checked while the modem is already running;
without that session the post-retry result cannot be measured. Do not repeat
the measured init_boot SHA or treat the lost SSH link as proof of WLAN success
or a particular crash. No new image is warranted until a working result is
measured in a live session.

## Bounded icnss2/WPSS bind gate on the run-28 init (#71, host-only, 2026-10-24)

**Host success: one bounded bind gate before the final `qca_cld3_qca6750.ko`
insmod, and one new reproducible stock-envelope init_boot.** No device, adb,
fastboot, USB, flash or userdata operation was performed. No kernel, vbmeta,
dtbo or slot-B artifact changed. The 127-module order, one peripheral write,
UDC wait, NCM+ECM addresses, key-only sshd, 150 s `/run/keep` timer and
`bin/restart2` are unchanged. This section records a host candidate, not a boot
result: the physical coordinator measures it under the standing approval.

### 1. Run-28 evidence and source determination

Run 28 (`attempt-20261024-1032-initboot-wlanrfkill`, image `9291c369…`, pstore
console-ramoops-0, 119,929 bytes) reached key-only SSH at 10:35 and USB
enumeration, then returned to fastboot on the 150 s timer; rollback to stock
`init_boot_a` was verified. Measured facts from that console:

- `system_dlkm_a`, `vendor_a` and `vendor_dlkm_a` all mounted read-only erofs
  (1.532–1.544 s), `modem_a` mounted read-only vfat at `/vendor/firmware_mnt`
  and `qca6750/bdwlan.elf` was present (1.553–1.557 s).
- All 21 closure modules were logged. `qcom_q6v5_pas.ko` loaded at 1.576 s,
  `rfkill.ko` at 1.585 s, `cfg80211.ko` at 1.604 s and `icnss2.ko` at 1.636 s,
  each with no unknown-symbol error. `cfg80211` logged `failed to load
  regulatory.db` with error -2.
- `qca_cld3_qca6750: Loading driver v5.2.1.94A +PANIC_ON_BUG` at 1.691 s, then
  `wlan_pld:pld_register_driver:305:: Fail to register ipci driver` at 1.693 s,
  and the init logged `module qca_cld3_qca6750.ko failed:` at 6.802 s — 5.11 s
  later. `wlan0` was absent.
- At 11.749 s the deferred-probe list still named `9bb00000.remoteproc-wpss`,
  `17110040.qcom,wcn6750`, `3d68024.qcom,gdsc`, `soc:pm3001a-s1j` and the
  adsp/cdsp/mss remoteprocs. No panic occurred.

The stock command line carries `fw_devlink.strict=1`. In the pinned vendor tree
the ipci failure is the last transport in `pld_register_driver`
(`vendor/qcom/opensource/wlan/qcacld-3.0/core/pld/src/pld_common.c:303-307`),
which calls `icnss_register_driver`. `__icnss_register_driver`
(`vendor/qcom/opensource/wlan/platform/icnss2/main.c:3331-3376`) returns
`-EAGAIN` at `:3337-3341` when `icnss_get_plat_priv()` is NULL, and that pointer
is only set at the end of a successful `icnss_probe`
(`icnss2/main.c:5095`). The HDD loader retries only that error, 50 times at
100 ms (`qcacld-3.0/core/hdd/src/wlan_hdd_main.c:20306-20330`), which is the
measured 5.11 s gap. The platform node `qcom,wcn6750`
(`vendor/qcom/proprietary/wlan-devicetree/volcano-qca6750.dtsi:33-38`) names
`qcom,rproc-handle = <&wpss_pas>`, and `wpss_pas` is
`remoteproc-wpss@9bb00000` with `compatible = "qcom,volcano-wpss-pas"`
(`arch/arm64/boot/dts/vendor/qcom/volcano.dtsi`). `adsp_probe`
(`drivers/remoteproc/qcom_q6v5_pas.c:1621-1622`) returns `-EPROBE_DEFER` while
`qcom_scm_is_available()` is false, and the kernel prints `deferred probe
pending` when the default 10 s deferred-probe timeout fires
(`drivers/base/dd.c:306-319`).

Hypothesis, not measured: the ipci registration failed because `icnss2` had not
finished probing while its strict supplier `remoteproc-wpss` was still deferred.
The alternative, a transport or DT mismatch, is not supported by anything in the
log: the `-ENODEV` path at `icnss2/main.c:3356-3360` prints
`not supported by platform driver`, and that text is absent from the run-28
console. Both remain leads until the next measurement.

### 2. The one discriminating variable

The discriminating variable is the platform-driver bind state of
`17110040.qcom,wcn6750` (icnss2) and `9bb00000.remoteproc-wpss` at the moment
`qca_cld3_qca6750.ko` registers its ipci driver. Everything else in the run-28
init is unchanged. Immediately before that one `insmod`, and only for that
module, the init now waits at most 12 s for
`/sys/bus/platform/devices/17110040.qcom,wcn6750/driver` to appear, then logs
exactly one of `ipci gate: wpss bound` or `ipci gate: wpss unbound` and exactly
one of `ipci gate: icnss2 bound after N s` or `ipci gate: icnss2 unbound after
N s`, and then performs the same single stock `insmod`.

Expected outcomes on the next physical measurement:

| observation | lead it supports | next step |
| --- | --- | --- |
| `icnss2 bound` and `module qca_cld3_qca6750.ko loaded`, with `Registering driver` in the wlan dmesg and `wlan0 present` | supplier/probe timing: the platform probe completed inside the wait | keep the gate; the next blocker is whatever the now-visible probe logs |
| `wpss bound` but `icnss2 unbound after 12 s`, and the same ipci failure | timing is not the whole story: the supplier bound but icnss2 still did not probe | the icnss2 probe's own deferred suppliers, not the WLAN stack |
| `wpss unbound` and `icnss2 unbound after 12 s`, same ipci failure | the WPSS remoteproc never leaves deferred state in this environment | the WPSS supplier chain (`qcom_scm`, `aoss_qmp`, smem states, the also-deferred `3d68024.qcom,gdsc` and `soc:pm3001a-s1j`), not the WLAN stack |
| `icnss2 bound` yet the ipci registration still fails, with `not supported by platform driver` or `devinfo is null` in the wlan dmesg | transport/DT mismatch: the device id the module registers does not match the probed platform | the `qcom,wcn6750` compatible and the module's `pld_ipci` device table |

The 150 s timer is unchanged. Run 28 spent 5.35 s to the module-load-end line
and the USB path had already enumerated, so the worst case this gate adds is
12 s, leaving the key-only SSH path its measured margin.

### 3. The image

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `init_boot-ipci-defer.img` | 8,388,608 | `e5b99b7c04b85aee66a0ac295ee1a94a0d5dd208f8c7b0f4112fc0cd3f78fc5d` |

The image keeps the stock prefix apart from the ramdisk-size field, carries one
LZ4 HC-12 legacy frame (1,934,024 bytes) of the 3,497,472-byte debug cpio
(SHA-256 `91e36163…e6d8`) at offset 4096, a zero gap and the unchanged signed
tail from offset 2,121,728. Two separate builds are byte-identical. This SHA
differs from `9291c369`, `2faab7e2`, `995aaca3`, `be946562`, `86402ac6`,
`9f89fe8d`, `88c93077`, `8f8b7331`, `bde3a3b3`, `6078269d` and every earlier
measured image.

`scripts/verify-init-boot-ipci-defer.py` fails closed. Negative fixtures reject
a removed, duplicated, retargeted, lengthened, unbounded or post-insmod bind
gate, a removed WPSS check or gate log line, the run-27 loop-minor regression,
rfkill from the wrong partition, cfg80211 before rfkill, a planted `.ko`, a
removed or lengthened timer, a removed wlan-init marker, envelope or tail
damage, and every repeated prior SHA including `9291c369` and `2faab7e2`.
`scripts/verify-bootimg.sh` runs it. `bash -n`, `shellcheck`,
`python3 -m py_compile` and `git diff --check` are clean.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-ipci-defer.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

Physical measurement of this new SHA is owned solely by the physical
coordinator under the standing `full_autonomy_device_iteration` approval:
`init_boot_a` only, host pins `172.16.42.1/24` first, then verified rollback.
No successful boot is claimed for `e5b99b7c…` until that measurement records
key-only SSH.

## WLAN rfkill and firmware mounts on the corrected run-27 init (#69, host-only, 2026-10-24)

**Host success: one corrected wlan-init stage fixes the measured run-27 mount
failures and packages one distinct, reproducible stock-envelope init_boot.**
No device, adb, fastboot, USB, flash or userdata operation was performed. No
kernel, vbmeta, dtbo or slot-B artifact changed. The 127-module order, one
peripheral write, UDC wait, NCM+ECM addresses, key-only sshd, 150 s `/run/keep`
timer and `bin/restart2` are unchanged.

### 1. Run-27 evidence and source determination

Run 27 (`attempt-20261024-0836-initboot-wlanclosure`, image `2faab7e2…`) mounted
`vendor_dlkm_a` read-only EROFS and loaded 18 of 21 closure modules, with SSH
held. It then logged `mount vendor_a read-only: failed` and `mount
system_dlkm_a read-only: failed`, followed by `rfkill.ko failed: missing …`.
The stock cmdline contains `loop.max_part=7`, so each loop device consumes eight
minors. The old init created `/dev/loop8`, `/dev/loop9` and `/dev/loop10` with
minor equal to index. Device 8 aliased loop1, while 9 and 10 hit loop1 partition
slots, explaining the two failures. The measured by-name table places `super` on
`/dev/block/sda6` and `modem_a` on `/dev/block/sde6`; it has no `vendor_a` or
`system_dlkm_a` entries. Primary LP metadata confirms both missing filesystems
are linear extents inside that one super device:

| source | block device | byte offset | bytes | probed type |
| --- | --- | ---: | ---: | --- |
| `system_dlkm_a` | super `/dev/block/sda6` | 4,797,235,200 | 11,804,672 | erofs |
| `vendor_a` | super `/dev/block/sda6` | 5,678,039,040 | 1,269,284,864 | erofs |
| `vendor_dlkm_a` | super `/dev/block/sda6` | 6,947,864,576 | 32,669,696 | erofs |
| firmware | by-name `modem_a` `/dev/block/sde6` | whole partition | measured stock partition | vfat |

Host read-only mounts of the pinned super dump verify all three extents as
erofs. `system_dlkm_a` contains `rfkill.ko` (63,817 bytes, SHA-256
`773ddddb360d8de4212da9a327124e97f5b8fe94626a82e44fdcfb689adabb47`). `vendor_a`
does not contain `bdwlan.elf`; its `firmware_mnt` entry is a mountpoint. The
stock recovery command mounts by-name `modem_a` read-only vfat at
`/vendor/firmware_mnt`, which is the stock path
`/vendor/firmware_mnt/image/qca6750/bdwlan.elf`. No second super loop is used.

### 2. The single wlan-init change

The frozen run-24 init and the existing 21-module closure order remain. The
stage now:

1. derives each loop node's major:minor from `/sys/block/loopN/dev`, rather than
   guessing minor equals index;
2. probes each super extent (erofs magic `e2e1f5e0` at byte 1024, otherwise ext4
   magic `53ef` at byte 1080, otherwise skips) and mounts `system_dlkm_a`,
   `vendor_a` and `vendor_dlkm_a` read-only with matching options;
3. probes by-name `sde6` for `PARTNAME=modem_a` and a FAT signature, then mounts
   it read-only vfat at `/vendor/firmware_mnt` and logs whether
   `qca6750/bdwlan.elf` is present;
4. `insmod`s `rfkill.ko` from the pinned system_dlkm path before `cfg80211.ko`,
   then keeps the existing closure, per-module results, wlan interface check,
   capped wlan dmesg and firmware-name log.

No `.ko` enters init_boot. The 150 s timer is unchanged.

### 3. The image

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `init_boot-wlan-rfkill.img` | 8,388,608 | `9291c369ec78b081c6445b3ee85431fa9a01e2e757a59337cfd165eca741c2f3` |

The image keeps the stock prefix apart from ramdisk size, carries one LZ4 HC-12
legacy frame (1,933,841 bytes) of the 3,496,960-byte debug cpio (SHA-256
`9f1bf645…a6db`) at offset 4096, a zero gap and the unchanged signed tail from
offset 2,121,728. Two consecutive builds are byte-identical. This SHA differs
from `2faab7e2`, `995aaca3`, `be946562`, `86402ac6`, `9f89fe8d`, `88c93077`,
`8f8b7331` and every earlier measured image.

`scripts/verify-init-boot-wlan-rfkill.py` fails closed. Negative fixtures reject
the run-27 minor guess, an assumed filesystem, a removed mount, a second super
loop, rfkill from the wrong partition, rfkill absent, cfg80211 before rfkill,
an unprobed or moved firmware mount, a planted `.ko`, timer changes, marker
changes, envelope or tail damage, and every repeated prior SHA including
`2faab7e2`. `scripts/verify-bootimg.sh` runs it. `bash -n`, `shellcheck`,
`python3 -m py_compile` and `git diff --check` are clean.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wlan-rfkill.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

Physical measurement of this new SHA is owned solely by the physical
coordinator under the standing `full_autonomy_device_iteration` approval:
`init_boot_a` only, host pins `172.16.42.1/24` first, then verified rollback.

## Stock WLAN closure load from super on the run-24 init (#67, host-only, 2026-10-24)

**Host success: the frozen run-24 init (initramfs/init, the #53 line) gains one
wlan-init phase that mounts the stock super logical partitions read-only and
insmods the measured stock WLAN module closure, and one new init_boot image was
assembled and verified host-only.** No device, adb, fastboot, USB, flash or
userdata operation was performed. Stock `boot_a`, `vendor_boot_a`, `dtbo`,
`vbmeta` and slot B are unchanged. The 127-module load order, the single
`peripheral` role write, the 40 × 0.25 s UDC wait, the NCM+ECM addresses
172.16.42.2/24 and 172.16.43.2/24, the key-only sshd, the 150 s `/run/keep`
timer and `bin/restart2` are unchanged. Every previously measured SHA stays
unreused; the new image SHA below is a first measurement.

### 1. The stock WLAN closure, measured from the slot-A super dump

The input is the coordinator's slot-A `super` dump (9,663,676,416 bytes, SHA-256
`7307e9ff…d8c`, matching the on-device `super` hash). Its LP metadata (magic
`0PLA` v10.2, tables SHA-256 `6450425f…a251`, identical in all six metadata
slots) names 14 logical partitions with seven single linear slot-A extents and
empty slot B. The three partitions this phase uses:

| partition | byte offset | bytes | filesystem |
| --- | ---: | ---: | --- |
| `vendor_dlkm_a` | 6,947,864,576 | 32,669,696 | erofs |
| `vendor_a` | 5,678,039,040 | 1,269,284,864 | erofs |
| `system_dlkm_a` | 4,797,235,200 | 11,804,672 | erofs |

`vendor_a/lib/modules` is a symlink to `/vendor_dlkm/lib/modules`, so every
vendor module lives in `vendor_dlkm_a`. The closure is computed from that
partition's `modules.dep` and `modules.load` for the five targets
`qcom_q6v5_pas.ko`, `qca_cld3_qca6750.ko`, `icnss2.ko`,
`cnss_plat_ipc_qmi_svc.ko` and `qrtr-smd.ko`, topologically ordered with
`modules.load` as the tie-break. The first target is the WPSS remoteproc
driver: the live FDT gives `qcom,wcn6750` a `qcom,rproc-handle` to
`remoteproc-wpss@9bb00000` (`compatible = "qcom,volcano-wpss-pas"`),
`qcom_q6v5_pas.ko` carries the matching `of:N*T*Cqcom,volcano-wpss-pas`
alias, and the measured stock console registers `9bb00000.remoteproc-wpss`
at 2.346 s, before `icnss2` probes at 2.399 s. With `fw_devlink.strict=1` on
the stock command line the icnss2 probe defers until that supplier binds, so
it belongs to the closure even though `modules.dep` does not name it. Nothing
in `modules.blocklist` names any of them (it names only `qca_cld3_kiwi`, a
module this device does not load); `modules.softdep` names `qcom_q6v5_pas`
once, as a `pre:` of the unrelated audio module `q6_notifier_dlkm`, which is
not in this closure. The closure list SHA-256 is `c4268566…af73`.

| # | module | bytes | source | status |
| ---: | --- | ---: | --- | --- |
| 1 | `qmi_helpers.ko` | 106,544 | `drivers/soc/qcom/qmi_encdec.c`, `qmi_interface.c` | already in the 127-module recovery closure |
| 2 | `qcom_ramdump.ko` | 24,736 | `drivers/soc/qcom/qcom_ramdump.c` | new, from `vendor_dlkm_a` |
| 3 | `qcom_pil_info.ko` | 18,408 | `drivers/remoteproc/qcom_pil_info.c` | new, WPSS remoteproc closure |
| 4 | `qcom_glink.ko` | 98,136 | `drivers/rpmsg/qcom_glink_native.c` | already loaded |
| 5 | `qcom_glink_smem.ko` | 19,848 | `drivers/rpmsg/qcom_glink_smem.c` | already loaded |
| 6 | `qcom_smd.ko` | 43,496 | `drivers/rpmsg/qcom_smd.c` | already loaded |
| 7 | `rproc_qcom_common.ko` | 65,912 | `drivers/remoteproc/qcom_common.c` | already loaded |
| 8 | `pdr_interface.ko` | 38,480 | `drivers/soc/qcom/pdr_interface.c` | already loaded |
| 9 | `qcom_sysmon.ko` | 45,384 | `drivers/remoteproc/qcom_sysmon.c` | new, WPSS remoteproc closure |
| 10 | `qcom_q6v5.ko` | 28,264 | `drivers/remoteproc/qcom_q6v5.c` | new, WPSS remoteproc closure |
| 11 | `qcom_q6v5_pas.ko` | 129,560 | `drivers/remoteproc/qcom_q6v5_pas.c:2919` (`qcom,volcano-wpss-pas`) | new, WPSS remoteproc supplier of icnss2 |
| 12 | `rfkill.ko` | 63,817 | `net/rfkill/core.c` | new, from `system_dlkm_a` |
| 13 | `cfg80211.ko` | 2,143,864 | `net/wireless/` | new, from `vendor_dlkm_a` |
| 14 | `qrtr-smd.ko` | 17,648 | `net/qrtr/smd.c` | new, from `vendor_dlkm_a` |
| 15 | `cnss_plat_ipc_qmi_svc.ko` | 49,448 | `vendor/qcom/opensource/wlan/platform/cnss_utils/` | new, from `vendor_dlkm_a` |
| 16 | `wlan_firmware_service.ko` | 93,336 | `vendor/qcom/opensource/wlan/platform/cnss_utils/` | new, from `vendor_dlkm_a` |
| 17 | `cnss_nl.ko` | 15,832 | `vendor/qcom/opensource/wlan/platform/cnss_genl/cnss_nl.c` | new, from `vendor_dlkm_a` |
| 18 | `cnss_prealloc.ko` | 20,400 | `vendor/qcom/opensource/wlan/platform/cnss_prealloc/` | new, from `vendor_dlkm_a` |
| 19 | `icnss2.ko` | 406,320 | `vendor/qcom/opensource/wlan/platform/icnss2/` | new, from `vendor_dlkm_a` |
| 20 | `cnss_utils.ko` | 33,288 | `vendor/qcom/opensource/wlan/platform/cnss_utils/cnss_utils.c` | new, from `vendor_dlkm_a` |
| 21 | `qca_cld3_qca6750.ko` | 17,065,984 | `vendor/qcom/opensource/wlan/qcacld-3.0/` | new, from `vendor_dlkm_a` |

The 20 vendor_dlkm modules total 20,464,888 bytes; with `rfkill.ko` the phase
loads 20,528,705 bytes. `rfkill.ko` is not in the `vendor_dlkm` closure because
`modules.dep` never names it, but `cfg80211.ko` declares `depends=rfkill` in its
`.modinfo` and imports seven `rfkill_*` symbols, and the stock console loads it
from `system_dlkm` (`…/kernel/net/rfkill/rfkill.ko`, 63,817 bytes, vermagic
`6.1.84-android14-11-gf4b0d69fdf34-ab12786779`) before cfg80211 runs. It is
therefore loaded immediately before `cfg80211.ko`, from the same super image,
rather than guessed.

Two cross-checks narrow the closure. Nine of the twenty vendor_dlkm names
(`qmi_helpers`, `qcom_ramdump`, `qcom_glink`, `qcom_glink_smem`, `qcom_smd`,
`rproc_qcom_common`, `pdr_interface`, `cfg80211`, `qrtr-smd`) also ship in the
stock `vendor_boot_a` recovery ramdisk, and all nine are byte-identical
(SHA-256) to the `vendor_dlkm_a` copies, so loading from either source is the
same stock binary. The measured stock console cross-checks the names: it shows
`q6v5_pdev`/`9bb00000.remoteproc-wpss` registering at 2.346 s,
`icnss2 17110040.qcom,wcn6750` probing at 2.399 s, `cnss_plat: CNSS Platform
IPC QMI Service is started` at 2.504 s, `qca_cld3_qca6750: Loading driver
v5.2.1.94A` at 2.605 s and `qca6750/wpss.*` firmware loads at 5.04-5.29 s on
this device, and `qrtr-smd`/`qrtr-mhi`/`cnss_plat_ipc_qmi_svc` are its measured
QMI transport set.

Unknowns, recorded rather than guessed:

- **The modem partition firmware.** The measured stock console serves
  `qca6750/bdwlan.elf` and `qca6750/wpss.*` from `/vendor/firmware_mnt/image`,
  which is the `modem_a` partition (`/dev/block/sde6`), not part of `super`.
  This image does not mount it and ships no firmware; the `wlan-init:` firmware
  name log records what the kernel actually requests.
- **The captured `config.gz` says `# CONFIG_QRTR is not set`** while
  `qrtr-smd.ko` declares `depends=qrtr` and the stock kernel loads it, so the
  trimmed config does not describe the built-in provider set. `qrtr.ko` itself
  is already in the 127-module recovery closure and is loaded before this phase.

### 2. The wlan-init phase

The phase is inserted into the frozen run-24 init immediately before
`log 'console ready'`, after the unchanged module load, role write, UDC wait,
gadget, address and listener steps. It:

1. creates `/dev/block/sda6` from `/sys/class/block/sda6/dev` if the node is
   missing, then requires `blockdev --getsize64` to return exactly
   9,663,676,416;
2. hashes five pinned 4 KiB pages of `sda6` (the LP geometry page, the LP
   metadata page and the first page of each of the three extents, each carrying
   the erofs magic) and skips every mount if any page differs;
3. maps each verified extent read-only through a loop device and mounts it
   `erofs -o ro,nosuid,nodev,noexec`, falling back to
   `ext4 -o ro,noload,nosuid,nodev,noexec` only if erofs fails;
4. walks the 21-module list in the order above, skips a module that is already
   present under `/sys/module`, and otherwise `insmod`s it from `vendor_dlkm_a`
   (or from the pinned `system_dlkm_a` path for `rfkill.ko`), logging
   `wlan-init: module <name> loaded`, `loaded (already present)` or
   `failed: <err>` (a module whose file is absent is logged as
   `failed: missing <path>`) with the log count capped at 64;
5. logs whether `/sys/class/net/wlan0` exists and whether `iw dev` is available
   in busybox, then scans `dmesg` for `icnss2|cnss_plat|qca_cld3|bdwlan` lines
   and for firmware-load names, each capped at 64, logging names only.

Every step is time-bounded: 2 s (+ 1 s kill grace) for the size check, each
page hash and each `losetup`; 3 s for each mount and for the `dmesg` scan; 2 s
(+ 1 s kill grace) for each `insmod`.

### 3. Timer-budget arithmetic

The 150 s `/run/keep` timer is unchanged. The measured anchors are the run-24
console reaching `console ready` at 1.415 s
(`attempt-20261023-1624-initboot-staticaddress`) and the stock WLAN sequence
(`attempt-20261022-1305-boota-imagesize`): `icnss2` probed at 2.399 s,
`qca_cld3_qca6750: Loading driver` at 2.605 s, `qca6750/bdwlan.elf` served at
5.734 s and `WLAN FW Initialization done` at 5.748 s — about 3.35 s of
WLAN-specific work once the drivers are resident. The worst case the new bounds
allow is 3 s for the size check, 15 s for the five page hashes, 9 s for the
three loop setups, 24 s for the three erofs mounts and their ext4 fallbacks, 63
s for the twenty-one module loads and 4 s for the dmesg scan: 118 s, which still
leaves 32 s of the 150 s budget for the unchanged USB and SSH path. The measured
sequence needs far less than that, so the timer constant is not raised.

### 4. The image

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `init_boot-wlan-closure.img` | 8,388,608 | `2faab7e2d4069d5f908e292d0a5d17e0be86a09ce91efc9e6aececfb0c6872bf` |

The image keeps the stock `init_boot_a` prefix apart from the ramdisk-size
field, carries one Android LZ4 legacy frame (LZ4 HC level 12, 1,933,289 bytes,
one block) of the debug cpio at offset 4096, a zero gap, and the stock signed
tail unchanged from offset 2,121,728. The debug cpio is 3,494,912 bytes, SHA-256
`b27a58cd…cdaf1`, and contains zero `.ko` files: every module is read from the
stock partitions at boot. Two consecutive builds are byte-identical.

`scripts/verify-init-boot-wlan-closure.py` fails closed. Its negative fixtures
reject a wrong WLAN module order, a planted `.ko`, a removed mount, a writable
mount flag, a removed or lengthened timer, a changed sshd, a changed address, a
changed gadget function, a second role write, a changed 127-module order,
removed or duplicated wlan-init markers, a bad envelope or tail, and every
repeated prior SHA including `995aaca3`, `be946562` and `86402ac6`.
`scripts/verify-bootimg.sh` runs it. `bash -n`, `shellcheck`,
`python3 -m py_compile` and `git diff --check` are clean.

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-wlan-closure.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

### 5. Predicted pstore outcomes

For the physical coordinator, flashing `init_boot_a` = `2faab7e2…` only, with
stock `boot_a`, `vendor_boot_a`, `dtbo`, `vbmeta` and slot B untouched:

1. **SSH plus every WLAN marker through `WLAN FW Initialization done`.** The
   stock `icnss2`/`qca_cld3` driver reaches firmware initialization on the stock
   kernel with no kernel or DT change; the next step is IP configuration over
   SSH, not a new image.
2. **`icnss2` probes but no QMI or firmware marker follows.** The first blocker
   is the QMI/firmware path — expected if the unmounted `modem_a` firmware is
   what the driver needs.
3. **Module load stops at a named module.** The capped `wlan-init: module
   <name> failed:` line names it; the first blocker is version or closure.
4. **The partitions mount but no module matches.** The `failed: missing`
   lines name the absent path; the first blocker is module identification.
5. **The existing USB/SSH path regresses.** No SSH, or the gadget markers
   disappear; that is an integration bug and the experiment stops.

## Early-kernel-boundary attribution and the initcall_debug diagnostic image (#63, host-only, 2026-10-24)

**Host success: the last retained run-25 console line `Actions configured` at
`T=0.148408` is attributed to `init_u32()`, entry 787 of the 997-entry initcall
table of the built 6.1.78 kernel; the 47,362-byte excerpt uses 2.258% of the
2 MiB stock ramoops console zone with its `[0.000000]` head intact, zero NUL
bytes and a cleanly LF-terminated last line, so every truncation mechanism
measured here is excluded and a genuine early stop between initcall entries 787
and 863 is the hypothesis most consistent with the evidence. The single
diagnostic variable is the `initcall_debug` token appended to `CONFIG_CMDLINE`;
the new kernel gzips to 13,806,507 bytes, 160,853 bytes under the 13,967,360-byte
signed-tail bound, and the new boot and init_boot images were assembled and
verified host-only with new never-measured SHAs.** No device, adb, fastboot,
USB, flash or userdata operation was performed. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. Every previously
measured SHA stays unreused; the run-25 SHAs `0ca048d5…` and `cafcabb6…` are now
also rejected by the new verifiers.

### 1. Attribution of the retained console tail (evidence, observation, hypothesis)

**Evidence (pinned vendor tree `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, file:line):**

- `u32 classifier`, `input device check on` and `Actions configured` are printed
  by the single initcall `init_u32()` at `net/sched/cls_u32.c:1455-1480`
  (`pr_info` at :1459/:1463/:1465), registered via `module_init(init_u32)`
  (:1488), which `include/linux/module.h:88` maps to `__initcall(x)` →
  `device_initcall` level 6 (`include/linux/init.h:291,296`). The built config
  has `CONFIG_NET_CLS_U32=y`, `CONFIG_NET_CLS_ACT=y` and `CLS_U32_PERF` off, so
  exactly these three lines print (the `Performance counters on` line is
  compiled out).
- The `.initcall` PREL32 table was decoded from the built `vmlinux` against
  `System.map` (997 entries: 34 early, 5 pure, 68 core, 36 postcore, 30 arch,
  161 subsys, 57 fs, 525 device, 81 late; identical ordering in the #59 and
  #63 builds). `init_u32` is entry **787**. The entries that follow in the same
  ordering: **788** `init_fw` (`net/sched/cls_fw.c:435`), **789** `init_basic`
  (`cls_basic.c:330`), **790** `cls_flow_init` (`cls_flow.c:704`), **791**
  `cls_bpf_init_mod` (`cls_bpf.c:695`), **792** `cls_mall_init`
  (`cls_matchall.c:404`), **793-797** `init_em_cmp`/`init_em_nbyte`/
  `init_em_u32`/`init_em_meta`/`init_em_text` (`em_cmp.c:80`, `em_nbyte.c:61`,
  `em_u32.c:45`, `em_meta.c:999`, `em_text.c:140`), **798** `nfnetlink_init`,
  **799-800** `nfnetlink_queue_init`/`nfnetlink_log_init`, **801-816** the
  conntrack/NAT initcalls, **817** `xt_init` (`net/netfilter/x_tables.c:1980`),
  **818-862** the x_tables match/target registrations including **863**
  `time_mt_init` (`net/netfilter/xt_time.c:275`, prints `xt_time: kernel
  timezone is -0000`), **867** `ipip_init` (`net/ipv4/ipip.c:606`), **869**
  `ipgre_init` (`ip_gre.c:1728`), **890** `xfrm_user_init`
  (`net/xfrm/xfrm_user.c:3811`), **891** `xfrmi_init`
  (`xfrm_interface_core.c:1181`), **892** `inet6_init`, **909** `packet_init`,
  **912** `vsock_init`, **915** `finalize_pkvm` (last level-6 entry). Level 7
  then runs **916-996**, ending with `pstore_init` (963), `clk_debug_init`
  (971), `deferred_probe_initcall` (973, `drivers/base/dd.c:371`),
  `clk_disable_unused` (993), `regulator_init_complete` (994) and
  `alsa_sound_last_init` (996, last overall).
- Subsystems visible in the log tail relative to the boundary: Gunyah
  `gh_dbl_init`/`ghd_msgq_init`/`gh_rm_driver_init` (entries 744-747; the
  0.146069 `Running under Gunyah hypervisor 51/v1` line is printed from
  `drivers/virt/gunyah/rsc_mgr.c:812`) run **before** the boundary; interconnect
  `qnoc_driver_init` (core level, entry 100, `drivers/interconnect/qcom/volcano.c:2306`),
  `icc_init` (757, `core.c:1168`), `qcom_icc_bcm_voter_driver_init` (758) and
  `qcom_icc_debug_init` (759) run before it, while the 0.087 s
  `failed to register ICC provider: -517` deferrals would only be retried by
  `deferred_probe_initcall` at entry 973 (**after**, never reached); dma-heap
  `dma_heap_init` (subsys, entry 277, `drivers/dma-buf/dma-heap.c:470`) and
  `init_heap_driver` (device, entry 614, `qcom_dma_heap.c:163`) run before it,
  and the 0.141960 `probe of soc:qcom,dma-heaps failed with error 1` is a
  probe error 6 ms before the boundary, not at it; clocks `gdsc_init` (264) and
  `gcc_volcano_init` (265, `drivers/clk/qcom/gcc-volcano.c:3496`) run before it,
  while `clk_disable_unused` (993) is after and never reached. No Gunyah,
  dma-heap, clock or interconnect initcall sits between entries 787 and 863; the
  silent window is entirely netfilter/net-sched plus generic entries.

**Observation (run-25 capture, read-only host copy):** the retained excerpt ends
`[0.148403][T1] u32 classifier` / `[0.148406][T1] input device check on` /
`[0.148408][T1] Actions configured`, all on `T1` (swapper/init, pid 1 — the
initcall-running task). The runtime order in the capture matches the decoded
table order (`GACT` 0.148361 = entry 773, `Mirror/redirect` 0.148371 = 774,
`netem` 0.148380 = 783, u32 = 787). The stock 6.1.84 reference console reaches
the same three lines at 0.149940-0.149943 and its **next** output line is
`xt_time: kernel timezone is -0000` at 0.161479 (entry 863 in the own build's
table). The stock kernel has a different config and initcall table, so this
shows only that on stock nothing printed between the u32 lines and `xt_time`;
it does not prove entries 788-862 of the own build are silent. Stock then logs
`Run /init as init process` at 0.169768.

**Hypothesis (separate from the above):** execution of the own 6.1.78 kernel
stopped at or shortly after `init_u32`, inside the window bounded by entry 787
(`init_u32`) and entry 863 (`time_mt_init`), i.e. roughly between 0.1484 s and
0.1615 s, before `kernel_init_freeable()` (`init/main.c:1591-1622`) could print
`Run /init`. Which of the three sub-variants holds — a hang inside `init_u32`
after its printks (its remaining work is a `kvmalloc_array` and
`register_tcf_proto_ops`, `cls_u32.c:1467-1479`), a hang in one of entries
788-862, or a silent reset with the last printks simply being the final output —
cannot be distinguished from this capture; that is exactly what the item-3
change measures.

### 2. Why the excerpt stops at 0.148 s (evidence, observation, hypotheses)

**Evidence — geometry is identical to the runs that captured full consoles.** The
own boot image keeps all 20 stock vendor DTBs byte-identical and lets stock
`dtbo_a` entry 65 supply the ramoops reservation (`verify-bootimg.sh` fails
closed on `reg = <0 81f20000 0 400000>`, `console-size = <0x200000>`,
`pmsg-size = <0x200000>`). Base `volcano.dtsi:2912-2918` defines `size
0x200000`, `pmsg-size 0x200000`, `mem-type 2` and no `reg`; overlay
`volcano-arca-common-overlay.dtsi:14-22` adds the 4 MiB `reg`,
`console-size 0x200000` and `pmsg-size 0x200000`. Neither defines
`ftrace-size`, `record-size`, `ecc-size` or `erase-block-size`; `ramoops_parse_dt`
(`fs/pstore/ram.c:675-690`) defaults every missing u32 to 0, so probe math
(`ram.c:781-827`) yields dump area `4 MiB - 2 MiB - 0 - 2 MiB = 0` →
`max_dump_cnt = 0` → no dmesg record region (consistent with only
`console-ramoops-0`/`pmsg-ramoops-0` ever appearing), a 2 MiB console zone that
is already a power of two (no `rounddown_pow_of_two` shrink, `ram.c:762-763`),
and `ecc: 0` (`ram.c:862-864`), which makes erase-block semantics irrelevant to
the layout. Both the own kernel (0.067209-0.067239) and the stock reference
(0.068077-0.068648) log the same `ramoops: using 0x400000@0x81f20000, ecc: 0`.

**Observation — the capture is complete for what it holds.** 47,362 bytes =
2.258% of the 2,097,152-byte console zone; head intact from `[0.000000] Booting
Linux on physical CPU`; zero NUL bytes; last line cleanly `\n`-terminated; the
file carries the own-kernel 6.1.78 banner and the `sm7635-boot-marker` cmdline;
the device-side `listing.txt` shows the same 47,362 bytes, so the pull is
complete. Comparable stock-kernel captures: 834,645 bytes (39.8% of the zone,
last ts 618.6 s, 0 NUL), 1,395,603 bytes (66.5%, last ts 1,402.9 s, 3 NUL,
interleaved ring overwrite), 113,761 bytes (5.4%, last ts 356.7 s, 4 NUL).
Console writes are synchronous per printk (`persistent_ram_write` at
`ram.c:317`, `memcpy_toio` at `ram_core.c:274-278`) — there is no deferred
flush to lose at reset. No panic/oops/watchdog line appears in the excerpt
(`CONFIG_PANIC_TIMEOUT=-1`, vendor `panic=-1`); a panic would normally log into
this console first, but a hard hang or an external reset would leave no such
line, so its absence does not discriminate between those.

**Hypothesis H1 — genuine early stop (hang or silent reset) at ~0.148 s:**
most consistent. The excerpt ends exactly at an initcall boundary; the next
expected line in the stock ordering (`xt_time`, entry 863) is absent; userspace
was never reached (no `Run /init`), so the initramfs 150 s self-recovery timer
never armed; and the coordinator's observe log shows fastboot reappear ~112 s
after the reboot command (01:27:59 → 01:29:51), which is consistent with a
bootloader/watchdog fallback after a stalled kernel but equally with a reset;
the cause of that return is not observed. Sub-variants: (a) hang inside `init_u32` after its
printks, (b) hang in one of entries 788-862, (c) silent hypervisor/hardware
reset that cut output after the last emitted line. Not yet distinguishable —
that is the item-3 measurement.

**Hypothesis H2 — capture truncation (lost at reboot):** every measured variant
is excluded. (a) Ring wrap/overwrite: 2.258% zone use with the `[0.000000]` head
intact is incompatible with wrapping, which produces mid-line splices and NULs
as seen in the stock ring files. (b) Flush loss at reset: writes are
synchronous. (c) Overwrite by a later boot: `PRZ_FLAG_ZAP_OLD`
(`ram.c:589`, `ram_core.c:510-545`) zaps the console PRZ at each new kernel
start, and the pulled file still carries the own-kernel banner, so it *is* the
failing session's capture, not a partial replacement. (d) Geometry difference
from the >100 s runs: excluded above — identical DTB/overlay numbers. (e)
Truncated pull: device and host sizes match. Conclusion: H2 does not survive the
numbers; H1 is the working hypothesis, with the exact stop location inside
entries 787-863 to be pinned by the next measurement.

### 3. The single variable: `initcall_debug` on the diagnostic kernel cmdline

`configs/asteroids-diagnostic-initcall-debug.fragment` is one line: the #59
marked `CONFIG_CMDLINE` plus the token ` initcall_debug`, merged last. Chosen
over the issue's alternatives because it is **measurement-only**: `init/main.c:13`
defines `DEBUG` and `:790-791` declares the `core_param`, so the token is parsed
in `start_kernel`'s `parse_args` (`init/main.c:973`) before
`initcall_debug_enable()` (`:1034-1035`, `:1256-1266`, requires
`CONFIG_TRACEPOINTS=y`, which the config has) registers the callbacks that make
`do_one_initcall` (`:1284-1295`) print `calling  <fn> @ <pid>` and
`initcall <fn> returned <n> after <t> usecs` for **every** entry, all levels,
including the level-6 neighborhood above. The callbacks print at `KERN_DEBUG`;
`suppress_message_printing()` (`kernel/printk/printk.c:1204-1207`) does not
suppress them because the stock vendor_boot cmdline already supplies
`ignore_loglevel` (run-25 line 7: `printk: debug: ignoring loglevel setting.`),
so no loglevel change is needed. `CONFIG_KALLSYMS=y` (kept since #60) resolves
`%pS` to real names. Output lands in the same 2 MiB ramoops console that already
proved it works up to 0.148 s.

Rejected alternatives: `initcall_blacklist=` **changes behavior** (skips a
suspect initcall) — that is intervention, not measurement, and confounds the
stop-vs-truncation question; an earlier/larger ramoops console region requires
`vendor_boot`/DTBO changes, forbidden by the issue; a staged marker printk
series is a vendor-source patch stack (AGENTS.md keeps kernel patches out of
this repository) and changes many files instead of one token.

Size accounting against the signed-tail bound: the `.config` delta is exactly
one symbol (`CONFIG_CMDLINE`, +15 bytes; the verifier asserts every other config
line byte-identical to #59). The rebuilt `Image-diagnostic-initcall-debug` is
34,986,496 bytes (same as #59); the gzip payload is **13,806,507 bytes vs the
13,967,360-byte bound — 160,853 bytes under** (+53 gzip bytes vs #59's
13,806,454). Estimated (not measured) runtime console volume: 997 initcalls × 2 lines of
roughly 90-110 bytes ≈ 180-220 KB, about 10% of the 2 MiB console zone, so even
a full boot should retain the decisive tail; ring overwrite would only discard
the oldest lines.
`vendor_boot`, `vbmeta`, `dtbo` and the stock signed tail are untouched: the
boot image differs from stock `boot_a` only in the v4 `kernel_size` field
(13,949,926 → 13,806,507), the payload at offset 4096 and the zero padding up
to 13,955,072; the AVB0 record, vbmeta block and AVBf footer are byte-identical.

The ancillary init_boot identity change is **strictly required by the no-reflash
rule**: run 25 measured `cafcabb6…`, so the #59 `init_boot-kernel-banner.img`
cannot be flashed again, and any rebuild of identical content would produce the
identical measured SHA. The chosen change is the smallest possible
identity-only edit: the existing #59 banner log line's literal
`kernel banner: ` becomes `kernel banner #63: ` — one string, no added or
removed line, no behavior change. The frozen #53 init, 127-module order,
peripheral write, UDC wait, 150 s timer, `bin/restart2`, NCM+ECM functions,
key-only sshd, gzip source cpio and the stock signed tail from offset 2,121,728
are unchanged. The single **diagnostic** variable of the experiment remains
`initcall_debug`; the init_boot rename is bookkeeping, not a second variable.

### 4. Artifacts, verification and the next measurement

Artifacts stay under `$WORK/out` and are not committed:

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `Image-diagnostic-initcall-debug` | 34,986,496 | `3c704a53e0b20ae16cc30be9665a2ea29a6947d92333c614c25d943391e60b5a` |
| `Image-diagnostic-initcall-debug.gz` | 13,806,507 | `13acc6b52eaaaf5bf95d17597949ec2c807cb83196e552d626737eb50ef220a8` |
| `.config-diagnostic-initcall-debug` | 225,444 | `1059295eb189fffac74d29dc4028245a30f977289d1a3f7922290e2957b27516` |
| `boot-diagnostic-initcall-debug.img` | 100,663,296 | `86402ac671b6bbc1f2e7c42b2e163c4804abe6349c577d319d182009b5046c65` |
| `init_boot-initcall-debug.img` | 8,388,608 | `be946562cfaa83efd1e573a019e1f88541f9618b0a3d675ba534677e2adb9403` |

All five SHAs are new and never measured. `scripts/verify-diagnostic-initcall-debug.py`
fails closed: it pins the #59 config reference (`c6d8a4e8…`), requires the
config to differ from #59 by exactly the one `CONFIG_CMDLINE` line (rejects a
missing, doubled or `initcall_blacklist`-extended token and any second delta),
asserts `initcall_debug` inside the embedded IKCONFIG and the Image string,
re-derives the exact stock signed-tail layout, runs the `verify-volcano-usb.py`
closure, and rejects 37 prior SHAs including run-25's `0ca048d5`, `cafcabb6`,
`7be448b9` and `d259b744` (a gap in the #59 verifier line, now closed). Its
self-test mutates header/payload/padding/AVB0/vbmeta/AVBf bytes, flips
`F2FS_FS` and `PANIC_TIMEOUT`, and proves every required prior SHA is rejected.
`scripts/verify-init-boot-initcall-debug.py` keeps every #59 kernel-banner
assertion and adds: the banner differs from #59 by exactly the `#63` literal,
the restored #59 text rebuilds the measured `cafcabb6` image and is rejected by
the SHA guard, and all 40 prior SHAs are rejected. `scripts/verify-bootimg.sh`
was extended to unpack both new images, run `verify-volcano-usb.py board` with
the new config against the new kernel's IKCONFIG and the LZ4-decoded new
ramdisk, run both new verifiers with self-tests, and record both images in the
artifact SHA-256 table. Full aggregate run: pass (three
`Volcano DTB: ... 22 resolved suppliers; built-in closure OK` lines, all
negative fixtures, 166 output lines containing `OK`). Two consecutive init_boot builds are
byte-identical. `bash -n`, `shellcheck`, `python3 -m py_compile` and
`git diff --check` are clean.

Command sequence (one build at a time, host only):

```sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-initcall-debug.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-initcall-debug.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

Expected contrasting outcomes for the physical coordinator (flash `boot_a` =
`86402ac6…` and `init_boot_a` = `be946562…`; `vendor_boot`, `dtbo`, `vbmeta`
and slot B untouched; both SHAs never measured):

- **Tail ends on an unpaired `calling  <fn> @ 1` with no `initcall <fn>
  returned` line.** H1 confirmed and the hanging initcall is named exactly; the
  next step is that driver, not USB or init.
- **Tail ends on `calling  init_u32 @ 1` only.** Hang inside `init_u32` after
  its printks (`kvmalloc_array`/`register_tcf_proto_ops`), narrowing to
  entry 787 itself.
- **Paired `calling`/`returned` lines continue through entry 915
  `finalize_pkvm` and `Run /init as init process` appears.** The early-stop
  hypothesis is falsified for the initcall phase; the boundary moves to
  kernel_init/initramfs, and the #53 init chain (150 s timer, sshd) applies —
  SSH at 172.16.42.2 becomes the observable.
- **Paired lines advance well past the run-25 stop but the excerpt ends mid-ring
  with the head overwritten.** Capture-late behavior is established (a variant
  of H2 at a much later time), and the stop-vs-truncation question is answered
  by comparing the last paired entry against the fastboot-return time.
- **No `calling` lines appear anywhere despite the `initcall_debug` token being
  visible in the `Kernel command line:` line.** The token is not taking effect
  on this kernel/ABL path; the next variable must then be the ramoops console
  region, which needs a `vendor_boot`/DTBO change and a new issue.

This does not unblock #12 and leaves the encrypted-userdata release gate
separate.

## Diagnostic own kernel with EXT4_FS off fits the signed tail (#59, host-only, 2026-10-24)

**Host success: the own 6.1.78 kernel with `CONFIG_KALLSYMS_ALL=n` and
`CONFIG_EXT4_FS=n` gzips to 13,806,454 bytes, 160,906 bytes under the
13,967,360-byte signed-tail bound. The boot image and the init_boot image were
assembled and verified host-only; no device operation was performed.** No adb,
fastboot, USB, flash or userdata operation. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. Every previously
measured SHA stays unreused; all new SHAs below are first measurements.

The named fragment `configs/asteroids-diagnostic-ext4-off.fragment` contains
exactly `CONFIG_EXT4_FS=n`, merged last on top of the delivered #60 baseline
(stock `config.gz` SHA-256
`90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`, the
43-symbol debug-off fragment, the Gunyah and ksyms link fragments, the USB,
pstore and marker fragments, and the #60 `KALLSYMS_ALL`/`NLS` fragment). The
resulting `.config` differs from #60's `.config` (SHA-256
`05c70f1a766c7f2d265dc538363445ae581d158a1e60d93313e0c35a0aa2dfd0`) in exactly
six symbols, `EXT4_FS` and the five symbols selected solely by it:
`EXT4_USE_FOR_EXT2`, `EXT4_FS_POSIX_ACL`, `EXT4_FS_SECURITY` (its sub-options),
`JBD2` and `FS_MBCACHE` (the vendor tree names the meta block cache
`FS_MBCACHE`, not `MBACHE`); all six go `y -> not set`. `CONFIG_KALLSYMS`,
`F2FS_FS`, `ANDROID_BINDER_IPC`, `NLS` and the
`verify-volcano-usb.py config` USB closure are byte-unchanged. The build used
the pinned vendor commit `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, Ubuntu
clang 17.0.6 with `ARCH=arm64 LLVM=-17 LLVM_IAS=1`, and the #55 stock gzip
framing (zlib level 9, header `1f 8b 08 00 00 00 00 00 02 03`).

| quantity | bytes |
| --- | ---: |
| #55 `Image-stock-config` | 37,198,336 |
| #60 `Image-diagnostic-kallsyms-nls` | 36,018,688 |
| #59 `Image-diagnostic-ext4` | 34,986,496 |
| #55 gzip payload | 14,782,792 |
| #60 gzip payload | 14,236,242 |
| #59 gzip payload | 13,806,454 |
| signed-tail bound | 13,967,360 |
| under bound | 160,906 |

Per-symbol measured deltas: `KALLSYMS_ALL=n` measured -546,550 gzip bytes (#60);
`EXT4_FS=n` (with `EXT4_USE_FOR_EXT2`, `EXT4_FS_POSIX_ACL`, `EXT4_FS_SECURITY`,
`JBD2`, `FS_MBCACHE`) measured -429,788 gzip bytes this issue (14,236,242 ->
13,806,454; #57 zero-mask estimate 329,690, so the estimate was 99,098 bytes
conservative). The #57 estimate excluded second-order kallsyms/BTF shrink,
which the measured rebuild includes. `F2FS_FS` (estimate 275,810) was not
needed and stays on.

`scripts/build-diagnostic-signed-tail-payload.py` assembles the boot image in
the measured stock signed-tail layout: a copy of stock `boot_a` (SHA-256
`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`) in which
only the v4 header `kernel_size` field changes (13,949,926 -> 13,806,454), the
gzip payload plus its header replaces the stock kernel payload at offset 4096,
the padding window [13,810,550, 13,955,072) is filled with 144,522 zero bytes,
and every byte from the stock separate 16 KiB `AVB0` record at 13,955,072
through the embedded 2,496-byte signed `AVB0` vbmeta block at 13,971,456 and
the terminal 64-byte `AVBf` footer is byte-identical to stock; 100,663,296-byte
image.

`scripts/verify-diagnostic-signed-tail.py` fails closed: it pins the #60
`.config` reference, re-derives the exact six-symbol config delta, runs the
`verify-volcano-usb.py` config closure, re-decompresses and re-compresses the
payload (stock framing, deterministic level 9), matches the embedded
`IKCONFIG_ST..IKCONFIG_ED` blob against the built config, requires the image to
equal `assemble(stock, payload)` (header field, payload, padding, unchanged
stock tail), and rejects the candidate and payload SHA against every previously
measured SHA (all of `9f89fe8d`, `995aaca3`, `88c93077`, `8f8b7331`,
`55fa78ca`, `5a513998`, `dc990b95`, `13a48ff9`, `37535dd1`, `bde3a3b3`,
`6078269d`, stock `197aff11` and the older line). Its self-test mutates a
header byte, a payload byte, a padding byte, the `AVB0` record, the vbmeta
block and the `AVBf` footer (each rejected), flips `F2FS_FS` off in the config
(rejected) and proves every required prior SHA is rejected.

Artifacts stay under `$WORK/out` and are not committed:

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `Image-diagnostic-ext4` | 34,986,496 | `7be448b91b618cbe1dbda9659dfeeb2d554f702091c39453bfa44497c280377e` |
| `Image-diagnostic-ext4.gz` | 13,806,454 | `d259b744465eb48b2c42ddcedcf89f6d2608638c6b04f3c2c534fa27b66d7738` |
| `.config-diagnostic-ext4` | 225,429 | `c6d8a4e86301d314adc8724b7b3d985d81b9cff2074e0e917ed976a46df3ebd9` |
| `boot-diagnostic-ext4.img` | 100,663,296 | `0ca048d554857b469aadf6a55e6fd70cc1cb51cd72eff8f6f98e451bb595f72b` |
| `init_boot-kernel-banner.img` | 8,388,608 | `cafcabb67a1d79f7877b59a1daff25d92fd8fc6ecb5d5128f44ab8cc17af541c` |

`scripts/build-init-boot-kernel-banner.sh` rebuilds the init_boot image from
the #53 static-address line: the frozen #53 init (`initramfs/init`, SHA-256
`ab2377a6ea4f852e03a24056e4087977f6d9d4c8019868c55e4d552e7b97d05b`, unchanged
in the repository) plus exactly one added diagnostic log line after
`log 'starting'`:
`log "kernel banner: $(uname -r 2>&1) $(/bin/busybox cat /proc/version 2>&1)"`,
so pstore can prove which kernel ran. The 127-module order and list (SHA-256
`4f0e151d…`), single peripheral write, 40x0.25 s UDC wait, 150 s `/run/keep`
timer, `bin/restart2` helper, NCM+ECM functions, key-only sshd, gzip cpio
source and the stock signed tail from offset 2,121,728 are unchanged. The
ramdisk is one Android LZ4 legacy HC-12 block (1,931,151 bytes) of the 3,489,792
-byte debug cpio (zero `.ko`). Two consecutive builds are byte-identical.
`scripts/verify-init-boot-kernel-banner.py` requires the embedded init to be
exactly frozen-#53-plus-that-one-line (a stripped init must pass the full #53
checker and equal the frozen bytes), proves the reproducible builder output,
and rejects every prior SHA; its self-test rejects a removed (which rebuilds
the measured #53 image `995aaca3` and is caught by the SHA guard), duplicated,
moved or reworded banner, a second diagnostic line, a changed module order, a
second role write, a changed gadget function, a removed address log, a timer
change, a planted `.ko`, and envelope, header, block, gap and tail corruptions.

`scripts/verify-bootimg.sh` now also unpacks both new images and runs
`verify-volcano-usb.py board` with the diagnostic config against the new
kernel's embedded IKCONFIG (the LZ4 ramdisk is decoded and gzip-wrapped for the
zero-`.ko` check against the stock board DTB), runs both new fail-closed
verifiers with self-tests, and records both images in the artifact SHA-256
table. Full aggregate run: pass (both `Volcano DTB: ... 22 resolved suppliers;
built-in closure OK` lines, all negative fixtures).

Command sequence (one build at a time, host only):

```sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-kallsyms-nls.sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-ext4.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-kernel-banner.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

The device experiment in the issue (flash `boot_a` with the new own-kernel
image plus the marker init_boot, distinct SHA set) belongs to the physical
coordinator under `full_autonomy_device_iteration`, not to this host-only
delivery. This does not unblock #12 and leaves the encrypted-userdata release
gate separate.

## Diagnostic own kernel with KALLSYMS_ALL off, NLS not removable (#60, host-only, 2026-10-23)

**Host failure: the rebuilt own 6.1.78 kernel gzips to 14,236,242 bytes, 268,882
bytes over the 13,967,360-byte signed-tail bound. No boot image and no init_boot
image were assembled and no image SHA is recorded.** No device, adb, fastboot,
USB, flash or userdata operation was performed. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. Every previously
measured SHA stays unreused.

The named fragment `configs/asteroids-diagnostic-kallsyms-nls-off.fragment`
contains exactly `CONFIG_KALLSYMS_ALL=n` and `CONFIG_NLS=n`, merged last on top
of the #55 baseline (stock `config.gz` SHA-256
`90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`, the 43-symbol
debug-off fragment, the Gunyah and ksyms link fragments, the USB, pstore and
marker fragments). `make olddefconfig` turns `CONFIG_NLS` back to `y`, because
other symbols that must stay on select it: `USB_GADGET=y` (the unchanged USB
closure), `F2FS_FS=y` (kept on by the issue) and `SCSI_UFSHCD=y`. Making NLS
disappear would require turning off one of those, which the issue forbids. The
resulting `.config` differs from the #55 `.config` in exactly one symbol,
`CONFIG_KALLSYMS_ALL` (`y` to not set); `CONFIG_KALLSYMS`, `EXT4_FS`, `F2FS_FS`,
`ANDROID_BINDER_IPC` and the USB closure (`verify-volcano-usb.py config`) are
unchanged. The build used the pinned vendor commit
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7`, Ubuntu clang 17.0.6 with
`ARCH=arm64 LLVM=-17 LLVM_IAS=1`, and the #55 gzip framing (zlib level 9,
header `1f 8b 08 00 00 00 00 00 02 03`).

| quantity | bytes |
| --- | ---: |
| #55 `Image-stock-config` | 37,198,336 |
| #60 `Image-diagnostic-kallsyms-nls` | 36,018,688 |
| #55 gzip payload | 14,782,792 |
| #60 gzip payload | 14,236,242 |
| signed-tail bound | 13,967,360 |
| over bound | 268,882 |

Per-symbol measured and estimated deltas against the 268,882-byte shortfall:

| symbol | state | gzip bytes | basis |
| --- | --- | ---: | --- |
| `KALLSYMS_ALL=n` | applied | -546,550 | measured rebuild (#57 estimate 546,197, +353) |
| `NLS=n` | not buildable | (-268,815) | zero-mask recompression of `fs/nls/` on the new Image, 669,180 raw bytes (#57 estimate 275,810) |
| of which CJK codepages 932/936/949/950 | not applied | (-248,629) | zero-mask estimate, 444,940 raw bytes |
| of which `nls_base.o` | not applied | (-1,102) | zero-mask estimate, 7,048 raw bytes |

The figures in parentheses are recompression estimates on the exact new map
bytes, not a build. They exclude second-order kallsyms and BTF shrink. Even if
`NLS` were removable, the estimate leaves the payload 67 bytes over the bound
(268,882 - 268,815). The 49 `NLS_CODEPAGE_*`, `NLS_ISO8859_*`, `NLS_MAC_*` and
`NLS_KOI8_*` charset symbols are separate options; this issue changes only the
two named symbols, so they were not touched. The issue's recorded contingency,
dropping `EXT4_FS` (#57 estimate 329,690 bytes), is not part of this delivery.

Artifacts stay under `$WORK/out` and are not committed:
`Image-diagnostic-kallsyms-nls` SHA-256
`724d8a6b3eac37046941458b83059d00a48ed37fc0f70a9f6a3224c38e86af6a`,
`Image-diagnostic-kallsyms-nls.gz` SHA-256
`37535dd13312e2d2078c344cbf11db32260f0d35c4d3e0b2bf95a214b27b9bb8`,
`.config-diagnostic-kallsyms-nls` SHA-256
`05c70f1a766c7f2d265dc538363445ae581d158a1e60d93313e0c35a0aa2dfd0`. A relink of
the same inputs differs from the built Image in 19 bytes, all inside the
`.notes` build-id.

Command sequence (one build at a time, host only):

```sh
WORK="$HOME/sm7635-build" JOBS=8 scripts/build-diagnostic-kallsyms-nls.sh
WORK="$HOME/sm7635-build" scripts/report-diagnostic-shortfall.sh
```

`build-diagnostic-kallsyms-nls.sh` fails closed at the bound check, removes any
`boot-diagnostic-kallsyms-nls.img` and writes no boot image, so the
step 3 and step 4 images (stock-prefix signed-tail boot image, and the #53
init_boot with one added `uname -r` line) were not produced. The script also
fails closed if `CONFIG_KALLSYMS_ALL` stays on, if `KALLSYMS`, `EXT4_FS`,
`F2FS_FS`, `ANDROID_BINDER_IPC`, `USB_GADGET` or `SCSI_UFSHCD` is off, or if the
USB closure check fails. `report-diagnostic-shortfall.sh` relinks the build into
scratch outside the repository and the build tree and prints the table above.

Contrasting outcomes defined by the issue: **fit** (not reached) would have
required packaging only the payload and gzip header into the stock `boot_a`
prefix with the stock AVB0, vbmeta and AVBf tail unchanged; **shortfall** (this
result) stops with the numbers above. The phone experiment in the issue is not
available because no new image set exists. This does not unblock #12 and leaves
the encrypted-userdata release gate separate.

## Attribution of the 815,432-byte gzip excess (#57, host-only, 2026-10-23)

**Host analysis only. The not-required set can reach the excess; this does not
change the shipped configuration or build an image.** No device, adb, fastboot,
USB, flash or userdata operation was performed. Stock `boot_a`, `init_boot_a`,
`vendor_boot_a`, `dtbo`, `vbmeta` and slot B are unchanged. No SHA is recorded
and every previously measured SHA stays unreused.

`scripts/analyze-gzip-excess.sh` reads the existing #55 build
(`Image-stock-config` 37,198,336 bytes, `Image-stock-config.gz` 14,782,792
bytes, signed-tail bound 13,967,360 bytes) and reproduces the payload
bit-exactly with zlib level 9 and the fixed stock framing. It relinks the same
inputs into scratch, outside the repository and the build tree. The replay
differs in 20 bytes, all inside the `.notes` build-id. A linker map covers
37,034,789 of the 37,198,336 loaded bytes; the remaining 163,547 bytes are
alignment and linker-script gaps. Decoding the deflate stream attributes
14,713,067 payload bytes to image bytes; 69,707 bytes are deflate block-header
overhead and are not attributed to a group.

The largest in-stream groups are `.BTF` (5,777,934 raw, 1,849,539 gzip),
kallsyms (2,374,536 raw, 1,173,632 in-stream), `.eh_frame` (3,058,212 raw,
731,335 gzip), then `drivers/usb` (527,505), merged strings, `arch/arm64`,
`net/ipv4`, `net/core`, ext4, f2fs and NLS. The script writes the full
per-section, per-directory and per-object tables, plus a classification of
every directory, into its scratch directory. They are generated from the build
tree and are not committed.

The classification uses the USB built-in closure, the symbols evidenced by
`initramfs/init`, the undefined symbols of the 127 stock vendor modules the
measured init loads, and whether an object is referenced from outside its own
group. A directory is required when it contains an object gated by a closure
symbol or one that exports a symbol imported by those modules; that marks the
directory as not wholly removable, not every byte inside it as needed. On that
basis `drivers/usb`, `arch/arm64`, `net/ipv4`, `net/core`, `drivers/hid`,
`drivers/base`, `kernel/sched`, `kernel/trace` and `drivers/clk` are required.
Generated tables are unknown because only part of them is attributable.
`ARM_SCMI_PROTOCOL` is the one candidate that is required outright: the 127
modules import four symbols defined only there. `DEBUG_INFO_BTF` and
`UNWIND_TABLES` stay unknown: all 127 modules carry both `.BTF` and
`.eh_frame`, and the effect of dropping the matching vmlinux data was not
measured. `MEDIA_SUPPORT`, `NLS` and `ZSTD_COMPRESS` stay selected by other
stock options, and DRM, sound, KVM, netfilter, traffic control, IPv6 and BPF
are referenced from objects outside their own directories, so none of those is
counted as removable.

The not-required set is `KALLSYMS_ALL`, `EXT4_FS`, `F2FS_FS` and
`ANDROID_BINDER_IPC`. `KALLSYMS_ALL` is not the whole kallsyms table:
regenerating the #55 symbol list without `--all-symbols` keeps the text
symbols and removes 1,189,640 of 2,374,536 `.rodata` bytes, estimated at
546,197 gzip bytes. The other three are zero-masked recompressions of the
exact map bytes: ext4 with its jbd2 and mbcache dependency at 329,690, f2fs at
275,810 and binder at 57,422. Disabling all four together turns off no closure
symbol. Their individual estimates sum to 1,209,119 bytes and the joint
estimate is 1,210,916 bytes, which is 395,484 bytes above the 815,432-byte
excess. These are recompression estimates, not a rebuilt kernel: they do not
include the second-order kallsyms, BTF and relocation changes a real rebuild
would make. "Not required" means not required by the USB/SSH closure and the
measured own-init only. Any later userdata mount (f2fs, ext4) or Android
userspace (binder) would need these symbols; that use is outside this
measurement and untouched here. Choosing whether to drop any of them is a
separate decision for the owner or coordinator.

## Own 6.1.78 kernel from the stock configuration, signed-tail bound (#55, host-only, 2026-10-23)

**Host failure — the stock-configuration own kernel still misses the
signed-tail bound. No image was packaged and no SHA is recorded as a control.**
No device, adb, fastboot, USB, flash or userdata operation was performed. Stock
`boot_a`, `init_boot_a`, `vendor_boot_a`, `dtbo`, `vbmeta` and slot B are
unchanged. Every previously measured SHA stays unreused.

The discriminating question was whether the own 6.1.78 source, built from the
captured stock configuration plus only the USB and recovery options already
required by the measured init, produces a gzip payload that fits before the
signed tail. It does not.

`scripts/build-stock-config-baseline.sh` starts from the read-only device
`config.gz` (SHA-256
`90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`), disables
only the debug options enabled in the current own build but absent from that
stock configuration (`configs/asteroids-stock-config-debug-off.fragment`, 43
symbols), keeps the USB closure (`asteroids-volcano-usb-builtin.fragment`),
pstore, panic and `sm7635-boot-marker` fragments, and adds two Kconfig gate
symbols (`asteroids-stock-config-gunyah-closure.fragment`:
`CONFIG_GUNYAH_DRIVERS=y`, `CONFIG_QCOM_MEM_BUF_GH=y`). They are not new
drivers: the existing USB fragment's verified built-in closure already lists
`GH_RM_DRV`, `GH_MSGQ`, `GH_DBL` and `QCOM_MEM_BUF_MSGQ`, which stay unset on
the stock base unless these two gates are on (`scripts/verify-volcano-usb.py`
rejected the merge without them). No compressor change or payload trimming was
used. Two further link-only deviations are listed below. The build ran the
pinned vendor commit `d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7` with
`ARCH=arm64 LLVM=-17 LLVM_IAS=1`, Ubuntu clang 17.0.6, and compressed `Image`
with the same fixed gzip framing as the stock payload (`zlib` level 9, header
`1f 8b 08 00 00 00 00 00 02 03`, OS byte 3, `XFL` byte 2).

| quantity | bytes |
| --- | ---: |
| decompressed `Image-stock-config` | 37,198,336 |
| gzip payload `Image-stock-config.gz` | 14,782,792 |
| signed-tail bound | 13,967,360 |
| over bound | 815,432 |

The build failed closed at the bound check and wrote no
`boot-signed-tail.img`. Because the payload exceeds the bound, the issue's
host-success branch (a deterministic image, its fail-closed image verifier, and
a SHA recorded as a host-only control) is not reached, so no such image,
verifier wiring or SHA is delivered. The stock configuration is closer to stock
than the current own configuration yet still yields a payload ~815 KB too large
for the signed-tail layout.

Two unavoidable non-debug deviations from the raw stock configuration were
required only so the tree links, and neither changes the conclusion:

- `CONFIG_TRIM_UNUSED_KSYMS` is set in the stock capture with
  `CONFIG_UNUSED_KSYMS_WHITELIST="abi_symbollist.raw"`, but that ABI whitelist is
  generated by the Android Bazel build and is absent from the pinned GPL tree.
  Keeping it makes `gen_autoksyms.sh` fail with `whitelist file not found`.
  `configs/asteroids-stock-config-ksyms.fragment` turns it off. Trimming can
  only remove exported-symbol tables: `__ksymtab`, `__ksymtab_gpl`, `__kcrctab`,
  `__kcrctab_gpl` and `__ksymtab_strings` total 613,483 raw bytes in this
  `vmlinux`. Removing all of them would save at most 613,483 gzip bytes, below
  the 815,432-byte gap, so restoring trimming cannot make the payload fit. This
  is an upper bound from section sizes, not a build of the trimmed kernel.
- The vendor `qcom_common.h` emits a non-`static` stub
  `qcom_sysmon_get_reason` when `CONFIG_QCOM_SYSMON=n`, producing a duplicate
  symbol once `QCOM_RPROC_COMMON=y` (from the USB supplier closure) links it into
  two built-in objects. The current own build avoids this only by setting
  `QCOM_SYSMON=m`. The build script applies one source fixup making that stub
  `static inline`, matching every sibling stub, so the stock-faithful
  `QCOM_SYSMON=n` links. This is a link-only correction, not a size change.

Contrasting outcomes defined by the issue:

- **Host failure (this result):** the stock-configuration own kernel still
  exceeds the signed-tail bound. Stop and report; do not choose a smaller
  payload opportunistically. Done here.
- **Host success:** would have required a payload ≤ 13,967,360 bytes packaged
  into a copy of verified stock `boot_a` with only `kernel_size` changed and a
  byte-identical signed tail. Not reached.

The remaining question, per the issue, is payload content, not another layout
variant or an opportunistic shrink. This does not unblock #12 and leaves the
encrypted-userdata release gate separate.

## Static USB address logging on the enumerated gadget (#53, host-only, 2026-10-23)

**Host-only artifact, not a boot, USB or SSH result.** No device, adb, fastboot,
USB, flash or userdata operation was performed. The one new image is
`$WORK/out/init_boot-static-address.img` (8,388,608 bytes, SHA-256
`995aaca380225be1b865493230164ecc49c5c958b50560d3851010bf3294e5f9`).
Two consecutive builds produced byte-identical files. The hash differs from
measured #51 `9f89fe8d…`, #49 `88c93077…`, #47 `8f8b7331…`, #44 `cdb9458f…`,
#42 `3932504a…`, #40 `f4a00ce3…`, stock `baa33fd4…`, vendor_boot `bde3a3b3…`
and `6078269d…`, and every earlier measured image SHA in the verifier's prior
set. No prior image is reused.

The measured #51 attempt (23) ran its own `/init`, accepted one `peripheral`
write, created `a600000.dwc3`, bound the NCM+ECM gadget and enumerated on the
host as `18d1:4ee2` for about 148 seconds. The host saw link carrier on both
interfaces, but its DHCP failed and no route to `172.16.42.2` existed; SSH
timed out. The #51 init ran `ip link set` and `ip addr add` for `usb0` and
`usb1` and discarded every result, so the pstore could not show whether the
device configured `172.16.42.2/24` and `172.16.43.2/24`. That is the only
question this image adds logging for. It does not assign any host address.

The #51 `/init` is frozen byte-for-byte as
`initramfs/init-51-peripheral-mode` (SHA-256
`995d9c84289502f77b8fb893e748524bcef84db07d1f2dd74cb403a017601263`).
The #51 builder and verifier now read that copy; a separate rebuild produced
`9f89fe8d614e213de1d197b78b2faf7f88ba190ba66cc41d5e3cd6c144d64af3`,
byte-identical to the retained #51 artifact. The new `/init` changes only the
gadget branch after `gadget bound`: the two `ip link set up` and two
`ip addr add` commands no longer discard their output and each result is
logged, then read-only `ip addr show dev usb0`, `ip addr show dev usb1` and
`ip route` are logged at most 32 lines. After the unchanged key-only sshd it
adds one read-only listener check for `172.16.42.2:22`, at most 64 lines, from
`ss -ltn` or `netstat -ltn` when present and otherwise from the dropbear
process list plus the `172.16.42.2:22` line of `/proc/net/tcp`. The 127-module
order (list SHA-256
`4f0e151da8a68339d34d7596d73e77f95415faa79b741aaa425572c1fa7caf69`), the single
`peripheral` write, the 40 × 0.25 s UDC wait, the 150 s `/run/keep` timer
(still started before the module phase, budget unchanged), `bin/restart2`, the
NCM+ECM functions and the key-only sshd command are unchanged. No extra `.ko`,
kernel, DT or gadget function was added.

`build-init-boot-static-address.sh` rebuilt twice sequentially and its
fail-closed verifier, including negative fixtures, passed on each build. The
3,489,280-byte newc (SHA-256
`767316300effaff75c8b8af331325b3f203bc0894c7a8547d0dc2f3def609d22`)
contains zero `.ko`. One Android LZ4 legacy HC-12 block of 1,931,104 bytes
(1,931,112-byte frame) starts at offset 4,096; the remaining 186,520-byte gap
to offset 2,121,728 is zero. Only the stock init_boot ramdisk-size header
field changes, to 1,931,112; the empty kernel, 8,388,608-byte size and
6,266,880-byte signed stock tail through the `AVBf` footer are preserved.
This does not establish stock AVB acceptance. Negative fixtures reject a
missing or duplicated address log, an address or link command that still
discards its result, missing or lengthened network or listener diagnostics,
a removed, moved or lengthened timer, a changed module order, a second role
write, a changed gadget function, a planted `.ko`, a bad header/frame/gap/tail
and every reused measured SHA including `9f89fe8d…`. `scripts/verify-bootimg.sh`
(157 `OK` checks), `bash -n`, `shellcheck` and `git diff --check` all passed.
Artifacts and test logs remain outside Git.

Contrasting outcomes to distinguish in any separately coordinated physical
measurement, none of which is claimed by this host proof:

- **Both addresses are logged and sshd listens on `172.16.42.2:22`.** The host
  can then assign `172.16.42.1/24` to the NCM interface and attempt the
  existing key. Create `/run/keep` only after login. This image assigns no
  host address.
- **An address command fails, or sshd is not listening on that address.**
  Record the exact error and stop. The next question is that failure, not
  another role or module change.
- **Addresses and the listener are present but SSH still times out.** That
  separates the device configuration from the host path. Stop this branch.
- **No usable USB.** Observe at least 180 seconds. Fastboot at about 150 to
  180 seconds with a captured pstore means the timer still returns the device;
  a userspace timer does not cover a kernel hang. No return, no log, or a
  reboot into itself is a separate result. Never repeat this SHA after a
  negative test.

#12 and the encrypted-userdata release gate remain untouched.

## One peripheral role event after EUD binds (#51, host-only, 2026-10-23)

**Host-only artifact, not a boot or USB result.** No device, adb, fastboot, USB,
flash or userdata operation was performed. The one new image is
`$WORK/out/init_boot-peripheral-mode.img` (8,388,608 bytes, SHA-256
`9f89fe8d614e213de1d197b78b2faf7f88ba190ba66cc41d5e3cd6c144d64af3`).
Two consecutive builds produced byte-identical files. The hash differs from
measured #49 `88c93077…`, #47 `8f8b7331…`, #44 `cdb9458f…`, #42 `3932504a…`,
#40 `f4a00ce3…`, stock `baa33fd4…`, vendor_boot `bde3a3b3…` and
`6078269d…`, and every earlier measured image SHA in the verifier's prior
set. No prior image is reused.

The measured #49 attempt (22) ran its own `/init`, loaded all 127 stock vendor
modules with `eud.ko` immediately before `dwc3-msm.ko`, and by ~11 s reported
EUD and `a600000.ssusb` bound without a UDC or a USB deferred probe. Its
in-image 150 s timer returned the device to fastboot at ~169 s with
`self-recovery -> bootloader` captured in pstore. On stock Android,
`a600000.dwc3` appears around 6.7 s after userspace and Type-C activity,
not when `a600000.ssusb` first binds. The vendor role-switch path needs a
later role event before it creates the DWC3 child; this is a hypothesis about
the minimal own-init, not a measured outcome of the new image.

The #49 `/init` is frozen byte-for-byte as
`initramfs/init-49-eud-softdep` (SHA-256 `8fa9b571b7e957cd64a68ebc5075fa198d8f3c53f5fef9ea065e312310d9bb7b`).
The #49 builder now reads that copy; a separate rebuild produced
`88c93077d5079d4dc81ce723299faab756bf5b52a5af8ebe99c84f68ea9ae0aa`,
byte-identical to the retained #49 artifact. In the new `/init`, after the
module phase and before the unchanged bounded 40 × 0.25 s UDC wait, one
step finds `a600000.ssusb` in `/sys/bus/platform/devices/*` and checks that
it is bound to `msm-dwc3`. If `mode` exists, it logs the current value,
writes exactly `peripheral` once through the discovered path, logs success
or the error text, and logs readback; if missing it logs that and does not
fall back. After the wait it logs UDC names, EUD/glue bind, whether
`a600000.dwc3` exists under glue and is bound, at most 64 `a600000.*`
`devices_deferred` entries, and at most 64 matching `msm-dwc3`/`dwc3`/
`phy`/`repeater` dmesg lines after the module-end marker. These diagnostics
are read-only. A successful attribute write alone is not a child, UDC,
gadget bind, enumeration or SSH success. The 127-module order (list SHA-256
`4f0e151da8a68339d34d7596d73e77f95415faa79b741aaa425572c1fa7caf69`),
150 s `/run/keep` timer, `bin/restart2`, key-only sshd and NCM/ECM path
are unchanged. No extra `.ko`, kernel, DT or gadget function was added.

`build-init-boot-peripheral-mode.sh` rebuilt twice sequentially and its
fail-closed verifier, including negative fixtures, passed on each build.
The 3,487,744-byte newc (SHA-256
`d499d3549cd232fc2b99f0b48be9a3248d354dc0f2b181fe780466409e4c6e53`)
contains zero `.ko`. One Android LZ4 legacy HC-12 block of 1,930,509
bytes (1,930,517-byte frame) starts at offset 4,096; the remaining
187,115-byte gap to offset 2,121,728 is zero. Only the stock init_boot
ramdisk-size header field changes, to 1,930,517; the empty kernel,
8,388,608-byte size and 6,266,880-byte signed stock tail through the
`AVBf` footer are preserved. This does not establish stock AVB acceptance.
Negative fixtures reject a missing or duplicated write, a write before
module completion or EUD/DWC3 loading, the wrong value, a hardcoded SoC
path, a removed or moved timer, a changed module order, a planted `.ko`,
a bad header/frame/gap/tail, a shortened UDC wait or reused measured SHA.
`scripts/verify-bootimg.sh` (155 `OK` checks), `bash -n`, `shellcheck`
and `git diff --check` all passed. Artifacts and test logs remain outside Git.

Contrasting outcomes to distinguish in any separately coordinated physical
measurement: a write error or named PHY/repeater/clock/regulator error would
identify a supplier blocker; an accepted write with a child but no UDC (or
gadget bind failure) would be a different blocker; an accepted write, child,
UDC and bound gadget still requires independent host enumeration and key-only
SSH evidence. If USB/SSH is absent, the 150 s userspace recovery is not a
kernel-hang guarantee; return to fastboot with pstore, a reboot loop and no
return/no log are separate results. **None of these is claimed by host proof.**
#12 and the encrypted-userdata release gate remain untouched.

## EUD softdep in the self-recovering debug init (#49, host-only, 2026-10-23)

**Host-only image, not a boot result.** No device, flash, USB or userdata
operation was performed. The stock 6.1.84 kernel and `boot_a`, `vendor_boot_a`,
`dtbo`, `vbmeta` and slot B are unchanged. The one new image is
`$WORK/out/init_boot-eud-softdep.img` (8,388,608 bytes, SHA-256
`88c93077d5079d4dc81ce723299faab756bf5b52a5af8ebe99c84f68ea9ae0aa`).
It differs from the measured `8f8b7331…`, `cdb9458f…`, `3932504a…`, `f4a00ce3…`,
stock `baa33fd4…`, both vendor_boot sets (`bde3a3b3…`, `6078269d…`) and every
earlier measured SHA. Never reflash those earlier images.

The attempt-21 pstore of the #47 image was read before this image was built.
It shows own `/init`, all 126 modules loaded before 1 s, `qcom-reboot-reason
bound`, `udc names: none` at about 11 s and `a600000.ssusb` deferred. The host
saw no USB network or SSH, and the device returned to fastboot at about 166 s
without a button press. The late timer marker did not survive pstore, so the
150 s path is consistent with the return but not directly proven.

The stock vendor `modules.softdep` says `softdep dwc3_msm pre: phy-generic
phy-msm-snps-hs phy-msm-ssusb-qmp eud`. The #44 closure calculator silently
skipped a softdep target that was not itself in the closure, which dropped
`eud.ko` even though it is present in the vendor ramdisk and named by
`modules.load.recovery`. Its `modules.dep` prerequisites are all already in the
126-module closure. Two other softdep targets, `qcom_tlmm_vm_irqchip` and
`phy_msm_snps_hs`, have no `.ko` in the vendor ramdisk and no enabled driver in
the stock `config.gz`; the new calculator accepts exactly those two as
unavailable and rejects any other unresolved target. `eud.ko` is checked to be
an aarch64 ELF with no prerequisite outside the old closure.

`initramfs/init` is the #47 init, kept byte-for-byte as
`initramfs/init-47-self-recovering`, plus exactly two additions and nothing
removed. The #47 image builder and verifier read the frozen copy, so the
measured `8f8b7331…` image still rebuilds unchanged. The module list inserts
`eud.ko` immediately before `dwc3-msm.ko` and changes nothing else, so the old
126 modules keep their order and SHA-256
`57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08`; the new
127-line list is SHA-256
`4f0e151da8a68339d34d7596d73e77f95415faa79b741aaa425572c1fa7caf69`.
The single existing `insmod` loop loads it. After the 10 s UDC wait and the
`udc names` line, and before the gadget path, init logs whether
`88e0000.qcom,msm-eud` is bound to the `msm-eud` driver, whether
`a600000.ssusb` is bound to `msm-dwc3`, and every `devices_deferred` line for
`a600000.ssusb` with its supplier reason. The 150 s timer, the `/run/keep`
escape, the `bin/restart2` helper, the key-only sshd and the NCM/ECM path are
unchanged. An `insmod` success is not a bind or a USB success.

The builder reuses the verified debug gzip `caa3eb82…` and changes only
`/init`. The resulting 3,485,696-byte newc carries zero `.ko` and hashes to
`5db0a7d4c4b9ab123c5437c9e5de771d40ce7b95474403c87f93c7f208a37467`.
Stock LZ4 HC level 12 makes one 1,929,933-byte block (1,929,941-byte legacy
frame) at offset 4,096, inside the 2,117,632 bytes before the signed tail. Only
header field `ramdisk_size@12` changes, from 2,113,581 to 1,929,941; the
187,691-byte gap to offset 2,121,728 is zero; all 6,266,880 bytes from the
signed `AVB0` block through the `AVBf` footer are unchanged. The candidate uses
no new kernel, is not signed, and claims no AVB, ABL or device verdict.

`scripts/build-init-boot-eud-softdep.sh` produced two byte-identical candidate
runs and kept one image outside Git. `scripts/verify-bootimg.sh` passed.
`scripts/verify-init-boot-eud-softdep.py` rejects an init with no timer, a timer
inside or after the module loop, a timer that ignores `/run/keep`, a missing or
misplaced loading marker, a removed reboot-reason bind check, a removed EUD
read-only check, a missing `eud.ko`, a duplicated `eud.ko`, `eud.ko` placed
before its prerequisites or after `dwc3-msm.ko`, a changed order of the old 126
modules, a missing, dynamic or altered helper, a planted `.ko`, a modified
header or signed tail, a closure whose softdep names an unresolved target, a
changed `dwc3_msm` softdep edge, an `eud.ko` with a prerequisite outside the
closure, an absent or non-aarch64 `eud.ko`, and every repeated prior SHA,
including `8f8b7331…`, `bde3a3b3…`, `6078269d…`, `cdb9458f…`, `3932504a…`,
`f4a00ce3…` and `baa33fd4…`. `bash -n`, `shellcheck` and `git diff --check`
pass. The only next physical step belongs to the human coordinator under the
standing mission-shift approval; repository work neither performs nor
authorizes a flash. This leaves #12 and the encrypted-userdata release gate
untouched.

A later measurement of this one image, flashed only to `init_boot_a` with stock
`boot_a`, `vendor_boot_a`, `dtbo_a`, `vbmeta_a` and slot B untouched, and
observed for at least 180 s before any button press, distinguishes three
outcomes. None is claimed here.

- **EUD binds, `a600000.ssusb` binds and a UDC exists.** Only then assess the
  gadget bind and key-only SSH. A flash that returns is not boot success.
- **EUD binds but `a600000.ssusb` or the UDC stays absent.** Record the new
  supplier and deferred state and contrast it with the stock sequence. Stop
  this branch; do not add more modules or force a USB role.
- **EUD `insmod` or bind fails.** Record the exact error and stop to investigate
  the provider. Do not infer an AVB rejection.

If no USB or SSH appears, observe at least 180 s without touching the device.
Fastboot at about 150 to 180 s plus a captured pstore supports the bounded
init-level recovery; if the device does not return, do not assume the timer
covers a kernel hang. A reboot into itself is a distinct failure. Never repeat
this SHA after a negative test.

# Temporary boot chain: diagnosis and next attempt

The 2026-10-19 analysis and historical test plan below preceded failed
2026-10-20 and 2026-10-21 full-chain slot-A attempts. Repository work never
performs device operations. The historical procedure below is not authorization
to repeat it.

## Self-recovering, module-attributing debug init (#47, host-only, 2026-10-23)

**Host-only image, not a boot result.** No device, flash, USB or userdata
operation was performed. The stock 6.1.84 kernel and `boot_a`, `vendor_boot_a`,
`dtbo`, `vbmeta` and slot B are unchanged, and the #44 module closure is
unchanged. The one new image is `$WORK/out/init_boot-self-recovering.img`
(8,388,608 bytes, SHA-256
`8f8b733150abc89f5e1769a85bac25583bafd9c8028986c6ae50ba7034c056dd`).
It differs from the measured `cdb9458f…`, `3932504a…`, `f4a00ce3…`, stock
`baa33fd4…` and every earlier measured SHA. Never reflash those earlier images.

The attempt-20 pstore of the #44 image was read before this image was built.
It shows `Run /init as init process`, all 126 `usb-init: module <name> loaded`
lines in the closure order, `usb-init: module load end` at 1.06 s, `udc names:
none`, `no UDC; USB gadget not bound`, exactly 7 deferred-probe entries (the
`a600000.ssusb` entry waits on `88e0000.qcom,msm-eud`) and `console ready`. No
module failed and none hung, so the module list is unchanged from #44 and its
newline-delimited list keeps SHA-256
`57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08`.

 `initramfs/init` is the #44 init, kept byte-for-byte as
 `initramfs/init-44-vendor-modules`, plus exactly three additions and nothing
 removed. The #44 image builder and verifier read the frozen copy, so the
 measured `cdb9458f…` image still rebuilds unchanged.
 Before each `insmod` it logs `usb-init: loading <name>`, so a hang names the
module that did not return. After the module phase and before the UDC wait it
logs whether the `qcom-reboot-reason` platform driver has bound, reported as
`usb-init: qcom-reboot-reason bound` or `usb-init: qcom-reboot-reason not
bound`. Right after `usb-init: starting` it starts a subshell that sleeps 150 s
and then, unless `/run/keep` exists, logs `usb-init: self-recovery ->
bootloader` and calls `/bin/restart2 bootloader`. If that call returns it logs
`usb-init: self-recovery RESTART2 failed; falling back to reboot -f` and runs
BusyBox `reboot -f`. The subshell is backgrounded before the module loop, so a
blocked `insmod` cannot stop it, and a reachable operator disables it with
`touch /run/keep`. The module sequence, the 10 s UDC wait and the gadget and
sshd path are otherwise byte-for-byte the #44 init.

The 150 s budget covers the measured attempt-20 behaviour with margin: the
closure finished in about 1 s and the UDC wait adds 10 s, and the budget stays
far below the 180 s observation window the physical measurement uses. It is a
fixed `sleep`, not a watchdog, so it fires even if init is wedged in one
`insmod`.

`/bin/restart2` is the only new binary. It is a freestanding static aarch64
ELF, built reproducibly from the committed `initramfs/restart2.c` with
`aarch64-linux-gnu-gcc -nostdlib -static` and no dynamic interpreter. It issues
`reboot(2)` with `LINUX_REBOOT_CMD_RESTART2` and accepts only `bootloader` and
`recovery`, so `qcom-reboot-reason` can store the matching PON reason. BusyBox
`reboot` passes no command string and cannot do this. The helper is 872 bytes,
SHA-256
`fbe1472929510910b7fbb570d98ad939a2f39fd13786d000bb67ed46434b29f7`; its source
is SHA-256
`6806922e9e5138df25ee13e5f11d4fad555479830436e283b040b6e666133f96`.

The builder reuses the verified debug gzip `caa3eb82…` as a source cpio and
changes only `/init` and the added `bin/restart2`. The resulting 3,485,696-byte
newc carries zero `.ko` and hashes to
`71eae6972aeac3b5be7a5086f8560665719e84133496b23d77a6b034477c3793`.
Stock LZ4 HC level 12 makes one 1,929,803-byte block (1,929,811-byte legacy
frame) at offset 4,096, inside the 2,117,632 bytes before the signed tail. Only
header field `ramdisk_size@12` changes, from 2,113,581 to 1,929,811; the
187,821-byte gap to offset 2,121,728 is zero; all 6,266,880 bytes from the
signed `AVB0` block through the `AVBf` footer are unchanged. The candidate uses
no new kernel, is not signed, and claims no AVB, ABL or device verdict.

`scripts/build-init-boot-self-recovering.sh` produced two byte-identical
candidate runs and kept one image outside Git. `scripts/verify-bootimg.sh`
passed, including the #44 closure-list SHA, the zero-`.ko` check and negative
fixtures that reject an init with no timer, a timer inside or after the module
loop, a timer that ignores `/run/keep`, a missing loading marker, a marker that
follows `insmod`, a removed bind check, a reordered module list, a missing
helper, a helper with an interpreter, a non-aarch64 helper, an altered or
truncated helper, a planted `.ko`, a modified header or signed tail and every
repeated prior SHA, including `cdb9458f…`, `3932504a…`, `f4a00ce3…` and
`baa33fd4…`. `bash -n`, `shellcheck` and `git diff --check` pass. The only next
physical step belongs to the human coordinator under the standing mission-shift
approval; repository work neither performs nor authorizes a flash. This leaves
#12 and the encrypted-userdata release gate untouched.

A later measurement of this one image, flashed only to `init_boot_a` with stock
`boot_a` and `vendor_boot_a` untouched, and observed for at least 180 s before
any button press, distinguishes four outcomes. None is claimed here.

- **Fastboot at about 150 s, pstore shows `loading` and `loaded` lines through
  the end.** Init ran, the closure is readable module by module, and the
  UDC/gadget question is answered from pstore. Later init experiments can rely
  on the same recovery.
- **Fastboot, pstore ends at `loading X`.** Module X hung or crashed the kernel
  path. That module is the blocker, not USB.
- **Own init runs again, pstore shows `qcom-reboot-reason not bound`.** The
  bootloader reason is not honored from this init. The next question is the
  SDAM/PMIC provider chain, and the fallback command has to change, for example
  to `recovery`.
- **No reaction at all.** The kernel hung before the timer could matter. The
  next question is panic and watchdog behaviour on the kernel command line, not
  init.

## Stock vendor modules in the measured debug init (#44, host-only, 2026-10-23)

**Host-only image, not a boot result.** No device, flash, USB or userdata
operation was performed. The stock 6.1.84 kernel and `boot_a`, `vendor_boot_a`,
`dtbo`, `vbmeta` and slot B are unchanged. The one new image is
`$WORK/out/init_boot-vendor-modules.img` (8,388,608 bytes, SHA-256
`cdb9458f515bce3f1059f89cab0d7a78945f20e73f3cb7b34645c15646aab42a`).
It is different from measured `3932504a…`, `f4a00ce3…`, stock `baa33fd4…`
and all prior SHAs. Never reflash those earlier measured images.

Stock `vendor_boot_a` SHA-256 `23725940…` contains one PLATFORM fragment,
8,821,389 bytes of Android legacy LZ4 with four blocks. It decompresses to a
29,905,920-byte newc cpio with 317 arm64 `.ko` under `lib/modules`, plus
`modules.dep`, `modules.softdep`, `modules.load` (110 names) and
`modules.load.recovery` (314 names). The generic debug cpio has no `lib` or
`.ko`; the stock recovery cpio has no `lib/modules`. The kernel's
`init/initramfs.c` unpacks the concatenated initrd in one pass, with a later
entry able to overwrite an earlier path. The host checker verifies all vendor
module and metadata paths survive concatenation in both normal and recovery
orders, independent of which archive supplies `/init`. The measured #42
console records `Freeing initrd memory: 57716K`, which equals the 4 KiB-aligned
sum of vendor ramdisk (8,821,389) + #42 generic ramdisk (1,927,750) + stock
recovery ramdisk (48,350,666) + bootconfig (175), then `Run /init as init
process` and `usb-init: starting`. Normal stock Android's `10680K` matches
vendor + stock generic + bootconfig. This demonstrates that the unchanged
vendor ramdisk contributes `lib/modules` to the same rootfs as our own init;
no modules are copied into `init_boot`.

The stock `modules.load` entries and six USB additions from
`modules.load.recovery` (`phy-generic.ko`, `phy-msm-ssusb-qmp.ko`,
`phy-msm-snps-eusb2.ko`, `dwc3-msm.ko`, `repeater.ko`,
`repeater-qti-pmic-eusb2.ko`) yield a deterministic 126-module closure from
`modules.dep` and the applicable softdep `pre` edges. `dwc3-msm.ko` has 33
listed dependencies; the closure adds only 16 names outside `modules.load`:
`qmi_helpers.ko`, `phy-generic.ko`, `phy-msm-ssusb-qmp.ko`, `repeater.ko`,
`phy-msm-snps-eusb2.ko`, `repeater-qti-pmic-eusb2.ko`, `redriver.ko`,
`qcom_glink.ko`, `qcom_glink_smem.ko`, `qcom_smd.ko`, `rproc_qcom_common.ko`,
`pdr_interface.ko`, `pmic_glink.ko`, `ucsi_glink.ko`, `wcd_usbss_i2c.ko`,
 `dwc3-msm.ko`. The priority-stable topological sequence embedded in the frozen
 #44 init, `initramfs/init-44-vendor-modules`, is independently computed by
 `scripts/vendor-module-closure.py`; its newline-delimited list has SHA-256
 `57068a564c5cc1b37a93673ce7d59dd5607ffe4451bb1e261f3feb39db24be08`.
The vendor `.ko` vermagic version prefix differs from the stock 6.1.84 kernel;
stock boot logs show vendor modules loaded under that kernel. Runtime module
acceptance and UDC creation remain unmeasured for this image.

Before the UDC wait, init uses BusyBox `insmod /lib/modules/<name>` exactly
once per closure entry, sends each name plus success or the exact loader
stderr via `usb-init:` kmsg, and continues after failure. It records all UDC
names; if none appears, it logs up to 64 deferred-probe entries from debugfs.
If a UDC appears, the existing NCM/ECM gadget path reports bind success or
its exact write error. The key-only sshd and console remain.

The builder reuses the verified debug gzip `caa3eb82…` only as a source cpio,
replacing only its executable `/init` and emitting zero `.ko`. The resulting
3,484,160-byte newc hashes to
`89ab93ffb30073eb65af81da27434d6934580f4fd59101893a6990dcaf55ba12`.
Stock LZ4 HC level 12 creates one 1,929,210-byte block (1,929,218-byte
legacy frame) at offset 4,096. Only header field `ramdisk_size@12` changes
from 2,113,581 to 1,929,218; the 188,414-byte gap to offset 2,121,728 is
zero; all 6,266,880 bytes from the signed `AVB0` block through `AVBf` footer
are unchanged. The candidate uses no new kernel or copied `.ko`, is not
signed, and does not claim an AVB/ABL or device verdict.

`scripts/build-init-boot-vendor-modules.sh` produced two byte-identical
candidate runs and retained one image outside Git. `scripts/verify-bootimg.sh`
passed, including the vendor-rootfs proof, image envelope, closure order,
zero-`.ko` check and negative fixtures rejecting an image without the load
path, a planted `.ko`, modified header/tail, corrupted block and repeated
measured SHA. `bash -n`, `shellcheck` and `git diff --check` pass. The only
next physical step belongs to the human coordinator under the standing
mission-shift approval; repository work neither performs nor authorizes a
flash. This leaves #12 and the encrypted-userdata release gate untouched.

## Stock-kernel init_boot with the debug cpio in the stock LZ4 envelope (#42, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict, not an ABL verdict, and not evidence that the debug userspace
runs. The only kernel evidenced to run remains the stock 6.1.84 kernel; this
image does not change it.

`scripts/build-init-boot-lz4-debug-ramdisk.sh` starts from the verified stock
slot-A `init_boot_a`
(`baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193`,
8,388,608 bytes) and the cpio unpacked from the verified debug gzip
`$WORK/out/initramfs.cpio.gz`
(`caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f`,
1,672,600 bytes). The unpacked cpio is 3,481,088 bytes and hashes to
`2998685ec31696017828f92934e867b47fe14df375c259d37e98b40f3dd52ee7`. The gzip
bytes themselves are not reused. The builder refuses any other source, gzip,
length or structure. It does not call `avbtool`, does not sign and does not
rebuild a kernel. Both inputs are read-only and neither is copied into Git.
The image stays under `$WORK/out`.

The only change is the generic ramdisk. The builder compresses the unpacked
cpio with LZ4 HC level 12 through host `liblz4.so.1` 1.10.0 into exactly one
Android LZ4 legacy frame: magic `02 21 4C 18`, one 4-byte little-endian
compressed size, then one LZ4 block. The same level reproduces the stock
compressed block exactly. The frame is 1,927,750 bytes, with a 1,927,742-byte
block, inside the 2,117,632 bytes before the signed tail. The header v4 page
stays byte-identical apart from the little-endian ramdisk-size field at offset
12, which changes from 2,113,581 to 1,927,750. The kernel-size field stays 0.
The frame replaces the stock LZ4 generic ramdisk at offset 4,096. The 189,882
bytes from offset 1,931,846 to the original vbmeta offset 2,121,728 are zeroes.
Every byte from 2,121,728 through the terminal `AVBf` footer is copied
unchanged: the 832-byte signed `AVB0` block and the footer (version 1.0,
original size 2,121,728, vbmeta offset 2,121,728, vbmeta size 832).

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `init_boot_a` input | 8,388,608 | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` (unchanged) |
| debug `initramfs.cpio.gz` input | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` (unchanged) |
| unpacked debug cpio | 3,481,088 | `2998685ec31696017828f92934e867b47fe14df375c259d37e98b40f3dd52ee7` |
| `init_boot-lz4-debug-ramdisk.img` | 8,388,608 | `3932504af4a962d39d4c44def68eb9bd0c9a87e79d415279b40ed2e432243527` |

Two consecutive runs produced that same SHA-256. The SHA differs from stock
`baa33fd4…`, from the measured gzip debug `init_boot` `f4a00ce3…`, from the
earlier debug `init_boot` `f4b987ee…`, and from every prior boot SHA
(`5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`,
`968625c7…`, `db2c635d…`, `13a48ff9…`, `6891dc51…`, `d966172c…`,
`5a513998…`, `dc990b95…`, `e7fd2022…`, `7c409cde…`, `197aff11…`,
`7cd886a2…`, `f1406364…`) and from both vendor_boot sets (`bde3a3b3…`,
`6078269d…`). `boot`, `vendor_boot`, `dtbo`, `vbmeta` and slot B are not
inputs and are not changed.

`scripts/verify-init-boot-lz4-debug-ramdisk.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless the stock prefix matches
apart from the ramdisk-size field, the kernel is empty, the payload is one
Android LZ4 legacy frame at offset 4,096 whose single HC level-12 block
decompresses to the cpio inside `caa3eb82…`, the gap is zero, the signed tail
is byte-identical, the size is 8,388,608 and the SHA is the expected value and
none of the prior images. Negative fixtures reject a changed tail byte, a
second changed header field, a gzip payload, a modern LZ4 frame, more than one
LZ4 block, a block that decompresses to a different cpio, a short image, a
moved tail offset and every repeated prior SHA, including `baa33fd4…`,
`f4a00ce3…` and `f4b987ee…`.

**What a later measurement would distinguish (contract, not a test request).**
Only the physical coordinator may flash this one image, and only to
`init_boot_a`. Stock `boot_a` and stock `vendor_boot_a` stay unwritten.
`f4a00ce3…` and every earlier measured SHA stay unrestored as a test image.
Before any Android boot, capture pstore from the recovery session this boot
enters, or from Android if Android boots. Roll back to verified stock either
way.

- **Own init reached:** pstore or the running system shows the debug
  `usb-init` marker, or key-only SSH answers on the debug address. That would
  be the first own userspace on the stock kernel.
- **Android boots with no debug marker:** the stock kernel ignored or did not
  execute this ramdisk. The next question is ramdisk selection, not the
  compression.
- **Recovery again, or fastboot fallback:** matching the gzip result means
  compression was not the cause. A new fastboot fallback means this envelope
  loses the known-good boot. Roll back; do not combine it with a custom kernel.

None of those outcomes is claimed here, and none of them is an AVB verdict or
an ABL verdict. This does not close #12 and does not touch userdata.

## Stock-kernel init_boot with the debug ramdisk (#40, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict, not an ABL verdict, and not evidence that the debug userspace
runs. The only kernel evidenced to run remains the stock 6.1.84 kernel; this
image does not change it.

`scripts/build-init-boot-debug-ramdisk.sh` starts from the verified stock
slot-A `init_boot_a`
(`baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193`,
8,388,608 bytes) and the existing verified debug ramdisk
`$WORK/out/initramfs.cpio.gz`
(`caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f`,
1,672,600 bytes). It refuses any other source, ramdisk, length or structure.
It does not call `avbtool`, does not sign and does not rebuild a kernel. Both
inputs are read-only and neither is copied into Git. The image stays under
`$WORK/out`.

The only change is the generic ramdisk. The header v4 page stays
byte-identical apart from the little-endian ramdisk-size field at offset 12,
which changes from 2,113,581 to 1,672,600. The kernel-size field stays 0.
The debug gzip bytes replace the stock LZ4 generic ramdisk at offset 4,096.
Because the debug ramdisk is shorter, the 445,032 bytes from offset 1,676,696
to the original vbmeta offset 2,121,728 are zeroes instead of the tail of the
stock ramdisk. Every byte from 2,121,728 through the terminal `AVBf` footer is
copied unchanged: the 832-byte signed `AVB0` block and the footer (version
1.0, original size 2,121,728, vbmeta offset 2,121,728, vbmeta size 832).

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `init_boot_a` input | 8,388,608 | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` (unchanged) |
| debug `initramfs.cpio.gz` input | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` (unchanged) |
| `init_boot-debug-ramdisk.img` | 8,388,608 | `f4a00ce3a1926f9b54eaa958158691efaabe90a9ea715d2bac3d424095f2f948` |

Two consecutive runs produced that same SHA-256, and a second invocation of
the builder produced it again. The SHA differs from stock `baa33fd4…`, from
the earlier debug `init_boot` `f4b987ee…`, and from every prior boot SHA
(`5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`,
`968625c7…`, `db2c635d…`, `13a48ff9…`, `6891dc51…`, `d966172c…`,
`5a513998…`, `dc990b95…`, `e7fd2022…`, `7c409cde…`, `197aff11…`) and from
both vendor_boot sets (`bde3a3b3…`, `6078269d…`). `boot`, `vendor_boot`,
`dtbo`, `vbmeta` and slot B are not inputs and are not changed.

`scripts/verify-init-boot-debug-ramdisk.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless the stock prefix matches
apart from the ramdisk-size field, the ramdisk bytes are the verified gzip
newc cpio, the kernel is empty, the gap is zero, the signed tail is
byte-identical, the size is 8,388,608 and the SHA is the expected value and
none of the prior images. Negative fixtures reject a changed tail byte (first
vbmeta byte, a byte inside the block, the last block byte, a later tail byte
and both footer ends), a second changed header field (os version, header
version, header size, command line, header padding and magic), a non-gzip
ramdisk, a plain cpio, a gzip that is not newc, a short image and every
repeated prior SHA, including `baa33fd4…` and `f4b987ee…`.

**What a later measurement would distinguish (contract, not a test request).**
Only the physical coordinator may flash this one image, and only to
`init_boot_a`. Stock `boot_a` and stock `vendor_boot_a` stay unwritten, and
`7c409cde…`, `e7fd2022…`, `db2c635d…`, `6891dc51…` and the earlier
custom-kernel sets must not be flashed again.

- **Own init reached:** pstore or the running system shows the debug
  `usb-init` marker, or key-only SSH answers on the debug address. That would
  be the first own userspace on the kernel already shown to boot.
- **Android still boots with no debug marker:** the stock kernel ignored or
  did not execute this ramdisk. The layout is then the next question, not
  another kernel.
- **Fastboot fallback:** this ramdisk or its size change is enough to lose the
  known-good boot. Roll back; do not combine it with a custom kernel.

None of those outcomes is claimed here, and none of them is an AVB verdict or
an ABL verdict. This does not close #12 and does not touch userdata.

## Stock AVBf footer erasure on the #36 control (#38, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-avbf-footer-erase.sh` starts from the verified #36 image
`boot-avb0-window-erase.img`
(`e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f`,
100,663,296 bytes). It refuses any other source SHA, length or structural
window. After that check it copies the source and zeroes exactly bytes
`[100663232, 100663296)`. It does not call `avbtool`, does not sign, does not
generate another footer and does not alter `vbmeta_a`, the kernel, the signed
vbmeta block or any other byte. The read-only stock `boot_a` reference
(`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`) is used
only to prove the source split and the stock footer fields. Neither image is
copied into Git. The result stays under `$WORK/out`.

The source split, checked before any output is written, is the #23
stock-kernel prefix (`13a48ff9…`, first 13,955,072 bytes), an all-zero
standalone AVB0 window at `[13955072, 13971456)`, and every byte from
13,971,456 onward equal to stock `197aff11…`. That stock tail ends with a
64-byte `AVBf` footer: version 1.0, original size 13,971,456, vbmeta offset
13,971,456, vbmeta size 2,496. The 2,496-byte signed `AVB0` block at that
offset is unchanged. The only change from the already measured Android-booting
`e7fd2022…` image is those terminal 64 bytes, replaced by zeroes.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #36 `boot-avb0-window-erase.img` source | 100,663,296 | `e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f` (unchanged input) |
| stock `boot_a` reference (read-only check) | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-avbf-footer-erase.img` | 100,663,296 | `7c409cdefe9e0f24cbe53e44d5bbab8ff50adadb9fbfb26d64917fe1a6fc4ddf` |

Two consecutive runs produced that same SHA-256. Bytes before offset
100,663,232 are byte-identical to `e7fd2022…`. The final 64 bytes are zero.
The SHA differs from `e7fd2022…`, `db2c635d…`, `6891dc51…`, `13a48ff9…`,
`968625c7…`, `d966172c…`, `5a513998…`, `dc990b95…` and stock `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs and are
not combined with this image.

`scripts/verify-avbf-footer-erase.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless the source SHA and length, prefix, zero AVB0 window,
signed-block identity, stock footer fields, byte equality before offset
100,663,232, the 64 zero footer bytes, the fixed size and the expected SHA all
hold, and the SHA is none of the prior images. Negative fixtures reject a
wrong source SHA or length, a changed prefix, a changed erased AVB0 window, a
changed signed vbmeta block, a one-byte change outside the 64-byte footer, a
nonzero output-footer byte, an incorrect SHA and a repeated prior SHA
(`e7fd2022…`, `db2c635d…`, `6891dc51…`, `13a48ff9…`, `968625c7…`,
`d966172c…`, `5a513998…`, `dc990b95…`, `197aff11…`).

**What a later measurement would distinguish (contract, not a test request).**
A fast return to fastboot, matching `db2c635d…`, would mean the terminal
`AVBf` bytes were necessary for the Android-booting control. A normal Android
boot, matching `e7fd2022…`, would mean those footer bytes are not individually
necessary and the signed vbmeta block or remaining layout is the next
question. A third mode is recorded as such. Neither outcome is an AVB verdict,
an ABL verdict, USB or SSH success, or a result of this host control. Only the
physical coordinator may decide whether to test this one new image alone.
`e7fd2022…` must not be flashed again.

## Stock-kernel standalone AVB0 window erasure (#36, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-avb0-window-erase.sh` starts from the verified #23 control
`boot-stock-kernel.img`
(`13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450`,
13,955,072 bytes), appends exactly 16,384 zero bytes, and then appends the
bytes of the read-only host stock `boot_a` reference
(`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`) from
offset 13,971,456 through the end. It refuses any other source, stock
reference, window or length. It does not call `avbtool`, does not add a
footer and does not sign or alter the signed tail. The stock image is only a
byte source and is never copied into Git. The image stays under `$WORK/out`.

In stock `boot_a`, bytes `[13955072, 13971456)` are the standalone 16,384-byte
`AVB0` record (3,479 nonzero bytes). The signed vbmeta block starts at
13,971,456 and the `AVBf` footer ends the image. The only change from the
already measured stock-tail overlay `968625c7…` is that window, replaced by
zeroes. That overlay is reconstructed in memory by the verifier self-test only
and is never written or packaged.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #23 `boot-stock-kernel.img` input | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` (unchanged prefix) |
| stock `boot_a` reference (tail source) | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-avb0-window-erase.img` | 100,663,296 | `e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f` |

Two consecutive runs produced that same SHA-256. The first 13,955,072 bytes
are byte-identical to `13a48ff9…`. Bytes `[13955072, 13971456)` are all zero.
The 86,691,840 bytes from offset 13,971,456 onward are byte-identical to stock
`197aff11…`. The SHA differs from `968625c7…`, `db2c635d…`, `13a48ff9…`,
`6891dc51…`, `d966172c…`, `5a513998…`, `dc990b95…` and `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs and are
not combined with this image.

`scripts/verify-avb0-window-erase.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless the length, SHA-256, prefix identity, zero window and
signed-tail identity all hold and the SHA is none of the prior images.
Negative fixtures reject a changed prefix byte, one nonzero byte in the erased
window (first and last), a changed signed-tail byte (first and last), a window
of any other size (zero, 12,288, 8,192, 20,480 bytes, and a short image) and a
repeated prior SHA (`968625c7…`, `db2c635d…`, `13a48ff9…`, `6891dc51…`,
`d966172c…`, `5a513998…`, `dc990b95…`, `197aff11…`).

**What a later measurement would distinguish (contract, not a test request).**
A fast return to fastboot, matching `db2c635d…`, would mean erasing the
standalone `AVB0` record is sufficient. A normal Android boot, matching
`13a48ff9…` and its stock-tail overlay, would mean that record is not
sufficient and the remaining full-size variable is the signed vbmeta block or
footer. Absence of a new pstore record stays inconclusive. Only the physical
coordinator may decide whether to test this one image alone.

## Stock-kernel full-size blank-tail control (#34, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-blank-tail-control.sh` starts from the verified #23 control
`boot-stock-kernel.img`
(`13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450`,
13,955,072 bytes) and refuses any other source or length. It copies that
image and appends exactly 86,708,224 zero bytes. It does not call `avbtool`,
does not add a hash footer and does not sign anything. The #32 image
`boot-stock-full-footer.img`
(`6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555`) is a
comparison input only and is not packaged again.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #23 `boot-stock-kernel.img` input | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` (unchanged prefix) |
| `boot-blank-tail.img` | 100,663,296 | `db2c635d5c51aed47cf6a626244bba5be6e6eeb240f0dd2d0ed0e72d85fdff00` |

Two consecutive runs produced that same SHA-256. The first 13,955,072 bytes
are byte-identical to `13a48ff9…`. Every one of the following 86,708,224 bytes
is zero. There is no `AVB0` block and no `AVBf` footer. The image differs from
`6891dc51…` only in that tail: the unsigned metadata is replaced by zeroes.
The SHA differs from `5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`,
`55fa78ca…`, `13a48ff9…`, `d966172c…`, `5a513998…`, `dc990b95…`, `6891dc51…`
and stock `197aff11…`. `init_boot` `f4b987ee…` and `vendor_boot` `6078269d…`
are not inputs and are not combined with this image. The image stays under
`$WORK/out` and is not committed.

`scripts/verify-blank-tail-control.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless the length, SHA-256, prefix identity and zero tail all
hold, and unless the image differs from `6891dc51…` only in that tail.
Negative fixtures reject a changed prefix byte, one nonzero tail byte, a short
image and a repeated prior SHA (`6891dc51…`, `13a48ff9…`, `d966172c…`,
`5a513998…`, `dc990b95…`, `197aff11…`).

## Stock-kernel unsigned full-size footer control (#32, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict. No test-kernel marker is expected from
this stock payload.

`scripts/build-stock-full-footer.sh` starts from the verified #23 control
`boot-stock-kernel.img`
(`13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450`,
13,955,072 bytes) and refuses any other source. It copies that image and
applies exactly the existing unsigned footer invocation from
`scripts/build-full-boot-footer.sh`, using the pinned `avbtool` 1.4.0
(SHA-256 `1aa6f2b462aa67aa3fdf488bee83ab517de8ad9d8228c7b45c35267ab2cf6781`):

```sh
python3 "$AVBTOOL" add_hash_footer \
	--image "$candidate" \
	--partition_name boot \
	--partition_size 100663296 \
	--hash_algorithm sha256 \
	--algorithm NONE \
	--salt d41d8cd98f00b204e9800998ecf8427e
```

No signing key is created or stored. The builder refuses another source,
algorithm, salt, partition size or footer placement through
`scripts/verify-stock-full-footer.py` before publishing the candidate. The
image stays under `$WORK/out` and is not committed.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| #23 `boot-stock-kernel.img` input | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` (unchanged prefix) |
| `boot-stock-full-footer.img` | 100,663,296 | `6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555` |

Two consecutive runs produced that same SHA-256. The first 13,955,072 bytes
are byte-identical to `13a48ff9…`. The footer references a 448-byte `AVB0`
block at offset 13,955,072. `avbtool info_image` reports algorithm `NONE`,
hash algorithm `sha256`, partition name `boot`, salt
`d41d8cd98f00b204e9800998ecf8427e`, image size 100,663,296, original image
size 13,955,072 and an empty authentication block. The SHA differs from
`5e866c54…`, `84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`,
`13a48ff9…`, `d966172c…`, `5a513998…`, `dc990b95…` and stock `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs and are
not combined with this image.

Against the failed #25 image `d966172c…`, the only structural differences are
the stock kernel payload in place of the debug kernel payload and the hash
descriptor that covers it. The boot header page matches apart from the
little-endian kernel-size field (13,949,926 versus 15,746,607). The 448-byte
`AVB0` block matches after substituting the covered size and digest, and the
final footer matches after substituting the original size and vbmeta offset.
Both use algorithm `NONE` and the same salt.

`scripts/verify-stock-full-footer.py`, called by `scripts/verify-bootimg.sh`,
fails closed unless all of those conditions hold. Negative fixtures reject a
changed prefix byte, algorithm type 1 instead of `NONE`, a different salt, a
footer that points away from offset 13,955,072, a truncated image, a stale
descriptor digest and a repeated prior SHA.

## Stock-kernel image_size header control (#30, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict, not an ABL verdict, and not evidence that the declared reservation
is the physical cause. No test-kernel marker is expected from this stock
payload.

The rejected #29 envelope mixed two variables and is not repeated. Matching
both the debug `image_size` (55,508,992) and the debug decompressed length
(41,859,584) produced a best gzip payload of 13,957,009 bytes, 2,987 past the
stock bound, and packaged nothing. This control changes only the declared
reservation.

`scripts/build-image-size-control.sh` decompresses the gzip payload of the
SHA-pinned stock slot-A `boot_a` reference
(`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`,
100,663,296 bytes) and checks its arm64 header: `text_offset = 0`, flags
`0xa`, three zero reserved words, `ARMd` magic and PE offset `0x40`. It reads
the verified debug `Image.gz`
(`b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277`) only to
confirm its `image_size`, then changes the little-endian field at decompressed
byte 16 from 35,913,728 (`0x2240000`) to 55,508,992 (`0x34f0000`). The
decompressed length stays 35,224,064. No byte is appended, and `code0`,
`code1`, flags, `text_offset` and every other stock kernel byte stay unchanged.

The builder recompresses with deterministic zlib deflate level 9 inside the
stock gzip framing: no filename, zero mtime, OS byte 3 and `XFL` byte 2. The
payload is exactly 13,949,926 bytes, the existing stock kernel-size field, so
the header page is not rewritten. Any other length fails closed. The payload
replaces the stock gzip bytes in a copy of the 100,663,296-byte slot-A image.
The byte immediately after the payload stays the stock zero, and the rest of
the zero-padding window, the separate AVB0 record at 13,955,072, the signed
vbmeta block and the footer are copied unchanged. Nothing is re-signed and no
AVB metadata is added or removed. The image stays under `$WORK/out` and is not
committed.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `boot_a` input | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-image-size.img` | 100,663,296 | `dc990b9517d53431fcaeebb2b0498e6e64d3e7cbbc7e469d3e0bfc73abe00075` |

Two consecutive runs produced that same SHA-256. The decompressed images
differ at bytes 16 through 23 only. The SHA differs from `5e866c54…`,
`84f7f5ea…`, `116b1662…`, `1fdc2570…`, `55fa78ca…`, `13a48ff9…`,
`d966172c…`, `5a513998…` and stock `197aff11…`. `init_boot` `f4b987ee…` and
`vendor_boot` `6078269d…` are not inputs and are not combined with this image.

`scripts/verify-image-size-control.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless that eight-byte field is the
only kernel difference, the decompressed length is 35,224,064, the gzip
framing and 13,949,926-byte size match, the boot header page is unchanged, the
AVB record and footer bytes are unchanged, and the salted SHA-256 of the first
13,971,456 bytes differs from the stock descriptor digest. Negative fixtures
reject a second changed kernel byte, an appended zero tail, a payload longer
than 13,949,926 bytes and a decompressed length other than 35,224,064.

## One-byte stock hash-boundary control (#27, host-only, 2026-10-22)

**This is a host-only control, not a boot result.** No device, fastboot, adb
or USB operation was performed, and nothing here asks for one. It is not an
AVB verdict and not an ABL verdict.

`scripts/build-hash-boundary-control.sh` copies the SHA-pinned stock slot-A
`boot_a` reference (`197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`,
100,663,296 bytes) and changes only byte offset 13,954,122 from `0x00` to
`0x01`. That offset is inside the zero padding `[13954022, 13955072)`, after
the gzip payload at `[4096, 13954022)` and before the separate AVB0 record at
13,955,072. It is inside the 13,971,456-byte prefix covered by the chained
hash descriptor. The builder refuses any other source image, a non-zero source
byte at that offset, and any output whose length is not 100,663,296. The image
stays under `$WORK/out` and is not committed.

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| stock `boot_a` input | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` (unchanged) |
| `boot-hash-boundary.img` | 100,663,296 | `5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b` |

Two consecutive runs produced that same SHA-256. A byte compare against the
stock reference found exactly one difference: offset 13,954,122, `0x00` to
`0x01`. The SHA differs from `5e866c54…`, `84f7f5ea…`, `116b1662…`,
`1fdc2570…`, `55fa78ca…`, `13a48ff9…`, `d966172c…` and stock `197aff11…`.
`init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` are not inputs.

`scripts/verify-hash-boundary-control.py`, called by
`scripts/verify-bootimg.sh`, fails closed unless every byte except that offset
matches stock; the offset is inside the padding window and outside the gzip
payload; the gzip payload, header page, separate AVB0 record, signed vbmeta
block and final footer are byte-identical to stock; `avbtool info_image`
reports the same `SHA256_RSA4096` algorithm, public-key SHA-1
`407b99d1f65947192fb4591e5732bc1b1da9d95a`, image size 100,663,296, original
image size 13,971,456 and descriptor set; and the salted SHA-256 of the first
13,971,456 bytes differs from the stock hash descriptor digest. The negative
fixture changes the last gzip payload byte, outside the padding window, and is
rejected. Further fixtures cover a second padding byte, a different padding
offset, a non-zero source byte, a short image and a repeated prior SHA.

## Stale boot_a AVB footer model (#25, host-only, 2026-10-22)

**This is a model of libavb, not an observed ABL verdict.** Nothing here was
flashed or booted, and the model does not say what ABL does with an unlocked
device. `scripts/verify-post-flash-avb.py`, called by
`scripts/verify-bootimg.sh`, models a fastboot flash as an overlay: the
candidate image replaces the start of the SHA-pinned stock partition image and
the tail is left untouched. It then classifies the result with the same parser
as the stock checks: footer magic and bounds, a well-formed AVB0 record at the
footer-referenced offset, and the separate boot AVB0 record. Negative fixtures
cover a footer pointing into payload bytes, a truncated footer and an intact
footer. Where an earlier image is no longer retained on the host, the
classification is derived from the recorded size and kernel/ramdisk lengths and
is marked as such; the verifier refuses that path if the recorded size could
reach the stock metadata.

Stock `boot_a` is 100,663,296 bytes. Its footer (`AVBf`, last 64 bytes) points
at a vbmeta block at offset 13,971,456 (2,496 bytes). A separate AVB0 record
starts at 13,955,072 and hashes the shorter kernel-only prefix. Every earlier
debug `boot.img` ends at or before 16,777,216 bytes, so the stock footer
survives the overlay but the bytes it references, and the separate AVB0 record,
are now inside the debug payload.

| image | bytes | SHA-256 | footer | vbmeta at footer offset | separate boot AVB0 | predicted post-flash state | evidence |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| boot #8/#10 `5e866c54…` | 16,777,216 | `5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | layout-derived; image bytes not retained |
| boot #14 `84f7f5ea…` | 16,777,216 | `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | byte-verified overlay |
| boot #16 `1fdc2570…` | 15,101,952 | `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | byte-verified overlay |
| boot #18 `116b1662…` | 15,753,216 | `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | layout-derived; image bytes not retained |
| boot #21 `55fa78ca…` | 15,753,216 | `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` | valid (stock, stale) | invalid | invalid | **invalid chained metadata** | byte-verified overlay |
| boot #23 control `13a48ff9…` | 13,955,072 | `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` | valid (stock) | valid | valid | **intact metadata** | byte-verified overlay |
| boot stock `197aff11…` | 100,663,296 | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` | valid | valid | valid | **intact metadata** | byte-verified overlay |
| init_boot #21 `f4b987ee…` | 1,679,360 | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | valid (stock) | valid (offset 2,121,728) | n/a | **intact metadata** | byte-verified overlay |
| vendor_boot #21 `6078269d…` | 11,108,352 | `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | valid (stock) | valid (offset 18,255,872) | n/a | **intact metadata** | byte-verified overlay |
| boot #25 candidate `d966172c…` | 100,663,296 | `d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131` | valid (new, unsigned) | valid | n/a (replaced) | **intact unsigned footer** | byte-verified overlay |

The model predicts **invalid chained metadata** for `5e866c54…`, `84f7f5ea…`,
`1fdc2570…`, `116b1662…` and `55fa78ca…`. It predicts **intact metadata** for
the #23 control `13a48ff9…`, stock `197aff11…`, and the #21 `init_boot` and
`vendor_boot` overlays. Those two leave their stock footers and vbmeta blocks
untouched; only the stock hash comparison fails, which this model does not
treat as invalid metadata. `55fa78ca…` is recorded as tested and failed in the
`boot_a`-alone configuration (`attempt-20261022-0620-boota-marker`), the same
fastboot fallback as `116b1662…`, not as untested.

The #14 row is byte-verified because the #16 image plus the verified gzip cpio
recreates `84f7f5ea…` exactly, which the #16 verifier already proved. The #8
and #18 rows use the sizes and kernel/ramdisk lengths recorded in this file
(16,777,216 with a 15,097,006-byte kernel and 1,672,600-byte ramdisk; 15,753,216
with a 15,746,316-byte kernel and an empty ramdisk). Both recorded payloads
extend past the stock vbmeta at 13,971,456, so the stale footer points into
payload bytes. The verifier rejects a recorded layout that does not reach that
metadata, so an earlier image cannot silently pass.

**Single change from the verified #21 boot.** `scripts/build-full-boot-footer.sh`
copies `boot.img` `55fa78ca…` and appends one unsigned AVB hash footer with the
pinned `avbtool` 1.4.0 (`add_hash_footer --partition_name boot
--partition_size 100663296 --algorithm NONE`, fixed salt
`d41d8cd98f00b204e9800998ecf8427e`). No signing key is created or stored. The
image is exactly 100,663,296 bytes. The hashed prefix is the 15,753,216-byte
#21 image, the footer-referenced vbmeta is 448 bytes at offset 15,753,216, and
the algorithm is `NONE` with a zero-length authentication block. Kernel bytes,
header page, command line, empty generic ramdisk, `init_boot.img` and
`vendor_boot.img` stay at the #21 hashes. Two consecutive runs produced the
same SHA-256 `d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131`,
which differs from every prior boot and from stock. The candidate stays under
`$WORK/out` and is not committed.

The candidate must not be combined with the #21 marker image or the #23 control
in one flash. Whether any slot-A test happens belongs to the physical
coordinator under the existing slot-A scope. No device operation was performed
for #25.

## Stock-kernel control image (#23, host-only, 2026-10-22)

**Single variable:** the kernel payload. `scripts/build-stock-kernel-control.sh`
copies the verified #21 `boot.img` and replaces only its gzip kernel bytes
with the unmodified gzip payload from the read-only stock slot-A `boot_a`
reference. The kernel-size field and the resulting image length are the only
other bytes that change. The stock kernel is not rebuilt and its bytes are
not copied into Git.

The #21 header page stays byte-identical apart from the little-endian
`kernel_size` at offset 8: header v4, header size 1,584, OS version 0,
signature size 0, empty generic ramdisk and the #21 command line
`console=ttynull stack_depot_disable=on cgroup_disable=pressure
kasan.page_alloc.sample=10 kasan.stacktrace=off kvm-arm.mode=protected
bootconfig ioremap_guard loglevel=6`. The payload starts at offset 4,096 and
the image ends at the next 4,096-byte boundary with zero padding and no AVB
footer or separate AVB0 record. `init_boot.img`, `vendor_boot.img`, the DTB
blob, bootconfig and both debug ramdisks are not inputs to this step and stay
at the verified #21 hashes.

| artifact | verified #21 (bytes; SHA-256) | #23 control (bytes; SHA-256) |
| --- | --- | --- |
| `boot.img` | 15,753,216; `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` | unchanged input; **identical** `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` |
| `boot-stock-kernel.img` | not produced | 13,955,072; `13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450` |
| embedded gzip payload | 15,746,607; `b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277` | 13,949,926; **identical to stock slot-A payload** `dcbd8ae71b7e6341c3604c35360213b1d40a69ac38672e247772d4af399c3651` |
| decompressed `Image` | 41,859,584 | 35,224,064 (stock 6.1.84; not rebuilt) |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |

The control SHA differs from `55fa78ca…`, `116b1662…`, `84f7f5ea…`,
`5e866c54…` and `1fdc2570…`, and from stock `boot_a` `197aff11…`. Two
sequential runs of `scripts/build-stock-kernel-control.sh` produced the same
control SHA. `scripts/verify-bootimg.sh` still checks the #21 image and the
unchanged `init_boot`/`vendor_boot`/DTB/ramdisk hashes, then
`scripts/verify-stock-kernel-control.py` fails closed unless the control
payload equals the stock slot-A gzip bytes, the header page equals #21 apart
from kernel size, the command line and empty ramdisk match, the image ends on
the aligned kernel with zero padding, both decompressed images share the arm64
`Image` fields (`MZ` branch `0xfa405a4d`, `text_offset = 0`, flags `0xa`,
reserved words zero, `ARMd` magic, PE offset `0x40`), and the control SHA is
none of the prior boots. Negative fixtures cover a changed payload byte, the
#21 payload left in place, dirty padding, appended data, a changed command
line, a nonempty generic ramdisk, a nonzero `text_offset`, different arm64
flags and a repeated prior SHA.

**How a later authorized capture discriminates (contract, not a test
request).** This control is not the unmeasured #21 marker image and must not
be combined with it. A capture is useful only if it is read *before* any later
kernel boot. No device operation was performed for #23.

- **Layout/header rejection:** the control follows the same under-five-second
  return to fastboot as test `boot_a` `116b1662…`. The debug 6.1.78 payload is
  not required for that failure.
- **Kernel-payload failure:** the control gets farther than that fastboot
  return, or leaves a stock 6.1.84 console from the control boot. The debug
  6.1.78 payload remains the isolated variable.
- **No kernel record:** the control fails without a usable new console. That
  still does not prove an AVB accept or reject verdict.
- **Invalid:** another kernel boots before the control attempt's pstore is
  read. The later boot can replace the buffer, so the capture proves nothing.

## Pre-ramoops marker and pstore panic (#21, host-only, 2026-10-22)

**Single kernel variable:** `configs/asteroids-debug-marker.fragment` is merged
last, after the measured stock command line and the #18 USB closure. It changes
exactly two settings relative to the verified #18 `.config`:

1. `CONFIG_CMDLINE` is the measured stock A059P value with one appended token,
   `sm7635-boot-marker`. With the unchanged `CONFIG_CMDLINE_EXTEND=y`, the
   pinned 6.1.78 `early_init_dt_scan_chosen()` copies `CONFIG_CMDLINE` first
   and then appends the bootloader `bootargs`, so the token ends the built-in
   part of the kernel's effective command line and is printed in the kernel's
   `Kernel command line:` line.
2. `CONFIG_PANIC_TIMEOUT=-1` is restated. It was already `-1` in the stock
   `config.gz` and the #18 build; `kernel/panic.c` initializes `panic_timeout`
   from it, and the `panic=` command-line parameter overrides it. The value is
   therefore present even if the bootloader supplies no `panic=` argument.
   Because it is non-zero, `panic()` reaches `emergency_restart()` without a
   delay instead of staying silent; the kmsg/console dump into the ramoops
   buffer happens before that restart.

**Issue exception — `CONFIG_PSTORE_CONSOLE_SIZE`:** the symbol does not exist
anywhere in the pinned vendor Kconfig tree at
`d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7` (`fs/pstore/Kconfig` has only
`PSTORE_BLK_CONSOLE_SIZE`, which is a pstore/blk setting and is not selected).
It is also absent from the measured stock `config.gz`. No symbol was added, no
header was redefined and no upstream patch was applied. The 2 MiB console
reservation is instead the stock device-tree value already verified on the #18
chain: after stock DTBO entry 65 is applied to vendor DTB index 9,
`/reserved-memory/ramoops_region` has `reg = <0x0 0x81f20000 0x0 0x400000>`,
`console-size = <0x200000>` and `pmsg-size = <0x200000>`. `fs/pstore/ram.c`
reads `console-size` from that node, so the reservation does not depend on the
missing Kconfig symbol. `CONFIG_PSTORE=y`, `CONFIG_PSTORE_CONSOLE=y` and
`CONFIG_PSTORE_RAM=y` are unchanged.

Nothing else moves. The diff of the #18 `.config` against this build is that
one command-line line. `init_boot.img`, `vendor_boot.img`, the 20 stock DTBs,
the 175-byte bootconfig, both gzip ramdisks and the boot/vendor header command
lines are byte-identical to #18. The boot header command line intentionally
does **not** carry the marker: the marker lives in the kernel so it can only
appear in a console written by this kernel.

| artifact | verified #18 (bytes; SHA-256) | #21 (bytes; SHA-256) |
| --- | --- | --- |
| `.config` | 237,546; `5781d141305c4f27bdc0dd3e69a1136a7e9be3c4fbc538d8b5c11e6f2442cd32` | 237,565; `93acd0920ceadb767625f06a30d992aea0901000e86abec7b61c7e6827f0fa28` |
| `Image` | 41,859,584; `a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29` | 41,859,584; `34fee908da7366f2f174eca4edcc84d732c709067cf81dcba43dfde627dffb13` |
| `Image.gz` | 15,746,316; `9055503e67a1321468fa75608b677eec257c403345a7a6de6709369fb71d5d4a` | 15,746,607; `b2280f309e50c65ccc422dec8958551a525680b33e78dd98d455867980d1a277` |
| `boot.img` | 15,753,216; `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` | 15,753,216; `55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af` |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| vendor `dtb.img` | 9,419,891; `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` | 9,419,891; **identical** `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| gzip cpio in both ramdisks | 1,672,600; `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` | 1,672,600; **identical** `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The new `boot.img` SHA differs from every previously tested boot
(`5e866c54…`, `84f7f5ea…`, `116b1662…`) and from the untested #16 boot
`1fdc2570…`. Two sequential `scripts/build-bootimg.sh` runs produced the same
SHA set, and `scripts/verify-bootimg.sh` passed on both. The verifier checks
the marker in the fragment, merged config, built `.config` and the IKCONFIG
embedded in the unpacked kernel, checks the NUL-terminated command-line string
inside `Image`, asserts `CONFIG_PANIC_TIMEOUT=-1` and the existing pstore
options, and fails closed if `CONFIG_PSTORE_CONSOLE_SIZE` is either silently
dropped or synthesized while absent from `fs/pstore/Kconfig`. If a future pin
gains the symbol, the same check requires the fragment and the built config to
set it to `2097152`. Every existing geometry, AVB, DTB, ramdisk, recovery and
USB-closure check still passes, including the negative fixtures. Config
comparison against the read-only stock `config.gz`: 5,996 stock and 6,979 built
symbol lines, 5,924 identical, 72 stock-only or changed and 1,055 built-only or
changed. `CONFIG_CMDLINE` now differs from stock by exactly the marker token.

**How a later capture distinguishes kernel entry (contract, not a test
request).** A console is useful only if it is read *before* any later kernel
boot, because the next kernel replaces the ramoops buffer. Parsed marker
counts are the public record; raw pstore stays on the build host.

- **Kernel entry:** the pre-restore console contains the literal token
  `sm7635-boot-marker` (in the `Kernel command line:` line), or the 6.1.78
  banner. The token cannot come from a stock or recovery 6.1.84 session, from
  the boot header or from `vendor_boot`: only this kernel's built-in command
  line carries it. Console text after the banner then localizes the failure.
  `Kernel panic - not syncing` is an early panic; `usb-init` or dropbear
  progress is a later failure. With `panic_timeout` at `-1` a panic restarts
  at once, so the panic text survives only in the ramoops buffer; an
  immediate restart that leaves the buffer intact is expected, and a reset
  with no marker at all still counts as no kernel entry.
- **No kernel entry:** the attempt returns to fastboot or wedges, and the
  pre-restore console is still only the preceding stock or recovery 6.1.84
  session with zero occurrences of `sm7635-boot-marker`. That supports failure
  before this kernel executed, or before it initialized the stock ramoops
  region at `0x81f20000`. It is not, by itself, an AVB accept or reject
  verdict.
- **Invalid:** the console is read only after another kernel has booted. That
  boot can overwrite the attempt buffer, so the absence of the marker then
  proves nothing.

No previously flashed complete set may be repeated. Boots `5e866c54…`,
`84f7f5ea…` and `116b1662…` are burned, and the complete sets that used
`vendor_boot` `bde3a3b3…` or `6078269d…` have failed as wholes. This build
keeps `init_boot` `f4b987ee…` and `vendor_boot` `6078269d…` byte-identical,
which is valid for a host-only artifact; only a physically new `boot.img` SHA
makes a future set new. Whether any slot-A test happens, and the verified
rollback around it, belongs solely to the physical coordinator. No device
operation was performed for #21.

## Recovery-path boundary after #18 (`attempt-20261021-1717`, host-only, 2026-10-21)

**Observed:** The physical coordinator flashed the #18 single-variable slot-A
chain (`boot_a` `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce`,
`init_boot_a` `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89`,
`vendor_boot_a` `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d`;
all three writes OKAY). After `fastboot reboot` at 17:53:57+02:00, host USB
disconnected and re-enumerated as fastboot `18d1:d00d` within four seconds
(17:54:01) and stayed there through all 45 observations (225s) with no
`18d1:4ee2` gadget, adb or SSH. At 17:59:24, `fastboot reboot recovery` was
issued *while the test chain remained on slot A*; it also returned to fastboot
`18d1:d00d` within four seconds (17:59:28) and remained there for all 12
samples (60s). After restoring stock `boot_a`, `init_boot_a` and `vendor_boot_a`
(18:03:35-18:03:44), the identical `fastboot reboot recovery` succeeded
(`adb` recovery at 18:04:16). On-device block SHA-256 reads in recovery
matched the verified stock backups for `boot_a` (`197aff11…06d4d`),
`init_boot_a` (`baa33fd4…1e3193`), `vendor_boot_a` (`23725940…c1253`), and
unchanged `dtbo_a` (`759813db…e13c992`) and `vbmeta_a` (`cc1926d2…cdffe`);
stock Android then reached `sys.boot_completed=1`. Host-only logs are at
`~/phone-second-life-data/mb003/pstore/attempt-20261021-1717/`.

**Recovery partition resolution and pstore provenance (measured, not inferred):**
`scripts/verify-recovery-boundary.py` (invoked by `scripts/verify-bootimg.sh`)
checks `recovery_a.img` (`0c6767698ebb069064b450b109cde6a1172b478e30000fe852e7d9bc19dbae9e`,
byte-identical to `OrangeFox-R12.0_6.1-Unofficial-Asteroids.img`) and
`recovery_b.img` (`6065f68502838b3cb20a51eb6a6aa1b250f3a58553246d9c4259593a3769874b`).
Both are 100 MiB Android boot-header v4 images with **`kernel_size = 0`** and
legacy LZ4-compressed `070701` newc ramdisks at offset 4,096 (`48,350,666` and
`15,609,526` bytes), no DTB and no bootconfig, plus AVBf footers at `48,357,376`
and `15,613,952` (`RSA4096_SHA256`, `flags = 0`, `rollback_index = 1`;
`recovery_b`'s public key matches `vbmeta_a`'s `recovery` chain descriptor at
rollback location 1, while `recovery_a`'s self-signed key differs). Neither
`recovery` partition contains a kernel or DTB: on this header-v4 layout,
booting recovery **requires** the kernel from `boot_a` and the DTB/bootconfig
from `vendor_boot_a`. Every captured recovery-session console (`0134`, `0550`,
`0640`, `1156`) logs `Freeing initrd memory: 57900K` (`59,289,600` bytes =
4 KiB-aligned sum of `8,821,389`-byte `vendor_boot_a` PLATFORM ramdisk +
`2,113,581`-byte `init_boot_a` generic ramdisk + `48,350,666`-byte OrangeFox
`recovery_a` ramdisk + bootconfig = `59,285,811` bytes), whereas normal
Android boot (`1717` and `2026-10-19`) logs `Freeing initrd memory: 10680K`
(`10,936,320` bytes = 4 KiB-aligned sum of `vendor_boot_a` + `init_boot_a` +
bootconfig = `10,935,145` bytes). Therefore:

1. Neither conflicted note was wholly accurate: recovery does **not** run from
   `recovery_a` + `vendor_boot_a` without `boot_a` (`recovery_a` has no kernel),
   and it does **not** use `boot_a` only for a hardware-key menu. On `A059P`,
   ABL's recovery boot path loads `boot_a` (kernel) + `vendor_boot_a` (PLATFORM
   ramdisk, DTB index 9, bootconfig) + `init_boot_a` (generic ramdisk) +
   `recovery_a` (OrangeFox ramdisk appended last, overriding `/init`). Because
   all three flashed slot-A partitions (`boot_a`, `init_boot_a`, `vendor_boot_a`)
   are consumed by both normal boot and `fastboot reboot recovery`, and all
   three were restored together at 18:03:35-18:03:44 before recovery succeeded,
   stage 6 (`fastboot reboot recovery` failing in 4s on the test chain) proves
   the failure is **not** specific to normal-boot userspace or Android-mode
   bootconfig, while keeping all three modified slot-A partitions inside the
   candidate boundary.
2. Why `attempt-20261021-1717` `pstore` differs from `0134`/`0640`/`1156` (and
   why `ramoops` exposes the *previous* boot): Linux `pstore/ramoops` exposes
    the buffer saved by the **previous** kernel session in `/sys/fs/pstore`
   while writing the **current** session's console to the live ring buffer for
   the *next* boot.    In `0134`, `0640` and `1156`, a pre-flash recovery session was booted to
   hash slot-A partitions just before `reboot bootloader`; its `57900K`-initrd
   recovery log (`37.6s`, `35.5s` and `1402.9s` uptime respectively, each
   ending at `Reboot start, reason: reboot,bootloader` immediately before the
   test flash) remained in `ramoops` across the failed test reboot and was read
   back by the post-restore recovery boot. In `1717`, there was **no**
   pre-flash recovery boot: the phone rebooted directly from the ~2.4h stock
   Android session (`10680K` initrd, `Load bootconfig: 1279 bytes 80 nodes`,
   `sys.boot_completed=1` at `[17.764152]`, ending at `[8764.401407]
   BATTERY_CHG: battery_shut_down`) into fastboot at 17:53:22, failed the
   17:53:57 normal test reboot (4s to `18d1:d00d`) and the 17:59:24 test-chain
   recovery reboot (4s to `18d1:d00d`), and then booted stock recovery at
   18:03:44, which mounted `/sys/fs/pstore` and pulled that **intact
   pre-attempt Android console** (`1,073,964` bytes) and `pmsg` (`4,973` bytes).
   **Consequence:** across **all four** attempts (`0134`, `0640`, `1156`,
   `1717`), the post-restore recovery boot did **not** overwrite the attempt
   window before `/sys/fs/pstore` was read — rather, none of the four normal
   test reboots (nor the `1717` stage-6 test-recovery reboot) ever initialized
   or wrote to `ramoops` at `0x81f20000` (which happens at `~0.068s` on stock).
   That proves every tested chain failed **either** before kernel hand-off (in
   XBL/ABL) **or** before the test kernel could initialize and write to that
   `ramoops` reservation.
3. Host xHCI USB enumeration timing (`journalctl -k` on the build/test host)
   across all five failed reboots (`0134` at 01:34:16, `0640` at 06:44:34,
   `1156` at 12:22:09, `1717` normal at 17:53:57, `1717` stage-6 recovery at
   17:59:24) shows a **single** reset cycle (`USB disconnect` at `t = 0s`,
   full-speed `t = +1..2s`, high-speed `18d1:d00d` fastboot at `t = +4.0s`),
   matching the `4.0–5.0s` timing of a direct `adb reboot bootloader` entry into
   ABL (`0640` 06:44:12 -> 06:44:17, `1156` 12:21:35 -> 12:21:39, `1717`
   17:53:22 -> 17:53:27) with no intermediate second reset. This is strongly
   consistent with synchronous ABL rejection into fastboot within the same boot
   cycle, though an immediate post-jump reset before `ramoops` cannot be ruled
   out by USB timing alone.

| tested slot-A chain | `boot_a` / `init_boot_a` / `vendor_boot_a` SHA-256 prefixes | single variable changed | observed normal + recovery result |
| --- | --- | --- | --- |
| #8 (`0134`) | `5e866c54…` / `f4b987ee…` / `bde3a3b3…` | initial 3-image SSH set (built DTBs, duplicate boot ramdisk) | `<5s` return to `18d1:d00d`; no gadget/adb/SSH |
| #10 (`0640`) | `5e866c54…` / `f4b987ee…` / `6078269d…` | `vendor_boot_a`: stock 20-DTB blob (DTBO 65 applies to index 9) | `<5s` return to `18d1:d00d`; not sole cause |
| #14 (`1156`) | `84f7f5ea…` / `f4b987ee…` / `6078269d…` | `boot_a`: stock `CONFIG_CMDLINE` override (no `panic_on_taint`) | `<5s` return to `18d1:d00d`; not sole cause |
| #16 (untested) | `1fdc2570…` / `f4b987ee…` / `6078269d…` | `boot_a`: `ramdisk_size = 0` (generic ramdisk only in `init_boot_a`) | not physically flashed alone; carried into #18 |
| #18 (`1717`) | `116b1662…` / `f4b987ee…` / `6078269d…` | `boot_a`: `#16` empty boot ramdisk + built-in Volcano USB closure | `<5s` return to `18d1:d00d` on both `reboot` and `reboot recovery` |

**Plain non-discrimination statement and exact blocker (#12 Acceptance 2):**
Across all four physical attempts, `init_boot_a` `f4b987ee…`, `vendor_boot_a`
`6078269d…` (after #8), `dtbo_a` and `vbmeta_a` (with `flags = 0` and stock
hash/chain descriptors that none of the unsigned, footerless test images match)
stayed constant, and targeted `getvar` recorded only `serialno`,
`current-slot: a`, `unlocked: yes` and `product: pineapple` (`getvar all` is
not used because it wedged fastboot on `0332`/`0535`). Host-only evidence
**cannot** discriminate between:

- **Regime 1 — Bootloader/AVB or header-format rejection before kernel hand-off:**
  ABL rejects unsigned/footerless `boot_a` and/or `vendor_boot_a` against stock
  `vbmeta_a` (`flags = 0`), or rejects `vendor_boot_a`'s gzip PLATFORM ramdisk /
  unpadded size during both normal and recovery boot.
- **Regime 2 — Pre-`ramoops` kernel failure:**
  ABL hands off to the 6.1.78 `Image.gz` in `boot_a`, which resets before
  `ramoops` initializes at `0x81f20000`. The preserved pre-attempt Android
  console and ~4s return do not rule this out, but the absence of a second
  host USB reset is less consistent with a kernel-triggered restart (which
  normally produces a second disconnect/re-enumeration). No 6.1.78 marker is
  required for this regime. `~0.068s` is stock kernel's observed probe time,
  not a measured upper bound for the test kernel.
- **Regime 3 — Later kernel/init/USB failure:**
  Incompatible with this attempt-specific evidence **if** the 6.1.78 kernel
  actually initialized the same `ramoops` reservation: any subsequent
  console writes should replace the pre-attempt Android console. The host
  verifies DTBO 65 applies to vendor DTB index 9 and supplies
  `0x400000@0x81f20000`; it cannot prove that the kernel reached the driver,
  that ABL passed this DTB, or that the persistent region survived a power
  reset. A late failure with `ramoops` absent/never mounted remains an
  alternative, not a proven rejection verdict.

No new kernel/ramdisk/boot-image build is produced for #12: building another
unauthenticated `{boot_a, init_boot_a, vendor_boot_a}` perturbation without
isolating `{boot_a}` vs `{vendor_boot_a}` vs `vbmeta_a` would be a speculative
blind flash. The **exact blocker** is that neither the 17:53:57 nor 17:59:24
attempt has an ABL AVB accept/reject verdict, boot reason/retry status, or an
attempt-tagged pre-rollback pstore capture. The only captured `getvar` values
were identity, slot, unlocked state and product; an earlier `getvar all`
wedge means it is not a supported fallback. Stock rollback changed all three
slot-A partitions together, so it cannot isolate the kernel-bearing `boot_a`
from the DTB/bootconfig-bearing `vendor_boot_a`. The latter is a **controlled
constant** (`6078269d…`) in the failed #10/#14/#18 sets; those complete SHA
sets must not be repeated. A signed replacement for `vbmeta_a`/`dtbo_a` is
outside the existing slot-A-only approval, and a stock `vbmeta_a` mismatch is
not a verdict on an unlocked/orange device. In particular, the OrangeFox
`recovery_a` key differs from `vbmeta_a`'s recovery chain key, yet recovery
worked after stock rollback; the logs do not prove whether recovery loaded
`recovery_a` or `recovery_b`, so this cannot establish an AVB exception for
the normal boot path.

**Single selected discriminator (measurement, not a new flash plan):** an
attempt-tagged **first bootloader-side hand-off verdict** with partition name
and AVB/retry reason, collected *before* any stock/recovery boot, would directly
separate pre-kernel rejection from kernel entry. An explicit *reject* of
`boot_a` or `vendor_boot_a` proves regime 1. An explicit *accept* without a
6.1.78 marker still leaves regime 2 and loss of the ramoops channel possible.
A 6.1.78 kernel banner/progress marker in a pre-restore capture proves kernel
entry and distinguishes regime 2 if it stops before `/init`, versus regime 3
if `usb-init`/`dropbear` markers precede the failure. The 1717 record already
supplies an attempt-specific **upper bound**: the test kernel did not write to
`ramoops` during either failed window, while no post-test stock/recovery boot
had yet modified the saved pre-attempt Android console. No currently preserved bootloader-side verdict or supported narrow read-only
AVB/reason/retry channel exists; an earlier `getvar all` wedged fastboot.
Thus the remaining boundary between ABL rejection and pre-`ramoops` kernel
failure and the minimal corrective artifact are **unproven**. The exact remaining blocker is a supported,
bounded, attempt-tagged read-only ABL hand-off/verdict channel on slot A,
**before** any recovery boot or stock rollback; a serial/bootloader log
interface is not established from these host records and must not be guessed.
The strategist/coordinator owns any future measurement decision under the
existing slot-A-only boundary and must not repeat a failed full SHA set;
writing `vbmeta_a`/`dtbo_a` needs separate approval and is not a staged
artifact here. This document does not request any physical operation.
Verified stock rollback for the historical attempt was already measured on
all three restored partitions plus unchanged `dtbo_a`/`vbmeta_a`; only the
physical coordinator owns that boundary. The release-image userdata decision
is independent.

## Volcano USB driver reachability (#18, host-only, 2026-10-21)

**Path B selected:** `boot.img` alone changes relative to the verified #16
three-image chain. The `init_boot.img` and `vendor_boot.img` payloads and hashes
are unchanged, including both identical gzip debug ramdisks, all 20 stock vendor
DTBs, the 175-byte bootconfig, cmdlines and stock DTBO 65 selection. The new
last-applied `configs/asteroids-volcano-usb-builtin.fragment` only promotes
`=m` drivers to `=y`; it does not alter source DTBs, boot layout or initramfs.
The #16 `Image`, `.config`, `Image.gz` and boot bytes change as expected; no
modules are staged. `CONFIG_USB_DWC3_QCOM=y` matches `qcom,dwc3` but does **not**
match the actual `qcom,dwc-usb3-msm` Volcano wrapper. Kconfig alone is not
proof: the full pinned 6.1.78 `vmlinux` link now succeeds (the source also
needs eight local build-only trace include path fixes to compile the promoted
drivers). The unpacked `Image.gz` IKCONFIG equals the merged `.config`; the
verifier resolves the exact phandle suppliers after applying the SHA-verified
stock DTBO 65 to stock vendor DTB index 9. The public repository contains no
raw stock image, module, DTB, key or build artifact.

| merged board DT binding / dependency | pinned source driver / config | #16 -> #18 location |
| --- | --- | --- |
| `/soc/ssusb@a600000` `qcom,dwc-usb3-msm`; child `snps,dwc3` `dr_mode=otg` | `drivers/usb/dwc3/dwc3-msm-core.c` `USB_DWC3_MSM`; core `USB_DWC3` | `m` -> `y`; `y` -> `y` |
| child `usb-phy` `hsphy@88e3000` `qcom,usb-snps-eusb2-phy`, `ssphy@88e8000` `qcom,usb-ssphy-qmp-dp-combo` | `drivers/usb/phy/phy-msm-snps-eusb2.c` `USB_MSM_EUSB2_PHY`; `phy-msm-ssusb-qmp.c` `USB_MSM_SSPHY_QMP` | `m` -> `y` each |
| HS PHY `usb-repeater`/`dummy-supply`; PMIC parent and SPMI arbiter | `drivers/usb/repeater/repeater-qti-pmic-eusb2.c` `QTI_PMIC_EUSB2_REPEATER`, `USB_REPEATER`; `MFD_SPMI_PMIC`, `SPMI_MSM_PMIC_ARB` | `m` -> `y` each |
| parent clocks/resets (5 GCC clocks, 1 reset); HS/SS PHY GCC, RPMh and fixed clocks | `drivers/clk/qcom/gcc-volcano.c` `SM_GCC_VOLCANO`, `COMMON_CLK_QCOM`; `clk-rpmh.c` `QCOM_CLK_RPMH`; fixed-clock builtin | `m` -> `y` (fixed-clock `y`) |
| parent `USB3_GDSC-supply`, SS PHY `usb3_dp_phy_gdsc-supply`, GCC CX/MX, HS/SS/repeater LDOs | `gdsc-regulator.c` `QCOM_GDSC_REGULATOR`, `rpmh-regulator.c` `REGULATOR_RPMH`, `QCOM_RPMH`, `QCOM_COMMAND_DB` | `m` -> `y` each |
| parent three `interconnects` through aggre1/mc_virt/cnoc_cfg/gem_noc and BCM voter | `drivers/interconnect/qcom/volcano.c` `INTERCONNECT_QCOM_VOLCANO`; `INTERCONNECT_QCOM_BCM_VOTER`, `INTERCONNECT_QCOM_RPMH`, `INTERCONNECT_QCOM_QOS`, `INTERCONNECT_QCOM_DEBUG` | `m` -> `y` each (helpers selected by Kconfig) |
| parent `extcon = <&eud>`; `usb-role-switch`, connector via PMIC GLINK/UCSI | `drivers/soc/qcom/eud.c` `QCOM_EUD`; `QTI_PMIC_GLINK`, `UCSI_QTI_GLINK` | `m` -> `y` each |
| child `iommus`, parent dummy SMMU probe-order phandle; SS PHY portselect pinctrl | `ARM_SMMU`, `ARM_SMMU_QCOM`, `QCOM_IOMMU_UTIL`, `QTI_IOMMU_SUPPORT`; `PINCTRL_VOLCANO`, `PINCTRL_MSM`, `QCOM_SCM`; `QCOM_PDC` for parent IRQs | `m` -> `y` each |

There is **no** direct `power-domains` property on either USB node. The
`dummy-supply` SMMU phandle is a probe-order edge, not a power rail. The
merged overlay adds the eUSB2 repeater phandle and its two regulator supplies.
The built-in closure also promotes link-only providers (RPMh, CRM, SOCINFO,
IPC logging, SMEM/GLINK, Gunyah RM/SHM, minidump/mem-buf, regulator debug and
proxy, regmap debug, hwspinlock and redriver). Without them `ld.lld-17`
reports undefined symbols including `crm_write_bw_vote`,
`devm_regulator_proxy_consumer_register` and `qcom_glink_spss_register`.
The additive fragment is the smallest link-complete `=y` closure found while
keeping the existing debug initramfs, role-switch path and vendor kernel
policy; the exact requested/selected symbol list is checked by
`scripts/verify-volcano-usb.py`. Promoting providers that are `=m` on #16
rather than staging 58+ modules avoids an unproven `modules.dep`/early insmod
sequence and preserves the two other chain images exactly.

| artifact | verified #16 (bytes; SHA-256) | #18 Path B (bytes; SHA-256) |
| --- | --- | --- |
| `.config` | 237,498; `8c00c6f8cd89a6b044a0c7df7c481248786b09e14b12964699ed3ee6da7905d9` | 237,546; `5781d141305c4f27bdc0dd3e69a1136a7e9be3c4fbc538d8b5c11e6f2442cd32` |
| `Image` | 39,971,328; `cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386` | 41,859,584; `a6e51840a47a9ef88bec6b027c8e808868567658f0e3f0d911205fe8c1048b29` |
| `Image.gz` | 15,096,553; `0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c` | 15,746,316; `9055503e67a1321468fa75608b677eec257c403345a7a6de6709369fb71d5d4a` |
| `boot.img` | 15,101,952; `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` | 15,753,216; `116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce` |
| `init_boot.img` | 1,679,360; `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360; **identical** `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352; `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352; **identical** `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| vendor `dtb.img` (20 entries) | 9,419,891; `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` | 9,419,891; **identical** `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| gzip cpio in both ramdisks | 1,672,600; `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` | 1,672,600; **identical** `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The boot header remains v4 with empty boot generic ramdisk, 1,584-byte
header in a 4,096-byte page, kernel at byte 4,096, kernel gzip length
15,746,316 and no bytes after the aligned kernel at byte 15,753,216.
Init_boot's empty kernel and generic ramdisk offset 4,096, vendor DTB offset
1,679,360, PLATFORM ramdisk, table and bootconfig offsets remain #16's.
The new boot SHA differs from all previously failed boots `5e866c54…`,
`84f7f5ea…`, and the untested #16 boot `1fdc2570…`. Two sequential
host-only packaging/verification runs produced the same SHA set. Verified
stock `parts-a.sha256` and `config.gz` were read only; the latter measures
`CONFIG_CMDLINE` but cannot establish vendor-module runtime loading.

**Checks:** `scripts/build-baseline.sh` (`Image dtbs`, `vmlinux` link passed),
`build-bootimg.sh` twice (deterministic SHA), `verify-bootimg.sh` twice
(DTBO-65 applied; 22 phandle suppliers; embedded config; 0 `.ko`), and
`compare-baseline.sh` passed. Synthetic fixture output includes
`expected module glue without .ko failure: CONFIG_USB_DWC3_MSM=m has no verified built-in driver; initramfs modules/load path not verified (0 .ko)`
and `expected unpacked zero-.ko initramfs failure: CONFIG_USB_DWC3_MSM=m has no built-in driver and initramfs has 0 .ko files`;
existing duplicate-ramdisk fixture still emits `boot generic ramdisk must be empty`.
Host structural checks do **not** prove that the USB controller binds, that
`/sys/class/udc/a600000.dwc3` appears, or that gadget/SSH is reachable.

**Evidence vs hypothesis:** The old chain could not load the `=m` glue and
PHY/power/clock closure from its zero-`.ko` initramfs. This new chain makes
those objects link-reachable in the unpacked `Image`. Actual probe ordering,
Type-C role, UDC enumeration (`18d1:4ee2`) and key-only Dropbear SSH remain
hypotheses pending separately authorized measurement. The previously observed
five-second return to fastboot predates the `/init` 10-second UDC wait and is
**not** explained by the missing driver closure; no bootloader rejection or
kernel entry has been established. Issue #12 remains blocked on an
attempt-specific discriminator. This work is independent of encrypted
userdata and release-image packaging.

**Physical test gate (not executed or requested by this worker):** Only the
physical-test coordinator may separately review the existing
`humanApprovals.bounded_full_chain_test_slot_a` scope for a bounded slot-A
three-image chain using these exact checked hashes, verified stock rollback
and an attempt-specific, supported read-only kernel-entry measurement path.
No approval here covers `dtbo`, `vbmeta`, `userdata`, slot B or permanent
flashing. Without a supported attempt-specific read-only discriminator, the
boot boundary remains unresolved. No device operation was performed for #18.

## Single generic ramdisk in init_boot (#16, 2026-10-20)

**Observed:** The #14 three-image set, with `boot.img` SHA-256
`84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a`,
returned to fastboot within five seconds after the physical coordinator's
bounded slot-A attempt. Stock rollback was verified; recovery pstore contains
only stock/recovery 6.1.84 banners and no attempted-kernel 6.1.78 marker.
Recovery can overwrite pstore. Neither bootloader rejection nor kernel entry
has been measured; USB gadget enumeration and key-only SSH are unproven.

The read-only A059P `parts-a.sha256` and `config.gz` references under
`~/phone-second-life-data/mb003/` were hash-checked before parsing. The stock
boot header v4 has an **empty** generic ramdisk; stock init_boot has a nonzero
one. The failed #14 build duplicated the same 1,672,600-byte gzip cpio in
both images. The local `/usr/bin/mkbootimg` header-v4 implementation writes
`ramdisk_size=0` and no payload when `--ramdisk` is omitted. The first
`mkbootimg` call in `scripts/build-bootimg.sh` now omits that flag; the
`init_boot` call retains it and `vendor_boot` retains the same PLATFORM vendor
ramdisk, DTBs and bootconfig. This is an additive, revertible boot packaging
change: `build-baseline.sh` still merges vendor `consolidate.fragment` and
`pineapple_consolidate.config`, then the measured stock cmdline fragment last.
No kernel source/config, dtbo, vbmeta, or release-image builder was changed.

| header-v4 image | stock A (bytes / generic ramdisk / SHA-256) | failed #14 (bytes / generic ramdisk / SHA-256) | new host build (bytes / generic ramdisk / SHA-256) |
| --- | --- | --- | --- |
| boot | 100,663,296 / 0 / `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` | 16,777,216 / 1,672,600 / `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` | 15,101,952 / 0 / `1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7` |
| init_boot | 8,388,608 / 2,113,581 / `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` | 1,679,360 / 1,672,600 / `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` | 1,679,360 / 1,672,600 / `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| vendor_boot (PLATFORM ramdisk) | 100,663,296 / 8,821,389 / `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` | 11,108,352 / 1,672,600 / `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` | 11,108,352 / 1,672,600 / `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |

Boot and init_boot headers are 1,584 bytes in 4,096-byte pages; both boot
kernels start at offset 4,096. Stock boot kernel is 13,949,926 bytes; #14/new
kernel is the unchanged 15,096,553-byte `Image.gz` with SHA-256
`0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c`.
In #14, boot's ramdisk started at 15,101,952; in the new boot that offset is
the end of the image. Init_boot has an empty kernel and retains the exact
1,672,600-byte gzip newc at offset 4,096 (SHA-256
`caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f`).
The vendor DTB still begins at 1,679,360, retains all 20 stock DTBs (index 9
matches stock DTBO entry 65), and both builds retain the 175-byte stock
bootconfig. Stock vendor DTB begins at 8,826,880. The new boot hash also
differs from the earlier failed #10 hash
`5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`.

The verifier reconstructs the *entire* failed #14 boot byte-for-byte by
restoring only boot's ramdisk size field and aligned generic-ramdisk payload;
its SHA-256 matches `84f7f5ea…` exactly. It pins the input `.config`, `Image`,
`Image.gz`, gzip cpio, DTB and both other image hashes to the #14 measurements,
and checks commandlines, embedded IKCONFIG, stock AVB hash relationships,
header geometry, DTBO-65 application and key-only SSH ramdisk content. Small
synthetic fixtures verify that duplicating a gzip newc cpio into boot is
rejected, as are advertised or unadvertised boot ramdisk payloads, a nonempty
init_boot kernel and a changed init_boot cpio. Expected negative output is
`expected verified #14 duplicated ramdisk failure: boot generic ramdisk must be empty`
for the reconstructed #14 image and
`expected duplicated small gzip cpio failure: boot generic ramdisk must be empty`
for the synthetic image. Checking the original failed #14 artifact alone
returns `FAIL: boot generic ramdisk must be empty`; no negative fixture is
silently accepted. Two
sequential host packaging runs yielded the same three image hashes; full
verification, `bash -n`, `shellcheck` and `git diff --check` passed. Artifacts
and reports remain only under `~/sm7635-build/out/`.

**Hypothesis, not observation:** Removing the non-stock boot ramdisk may avoid
an early loader misinterpretation. Structural equivalence establishes only
that the new chain isolates this one variable; it cannot locate the failure
boundary or prove a physical fix. Stock vbmeta's hashes still do not
validate the unsigned test images. No device operation is part of this work.
Any future attempt-specific hand-off measurement and bounded slot-A gate
review belong solely to the physical coordinator; no blind retest is requested.

## Stock built-in command line discriminator (#14, 2026-10-20)

Both failed full-chain sets returned to fastboot within five seconds; the
later recovery pstore does not establish whether the test kernel entered.
The #8 and #10 `boot.img` hashes were identical, so they both contained the
same kernel with the `consolidate.fragment` built-in command line, including
`panic_on_taint=0x20`, `page_owner=on`, `page_pinner=on`, `slub_debug=`,
`no_hash_pointers` and `stack_depot_disable=off`. With
`CONFIG_CMDLINE_EXTEND=y`, this could alter early-boot behavior despite the
bootloader's `stack_depot_disable=on`; an early panic remains a hypothesis,
not an observed cause or proof of bootloader acceptance.

The read-only A059P `~/phone-second-life-data/mb003/config.gz` (44,361 bytes,
SHA-256 `90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`)
measures `CONFIG_CMDLINE="console=ttynull stack_depot_disable=on
cgroup_disable=pressure kasan.page_alloc.sample=10 kasan.stacktrace=off
kvm-arm.mode=protected bootconfig ioremap_guard"` and
`CONFIG_CMDLINE_EXTEND=y`. The new `configs/asteroids-stock-cmdline.fragment`
repeats only that measured `CONFIG_CMDLINE`, merged last after the pinned
`gki_defconfig`, `pineapple_GKI.config`, unchanged `consolidate.fragment` and
`pineapple_consolidate.config`. The merge log records the override, so removing
this final fragment restores the original vendor policy. The boot and vendor
image header command lines remain the #10 diagnostic values; only the
kernel's built-in command line changes. The old `panic_on_taint` mask can no
longer be prepended by `CONFIG_CMDLINE_EXTEND`.

A single host-only run of `scripts/build-baseline.sh`, `scripts/build-bootimg.sh`,
`scripts/verify-bootimg.sh` and `scripts/compare-baseline.sh` passed. The
verifier matches the fragment, merged config, built `.config` and IKCONFIG
extracted from the unpacked kernel against the measured stock command line;
it checks the absence of `panic_on_taint` and the removed debug flags from all
three boot-chain image command lines as well. Line-by-line config comparison:
5,996 stock and 6,978 built symbol lines, 5,925 identical, 71 stock-only or
changed and 1,053 built-only or changed; `CONFIG_CMDLINE` is now identical,
not the entire 6.1.78/6.1.84 configuration. `shellcheck`, `bash -n` and
`git diff --check` passed. Host artifacts and comparison logs remain only in
`~/sm7635-build/out/`.

| host artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `.config` | 237,498 | `8c00c6f8cd89a6b044a0c7df7c481248786b09e14b12964699ed3ee6da7905d9` |
| `Image` | 39,971,328 | `cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386` |
| `Image.gz` | 15,096,553 | `0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c` |
| `boot.img` | 16,777,216 | `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` |
| `init_boot.img` | 1,679,360 | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352 | `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| `dtb.img` | 9,419,891 | `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| `initramfs.cpio.gz` | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The new `boot.img` kernel gzip payload is 15,096,553 bytes at offset 4,096.
Its hash differs from both failed sets' `boot.img`
`5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`;
its `Image.gz` differs from the earlier baseline
`159a970903ffbf2012d706099f67703ad6c5d7e31f83441deff363e80eaacc8f`.
The intentionally unchanged `init_boot.img` and `vendor_boot.img` retain the
#10 hashes (and the debug ramdisk, all 20 stock DTBs, vendor command line,
stock DTBO-65 compatibility and bootconfig). This is a distinct **chain**,
not a claim that every component differs: changing those components would
introduce a second variable. The #8 `vendor_boot.img` hash was
`bde3a3b3bc7ea587f195de63de76db5f14f8dfd197d6d3224904f722af18fd31`;
no failed three-image set is repeated. These host-only checks do not prove
physical boot or resolve the AVB/early-kernel boundary. No worker device
operation or new physical test is part of #14; the separately gated physical
coordinator alone decides whether to test a new chain.

## Corrected-chain return to fastboot (#12, 2026-10-20)

**Observed:** The physical coordinator's 06:40 attempt used the #10 chain:
`boot` SHA-256 `5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`,
`init_boot` `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89`,
`vendor_boot` `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d`.
All three slot-A writes returned OKAY; the phone returned to fastboot within
five seconds and stayed there through 45 observations over roughly four
minutes, without gadget, adb or SSH. The unchanged stock `dtbo_a` and all
three restored stock slot-A images matched the verified on-device backup
hashes; stock Android subsequently completed boot on slot A. Host-only
records at `~/phone-second-life-data/mb003/pstore/attempt-20261020-0640/`
include a 1,197,548-byte recovery console (SHA-256
`56d976062bd7e1f6853f0ee2ab389f194964eab5dec224f2e5600abc0049b81e`)
with one stock/recovery 6.1.84 boot banner, zero 6.1.78 baseline banners and
zero dropbear markers. It was collected *after* fallback, verified stock
rollback and an explicit recovery boot, but before Android, so it does not
establish whether the attempted kernel entered.
Only `vendor_boot` differed between the failed #8 and #10 chains: the stock
DTB/DTBO incompatibility fixed in #10 was not the **sole** cause of the same
observed return to fastboot.

**Host-only comparison:** `scripts/verify-bootimg.sh` passed against SHA-pinned
slot-A stock `boot`, `init_boot`, `vendor_boot`, `dtbo` and `vbmeta` references
and the exact failed #10 images. Stock `vbmeta_a` has flags zero and rollback
index zero; it chains `boot` at rollback location 3 and has matching salted
hash descriptors for stock `init_boot`, `vendor_boot` and `dtbo`. Each stock
boot-family image fills its partition and has a footer-referenced embedded
vbmeta with a matching hash of its stock prefix. Stock `boot` also has a
**separate** 16 KiB AVB0 record between its kernel and footer-referenced
vbmeta; it hashes the shorter kernel-only prefix. The regression check now
checks that record's descriptor and hash separately, verifies the zero
verification flags of the stock records, and confirms the test `boot` has
no corresponding separate record. It does not verify signatures or
establish which records the bootloader enforced on the failed attempt. The
stock `vbmeta_a` hash for `dtbo` still matches: no `dtbo` or `vbmeta` change is
proposed.

| relationship | verified stock slot A | failed #10 chain |
| --- | --- | --- |
| boot image | 96 MiB; header v4, kernel at 4096; separate AVB0 at 13,955,072, embedded vbmeta at 13,971,456 | 16 MiB; v4, gzipped 6.1.78 kernel at 4096 and debug ramdisk at 15,101,952; no stock AVB0 record or footer; stock boot hash does not match |
| init_boot | 8 MiB; v4, generic Android LZ4 ramdisk at 4096, embedded vbmeta at 2,121,728 | 1,679,360 bytes; v4, empty kernel, debug gzip generic ramdisk at 4096; shorter than stock hashed prefix, no footer |
| vendor_boot | 96 MiB; v4, one PLATFORM LZ4 ramdisk, DTB at 8,826,880, table at 18,247,680, bootconfig at 18,251,776; embedded vbmeta at 18,255,872 | 11,108,352 bytes; v4, one PLATFORM gzip debug ramdisk, DTB at 1,679,360, table at 11,100,160, bootconfig at 11,104,256; shorter than stock hashed prefix, no footer |
| selection and parameters | stock property capture reports DTB index 9, DTBO entry 65; vendor page 4096, kernel/ramdisk/tags/DTB addresses `0x8000`/`0x1000000`/`0x100`/`0x1f00000` | same geometry; all 20 stock DTBs byte-identical, stock entry 65 applies to index 9 and supplies ramoops; bootconfig matches stock's 175 bytes |

The boot cmdline and vendor cmdline differ from stock (diagnostic earlycon,
`panic=-1`); stock `boot` has no generic ramdisk, while the test places the
debug ramdisk in `init_boot` as required by header v4. The stock 6.1.84
kernel/vendor modules and Android generic ramdisk cannot be assumed compatible
with the 6.1.78 baseline; the test instead replaces both ramdisks with the
same debug payload and never loads the stock vendor modules. Gzip versus LZ4,
smaller image geometry and AVB mismatches are candidate explanations, **not**
a bootloader verdict. A pre-attempt unlocked/orange report supersedes the
older locked/green stock property capture, but does not show what policy was
enforced at hand-off. The preserved pre/post `getvar` records identify slot A
and unlocked state; no attempt-specific AVB accept/reject status, boot reason,
A/B retry counter or supported read-only source for them is established by the
host records. Stock-kernel boot counters in pstore cannot be attributed to
this attempted hand-off. The OrangeFox pmsg boot-recovery reason follows an
explicit recovery request after stock rollback, and its slot-suffix use does
not identify which image the bootloader loaded during the failed attempt.
A successful fastboot write or reboot is not proof of bootloader image
acceptance.

**Single selected diagnostic:** the host-only AVB relationship audit in
`scripts/verify-bootimg.sh`, including the separate stock boot AVB0 record.
It confirms structural divergences, not the boundary at which the device
failed; no supported single-variable image correction follows. No new images
were built or designated for flashing. Do **not** repeat the #8 or #10 SHA
sets or try a multi-variable revision. The current host evidence cannot
distinguish rejection before kernel hand-off from a very early kernel failure
or a later init/USB failure.

**Conditional measurement/rollback handoff (physical coordinator only):**
There is no new test request or flash approval in this diagnosis. If distinct
images are ever independently justified and the existing bounded slot-A gate
is re-evaluated, the coordinator owns the complete test and verified stock
rollback. Before any such test, the coordinator must establish a supported
read-only evidence channel or explicitly accept that the boundary may remain
unknown; a new image SHA alone cannot discriminate it. An attempt-tagged
record should associate image SHAs and a timed first return to fastboot with
any *supported, bounded, read-only* bootloader
AVB decision, slot/retry and boot-reason observations **before** recovery,
stock boot or rollback can erase evidence; do not use a broad or hung probe.
If such a signal is unavailable, record it as unavailable rather than infer
a verdict. An explicit rejection supports failure before hand-off. An
explicit acceptance **without** a test-kernel marker remains inconclusive:
very early failure or lost/overwritten ramoops is still possible. A surviving
6.1.78 kernel marker establishes hand-off; last kernel progress before
`usb-init: starting` supports an early/pre-init failure, while `usb-init`
markers without gadget or SSH support a later init/USB failure. Preserve only
parsed marker counts, timing and structural facts in public reports, not raw
dumps. The coordinator alone decides whether and how to obtain a timely
record and restore/verify the three stock slot-A partitions. No operation on
slot B, `dtbo`, `vbmeta` or `userdata` is in scope. Without a supported
attempt-specific read-only signal or new evidence-backed artifact, stop.

## 2026-10-20 full-chain attempt and host-only diagnosis (#10)

The authorized physical team confirmed the stock slot-A backups before writing
all three #8 images; the writes returned OKAY, but the reboot returned to
fastboot within seconds without USB networking or SSH. Stock slot-A images were
restored and rechecked on-device; `dtbo_a` was not changed, and stock Android
booted fully afterward. The host-only attempt records are under
`~/phone-second-life-data/mb003/pstore/attempt-20261020-0134/`; do not publish
their contents. The preserved console has one 6.1.84 stock/recovery kernel
marker and zero 6.1.78 baseline markers. The `nt_kmsg` capture has 16 6.1.84
markers and zero 6.1.78 markers; these are not 16 distinct attempt boots.
OrangeFox recovery or subsequent stock boots can overwrite ramoops, so absence
of a 6.1.78 marker does not establish that the bootloader rejected the images.
An OrangeFox recovery header or recovery marker is not evidence of the attempted
kernel either. There is no captured attempt-specific bootloader AVB verdict,
boot reason or retry counter. The older stock property capture reports locked,
green and DTB/DTBO indices 9/65, but predates this attempt; it cannot establish
the verification state during it.

The verified stock `boot_a`, `init_boot_a` and `vendor_boot_a` images each fill
the partition and have an AVB footer and embedded vbmeta. The #8 images have
neither footer nor matching stock hash; `vbmeta_a` chains `boot`, hashes
`init_boot`, `vendor_boot` and the unchanged `dtbo`. On an unlocked device,
missing footers and hash mismatches alone do not prove the reason for the
fastboot return. Stock `boot_a` additionally contains a 16,384-byte AVB0
region between the aligned boot payload and the footer-referenced embedded
vbmeta; the #8 boot image lacks it. Do not treat the header's zero signature
size as proof that these records do not matter. No alternate AVB/vbmeta images
or partition writes are proposed here.

A read-only libfdt application of the actual stock `dtbo_a` entry 65 to the
#8 `vendor_boot.img` base DTB index 9 fails `FDT_ERR_NOTFOUND`: 32 fixup
symbols referenced at 82 sites are absent from that built DTB. The same stock
overlay applies to stock index 9. The separate generated QRD Pro overlay
applies to the built base, but that overlay was *not* in the flashed chain;
checking only its model and board ID was insufficient. This is a concrete
boot-chain incompatibility, not proof of the bootloader's exact failure point.

The host-only correction for #10 copies the SHA-256-pinned stock 20-entry DTB
blob into `vendor_boot` without modifying it. The stock overlay can then apply
to index 9, and the stock overlay supplies the ramoops reservation. The
baseline 6.1.78 kernel, debug ramdisks, vendor command line and bootconfig
remain unchanged. Only `vendor_boot.img` changes from #8. The verifier checks
all 20 DTBs byte-for-byte, applies stock DTBO 65, and checks the resulting
ramoops fields and the stock AVB hash relationship; it does *not* establish
bootloader acceptance. Images and reports stay under `~/sm7635-build/out/`.

This DTB-only candidate was tested as #10's corrected set and returned to
fastboot; it must not be repeated. The #12 assessment above supersedes this
candidate and preserves the unresolved boot boundary. Physical tests, record
capture and stock slot-A restoration remain exclusively the coordinator's
responsibility; slot B, dtbo, vbmeta and userdata remain outside scope.

## 2026-10-19 single-boot analysis

## Why the 19:00 boot produced no USB gadget

The attempt passed `boot.img`
`7cd886a24121c878a62839424b6b7f88840ba7504eb09cd0720eec96cb8ecfe5` to
`fastboot boot`. The bootloader answered `Booting OKAY` after 10.4s, no
`18d1:4ee2` gadget appeared, and the device returned to stock Android on
slot `_a` after about 35s. `Booting OKAY` only means the bootloader accepted
the image. It does not show that a kernel started.

`fastboot boot` supplies only the `boot` payload, not `init_boot` or
`vendor_boot`. For the observed stock header-v4 layout the generic ramdisk
comes from `init_boot`. The DTB blob, vendor command line and bootconfig
come from `vendor_boot`, and the board overlay comes from `dtbo`; those
partition images stayed stock. Stock-boot properties report
`ro.boot.dtb_idx=9` and `ro.boot.dtbo_idx=65`, but are not an
attempt-specific selection record.

Checked against the unpacked stock images:

| selection | source | contents |
| --- | --- | --- |
| DTB index 9 | `vendor_boot_a`, tenth of twenty concatenated DTBs | `Qualcomm Technologies, Inc. Volcano SoC`, `compatible = "qcom,volcano"`, `qcom,msm-id = <0x27c 0x10000>`, `qcom,board-id = <0 0>` |
| DTBO index 65 | `dtbo_a`, entry 65 of 76 | `Qualcomm Technologies, Inc. Volcano QRD Pro`, the live-FDT compatible list, `qcom,board-id = <0x0b 0>`, `qcom,oem-id = <2>` |

Any attempted hand-off would have used the stock DTB and stock DTBO
selection; the supplied `boot.img` carried neither a DTB nor a command line.
The later stock/recovery console starts its command line with `console=ttynull`
and ends with `rootwait ro init=/init`; its vendor part is
`video=vfb:640x400,bpp=32,memsize=3072000 nosoftlockup log_buf_len=1M
ignore_loglevel printk.devkmsg=on bootconfig`. This is consistent with the
stock vendor partition, not a captured attempted-kernel command line. It
has no `earlycon`, `keep_bootcon` or `panic=`; `chosen/stdout-path` names
the GENI debug UART, but nothing enables it in this stock cmdline.

The two stock ramdisks were unpacked and listed:

| image | ramdisk | contents |
| --- | --- | --- |
| `init_boot_a` | 2113581 bytes, lz4 legacy | the generic ramdisk: `/init` (2747936 bytes), `/system/bin`, `dev` nodes |
| `vendor_boot_a` | 8821389 bytes, lz4 legacy | `first_stage_ramdisk/fstab.qcom` and 324 files under `lib/modules/*.ko`; no `/init` |
| built `boot.img` | 1032027 bytes, gzip | `/init` (the debug shell), `/bin/busybox` |

Header v4 gets the generic ramdisk from `init_boot`; `fastboot boot` did
not replace stock `init_boot_a`. Had the 6.1.78 kernel reached init, it
would have received stock Android `/init` and 6.1.84 vendor modules rather
than the debug `/init` in the supplied `boot` ramdisk. Those stock modules
cannot be assumed compatible with the baseline kernel. The available
`Run /init as init process` and module-load messages belong to the
6.1.84 stock/recovery console described below, **not** an established
6.1.78 hand-off. The test kernel's entry and the reason the gadget never
enumerated are unresolved. Putting a ramdisk only in `boot.img` cannot
deliver it as the generic ramdisk in this header-v4 layout.

## What the pstore file does and does not show

`~/phone-second-life-data/mb003/pstore/console-ramoops-0` (834645 bytes,
sha256 `c9c49d9244c6531ffb06560ca9c26b24b30786fdd03bc2bce7e193e80b453fd2`)
was pulled from OrangeFox after the attempt. Its first line is `Linux
version 6.1.84-android14-11-gf4b0d69fdf34-ab12786779`, built
`Wed Dec 11 19:19:40 UTC 2024` with Android clang 17.0.2. The baseline
`Image` is 6.1.78 built with Ubuntu clang 17.0.6, so this file is a stock
boot's console, not the failed boot's. `pmsg-ramoops-0` (sha256
`36b2c0669098fa7b10b03e77f7c63a7b1a8cd46431bb220b8e3180dc5aa01bfb`) is the
matching pmsg record. Neither file is committed; both stay on the build
host.

It does establish the capture mechanics. The live FDT reserves ramoops at
`0x81f20000`, size `0x400000`, with `console-size = <0x200000>` and
`pmsg-size = <0x200000>`, and the stock kernel logs `ramoops: using
0x400000@0x81f20000`. The same reservation is what the built kernel needs,
and the 19:00 capture shows why timing matters: a later stock boot may
replace any attempt-specific console, if the attempt wrote one at all.

## Diagnosability of the baseline kernel

The baseline `.config` already has `CONFIG_PSTORE=y`,
`CONFIG_PSTORE_CONSOLE=y`, `CONFIG_PSTORE_PMSG=y`, `CONFIG_PSTORE_RAM=y`,
`CONFIG_SERIAL_EARLYCON=y` and `CONFIG_SERIAL_QCOM_GENI=y`. No kernel
rebuild is needed for console capture.

The reservation is the gap. `ramoops_region` in `volcano.dtsi` carries
`size = <0x0 0x200000>` and `pmsg-size = <0x200000>` but no `reg`, so no
fixed address, and no `console-size`. The stock values come from
`volcano-arca-common-overlay.dtsi`, which `volcano-qrd-pro-overlay`
includes, and that overlay is applied from `dtbo` rather than from the DTB.
The #5/#8 build tried to add
`reg = <0x0 0x81f20000 0x0 0x400000>` and `console-size = <0x200000>`
to every built DTB, but the unchanged stock `dtbo_a` could not apply to
built index 9. The #10 build instead retains the verified stock DTB blob;
`scripts/verify-bootimg.sh` checks the ramoops reservation after applying
stock overlay 65. That reservation still cannot prove that the attempted
kernel executed or that a later stock boot did not overwrite its console.

`earlycon` needs no address. The stock index-9 DTB has `chosen/stdout-path =
"/soc/qcom,qupv3_0_geni_se@ac0000/qcom,qup_uart@a94000:115200n8"` and the
driver registers `OF_EARLYCON_DECLARE(qcom_geni, "qcom,geni-debug-uart", ...)`,
so a bare `earlycon` follows the stdout path. No UART test points or
voltages were identified, so a USB-TTL adapter is not part of this setup.
`panic=-1` makes `panic()` sit and wait instead of rebooting, which keeps
the ramoops console intact until recovery reads it.

## The corrected images

`scripts/build-bootimg.sh` writes three images to `$WORK/out`. The current
chain carries the generic debug ramdisk only in `init_boot`; `vendor_boot`
still carries the same debug payload as its distinct PLATFORM vendor ramdisk.

| image | contents |
| --- | --- |
| `boot.img` | header v4, gzipped baseline `Image`, empty generic ramdisk, command line beginning `console=ttynull` and carrying the stock bootconfig tokens |
| `init_boot.img` | header v4, empty kernel, debug generic ramdisk, empty command line, matching the stock `init_boot` layout |
| `vendor_boot.img` | header v4 at the stock offsets, the debug ramdisk as its single PLATFORM vendor ramdisk, the DTB blob, vendor command line `earlycon keep_bootcon loglevel=8 log_buf_len=1M ignore_loglevel printk.devkmsg=on panic=-1 bootconfig` |

At the time of the failed attempt the first nine DTBs were copied verbatim
from stock, while index 9 and the following ten Volcano DTBs were replaced by
the pinned 6.1.78 source build. The unchanged stock `dtbo_a` entry 65 cannot
apply to that index 9; see #10 diagnosis above. The current host-only build
instead retains all twenty stock DTBs, including index 9, so the unchanged
stock overlay can supply the ramoops reservation. No `dtbo.img` is produced.

Replacing the vendor ramdisk drops `first_stage_ramdisk/fstab.qcom` and the
324 stock modules from the chain. The debug init never mounts a block
device or loads a module, so it does not need them, and dropping them is
what stops stock init from loading 6.1.84 modules into a 6.1.78 kernel.

## Full-chain caveat

The standing flash gate does **not** authorize any partition writes. This
issue does not authorize any physical execution. The three-image chain below
is superseded historical context, not a procedure to run as part of this issue.

The host `fastboot` is 34.0.5 and its `boot` command downloads a single
image, so it cannot replace `init_boot` and `vendor_boot`. The bounded test
team wrote and restored all three slot-A images; `boot` and `vendor_boot`
partitions are 96MiB each and `init_boot` is 8MiB.

The verified backups are `~/phone-second-life-data/mb003/parts/`, both
slots, recorded in `parts.sha256`. Slot `_a` and slot `_b` are byte
identical for these four partitions:

| backup | sha256 |
| --- | --- |
| `boot_a.img`, `boot_b.img` | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` |
| `init_boot_a.img`, `init_boot_b.img` | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` |
| `vendor_boot_a.img`, `vendor_boot_b.img` | `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` |
| `dtbo_a.img`, `dtbo_b.img` | `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992` |

Only slot `_a` was written during the historical attempt. Slot `_b` remained
untouched and `dtbo` was not written.

The expected USB evidence is the configfs gadget enumerating as
`18d1:4ee2`, with NCM on `usb0` at `172.16.42.2/24` and ECM on `usb1` at
`172.16.43.2/24`. The serial string is the literal `sm7635`. The debug
ramdisk now includes a key-only dropbear sshd listening at `172.16.42.2:22`;
the expected result is both the gadget and an SSH login over NCM. No SSH
observation has been made on the physical device as part of this issue.

The server allows root with the single ed25519 public key from the build
host's `~/.ssh/id_ed25519.pub` (or `$PUBKEY`) packed as
`/root/.ssh/authorized_keys`. Password and PAM authentication are compiled
out; no password or lockscreen exists in the initramfs. Its host key is
generated into RAM on first connection, so it changes on every boot. No
private key is shipped in the ramdisk or committed. The console shell
remains a fallback debug path if the gadget or SSH does not work.

The earlier test plan proposed prompt preservation of ramoops before a later
stock boot could overwrite it; the 2026-10-20 capture instead contains only
stock/recovery 6.1.84 markers. `nt_kmsg` is another host-only source of
kernel evidence, not a guaranteed record of the attempted boot. Any future
physical observation and restoration require the coordinator's separate
bounded authorization. Slot B, dtbo, vbmeta and userdata are not part of
this issue.
