---
date: 2026-10-27
issue: omnipha/linux-sm7635#139
subsystem: userspace
result: inconclusive
source: README.md
---
## Reproducible postmarketOS RAM userspace for a held stock-kernel session (#139, host-only, 2026-10-27)

[BOOT.md](BOOT.md#reproducible-postmarketos-userspace-for-a-held-stock-kernel-usb-session-139-host-only-2026-10-27)
prepares a RAM-only postmarketOS v24.12 / Alpine v3.21 aarch64 userspace for one
coordinator-held stock-kernel USB-SSH session. `scripts/build-alpine-session.py`
installs the real `postmarketos-base=38-r3` closure — **134** hash-pinned APKs
locked in `scripts/alpine-session-packages.lock` — from three signed APKINDEX
archives with `apk.static --initdb --no-scripts --no-network`, never executing
package scripts. It verifies per-APK SHA-256/index size, 390 aarch64 ELF/musl
closure entries, and packs a byte-reproducible 23,713,302-byte transport
(`7a76a110…`), root password locked, no key/firmware/profile/credential staged.
`scripts/test-alpine-session.sh` fails closed on duplicate/missing/corrupt
inputs, an incomplete lock, wrong-arch ELF and missing libs, and runs a chroot
smoke of `/bin/sh`, `apk`, `iw`, `wpa_supplicant` and Dropbear from the produced
tarball under QEMU+bwrap. The builder's own `apk add` of the frozen set is the
dependency gate (it exits non-zero if any provider is absent). A separate manual
host loopback chroot proved a real key-only Dropbear shell into that postmarketOS
userland with an independent kernel/userland identity (synthetic keys, torn down
afterward); that is host mechanics, not the phone. `scripts/pmos-session-stage.sh` / `-teardown.sh` stage and remove it
reversibly under guest RAM, keeping the diagnostic PID 1, gadget and pinned
`:22` SSH intact and starting a **second** key-only Dropbear on `:2222`. This is
host preparation, not a phone result, image, own-kernel test, persistence path or
release; the coordinator owns the live session and stock rollback.
