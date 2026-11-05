#!/usr/bin/env python3
import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "docs" / "persistent-root-device-checklist.md"
GATES = ("root_carrier", "usb_ssh_rescue", "guard", "filesystem_policy", "marker_persistence")
PLACEHOLDERS = {"", "unknown", "none", "n/a", "tbd", "unverified"}


def text(value: object) -> bool:
    return isinstance(value, str) and value == value.strip() and value.lower() not in PLACEHOLDERS


def fields(value: object, expected: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def screen(data: object) -> bool:
    if not fields(data, {"device", "evidence", "plan"}) or not isinstance(data, dict):
        return False
    device = data["device"]
    evidence = data["evidence"]
    plan = data["plan"]
    if not text(device) or not isinstance(evidence, dict) or set(evidence) != set(GATES):
        return False
    for gate in GATES:
        item = evidence[gate]
        if not fields(item, {"status", "device", "source", "detail"}):
            return False
        if (item["status"] != "measured" or item["device"] != device
                or not text(item["source"]) or not text(item["detail"])):
            return False
    if not fields(plan, {"userdata_action", "owner_approval", "operations"}):
        return False
    action = plan["userdata_action"]
    approval = plan["owner_approval"]
    if action not in ("none", "erase", "format"):
        return False
    if action != "none":
        if not fields(approval, {"device", "action", "explicit", "source"}):
            return False
        if (approval["device"] != device or approval["action"] != action
                or approval["explicit"] is not True or not text(approval["source"])):
            return False
    elif approval is not None:
        return False
    operations = plan["operations"]
    if not isinstance(operations, list):
        return False
    captures: set[str] = set()
    boots: set[str] = set()
    current = None
    guard_confirmed = False
    marker_written = False
    for operation in operations:
        if not isinstance(operation, dict):
            return False
        kind = operation.get("kind")
        boot = operation.get("boot")
        if not text(boot):
            return False
        if not isinstance(boot, str):
            return False
        if kind == "capture":
            if (not fields(operation, {"kind", "boot", "armed"})
                    or operation["armed"] is not True or boot in captures or boot in boots):
                return False
            captures.add(boot)
        elif kind == "reboot":
            if not fields(operation, {"kind", "boot"}) or boot not in captures or boot in boots:
                return False
            boots.add(boot)
            current = boot
            guard_confirmed = False
        elif kind == "guard":
            if (not fields(operation, {"kind", "boot", "confirmed", "unacknowledged", "deadline_safe"})
                    or boot != current or operation["confirmed"] is not True
                    or operation["unacknowledged"] is not True
                    or operation["deadline_safe"] is not True):
                return False
            guard_confirmed = True
        elif kind == "read":
            if (not fields(operation, {"kind", "boot", "fail_closed"}) or boot != current
                    or not guard_confirmed or operation["fail_closed"] is not True):
                return False
        elif kind == "marker":
            if (not fields(operation, {"kind", "boot", "ssh_calls"}) or boot != current
                    or not guard_confirmed or marker_written or type(operation["ssh_calls"]) is not int
                    or operation["ssh_calls"] != 1):
                return False
            marker_written = True
        else:
            return False
    return True


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def document_fixture() -> dict[str, Any]:
    content = CHECKLIST.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
    if len(blocks) != 1:
        raise ValueError("expected exactly one JSON fixture")
    fixture = json.loads(blocks[0], object_pairs_hook=unique_object)
    if not isinstance(fixture, dict):
        raise TypeError("fixture is not an object")
    return fixture


def synthetic() -> dict[str, Any]:
    evidence = {
        gate: {"status": "measured", "device": "synthetic", "source": f"synthetic:{gate}",
               "detail": "fictional measurement"}
        for gate in GATES
    }
    operations = [
        {"kind": "capture", "boot": "boot-1", "armed": True},
        {"kind": "reboot", "boot": "boot-1"},
        {"kind": "guard", "boot": "boot-1", "confirmed": True,
         "unacknowledged": True, "deadline_safe": True},
        {"kind": "marker", "boot": "boot-1", "ssh_calls": 1},
        {"kind": "read", "boot": "boot-1", "fail_closed": True},
        {"kind": "capture", "boot": "boot-2", "armed": True},
        {"kind": "reboot", "boot": "boot-2"},
        {"kind": "guard", "boot": "boot-2", "confirmed": True,
         "unacknowledged": True, "deadline_safe": True},
        {"kind": "read", "boot": "boot-2", "fail_closed": True},
    ]
    return {"device": "synthetic", "evidence": evidence,
            "plan": {"userdata_action": "none", "owner_approval": None, "operations": operations}}


class ChecklistTests(unittest.TestCase):
    def test_mb005_seed_fixture_is_blocked(self) -> None:
        data = document_fixture()
        self.assertEqual(data["device"], "mb005")
        self.assertEqual(data["evidence"]["root_carrier"]["status"], "reported")
        self.assertEqual(data["evidence"]["root_carrier"]["source"], "omnipha/agents@9c8a27a:K5")
        for gate in GATES[1:]:
            self.assertEqual(data["evidence"][gate]["status"], "open")
        self.assertEqual(data["evidence"]["usb_ssh_rescue"]["source"], "omnipha/agents@9c8a27a:K12")
        self.assertEqual(data["plan"], {"userdata_action": "none", "owner_approval": None, "operations": []})
        self.assertFalse(screen(data))

    def test_synthetic_positive_is_not_device_evidence(self) -> None:
        self.assertTrue(screen(synthetic()))

    def test_all_gates_need_same_device_measured_evidence(self) -> None:
        for gate in GATES:
            for mutation in ("missing", "reported", "open", "refuted", "unknown", "other_device", "no_source"):
                with self.subTest(gate=gate, mutation=mutation):
                    data = synthetic()
                    if mutation == "missing":
                        del data["evidence"][gate]
                    elif mutation == "other_device":
                        data["evidence"][gate]["device"] = "another-device"
                    elif mutation == "no_source":
                        data["evidence"][gate]["source"] = " "
                    else:
                        data["evidence"][gate]["status"] = mutation
                    self.assertFalse(screen(data))

    def test_rejects_malformed_or_extra_fields(self) -> None:
        invalid_values: list[Any] = [None, [], {}, {"device": "synthetic"}]
        for invalid in invalid_values:
            self.assertFalse(screen(invalid))
        for field in ("device", "evidence", "plan"):
            data = synthetic()
            data[field] = None
            self.assertFalse(screen(data))
        data = synthetic()
        data["evidence"]["extra"] = copy.deepcopy(data["evidence"][GATES[0]])
        self.assertFalse(screen(data))
        data = synthetic()
        data["evidence"][GATES[0]]["extra"] = True
        self.assertFalse(screen(data))
        with self.assertRaises(ValueError):
            json.loads('{"x": 1, "x": 2}', object_pairs_hook=unique_object)

    def test_erase_and_format_require_explicit_matching_approval(self) -> None:
        for action in ("erase", "format"):
            with self.subTest(action=action):
                data = synthetic()
                data["plan"]["userdata_action"] = action
                self.assertFalse(screen(data))
                approval = {"device": "synthetic", "action": action,
                            "explicit": True, "source": "synthetic-owner-approval"}
                data["plan"]["owner_approval"] = approval
                self.assertTrue(screen(data))
                for field, value in (("device", "other"), ("action", "other"),
                                     ("explicit", False), ("source", "")):
                    changed = copy.deepcopy(data)
                    changed["plan"]["owner_approval"][field] = value
                    self.assertFalse(screen(changed))
        data = synthetic()
        data["plan"]["userdata_action"] = "unlock"
        self.assertFalse(screen(data))

    def test_capture_armed_before_every_reboot(self) -> None:
        for index in (0, 5):
            data = synthetic()
            data["plan"]["operations"][index]["armed"] = False
            self.assertFalse(screen(data))
            data = synthetic()
            del data["plan"]["operations"][index]
            self.assertFalse(screen(data))
        data = synthetic()
        ops = data["plan"]["operations"]
        ops[0], ops[1] = ops[1], ops[0]
        self.assertFalse(screen(data))

    def test_single_marker_call_and_guard_before_reads(self) -> None:
        data = synthetic()
        data["plan"]["operations"][3]["ssh_calls"] = 2
        self.assertFalse(screen(data))
        data = synthetic()
        data["plan"]["operations"][3]["ssh_calls"] = True
        self.assertFalse(screen(data))
        data = synthetic()
        data["plan"]["operations"].insert(4, copy.deepcopy(data["plan"]["operations"][3]))
        self.assertFalse(screen(data))
        for field in ("confirmed", "unacknowledged", "deadline_safe"):
            data = synthetic()
            data["plan"]["operations"][2][field] = False
            self.assertFalse(screen(data))
        data = synthetic()
        data["plan"]["operations"].insert(2, {"kind": "read", "boot": "boot-1", "fail_closed": True})
        self.assertFalse(screen(data))
        data = synthetic()
        data["plan"]["operations"][4]["fail_closed"] = False
        self.assertFalse(screen(data))
        data = synthetic()
        data["plan"]["operations"][7]["boot"] = "boot-1"
        self.assertFalse(screen(data))
        data = synthetic()
        del data["plan"]["operations"][7]
        self.assertFalse(screen(data))

    def test_no_mknod_or_unknown_operations(self) -> None:
        for kind in ("mknod", "unknown"):
            data = synthetic()
            data["plan"]["operations"].append({"kind": kind, "boot": "boot-2"})
            self.assertFalse(screen(data))


if __name__ == "__main__":
    unittest.main(verbosity=2)
