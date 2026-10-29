---
date: 2026-10-26
issue: omnipha/linux-sm7635#134
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Planned live-session WLAN handoff: scan through connectivity (#134, host-only, 2026-10-26)

**Host delivery only; no device result, no WLAN connectivity is claimed.** This
section prepares a reproducible **live-session** handoff for one bounded,
coordinator-owned session on the **unchanged** run-43 image
(`0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa`,
8,388,608 bytes). No image, source, kernel, config, module, timer or host key was
changed; nothing here flashes, boots, rebuilds an image or touches the phone. The
physical coordinator owns the authorized run and stock rollback under the recorded
standing `full_autonomy_device_iteration` approval; this host work claims no
physical acceptance. #134 stays `AWAITING_PHYSICAL_RESULT` until the coordinator
records the discriminating per-stage result **and** verified rollback (or a named
pre-flash gate refusal).

Dependencies #130 (physical run-46 finding) and #132 (host-only guest inventory)
are CLOSED and verified. #132 established that the unchanged run-43 guest has no
runnable nl80211 scan client and named the host-cached Alpine aarch64 bundle as
the smallest RAM-only delivery option; this section verifies that bundle on the
host and turns the option into a staged, separately-reportable session plan.

### What was verified on the host (not in the guest)

The host cache at `~/sm7635-build/wlan-tools/` was a **host-side source**, not a
claim that anything was on the guest when this plan landed. The facts below were
measured on this host; the subsequent guest scan result is recorded in the
run-47 finding above, not inferred from host QEMU.

1. **APK file hashes match the #132 pins.** `apk/iw-6.9-r0.apk`
   (`2a1664f4…`), `apk/libnl3-3.11.0-r0.apk` (`a5210a2d…`) and
   `apk/musl-1.2.5-r12.apk` (`f37e73d4…`) hash to the SHAs recorded in #132.
   The association path additionally uses `wpa_supplicant-2.10-r11.apk`
   (`43d104c4…`), `libcrypto3-3.3.7-r2.apk` (`2303cca1…`),
   `libssl3-3.3.7-r2.apk` (`d494a0a2…`), `dbus-libs-1.14.10-r4.apk`
   (`f4cd5427…`) and `pcsc-lite-libs-2.2.3-r1.apk` (`29f61fc6…`).
2. **Bundle files match their APK members byte-for-byte, and the ELF is
   self-contained.** `wlan-bundle-arm64.tar.gz`
   (`4acd05936bc7a785610da54b0f026263acfb4f04fce88e4ef5c3c60c385ad93d`,
   4,127,002 bytes) unpacks identical to `bundle/`. Every bundled file equals its
   APK member: `bin/iw` (`dab68988…`), `bin/wpa_supplicant` (`c570a688…`),
   `bin/wpa_cli` (`0e2d8013…`), `lib/libnl-3.so.200.26.0` (`32425f9e…`),
   `lib/libnl-genl-3.so.200.26.0` (`7cd51e40…`), `lib/ld-musl-aarch64.so.1`
   (`a965363d…`), `lib/libcrypto.so.3` (`c7ca672c…`), `lib/libssl.so.3`
   (`2ef41af2…`), `lib/libdbus-1.so.3.32.4` (`08386d98…`),
   `lib/libpcsclite.so.1` (`dd5c96a1…`); SONAME links
   `libnl-3.so.200`, `libnl-genl-3.so.200`, `libdbus-1.so.3` are relative and
   resolve inside `lib/`. `readelf -l` reports interpreter
   `/lib/ld-musl-aarch64.so.1` for all three programs; `readelf -d` shows `iw`
   needs only `libnl-genl-3.so.200`, `libnl-3.so.200` and
   `libc.musl-aarch64.so.1`, and `wpa_supplicant` additionally needs
   `libpcsclite.so.1`, `libssl.so.3`, `libcrypto.so.3` and `libdbus-1.so.3`.
3. **Host QEMU smoke loads pass, and prove loading only.** Invoking each program
   through the **bundled** loader (no host `/lib` mutation) under `qemu-aarch64`:

   ```sh
   B="$HOME/sm7635-build/wlan-tools/bundle"
   qemu-aarch64 "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/iw" --version            # iw version 6.9 (exit 0)
   qemu-aarch64 "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/wpa_supplicant" -v        # wpa_supplicant v2.10 (exit 0)
   qemu-aarch64 "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/iw" help                 # full command set (exit 0)
   ```

   `iw phy` and `iw dev` return `Failed to connect to generic netlink.` (exit 1)
   on this host, which has no nl80211 socket: that is the **expected host** result
   and is **not** a guest scan. **These are host executions; they did not predict
   whether the guest driver serves a scan, association or DHCP.** The subsequent
   run-47 guest scan is recorded above; association and DHCP remain unmeasured.

### DHCP tooling inventory (guest, no profile accessed)

Read-only parse of the **unchanged** run-43 cpio (`0f998e29…`) via
`scripts/vendor-module-closure.py`, then host-QEMU `--help` on the extracted
BusyBox (`c2f279d1…`) applets — no WLAN profile read:

- The guest BusyBox **provides** the applets `udhcpc`, `udhcpc6`, `ip`, `route`,
  `ipcalc`, `nslookup`, `ping`, `ping6`, `wget`, `awk`, `sha256sum`, `tar`,
  `gzip`, `timeout` and `sh` (276 applets total, none of them `iw`/`wpa_*`). The
  run-43 cpio creates only 10 `/bin` symlinks (`sh`, `ip`, `mkdir`, `mknod`,
  `mount`, `ln`, `sleep`, `hostname`, `cttyhack`, `setsid`, plus `/sbin/init`), so
  other applets must be called as `/bin/busybox <applet>` (e.g.
  `/bin/busybox udhcpc`, `/bin/busybox ping`).
- **Gap:** the run-43 cpio ships **no** `/etc/udhcpc/default.script`, so a bare
  `/bin/busybox udhcpc` obtains a lease but cannot apply it (no address/route/DNS
  write). This handoff supplies a minimal, dependency-free lease script,
  `scripts/wlan-udhcpc-lease.sh`, that uses only the guest's own `ipcalc`, `printf`
   and `/bin/ip`; it is transferred into guest RAM and passed to `udhcpc -s`.
   Reachability then uses the guest's own `/bin/ip route`, `/bin/busybox ipcalc -p`
   (prefix derivation), `/bin/busybox ping -c` and `/bin/busybox nslookup`.
   `dhclient`/`dhcpcd` are **not** present on the guest and are not required.
- **Host check of the lease script (loading/logic only, no host network write).**
  Run under host QEMU with the busybox extracted from the **unchanged** run-43 cpio
  (`c2f279d1…`), a fake `ip` that only logs its argv, and a temporary
  `RESOLV_CONF` (no real interface or resolver touched), the `bound` event with
  `ip=192.0.2.5 subnet=255.255.255.0 router=192.0.2.1` produced exactly
  `ip addr flush dev wlan0`, `ip addr add 192.0.2.5/24 dev wlan0`,
  `ip route replace default via 192.0.2.1 dev wlan0` and a two-line
  `nameserver` resolver; `deconfig` flushed only, and a wrong interface or unknown
  verb exited 1. This proves the guest-applet logic, **not** a live lease on the
  device.

### Coordinator-owned live-session plan (one bounded session)

The coordinator rechecks the device-op reuse decision, exact candidate
hash/size, verified stock backups, five-partition stock baseline, targeted
fastboot gate and rollback capability **at the time of use**; the SHA above is a
snapshot, not permission to bypass a changed live gate, and all older refused
images stay refused. If any preboot check refuses the SHA or finds changed state,
stop **before** flash, record the concrete gate failure and route back to
strategist. The preboot listener/known-hosts/route/selftest/`/run/keep` order is
the unchanged #113/#120 handoff with the pinned `[172.16.42.2]:22 ssh-ed25519 …`
key from #120; the single guarded remoteproc2 start and one `/bin/wpss-once`
(exit 0, node precheck, one 25 s ON hold, one `wpss_boot=1`) reproduce the run-46
prerequisite **once**. Per-stage findings stay separately reportable; **no
inferred connectivity**.

1. **Preboot fail-closed readiness (no secret printed).** Before any reboot,
   confirm on the host and record a PASS/FAIL each: (i) `wlan-bundle-arm64.tar.gz`
   present and its SHA-256 equals `4acd0593…` and the APK/file hashes above still
   match; (ii) the protected host-local WLAN profile — a private build input at a
   `0600` host path known to the coordinator, **not** committed and **not** named in
   this public doc — exists and is *structurally* valid: it parses and has one
   `network={…}` block with `ssid`, `psk`/`key_mgmt` and a `ctrl_interface`,
   checked **without printing contents, SSID, BSSID, key or the path**; (iii)
   `scripts/wlan-udhcpc-lease.sh` exists and hashes to
   `86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896`
   (no outside DHCP binary or script needed). Do **not** assume the profile is
   already on the phone. Any FAIL stops before flash and names the gap.
2. **Root-only RAM transfer over the coordinator-verified pinned-key session.**
   After key-only SSH and a fresh capture selftest for **this** boot, stream the
   SHA-checked bundle into guest RAM (no persistent install, no `/lib` or
   `/vendor` write, no image rebuild):

   ```sh
   # host -> guest over the pinned key-only SSH; /run is a directory on the
   # RAM-backed initramfs rootfs in this init (not a separate tmpfs, not persistent)
   sha256sum "$HOME/sm7635-build/wlan-tools/wlan-bundle-arm64.tar.gz"   # must be 4acd0593…
   cat "$HOME/sm7635-build/wlan-tools/wlan-bundle-arm64.tar.gz" \
     | ssh <pinned-key opts> root@172.16.42.2 \
       'umask 077; /bin/mkdir -p /run/wlan-tools && \
        /bin/busybox cat > /run/wlan-tools/bundle.tar.gz && \
        /bin/busybox printf "%s  %s\n" \
          4acd05936bc7a785610da54b0f026263acfb4f04fce88e4ef5c3c60c385ad93d \
          /run/wlan-tools/bundle.tar.gz | /bin/busybox sha256sum -c - && \
        /bin/busybox tar -xzf /run/wlan-tools/bundle.tar.gz -C /run/wlan-tools && \
        /bin/busybox chmod -R go-rwx /run/wlan-tools'
   cat scripts/wlan-udhcpc-lease.sh \
     | ssh <pinned-key opts> root@172.16.42.2 \
       'umask 077; /bin/busybox cat > /run/wlan-tools/udhcpc.script && \
        /bin/busybox printf "%s  %s\n" \
          86ebff20670faaa066685b1674f085a5e391676788a45a671f32a2c214fe3896 \
          /run/wlan-tools/udhcpc.script | /bin/busybox sha256sum -c - && \
        /bin/busybox chmod 700 /run/wlan-tools/udhcpc.script'
   ```

   Only `/bin/sh`, `/bin/ip`, `/bin/mkdir` and seven other names have `/bin`
   symlinks in the run-43 cpio, so `cat`/`tar`/`sha256sum`/`chmod` are invoked as
   `/bin/busybox <applet>` above. The guest verifies the streamed tar's SHA-256
   equals `4acd0593…` and the lease script's equals `86ebff20…` before use (fail
   closed on either mismatch).

   **Stage: client load / phy.** In the guest, load through the bundled loader and
   identify the phy — this is the first *guest* measurement and is reported on its
   own:

   ```sh
   B=/run/wlan-tools
   "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/iw" --version   # expect iw version 6.9
   "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/iw" phy         # expect a phy for wlan0
   "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/iw" dev         # expect wlan0 present
   ```

   Record whether the client **loads in the guest** and reports a phy for `wlan0`.
   If it does not load or reports no phy, stop with that named gap; do not scan.
3. **Stage: scan (20-second-bounded).** Only if the guest `iw` reported a phy,
   record a pre-scan kmsg offset and read-only `wlan0` flags/operstate, then issue
   exactly one bounded scan with capture preserved. **Run-47 measured precondition:
   `wlan0` must have `IFF_UP` set before the scan** — flags must include the `0x1`
   bit (`0x1003`/`0x1043`…), not merely `0x1002`. A scan on an administratively
   down interface returns exit 156 `command failed: Network is down (-100)`; that
   is `-ENETDOWN`, a user-space ordering bug, **not** a driver/phy fault. If flags
   lack `0x1`, issue a single `ip link set wlan0 up` (exit 0 expected;
   operstate staying `down` is normal pre-association) before the scan:

   ```sh
   /bin/ip link set wlan0 up
   /bin/busybox timeout -k 1 20 /run/wlan-tools/lib/ld-musl-aarch64.so.1 \
     --library-path /run/wlan-tools/lib /run/wlan-tools/bin/iw dev wlan0 scan 2>&1
   ```

   Preserve exit, stdout and stderr. Report **separately**: (a) target found with
   `wlan0` still registered and no new fatal/crash/idle line — run 47 measured
   exit 0 with 17 BSS; (b) the named scan/driver error (including timeout 124 /
   kill 137, nl80211 unsupported, no target); (c) `wlan0` vanished or a new
   fatal/crash/`hdd_psoc_idle_timeout_callback` line — stop immediately. Summarize
   BSSID/frequency lines **without publishing private identifiers**. A successful
   scan is **not** connectivity and does **not** itself trigger rollback.
4. **Stage: association (only if scan succeeded and interface/capture are
   healthy).** Provision the protected host-local profile into guest RAM over the
   pinned key-only SSH **without logging its contents, SSID or key**, then start
   `wpa_supplicant` with bounded observation and inspect association:

   ```sh
   PROFILE=<coordinator-private-host-path>
   cat "$PROFILE" \
     | ssh <pinned-key opts> root@172.16.42.2 \
       'umask 077; /bin/busybox cat > /run/wpa_supplicant.conf && \
        /bin/busybox chmod 600 /run/wpa_supplicant.conf'
   # guest: bound the startup, not the lifetime; -B keeps ONE RAM-only
   # supplicant running through DHCP. Never use -K (logs key material).
   B=/run/wlan-tools
   /bin/mkdir -p /run/wlan-wpa-ctrl
   umask 077
   /bin/busybox chmod 700 /run/wlan-wpa-ctrl
   /bin/busybox timeout -k 2 10 "$B/lib/ld-musl-aarch64.so.1" \
     --library-path "$B/lib" "$B/bin/wpa_supplicant" -B -q -i wlan0 \
     -c /run/wpa_supplicant.conf -D nl80211 -O /run/wlan-wpa-ctrl \
     -P /run/wlan-wpa.pid > /run/wlan-wpa-start.log 2>&1
   # bound observation only; the daemon must survive this poll for DHCP
   /bin/busybox timeout -k 2 30 /bin/sh -c '
     B=/run/wlan-tools
     n=0
     while [ "$n" -lt 15 ]; do
       if "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" \
            "$B/bin/wpa_cli" -p /run/wlan-wpa-ctrl -i wlan0 status \
            | /bin/busybox grep -q "^wpa_state=COMPLETED$"; then exit 0; fi
       /bin/sleep 2; n=$((n+1))
     done
     exit 1'
   # report only the boolean state and link summary; never print raw status
   # (wpa_cli status exposes SSID/BSSID) or the RAM log
   "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" \
     "$B/bin/wpa_cli" -p /run/wlan-wpa-ctrl -i wlan0 status \
     | /bin/busybox grep -c "^wpa_state=COMPLETED$"
   "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" "$B/bin/iw" dev wlan0 link
   ```

   Keep the single RAM-only supplicant running through the address and
   reachability stages; a foreground `timeout` that killed it would drop the
   association and invalidate DHCP. `-O` overrides the profile's `ctrl_interface`
   into `/run`, and teardown uses the ctrl socket (`wpa_cli … terminate`), not the
   `-P` pidfile (whose write cannot be observed on the host because nl80211 init
   fails there). Require
   `wpa_state=COMPLETED` **and** a connected `iw dev wlan0 link`; if they disagree,
   report a named association gap. Report association as its own outcome
   (`associated` / named error / timeout). An associated link **without** an address
   or network access is a distinct outcome, not connectivity. If association fails
   while USB SSH stays healthy, inspect the private RAM log/error and iterate
   safely in the **same** session; do not burn a new boot on an easily corrected
   user-space dependency, and do not print the profile, log or status.
5. **Stage: address (only if associated).** Acquire an address with the guest's own
   `udhcpc` and the hash-checked transferred lease script, bounded and once, then
   read it back:

   ```sh
   /bin/busybox timeout -k 2 25 /bin/busybox udhcpc -i wlan0 -q -n -t 5 -T 3 -A 5 \
     -s /run/wlan-tools/udhcpc.script 2>&1
   /bin/ip addr show dev wlan0 ; /bin/ip route ; /bin/busybox cat /etc/resolv.conf
   ```

   Report `lease obtained` / named error / timeout separately. No address means no
   reachability stage.
6. **Stage: reachability (only if an address was obtained).** Test gateway, DNS and
   one external network path, each bounded, and report each separately:

   ```sh
   /bin/busybox timeout -k 1 8 /bin/busybox ping -c 3 -W 2 <gateway>          # gateway
   /bin/busybox timeout -k 1 8 /bin/busybox nslookup <one-resolvable-host>     # DNS
   /bin/busybox timeout -k 1 8 /bin/busybox ping -c 3 -W 2 <one-network-host>  # network
   ```

   Only a measured association **and** address **and** reachability together
   establish WLAN working; keep gateway/DNS/network results distinct. Mark WLAN
   working only on that full measured chain, and do not close the mission epic from
   it. Keep SSIDs/BSSIDs, credentials, raw logs and private paths out of public
   reports.
7. **Stop rules and session close.** Stop risky actions and preserve evidence on
   interface loss, a new fatal/crash/idle-timeout line, lost capture, lost SSH or
   an unverified precondition; report the stage that failed rather than inferring a
   later success. A kernel hang before the userspace timer is reported separately
   (the 150 s timer cannot recover it). Before leaving the session, terminate the
   transferred supplicant and leave nothing private in RAM:

   ```sh
   B=/run/wlan-tools
   /bin/busybox timeout -k 2 10 "$B/lib/ld-musl-aarch64.so.1" --library-path "$B/lib" \
     "$B/bin/wpa_cli" -p /run/wlan-wpa-ctrl -i wlan0 terminate || true
   /bin/busybox rm -f /run/wpa_supplicant.conf /run/wlan-wpa-start.log /run/wlan-wpa.log
   /bin/busybox rm -rf /run/wlan-tools /run/wlan-wpa-ctrl
   ```

   After the worker lands the full finding or a measured blocker, the coordinator
   recovers to fastboot via the guarded session path, preserves host-only
   evidence/pstore **before** Android, restores stock `init_boot_a` and proves all
   five stock hashes plus stock boot. The coordinator alone closes the device
   session, owns rollback, and records the discriminating result; the issue does
   not close on this host PR.

`scripts/verify-run44-session-plan.py` still gates the synthetic preboot
listener/pinned-key, post-enumeration route, capture selftest, `/run/keep` before
150 s, single guarded modem/WPSS prerequisite, bounded action and stock-rollback
order that this session reuses unchanged; it does not model the transferred
client, scan, association, address or reachability stages, which are coordinator-
measured live, not synthetic. `scripts/test-wlan-udhcpc-lease.sh` is a separate
synthetic host-only test for the supplied DHCP lease helper: it runs
`scripts/wlan-udhcpc-lease.sh` under host QEMU using the BusyBox extracted from
the **unchanged** run-43 cpio, with a fake `ip` that only logs argv and a
temporary resolver file, and proves the `bound`/`deconfig`/wrong-interface/
unknown-verb branches — it touches no interface, resolver, profile or device and
claims no live lease. Run both, plus `git diff --check`, for these host-only
changes. No cached-tooling gap was found: the bundle, its APK members, the ELF
dependency closure and the DHCP lease helper are all host-verified. The one
honest limit was that host QEMU proves **loading and script logic only**. Run 47
(above) has since measured a guest nl80211 scan success; association, address and
reachability remain coordinator-owned and unmeasured.
