---
date: 2026-10-25
run: 37
issue: omnipha/linux-sm7635#101
subsystem: wlan
result: inconclusive
source: BOOT.md
---
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
