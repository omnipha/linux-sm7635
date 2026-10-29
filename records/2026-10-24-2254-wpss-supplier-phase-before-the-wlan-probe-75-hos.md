---
date: 2026-10-24
issue: omnipha/linux-sm7635#75
subsystem: wlan
result: inconclusive
source: BOOT.md
---
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
