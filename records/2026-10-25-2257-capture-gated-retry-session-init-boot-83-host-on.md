---
date: 2026-10-25
issue: omnipha/linux-sm7635#83
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
