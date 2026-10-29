---
date: 2026-10-25
run: 39
issue: omnipha/linux-sm7635#109
subsystem: wlan
result: inconclusive
source: BOOT.md
---
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
- **Userspace hold (the single tested variable):** run 38 registered the
  `wlan_hdd_state` device (`kmsg:2401`), but did not check whether the
  `/dev/wlan` character file existed (see #122 vetting above). An `ON` write
  through that node is a recognized value (`main.c:18958-18981,19121-19134`),
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
