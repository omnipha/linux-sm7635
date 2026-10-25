# SM7635 `modem_a` acquisition and stock domain-map extraction (host-only, #88)

Status: **procedure prepared, nothing executed**. This document and the
scripts below prepare two fail-closed steps: (1) a read-only physical
acquisition of the stock slot-A `modem_a` partition by the physical
coordinator, and (2) a host-side extraction/pd-mapper-config-generation for
a dump supplied later. Neither has been run against the device. The physical
step belongs to [#89](https://github.com/omnipha/linux-sm7635/issues/89) and
requires explicit physical-coordinator authorization; the standing approval
`full_autonomy_device_iteration` is **not** re-requested or implied by this
issue. No real stock domain map exists on the host yet
([#85](https://github.com/omnipha/linux-sm7635/issues/85), PR
[#87](https://github.com/omnipha/linux-sm7635/pull/87): the `.jsn` source is
`/vendor/firmware_mnt/image/` on the undumped `modem_a` partition), so
nothing here may be presented as stock evidence until #89 hash-pins the
actual partition.

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
  physical-coordinator read-only dump step consuming §1 below.

## 1. Read-only `modem_a` acquisition procedure (physical coordinator, #89)

Authorization gate (explicit, before anything else): the physical coordinator
personally confirms, in the #89 issue, that this single read-only acquisition
may proceed. Without that recorded authorization nothing below is executed.
No write, flash, reboot or remoteproc operation is part of this procedure.

Measured identity anchors (from #85 / run artifacts, not re-measured here):

- by-name `modem` in the active slot-A boot resolves to `modem_a` →
  `/dev/block/sde6` (`by-name.txt:50`, `dev.mnt.blk.vendor.firmware_mnt=[sde6]`
  in `getprop.txt:154`).
- The stock fstab mounts it vfat, read-only, at `/vendor/firmware_mnt`
  (`vendor_a` image `etc/fstab.qcom:63`).
- It is **not** part of `super` (`super` is `/dev/block/sda6`); never read a
  `super` extent in place of the raw `modem_a` device.

Precondition: #89 has a **separately authorized, already available**
read-only shell channel to the stock slot-A device with permission to read
`/dev/block/by-name/modem`. This issue does not create that channel or
authorize a boot, flash, USB/ADB operation, write, remount, or login setup.
If the channel is unavailable, stop and report the blocker in #89. The
following commands are a recipe for the physical coordinator **only after**
its explicit authorization, not an instruction to this worker to run them.
The host output location is outside Git. Use an empty, coordinator-created
private directory under `~/phone-second-life-data/mb003` for the dump; do
not copy raw bytes into an issue, a PR, or this repository.

On the **device** (read-only commands only), record `getprop
ro.boot.slot_suffix`, `readlink -f /dev/block/by-name/modem`,
`cat /sys/class/block/sde6/uevent`, `cat /sys/class/block/sde6/size`,
`cat /sys/class/block/sde6/queue/logical_block_size`, and the line for
`/vendor/firmware_mnt` in `/proc/mounts` before the read. The expected
values are `_a`, `/dev/block/sde6`, `PARTNAME=modem_a` in the uevent,
a strictly positive decimal sector count, a 512-byte logical block, and
an `ro` vfat mount at `/vendor/firmware_mnt` (or no mount). Compare the
by-name target and sysfs partition name, not only the historical `sde6`
index. Read the first 512 bytes of the **same** by-name block device
read-only (`dd if=/dev/block/by-name/modem bs=512 count=1 status=none`) and
check offset 510–511 is `55 aa`, the BPB sector size is 512, and the
FAT12/16/32 type signature at offset 54 or 82 is present. Abort if any
check fails; do not mount or change state to make it pass.

Once the coordinator has recorded the sector count `N` and verified all
identity checks, use the **host** as the only output target. The single
remote read is conceptually this exact command, with `N` replaced by the
recorded decimal sector count and `READ_ONLY_SHELL` replaced by the
coordinator's *already-authorized* transport (its stdout must be raw bytes,
not a TTY):

```sh
set -e
N=<verified-sector-count>
DUMP="$HOME/phone-second-life-data/mb003/acquire/modem_a.bin"
[ "$N" -gt 0 ] && [ ! -e "$DUMP" ] || exit 1
READ_ONLY_SHELL 'dd if=/dev/block/by-name/modem bs=512 count='"$N"' status=none' > "$DUMP"
[ "$(stat -c %s "$DUMP")" -eq "$((N * 512))" ] || exit 1
sha256sum "$DUMP"
```

`READ_ONLY_SHELL` is deliberately not supplied by this issue: replacing it
with an access path is a #89 physical-coordinator decision after the gate,
not a hidden device step. If the transport fails, the host redirection may
leave a partial file: quarantine it locally, record failure, and stop. Do
not re-read or retry blind. Do not pipe through a command that masks the
remote read's exit status; fail closed unless the transport propagates the
remote `dd` exit code. No partition write exists in the command.

On the **host**, verify the full dump size equals exactly `N × 512`, compute
and record its complete SHA-256 (not a prefix), and run the §2 extractor
against it; the extractor validates the copy's FAT BPB, geometry, directory
chains, `.jsn` files and map structure. A bad hash/size, unreadable block,
read/transport error, invalid FAT or unsuccessful extractor is a failed
acquisition, not stock-map evidence. Post-read, repeat the read-only device
identity/size/mount checks from before the read; any change aborts. Record
`modem_a size=<bytes> sha256=<64 hex> captured=<UTC timestamp> method=one read-only dd`
in #89 (plus extractor manifest hashes and paths only). The raw dump and
extracted `.jsn` stay outside Git. No rollback command is needed or
permitted because this recipe performs no device state change; if the
pre/post state differs, stop, preserve read-only evidence, and hand recovery
to the physical coordinator, not this issue.

Abort conditions (any one stops the procedure immediately; record the
failure in #89, do not retry blind, do not improvise):

- no separately authorized read-only channel exists, or the slot is not `_a`;
- the by-name target, sysfs `PARTNAME`, logical block size or size is not
  the expected modem partition identity;
- the FAT boot-sector signature/BPB check fails;
- the read or transport reports an error, a non-zero exit, or a byte count
  other than `N × 512`;
- the host-side size/hash or §2 extractor verification fails;
- any post-read identity/size/mount check differs from its pre-read value.

There is no flashing, no reboot, no remoteproc start and no other-partition
access in this procedure. Its failure mode is "stop and record", never
"retry" or "substitute".

## 2. Fail-closed host-side extraction and pd-mapper config generation

Input: a `modem_a` raw dump supplied later (from #89). The extractor never
mounts anything and never writes to a device; it parses the FAT filesystem
read-only in pure Python, so no host kernel or loop device touches the dump.

Run:

```sh
scripts/extract-modem-domain-maps.py <modem_a-dump> --out <outdir>
```

Fail-closed contract (each is a hard stop with a bounded error message, no
fallback, no guessed map):

- the input must be a regular file of non-zero size, exactly sized to a
  512-byte sector multiple and ≥ 33 sectors;
- FAT12/16/32 BPB validation: `55 AA` at 510, plausible
  sectors-per-FAT/cluster/root/geometry fields, consistent total-sector
  count against the file size, valid cluster count;
- the FAT table and directory chain are parsed read-only; every path is
  canonical (no `..`, absolute, no NUL, no repeats);
- it lists **every** `.jsn` under the `image/` root recursively (and reports
  the full file inventory); each is hashed (SHA-256) with path, size;
- each `.jsn` must parse as JSON and match one of the two evidenced
  pd-mapper schemas — upstream `pd-mapper.c` `pd_load_map()` (nested
  `sr_domain` object with `soc`/`domain`/`subdomain`, optional
  `qmi_instance_id`, top-level `sr_service` array and optional `sr_version`)
  or the flat key set #85 measured from the stock pd-mapper binary strings
  (`soc`, `domain`, `subdomain`, `provider`, `sr_version`, `sr_service`). Each
  service entry carries `provider` and `service` plus optional `instance`,
  `qmi_instance_id`, `service_data_valid`, and `service_data` fields.
  Anything else — unknown keys, wrong types, empty arrays, empty strings —
  fails;
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

Builds synthetic FAT12 dumps with `scripts/make-synthetic-modem-dump.py`
under `/tmp` — clearly marked synthetic (volume label `SYNTHETIC`, every
`.jsn` carries `soc`/`provider` values literally named `synthetic`) — and
runs the extractor against:

- a positive synthetic dump (two nested-schema `.jsn` under `image/`, one
  nested directory): must produce the manifest, maps, config, per-file
  hashes and the `synthetic`/`non_flashable`/`stock_verified=false` stamps;
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
  of a non-empty output directory.

The synthetic fixtures exist only to exercise the parser and its failure
modes. They are not evidence about the stock `modem_a` content, and no
synthetic output is flashable or ever leaves `/tmp`.

## 3. Physical handoff to #89

Deliverables #89 receives (only after its authorization gate is recorded):

1. one verified, hash-pinned, read-only `modem_a` dump
   (size + SHA-256 recorded in the #89 issue; raw bytes stay under
   `~/phone-second-life-data/mb003/acquire/`, outside Git);
2. the §2 extraction outputs for that dump (`maps/`, `domain-maps.json`,
   `pd-mapper.conf.json`, `extraction-manifest.txt`), which unblock
   [#86](https://github.com/omnipha/linux-sm7635/issues/86) exactly when
   their manifest records a passed extraction of the #89 hash-pinned dump.

Gate: the physical coordinator's explicit authorization in #89 precedes
step 1 of §1. This repository's work ends at the procedure and the
extractor; no agent executes the acquisition.

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
