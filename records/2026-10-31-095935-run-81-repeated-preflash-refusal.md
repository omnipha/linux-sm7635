---
date: 2026-10-31
run: 81
issue: omnipha/agents#77
subsystem: boot
result: refuted
---
# Run 81: repeated pre-flash refusal of the stale artifact pair, no write

The pending artifact receipt `init_boot-coldstart-hostfree.img` SHA-256 `becd37846fedd0d4298cf562667fd498f76a5c99e2e68810ca5cacf8c1ee72b4` plus `vendor_boot_b-coldstart-hostfree.img` `adb47dc0228cdbb1ba57dd245ecec49386d53bf24c3ab8f72493e709b78aeae8` was re-checked against merged main `ae59971` (post #230 close, PR #232) and refused again: `candidate repeats a stock, measured or refused image SHA-256`, exit 1. The pair is in the verifier REFUSED set from run 76 onward (PR #226, #228, #231); run 80 recorded the same refusal against `db8747c`. Nothing was flashed or booted. The artifact stays pending per its receipt rule; the repeat is expected until `omnipha/agents#77` makes a merged-main verifier refusal terminal.

The merged verifier still accepts the installed run-79 pair, re-proven after the refusal in the same run: `init_boot-coldstart-record.img` `a4ee7def41e645301f59bdc4dc043c97253a4002d8774016ee3557633b0cb6e3` plus `vendor_boot_b-coldstart-record.img` `6e7c5a2e26981fc19c9eba97356d1a52f80e768cb6b9536bc9cb4fd906a8c59e` passes the self-test with the same stock inputs, so the refusal discriminates the stale artifact, not the gate inputs.

Device side stayed read-only and responsive: host backup manifests `parts.sha256`, `parts-a.sha256`, `parts-b.sha256` all verified OK; fresh device-op USB scan and fastboot gate answered serial `00181152O003821`, slot a, unlocked. Installed carriers remain run 79 `init_boot_a a4ee7def`, `vendor_boot_b 6e7c5a2e`, last read exact by run 79's diagnostic boot; stock slot-A rescue `boot_a 197aff11`, `vendor_boot_a 23725940`, `dtbo_a 759813db`, `vbmeta_a cc1926d2` unchanged since that on-device read, no write since. No cold start, stock restore, userdata erase, Android boot, or open session. Evidence: `attempt-20261031-1041-preflash-refusal-run80` (run 80) plus this run's device-op events.
