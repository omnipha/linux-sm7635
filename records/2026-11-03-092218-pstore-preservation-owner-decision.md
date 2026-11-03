---
date: 2026-11-03
issue: omnipha/linux-sm7635#301
subsystem: wlan
result: confirmed
---
# Run-100 pstore preservation decision

The [owner decision in #294](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6598398647)
explicitly accepted possible loss of uncopied run-100 pstore and lifted the
specific preservation hold recorded in the
[run-101 preboot blocker](2026-11-03-023259-run101-preboot-pstore-access-blocker.md).
The [coordinator independently confirmed that decision](https://github.com/omnipha/linux-sm7635/issues/294#issuecomment-6598721435)
and specified that the retained #294 worker context should receive a newly
proven capture/SSH handoff after #301 completes. This records the decision and
review, not a new device measurement or a worker handoff.

The existing host console is not a pstore pull; no post-run-100 pstore capture
is established. The run-100 cause remains unproven, and #294 still requires
physical diagnostic and WLAN acceptance. No device operation or deployment was
performed in #301. The owner decision supersedes the hold, not the historical
fact that the hold was in force when run 101 was assessed.
