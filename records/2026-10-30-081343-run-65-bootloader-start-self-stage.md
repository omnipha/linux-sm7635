---
date: 2026-10-30
run: 65
issue: omnipha/linux-sm7635#191
subsystem: boot
result: confirmed
---
# Run 65: bootloader-start self-stage on the installed run-64 chain (#191)

**Measured physical result — a fresh bootloader start of the already-installed run-64 chain reaches postmarketOS PID 1 and self-stages from read-only `userdata` with no host archive push and no partition write.** The physical coordinator started the installed `init_boot_a` `fcb0ed91…` / `userdata` `ea09444c…` pair from the verified fastboot state, armed the host reboot-hold and proved the handoff (`handoff: ok`, marker `linux191_handoff_1793347310_19086`). The worker independently rechecked boot ID `3fa41974-d20b-4ea7-9e49-ec4d70b54584`, pinned key-only SSH on `:2222` (fingerprint `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`), `session-capture.py check` (`ready: true`, same boot) and a fresh console-marker selftest (`ok: true`, 0.44 s). Root-only `/run/keep` was `0:600`, PID 1 was guest BusyBox on a tmpfs root and the host-owned guard ack was already accepted for this boot. No image, partition write, reflash or reboot was performed by the worker.

| stage | measured result |
| --- | --- |
| bootloader start | one normal start of the installed chain from fastboot; no flash, erase or format; slot-A rescue, slot B, `vbmeta_*`, `dtbo_*` and `super` untouched |
| diagnostic hold and `:22` | kmsg: `pmos-self-stage: diagnostic hold and :22 verified on boot 3fa41974…` |
| read-only `userdata` and archive | `EXT4-fs (sda13): mounted filesystem without journal`, unmounted, `copied userspace archive from read-only /dev/block/sda13 (sda13) and verified SHA-256`; no host push |
| self-stage and PID 1 | staged postmarketOS root and armed the PID-1 request; `switch_root` executed; post-cutover PID 1 on tmpfs, OpenRC `softlevel=default`, `local` started |
| guard ack | `pmos-self-post: host-owned guard ack accepted on boot 3fa41974…`; `/run/pid1-guard/accepted` equals the boot ID |
| modem / WPSS / `wlan0` | `remoteproc2` and `remoteproc3` `running`; `wlan0` and phy present; each stage preceded by a fresh capture marker |
| scan | bounded scan exit 0, **37 BSS** (scan is not connectivity) |

## WLAN (separate from the boot result)

| stage | measured result |
| --- | --- |
| target visibility | the designated network was visible: **1 match** in the 37-BSS guest scan and **2 matches** on a fresh host-radio rescan (counts only) |
| first OpenRC start | `wpa_supplicant` service `started`, but the pre-baked profile's target had **0 matches** and `networking` stopped with `udhcpc: no lease, failing` |
| corrected OpenRC start | the designated host-local profile was provisioned over pinned `:2222` into root-only guest RAM (174 bytes, `0:600`, one network block) and OpenRC restarted; `wpa_supplicant` ran `-iwlan0` and reached `wpa_state=COMPLETED` **and** `iw dev wlan0 link` Connected; `networking` stayed `started` |
| address / route | one global IPv4 on `wlan0`, one default route through `wlan0`, one nameserver |
| gateway | bounded `ping -c 3 -W 2`, rc 0, **3/3** |
| DNS | bounded `nslookup one.one.one.one`, rc 0, **4** answers |
| external network | bounded `ping -c 3 -W 2 1.1.1.1`, rc 0, **3/3** |

**Health and cleanup.** Capture stayed live on the same boot. One `hdd_psoc_idle_timeout_callback` line appeared after the link was brought down (benign idle timeout, not a fatal); **0** `fatal error received:`, **0** `fs_device_efs_rmts.c` and **0** `kernel panic` lines. Before ending radio work the profile, raw scan and service logs were scrubbed from guest RAM; `/run/keep` (`0:600`), both remoteprocs (`running`), `:2222` and capture remained healthy on boot `3fa41974…`.

**Conclusion.** The installed-chain bootloader-start question is measured: self-stage, PID 1 and the guard ack all succeed without a host archive push or a partition write. WLAN association, address, route, gateway, DNS and external reachability were each measured separately and succeeded once the designated network was visible. The next design question is persistence, not another reboot-hold variant. The coordinator owns session close and the untouched slot-A rescue proof; this record does not claim them.
