---
date: 2026-10-25
issue: omnipha/linux-sm7635#81
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
