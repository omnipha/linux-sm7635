---
date: 2026-11-02
issue: omnipha/linux-sm7635#291
subsystem: wlan
result: inconclusive
---
# Host-only fresh-boot candidate: persistent local hook, pre-ack nonce gate

Issue #291; base `923c450a52b78bd0a6040a358294c4370aa0eec3`. No device contact,
USB, partition write, image build or flash. This is a host-derived candidate,
not evidence of a successful live boot, WLAN acceptance, or a substitute for
PLAN.md's two fresh boots.

## Ownership of every run-98/99 host action

| Host action | Smallest existing device-side owner / exact fixture |
|---|---|
| Capture, SSH/key/boot/hold checks and exactly one ACK | Existing diagnostic init and `pmos-self-stage.sh` stage hold, key-only SSH, `prepare` and switch-root; `pmos-pid1-guard.sh` arms and independently recovers. The candidate **does not ACK**. Its nonce-bound guest markers retain the installed self-post capture gate; these are not host capture selftests. `test-pmos-self-stage.sh`, `test-pmos-root-contract.sh`, `test-pmos-fresh-post.sh` and `test-pmos-radio-bringup.sh` cover their respective parts. An ACK consumes the nonce: if it occurs during the pre-ack chain, subsequent stages fail closed; the candidate does not use the post-ack derivation or synthesize an ACK. An unacknowledged boot still returns to bootloader at the guard deadline, even if WLAN worked briefly. |
| Transfer/recheck the run-99 composed post-ack radio | Replace the already-allowed persistent `/etc/local.d/10-omnipha-self-stage.start` with the generated hook. It pins the two new root-owned `0700` persistent scripts and launches self-post using the existing `local.d`/`setsid` mechanism. `test-pmos-fresh-post.sh` tests launch and altered-radio refusal; `test-derive-radio-fresh-boot.py` tests pins and exact transformations. This is a proposed later persistent-root change, not a deployment in this issue. |
| `prepare`: stage stock INI/link, WPSS/lease helpers, QRTR/rmtfs status, log and PID before cutover | Existing installed self-stage and pinned `prepare` own this; never rerun it after cutover. `test-pmos-self-stage.sh` and `test-pmos-radio-bringup.sh` exercise staging. The run-66 lease helper is unchanged; its unowned WLAN `:22` listener remains a known side effect, not newly authorized. |
| Known empty `/vendor/firmware_mnt` repair before modem | Fresh radio variant's existing modem/bind owner removes only a root-owned `0700`, unmounted, empty, non-symlink directory with `rmdir`, before creating and binding the read-only firmware path. `test-pmos-radio-bringup.sh` exercises success and refuses regular files, symlinks, hidden contents, wrong mode and another mount before `modem.attempted`. Other rmtfs node/link restoration remains inside the existing modem stage. |
| Per-stage host capture selftest; modem, WPSS, driver, scan in order | Self-post creates the existing per-stage, same-boot nonce-derived root-only marker and publishes it to kmsg; the original radio capture gate verifies it. The ordered stages and one-shot limits are unchanged. `test-pmos-fresh-post.sh` checks order, stop-on-failure and marker creation; `test-pmos-radio-bringup.sh` checks marker/nonce negatives and mocked stages. Guest markers are **not** a claim that a host capture exists. |
| Manual helper reconstruction and service starts in run 98; run 99 services stage, profile on stdin | Persistent `services` stage recreates `/run/radio-bringup/{ifquery-wlan,lease-wrapper.sh}`, validates persisted own output/profile, and starts `wpa_supplicant` then `networking`. The existing generated local hook starts self-post asynchronously after local starts; self-post waits for OpenRC default/local. `test-pmos-radio-bringup.sh` covers own-output replay, helper recreation, ordered services and foreign config/profile refusals; `test-pmos-session-dev.sh --stage-only` covers the distro guest. Persisted runlevel links may attempt services earlier: that race and recovery from an early OpenRC failure are **not established** by these mocks and require later live observation. |
| Read-only association, address, route, ICMP, DNS and final health measurements | These are measurements, not startup actions. Existing services own association and DHCP; no fixture pretends to prove connectivity. Later live verification remains necessary. |

## Post-cutover record and deployment boundary

Run 97's panel restore did not fire; its capture alone does not prove what the
guest's BusyBox `dmesg` returned. The new derivation accepts either the existing
timestamped format or a raw `<priority>` prefix, preserving the required unique
same-boot kmsg line, equality with record line 3, safe file metadata, and the
unchanged ordered append/verify. This is a hypothesis, not a measured cause.
`test-pmos-fresh-post.sh` replays both formats, identical/conflicting lines and
a foreign record; its mount/contract and radio calls are mocked. The real
loop-backed ext4 guard/root contract remains covered by the existing
`test-pmos-root-contract.sh`, not by a combined live simulation.

**Deployable in principle without a new init_boot/vendor_boot**, conditional on
later authorized persistent-root installation and live proof: the installed
builder permits exactly this existing local.d path when it is a regular root
`0700` file, and the radio/self-post variants live under
`/usr/libexec/omnipha/`. No change to the pinned images, guard, interlock,
capture gate or recovery logic is required for this proposed installation.
The generated hook is not installed here. This does not prove the chain succeeds
before the unacknowledged guard deadline, nor that an acked boot can self-start.
If the candidate cannot run under these constraints, stop for an owner decision;
do not weaken the guard or replace a pinned image in this task.

For reproducibility, use `build-init-boot-persistent-root.py::current_scripts()`
to obtain the staged radio, `derive-radio-persistent.py`, then
`derive-radio-fresh-boot.py`; feed that output and `pmos-self-post.sh` to
`derive-self-post-fresh-boot.py`. The fixture runs these transformations without
accessing profile data. SHA-256:

| Host artifact | SHA-256 |
|---|---|
| installed staged radio | `f54b33727cefdf728001e4692d625c0f5a77298694454832e02b6cf0c765764f` |
| persistent services staged radio | `c54c29e1278827bc00faaf506c7ff8e923a8a689a011a2852d5d4b7778d0188d` |
| fresh radio | `a0ea867a7fb8ada2fda46fdf94076c44c814e8a8d2a470c200df820529445c21` |
| fresh self-post | `c9173d6d362a79cd55a92814f2572ba0a111b99a61a84b99b0c3076a7e1fcbc7` |
| generated local hook | `aaeb1b999bccba577fb1536825d56562ef7892c7ee03edb510120f2fc16b1ee3` |

## Host verification

All passed: `python3 -B scripts/test-derive-radio-fresh-boot.py`,
`sh scripts/test-pmos-fresh-post.sh`, `sh scripts/test-pmos-radio-bringup.sh`,
`python3 -B scripts/test-derive-radio-persistent.py`,
`python3 -B scripts/test-derive-radio-postack.py`,
`sh scripts/test-pmos-self-stage.sh`, `sh scripts/test-pmos-boot-record.sh`,
`sh scripts/test-pmos-session-dev.sh --stage-only`,
`sh scripts/test-pmos-root-contract.sh`, `sh scripts/test-wlan-udhcpc-lease.sh`,
`sh -n` and `shellcheck -S error` on the two changed shell fixtures, Python
`ast.parse` of all three new Python files, and `git diff --check`.
`test-pmos-pid1-request.sh` was attempted separately and still fails with the
pre-existing `pinned transition script unavailable` stale pin, as recorded in
#275; it was not changed. Fixtures use isolated namespaces, loop-backed host
files or mocks, not the phone.

Host-local files hashed twice before/after tests, matching recorded pins (not a
new device read): init artifact `2ebdf1db26193f7f0c3f4c6d42f722008bd1ee2718adf399dfe4927cc3eb9632`,
carrier artifact `a71b3f5f5e73ed7d8855abdd06c0379aa8084dfa9aa8068e347347d36254f9b3`;
stock slot-A rescue references `boot_a` `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d`,
`vbmeta_a` `cc1926d2aa8e9c12df6a469111bf87f1e61e70022b84626fabcd014ae33cdffe`,
`dtbo_a` `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992`,
`vendor_boot_a` `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253`.
