---
date: 2026-10-26
run: 42
issue: omnipha/linux-sm7635#116
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Run 42 candidate: pinned deterministic Dropbear host key for the #116 capture handoff (#120, host-only, 2026-10-26)

**Host result, not a device result.** No flash, reboot or other device operation
was performed. The one physical run stays owned by #116 under its unchanged
outcomes (a)/(b)/(c)/(d), one-attempt stop rule and never-reflash list, and must
use this new SHA only, once.

The #113/#116 preboot capture handoff requires a known-hosts pin **before** the
reboot, but the run-41 image started Dropbear with `-R`, which generates a fresh
RAM host key on every boot. No pre-existing pin can therefore match the next
boot, and `session-capture.py` runs `StrictHostKeyChecking=yes`, so it can only
fail closed. This image repairs exactly that gate: the next distinct-SHA session
init carries a deterministic host key whose public half is pinned here and can be
placed in the known-hosts file before reboot.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-psoc-hold-capture-hostkey.img` | 8,388,608 | `8b62520fe6288361fd15faa573587a0d1be1e0788f780c62440677a60b739801` |

**Pinned Dropbear host public key.** Place this exact line in the attempt
directory's known-hosts file before any reboot:

```
[172.16.42.2]:22 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA2ioqI4txcs3PSJWvcgSd/qBuDuCC50OIvIpKsjrjql
```

Fingerprint `SHA256:fZKbZhNlbjd9/c7oxUy2YWmOgZs5TcVjxLRuPLEgb4w`. The matching
private key is a **protected build input**, `HOSTKEY` (default
`$HOME/.omnipha/sm7635/dropbear_ed25519_host_key`, mode `0400`), and is never
committed; the build refuses a group- or world-readable key and scans every
tracked repository file for the private material. The key is packaged verbatim
into the debug cpio at `etc/dropbear/dropbear_ed25519_host_key`, mode `0600`,
inside a mode `0700` `etc/dropbear`, and `init` starts
`dropbear -r /etc/dropbear/dropbear_ed25519_host_key -p 172.16.42.2:22`; no `-R`
remains. Two serial builds from the same protected input are byte-identical.

The only deltas from the unflashed #116 run-41 image (`7c3d915f…`) are that one
Dropbear invocation and the two new cpio entries. The #116 session marker stays
byte-exact. `bin/wpss-once` is byte-identical to #109, so the single 25 s-capped
`/dev/wlan` `ON` hold, the one stock `wpss_boot=1` write and the 12 s window
sample are unchanged; the stock INI phase, the modem-holding stack, the 21-module
WLAN closure, the armed `sleep 150` self-recovery timer and the single `/run/keep`
test inside it are byte-exact #109. The debug cpio carries zero `.ko` and is
3,672,576 B, SHA-256
`9a5e5d6798b885792fc6c138ae335add43cc23915cb173b9c4f3ec2d631eded4`; the LZ4 HC-12
frame is 2,096,286 / 2,117,632 B and the 6,266,880 B signed tail from offset
2,121,728 is unchanged.

`scripts/verify-init-boot-psoc-hold-capture-hostkey.py` first re-verifies the
unflashed `7c3d915f` image through the #116 checker, then requires the candidate
cpio to differ by exactly the marker, the Dropbear invocation and the pinned key,
and re-derives the packaged public key from the protected private key without any
third-party crypto. It fails closed on a restored `-R` generated key, a removed,
duplicated or retargeted `-r` invocation, a missing key file or its directory, a
world-readable key, an unpinned or replaced key, committed private key material,
a lengthened, shortened or removed 150 s timer, a disabled, early or renamed
`/run/keep`, a removed or re-capped 25 s hold, an altered `/dev/wlan` `ON` write,
a second WPSS write, a removed or regressed marker, the reused run-41 and run-39
images, tail, header, block, gap and size damage, and every prior measured SHA
including the unflashed `7c3d915f`. `scripts/build-init-boot-psoc-hold-capture-hostkey.sh`
builds twice in series and fails unless the outputs are byte-identical. Both are
wired into `scripts/verify-bootimg.sh`:

```sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-psoc-hold-capture-hostkey.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Coordinator handoff (one run, `init_boot_a` only, this SHA only).** Follow the
#113 handoff recorded below exactly, with the pinned public key above instead of
any previously measured pin, and add nothing:

1. Use a new attempt directory outside Git. Before any `fastboot reboot`, write
   the pinned `[172.16.42.2]:22 ssh-ed25519 …` line above into that directory's
   known-hosts file, start `omnipha/agents/scripts/session-capture.py start` with
   `--target root@172.16.42.2` and `--known-hosts-file` pointing at it, configure
   the NCM host address `172.16.42.1/24`, mark both gadget links unmanaged, and
   verify the link and the route to `172.16.42.2`. Abort if any preboot check
   fails. `session-capture.py check` is not the preboot gate.
2. Flash `8b62520fe6288361fd15faa573587a0d1be1e0788f780c62440677a60b739801` to
   `init_boot_a` only, after the verified five-partition stock rollback and the
   fresh fastboot gate, and reboot once. The SHA becomes never-reflash on first
   flash. Never flash the unflashed `7c3d915f…`, `0b40ac34…`, `e75c5bd2…`,
   `d9d8d2b8…`, `bf2089c4…` or any earlier measured SHA.
3. At the earliest key-only SSH acceptance, the host key must match the pin above;
   read and retain `/proc/sys/kernel/random/boot_id` over that same connection,
   start `session-capture.py selftest <attempt-dir> --marker <unique-boot-marker>
   --timeout 8`, write that unique marker to `/dev/kmsg` over the same boot's SSH
   session, require `check` to report this boot ID and `ok: true` for the same ID
   with the marker line arriving after the selftest starts, and only then create
   `/run/keep` strictly before the unchanged 150 s deadline.
4. Then exactly one guarded session under the #101/#106 preconditions, recording
   the outcomes (a)/(b)/(c)/(d) below unchanged. No outcome authorizes a second
   attempt or a second variable.
