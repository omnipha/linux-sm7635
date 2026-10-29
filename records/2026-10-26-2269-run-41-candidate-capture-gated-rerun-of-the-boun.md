---
date: 2026-10-26
run: 41
issue: omnipha/linux-sm7635#116
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Run 41 candidate: capture-gated rerun of the bounded HDD psoc-idle ON hold (#116, host-only, 2026-10-26)

**Superseded and never-reflash.** This candidate was never flashed, and #120
showed its `-R` generated host key cannot be pinned before the reboot that the
#113/#116 handoff requires. Use the run-42 image
`8b62520fe6288361fd15faa573587a0d1be1e0788f780c62440677a60b739801` above
instead; do not flash `7c3d915f3c8554d8a551b33f1b1caf162d410c0f629fae75425f29112c2fedf0`.

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

**Historical #116 handoff, superseded by #120: do not execute.** The SHA in this
section is unflashed and never-reflash; use the pinned host-key handoff for run
42 above. This historical text records what failed at the preboot gate:

1. Use a new attempt directory outside Git and a previously verified, pinned SSH
   host key. Before any `fastboot reboot`, start
   `omnipha/agents/scripts/session-capture.py start` for that directory with
   `--target root@172.16.42.2` and `--known-hosts-file` pointing at the verified
   file; configure the NCM host address `172.16.42.1/24`, mark both gadget links
   unmanaged, and verify the link and the route to `172.16.42.2`. Abort if any
   preboot check fails. `session-capture.py check` is not the preboot gate.
 2. (Do not execute.) Flash
   `7c3d915f3c8554d8a551b33f1b1caf162d410c0f629fae75425f29112c2fedf0` to
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
