---
date: 2026-10-26
issue: omnipha/linux-sm7635#120
subsystem: boot
result: inconclusive
source: README.md
---
## Pinned Dropbear host key for the preboot capture handoff (2026-10-26, #120)

`scripts/build-init-boot-psoc-hold-capture-hostkey.sh` packages a protected
Dropbear ed25519 private key (default input
`$HOME/.omnipha/sm7635/dropbear_ed25519_host_key`, mode `0400`, never in Git)
with the unflashed #116 session init, replacing the RAM-generated `dropbear -R`
key with `dropbear -r /etc/dropbear/dropbear_ed25519_host_key`. The public key
and the `[172.16.42.2]:22` known-hosts line are pinned in [BOOT.md](BOOT.md) and
printed by the verifier before reboot. The key file is mode `0600` in the cpio;
the single 25 s-capped `/dev/wlan` ON hold and the one-shot WPSS trigger, 150 s
timer and `/run/keep` semantics are byte-exact #109. The builder requires two
serial byte-identical builds, and `scripts/verify-bootimg.sh` checks the pinned
public key, exact cpio delta, committed-private-key rejection, -R regression,
missing/unpinned key, timer and keep regressions, and distinct SHA including the
unflashed `7c3d915f…` candidate. This is host-only; #116 owns the single
physical rerun with the new SHA and unchanged outcomes (a)/(b)/(c)/(d) and
one-attempt stop rule. Never reflash `7c3d915f…`, `0b40ac34…` or any earlier
measured SHA.
