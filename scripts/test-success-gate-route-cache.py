#!/usr/bin/env python3
import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('route_cache', HERE / 'derive-route-cache-gated-ack.py')
assert spec is not None and spec.loader is not None
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
GATE_AWK_OLD = candidate.OLD_AWK
GATE_AWK_CORRECTED = candidate.NEW_AWK


def run_awk(prog, text):
    proc = subprocess.run(
        ["/bin/busybox", "awk", prog],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def main():
    real_iproute2_out = (
        "1.1.1.1 from 192.0.2.2 via 192.0.2.1 dev wlan0 uid 0 \n"
        "    cache \n"
    )

    old_result = run_awk(GATE_AWK_OLD, real_iproute2_out)
    if old_result is not False:
        raise AssertionError("reproduction failed: old awk unexpectedly accepted two-line cache output")

    corr_result = run_awk(GATE_AWK_CORRECTED, real_iproute2_out)
    if corr_result is not True:
        raise AssertionError("corrected awk failed to accept real iproute2 cache output")

    matrix = [
        ("real iproute2 with cache", real_iproute2_out, True),
        ("real iproute2 without trailing spaces", "1.1.1.1 via 192.0.2.1 dev wlan0 uid 0\n    cache\n", True),
        ("tab indented cache", "1.1.1.1 via 192.0.2.1 dev wlan0 uid 0\n\tcache\n", True),
        ("single-line output (busybox/no cache)", "1.1.1.1 via 192.0.2.1 dev wlan0 src 192.0.2.2\n", True),
        ("single-line without via", "1.1.1.1 dev wlan0 src 192.0.2.2\n", True),
        ("no trailing newline single line", "1.1.1.1 via 192.0.2.1 dev wlan0", True),
        ("no trailing newline two line", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache", True),

        ("empty string", "", False),
        ("whitespace only", "   \n\n", False),
        ("dev is eth0", "1.1.1.1 via 192.0.2.1 dev eth0 uid 0\n    cache\n", False),
        ("dev is usb0", "1.1.1.1 via 192.0.2.1 dev usb0 uid 0\n    cache\n", False),
        ("dev prefix match wlan01", "1.1.1.1 via 192.0.2.1 dev wlan01 uid 0\n    cache\n", False),
        ("missing dev keyword", "1.1.1.1 via 192.0.2.1 wlan0 uid 0\n    cache\n", False),
        ("dev at end without argument", "1.1.1.1 via 192.0.2.1 dev", False),
        ("duplicate dev wlan0 on line 1", "1.1.1.1 dev wlan0 dev wlan0\n", False),
        ("both wlan0 and eth0 dev on line 1", "1.1.1.1 dev wlan0 dev eth0\n", False),
        ("line 2 is not cache (e.g. foreign dev)", "1.1.1.1 via 192.0.2.1 dev wlan0\n    dev eth0\n", False),
        ("line 2 has trailing garbage after cache", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache foreign\n", False),
        ("three lines", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache\n    extra\n", False),
        ("four lines", "1.1.1.1 via 192.0.2.1 dev wlan0\n    cache\n    extra\n    more\n", False),
    ]

    for label, inp, expected in matrix:
        res = run_awk(GATE_AWK_CORRECTED, inp)
        if res != expected:
            raise AssertionError(f"test case '{label}' failed: got {res}, expected {expected}")

    print("pass: defect reproduction and corrected route parser matrix verified cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
