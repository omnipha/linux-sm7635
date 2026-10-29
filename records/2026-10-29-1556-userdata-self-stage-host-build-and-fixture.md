---
date: 2026-10-29
issue: omnipha/linux-sm7635#176
subsystem: userspace
result: inconclusive
---
## `userdata` self-stage host build and fixture (#176, host-only)

**Host-only: no USB, flash, guest boot or physical result. #176 stays OPEN for
the coordinator-held second-boot and WLAN-autoconnect measurement.** The single
image variable is the staging source: the same pinned archive now comes from a
small plain ext4 image on `userdata` instead of the raw `recovery_b` window.

### Deterministic `userdata` ext4 image

`scripts/build-userdata-userspace-payload.sh` (Python builder of the same base
name) produces `$WORK/out/userdata-userspace.img` outside Git under
`flock`. It is 33,554,432 bytes (8192 x 4096), one plain ext4 filesystem with
no journal, fixed UUID `6f6d6e69-7068-4170-6d6f-732d7573726b`, fixed directory
hash seed `6f6d6e69-7068-4173-6565-642d75737264` and fixed timestamps
(1767225600), containing exactly `/omnipha-userspace/` (0700) and the pinned
23,713,302-byte archive `7a76a110…` as a root-owned 0444 regular file. Two
serial builds are required to be byte-identical; `--verify` reproduces the whole
image, runs `e2fsck -f -n`, checks the root listing and file type, and re-reads
the archive with `debugfs`. SHA-256 on the current pinned inputs:
`ea09444c0ddde87e970d0b27cb8c067a28424da6501eed88bca749729855d4ed`.
`--self-test` rejects truncation, changed archive bytes, wrong size, extra root
entries and a symlinked archive path.

Flashing this image is a normal raw flash of `userdata`, not a resize or a
`super` write: `fastboot flash userdata` writes the 32 MiB image at the start of
the partition and the rest of `userdata` stays stale/unused, because the ext4
superblock fixes the filesystem size at 8192 blocks. The guest mounts it
read-only with `noload`, so no journal replay, fsck or format happens on the
phone. `userdata` has no backup; the owner approved the wipe for the Linux root
home.

### `init_boot` single-delta proof

`scripts/pmos-self-stage.sh` changes only the staging block: exactly one
`PARTNAME=userdata` in sysfs with verified major:minor, size at least the image
size, `mount -t ext4 -o ro,noload`, a `/proc/mounts` check for `ro` plus
`noload`/`norecovery`, fixed-path regular-file/size/SHA-256 checks, copy to RAM,
unmount and mountpoint removal on both success and failure. The 150 s
`/run/keep` guard, 145 s wait, 151.01 s settle, 160 s host-owned ack, pinned-key
`:2222`, every script pin and all fail-closed checks are unchanged.
`scripts/build-init-boot-self-stage.py` replaces that block with the recorded
`recovery_b` block and requires script SHA `af5e4c53…`, then rebuilds the old
init and requires exactly run-61 `bee02ce1…` (and run-58 `4b83ea24…` for the
older carrier), so any other delta, marker line, writable mount or wrong
archive pin fails closed. `scripts/build-init-boot-self-stage.sh` produced
8,388,608-byte `$WORK/out/init_boot-self-stage-userdata.img`, SHA-256
`fcb0ed91c83461be1f22df859c2f9b331e72d31a576fcf33876de6c3136c2e0d`, LZ4 HC-12
frame 2,116,092 of 2,117,632 bytes, signed tail unchanged.

### Verification and timing budget

```sh
scripts/build-userdata-userspace-payload.sh
scripts/build-init-boot-self-stage.sh
scripts/verify-bootimg.sh init-boot-self-stage --fixture
sh scripts/test-pmos-pid1.sh
sh scripts/test-usb-readdress.sh
```

All passed host-only. The verifier and `verify-bootimg.sh` reject stock
`baa33fd4…`, handoff `fef03008…`, both never-reflash pairs (`4b83ea24…` /
`1bdb7c22…`, `bee02ce1…` / `41cab142…`), stock `vendor_boot`/`recovery_b`
hashes, marker-only deltas, a writable mount and wrong archive size/hash.
`scripts/test-pmos-self-stage.sh` attaches the built image read-only through a
loop device and really mounts it `ro,noload` in a mount namespace: it proves
refusal on zero/duplicate `PARTNAME`, wrong node numbers, non-block/symlinked
nodes, a too-small device, an occupied mountpoint, a pre-existing tarball, a
non-ext4 filesystem, a changed archive byte, a short/wrong-mode/missing file and
a symlinked path, plus a forced writable mount; the positive copy is
hash-verified and unmounted. A userspace timer does not cover a kernel hang.
The carrier read is bounded by the existing 2 s device query, 5 s mount and 30 s
copy timeouts inside the unchanged guard sequencing; the second-boot budget is
unchanged (measured ~17 s gadget gap plus immediate udev re-addressing leaves
over 120 s of the 145 s `/run/keep` wait).

### Coordinator-only physical commands (not run here)

These are recorded for the physical coordinator, who owns preflight, one held
session, flashing only this verified pair, capture, the single guest reboot and
stock rollback. They must not be run by host-only repo work. `WORK` is the host
build directory; the candidate hashes must be rechecked immediately before use.

```sh
sha256sum "$WORK/out/init_boot-self-stage-userdata.img" "$WORK/out/userdata-userspace.img"
fastboot flash init_boot_a "$WORK/out/init_boot-self-stage-userdata.img"
fastboot flash userdata "$WORK/out/userdata-userspace.img"
```

Writes are limited to `init_boot_a` and `userdata`. `recovery_b`,
`vendor_boot_b`, `boot_a`, `vendor_boot_a`, `dtbo_*`, `vbmeta_*` and `super`
stay untouched. After capture, `/run/keep`, self-stage and the PID-1 request,
the coordinator releases the ack with the merged #174 contract
(`sh scripts/pmos-pid1-ack.sh "$BOOT_ID" "$KNOWN_HOSTS_2222" "$CLIENT_KEY"`)
and requires both acceptance lines before any stage marker, then measures
modem/WPSS/`wlan0`, one clean guest reboot, host re-addressing, fresh boot ID,
`:22`, second `userdata` self-stage and WLAN autoconnect. Rollback restores the
pinned stock `init_boot_a` and uses a supported stock `userdata` restore, never
a non-supported partial restore:

```sh
fastboot flash init_boot_a "$HOME/phone-second-life-data/mb003/parts/init_boot_a.img"
fastboot erase userdata
fastboot reboot
```

The coordinator may instead choose recovery's stock format of `userdata`; stock
Android recreates and re-encrypts it on first boot. Rollback is complete only
after the five slot-A hashes match the pinned backups and Android
`boot_completed` is observed. No profile, scan dump, private address or private
artifact is in Git or this record. BOOT.md remains the historical pointer; its
commands for this phase live in this record per the append-only records policy.
