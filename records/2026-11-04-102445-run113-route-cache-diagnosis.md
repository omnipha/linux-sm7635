---
date: 2026-11-04
issue: linux-sm7635#311
subsystem: wlan
result: confirmed
---
# run113 route cache diagnosis

## Measurement and boundary

Session forensics on the closed run-113 candidate boot (`7dec62b0-ddf3-4a37-abe8-0dad251aa25d`)
from `/home/gregor/phone-second-life-data/mb003/pstore/attempt-20261104-0955-pair-flash-run113/`:

1. All pre-radio, modem, WPSS, driver, scan and service stages completed.
2. The gate passed association (`Connected to ... on wlan0`), address (`inet ... scope global wlan0`),
   default route query (`default via ... dev wlan0`) and gateway ICMP (`ping -4 -I wlan0 ...`).
3. At uptime 199.62 s, stage `internet` failed with `internet route is not wlan0`.
4. Capture log shows the unacknowledged guard armed, nonce present, and no ACK published.

## Host reproduction of the refusal

Testing the exact AArch64 binary `/sbin/ip` from `postmarketos-session-aarch64.tar.gz`
(SHA-256 `7a76a110…`, extracted `iproute2-minimal 6.11.0-r0`) under `qemu-aarch64`
in an isolated dummy-interface namespace shows that a valid route query:

```sh
/sbin/ip -4 route get 1.1.1.1 from 192.0.2.2
```

produces a two-line output:

```
1.1.1.1 from 192.0.2.2 via 192.0.2.1 dev wlan0 uid 0 
    cache 
```

The run-113 success-gate awk expression:

```sh
$BB awk 'NR == 1 {for (i=1;i<NF;i++) if ($i == "dev" && $(i+1) == "wlan0") ok++} END {exit(NR != 1 || ok != 1)}'
```

strictly required `NR == 1`. Because the second line (`cache`) caused `NR == 2`,
the parser exited 1 and triggered `internet route is not wlan0` despite a valid
route via `wlan0`. The actual route text was not preserved in the captured log;
this defect is a demonstrated, sufficient cause for the observed gate refusal.

## Candidate derivation and regression test

1. Added `scripts/derive-route-cache-gated-ack.py` to derive the corrected candidate
   without modifying the installed pair or invalidating historical verification:
   - Updated post: SHA-256 `e48445964beda83d2f661730360954d8c8f9acead7ecbfc6965e2475356c743f`.
   - Updated hook: SHA-256 `6488f1339f4ff6876219a452712c71e9465ddd3887f835d9475a346cd0310377`.
   - The corrected awk expression permits the optional single `cache` second line:
     `NR == 1 {for (i=1;i<NF;i++) if ($i == "dev") {if ($(i+1) == "wlan0") ok++; else bad++}} NR == 2 {if ($0 !~ /^[ \t]*cache[ \t]*$/) bad++} NR > 2 {bad++} END {exit(NR < 1 || ok != 1 || bad)}`
2. Added `scripts/test-success-gate-route-cache.py`:
   - Confirms that the old awk strictly rejects the real `iproute2` two-line output.
   - Confirms that the corrected awk accepts it.
   - Matrix testing verifies rejection of wrong interface, empty output, multi-dev injection,
     foreign second line, and extra lines beyond the cache continuation.
3. Existing tests pass cleanly:
   - `python3 -B scripts/test-success-gate-route-cache.py`: PASS.
   - `python3 -B scripts/test-derive-success-gated-ack.py`: PASS.
   - `python3 -B scripts/test-success-gate-dns.py`: PASS.
   - `python3 -B scripts/test-derive-radio-persistent.py`: PASS.
   - `python3 -B scripts/verify-dependent-pair-manifest.py verify ...`: PASS on settled pair.
