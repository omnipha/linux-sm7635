---
date: 2026-11-04
run: 112
issue: linux-sm7635#311
subsystem: wlan
result: inconclusive
---
# setup rescue measured; flash gate refused

The previously installed Linux chain was booted for diagnosis and setup
without a partition flash. Both boots reached pinned key-only SSH and
measured capture/handoff; both sessions were closed. On setup boot
`ecb96a00...`, direct same-boot SHA-256 reads matched all four stock slot-A
rescue partitions and both installed Linux carriers (`2ebdf1db...`,
`a71b3f5f...`). The three stock host backup manifests passed; the device
returned to a responsive targeted fastboot identity gate.

The altered persistent radio `d7b74c24...`, the legacy local startup hook
and the old post script were backed up privately, then removed from the
persistent root; their absence was checked. The reviewed replacements have
not yet been installed. Neither the altered radio nor a host guard ACK was
executed in this run. The unchanged candidate pair was independently
verified under its producer lock, but never flashed or booted.

The flash wrapper refused twice before its preflight hook, with
`successful boot does not name its changed image`: the newest successful
repeat boot recorded no partition writes. No flash command was sent.
[agents#121](https://github.com/omnipha/agents/issues/121) tracks the P0
gate repair. The pair notification remains received but unmeasured.

Before diagnosis, fastboot pstore fetch was unsupported; owner-authorized
WLAN-specific possible evidence loss applies. Later pstore reads were saved
without attributing them to the prior boot. No Android boot, userdata erase
or stock restore occurred. Linux remains installed; autonomous WLAN remains
unmeasured. Raw captures, file backups and hashes stay outside Git.
