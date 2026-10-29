---
date: 2026-10-26
run: 48
issue: omnipha/linux-sm7635#137
subsystem: wlan
result: confirmed
source: BOOT.md
---
## Run-48 measured guest WLAN connectivity in one held session (#137, live-session finding, 2026-10-26)

**Measured physical result — the full scan→target-match→association→address→reachability chain, in one held SSH session.** The physical coordinator flashed the currently reusable `init_boot_a` image (`0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa`, 8,388,608 bytes) to `init_boot_a` only, after checked backups (16/16), the five-partition recovery-root stock baseline and a fresh serial/slot/unlocked fastboot gate; pinned key-only USB SSH reached boot ID `17494a88-4056-4400-aded-657afa6a44e4` on stock kernel `6.1.84-android14`; `/run/keep` was set before the 150 s deadline; the pinned host capture had a fresh console-marker selftest; then the worker owned the bounded reversible guest WLAN diagnosis over that same held session. No image, kernel, config, module, timer, host key or partition was changed by the worker. `boot_a`, `vendor_boot_a`, `dtbo_a` and `vbmeta_a` stayed stock; **at the time of this finding the stock `init_boot_a` restore and five-hash rollback were still PENDING and remain coordinator-owned**. The worker claims no `PACKAGE_COMPLETE` and does not close #137; this is not proof of WLAN autoconnect after a reboot, only in-session connectivity on the stock-kernel session image.

### The worker independently rechecked the handoff before any guest action

Same-boot key-only SSH returned the coordinator's recorded boot ID `17494a88…`; `/run/keep` was present; `session-capture.py check` reported `ready: true` for that boot on the run-48 attempt directory; the worker then wrote its own fresh console marker over SSH and `session-capture.py selftest` returned `ok: true` with a matching boot ID and sub-second latency — a *fresh* selftest for this boot, not the coordinator's earlier one. The pinned attempt `known_hosts` fingerprint matched the #120 pin `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w` for `[172.16.42.2]:22`. Only then did guest work begin.

### Stage-by-stage measured outcomes

| stage | measured outcome |
| --- | --- |
| guarded modem prerequisite | one `remoteproc2` (`4080000.remoteproc-mss`) start from an `offline` guard, rc 0, `running` and held past +60 s; QRTR/rmtfs status files already `published`; `modem_a` mounted read-only at `/vendor/firmware_mnt`; icnss2 bound at `17110040.qcom,wcn6750`; **QMI DMS service connected** |
| one-shot WPSS trigger | exactly one `/bin/wpss-once`, rc 0; its own one-shot marker set; `remoteproc3` (`9bb00000.remoteproc-wpss`) `running`; `FW ready event received` and `WLAN FW is ready` in the captured kmsg; `/dev/wlan` character node `495:0` present as created by init |
| `wlan0` | present, ifindex 16, type managed, on phy#0 (alongside `p2p0`/`wifi-aware0`); flags `0x1002` → `0x1003` after one `ip link set wlan0 up` (rc 0); after association: `operstate=up`, `carrier=1` |
| client load | hash-checked RAM bundle (`4acd0593…`) unpacked under `/run/wlan-tools` at mode `0700`; `iw version 6.9` and `wpa_supplicant v2.10` both load in the guest through the bundled musl loader; `iw dev` reports a phy for `wlan0` |
| scan (20 s-bounded, IFF_UP first) | rc **0**, empty stderr, complete raw output retained privately on the host (64,690 bytes) together with its exit status and boot ID — **not** replaced by a BSS count; 20 BSS lines / 19 `SSID` fields in the retained raw scan |
| private target match | **matched**: the designated hotel profile's target SSID appears in **7** of the 20 scanned BSS (multi-AP). Matching was performed by a private host-only helper that reads the profile and the retained raw scan and emits only booleans and counts — never SSID/BSSID/MAC/PSK/path. Raw identifiers and the profile stayed in root-only host/guest storage; none appears in Git, CI, issue comments or chat. |
| association | designated host-local profile transferred over the pinned key-only SSH into root-only guest RAM (`/run/wpa_supplicant.conf`, mode `0600`, never printed); one RAM-only `wpa_supplicant` started with `-O /run/wlan-wpa-ctrl` (bounded start, unbounded lifetime, never `-K`); `wpa_state=COMPLETED` **and** a connected `iw dev wlan0 link` — both agree, so association is measured, not inferred. The daemon was left running through DHCP. |
| address | hash-checked lease helper (`86ebff20…`) transferred to RAM; one bounded `udhcpc -i wlan0 -q -n -t 5 -T 3 -A 5 -s <lease-script>`, rc **0**, lease obtained; a non-link-local IPv4 on `wlan0`, a default route and a configured `/etc/resolv.conf` were all read back |
| gateway | bounded `ping -c 3`, rc 0, **3/3** replies |
| DNS | bounded `nslookup` of a well-known name through the configured resolver, rc 0, answers present |
| external network | bounded `ping -c 3` to a routable external IPv4, rc 0, **3/3** replies (confirmed twice) |

Association **and** address **and** gateway **and** DNS **and** external reachability were each measured separately, so this run meets the issue's connectivity definition — a scan alone or association alone would not.

### Session safety across the whole chain

Against the worker's pre-scan continuous-capture offset, the host capture grew by 9,109 bytes with **0** new `fatal`, **0** new `crash` and **0** new `hdd_psoc_idle_timeout_callback` matches (the single `fatal`/`crash` substring hits in the whole boot kmsg are the `wpss-once` helper's own log wording and the pre-userspace `tme_crash_dump_region` reserved-memory label, both benign and present before any worker action). `remoteproc2` and `remoteproc3` stayed `running`, `wlan0` stayed registered, `/run/keep` stayed present, and SSH plus capture remained live through the final reachability stage (uptime ~1,351 s). No private identifier, credential, raw log or profile content was published.

### What remains

The worker landed this sanitized finding while SSH was healthy. Session closure — guarded fastboot return, pstore/evidence preservation **before** Android, stock `init_boot_a` restore, all five stock slot-A hashes and stock Android boot proof — is the coordinator's alone and was still PENDING at the time of writing. #137 stays **OPEN** until that verified rollback (or a named gate refusal) is recorded. This in-session result does not close the ports#3 mission, does not prove autoconnect after reboot, and does not resolve the separate builder#4 metadata-encrypted `/data` release gate.
