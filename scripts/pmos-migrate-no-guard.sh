#!/bin/busybox sh
set -eu
BB=${BB:-/bin/busybox}
root=$1
marker="$root/etc/.omnipha-no-guard-migrated"

radio_target="$root/usr/libexec/omnipha/pmos-radio-bringup-fresh-boot.sh"
post_target="$root/usr/libexec/omnipha/pmos-self-post-fresh-boot.sh"
hook_target="$root/etc/local.d/10-omnipha-self-stage.start"
bad_radio=d7b74c2450fec86b17f325cab4100cc19c0a6319b8f9c5baa73e83a9acb0bfd3
work="$root/run/no-guard-work"
published=

for target in "$radio_target" "$post_target" "$hook_target"; do
	[ -e "$target" ] || [ -L "$target" ] || continue
	[ -f "$target" ] && [ ! -L "$target" ] || exit 1
done
if [ -e "$radio_target" ]; then
	radio_sum=$($BB sha256sum "$radio_target") || exit 1
	[ "${radio_sum%% *}" != "$bad_radio" ] || exit 3
fi
if [ -e "$marker" ] || [ -L "$marker" ]; then
	[ -f "$marker" ] && [ ! -L "$marker" ] || exit 1
	exit 0
fi

[ ! -e "$work" ] && [ ! -L "$work" ] || exit 1
$BB mkdir -m 700 "$work" || exit 1
trap '$BB rm -rf "$work"' EXIT

needs_migration() {
	case "$1" in
	hook) $BB grep -q 'guard\.sh watch' "$2" ;;
	*) $BB grep -q 'pid1-guard' "$2" ;;
	esac
}

transform() {
	kind=$1
	target=$2
	out=$3
	case "$kind" in
	radio)
		$BB awk '
			BEGIN { armed = 0; nonce = 0 }
			index($0, "[ \"$($BB cat /run/pid1-guard/armed") { armed = 1; next }
			armed { if (index($0, "fail '\''PID 1 guard is not armed")) armed = 0; next }
			index($0, "nonce=$($BB cat /run/pid1-guard/nonce") { nonce = 1; next }
			nonce { if ($0 ~ /^[ \t]*esac$/) nonce = 0; next }
			{
				gsub("/run/pid1-guard/root-contract.sh", "/run/pmos-root-contract.sh")
				gsub("\\$boot:\\$nonce:\\$stage", "$boot:$stage")
				gsub("this guard nonce", "this boot")
				print
			}
			END { if (armed || nonce) exit 1 }
		' "$target" > "$out" ;;
	post)
		$BB awk '
			BEGIN { trace = 0; identity = 0; guard = 0; nonce = 0; gate = 0; gnonce = 0; finished = 0 }
			/^GUARD=\/run\/pid1-guard$/ { next }
			/^trace_state\(\) \{/ { print "trace_state() { :; }"; trace = 1; next }
			trace { if (/^trace_refusal\(\) \{/) trace = 0; else next }
			index($0, "trace '\''pre check switched-root and guard identity'\''") {
				print "[ \"$($BB sha256sum /proc/1/exe | $BB cut -d '\'' '\'' -f 1)\" = \"$($BB sha256sum /bin/busybox | $BB cut -d '\'' '\'' -f 1)\" ] &&"
				print "\t[ \"$($BB stat -c '\''%d:%i'\'' /)\" = \"$($BB stat -Lc '\''%d:%i'\'' /proc/1/root)\" ] &&"
				print "\t[ -f /run/pmos-root-contract.sh ] && [ ! -L /run/pmos-root-contract.sh ] &&"
				print "\t. /run/pmos-root-contract.sh && root_contract_switched_root /proc/1/mounts /proc/1/mountinfo ||"
				print "\tdie '\''switched-root or PID 1 identity check failed'\''"
				identity = 1; next
			}
			identity { if (index($0, "trace '\''post check switched-root and guard identity'\''")) identity = 0; next }
			index($0, "trace '\''pre check guard armed and unacknowledged'\''") { guard = 1; next }
			guard { if (index($0, "trace '\''post check guard armed and unacknowledged'\''")) guard = 0; next }
			index($0, "|| contract=\"$GUARD/root-contract.sh\"") { next }
			/^guest_marker\(\) \{/ { in_marker = 1 }
			in_marker && index($0, "[ \"$($BB cat \"$GUARD/armed\"") { nonce = 1; next }
			nonce { if ($0 ~ /^[ \t]*esac$/) nonce = 0; next }
			in_marker && /^}/ { in_marker = 0 }
			/^gate_identity\(\) \{/ {
				print "gate_identity() {"
				print "\t[ \"$($BB cat /proc/sys/kernel/random/boot_id 2>/dev/null)\" = \"$boot\" ] &&"
				print "\t[ \"$($BB stat -c '\''%d:%i'\'' / 2>/dev/null)\" = \"$($BB stat -Lc '\''%d:%i'\'' /proc/1/root 2>/dev/null)\" ]"
				print "}"
				print "gate_check() { gate_identity || gate_fail '\''boot or root changed'\''; }"
				gate = 1; next
			}
			gate { if (/^gate_snapshot\(\) \{/) gate = 0; else next }
			/^gate_stage=nonce-and-radio-markers$/ { print "gate_stage=radio-markers"; gnonce = 1; next }
			gnonce { if (/^gate_dir_id=/) gnonce = 0; else next }
			/^gate_stage=ack-publication$/ { ack = 1; next }
			ack {
				if (index($0, "[ \"$gate_complete\" = 1 ] || gate_fail '\''acceptance not confirmed; ACK may still be consumed'\''")) {
					print "gate_complete=1"; finished++; ack = 0
				}
				next
			}
			{
				gsub("guard identity check passed; ", "")
				gsub("\\$boot:\\$nonce:\\$stage", "$boot:$stage")
				gsub("\\$boot:\\$gate_nonce:\\$g_stage", "$boot:$g_stage")
				gsub("; independent recovery guard remains unacknowledged", "")
				gsub("before ACK", "after startup")
				gsub("all checks passed; no ACK yet", "all checks passed")
				gsub("END \\{exit\\(NR != 1 \\|\\| ok != 1\\)\\}", "END {exit(ok != 1)}")
				print
			}
			END { if (finished != 1 || ack || trace || identity || guard || nonce || gate || gnonce) exit 1 }
		' "$target" > "$out" ;;
	hook)
		$BB awk '
			BEGIN { buffering = 0 }
			index($0, "( /bin/busybox setsid /bin/busybox sh -c '\''") { block = $0 "\n"; buffering = 1; next }
			buffering {
				block = block $0 "\n"
				if (index($0, "'\'' ") && index($0, " & )")) {
					if (!(index(block, "guard.sh watch") && index(block, "kill -TERM"))) printf "%s", block
					block = ""; buffering = 0
				}
				next
			}
			{ print }
			END { if (buffering) exit 1 }
		' "$target" > "$out" ;;
	esac
}

prepare() {
	kind=$1
	target=$2
	[ -e "$target" ] || return 0
	$BB sh -n "$target" || exit 1
	if ! needs_migration "$kind" "$target"; then
		return 0
	fi
	out="$work/$kind"
	transform "$kind" "$target" "$out" || exit 1
	$BB sh -n "$out" || exit 1
	if $BB grep -q 'pid1-guard\|guard\.sh\|\$GUARD\|/nonce\|/ack\|accepted' "$out"; then
		exit 1
	fi
	if [ "$kind" = radio ]; then
		[ "$($BB sha256sum "$out" | $BB cut -d ' ' -f 1)" != "$bad_radio" ] || exit 3
	fi
}

rollback() {
	for item in $published; do
		kind=${item%%:*}
		case "$kind" in
		radio) target=$radio_target ;;
		post) target=$post_target ;;
		hook) target=$hook_target ;;
		esac
		backup="$target.before-no-guard"
		if [ -f "$backup" ]; then
			$BB cp -p "$backup" "$target.omnipha-restore" &&
				$BB mv -f "$target.omnipha-restore" "$target" &&
				$BB rm -f "$backup"
		fi
	done
}

publish() {
	kind=$1
	target=$2
	out="$work/$kind"
	[ -f "$out" ] || return 0
	backup="$target.before-no-guard"
	[ ! -e "$backup" ] && [ ! -L "$backup" ] || return 1
	staged="$target.omnipha-new"
	[ ! -e "$staged" ] && [ ! -L "$staged" ] || return 1
	$BB cp -p "$target" "$backup" || return 1
	if $BB cp -p "$target" "$staged" && $BB cat "$out" > "$staged" &&
		$BB cmp -s "$staged" "$out" && $BB mv -f "$staged" "$target"; then
		published="$published $kind:done"
		return 0
	fi
	$BB rm -f "$staged" "$backup"
	return 1
}

prepare radio "$radio_target"
prepare post "$post_target"
prepare hook "$hook_target"

for spec in "radio $radio_target" "post $post_target" "hook $hook_target"; do
	set -- $spec
	publish "$1" "$2" || { rollback; exit 1; }
done
(umask 077; $BB touch "$marker") || { rollback; exit 1; }
