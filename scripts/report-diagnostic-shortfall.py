#!/usr/bin/env python3
import argparse
import importlib.util
import pathlib
import re
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).parent
BASE_IMAGE_SIZE = 37198336
BASE_GZIP_SIZE = 14782792
PAYLOAD_BOUND = 13967360
KALLSYMS_ESTIMATE = 546197
NLS_ESTIMATE = 275810
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--gz", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--replay-elf", required=True)
    parser.add_argument("--replay-image", required=True)
    parser.add_argument("--map", required=True)
    args = parser.parse_args()
    analyzer = load("analyze-gzip-excess.py", "gzip_excess")

    image = pathlib.Path(args.image).read_bytes()
    packed = pathlib.Path(args.gz).read_bytes()
    config = analyzer.config_values(pathlib.Path(args.config).read_text())
    require(packed[:10] == GZIP_HEADER, "payload does not carry the stock gzip header")
    expected = (GZIP_HEADER + analyzer.raw_deflate(image) +
                struct.pack("<II", zlib.crc32(image) & 0xFFFFFFFF, len(image)))
    require(packed == expected, "zlib level 9 does not reproduce the payload bytes")
    require("CONFIG_KALLSYMS_ALL" not in config and config.get("CONFIG_NLS") == "y",
            "config is not KALLSYMS_ALL off with NLS forced on")
    for symbol in ("CONFIG_EXT4_FS", "CONFIG_F2FS_FS", "CONFIG_ANDROID_BINDER_IPC",
                   "CONFIG_USB_GADGET"):
        require(config.get(symbol) == "y", symbol + " is not on")

    replay = pathlib.Path(args.replay_image).read_bytes()
    require(len(replay) == len(image), "relinked Image length differs")
    differing = [index for index in range(len(image)) if image[index] != replay[index]]
    notes = [s for s in analyzer.image_sections(args.replay_elf) if s[0] == ".notes"][0]
    require(all(notes[1] <= index < notes[1] + notes[2] for index in differing),
            "relinked Image differs outside the .notes build-id")

    size = len(packed)
    shortfall = size - PAYLOAD_BOUND
    kallsyms_delta = BASE_GZIP_SIZE - size
    print(f"Image: {len(image)} bytes (#55: {BASE_IMAGE_SIZE}, delta {len(image) - BASE_IMAGE_SIZE})")
    print(f"payload: {size} bytes, bound {PAYLOAD_BOUND}, "
          f"{'over' if shortfall > 0 else 'under'} by {abs(shortfall)}")
    print(f"relink: {len(differing)} of {len(image)} bytes differ, all inside .notes (build-id)")
    print(f"KALLSYMS_ALL=n measured: {BASE_GZIP_SIZE} -> {size} = -{kallsyms_delta} gzip bytes "
          f"(#57 estimate {KALLSYMS_ESTIMATE}, difference {kallsyms_delta - KALLSYMS_ESTIMATE:+d})")

    ranges = analyzer.attribute_crc(analyzer.parse_map(args.map, len(image)))
    groups = {
        "fs/nls/ (all)": ("fs/nls/",),
        "fs/nls/ CJK codepages 932/936/949/950": (
            "fs/nls/nls_cp932.o", "fs/nls/nls_cp936.o", "fs/nls/nls_cp949.o", "fs/nls/nls_cp950.o"),
        "fs/nls/nls_base.o": ("fs/nls/nls_base.o",),
    }
    print("NLS=n is not buildable: USB_GADGET=y, F2FS_FS=y and SCSI_UFSHCD=y select NLS")
    saved = {}
    for label, prefixes in groups.items():
        selected = analyzer.merge_ranges([
            (offset, length) for offset, length, output, owner, section in ranges
            if any(owner.startswith(prefix) for prefix in prefixes)])
        raw = sum(length for _, length in selected)
        saving = size - analyzer.gzip_size(masked(image, selected))
        saved[label] = (raw, saving)
        print(f"  zero-mask estimate on the new Image, {label}: raw {raw}, gzip -{saving}")
    nls_raw, nls_saving = saved["fs/nls/ (all)"]
    print(f"NLS gzip estimate {nls_saving} (#57 estimate {NLS_ESTIMATE}); "
          f"would leave {shortfall - nls_saving:+d} against the bound if NLS were removable")
    print(f"non-selected NLS_CODEPAGE_*/NLS_ISO8859_*/NLS_MAC_* symbols set: "
          f"{sum(1 for key, value in config.items() if key.startswith('CONFIG_NLS_') and value == 'y')}")


def masked(image, selected):
    data = bytearray(image)
    for offset, length in selected:
        data[offset:offset + length] = bytes(length)
    return bytes(data)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error, KeyError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
