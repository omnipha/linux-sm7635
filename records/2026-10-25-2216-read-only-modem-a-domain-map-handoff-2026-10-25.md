---
date: 2026-10-25
issue: omnipha/linux-sm7635#88
subsystem: modem
result: inconclusive
source: README.md
---
## Read-only `modem_a` domain-map handoff (2026-10-25, #88, #92)

`docs/modem-a-acquisition-and-extraction.md` records the physical coordinator's
single read-only `modem_a` acquisition for #89 and the fail-closed host
extractor. The acquisition ran once: 367,001,600 bytes, SHA-256
`08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`, quarantined
outside Git, device unchanged. #92 corrected the #88 tooling against that dump
(4096-byte FAT16 sectors, the LFN short-name checksum mask bug, the stock
`sr_version` object form) and extracted six validated `.jsn` under `image/`.
`scripts/extract-modem-domain-maps.py` reads only a supplied FAT image, lists
and hashes every `.jsn`, validates the evidenced pd-mapper schema, and derives
a JSON config only from validated data. `scripts/test-modem-domain-map-extraction.sh`
exercises it with synthetic non-stock, non-flashable fixtures, including a
4096-byte-sector FAT16 fixture and the LFN case that aborted the stock run.
The independent `msm_sharedmem.ko`/rmtfs evidence from #85 stays separate from
the #86 pd-mapper/tftp variable.

The first `fastboot boot` of the earlier single `boot.img` returned
`Booting OKAY` but never enumerated the gadget. A header-v4 boot takes its
generic ramdisk from `init_boot` and its DTB and vendor command line from
`vendor_boot`, neither of which that attempt replaced. Its later stock
pstore does not establish whether the attempted kernel entered. [BOOT.md](BOOT.md)
records the evidence and the historical procedure. All four three-image attempts returned to fastboot, including #18's
recovery-path attempt before stock rollback; the physical coordinator alone
may authorize any future bounded test of a new evidence-backed set. Nothing in this
repository flashes or boots the phone.
