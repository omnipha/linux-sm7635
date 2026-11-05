---
date: 2026-11-05
issue: linux-sm7635#324
subsystem: userspace
result: inconclusive
---
# run 116 record correction two wording flaws

This corrects wording in
`records/2026-11-05-095841-run-116-unpinned-marker-survives-no-flash-reboot.md`
(merged in PR #334, `9ff5a2026a4deed743fe71d82e205678951a294f`). Records are
immutable, so that file is left unchanged and this record supersedes the
wrong cross-reference and the two flawed wordings below. Nothing else in it
changes. Re-read source: only the pinned
coordinator comment
https://github.com/omnipha/linux-sm7635/issues/324#issuecomment-6654794020
(2026-11-05 09:45 UTC), re-fetched for this record. No other device-evidence
source was used, and no device action was taken.

## Wording only; measured numbers unchanged

Unchanged from the earlier record, all as stated in comment 6654794020:
marker sha256
`136b5c5122e750138e5fa420dda2b0e23233b6c0a3b0dcf2d96ae741b28d2420`,
98 bytes, path `/root/.omnipha-persist-marker`; boot 1
`e3af385f-1117-4dd6-8435-252c34929847`, boot 2
`58c40d9a-2552-48f8-9063-94edca098482`; root
`/dev/block/sda13 / ext4 rw,relatime,norecovery` on both boots; installed pair
`d7bba454…` / `221bfd82…`, reported unchanged, not re-read on the device.

## Flaw 1: cross-reference to a section that does not exist

The earlier record's "Installed artifacts" bullet says the carrier hashes
"were not re-read on the device during run 116 (see Not measured)". There is
no "Not measured" section in that record. The statement it points at lives in
the "Caveats stated by the coordinator, not claimed here" section: the comment
says the carrier hashes were not re-read on the device because no admissible
read-only reader exists.

## Flaw 2: guard and nonce wording not checkable against the comment

The earlier record's acceptance item 5 says the comment "reports no re-read
of the three pinned userland files, guard or nonce state, or the altered radio
file". The comment lists no re-read of any of these. As worded, the sentence
can be read as a denial that a re-read happened, and the comment cannot be
checked for that: it is silent on these items. Correct sense, for the whole
listed set including guard and nonce state: the comment does not report any
such re-read, on the device or otherwise. This correction does not claim that
a re-read happened, and it does not claim that none happened. The pending
handoff for acceptance item 5 is not satisfied by it.

## Flaw 3: non-write claim beyond the comment

The same item 5 says the comment reports "no write outside the marker". The
comment does not say that. Its exact text for run 116 is "No flash, erase,
ACK, radio action, mknod, partition hash, stock restore or Android", plus the
single marker write described in its boot 1 entry. That does not establish the
absence of every other write outside the marker path.

## Restated acceptance item 5, bounded to the comment

From comment 6654794020 only: no flash, no erase, and one 98-byte marker write
(`/root/.omnipha-persist-marker`, one pinned SSH call on boot 1). The comment
also reports targeted fastboot identity exact at both guard returns. Anything
else about other writes, re-reads of the pinned userland files, guard or nonce
state, the altered radio file, or other envelope state is only "not reported
by the comment". Item 5 stays unmeasured.

## What this correction does not change

No acceptance status is flipped. These stay as the earlier record and the
dossier have them: acceptance 1 partial, acceptance 2 with the rw mount
observed and the journal/fsck policy not measured, rescue under an induced
root fault unmeasured, replacement of the hash pins unmeasured, and the
envelope re-read unmeasured. Nothing here adds to or reinterprets the owner
key decision or the accepted boot-1 pstore loss (#324 comment 6653556220).
`docs/strategy/persistent-root.md`, `status.yaml` and the host guards are not
touched. The installed pair stays untouched and never-reflash, and no
replacement pair is built.
