---
date: 2026-10-26
run: 46
issue: omnipha/linux-sm7635#132
subsystem: wlan
result: inconclusive
source: BOOT.md
---
## Run-46 guest scan-client diagnosis (#132, host-only, 2026-10-26)

**Finding:** The unchanged run-43 guest has no *usable* nl80211 scan client.
Run 46 measured an absent **BusyBox `iw` applet**, not an exhaustive on-device
binary inventory. The standalone/rootfs and mounted-partition inventory below
is instead a host inference from the published build inputs and read-only stock
references. `iw` is a standalone program, **not** a BusyBox applet to enable.
No image, source, kernel, config, module or device state was changed here.

### Observed run-46 evidence (not a scan)

The physical coordinator's #130 comment and read-only files under
`~/phone-second-life-data/mb003/pstore/attempt-20261026-1648-initboot-run46/`
record outcome **(b)** and verified stock rollback. In that directory,
`stage9-iw-applet.txt` is empty, and `stage9-iw-dev.txt` says `iw applet
absent`; `stage9-action.txt` records `remote_exit=0`, `ssh_exit=0` for the
sole 20 s-bounded fallback `ip link set wlan0 up`. `stage9-preaction-state.txt`
and `stage9-postaction-state.txt` record `wlan0=present`, flags `0x1002` to
`0x1003`, `operstate=down` both times, modem and WPSS running.
`stage9-kmsg-counts.txt` records zero new fatal, crash and
`hdd_psoc_idle_timeout_callback` lines. The run-46 live
`capture/kmsg.log` records the stock `vendor_a` erofs mount and read-only
`/vendor` bind (`wlan-init: mount vendor_a read-only: ok`, `wlan-ini: stock
vendor_a bound read-only at /vendor`), and `Freeing initrd memory: 10660K`;
this is the normal generic+vendor ramdisk, not the extra ~48 MB recovery
ramdisk. No `iw dev` discovery or scan was run. Link-up with no carrier is
neither a scan result nor evidence of association or connectivity.

### Reproducible host inventory of the unchanged image

Inputs: `scripts/build-init-boot-psoc-hold-wlan-node.sh` and
`-payload.py` derive the run-43 `init_boot` from the stock slot-A image;
`vendor-module-closure.py` parses the newc and stock vendor ramdisks;
`build-bootimg.sh` pins Ubuntu arm64 `busybox-static_1.37.0-7ubuntu1`.
Check the locally preserved image at
`~/sm7635-build/out/init_boot-psoc-hold-wlan-node.img`: 8,388,608 bytes,
SHA-256 `0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa`.
The following reads only host artifacts, checks the image and vendor ramdisk
hashes, and runs **only** the extracted BusyBox `--list` under host QEMU in a
temporary directory; it does not inspect or print the bundled host private key:

```sh
python3 -B - <<'PY'
import hashlib, importlib.util, pathlib, struct, subprocess, tempfile
repo = pathlib.Path.cwd()
spec = importlib.util.spec_from_file_location('closure', repo / 'scripts/vendor-module-closure.py')
closure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closure)
image = (pathlib.Path.home() / 'sm7635-build/out/init_boot-psoc-hold-wlan-node.img').read_bytes()
assert len(image) == 8388608
assert hashlib.sha256(image).hexdigest() == '0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa'
size = struct.unpack_from('<I', image, 12)[0]
archive, blocks = closure.unpack_legacy_lz4(image[4096:4096 + size], closure.lz4_library())
entries, _ = closure.parse_newc(archive, 'run-43 generic cpio')
print('generic entries, LZ4 blocks:', len(entries), blocks)
for entry in entries:
    if entry['mode'] & 0o170000 == 0o100000 and entry['mode'] & 0o111:
        print('generic executable:', entry['name'])
busybox = next(entry['data'] for entry in entries if entry['name'] == 'bin/busybox')
print('busybox SHA-256:', hashlib.sha256(busybox).hexdigest())
with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / 'busybox'
    path.write_bytes(busybox)
    path.chmod(0o700)
    applets = set(subprocess.run(['qemu-aarch64', str(path), '--list'], check=True,
                                 capture_output=True, text=True, timeout=10).stdout.split())
print('applets:', len(applets))
print('network applets:', sorted(applets & {'ip', 'ifconfig', 'route', 'nc', 'wget', 'iw',
                                             'iwconfig', 'iwlist', 'iwpriv', 'wpa_cli',
                                             'wpa_supplicant', 'hostapd'}))
vendor = (pathlib.Path.home() / 'phone-second-life-data/mb003/parts/vendor_boot_a.img').read_bytes()
stock_cpio = closure.vendor_ramdisk_cpio(vendor, closure.lz4_library())
stock_entries, _ = closure.parse_newc(stock_cpio, 'stock vendor cpio')
print('vendor_boot entries:', len(stock_entries))
print('vendor_boot scan tools:', [entry['name'] for entry in stock_entries
      if entry['name'].rsplit('/', 1)[-1] in {'iw', 'iwconfig', 'iwlist', 'wpa_cli', 'wpa_supplicant'}])
PY
```

This reports **54** generic entries, one LZ4 block, five executable regular
files (`init`, `bin/busybox`, `bin/dropbear`, `bin/restart2`, `bin/wpss-once`),
and **276** BusyBox applets. `/bin/ip` and other `/bin/*` links invoke
`/bin/busybox`; `ip`, `ifconfig`, `route`, `nc` and `wget` are available,
but `iw`, `iwconfig`, `iwlist`, `iwpriv`, `wpa_cli`, `wpa_supplicant` and
`hostapd` are **not** applets. The BusyBox SHA-256 is
`c2f279d1d5640a0f327890d41cad594c0f059f3fed3f96dd72fdcc4f5e18ec02`.
The stock `vendor_boot_a` PLATFORM ramdisk has 327 entries, no scan program;
`/bin/pd-mapper`, `/bin/tqftpserv` and `/bin/rmtfs` are reconstructed from
`.xz` by init, but are QRTR/modem services, not scan clients. In the run-43
init, `PATH=/bin:/sbin` and there is no `/system` mount. The read-only
`system_dlkm_a` and `vendor_dlkm_a` mounts contain module/metadata trees, not
guest userland commands.

Independently check the **mounted** `vendor_a` from the preserved read-only
`~/phone-second-life-data/mb003/super-dump/super.img` with `dump.erofs`:

```sh
dump.erofs --offset=5678039040 --ls --path=/bin "$HOME/phone-second-life-data/mb003/super-dump/super.img"
dump.erofs --offset=5678039040 --ls --path=/bin/hw "$HOME/phone-second-life-data/mb003/super-dump/super.img"
dump.erofs --offset=5678039040 --path=/bin/wpa_cli "$HOME/phone-second-life-data/mb003/super-dump/super.img"
```

The preserved `super.img` SHA-256 is
`7307e9ff22fa4d9d0bfbf3dd0b1cf7d97c4c5de6eda3d44ff8c740e340462d8c`
(`super-dump/super.img.sha256`); the `vendor_a` offset is pinned by
`scripts/super-wlan-closure.py` and checked by the run-43 init. The actual
mount/bind success is **observed** in run 46.
The `/vendor/bin` listing has no standalone `iw`/`iwconfig`/`iwlist` (nor
`wpa_supplicant`), but does contain `/vendor/bin/wpa_cli` (152,520-byte
Android ELF), `hostapd_cli`, `sigma_dut`, `cnss_cli` and `qsh_wifi_test`;
`/vendor/bin/hw` contains Android `wpa_supplicant` (3,576,840 bytes),
`hostapd` and `android.hardware.wifi-service`. `sigma_dut` and
`wpa_supplicant` contain scan/nl80211 code, but are Android programs with
`/system/bin/linker64` and Android shared-library dependencies: the guest
has no `/system` (the OrangeFox `recovery_a` ramdisk that contains a linker
is **not** part of the run-46 normal boot). `wpa_cli` only sends requests to
a **running** `wpa_supplicant` control socket (default
`/data/vendor/wifi/wpa/sockets`); no such service/socket was started in this
guest. None of these is an invocable standalone scan client in the unchanged
session. This is an inference from the image, mount plan and ELF dependencies,
**not** a run-46 attempt to execute them. `ip link set wlan0 up` uses netlink
link control, not nl80211 scanning.

### Missing dependency and smallest host-side option (not delivered to phone)

Missing is a runnable **standalone arm64 `iw`** (nl80211 CLI) and its runtime:
`libnl-3.so.200`, `libnl-genl-3.so.200`, and an arm64 ELF loader/libc.
For a reproducible independent userspace without Android, the host cache at
`~/sm7635-build/wlan-tools/apk/` holds Alpine **v3.21/main/aarch64**
`iw-6.9-r0.apk` (SHA-256
`2a1664f4613318e233bd36885f5878df8242a6959a5c7105f9b67b2648d2bac6`),
`libnl3-3.11.0-r0.apk` (SHA-256
`a5210a2d84870c46b8184214bd72f14829a766027a138015db87d55e588c029a`)
and `musl-1.2.5-r12.apk` (SHA-256
`f37e73d41880bbc653b771c7d8962c8739bff773503f5155c14fab1bd7c4d52f`).
These exact package versions and checksums are the **host-side source**, not
a claim that the packages are on the guest. Extract only `usr/sbin/iw`,
`usr/lib/libnl-3.so.200.26.0`, `usr/lib/libnl-genl-3.so.200.26.0` (with
SONAME links), and `lib/ld-musl-aarch64.so.1`; `readelf -d` on `iw` confirms
those two libnl SONAMEs plus musl libc, and `readelf -l` confirms the musl
interpreter. The extracted cache at `~/sm7635-build/wlan-tools/bundle/`
matched the APK file contents byte-for-byte; host-only
`qemu-aarch64 -L "$HOME/sm7635-build/wlan-tools/bundle" -E LD_LIBRARY_PATH=/lib "$HOME/sm7635-build/wlan-tools/bundle/bin/iw" --version`
returned `iw version 6.9` (exit 0). This checks loading, **not** nl80211 or
a device scan.

The least image-invasive option for a *separately authorized* session is an
SSH-streamed, SHA-checked four-file `iw`/musl/libnl bundle into guest RAM,
with a private loader/library search path; no existing guest image or kernel
config change is inherent to this option. It depends on the unchanged run-43
key-only SSH/NCM guest, writable RAM rootfs and the already loaded stock
`rfkill.ko`/`cfg80211.ko`/`qca_cld3_qca6750.ko` WLAN closure and registered
`wlan0`; whether that stock driver actually serves a scan is **unmeasured**.
The alternative of embedding even a compact four-file tar.xz in `init_boot`
is **not** a trivial drop-in: the run-43 LZ4 HC-12 frame is 2,097,145 bytes
with only 20,487 bytes before the stock signed-tail limit 2,117,632. A
host-only counterfactual using `build-init-boot-vendor-modules-payload.py`'s
LZ4 encoder made the compressed frame ~2,565,386 bytes after adding a
466,388-byte tar.xz of these files; it does not fit. That alternative needs
a **different, verified** image/layout or reduction with the same stock
boot/config and closure; it is not built or authorized here.

The run-46 permission/rollback is complete. A later live USB-SSH scan needs
its **own** issue, recorded physical authorization and fresh image-reuse gate;
an ephemeral transferred client would not itself require a different image,
provided the unchanged image is still permitted at that gate. If transfer is
not authorized or reuse is refused, a different verified image/approval is
required. No transfer, scan, association, credential access or live stop rule
belongs to #132.
