---
date: 2026-10-19
issue: omnipha/ports#3
subsystem: boot
result: inconclusive
source: BOOT.md
---
## Diagnosability of the baseline kernel

The baseline `.config` already has `CONFIG_PSTORE=y`,
`CONFIG_PSTORE_CONSOLE=y`, `CONFIG_PSTORE_PMSG=y`, `CONFIG_PSTORE_RAM=y`,
`CONFIG_SERIAL_EARLYCON=y` and `CONFIG_SERIAL_QCOM_GENI=y`. No kernel
rebuild is needed for console capture.

The reservation is the gap. `ramoops_region` in `volcano.dtsi` carries
`size = <0x0 0x200000>` and `pmsg-size = <0x200000>` but no `reg`, so no
fixed address, and no `console-size`. The stock values come from
`volcano-arca-common-overlay.dtsi`, which `volcano-qrd-pro-overlay`
includes, and that overlay is applied from `dtbo` rather than from the DTB.
The #5/#8 build tried to add
`reg = <0x0 0x81f20000 0x0 0x400000>` and `console-size = <0x200000>`
to every built DTB, but the unchanged stock `dtbo_a` could not apply to
built index 9. The #10 build instead retains the verified stock DTB blob;
`scripts/verify-bootimg.sh` checks the ramoops reservation after applying
stock overlay 65. That reservation still cannot prove that the attempted
kernel executed or that a later stock boot did not overwrite its console.

`earlycon` needs no address. The stock index-9 DTB has `chosen/stdout-path =
"/soc/qcom,qupv3_0_geni_se@ac0000/qcom,qup_uart@a94000:115200n8"` and the
driver registers `OF_EARLYCON_DECLARE(qcom_geni, "qcom,geni-debug-uart", ...)`,
so a bare `earlycon` follows the stdout path. No UART test points or
voltages were identified, so a USB-TTL adapter is not part of this setup.
`panic=-1` makes `panic()` sit and wait instead of rebooting, which keeps
the ramoops console intact until recovery reads it.
