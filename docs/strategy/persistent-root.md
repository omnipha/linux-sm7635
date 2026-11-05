# Persistent-root migration strategy

Status: **proposal under revision**, not implemented or accepted. This document
is not evidence and authorizes no installation, flash, reboot or device
access. The physical coordinator owns every device decision. #324 requires
PC-style SSH edits that survive reboot without a partition flash, measured
writable-root and rescue behavior, and provenance-checked updates **and
rollback** with protection equivalent to the current pins.

Host-side decision: pursue the signed-generation design and phase-separated
inspection/write sequencing below, without relaxing any existing guard or pin.
This is a direction for further host work, **not deployment approval**. The
[190612 record](../../records/2026-11-04-190612-pair-deliverable-host-proofs.md)
reports an inconclusive result: no replacement pair was built, and no
owner-authorized signing keys, signed baseline or embedded trust anchors are
demonstrated. Only synthetic throwaway-key fixtures exist. The migration model
and the other host fixtures are described below; they do not supply a
deployable bootstrap. The record also reports a failed host PID 1 `ack` case;
`test-pmos-pid1.sh` has since been rewritten and passes all six host cases
against the unchanged guard (fixture-authored `success-ready` and record
evidence, see the finding below); this is a host result, not a device ACK.

## Current boundary

[Run 113](../../records/2026-11-04-093054-run113-pair-installed-internet-route-gate-refused.md)
installed and measured this dependent pair:

| Partition | SHA-256 |
| --- | --- |
| `init_boot_a` | `d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c` |
| `vendor_boot_b` | `221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500` |

Keep this pair installed and unchanged while a replacement is designed and
verified. **Never reflash this measured pair**; it is not the fallback after a
failed cutover. This proposal does not authorize any other pair. Run 113
reached persistent-root PID 1 and the internet gate refused; no WLAN success
or cause of the missing route output is established. Its installed-files
check implied a writable stage; run 116 later observed the final root mounted
`ext4 rw,relatime,norecovery` on `sda13` (see "Next single variable").

The current generated chain checks these three regular, single-link,
`root:root` `0700` files against exact SHA-256 pins:

| Fixed path | Current SHA-256 |
| --- | --- |
| `/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh` | `146ed59271cde6b593f28212caf8871c0f00062a3c5b1d460c858e4c90271e14` |
| `/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh` | `113553dddfc646b77dacb06777cc2c450e4f17d33aaf508e3113c993968ac0f3` |
| `/etc/local.d/10-omnipha-self-stage.start` | `3d317a6937f547565968785dee9984c9d5edd714ac0a8dde4c1dbf2c550b4e67` |

The checks are not just one installer setting:

- Image-carried `pmos-session-stage.sh` checks the existing hook against its
  fixed digest before continuing
  (`scripts/build-init-boot-persistent-root.py:354`).
- Image-carried self-stage's `persistent_installer()` verifies the carrier
  payloads and existing files, installs only missing files, and refuses a
  mismatch rather than overwriting it
  (`scripts/build-init-boot-persistent-root.py:182`).
- The generated hook itself pins both post and radio before launching the
  post (`scripts/derive-success-gated-ack.py:714`); the post also pins radio.
- The radio used for pre-cutover `prepare` is separately staged and pinned
  from the verified carrier. `runtime_scripts()` and self-stage bind that
  staged radio to the same fresh-radio digest
  (`scripts/build-init-boot-persistent-root.py:709`).

Thus ordinary userland edits are not automatically blocked, but replacing
these three paths needs a reviewed migration. A signed file, verifier or
manifest placed on userdata cannot change the image-carried checks. Publishing
the hook last cannot make its old embedded pins accept new bytes, and a
local-only manifest cannot create an independent trust anchor. The separately
pinned route-cache variant is refused by the installed installer, not an
in-place update
([host integration](../../records/2026-11-04-113000-route-cache-variant-integration.md)).

## Trust boundary and required carrier cutover

Replace the pins, **do not drop them**. The existing installed pair and its
fail-closed checks remain unchanged until a replacement has passed independent
host verification. The proposed replacement is one different, independently
verified `init_boot_a` / `vendor_boot_b` pair with changed pre-SSH bootstrap
code. This is the only proposed technical reason for the coordinator to
consider one different verified pair after host proofs: userdata alone cannot
change the current image-carried session-stage, installer and staged-radio
pins. Host approval does not itself authorize a device write.

The new bootstrap would validate the entire selected signed generation before
any managed file is executed, before guest SSH or PID 1 cutover, and before
radio `prepare`. Diagnostic key-only USB SSH and rescue must remain available
on refusal; prove the required sequencing without weakening the present
rescue path. If that cannot be implemented and tested without compromising
rescue, do not deploy.

### Threat boundary and candidate sequencing

Defensible boundary: **no untrusted privileged writer may exist while a
bounded transaction write occurs.** "Untrusted privileged writer" means any
process that can write the userdata filesystem or change its mount state
without passing the verified updater — explicitly including diagnostic SSH
sessions and processes spawned earlier in the boot (a shell left running,
a background job, a child that outlived its parent) and processes in
alternate mount namespaces, which can hold their own writable view of the
same filesystem. The boundary is about what exists, not about what is
connected: disconnecting the SSH client does not terminate a session's
processes, so it does not by itself exclude root writers.

Neither of the two mechanisms examined can enforce this boundary.
`scripts/test-pmos-writer-exclusion.sh` demonstrates the negative on a
synthetic tmpfs: `flock` excludes only cooperating `flock` users (an
unprivileged non-cooperating writer appended 20 lines under a held lock);
a `ro` bind mount denies writers going through that mount, including root
(`EROFS`), but not writers using the still-`rw` original path, and root can
remount it; root can also `nsenter` into another mount namespace and remount
its view. `ro,noload` has the same shape as a read-only mount option: it
constrains opens through the mounts that carry it, and a privileged process
can remount or use a mount that does not carry it. Cooperative locks plus
`ro,noload` are therefore necessary hygiene, not the exclusion mechanism.

Candidate sequencing, proposed and not proven: keep userdata read-only from
mount until a bounded write window; before opening that window, read-only
inspection must establish that no privileged writer exists — no diagnostic
or earlier-spawned process able to write, no other mount namespace holding
the filesystem writable — and the same inspection must hold after the window
closes and the transaction is reverified. The window itself is the only
interval in which the verified updater writes, and it must be abortable back
to the preverified previous generation through the recovery table below,
with diagnostic recovery and rescue reachable in every phase.

This sequencing is a direction, not a production proof. No mechanism has
been independently demonstrated to establish that quiescence, to prevent a
privileged writer from appearing during the window, and to keep rescue and
abort safe at the same time; asserting the sequence does not make it true.
Until such a mechanism exists and is demonstrated without weakening rescue,
the exclusion requirement is unmet and no transaction write is deployable.

The independently verified image pair is the trust anchor, not a key or
verifier first obtained from userdata. The proposal assumes the coordinator's
existing host verification, pair handoff, targeted write and readback gates;
it does not claim hardware-enforced verified boot on this device. A party that
can replace the trusted images, the offline signing keys, or the running kernel
is outside this boundary. Root SSH can also execute arbitrary user commands
and alter other userland: this proposal protects the specified boot chain, not
the entire operating system against an already privileged root user.

- Trust anchor: two offline Ed25519 keys — one release key and one separately
  controlled rollback-authorization key — embedded as public keys in the
  verified initramfs, or in the carrier bundle whose exact header and payload
  digests are pinned by that initramfs. This is the design's trust anchor, not
  a key or verifier first obtained from userdata. Owner decision "Option A"
  (2026-11-05, #324 comment 6652407108) approves this two-key shape; private
  halves stay offline outside the repository and must never be read, copied or
  committed. The two role-specific Ed25519 owner public keys are now recorded
  in `configs/persistent-root-trust-anchors.json` with their fingerprints
  (release `SHA256:aiUM8xoA0XpncAyFhsf+mVp2h/MqO0ag9byKnaohBJ8`,
  comment `omnipha-sm7635-release-20261105`; rollback
  `SHA256:bhAnhbEInLjaSxPUHzjnXjZkGuN0SvA5VkCCVTLfpsA`,
  comment `omnipha-sm7635-rollback-20261105`) and pinned in
  `scripts/persistent_root_trust.py`. Its production check reads only that
  fixed config, requires the exact role comments, and fails closed when a
  slot, pin, file or key is absent, malformed, duplicated, swapped or not the
  reviewed value. A throwaway key is not identifiable from its public bytes
  and cannot pass that gate or become a shippable default. The host gate does
  not build or verify an image; recording the public anchors is a prerequisite
  for a future replacement pair, not the building of one. Pin and verify the
  verifier, hashing tools, static interpreter and updater the same way. Key
  rotation or verifier replacement needs a separately reviewed carrier cutover;
  userdata cannot authorize its own trust-root replacement. The pins and
  config live in the same reviewable commit, so after they are recorded the
  gate relies on review of that recording commit, not on an independent
  cryptographic property.
- Before and after `switch_root`, security decisions must use verified
  RAM-side tools, not executables, interpreters or mutable runtime libraries
  loaded from userdata. Map and pin the complete executable and dependency
  closure used by the verifier, installer, generated hook, guard and their
  security decisions; use static tools or verified RAM-side libraries, a
  sanitized environment and protected paths. In particular, the byte-exact
  baseline scripts call `/bin/busybox`: prove the exact compatible binary and
  arrange a verified read-only RAM-side instance at that path across cutover,
  with PID 1/guard identity checks still valid. Account for any deliberately
  mounted runtime path in mount-topology checks. If this closure, image size
  envelope, timing or rescue behavior cannot be proven, the design is blocked.
- Keep the root contract, guard arming and recovery deadline, nonce and ACK
  protocol, capture gates, host-key pins and success conditions at least as
  strict as today. No host ACK, forged marker, weakened interlock or manual
  radio recipe is a substitute. Never install, carry as a candidate, or execute
  the altered radio
  `d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3`
  ([run 106](../../records/2026-11-03-143859-run106-radio-pin-mismatch.md)).

## Signed generation contract

A release consists of a bounded, strictly parsed bundle with exactly one
canonical manifest, its detached release signature and the three payloads in
the table order above. Use a fixed length-delimited framing, not general archive
extraction. Proposed hard bounds are 4 KiB for the manifest, 1 MiB per payload
and 3 MiB plus 8 KiB for the bundle; prove these accommodate the byte-exact
baseline and the RAM budget before implementation. Reject overflow, trailing
bytes, duplicate members or any unrecognized field.

Define manifest v1 as UTF-8 ASCII-only JSON with a single prescribed key and
array order, no whitespace, escapes, duplicate keys, unknown keys or alternate
number spellings. The exact schema and test vectors are part of the future
implementation review. It contains:

- schema `omnipha-sm7635-root-generation-v1`, an integer sequence number with
  `0 <= sequence <= 2**31 - 1`, operation `baseline`, `forward` or `rollback`,
  and `previous`;
- exactly the three absolute paths above, their exact byte sizes, lowercase
  SHA-256 digests, owner/group `0:0` and mode `0700`, in fixed order;
- for a rollback, the ID of the retained generation whose **content** is to
  be restored; otherwise that field is null.

The generation ID is SHA-256 of the exact canonical manifest bytes, computed
outside the manifest; it is not a self-referential field. An Ed25519 release
signature covers a fixed domain separator followed by those exact bytes. The
manifest's `previous` is the exact active manifest ID, so the signed statement
specifies the intended previous-to-target transition; only the initial
image-pinned baseline may have a null predecessor. Reject alternate encodings,
malformed signatures, wrong keys, versions, paths, sizes, modes or digests.

Each later generation has sequence `previous + 1`. A normal update can only
advance from the verified current ID; reject stale, skipped, substituted or
replayed transitions. A rollback is **not** an unsigned selector edit or a
reuse of an old manifest: it is a forward transition in sequencing terms — a
new, higher-sequence generation naming the current ID as predecessor and
reproducing the exact three bytes of the named, verified earlier generation —
while being separately authorized across a separate domain and a different
public key: a detached rollback-authorization signature by the
rollback-authorization key covers the rollback namespace and domain with the
current ID, the new target ID, the restored source content ID and the
sequence, in addition to the release signature on the manifest. Verify both
signatures, the identifier and sequence binding, and the retained earlier
source before installing. Recovery of an interrupted, uncommitted
transaction to its previous generation is not a committed release rollback.

A host-only prototype, `scripts/verify-root-generation-bundle.py --self-test`,
checks framed chains with real SSHSIG, a pinned baseline, distinct key blobs and
exact older-ancestor rollback. It is not wired into any image, userdata or write
path and is not a target-side verifier closure. Its forward rule is an
experimental full-tuple reissue refusal only: a forward reusing one earlier
payload, or trivially altered older bytes, is still accepted, and the logical
model accepts full reissue. Hash comparison is not semantic downgrade
prevention. That difference needs an owner decision before either rule is
adopted. All three host prototypes now share one sequence bound: `sequence` is an
integer with `0 <= sequence <= 2**31 - 1` (`SEQUENCE_MAX`). The bound is a
host-contract limit, not a device measurement: it keeps the decimal
representation inside 10 digits, well under the 4 KiB manifest cap, and it
matches the verifier's existing constant. Baseline sequence 0, forward and
rollback sequences 1 through `SEQUENCE_MAX`, and rollback statements at 1 and
`SEQUENCE_MAX` are accepted; negative, non-integer, and values at or above
2**31 are refused by the model parser, the model rollback statement, and the
verifier parser and rollback statement alike, as does the baseline-provenance
fixture's parser and rollback statement. This unifies the earlier divergence
where the model and the provenance fixture accepted any nonnegative integer.
The model and the provenance fixture now also delegate signer-file loading and
signature armor checks to the verifier's strict policy: one canonical
single-link regular `ssh-ed25519` line per role with the exact role principal
and namespace, distinct role key blobs pinned once per verification call and
re-checked against the signer file within that call only (no pin persists
across calls or boots), and canonical armor in the expected namespace. They
differ from the verifier in rules not about the anchors themselves (full-tuple
reissue, baseline pinning, the provenance fixture's denylist coverage), which
still need the owner decision above. All three sign their chains with per-run
throwaway keys. Owner anchors are consumed only by
`persistent_root_trust.load_owner_anchors` and the verifier's
`verify_owner_bootstrap_baseline` / `verify_owner_chain` entry points. Those
entry points verify the release or rollback signature against the anchors from
`load_owner_anchors` and, separately and independently, require the baseline
payloads to equal the hardcoded `BASELINE_DIGESTS` and `BASELINE_SIZES`. The
baseline manifest ID stays caller-supplied and is not pinned anywhere: there is
no recorded binding between one owner key and one baseline. No owner-signed
bundle exists — private keys are offline — so the only positive owner-path
test runs against an explicitly labeled fake loader with throwaway keys, and a
valid throwaway-signed chain is refused by the genuine owner entry points.
Owner keys are verified only against the hardcoded fixture principal and
namespace strings; adopting real identities is an open design point of the
separately reviewed cutover, not a settled property of the recorded keys.
The acceptance above is parser and statement acceptance only; it is not a
full signed-chain verification at the boundary. A successor to `SEQUENCE_MAX`
cannot exist: it would need sequence `SEQUENCE_MAX + 1`, which the parser
refuses, so a chain head at the bound fails closed instead of wrapping.

Realistic replay limits: sequence and selector checks hold only relative to
intact local state. A privileged actor — or a whole-userdata rollback —
that rewinds the selector, the matching history, or the locally stored
rollback authorization is not detected by the sequence check alone; the
host model prints both limits explicitly, and accepts selector
rewind with identical restored bytes as well as whole-store rewind. There is
no hardware monotonic guarantee, so these are intentionally scoped
detections, not anti-rollback hardware semantics.

Retain the signed baseline and full predecessor chain, with a reviewed bound
on chain length and storage; check every link back to the image-pinned baseline
at boot. Capacity exhaustion, missing history, or sequence exhaustion at
`SEQUENCE_MAX` stops further updates rather than silently pruning trust or
wrapping the sequence. Sequence and selector state live on userdata and
are subject to the replay limits above. The same limit applies to locally
stored rollback authorizations; physical and signing-key controls remain
necessary.

Independent release review must derive the radio, post and hook from exact
reviewed source inputs, not merely sign arbitrary bytes. In each generation,
the hook's embedded post/radio hashes and the post's radio hash must match the
signed payloads. The bootstrap must stage the **same selected radio bytes**
for pre-cutover `prepare` and for post-cutover use, with its active digest
bound to that generation. Thus session-stage hook verification, installer,
hook, post and staged-radio runtime pins change together; updating a single
file or only a manifest is never sufficient.

## Verification and update storage

Proposed private storage is
`/var/lib/omnipha/root-generations/`, on the same pinned userdata filesystem.
Each immutable `generations/<manifest-id>/` contains the canonical manifest,
signature, any rollback authorization and separate copies of all three exact
payloads. The root-owned `0600` regular `selector` names one manifest ID;
a root-owned `0600` transaction journal names its previous and target IDs.
Generation directories and the store are `root:root` `0700`. Copies are
single-link regular files, not links to the active fixed paths. Paths and
metadata are a proposed interface, not deployed state.

An update is submitted as data over SSH to a bounded staging area; it is not
executed there. The trusted RAM-side updater applies it only on a later boot,
before guest startup, after the root contract verifies the single
`PARTNAME=userdata` ext4 device, size and mount identity. It starts read-only
with `noload`; any later promotion to writable mode is conditional on the
filesystem policy below and on the threat boundary above, and `noload` or the
read-only flag is not itself the exclusion. No mutable userdata verifier or
library participates in that decision. All verification, including the
inspections before and after the write window, is read-only.

Before reading or writing, the verifier must reject:

- oversized, truncated, ambiguous, duplicated or unknown input, invalid
  signature or unauthorized rollback, and any path outside the three fixed
  paths; do not execute, source or extract bundle content;
- unsafe parent ownership or permissions, set-id bits, ACLs or capabilities
  that change the intended access policy, unexpected objects in managed
  locations, or foreign devices and parent/nested mounts. Inspect mountinfo
  before use and recognize only explicitly verified bootstrap mounts;
- symlinks in any component, hardlinks, path aliases or collisions, wrong
  type, owner, group, mode, link count, size or digest. An unexpected local.d
  startup hook remains a refusal;
- staging-name collisions, changed inodes or mount topology, concurrent
  writers and read/verify/publish races. Use directory file descriptors,
  no-follow/beneath resolution and `fstat` checks; copy and hash bounded
  input into protected RAM and recheck both source and destination. No
  pathname check followed by an unprotected reopen is a proof.

Every active fixed path and its generation copy must agree in bytes and
metadata with the verified selected manifest before launch. A missing or
unknown fixed file, including a file matching neither side of a recorded
transaction, is a stop, not an instruction to recreate or overwrite it.
Ordinary edits elsewhere are outside this three-path mechanism.

## Publication and interruption recovery

The selector alone cannot atomically change three existing fixed files. The
proposed updater therefore gates **all** managed startup until a transaction
has reached a consistent state; no hook-last shortcut is used. With a clean
filesystem and the threat boundary above satisfied by a mechanism that has
been independently demonstrated (none has), it performs these steps inside
the bounded write window:

1. Verify the selected previous signed chain, its retained payload copies,
   all three fixed files and their metadata. Verify the target bundle and its
   explicit transition, including rollback authorization if applicable.
   Keep the previous generation intact and preverified.
2. Create the target generation under an exclusive staging name. Write,
   `fsync`, read back and verify each member and its metadata; `fsync` the
   directory, publish the complete generation without replacement, and
   `fsync` its parent. Any unrecognized collision stops; never overwrite a
   generation or delete an unknown object.
3. Write and `fsync` a transaction journal containing the two IDs; publish it
   without replacement and `fsync` its parent **before** changing any fixed
   path. The journal is not authority: signed manifests and the verified
   predecessor relationship are. Stage an exact target copy in each fixed
   path's own directory, `fsync` each file, verify it and its parent, and
   replace only the separately verified previous file with an atomic rename.
   Recheck inode, type, mode, link count and digest after each publication;
   `fsync` each affected directory. Replacement is permitted only inside this
   recorded, authorized transition and with no untrusted privileged writer
   present, never on a mismatch.
4. Reverify all three fixed paths as the target together. Write a new regular
   selector to an exclusive temporary name, `fsync` it, atomically rename it
   over the verified previous selector, and `fsync` the selector directory.
   Reverify selector, target, fixed paths and mount topology. Atomically move
   the recognized journal to a unique no-replace history name and `fsync` the
   directory. Only after this commit may managed startup proceed.

On each boot, first verify the previous signed generation and inspect the
journal, selector, fixed paths and staging names without executing them:

| Observed state | Deterministic action |
| --- | --- |
| No journal; selector and all fixed paths match one verified generation | Start that generation after all checks pass. |
| Valid pending journal; selector is previous or target; each fixed file is exactly the signed previous or target version | Treat the transition as uncommitted. Restore **all three** from the preverified previous generation using exclusive staged copies and atomic per-file renames; fsync files and directories, atomically restore/fsync the previous selector, reverify the complete previous set, then archive the recognized journal without replacement. Recovery is idempotent if interrupted again. |
| Incomplete target staging before the journal, with the selector and all fixed files still exactly previous | Preserve and report the inert staging object. Start the verified previous generation only if its isolation and all metadata checks pass; block further updates until separately reviewed cleanup. Unknown collisions stop instead. |
| Missing/invalid previous generation, invalid journal or transition, unknown or missing fixed file, unsafe metadata/mount, I/O or fsync failure | Stop reconciliation and managed startup; retain objects for coordinator-led rescue. Never silently overwrite, guess a generation, or recursively clean up. |

A target selector observed with a still-present journal is deliberately
rolled back to previous: target is committed only after the journal's durable
archive. After a crash during archival, either the journal remains and
recovery runs, or it is absent and the fully synced target is reverified. A
crash or filesystem failure that produces anything outside these recognized
states is a refusal, not automatic repair. Archiving only the verified journal
is not permission to remove arbitrary staging data. `fsync` ordering is a
conditional durability argument, not a simulation or measurement of power
loss; actual storage behavior and failures still require separate evidence.

## Baseline and migration gates

1. Host-side, derive the three table bytes from the exact pinned builder and
   derivation chain. Create an initial signed baseline whose manifest and
   payload digests exactly reproduce **all three**. Pin its manifest ID in the
   proposed carrier as well as verifying its signature. Independent review
   checks derivation inputs, byte equality, interlocks, both image digests,
   dependent-pair binding, image envelope and stock-reference preservation.
2. The proposed new bootstrap accepts the uninitialized store only when the
   three existing fixed files are all present and exactly match the baseline,
   including metadata and mount checks. It creates and syncs the baseline
   generation and selector without replacing those fixed files. If interrupted,
   it either completes from the image-pinned signed baseline when all
   recognized state verifies, or stops with unknown/partial objects preserved
   for review. It must never treat an unknown existing file as missing.
3. Only after host model tests, independent release review and the
   coordinator's separate authorization may the coordinator consider a
   different verified pair. Identity, checksum-verified backups and rescue
   preflight are mandatory before any write. The old pair remains installed
   until that decision; do not erase or format userdata. No plan here relies
   on reflashing the measured pair for fallback. If the new carrier fails,
   preserve evidence and use the coordinator's separately verified rescue
   procedure, not an assumed restoration path.
4. Once the baseline is verified under the replacement carrier, later signed
   transitions can update the fixed paths without flashing partitions. A
   route-cache candidate is not implicitly approved or signed by this design;
   #311 remains paused pending the reviewed #324 migration path.

## Host proofs and physical measurement

An independent second agent should write **host-only model tests** against
this contract, without this design depending on their fixture details. Required
cases include canonical/signature and separately authorized rollback vectors,
wrong predecessor and replay, altered `d7b74c24…`, unsafe metadata and
mounts, symlinks/hardlinks/collisions, races, fsync/I/O failures, and an
interruption at every staging, rename, selector, journal and recovery step.
Exercise hook/post/radio pin agreement and unchanged guard/nonce/ACK behavior.
Synthetic keys and fixtures are illustrative only: they are not deployable
bundles and do not establish device behavior. Independently verify the actual
candidate pair and release derivations in addition to the model.

Current host fixture boundaries, as run on this checkout (host-only; no
device, USB, flash or partition access):

- `scripts/test-persistent-root-migration.py` (passes) is a synthetic
  logical model with disposable `ssh-keygen` Ed25519 keys. It exercises canonical-manifest and authorization vectors, a
  separately keyed and domain-separated higher-sequence rollback, and
   interruption cuts at every modelled publication and recovery step (49
   forward and 52 rollback publication cuts, each with 1300 recovery cuts).
  Recovery coverage is of that abstract state machine, not of ext4, `fsync`
  or a power cut. Its legacy-fixture sections run on unprivileged host
  directories with path-based `lstat` checks that have reopen races and no
  root ownership, ACL, capability, mount, `fsync` or case-insensitive
  filesystem coverage. It prints that it is not deployable and has no
  device, durability, concurrency, mount, guard or hardware anti-replay proof.
- Known gaps and trade-offs the model asserts: clean boot inspects leftover
  temporary objects via `inspect_leftovers` rather than ignoring them, but
  judges staged generation prefixes only against a caller-supplied verified
  candidate generation (a real boot has no such oracle); an uncleaned previous
  staging attempt causes `staging collision` and refuses another update until
  resolved; retries succeed after a recovered journal-publish cut or
  selector-rename cut, whereas fixed/selector temporary staging cuts refuse
  another update without cleanup; and `recognized`/`isolated`/`safe_metadata`
  remain abstract model booleans.

- `scripts/test-pmos-writer-exclusion.sh` (synthetic tmpfs in a private mount
  namespace) shows the negatives described in the threat boundary; it
  establishes no sufficient exclusion for any real block device.
- `scripts/test-pmos-journal-fsck.sh` (synthetic loop images) checks a strict
  offline `dumpe2fs` allowlist and a clean `e2fsck -fn` transcript; it is not
  a production filesystem safety proof or the live `sda13` measurement.
-   `scripts/test-pmos-baseline-provenance.py` (synthetic throwaway keys)
  derives the three baseline payloads and checks the contract except the
  altered-radio denylist, which its parser does not enforce (`ALTERED_RADIO`
  is only asserted against the derived bytes). The model and the verifier do
  refuse that digest inside their parsers.

The first physical measurement is a separately authorized,
coordinator-run baseline cutover boot, not part of this proposal. Preflight
must establish targeted fastboot identity, checksum-verified backups before
writes, verified untouched stock rescue partitions, current carrier and
userdata identity, a safe rescue route, key-only SSH, capture readiness and
pstore handling, and stop conditions. Record the exact pair, baseline
signature, selector and all three file digests/modes, root mount and guard
state, and the outcome without disclosing private profiles, keys or device
data. No guard acceptance or WLAN pass is assumed.

That first boot cannot by itself prove a subsequent no-flash reboot, an
update **and** a rollback. #324 remains open until the coordinator separately
plans and measures those facts: an innocuous SSH edit persists across a reboot
with carrier hashes unchanged and no intervening partition flash; a signed
update and separately authorized rollback survive their required boot
transitions; and USB key-only SSH remains reachable after a reversible root
fault. Each additional boot or fault needs its own technical reason and
coordinator approval. Host fixtures, a successful signature check, or a
planned rescue are not physical passes.

The original userdata image was journal-free; the live filesystem's features,
final writable mode and behavior need measurement. Before any writable
transaction, propose a no-automatic-repair policy: inspect filesystem features
and clean/error state with verified RAM-side tools and an offline, read-only
check while unmounted when required; refuse dirty, journal-replay-needed,
damaged or ambiguous state pending a separately approved backup and recovery
plan. No `fsck -y`, journal replay, format or cleanup is authorized here.
Verify that this policy is compatible with the actual filesystem and with
interruption recovery before deployment; measure mount options and fsck/journal
behavior rather than inferring them from `ro,noload` or a host fixture. The
synthetic journal-fsck fixture above does not replace that measurement.

## Next single variable

Coordinator run 116 (2026-11-05, #324 comment 6654794020, recorded in
[records/2026-11-05-095841-run-116-unpinned-marker-survives-no-flash-reboot.md](../../records/2026-11-05-095841-run-116-unpinned-marker-survives-no-flash-reboot.md))
measured two of the acceptance facts below on the installed pair: the root
mounted `ext4 rw,relatime,norecovery` on `/dev/block/sda13` on both boots, and
one unpinned 98-byte file survived a no-flash reboot with an identical sha256.
The dossier fallback below (root stays read-only, or the marker does not
survive) did **not** trigger, so the migration design is not re-scoped. Still
unmeasured, and still caveats on that result: ext4 features, clean state,
error counters, journal behavior and fsck policy; the carrier hashes, which
were not re-read on the device because no admissible read-only reader exists;
durability beyond the one observed survival (the guest has no `sync` binary
and boot 1 ended in the guard's unclean bootloader return); USB SSH rescue
after a reversible root fault; and replacement of the hash pins. The signed
generation model gets no further redesign rounds from this result.

The exact owner public-key values are now recorded in
`configs/persistent-root-trust-anchors.json`, which closes the missing-keys
blocker named by the
[pair-deliverable proofs](../../records/2026-11-04-190612-pair-deliverable-host-proofs.md);
the replacement pair is still blocked on a bootstrap that does not exist yet.
Spending further boots and design rounds on a pair that cannot be built does
not move the check.

**Next single variable (coordinator-owned, separately authorized):** the
remainder of acceptance item 2 on the installed pair, unchanged: the `sda13`
ext4 features, clean state and error counters, captured with read-only tools
only (no `fsck -y`, no journal replay, no remount, no write), so a journal and
fsck policy can be stated from measurement instead of inference. Whether that
read can be made without a further boot, and which read-only tool exists on the
installed system, is the coordinator's call; nothing here names a tool or
authorizes a boot. A superblock read of a filesystem mounted read-write is an
observational snapshot only (see the runbook below). Any boot beyond run 116
needs its own technical reason and its own coordinator approval.

Run 116 against the original two-item variable:

1. Final root mount mode of `sda13`: **measured**, read-write
   (`rw,relatime,norecovery`). Filesystem features, clean state and error
   counters: **not measured**; this is the next single variable above.
2. One unpinned file outside the three pinned paths surviving a no-flash
   reboot: **measured once**, identical sha256. "Carrier hashes unchanged"
   was **not measured**, because no admissible read-only reader exists; it
   stays a caveat, not a pass, until one is named.

The two boots shared one technical reason and are spent. A single boot cannot
observe both marker creation and survival across a reboot, so the earlier
one-boot wording stays withdrawn. Run 116 is not the reversible-root-fault
rescue test and not an update/rollback test; those stay unmeasured.

### Guard-window measurement runbook (installed pair)

Draft only. Run 116 executed its marker and mount-mode parts (with the
process deviation and unread items in the run-116 record); the ext4 feature,
clean-state and error-counter reads and the carrier-hash re-read were not done.
This runbook authorizes nothing. The coordinator runs it, or does
not; no step here is a device action, a flash, a boot, or a command to execute
from this repository. Which tools exist on the installed system is **not
invented here**. The coordinator names the read-only tools actually present
before boot 1. If a required observation has no known read-only tool, stop.
Do not substitute a tool that writes.

**What may write.** The single intentional userdata write is marker creation
on boot 1 only: one new regular file, outside the three pinned paths, with no
other content change. Every inspection tool is read-only. No host radio action;
the installed guest's autonomous pre-ACK chain is not changed by this runbook.
No ACK. No remount. No `fsck`, no journal replay, no mount-option change, no
package install, no editor, and no shell redirection onto the device filesystem
except the single boot-1 marker write.

**Commands that implicitly write are not inspection.** Do not use a tool
because its name sounds read-only if invoking it replays a journal, updates
a superblock mount count or last-mount time, rewrites an inode, creates a
dotfile, or truncates a capture path on the phone. If that behavior is
uncertain for a candidate tool, do not use it. Host-side session logs are the
capture: the coordinator host records the session transcript. Do not write
logs, checksums or notes onto userdata, `/tmp` on the device, or pstore.

**Deadline.** The guard enforces a per-boot budget from arming:
armed uptime + budget defines the deadline on the device's `/proc/uptime`
clock. The installed pair arms with a 160-second budget
(`scripts/pmos-pid1-transition.sh` requests 160; `scripts/pmos-pid1-guard.sh`
rejects budgets outside 1..178). `/run/pid1-guard/armed` contains the boot ID,
not an arm timestamp, and the script truncates uptime with `awk int()` then
computes `deadline = floor(arm uptime) + 160`. A `/proc/uptime` read in a later session shows only the current uptime,
not the arm uptime: it provides a usable lower bound on remaining time only if a
defensible conservative lower bound for the same boot's arm uptime is available
(`remaining >= lower_bound_on_start + 160 - current_uptime`).
If no defensible same-boot lower bound is established, stop: absolute or
cross-image arm/uptime claims are not safe substitutes. The mere presence of
`/run/pid1-guard/armed` proves only that arming occurred at or before that file
was checked, not a lower bound on when arming started. Run 61 armed at a
measured kernel uptime near 155.4 seconds on a different image reaching
post-cutover PID 1; the installed run-113 pair ended around uptime 315 seconds
but this does not establish the same boot's arm timestamp, so no inspect
derived from those two numbers is a safe deadline for the physical session.
If uncertain, stop rather than infer. When armed and safe: leave before
`(lower_bound_on_start + 160) - margin`, with integer `margin >= 1` covering
teardown and coarseness, ensuring the session finishes while uptime is still
strictly below `start + 160`. If the deadline expires, the guard
attempts bootloader recovery, but that recovery is not guaranteed: it refuses
if the device identity or `/bin/restart2` helper checks fail, and it falls
through to sleep rather than forcing an untrusted reboot.

**Boot 1, in order, only if the previous step is unambiguous:**

1. Confirm the session is the installed pair (carrier identity as already
   pinned) and that the PID 1 guard is armed and not ACKed. Read
   `/proc/uptime` and establish, before any other step, whether a defensible
   conservative lower bound for this boot's guard arming time is available
   (same boot only). If it is not, stop; do not estimate from other boots or
   images. Otherwise compute `(lower bound on arm uptime) + 160` minus an
   integer margin of at least 1 second as the leave-by uptime, and start the
   host-side session log. A host log timestamp is not the guard's truncated
   `/proc/uptime` sample.
2. Record `sda13` mount mode (read-only or read-write) and the mount
   identity. Read-only observation only.
3. Record filesystem features, clean state and error counters by reading the
   superblock. See the observational limit below.
4. Record carrier hashes for `init_boot_a` and `vendor_boot_b` over the
   key-only session using a genuinely read-only method. The run-79 temporary
   BusyBox block-node read is **not** approved here: node creation is not
   purely read-only, and an earlier attempt reset its session. If no
   genuinely read-only carrier-hash method is available, stop; do not
   substitute a remembered digest and do not create device nodes.
5. Only then, and only on boot 1, create the one marker file outside the
   three pinned paths. Record its path, size and digest in the **host** log.
   Do not create it on boot 2. Do not touch the three pinned paths.
6. Leave the session before the guard deadline. No ACK.

**Boot 2**, reboot, no flash, same constraints, no marker creation:

1. Same session, timer and host log rules. No ACK, no radio, no remount.
2. Confirm the marker path, size and digest match the host log from boot 1.
   Absence or mismatch is the result; do not recreate the marker. Absence
   after the guard's unclean bootloader return is ambiguous: unclean-shutdown
   loss is not excluded, so it is not by itself proof of a non-persistent root.
3. Re-read mount mode, features, clean state and error counters.
4. Re-read carrier hashes with the same genuinely read-only method and
   compare to `d7bba454…` and `221bfd82…`; if none exists, stop.
5. Leave before the guard deadline.

**Superblock read while mounted read-write.** A raw read of the ext4
superblock on a filesystem that is mounted read-write is an observational
snapshot of bytes at one moment. It is not an offline integrity check and
not proof of a clean shutdown. Mount-count, timestamps and error fields can
change under a writer this runbook does not control, and a read does not
establish what a later unmount would commit. If the snapshot is inconsistent,
partial, or disagrees with the mount table, stop. Do not "fix" it, do not
unmount to re-read, and do not treat a matching clean flag as clearance for
a later transaction.

**Stop on uncertainty.** Any ambiguous tool, hash, mount mode, marker path
or deadline miss ends the run. Record the stop on the coordinator host. Do
not improvise a write, a remount, an ACK, or another boot. A guard expiry that
returns to the bootloader is an unclean end of the boot, not a substitute for
the coordinator-approved no-flash second boot, and it is not guaranteed (see
Deadline). Booting again may overwrite the first boot's ramoops, and the
recorded preboot pstore fetch was unsupported, so loss of boot-1 pstore is a
risk. The owner has since decided (2026-11-05, #324 comment 6653556220):
boot-1 pstore loss is accepted, boot-1 evidence is the marker plus the sda13
mount mode kept on the coordinator host, the guard deadline stays a technical
stop rule, and no userdata format/erase. Booting again may still overwrite the
first boot's ramoops, and the recorded preboot pstore fetch was unsupported;
that accepted risk is managed by keeping boot-1 evidence off-pstore.

## Budget and fallback

Host-side, the model now implements the separately keyed new-generation
rollback, and `test-pmos-pid1.sh` is rewritten to supply `success-ready` and an
ordered boot record on an isolated loop-backed ext4 root; it passes all six
cases on the host with the production scripts unchanged. The fixture's
post-cutover descriptor sweep reads `/proc/1/fd` once at the start of the
switched PID 1, after the pre-cutover Dropbear service is already running and
before OpenRC starts, skips links whose `readlink` fails, passes if nothing is listed, matches only
`/dev/loop*`, `/dev/block/sda13` and `/tmp/pmos-pid1.*` targets, and has not
been shown to fail under an injected post-cutover leak; only the pre-cutover
fd-9 assertion was negative-tested. That evidence is fixture-authored, so it
is not a device ACK. Still open: the deployable bootstrap reconciled with the
model. No image is built and no pair is flashed until the bootstrap exists and
is independently reviewed; the owner public-key values for the two
trust-anchor keys are now recorded, closing that blocker.

Fallback condition: if the final root stays read-only, or an unpinned file does
not survive a no-flash reboot, then persistent PC-style operation is not a
property of the installed system at all and the migration design alone cannot
deliver it: stop designing the replacement pair and re-scope #324 around the
measured mount and persistence behavior instead of assuming it. Run 116 saw a
read-write root and one surviving marker, so this condition did **not**
trigger. That is one marker and one reboot, not a durability proof.

Fallback for the privileged-writer problem is the phase separation above. Do
not spend another fixture round proving that locks, read-only bind mounts or
mount namespaces exclude root; the 2026-11-04 fixture already refutes all
three.

This strategy is not a new record or public support claim. Actual decisions
and measurements belong in new dated `records/` entries via `records.py`;
private capture and device data stay outside Git. Public support claims belong
only in `omnipha/ports` `devices/nothing-asteroids/device.yaml`.
