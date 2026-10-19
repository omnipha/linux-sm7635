#!/usr/bin/env bash
# Compare a baseline build against the read-only device reference artifacts.
#
#   DEVICE_CONFIG  on-device /proc/config.gz   (default: mb003 capture)
#   DEVICE_FDT     on-device live FDT          (default: mb003 capture)
#   WORK           build directory used by build-baseline.sh
#
# Writes $WORK/out/comparison.txt. Never modifies the reference artifacts and
# never writes into this repository.

set -euo pipefail
export LC_ALL=C

DEVICE_CONFIG=${DEVICE_CONFIG:-$HOME/phone-second-life-data/mb003/config.gz}
DEVICE_FDT=${DEVICE_FDT:-$HOME/phone-second-life-data/mb003/dtb/live-fdt.dtb}
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out

[ -f "$DEVICE_CONFIG" ] || { echo "missing $DEVICE_CONFIG" >&2; exit 1; }
[ -f "$DEVICE_FDT" ] || { echo "missing $DEVICE_FDT" >&2; exit 1; }
[ -f "$OUT/.config" ] || { echo "missing $OUT/.config; run build-baseline.sh" >&2; exit 1; }
command -v fdtget >/dev/null || { echo "missing fdtget (dtc package)" >&2; exit 1; }

report=$OUT/comparison.txt
: >"$report"
say() { printf '%s\n' "$*" | tee -a "$report"; }

say "# baseline comparison $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say

# --- board identification ---------------------------------------------------
# model/compatible of the root node. fdtget reads the property directly, so
# nested nodes named "model" cannot confuse the match.
fdt_model=$(fdtget -t s "$DEVICE_FDT" / model 2>/dev/null || true)
fdt_compat=$(fdtget -t s "$DEVICE_FDT" / compatible 2>/dev/null || true)
say "## live FDT"
say "model: $fdt_model"
say "compatible: $fdt_compat"
say
say "## built devicetrees (matched by content, not by filename)"

matched=0
for dtb in "$OUT"/*.dtb "$OUT"/*.dtbo; do
	[ -f "$dtb" ] || continue
	m=$(fdtget -t s "$dtb" / model 2>/dev/null || true)
	c=$(fdtget -t s "$dtb" / compatible 2>/dev/null || true)
	flag=" "
	if [ "$m" = "$fdt_model" ] && [ "$c" = "$fdt_compat" ]; then
		flag="*"
		matched=$((matched + 1))
	fi
	say "$flag $(basename "$dtb")"
	say "    model: $m"
	say "    compatible: $c"
done
say
say "board-dt matches: $matched"
say

# --- config comparison --------------------------------------------------------
dev=$OUT/device.config
zcat "$DEVICE_CONFIG" | grep -E '^(CONFIG_|# CONFIG_)' | sort >"$dev"
built=$(grep -E '^(CONFIG_|# CONFIG_)' "$OUT/.config" | sort)

only_dev=$(comm -23 "$dev" <(printf '%s\n' "$built"))
only_built=$(comm -13 "$dev" <(printf '%s\n' "$built"))
say "## config"
say "device config symbols: $(wc -l <"$dev")"
say "built config symbols:  $(printf '%s\n' "$built" | wc -l)"
say "identical:             $(comm -12 "$dev" <(printf '%s\n' "$built") | wc -l)"
say "device-only or changed lines: $(printf '%s\n' "$only_dev" | grep -c . || true)"
say "built-only or changed lines:  $(printf '%s\n' "$only_built" | grep -c . || true)"
say
say "### device-only or changed lines"
printf '%s\n' "$only_dev" | tee -a "$report"
say
say "### built-only or changed lines"
printf '%s\n' "$only_built" | tee -a "$report"
