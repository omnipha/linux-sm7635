---
date: 2026-11-02
issue: omnipha/linux-sm7635#284
subsystem: wlan
result: confirmed
---
# Host-only #284: the services stage becomes persistent-root-aware as a separate pinned variant; the installed script and image pins stay byte-identical

Host-only follow-up to run 98 (#280): the `services` stage refused its own
persisted output on the persistent root (conf.d pristine hash, runlevel
inventory, no-overwrite). No device, no image build, no flash; issue #284 only.

## Change

`scripts/pmos-radio-bringup-persistent.sh` (sha256 `58476d77…`) is the
persistent-root-aware variant, reproduced exactly by the new fail-closed
derivation `scripts/derive-radio-persistent.py` (four services-stage blocks,
each matched exactly once; nonce interlock, capture gate, guard checks and all
pins untouched — `test-derive-radio-persistent.py`). The pinned `scripts/pmos-radio-bringup.sh`
(`7ef63826…`, staged on the installed chain as `f54b3372…`) stays
byte-identical, so `build-init-boot-persistent-root.py`,
`verify-init-boot-persistent-root.py`, `pmos-self-post.sh`, `pmos-self-stage.sh`
and the installed `vendor_boot_b a71b3f5f` carrier all keep working unchanged.
Deployment of the variant onto the phone stays host-run (an acked live session
like run 98) until the self-starting chain exists; it must not be flashed. For
the installed chain the same derivation applies to the builder-patched staged
script (`f54b3372…`, `LEASE_SHA=1fbf50af…`, persistent prepare behavior), yielding
`c54c29e1278827bc00faaf506c7ff8e923a8a689a011a2852d5d4b7778d0188d`; `derive-radio-postack.py` composes with both (acked-session guard +
capture gate).

Inside the `services` stage of the variant:

- The exact bytes the stage writes are factored into `emit_*` functions;
  `own_digest` computes the expected sha256 of each output from the emitters.
- conf.d: pristine archive hash or the stage's own exact output
  (`wpa_supplicant_args=""` + `wpa_supplicant_if="wlan0"`), root-owned, mode
  600/644; anything else still refuses with the run-98 message
  `unexpected supplicant arguments; no -f supported`.
- Inputs (`/etc/network/interfaces`, conf.d files, `/bin/run-parts`,
  `/sbin/udhcpc`, the two `$STATE` helpers): absent (pristine archive) or the
  stage's own output verified by mode, owner and own digest; anything else
  refuses `service input already exists …`. Persisted WLAN profile: root-only
  file whose digest equals this run's stdin; a differing profile refuses
  (`persisted WLAN profile differs from standard input; no silent overwrite`)
  — no overwrite of a foreign or stale profile, ever.
- Runlevel inventory: own entries `/etc/runlevels/default/{local,
  wpa_supplicant, networking}` linking to `/etc/init.d/<same name>`; any other
  entry still refuses `another OpenRC service enabled`. Already-running
  `wpa_supplicant`/`networking` are accepted only when their own runlevel
  entries exist (self-starting direction); running-but-not-enabled still
  refuses `unexpected OpenRC service state`.
- `install_service_config` is idempotent: files with identical content are
  rewritten, symlinks created only when absent; per-boot `services.attempted`
  still refuses a same-boot retry (`services already attempted this boot; no
  retry`).
- Nonce interlock, capture gate, guard checks, service/init.d/lease-helper
  pins, kmsg fatal scan, `:2222` health check, root-only config checks: all
  unchanged. The lease helper (`LEASE_SHA`) stays pinned.

## Fixtures (all pass, host-only)

`test-pmos-radio-bringup.sh` now runs the full existing suite against BOTH
variants (installed first, then the persistent variant). The persistent block
adds: own-output replay passes (fresh boot state, services.attempted removed);
already-started own services replay passes; foreign `wpa_supplicant_if="wlan1"`
refuses; wrong conf.d mode refuses; foreign runlevel entry, modified own
runlevel target, started-but-not-enabled service refuse; modified lease helper
refuses at the pin; modified `/etc/network/interfaces` refuses; foreign
`/bin/run-parts` link refuses; differing persisted profile refuses without
overwrite; same-boot retry refuses. `test-derive-radio-postack.py` derives both
variants (guard + capture gate only); `test-pmos-session-dev.sh --stage-only`
installs the variant's emitters in the real OpenRC guest. Additionally
re-verified green on this host: `test-pmos-self-stage.sh`, `test-pmos-boot-record.sh`,
`test-pmos-root-contract.sh`, `test-wlan-udhcpc-lease.sh`, and
`build-init-boot-persistent-root.py::current_scripts()` still yields the
installed `f54b3372` radio.

Known gap: `/etc/network/interfaces` and conf.d point at `/run` (tmpfs)
helpers; on the next boot OpenRC's `networking` start needs the stage (or a
self-post variant) to recreate `$STATE/ifquery-wlan` and `lease-wrapper.sh`
before `ifup`. That ordering is exactly the next single variable.

## Lease helper `:22` listener: not established as deliberate

Run 98 observed the networking lease helper starting a key-only dropbear on the
WLAN address `:22`. The staged helper on the installed chain is the run-66
bundle member (sha256 `1fbf50af…`, pinned `RUN66_LEASE` in
`build-init-boot-persistent-root.py`), not the repo's
`scripts/wlan-udhcpc-lease.sh` (`86ebff…`, without any dropbear line). The
three-line `bound|renew` addition (`/usr/sbin/dropbear -s -g -j -k -E -r
/etc/dropbear/session_host_key -p "$ip:22" -P /run/dropbear-wlan.pid || true`)
was never committed: it first appears in the pinned image bundle, and
records/2026-10-30-102155 flags the identical working-tree change as a foreign
regression that broke session teardown. No issue, record or commit authorizes
it. Verdict: deliberate-or-not cannot be established from the evidence — treat
the listener as an unowned, undocumented part of the run-66 bundle; it re-arms on
every lease and is not owned by `pmos-session-teardown.sh`. The follow-up
question is whether to pin a lease helper without the dropbear block.

## Next single variable

A live acked session proving the persistent variant's `services` stage on the
installed chain (run-98 recipe, post-ack derivation of this variant), then the
self-starting chain: who recreates the `/run` helpers and starts OpenRC on a
fresh boot — the natural candidate is a persistent-root self-post stage between
the guard ack and OpenRC `networking`.

Not WLAN acceptance; no image built; no device touched.
