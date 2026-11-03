---
date: 2026-11-03
issue: omnipha/linux-sm7635#298
subsystem: wlan
result: inconclusive
---
# Run-100 pstore preservation: bounded host-only investigation

## Result and decision boundary

No supported, demonstrably non-overwriting route to the possible run-100
pstore was found in this bounded investigation. This is not a proof that no
vendor-specific interface could exist, that the reserved RAM is empty, or that
its contents survived. No post-candidate pstore pull is recorded. The captured
host console is useful run-100 evidence but is not that pull. There is no
verified alternative satisfying the preboot preservation requirement.

The coordinator should hold before any potentially overwriting boot. Per
[the WLAN strategy](../docs/strategy/wlan.md), the fallback is an explicit
owner decision on preservation versus potential loss; the earlier device
iteration approval is not a pstore-preservation waiver. A decision to preserve
is not permission to risk loss. The coordinator alone assesses the evidence
contract and any later physical action. Keep #294 open and its existing worker
context for a newly proven handoff; this finding is neither a WLAN diagnosis
nor physical acceptance. No new SHA or image is
required merely for a distinct identifier, and no guard, capture, rescue or
recovery interlock is bypassed.

## Existing evidence, not a new device measurement

- [Run 100](2026-11-03-014728-run100-candidate-boot1-capture-boundary.md)
  recorded a candidate capture through the panel pre-check, then fastboot near
  the guard deadline, with no proven WLAN or accepted ACK. Its launch
  provenance and the reason for the stopped trace remain unproven.
- [Run 101](2026-11-03-023259-run101-preboot-pstore-access-blocker.md)
  records no subsequent pstore pull, boot or flash. Its last recorded state was
  responsive fastboot. The existing pstore archive was pulled before the
  candidate boot. This is historical state, not a claim about the device now.
- The run-100 host capture has two connected segments: the earlier setup boot
  followed by candidate boot 1. The setup segment contains the append refusal;
  the candidate segment reaches the panel pre-check without a later panel
  post-check or append-refusal marker in that capture. The capture's recorded
  SHA-256 matches. This verifies file identity, not completeness or pstore
  equivalence. The pre-candidate tar's console member matches the extracted
  console and its recorded host/device checksums; this does not make it a
  post-candidate archive or independently verify the tar file as a whole.
- The documented [ramoops layout](2026-10-24-2249-early-kernel-boundary-attribution-and-the-initca.md)
  reserves 4 MiB of RAM, with a 2 MiB console and 2 MiB pmsg and no dmesg dump
  area under the recorded configuration. The candidate capture shows ramoops
  registration around 0.068 s, before `/init`. It does not show the retained
  physical bytes after the candidate returned to fastboot.

## Candidate routes evaluated

| Route | Evidence and limit |
| --- | --- |
| Existing host capture/archive | Capture checksum and segment attribution checked above; the only identified pstore archive predates candidate boot 1. Neither is an actual post-run-100 pstore pull. |
| Bootloader partition fetch | Run-101 targeted `getvar` queries did not expose pstore/ramoops partition variables. Both `fetch pstore` and a `boot_a` control failed on unavailable `max-fetch-size`. This is failure of the attempted client path, not proof that every partition or OEM mechanism is absent. Ramoops is reserved RAM, not inherently a flash partition. |
| AOSP fetch or upload | The [Android 14 client](https://github.com/aosp-mirror/platform_system_core/blob/android-14.0.0_r1/fastboot/fastboot.cpp#L1422-L1452) checks a nonzero `max-fetch-size` before issuing partition transfers, and fetch addresses a partition and offset, not arbitrary physical RAM. The [AOSP protocol](https://android.googlesource.com/platform/system/core/+/refs/tags/android-14.0.0_r1/fastboot/README.md) describes `upload` as returning previously staged data; no supported device-specific command to stage this RAM was found. This source is an explanatory example, not identification of the historical host binary or proof of the installed bootloader's behavior. |
| Linux, recovery or fastbootd | The preceding recovery request started Linux setup, not recovery ADB. Historical [recovery-layout analysis](2026-10-21-2228-recovery-path-boundary-after-18-attempt-20261021.md) found ramdisk-only recovery images dependent on the installed kernel and other boot components; it does not prove current selection or non-overwrite. Linux userspace, including a read-only pstore mount or an early `/dev/mem` copy, cannot undo earlier kernel writes. No safe current recovery or fastbootd route was demonstrated. |
| Serial, crash mode or early loader | Historical `getvar all` wedged fastboot; a past Sahara reset was recovery, not a proven memory-read path. No supported non-overwriting serial, crash-mode or pre-kernel RAM exporter is established by these records. An alternate loader would need evidence of actual support, RAM retention, placement and non-overwrite; none is claimed. |

The [pinned published vendor source](../UPSTREAM.md) is 6.1.78, not the
observed 6.1.84 device binary, so its behavior is supporting analysis rather
than an exact binary guarantee. In that source, ramoops initializes the
console and pmsg zones with `PRZ_FLAG_ZAP_OLD`: for a valid nonempty ring it
attempts to copy old contents to a volatile kernel-memory shadow, then resets
persistent ring metadata; allocation failure can leave no shadow. Registering
the pstore console can then replay or write current-boot messages to that ring
before userspace. See [`ram.c`](https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635/blob/d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7/fs/pstore/ram.c#L570-L600),
[`ram_core.c`](https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635/blob/d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7/fs/pstore/ram_core.c#L506-L547),
and [`platform.c`](https://github.com/NothingOSS/android_kernel_msm-6.1_nothing_sm7635/blob/d5f5f965fd0b478eaf4eb63fd984c5a4a92135a7/fs/pstore/platform.c#L489-L520).
Resetting ring metadata is not a bytewise wipe, but subsequent writes may
replace old bytes. A successful same-boot read could expose the shadow; it is
not proof of non-overwrite, guaranteed retrieval, or survival through another
reset. In this source, unlink invokes backend erase; a read-only mount does not
reverse earlier writes. The historical record of an intact predecessor console
and the separate [overwritten crash-console example](2026-10-25-2256-live-session-init-boot-for-the-continuous-fatal.md)
illustrate different outcomes, not a guarantee for run 100.

## Reproducible host-only verification

The authorized private artifact root is
`~/phone-second-life-data/mb003/pstore/`. Under
`attempt-20261103-0235-success-gated-ack-run100/`, the
`candidate-boot1/capture/kmsg.log` SHA-256 matches
`candidate-boot1/capture.sha256`. Its connected segment boundaries identify
setup first and candidate second; classify markers within those boundaries,
not across the entire file. The console member of `preboot-pstore-final.tar`
matches the extracted `preboot-pstore-final/console-ramoops-0` and the console
checksums recorded in `preboot-pstore-host.txt` and
`preboot-pstore-on-device.txt`. The ledger places that archive before candidate
boot 1. Under
`attempt-20261103-0330-run101-diagnostic-preflight/`, the recorded
`fastboot-pstore-probe.txt`, `fetch-pstore.txt` and `fetch-boot-a.txt` support
the fetch observations above. These are host-private references; do not copy
raw captures, device data or serials into the repository or issue.

The following reads only those host files and prints booleans or classified
line numbers, not their private contents. The preboot archive's timing still
requires checking the ledger and run-101 record; the script does not infer it
from the archive checksum.

```sh
python3 -B - <<'PY'
import hashlib
import re
import tarfile
from pathlib import Path

if __debug__ is False:
    raise SystemExit('verification requires Python assertions enabled')
root = Path.home() / 'phone-second-life-data/mb003/pstore'
run100 = root / 'attempt-20261103-0235-success-gated-ack-run100'
run101 = root / 'attempt-20261103-0330-run101-diagnostic-preflight'
sha = lambda data: hashlib.sha256(data).hexdigest()
digest = lambda name: re.search(r'\b[0-9a-fA-F]{64}\b', (run100 / name).read_text()).group().lower()
capture = run100 / 'candidate-boot1/capture/kmsg.log'
assert sha(capture.read_bytes()) == digest('candidate-boot1/capture.sha256')
console = sha((run100 / 'preboot-pstore-final/console-ramoops-0').read_bytes())
with tarfile.open(run100 / 'preboot-pstore-final.tar') as archive:
    assert sha(archive.extractfile('./console-ramoops-0').read()) == console
assert console == digest('preboot-pstore-host.txt') == digest('preboot-pstore-on-device.txt')
uid = re.compile(r'(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b')
ids = {label: uid.search((run100 / path).read_text()).group().lower() for label, path in (
    ('setup', 'boot-id.txt'), ('candidate', 'candidate-boot1/boot-id.txt'))}
assert ids['setup'] != ids['candidate']
segments, markers, label = [], [], 'unknown'
for number, line in enumerate(capture.open(errors='replace'), 1):
    if line.startswith('# connected '):
        match = uid.search(line)
        label = next((key for key, value in ids.items() if match and match.group().lower() == value), 'unknown')
        segments.append((label, number))
    for tag, pattern in (('pre-panel', r'pre check panel record'),
                         ('post-panel', r'post check panel record'),
                         ('append-refusal', r'append.{0,30}refus|refus.{0,30}append')):
        if re.search(pattern, line, re.I):
            markers.append((label, tag, number))
assert [name for name, _ in segments] == ['setup', 'candidate']
assert any(name == 'setup' and tag == 'append-refusal' for name, tag, _ in markers)
assert any(name == 'candidate' and tag == 'pre-panel' for name, tag, _ in markers)
assert not any(name == 'candidate' and tag in ('post-panel', 'append-refusal') for name, tag, _ in markers)
for name in ('fetch-pstore.txt', 'fetch-boot-a.txt'):
    assert 'max-fetch-size' in (run101 / name).read_text()
print('capture and preboot console checksums match; both fetch reports name max-fetch-size')
print('connected segments:', segments)
print('classified markers:', markers)
PY
```

This investigation independently compared those existing files and classified
segment markers locally. No device, USB, SSH, ADB, fastboot connection, image
build or device operation was used. A synthetic ring-buffer fixture could test
a model of source behavior, but cannot establish the installed binary, RAM
retention or a reachable safe exporter, so it would not establish the requested
non-overwriting route and was not substituted for physical evidence.
