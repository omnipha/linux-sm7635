---
date: 2026-10-31
issue: omnipha/linux-sm7635#223
subsystem: boot
result: refuted
---
# Cold-start installed-chain host boundary

Host-only audit. No image was built, and no USB, device, flash, reboot, SSH, session, partition, scheduling, or power operation was performed. This is not a cold-start measurement and does not schedule or substitute one.

## Installed starting point

The installed chain is the required identity-preserving starting point: `init_boot_a` `2f73c94764be3f443ace02fc46001662686512f37f4951bedfb5900cf3d31c28`, `vendor_boot_b` `f792174c3e886b6f3280d447c3da4704403f713fe24228fb4f52f24e7da11095`, and the existing pinned persistent ext4 userdata root. Run 73 verified exact rollback to those carrier hashes and the untouched stock slot-A rescue hashes. Run 73 `3eeddb35…6522` / `762566b7…fc4e5d`, run 72 `3c97c918…bc71a`, and every earlier measured image remain never-reflash. No partition write is part of the cold-start experiment.

The proposition that this unchanged chain can produce the issue's full host-free observation sequence is refuted by already-recorded image deltas and the current host scripts:

- Run 69 lacks guest-owned keep creation. The #216 host record proves that removing the five later-added `/run/keep` lines reconstructs installed `2f73c947…31c28`. With no host hold, self-stage waits for `/run/keep` and refuses at `diagnostic hold not set before self-recovery deadline` (`scripts/pmos-self-stage.sh:97-108`).
- Run 69 lacks safe prior-helper guard re-arming. Run 69's measured second boot stopped at `independent recovery guard not armed` because the pinned prior `restart2` already existed; #220 changed that refusal and run 73 then passed, but its images were rolled back.
- Even after a successful cutover, the unchanged post-cutover helper waits for the host-owned guard ack before radio setup and then requires fresh host-verified capture releases for modem, WPSS, driver, scan, and services (`scripts/pmos-self-post.sh:51-97`). Thus the requested no-host-signal radio/MINDSTORMS sequence is not reachable with that helper unchanged.

These are concrete pre-SSH/pre-radio host-design defects, not newly measured cold-start failures. Recording them here satisfies the issue's requirement to record a defect before any image build; this host phase builds none. The unchanged chain must not be described as ready for outcome (a), and a known-defect boot must not be substituted for the coordinator's single cold-start measurement.

## Exact observation contract

If and only if the starting-chain contradiction is resolved without an unauthorized carrier or partition write, the coordinator's one power-off plus one scheduled operator power-button press must record the following, in order, with no host hold, guard ack, capture release, or push before the boot has had its chance:

1. Guest-owned `/run/keep`: regular root-only empty file, `0:600:1`; run 72's observation is `The guest created a regular root-only empty /run/keep (0:600:1).`
2. Self-stage: `diagnostic hold and :22 verified on boot <boot-id>`, reached before the former 145-second deadline.
3. Persistent ext4 root: `copied userspace archive from read-only <node> (userdata) and verified SHA-256`, with the pinned root contract verified at `/run/pmos`.
4. Guard armed: `pid1 transition guard armed; exec switch_root to postmarketOS init`; after cutover, `/run/pid1-guard/armed` is a regular root-only file containing this boot ID, the nonce exists, and no acceptance file exists.
5. `switch_root`: diagnostic `:22` closes at the transition to the verified persistent root.
6. postmarketOS PID 1: key-only guest access reports `uid=0`, postmarketOS v24.12, and PID 1 `/sbin/init`.
7. Radio start: the modem, WPSS, and `wlan0` stages are each recorded as reached; no scan or association claim is made at radio start alone.
8. MINDSTORMS association: record association to MINDSTORMS, then address, route, DNS, and reachability separately.
9. Key-only `:2222`: persistent SSH uses only the independently pinned public key and remains on postmarketOS PID 1.

Record each as reached or name the exact first missing line and stop there; do not infer later stages.

Contrasting outcomes: **(a)** host-free persistent PID 1, radio, and MINDSTORMS WLAN verify the cold-start gate; with no host ack, the independent 160-second deadline must then return to responsive fastboot, which is designed bounded recovery, not boot failure. **(b)** a stop at any earlier named line is reported with that exact first missing line and no later success claim. **(c)** never enumerating is the stop boundary; the operator gets only the one scheduled button press, not a diagnosis request. Any partition write, unauthorized carrier, guard-arm refusal, or rescue-path loss is also a stop.

Afterwards, rescue/readback proof must show installed `init_boot_a 2f73c947…31c28` and `vendor_boot_b f792174c…11095`, plus untouched stock slot-A `boot_a 197aff11…706d4d`, `vendor_boot_a 23725940…dc1253`, `dtbo_a 759813db…13c992`, and `vbmeta_a cc1926d2…cdffe`, using a held diagnostic boot as in run 73. Since this experiment writes nothing, matching hashes are preservation/readback proof, not a rollback claim. No cold-start outcome is recorded until the coordinator's committed measured evidence exists.
