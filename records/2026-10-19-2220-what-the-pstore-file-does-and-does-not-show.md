---
date: 2026-10-19
issue: omnipha/ports#3
subsystem: boot
result: inconclusive
source: BOOT.md
---
## What the pstore file does and does not show

`~/phone-second-life-data/mb003/pstore/console-ramoops-0` (834645 bytes,
sha256 `c9c49d9244c6531ffb06560ca9c26b24b30786fdd03bc2bce7e193e80b453fd2`)
was pulled from OrangeFox after the attempt. Its first line is `Linux
version 6.1.84-android14-11-gf4b0d69fdf34-ab12786779`, built
`Wed Dec 11 19:19:40 UTC 2024` with Android clang 17.0.2. The baseline
`Image` is 6.1.78 built with Ubuntu clang 17.0.6, so this file is a stock
boot's console, not the failed boot's. `pmsg-ramoops-0` (sha256
`36b2c0669098fa7b10b03e77f7c63a7b1a8cd46431bb220b8e3180dc5aa01bfb`) is the
matching pmsg record. Neither file is committed; both stay on the build
host.

It does establish the capture mechanics. The live FDT reserves ramoops at
`0x81f20000`, size `0x400000`, with `console-size = <0x200000>` and
`pmsg-size = <0x200000>`, and the stock kernel logs `ramoops: using
0x400000@0x81f20000`. The same reservation is what the built kernel needs,
and the 19:00 capture shows why timing matters: a later stock boot may
replace any attempt-specific console, if the attempt wrote one at all.
