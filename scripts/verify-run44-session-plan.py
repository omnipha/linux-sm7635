#!/usr/bin/env python3
"""Synthetic, host-only gate for the #127 physical coordinator handoff."""

from copy import deepcopy

IMAGE = "0f998e29fa87037dd1c0c474f4e9eccdb405fa75fb21bfaf0743c351594bb3aa"
PIN = "[172.16.42.2]:22 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA2ioqI4txcs3PSJWvcgSd/qBuDuCC50OIvIpKsjrjql"
ORDER = (
    "image_gate", "known_hosts", "listener", "host_address", "flash", "enumerate",
    "route", "ssh", "selftest", "keep", "modem", "wpss", "ready", "pre_action",
    "iw_probe", "iw_dev", "action", "result", "post_action", "rollback", "decision",
)


def require(ok):
    if not ok:
        raise ValueError("run-44 handoff rejected")


def check(events):
    require(tuple(name for name, _, _ in events) == ORDER)
    times = {name: t for name, t, _ in events}
    values = {name: value for name, _, value in events}
    require(all(isinstance(t, (int, float)) for t in times.values()))
    require(list(times.values()) == sorted(times.values()))
    require(values["image_gate"] == (IMAGE, 8388608, "verified stock five", "approval and unused"))
    require(values["known_hosts"] == PIN and values["listener"] == "running")
    require(times["listener"] < times["flash"] and times["known_hosts"] < times["flash"])
    require(values["host_address"] == "172.16.42.1/24; unmanaged")
    require(values["flash"] == (IMAGE, "init_boot_a", "once"))
    require(values["enumerate"] == "NCM" and values["route"] == "link and route pinned")
    require(times["flash"] < times["enumerate"] <= times["route"] < times["ssh"])
    require(values["ssh"] == ("key-only", "new boot ID", "pinned host key"))
    require(values["selftest"] == ("same boot ID", "fresh post-start kmsg line", "ok true"))
    require(values["keep"] == "/run/keep" and 0 < times["keep"] < 150)
    require(values["modem"] == ("offline guard", "one start", "running", "DMS connected"))
    require(values["wpss"] == ("one invocation", "exit 0", "node precheck passed",
                                "one 25 s ON hold", "one wpss_boot=1", "remoteproc3 running"))
    require(values["ready"] == ("FW-ready event", "wlan0 present", "idle callback 0"))
    require(values["pre_action"] == ("sysfs flags+operstate", "kmsg offset", "live capture"))
    require(values["iw_probe"] in ("applet present", "applet absent"))
    require(values["iw_dev"] in ("phy reported", "no phy", "unavailable"))
    require(values["iw_dev"] == "unavailable" if values["iw_probe"] == "applet absent"
            else values["iw_dev"] != "unavailable")
    command = "scan" if values["iw_dev"] == "phy reported" else "link up"
    require(values["action"] == (command, 20, 1, "guest binary", "once"))
    exit_code, output = values["result"]
    require(isinstance(exit_code, int) and 0 <= exit_code <= 255)
    require(output in ("BSSID/frequency lines", "named error", "empty", "link up ok"))
    present, flags, operstate, new_fatal, new_crash, new_idle = values["post_action"]
    require(present in (True, False) and flags is not None and operstate is not None)
    require(all(isinstance(n, int) and n >= 0 for n in (new_fatal, new_crash, new_idle)))
    require(values["rollback"] == ("stock init_boot_a restored", "five stock hashes",
                                   "pstore before Android"))
    if not present or new_fatal or new_crash or new_idle:
        outcome = "c"
    elif command == "scan" and exit_code == 0 and output == "BSSID/frequency lines":
        outcome = "a"
    elif output == "named error" or command == "link up":
        outcome = "b"
    else:
        outcome = "gap"
    require(values["decision"] == outcome)
    return outcome


def baseline():
    return [
        ("image_gate", -10, (IMAGE, 8388608, "verified stock five", "approval and unused")),
        ("known_hosts", -9, PIN),
        ("listener", -8, "running"),
        ("host_address", -7, "172.16.42.1/24; unmanaged"),
        ("flash", 0, (IMAGE, "init_boot_a", "once")),
        ("enumerate", 18, "NCM"),
        ("route", 25, "link and route pinned"),
        ("ssh", 31, ("key-only", "new boot ID", "pinned host key")),
        ("selftest", 33, ("same boot ID", "fresh post-start kmsg line", "ok true")),
        ("keep", 48, "/run/keep"),
        ("modem", 66, ("offline guard", "one start", "running", "DMS connected")),
        ("wpss", 138, ("one invocation", "exit 0", "node precheck passed",
                       "one 25 s ON hold", "one wpss_boot=1", "remoteproc3 running")),
        ("ready", 160, ("FW-ready event", "wlan0 present", "idle callback 0")),
        ("pre_action", 190, ("sysfs flags+operstate", "kmsg offset", "live capture")),
        ("iw_probe", 191, "applet absent"),
        ("iw_dev", 191, "unavailable"),
        ("action", 192, ("link up", 20, 1, "guest binary", "once")),
        ("result", 193, (0, "link up ok")),
        ("post_action", 194, (True, "0x1002", "down", 0, 0, 0)),
        ("rollback", 250, ("stock init_boot_a restored", "five stock hashes",
                           "pstore before Android")),
        ("decision", 251, "b"),
    ]


def fixtures():
    base = baseline()
    yield "fallback (iw absent; link up is not a scan result)", True, base
    scan = deepcopy(base)
    scan[14] = ("iw_probe", 191, "applet present")
    scan[15] = ("iw_dev", 191, "phy reported")
    scan[16] = ("action", 192, ("scan", 20, 1, "guest binary", "once"))
    scan[17] = ("result", 193, (0, "BSSID/frequency lines"))
    scan[20] = ("decision", 251, "a")
    yield "scan results and wlan0 persists", True, scan
    error = deepcopy(scan)
    error[17] = ("result", 193, (1, "named error"))
    error[20] = ("decision", 251, "b")
    yield "named nl80211 error", True, error
    timeout = deepcopy(error)
    timeout[17] = ("result", 213, (124, "named error"))
    timeout[18] = ("post_action", 214, (True, "0x1002", "down", 0, 0, 0))
    yield "20 s timeout is a named blocker, not a second scan", True, timeout
    crash = deepcopy(scan)
    crash[18] = ("post_action", 194, (True, "0x1002", "down", 0, 1, 0))
    crash[20] = ("decision", 251, "c")
    yield "new crash line stops the session", True, crash
    vanished = deepcopy(scan)
    vanished[18] = ("post_action", 194, (False, "unavailable", "unavailable", 0, 0, 0))
    vanished[20] = ("decision", 251, "c")
    yield "wlan0 vanished stops the session", True, vanished
    idle = deepcopy(scan)
    idle[18] = ("post_action", 194, (True, "0x1002", "down", 0, 0, 1))
    idle[20] = ("decision", 251, "c")
    yield "new idle-timeout line stops the session", True, idle
    for label, index, value in (
        ("wrong measured SHA", 0, ("8b62520f", 8388608, "verified stock five", "approval and unused")),
        ("no pinned host key", 1, "unknown key"),
        ("listener absent", 2, "stopped"),
        ("second flash", 4, (IMAGE, "init_boot_a", "twice")),
        ("unverified route", 6, "route missing"),
        ("wrong SSH boot", 7, ("key-only", "stale boot ID", "pinned host key")),
        ("stale capture marker", 8, ("same boot ID", "stale line", "ok true")),
        ("missing keep", 9, "absent"),
        ("modem restart", 10, ("offline guard", "two starts", "running", "DMS connected")),
        ("second WPSS write", 11, ("one invocation", "exit 0", "node precheck passed",
                                   "one 25 s ON hold", "two wpss_boot=1", "remoteproc3 running")),
        ("idle callback before command", 12, ("FW-ready event", "wlan0 present", "idle callback 1")),
        ("scan on absent phy", 16, ("scan", 20, 1, "guest binary", "once")),
        ("unbounded action", 16, ("link up", 40, 1, "guest binary", "once")),
        ("host binary", 16, ("link up", 20, 1, "host binary", "once")),
        ("no pstore before Android", 19, ("stock init_boot_a restored", "five stock hashes", "pstore lost")),
    ):
        changed = deepcopy(base)
        changed[index] = (changed[index][0], changed[index][1], value)
        yield label, False, changed
    early_keep = deepcopy(base)
    early_keep[9] = ("keep", 150, "/run/keep")
    yield "keep at unchanged recovery deadline", False, early_keep
    preboot_route = deepcopy(base)
    preboot_route[6] = ("route", -6, "link and route pinned")
    yield "pretend route live before gadget enumeration", False, preboot_route
    repeated = deepcopy(base)
    repeated.insert(17, ("action", 193, ("scan", 20, 1, "guest binary", "once")))
    yield "second userspace action", False, repeated
    wrong_outcome = deepcopy(scan)
    wrong_outcome[20] = ("decision", 251, "b")
    yield "scan result mislabeled error", False, wrong_outcome


def main():
    for label, expected, events in fixtures():
        try:
            check(events)
            passed = True
        except ValueError:
            passed = False
        if passed != expected:
            raise SystemExit(f"unexpected fixture result: {label}")
        print(f"{label}: {'PASS' if passed else 'rejected'}")
    print("synthetic only: no device, SSH, flash or scan")


if __name__ == "__main__":
    main()
