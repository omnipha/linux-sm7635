# AGENTS.md — omnipha/linux-sm7635

Purpose: source tracking for the Qualcomm SM7635 (`volcano`) kernel used by
Omnipha. The first target device is the Nothing Phone (3a) Pro (`asteroids`,
A059P, fleet unit `mb003`).

## What this repo is

A tracking repo, **not** a kernel tree. `main` contains documentation, build
scripts and the pinned upstream reference only. See README.md "Source policy"
and UPSTREAM.md.

## How agents contribute

- Work happens through the mission shift documented in
  [omnipha/agents/docs/mission-shifts.md](https://github.com/omnipha/agents/blob/main/docs/mission-shifts.md)
  (epic omnipha/ports#3, shift `sm7635`). The org-wide issue selector never
  selects this repo.
- One issue per fresh model context, PR-based delivery, sign commits as
  `Gregor Sprint <gregor@sprintcx.de>` unless told otherwise. English commits.
- Build scripts and documentation land here as PRs against `main`. Kernel
  patches themselves do not: while there are none, packages reference the
  pinned vendor commit (NothingOSS/android_kernel_msm-6.1_nothing_sm7635).
  If a tested patch becomes necessary, prefer a small patch stack in
  omnipha/ports first; an `omnipha` branch in this repo is the last resort.

## Hard rules

- Never commit kernel trees, firmware blobs, partition dumps, serials,
  credentials or private device data.
- Device reference data lives only under `~/phone-second-life-data/mb003` on
  the build host; read-only, never committed.
- Build artifacts (`Image`, DTBs, logs) stay outside this repo.
- No flashing, booting or writing to the physical phone from repo work.
  Physical device work is human-gated in the mission shift state.
- One build at a time on a host; see README.md build instructions.
