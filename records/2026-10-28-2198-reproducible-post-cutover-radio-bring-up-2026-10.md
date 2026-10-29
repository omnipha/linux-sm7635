---
date: 2026-10-28
issue: omnipha/linux-sm7635#150
subsystem: modem
result: inconclusive
source: README.md
---
## Reproducible post-cutover radio bring-up (2026-10-28, #150)

[BOOT.md](BOOT.md#reproducible-post-cutover-radio-bring-up-150-host-only-2026-10-28)
records `scripts/pmos-radio-bringup.sh`, the hash-checked reproduction of the
run-53 radio order. Before `switch_root` it stages the read-only stock WLAN INI
(`57989aba…`), the measured one-shot WPSS helper (`fef7e5da…`) and the service
markers into the guest tmpfs. After cutover it runs one guarded modem start, one
WPSS trigger (copying `/dev/wlan` before cutover or deriving it fail-closed from
`/sys/class/wlan/wlan/dev` and the single character `qcwlanstate` major in
`/proc/devices`), one `qca_cld3` insmod with at most one reload, and one 20 s-bounded
scan, each gated on the current boot, `/run/keep` and a fresh capture marker.
`sh scripts/test-pmos-radio-bringup.sh` checks those pins, the fail-closed
`/dev/wlan` derivation and negative fixtures, and the one-shot guards in an
isolated tmpfs. No new image is built: the unchanged `fef03008…` image stays
the only reusable changed image. This is a host script, not a device result;
WPSS/wlan0 after the #155 rmtfs fix and association/reachability with the
regenerated profile remain unmeasured and await the coordinator-held session.
