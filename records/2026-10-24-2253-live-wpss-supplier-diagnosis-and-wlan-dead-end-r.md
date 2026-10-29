---
date: 2026-10-24
run: 29
issue: omnipha/linux-sm7635#73
subsystem: wlan
result: inconclusive
source: BOOT.md
---
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
