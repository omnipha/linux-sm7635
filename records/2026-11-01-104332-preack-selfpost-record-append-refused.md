---
date: 2026-11-01
issue: omnipha/linux-sm7635#253
subsystem: wlan
result: inconclusive
---
# Pre-ack pmos-self-post refuses before any radio stage (boot e64091d8, run 90)

Issue #253 outcome (b), worker-measured on the installed never-reflash run-87
pair (`init_boot_a f9449ba5` / `vendor_boot_b a71b3f5f`), boot
`e64091d8-f19b-4e36-a041-7a510c2ff13a`, host attempt dir
`~/phone-second-life-data/mb003/pstore/attempt-20261101-1140-preack-radio-run90/`
(host-only, not in git). No flash, no partition write, no pid1-ack.

Verified before invoking the pinned chain: key-only SSH on staged root `:2222`
(pinned host key fingerprint unchanged), capture connected to the same boot id,
`/run/keep` `0:600:1`, guard `armed` = boot id with no `accepted`/`ack`,
OpenRC softlevel `default`, `local` started, PID 1 `/sbin/init` (postmarketOS)
whose `/proc/1/exe` hash equals `/bin/busybox`, root on persistent
`/dev/block/sda13` (ext4, `rw,relatime,norecovery`). The staged
`/run/radio-bringup/pmos-self-post.sh` (sha256
`5e118ffc…3db5bd81f`) pins its own radio script (sha256 `f54b3372…765764f`,
self-consistent on device), and all of the script's own pre-record identity
gates passed.

Measured refusal, twice, unchanged invocation `sh /run/radio-bringup/pmos-self-post.sh`:

1. `pmos-self-post: FAIL: post-cutover boot record contract unavailable` —
   the script's default contract path `/run/pmos-root-contract.sh` does not
   exist on this persistent root (only `/run/pid1-guard/root-contract.sh`,
   sha256 equal to repo `scripts/pmos-root-contract.sh`, is staged).
2. With the documented env override
   `PMOS_ROOT_CONTRACT=/run/pid1-guard/root-contract.sh`: `FAIL: post-cutover
   boot record append refused`. `sh -x` tracing shows `boot_record_append`
   walking `/sys/class/block/*` partition names and failing inside
   `root_contract_switched_root` after `sda13` PARTNAME=`userdata` matches;
   the appended `pmos-self-post: post-cutover PID 1…` line never lands (the
   boot record still ends at the `usb-init: pid1 transition guard armed` line).

No radio stage ran: no `modem`, `wpss`, `driver`, `scan` or `services` marker
was created and `wlan0` never appeared; the failure precedes the `for stage in
modem wpss driver scan` loop. This is the first named pinned-script refusal, so
per the issue no manual workaround or second radio attempt was made. The
run-89 stage "independent recovery guard is not armed and unacknowledged" FAIL
in `self-post.log` was the auto-invocation at 156.5 s before the worker window.

At 10:42:58Z (uptime ~285 s) the unacknowledged guard returned the phone to
fastboot (`18d1:d00d`) after the result was recorded; capture `kmsg.log`
(170690 B) shows the designed shutdown sequence, no kernel fatal. No pid1-ack
was ever issued on this boot.

Interpretation: the ordering hypothesis (radio works if the chain runs before
the ack) remains untested by the radio itself. The measured boundary moved one
stage earlier than run 69's experience: on this boot the chain cannot even
reach the radio because the post-cutover boot-record append refuses inside the
persistent-root identity check. Next single variable for a successor
in-session question: why `boot_record_append` refuses on a root whose
`PARTNAME=userdata` matches — or stage the contract at the script's default
path — before re-attempting the pre-ack radio chain.

Post-ack WLAN checks: not applicable (no pid1-ack on this boot; the session
self-returned to fastboot after the recorded result).
