---
date: 2026-10-24
issue: omnipha/linux-sm7635#77
subsystem: wlan
result: inconclusive
source: BOOT.md
---
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
