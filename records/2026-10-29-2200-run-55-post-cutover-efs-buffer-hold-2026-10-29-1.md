---
date: 2026-10-29
run: 55
issue: omnipha/linux-sm7635#155
subsystem: modem
result: inconclusive
source: README.md
---
## Run-55 post-cutover EFS buffer hold (2026-10-29, #155)

[BOOT.md](BOOT.md#run-55-measured-post-cutover-modem-hold-past-the-efs-request-155-2026-10-29)
records one coordinator-held stock-kernel session: the merged rmtfs script
restored only the two lost `/boot/modemst*` backing links, then one guarded
modem start reached `now up` and remained `running` past +73 s with QMI DMS
connected, no EFS fatal and live key-only SSH/capture. WPSS and WLAN were not
started. Run 55 is closed after coordinator-verified five-partition stock
rollback and Android; #155 is closed.
