---
date: 2026-10-25
issue: omnipha/linux-sm7635#86
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Stock-map pd-mapper + tqftpserv session init_boot (#86, host-only, 2026-10-25)

**Host result:** one new candidate, not a device boot result. Run 34 already
measured `35866d56…` and verified rollback; that SHA, `ae2ccff7…`,
`4216af26…`, `bde3a3b3…`, `6078269d…` and every other measured SHA are
rejected for reuse. No physical access, flash, remoteproc operation, new
`modem_a` read, kernel build, boot_a/dtbo/vbmeta/slot-B or rmtfs/sharedmem
change occurred in #86.

| artifact (outside repo) | bytes | SHA-256 |
| --- | ---: | --- |
| `$HOME/sm7635-build/out/init_boot-pdmapper-tqftpserv.img` | 8,388,608 | `8dddb8c714dce40c2795c95103236d8af9cfdc8ef00aaa6b6723055e41de09d1` |
| `$HOME/sm7635-build/out/pd-mapper` | 199,008 | `40acf0b06856205cb6cb9d53084afe5f6619fd1330c13242be1464b1dede3f43` |
| `$HOME/sm7635-build/out/tqftpserv` | 132,592 | `4eacb4ae30fe9c1ee3078bf140bd391c0179c2e8599461c67636d26006313965` |

The binaries are static musl 1.2.5 aarch64, compiled from pinned upstream
sources with one explicit post-publish log line each (`pd-mapper: published
QRTR service ...` and `tqftpserv: published QRTR service ...`): `qrtr` v1.2 (`b51ffaf22707b6000ecfb894c5b750f3bb7843b2`),
`pd-mapper` v1.1 (`5ecd2fe926aca7abfe40724177f63b942cff3947`) and
`tqftpserv` v1.3 (`b31de6db4f31d09119293203d39636b827f16321`), with
liblzma from xz 5.6.4. The host build verifies source tarball hashes,
cross-builds twice, checks ELF static/aarch64/size/sha and smoke-tests
tqftpserv under qemu-aarch64. It does not import firmware from Git.

`modem_a` is the single already-pinned #89 read (367,001,600 B,
`08a5caf81d50a0a2450dee77cb74ba71a215f9009aba55594912373dd2de843a`).
The six `.jsn` are re-extracted read-only by #92's merged extractor under
`~/phone-second-life-data/mb003/acquire/attempt-20261025-0632-modem-a/issue-86-maps`;
manifest `verdict=PASS`, `synthetic=false`, `jsn_under_image=6`,
`jsn_outside_image=0`, all six #89-recorded SHA-256s checked before packaging.
The **byte-exact** `image/{adspr,adsps,adspua,battmgr,cdspr,modemr}.jsn` are
included at `etc/pd-mapper/` in the cpio. Upstream pd-mapper consumes those
individual stock map files (not the extractor's aggregate JSON) via its
non-Android `/lib/firmware` search. At runtime the new init compares the
stock read-only-mounted `modem_a` map files byte-for-byte with the cpio
copies and checks their recorded hashes before it bind-mounts the stock
firmware image at `/lib/firmware` read-only. No upstream example map is used.

The new `/init` equals the decoded run-34 #83 `/init` with the session
marker reworded and one new phase *after* the key-only SSH/listener block
and *before* `console ready`. It starts `/bin/pd-mapper` and
`/bin/tqftpserv -d` in the background only when the stock maps and both
executables are available, logs launch and PID lines to kmsg and
`/run/pd-mapper.log` + `/run/tqftpserv.log`, then waits at most 5 s for
both explicit QRTR publish lines and live PIDs before writing
`/run/qrtr-services.status` (`qrtr-published` or `failed`). Missing/mismatched
maps, mount, binaries or publish lines fail closed. The physical coordinator
must check the processes, the logs, and QRTR publication before proceeding.
The publish line itself is the evidence of a successful QRTR bind; its absence
after 5 s is a hard stop. No init-time remoteproc2 start or
`/run/keep` creation is added. The 127-module order, corrected read-only
mounts, WPSS supplier/bind gate, single WLAN load, USB/key-only SSH and the
150 s self-recovery timer are unchanged. Kernel QRTR nameserver is already
in `qrtr.ko`, no separate qrtr-ns service added. The 150 s userspace timer
cannot protect against the expected kernel panic.

Two serial builds produced identical images: debug cpio 3,838,464 B,
SHA-256 `9cc1a1996604d72fd42b3e2321ad1ad2f0c28c0b2abe6a63636364638ad7539a`,
zero `.ko`; one LZ4 HC-12 legacy frame 2,095,184 B (limit 2,117,632 B;
22,448 B spare); stock header except ramdisk-size field, zero gap, same
stock signed tail from offset 2,121,728 through terminal AVBf (6,266,880
B), fixed 8,388,608-B image. `verify-init-boot-pdmapper-tqftpserv.py`
independently decodes and rebuilds against the run-34 image, proves exact
init/cpio delta, executable ELF and config bytes, ordering and `/run` logs,
checks the signed-tail/prefix/frame/size, and rejects missing/altered
binaries/maps, missing/moved phase or marker, init-time remoteproc control,
and all 50 previously measured SHAs. It is wired into `verify-bootimg.sh`.

```sh
WORK="$HOME/sm7635-build" scripts/build-pdmapper-tqftpserv-binaries.sh
WORK="$HOME/sm7635-build" scripts/build-init-boot-pdmapper-tqftpserv.sh
WORK="$HOME/sm7635-build" scripts/verify-bootimg.sh
```

**Predicted physical outcomes, not observations:** The physical coordinator
alone (standing `full_autonomy_device_iteration` approval) flashes the **new**
SHA to `init_boot_a` only, pins host `172.16.42.1/24`, proves the capture
selftest on a live console line, confirms both services running and QRTR
publication in their `/run` logs/status, then issues one guarded remoteproc2
start with continuous host capture. If modem stays up beyond +60 s and
`wlan0` appears, the pd-mapper/tqftp hypothesis is supported. If the same
~40 s DOG recurs despite both QRTR services running, this pair is not the
single missing dependency; rmtfs/sharedmem is a *separate* successor
experiment, not a second run in #86. If the fatal text differs, record it
rather than forcing either interpretation. Either result requires the
coordinator's measured Sahara reset/timer recovery and **verified stock
rollback of all five partition hashes**. The issue stays open until that
capture-gated single result and rollback proof are recorded.
