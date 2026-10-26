#!/usr/bin/env python3
"""Run an in-memory, host-only preboot capture handoff simulation."""

import argparse
import copy

RECOVERY_DEADLINE = 150
SSH_UP_RUN40 = 120
SELFTEST_TIMEOUT = 8
BOOT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_BOOT_ID = "22222222-2222-4222-8222-222222222222"
MARKER = "sm7635_capture_selftest_" + BOOT_ID.replace("-", "") + "_synthetic113"


def require(condition):
    if not condition:
        raise ValueError("capture handoff gate failed")


def handoff(events):
    listener = False
    route = False
    preflight = False
    rebooted = False
    ssh_boot = None
    capture_boot = None
    marker = None
    offset = None
    started = None
    marker_written = False
    marker_write_at = None
    lines = []
    passed = False
    kept = False
    previous = float("-inf")
    names = []

    for name, t, value in events:
        require(isinstance(t, (int, float)) and t >= previous)
        require(name not in names)
        names.append(name)
        previous = t
        if name == "capture_start":
            require(not rebooted and t < 0 and value == "listening")
            listener = True
        elif name == "route_ready":
            require(not rebooted and t < 0 and value == ("172.16.42.1/24", "link-ready"))
            route = True
        elif name == "preflight":
            require(not rebooted and listener and route and t < 0)
            preflight = True
        elif name == "simulated_reboot":
            require(t == 0 and preflight and listener and route)
            rebooted = True
        elif name == "ssh_accept":
            require(rebooted and ssh_boot is None and t > 0 and t < RECOVERY_DEADLINE)
            require(value == BOOT_ID)
            ssh_boot = value
        elif name == "capture_ready":
            require(ssh_boot is not None and listener and t >= events[names.index("ssh_accept")][1])
            require(value == ssh_boot)
            capture_boot = value
        elif name == "selftest_start":
            require(capture_boot == ssh_boot and listener and started is None)
            require(t >= events[names.index("capture_ready")][1] and t < RECOVERY_DEADLINE)
            require(value == MARKER)
            marker = value
            offset = len(lines)
            started = t
        elif name == "marker_write":
            require(started is not None and not marker_written and t >= started
                    and t - started <= SELFTEST_TIMEOUT
                    and value == (ssh_boot, marker))
            marker_written = True
            marker_write_at = t
        elif name == "capture_line":
            require(rebooted and listener and t >= 0)
            lines.append((t, value))
        elif name == "selftest_result":
            require(started is not None and not passed and listener and capture_boot == ssh_boot)
            require(t >= started and t - started <= SELFTEST_TIMEOUT and t < RECOVERY_DEADLINE)
            require(value == {"ok": True, "boot_id": ssh_boot})
            require(marker_written and marker_write_at is not None)
            require(any(line_at >= marker_write_at and line == (ssh_boot, marker)
                        for line_at, line in lines[offset:]))
            passed = True
        elif name == "permit_keep":
            require(not kept and passed and ssh_boot == capture_boot and value == "/run/keep")
            require(t < RECOVERY_DEADLINE and t > started)
            kept = True
        else:
            raise ValueError("unknown handoff event")
    require(names == [
        "capture_start", "route_ready", "preflight", "simulated_reboot",
        "ssh_accept", "capture_ready", "selftest_start", "marker_write",
        "capture_line", "selftest_result", "permit_keep",
    ])
    require(kept)
    return events[-1][1]


def good_events():
    return [
        ("capture_start", -4, "listening"),
        ("route_ready", -3, ("172.16.42.1/24", "link-ready")),
        ("preflight", -2, None),
        ("simulated_reboot", 0, None),
        ("ssh_accept", SSH_UP_RUN40, BOOT_ID),
        ("capture_ready", 121, BOOT_ID),
        ("selftest_start", 121, MARKER),
        ("marker_write", 122, (BOOT_ID, MARKER)),
        ("capture_line", 123, (BOOT_ID, MARKER)),
        ("selftest_result", 123, {"ok": True, "boot_id": BOOT_ID}),
        ("permit_keep", 124, "/run/keep"),
    ]


def fixtures():
    events = good_events()
    yield "on-time fresh boot marker", True, events

    late_capture = copy.deepcopy(events)
    late_capture[0] = ("capture_start", 1, "listening")
    yield "late capture", False, late_capture

    late_selftest = copy.deepcopy(events)
    late_selftest[6] = ("selftest_start", 150, MARKER)
    late_selftest[7] = ("marker_write", 151, (BOOT_ID, MARKER))
    late_selftest[8] = ("capture_line", 152, (BOOT_ID, MARKER))
    late_selftest[9] = ("selftest_result", 152, {"ok": True, "boot_id": BOOT_ID})
    late_selftest[10] = ("permit_keep", 153, "/run/keep")
    yield "late selftest and keep", False, late_selftest

    late_keep = copy.deepcopy(events)
    late_keep[10] = ("permit_keep", 150, "/run/keep")
    yield "late keep", False, late_keep

    wrong_boot = copy.deepcopy(events)
    wrong_boot[7] = ("marker_write", 122, (OTHER_BOOT_ID, MARKER))
    wrong_boot[8] = ("capture_line", 123, (OTHER_BOOT_ID, MARKER))
    yield "marker from another boot", False, wrong_boot

    stale_marker = copy.deepcopy(events)
    stale_marker[6] = ("capture_line", 121, (BOOT_ID, MARKER))
    stale_marker[7] = ("selftest_start", 122, MARKER)
    stale_marker[8] = ("marker_write", 123, (BOOT_ID, MARKER))
    yield "marker only before selftest", False, stale_marker

    no_selftest = copy.deepcopy(events)
    no_selftest[9] = ("selftest_result", 123, {"ok": False, "boot_id": BOOT_ID})
    yield "keep without passing selftest", False, no_selftest

    no_route = copy.deepcopy(events)
    no_route[1] = ("route_ready", -3, ("172.16.42.1/24", "link-down"))
    yield "link down at preflight", False, no_route


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    for label, should_pass, events in fixtures():
        try:
            keep_at = handoff(events)
            passed = True
        except ValueError:
            passed = False
        if passed != should_pass:
            raise SystemExit(f"unexpected fixture result: {label}")
        print(f"{label}: {'PASS' if passed else 'rejected'}")
    if args.report:
        print(f"run-40 SSH at uptime {SSH_UP_RUN40} s; recovery at {RECOVERY_DEADLINE} s")
        print(f"SSH + capture-ready 1 s + selftest 2 s + keep 1 s: keep at {keep_at} s")
        print(f"residual after SSH: {RECOVERY_DEADLINE - SSH_UP_RUN40} s; "
              f"remaining after keep: {RECOVERY_DEADLINE - keep_at} s")
        print("synthetic prediction only; no physical session or image")


if __name__ == "__main__":
    main()
