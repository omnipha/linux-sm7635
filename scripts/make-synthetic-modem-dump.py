#!/usr/bin/env python3
import json
import pathlib
import struct
import sys

SECTOR = 512
TOTAL_SECTORS = 2880
FAT_SECTORS = 9
ROOT_SECTORS = 14
ROOT_START = (1 + 2 * FAT_SECTORS) * SECTOR
DATA_START = (1 + 2 * FAT_SECTORS + ROOT_SECTORS) * SECTOR
LABEL = b"SYNTHETIC  "


def directory_record(name, attr, cluster, size=0):
    assert len(name) == 11
    record = bytearray(32)
    record[:11] = name
    record[11] = attr
    struct.pack_into("<H", record, 26, cluster)
    struct.pack_into("<I", record, 28, size)
    return record


def map_content(soc, domain, subdomain, service, version=1):
    return json.dumps({
        "sr_domain": {"soc": soc, "domain": domain,
                      "subdomain": subdomain, "qmi_instance_id": 1},
        "sr_version": version,
        "sr_service": [{"provider": "synthetic", "service": service}],
    }, separators=(",", ":")).encode()


def make_fixture(path, case):
    assert case in {"good", "empty", "bad-json", "bad-schema", "duplicate",
                    "invalid-name", "no-image", "loop", "elsewhere", "conflict",
                    "flat", "noversion"}
    data = bytearray(TOTAL_SECTORS * SECTOR)
    boot = data[:SECTOR]
    boot[:3] = b"\xeb\x3c\x90"
    boot[3:11] = b"SYNTH88 "
    struct.pack_into("<H", boot, 11, SECTOR)
    boot[13] = 1
    struct.pack_into("<H", boot, 14, 1)
    boot[16] = 2
    struct.pack_into("<H", boot, 17, 224)
    struct.pack_into("<H", boot, 19, TOTAL_SECTORS)
    boot[21] = 0xF0
    struct.pack_into("<H", boot, 22, FAT_SECTORS)
    struct.pack_into("<H", boot, 24, 18)
    struct.pack_into("<H", boot, 26, 2)
    boot[43:54] = LABEL
    boot[54:62] = b"FAT12   "
    boot[510:512] = b"\x55\xaa"
    data[:SECTOR] = boot

    fat = bytearray(FAT_SECTORS * SECTOR)
    fat[:3] = b"\xf0\xff\xff"

    def set_cluster(cluster, value):
        index = cluster + cluster // 2
        old = fat[index] | fat[index + 1] << 8
        if cluster & 1:
            new = (old & 0x000F) | (value << 4)
        else:
            new = (old & 0xF000) | value
        fat[index:index + 2] = struct.pack("<H", new)

    for cluster in (2, 3, 4, 5, 6):
        set_cluster(cluster, 0xFFF)
    if case == "loop":
        set_cluster(4, 4)
    data[SECTOR:SECTOR + len(fat)] = fat
    data[(1 + FAT_SECTORS) * SECTOR:(1 + 2 * FAT_SECTORS) * SECTOR] = fat

    root = bytearray(ROOT_SECTORS * SECTOR)
    root[:32] = directory_record(LABEL, 0x08, 0)
    if case != "no-image":
        root[32:64] = directory_record(b"IMAGE      ", 0x10, 2)
    if case == "elsewhere":
        text = map_content("synthetic", "elsewhere", "remote", "outside")
        root[64:96] = directory_record(b"OUTSIDE JSN", 0x20, 6, len(text))
        data[DATA_START + 4 * SECTOR:DATA_START + 4 * SECTOR + len(text)] = text
    data[ROOT_START:ROOT_START + len(root)] = root

    image = bytearray(SECTOR)
    image[:32] = directory_record(b".          ", 0x10, 2)
    image[32:64] = directory_record(b"..         ", 0x10, 0)
    image[64:96] = directory_record(b"NESTED     ", 0x10, 3)
    text1 = map_content("synthetic", "domain", "modem", "a")
    text2 = map_content("synthetic", "domain", "wlan", "b")
    if case == "bad-json":
        text1 = b"{bad json"
    elif case == "bad-schema":
        text1 = json.dumps({"sr_domain": {"soc": "synthetic"},
                            "sr_version": 1, "sr_service": []}).encode()
    elif case == "conflict":
        text2 = map_content("synthetic", "domain", "modem", "b", version=2)
    elif case == "flat":
        text1 = json.dumps({
            "soc": "synthetic", "domain": "domain", "subdomain": "modem",
            "provider": "synthetic", "sr_version": 1,
            "sr_service": [{"provider": "synthetic", "service": "a",
                            "instance": 1, "qmi_instance_id": 2,
                            "service_data_valid": 1, "service_data": 7}],
        }, separators=(",", ":")).encode()
    elif case == "noversion":
        text1 = json.dumps({
            "sr_domain": {"soc": "synthetic", "domain": "domain",
                          "subdomain": "modem", "qmi_instance_id": 1},
            "sr_service": [{"provider": "synthetic", "service": "a"}],
        }, separators=(",", ":")).encode()
        text2 = json.dumps({
            "sr_domain": {"soc": "synthetic", "domain": "domain",
                          "subdomain": "wlan"},
            "sr_service": [{"provider": "synthetic", "service": "b"}],
        }, separators=(",", ":")).encode()
    if case not in ("empty", "no-image"):
        name = b"FIRST   JSN"
        if case == "invalid-name":
            name = b"BAD/NAMEJSN"
        image[96:128] = directory_record(name, 0x20, 4, len(text1))
        if case == "duplicate":
            image[128:160] = directory_record(name, 0x20, 4, len(text1))
        data[DATA_START + 2 * SECTOR:DATA_START + 2 * SECTOR + len(text1)] = text1
    data[DATA_START:DATA_START + SECTOR] = image

    nested = bytearray(SECTOR)
    nested[:32] = directory_record(b".          ", 0x10, 3)
    nested[32:64] = directory_record(b"..         ", 0x10, 2)
    if case not in ("empty", "no-image"):
        nested[64:96] = directory_record(b"SECOND  JSN", 0x20, 5, len(text2))
        data[DATA_START + 3 * SECTOR:DATA_START + 3 * SECTOR + len(text2)] = text2
    data[DATA_START + SECTOR:DATA_START + 2 * SECTOR] = nested
    path.write_bytes(data)


def main():
    if len(sys.argv) != 3:
        raise ValueError("usage: make-synthetic-modem-dump.py OUTFILE CASE "
                         "(good|empty|bad-json|bad-schema|duplicate|invalid-name|"
                         "no-image|loop|elsewhere|conflict|flat)")
    path = pathlib.Path(sys.argv[1])
    if path.exists() or path.parent.resolve() == pathlib.Path(__file__).resolve().parent:
        raise ValueError("OUTFILE must be a new path outside the repository")
    make_fixture(path, sys.argv[2])
    print(f"SYNTHETIC NON-STOCK NON-FLASHABLE fixture: {path}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, AssertionError) as exc:
        raise SystemExit(f"FAIL: {str(exc)[:200]}") from exc
