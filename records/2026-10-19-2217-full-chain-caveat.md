---
date: 2026-10-19
issue: omnipha/ports#3
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Full-chain caveat

The standing flash gate does **not** authorize any partition writes. This
issue does not authorize any physical execution. The three-image chain below
is superseded historical context, not a procedure to run as part of this issue.

The host `fastboot` is 34.0.5 and its `boot` command downloads a single
image, so it cannot replace `init_boot` and `vendor_boot`. The bounded test
team wrote and restored all three slot-A images; `boot` and `vendor_boot`
partitions are 96MiB each and `init_boot` is 8MiB.

The verified backups are `~/phone-second-life-data/mb003/parts/`, both
slots, recorded in `parts.sha256`. Slot `_a` and slot `_b` are byte
identical for these four partitions:

| backup | sha256 |
| --- | --- |
| `boot_a.img`, `boot_b.img` | `197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d` |
| `init_boot_a.img`, `init_boot_b.img` | `baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193` |
| `vendor_boot_a.img`, `vendor_boot_b.img` | `237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253` |
| `dtbo_a.img`, `dtbo_b.img` | `759813dbfd94f4a4124b08afb2c9ef85f1f9afb7cdca9829be2558ffde13c992` |

Only slot `_a` was written during the historical attempt. Slot `_b` remained
untouched and `dtbo` was not written.

The expected USB evidence is the configfs gadget enumerating as
`18d1:4ee2`, with NCM on `usb0` at `172.16.42.2/24` and ECM on `usb1` at
`172.16.43.2/24`. The serial string is the literal `sm7635`. The debug
ramdisk now includes a key-only dropbear sshd listening at `172.16.42.2:22`;
the expected result is both the gadget and an SSH login over NCM. No SSH
observation has been made on the physical device as part of this issue.

The server allows root with the single ed25519 public key from the build
host's `~/.ssh/id_ed25519.pub` (or `$PUBKEY`) packed as
`/root/.ssh/authorized_keys`. Password and PAM authentication are compiled
out; no password or lockscreen exists in the initramfs. Its host key is
generated into RAM on first connection, so it changes on every boot. No
private key is shipped in the ramdisk or committed. The console shell
remains a fallback debug path if the gadget or SSH does not work.

The earlier test plan proposed prompt preservation of ramoops before a later
stock boot could overwrite it; the 2026-10-20 capture instead contains only
stock/recovery 6.1.84 markers. `nt_kmsg` is another host-only source of
kernel evidence, not a guaranteed record of the attempted boot. Any future
physical observation and restoration require the coordinator's separate
bounded authorization. Slot B, dtbo, vbmeta and userdata are not part of
this issue.
