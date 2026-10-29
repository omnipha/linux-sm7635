---
date: 2026-10-20
issue: omnipha/linux-sm7635#14
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Stock built-in command line discriminator (#14, 2026-10-20)

Both failed full-chain sets returned to fastboot within five seconds; the
later recovery pstore does not establish whether the test kernel entered.
The #8 and #10 `boot.img` hashes were identical, so they both contained the
same kernel with the `consolidate.fragment` built-in command line, including
`panic_on_taint=0x20`, `page_owner=on`, `page_pinner=on`, `slub_debug=`,
`no_hash_pointers` and `stack_depot_disable=off`. With
`CONFIG_CMDLINE_EXTEND=y`, this could alter early-boot behavior despite the
bootloader's `stack_depot_disable=on`; an early panic remains a hypothesis,
not an observed cause or proof of bootloader acceptance.

The read-only A059P `~/phone-second-life-data/mb003/config.gz` (44,361 bytes,
SHA-256 `90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478`)
measures `CONFIG_CMDLINE="console=ttynull stack_depot_disable=on
cgroup_disable=pressure kasan.page_alloc.sample=10 kasan.stacktrace=off
kvm-arm.mode=protected bootconfig ioremap_guard"` and
`CONFIG_CMDLINE_EXTEND=y`. The new `configs/asteroids-stock-cmdline.fragment`
repeats only that measured `CONFIG_CMDLINE`, merged last after the pinned
`gki_defconfig`, `pineapple_GKI.config`, unchanged `consolidate.fragment` and
`pineapple_consolidate.config`. The merge log records the override, so removing
this final fragment restores the original vendor policy. The boot and vendor
image header command lines remain the #10 diagnostic values; only the
kernel's built-in command line changes. The old `panic_on_taint` mask can no
longer be prepended by `CONFIG_CMDLINE_EXTEND`.

A single host-only run of `scripts/build-baseline.sh`, `scripts/build-bootimg.sh`,
`scripts/verify-bootimg.sh` and `scripts/compare-baseline.sh` passed. The
verifier matches the fragment, merged config, built `.config` and IKCONFIG
extracted from the unpacked kernel against the measured stock command line;
it checks the absence of `panic_on_taint` and the removed debug flags from all
three boot-chain image command lines as well. Line-by-line config comparison:
5,996 stock and 6,978 built symbol lines, 5,925 identical, 71 stock-only or
changed and 1,053 built-only or changed; `CONFIG_CMDLINE` is now identical,
not the entire 6.1.78/6.1.84 configuration. `shellcheck`, `bash -n` and
`git diff --check` passed. Host artifacts and comparison logs remain only in
`~/sm7635-build/out/`.

| host artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `.config` | 237,498 | `8c00c6f8cd89a6b044a0c7df7c481248786b09e14b12964699ed3ee6da7905d9` |
| `Image` | 39,971,328 | `cc9ec0d6f2903d6964ba0091c186a32cfbbccc42191a8675764b5c607c329386` |
| `Image.gz` | 15,096,553 | `0cef9dbfb53d6c2df6532946158180684f3d5de59136c64703dff7460eb0849c` |
| `boot.img` | 16,777,216 | `84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a` |
| `init_boot.img` | 1,679,360 | `f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89` |
| `vendor_boot.img` | 11,108,352 | `6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d` |
| `dtb.img` | 9,419,891 | `e04c86261f328dddb7d0ef72483e575809bfe63c5c8feab73271e0e5743c87a9` |
| `initramfs.cpio.gz` | 1,672,600 | `caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f` |

The new `boot.img` kernel gzip payload is 15,096,553 bytes at offset 4,096.
Its hash differs from both failed sets' `boot.img`
`5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb`;
its `Image.gz` differs from the earlier baseline
`159a970903ffbf2012d706099f67703ad6c5d7e31f83441deff363e80eaacc8f`.
The intentionally unchanged `init_boot.img` and `vendor_boot.img` retain the
#10 hashes (and the debug ramdisk, all 20 stock DTBs, vendor command line,
stock DTBO-65 compatibility and bootconfig). This is a distinct **chain**,
not a claim that every component differs: changing those components would
introduce a second variable. The #8 `vendor_boot.img` hash was
`bde3a3b3bc7ea587f195de63de76db5f14f8dfd197d6d3224904f722af18fd31`;
no failed three-image set is repeated. These host-only checks do not prove
physical boot or resolve the AVB/early-kernel boundary. No worker device
operation or new physical test is part of #14; the separately gated physical
coordinator alone decides whether to test a new chain.
