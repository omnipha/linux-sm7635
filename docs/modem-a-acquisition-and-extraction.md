# SM7635 `modem_a` acquisition and stock domain-map extraction (#88, #92)

Status: **acquisition executed once, read-only, on #89; extraction delivered
on #92**. The single authorized physical read (2026-10-25, #89 comment
04:35Z) produced the complete hash-pinned dump this document now describes:
367,001,600 bytes, SHA-256
`08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`,
quarantined outside Git; the device returned to stock unchanged. §1 below
records both the original #88 procedure and the measured deviations #92
corrected; §2 describes the corrected, executed extraction. There will be
no second device read.

References:

- [#85](https://github.com/omnipha/linux-sm7635/issues/85) (PR
  [#87](https://github.com/omnipha/linux-sm7635/pull/87),
  `docs/modem-fw-init-dependency.md`, unmerged at the time of writing):
  domain-map source, stock modem-touching services, `msm_sharedmem.ko`/rmtfs
  by-name evidence.
- [#86](https://github.com/omnipha/linux-sm7635/issues/86): the
  pd-mapper/tqftpserv single-variable experiment; blocked on the real maps
  from #89. The extractor below is its config source of truth. No #86
  binaries or image work happens here.
- [#89](https://github.com/omnipha/linux-sm7635/issues/89): the
  physical-coordinator read-only dump step consuming §1 below — executed
  once; the dump it delivered is the sole input to §2.
- [#92](https://github.com/omnipha/linux-sm7635/issues/92): the host-only
  fix of the #88 tooling against the real dump (4096-byte-sector geometry,
  LFN checksum parser bug, stock `sr_version` object) and the validated
  stock `.jsn` inventory.

## 1. Read-only `modem_a` acquisition procedure (physical coordinator, #89)

Authorization gate (explicit, before anything else): the physical coordinator
personally confirms, in the #89 issue, that this single read-only acquisition
may proceed. Without that recorded authorization nothing below is executed.
No write, flash, reboot or remoteproc operation is part of this procedure.
The one execution of this procedure is complete; this section is kept as the
record of what was — and was not — verified on the device.

Measured identity anchors (from #85 / run artifacts, not re-measured here):

- by-name `modem` in the active slot-A boot resolves to `modem_a` →
  `/dev/block/sde6` (`by-name.txt:50`, `dev.mnt.blk.vendor.firmware_mnt=[sde6]`
  in `getprop.txt:154`).
- The stock fstab mounts it vfat, read-only, at `/vendor/firmware_mnt`
  (`vendor_a` image `etc/fstab.qcom:63`).
- It is **not** part of `super` (`super` is `/dev/block/sda6`); never read a
  `super` extent in place of the raw `modem_a` device.

### 1a. Original #88 assumptions vs the measured #89 recovery-channel reality

The #88 recipe assumed the stock-boot channel and the recovery channel are
equivalent. They are not, and every following #88 assumption it implied was
wrong:

- **Channel**: the acquisition ran from OrangeFox recovery root
  (`u:r:su:s0`), because stock ADB (uid 2000) cannot read
  `/dev/block/by-name/modem`, `/vendor/firmware_mnt` or the `sde6` sysfs
  nodes.
- **by-name path**: in recovery, `/dev/block/by-name/modem` is **absent**;
  the partition is reachable only as the raw block device `/dev/block/sde6`
  (sysfs: `MAJOR=8 MINOR=70`, `DEVNAME=sde6`, `PARTNAME=modem_a`,
  `PARTN=6`). Identity must therefore be confirmed from the sysfs uevent
  (`PARTNAME=modem_a`), not from a by-name symlink.
- **Mount check**: `/vendor/firmware_mnt` is **not mounted** in recovery, so
  the #88 pre-read `ro`-vfat-mount check at that path is inapplicable there;
  "not mounted" is the expected recovery state, not an abort.
- **Sector geometry**: the #88 recipe hard-assumed a 512-byte BPB sector
  size and `dd bs=512` sector math. The real partition reports **716800
  512-byte blocks = 367,001,600 bytes**, but its FAT filesystem uses
  **`bytes_per_sector = 4096`** with 89600 FAT sectors × 4096 = 367,001,600
  exactly (§2 records the full geometry). A raw whole-partition `dd` of the
  byte size is correct regardless of the FAT sector size; only the
  boot-sector check and the extractor's geometry math were wrong.
- **Boot signature**: with a 4096-byte boot sector the FAT `55 AA`
  signature sits at **offset 510–511 of the boot sector** (the FAT
  signature field is at fixed offset 510 even for large sectors, as on this
  dump), while the boot sector itself runs to byte 4095; a "first 512 bytes
  = whole boot sector" assumption is false for this partition.

The executed single read used the raw block device `/dev/block/sde6`
read-only, produced the hash-pinned dump above, and left the device
unchanged (post-read identity checks identical: same `PARTNAME`, size,
slot; no state change). No second read is authorized or needed.

## 2. Fail-closed host-side extraction and pd-mapper config generation

Input: the pinned `modem_a` dump from #89 (367,001,600 bytes, SHA-256
`08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`,
quarantined outside Git, read-only). The extractor never mounts anything and
never writes to a device; it parses the FAT filesystem read-only in pure
Python, so no host kernel or loop device touches the dump. Always re-verify
the dump's full SHA-256 before use.

Measured FAT geometry of that dump (from its BPB; #92 corrected the #88
512-byte assumptions here):

- OEM `MSDOS5.0`, **FAT16**, `bytes_per_sector = 4096`, 4 sectors per
  cluster (16384-byte clusters), 1 reserved sector, 2 FATs of 11 sectors,
  512 root entries (4 root-directory sectors), 89600 total sectors;
  `FAT16` type string at offset 54, `55 AA` at offset 510 of the 4096-byte
  boot sector; no volume label record.
- The #88 extractor wrongly required `55 AA` at image offset 510 only after
  assuming a 512-byte boot sector, and its LFN short-name checksum routine
  missed the per-step `& 0xFF` mask of the spec's rotate-and-add, computing
  `0x89` where the stock filesystem carries the spec value `0x35` for the
  LFN alias `image` (`PCAFUI~2`, NT lowercase flag `0x08`) — a parser bug,
  not variant on-disk behavior. #92 fixed both; the checksum comparison
  itself is unchanged and still fails closed (a wrong on-disk checksum
  remains a hard stop).

Run:

```sh
scripts/extract-modem-domain-maps.py <modem_a-dump> --out <outdir>
```

Fail-closed contract (each is a hard stop with a bounded error message, no
fallback, no guessed map):

- the input must be a regular file of non-zero size, exactly sized to a
  512-byte block multiple and ≥ 33 blocks;
- FAT12/16/32 BPB validation: bytes-per-sector one of 512/1024/2048/**4096**
  (all geometry in bytes is derived from the BPB value, never from a fixed
  512), `55 AA` at offset 510 of the boot sector, plausible
  sectors-per-FAT/cluster/root/geometry fields, consistent total-sector
  count against the file size, valid cluster count;
- the FAT table and directory chain are parsed read-only; long file names
  are honored with the spec short-name checksum enforced; every path is
  canonical (no `..`, absolute, no NUL, no repeats);
- it lists **every** `.jsn` under the `image/` root recursively (and reports
  the full file inventory); each is hashed (SHA-256) with path, size;
- each `.jsn` must parse as JSON and match one of the evidenced
  pd-mapper schemas — upstream `pd-mapper.c` `pd_load_map()` (nested
  `sr_domain` object with `soc`/`domain`/`subdomain`, optional
  `qmi_instance_id`, top-level `sr_service` array) or the flat key set #85
  measured from the stock pd-mapper binary strings
  (`soc`, `domain`, `subdomain`, `provider`, `sr_version`, `sr_service`).
  Optional top-level `sr_version` is either a non-negative integer or the
  stock object form `{"major": 1, "minor": 1, "patch": 1}` that the real
  dump carries in every `.jsn` (upstream `pd_load_map()` ignores the key
  entirely). Each service entry carries `provider` and `service` plus
  optional `instance`, `qmi_instance_id`, `service_data_valid`,
  `service_data`, and the stock `dcomment` string (bounded, ≤ 512 bytes;
  carried through verbatim, never interpreted). Anything else — unknown
  keys, wrong types, empty arrays, empty strings — fails;
- two `.jsn` files that disagree on `sr_version` or duplicate a service with
  different content for the same group fail (no silent merge);
- **zero `.jsn` under `image/` is a stop**, not a default map;
- a `.jsn` anywhere else than under `image/` is reported and also parsed —
  nothing is silently dropped.

Outputs (all under `--out`, which must be outside any Git worktree and
empty or absent; the directory is created atomically only after every check
passed, so a failed run leaves nothing behind):

- `maps/` — the byte-exact `.jsn` files as they sit in the dump, at their
  dump-relative paths;
- `domain-maps.json` — the parsed and validated maps, content-addressed with
  the source dump's SHA-256 and per-file hashes;
- `pd-mapper.conf.json` — derived **only** from the validated map data: one
  provider group per `{soc,domain,subdomain,provider,qmi_instance_id}` with
  its `sr_version` and sorted service entries;
- `extraction-manifest.txt` — dump host path (the dump itself never enters
  Git), dump size, dump SHA-256, FAT type, volume label, per-`.jsn`
  path/size/SHA-256, full file inventory and the pass verdict.

Every JSON output carries `"synthetic": true|false` (from the volume label),
`"non_flashable": true` and `"stock_verified": false`. `stock_verified` can
only become true after #89 hash-pins the real partition; the extractor
always writes `false` and never rewrites a past output. The optional
`--expect-synthetic` flag makes a run **fail** if the input is not labeled
synthetic — the test runner always passes it, so no test can accidentally
validate an unlabeled image.

No output is a flashable image; the config is a JSON input for #86's later
pd-mapper build, never an `init_boot` component.

### Synthetic tests (explicitly non-flashable, not stock evidence)

```sh
scripts/test-modem-domain-map-extraction.sh
```

Builds synthetic FAT dumps with `scripts/make-synthetic-modem-dump.py`
under `/tmp` — clearly marked synthetic (volume label `SYNTHETIC`, every
`.jsn` carries `soc`/`provider` values literally named `synthetic`) — and
runs the extractor against:

- a positive synthetic FAT12 dump (two nested-schema `.jsn` under
  `image/`, one nested directory): must produce the manifest, maps, config,
  per-file hashes and the `synthetic`/`non_flashable`/`stock_verified=false`
  stamps;
- a positive nested-schema dump without `sr_version` (as in the upstream
  parser) that still derives provider groups, preserving the absent value
  as `null`, not guessing a version; and a flat-schema positive dump
  exercising the stock-string key set with all optional service fields;
- an outside-`image/` `.jsn`: parsed and reported with `under_image=no`;
- negative fixtures, each failing closed with a bounded message and **no**
  output directory: `.jsn`-free `image/` root; no `image/` at all; invalid
  JSON; schema violation; duplicate directory entry; illegal 8.3 name;
  looping cluster chain; `.jsn` group conflict; non-FAT text; truncated
  dump; missing dump; bad arguments; output inside the Git worktree; reuse
  of a non-empty output directory;
- #92 fixtures: a 4096-byte-sector FAT16 image (4 sectors per cluster, 512
  root entries, `55 AA` at offset 510 of the 4096-byte boot sector) whose
  `image/` directory is LFN-aliased exactly as the real dump aliases it
  (`PCAFUI~2`, NT lowercase flag `0x08`, spec checksum `0x35`), carrying the
  stock `sr_version` object form `{"major","minor","patch"}` and a
  `dcomment` string; the same geometry with a deliberately wrong LFN
  checksum and with no `image/` directory, both failing closed; and the LFN
  alias case repeated on the small FAT12 fixture.

The synthetic fixtures exist only to exercise the parser and its failure
modes. They are not evidence about the stock `modem_a` content, and no
synthetic output is flashable or ever leaves `/tmp`.

## 3. Physical handoff to #89

Deliverables #89 received (after its authorization gate was recorded):

1. one verified, hash-pinned, read-only `modem_a` dump
   (367,001,600 bytes, SHA-256
   `08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`,
   captured 2026-10-25 by one read-only `dd` of the raw block device
   `/dev/block/sde6` in recovery; raw bytes stay under
   `~/phone-second-life-data/mb003/acquire/`, outside Git);
2. the §2 extraction outputs for that dump (`maps/`, `domain-maps.json`,
   `pd-mapper.conf.json`, `extraction-manifest.txt`), produced by the
   corrected #92 extractor: six validated `.jsn` under `image/` (paths and
   SHA-256 hashes recorded in the #92 issue comment), which unblock
   [#86](https://github.com/omnipha/linux-sm7635/issues/86) exactly when
   their manifest records a passed extraction of the #89 hash-pinned dump.

Gate: the physical coordinator's explicit authorization in #89 preceded
the acquisition. This repository's work ends at the procedure and the
extractor; no agent executes a further acquisition. No second device read
is authorized.

## 4. Independent evidence kept separate (not the #86 variable)

From [#85](https://github.com/omnipha/linux-sm7635/issues/85) — already
dumped/known stock material, evidence for a **later, separate** experiment
(the #85 top-ranked rmtfs candidate), **not** part of the pd-mapper/tftp
variable of #86:

- `msm_sharedmem.ko`: present in stock `vendor_dlkm_a`
  (`lib/modules/msm_sharedmem.ko`, vermagic 6.1.78, alias
  `of:N*T*Cqcom,sharedmem-uio`); the DT node `qcom,rmtfs_sharedmem@0`
  (`qcom,sharedmem-uio`, client-id 1, live-fdt.dts:6498-6503) had no driver
  in run 34 (zero `msm_sharedmem` kmsg lines), while stock logs
  `msm_sharedmem_probe: Device created for client 'rmtfs'`.
- rmt_storage/rmtfs by-name paths: the stock `rmt_storage` binary serves
  `/boot/modem_fs1`, `/boot/modem_fs2`, `/boot/modem_fsc`, `/boot/modem_fsg`
  — by-name `modemst1`, `modemst2`, `fsc`, `fsg` (`by-name.txt:50-53,35-36`);
  stock serves them within ~60 ms of modem `now up`
  (`console-ramoops-0:6154-6155`).

These are recorded here so the successor experiment can cite them without
re-derivation; they are not acquired, modified or validated by this issue,
and they are deliberately not merged into the #86 pd-mapper/tftp
experiment's variable set.
