---
date: 2026-10-24
issue: omnipha/linux-sm7635#63
subsystem: boot
result: inconclusive
source: BOOT.md
---
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
