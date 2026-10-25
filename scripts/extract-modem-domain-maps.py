#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import shutil
import struct
import sys
import tempfile

BOOT_HEADER_BYTES = 512
MAX_JSN_BYTES = 1 << 20
MAX_INVENTORY = 200000
MAX_DEPTH = 16
IMAGE_ROOT = "image"
TOP_NESTED_REQUIRED = {"sr_domain", "sr_service"}
TOP_NESTED_OPTIONAL = {"sr_version"}
TOP_FLAT_KEYS = {"soc", "domain", "subdomain", "provider", "sr_version", "sr_service"}
DOMAIN_REQUIRED = {"soc", "domain", "subdomain"}
DOMAIN_OPTIONAL = {"qmi_instance_id"}
SERVICE_REQUIRED = {"provider", "service"}
SERVICE_OPTIONAL = {"instance", "qmi_instance_id", "service_data_valid",
                     "service_data", "dcomment"}
MAX_DCOMMENT = 512
MANIFEST_NAME = "extraction-manifest.txt"
MAPS_NAME = "domain-maps.json"
CONFIG_NAME = "pd-mapper.conf.json"
NON_STOCK_NOTE = (
    "stock_verified is always false in generated outputs; #89 hash-pinned the "
    "modem_a partition independently, and this file is never a flashable image"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def short_checksum(raw11):
    total = 0
    for byte in raw11:
        total = (((total & 1) << 7) + (total >> 1) + byte) & 0xFF
    return total


class FatImage:
    def __init__(self, path):
        self.size = path.stat().st_size
        require(self.size >= BOOT_HEADER_BYTES,
                "dump is smaller than a FAT boot header")
        self.stream = open(path, "rb")
        self.head = self.read_at(0, BOOT_HEADER_BYTES)
        bps = struct.unpack_from("<H", self.head, 11)[0]
        require(bps in (512, 1024, 2048, 4096),
                "FAT bytes-per-sector is not one of 512/1024/2048/4096")
        require(self.size >= bps, "dump is smaller than one FAT boot sector")
        boot = self.head if bps == 512 else self.read_at(0, bps)
        require(boot[510:512] == b"\x55\xaa" or boot[bps - 2:bps] == b"\x55\xaa",
                "dump has no FAT boot signature 55 AA at offset 510 or the "
                f"{bps}-byte boot-sector end")
        spc = self.head[13]
        reserved = struct.unpack_from("<H", self.head, 14)[0]
        nfats = self.head[16]
        root_ents = struct.unpack_from("<H", self.head, 17)[0]
        tot16 = struct.unpack_from("<H", self.head, 19)[0]
        fat16_size = struct.unpack_from("<H", self.head, 22)[0]
        tot32 = struct.unpack_from("<I", self.head, 32)[0]
        fat32_size = struct.unpack_from("<I", self.head, 36)[0]
        self.root_cluster = struct.unpack_from("<I", self.head, 44)[0]
        require(spc >= 1 and spc & (spc - 1) == 0,
                "FAT sectors-per-cluster is not a power of two")
        require(reserved >= 1 and nfats in (1, 2),
                "FAT reserved-sector or table count is implausible")
        total = tot16 if tot16 else tot32
        require(total > 0 and total * bps == self.size,
                "FAT total-sector count does not match the dump size exactly")
        fat_size = fat16_size if fat16_size else fat32_size
        require(fat_size > 0, "FAT table size is zero")
        self.is32 = fat16_size == 0
        if self.is32:
            require(root_ents == 0 and self.root_cluster >= 2,
                    "FAT32 root-directory fields are invalid")
            root_dir_sectors = 0
        else:
            require(root_ents > 0, "FAT12/16 root-entry count is zero")
            root_dir_sectors = (root_ents * 32 + bps - 1) // bps
        self.bps = bps
        self.cluster_bytes = spc * bps
        self.fat_start = reserved * bps
        self.root_dir_start = (reserved + nfats * fat_size) * bps
        self.data_start = self.root_dir_start + root_dir_sectors * bps
        self.root_dir_sectors = root_dir_sectors
        self.clusters = (total * bps - self.data_start) // self.cluster_bytes
        require(self.clusters >= 1, "FAT data region holds no clusters")
        if self.clusters < 4085:
            self.kind = 12
        elif self.clusters < 65525:
            self.kind = 16
        else:
            self.kind = 32
        require((self.kind == 32) == self.is32,
                "FAT type from the cluster count contradicts the boot sector layout")
        self.eoc = {12: 0x0FF8, 16: 0xFFF8, 32: 0x0FFFFFF8}[self.kind]
        self.bad = {12: 0x0FF7, 16: 0xFFF7, 32: 0x0FFFFFF7}[self.kind]

    def read_at(self, offset, length):
        self.stream.seek(offset)
        data = self.stream.read(length)
        require(len(data) == length, "dump is shorter than its FAT geometry claims")
        return data

    def fat_entry(self, cluster):
        if self.kind == 12:
            pair = self.read_at(self.fat_start + cluster + cluster // 2, 2)
            value = pair[0] | (pair[1] << 8)
            return value >> 4 if cluster & 1 else value & 0x0FFF
        if self.kind == 16:
            return struct.unpack("<H", self.read_at(self.fat_start + 2 * cluster, 2))[0]
        return struct.unpack(
            "<I", self.read_at(self.fat_start + 4 * cluster, 4))[0] & 0x0FFFFFFF

    def chain(self, start, label):
        require(2 <= start < self.clusters + 2, f"{label} starts at an out-of-range cluster")
        clusters = []
        seen = set()
        cluster = start
        while True:
            require(cluster not in seen, f"{label} cluster chain loops")
            seen.add(cluster)
            clusters.append(cluster)
            require(len(clusters) <= self.clusters,
                    f"{label} cluster chain is longer than the data region")
            value = self.fat_entry(cluster)
            if value >= self.eoc:
                return clusters
            require(value != self.bad and 2 <= value < self.clusters + 2,
                    f"{label} cluster chain hits an invalid cluster")
            cluster = value

    def read_clusters(self, clusters, size):
        out = bytearray()
        for cluster in clusters:
            if len(out) >= size:
                break
            out += self.read_at(self.data_start + (cluster - 2) * self.cluster_bytes,
                                self.cluster_bytes)
        require(len(out) >= size, f"{size} bytes do not fit in the recorded cluster chain")
        return bytes(out[:size])

    def read_file(self, record):
        if record["size"] == 0:
            return b""
        clusters = self.chain(record["cluster"], record["path"])
        return self.read_clusters(clusters, record["size"])

    def walk(self):
        self.entries = {}
        self.label = None
        if self.is32:
            clusters = self.chain(self.root_cluster, "root directory")
            root = self.read_clusters(clusters, len(clusters) * self.cluster_bytes)
        else:
            root = self.read_at(self.root_dir_start, self.root_dir_sectors * self.bps)
        self.parse_dir(root, "", 0)
        return self.label, self.entries

    def parse_dir(self, data, path, depth):
        require(depth <= MAX_DEPTH, f"directory tree under {path or '/'} is deeper than {MAX_DEPTH}")
        require(len(data) % 32 == 0, f"directory {path or '/'} is not a whole 32-byte record count")
        lfn_parts = None
        lfn_expected = None
        lfn_checksum = None
        pos = 0
        while pos < len(data):
            record = data[pos:pos + 32]
            pos += 32
            first = record[0]
            if first == 0x00:
                break
            if first == 0xE5:
                lfn_parts = None
                continue
            attr = record[11]
            if attr & 0x0F == 0x0F:
                seq = first & 0x3F
                chars = record[1:11] + record[14:26] + record[28:32]
                units = [struct.unpack_from("<H", chars, i)[0] for i in range(0, 26, 2)]
                part = []
                for unit in units:
                    if unit in (0x0000, 0xFFFF):
                        break
                    part.append(chr(unit))
                if first & 0x40:
                    lfn_parts = []
                    lfn_expected = seq
                    lfn_checksum = record[13]
                require(lfn_parts is not None and seq == lfn_expected and seq >= 1,
                        f"LFN sequence is broken in directory {path or '/'}")
                lfn_parts.append("".join(part))
                lfn_expected = seq - 1
                continue
            base = record[0:8].rstrip(b" ")
            ext = record[8:11].rstrip(b" ")
            require(all(32 <= byte < 127 and byte not in b":;=<>*?|/\\\","
                        for byte in base + ext),
                    f"short name in directory {path or '/'} carries an illegal byte")
            if lfn_parts is not None:
                require(lfn_expected == 0, f"LFN run for {base!r} is incomplete")
                require(short_checksum(record[0:11]) == lfn_checksum,
                        f"LFN checksum mismatch for {base!r}")
                name = "".join(reversed(lfn_parts))
                lfn_parts = None
            else:
                name = base.decode() + (b"." + ext).decode() if ext else base.decode()
                name = name.lower()
            cluster = struct.unpack_from("<H", record, 26)[0]
            if self.is32:
                cluster |= struct.unpack_from("<H", record, 20)[0] << 16
            size = struct.unpack_from("<I", record, 28)[0]
            if attr & 0x08:
                require(path == "" and self.label is None,
                        "volume label entry appears outside the root directory")
                self.label = record[:11].decode("ascii").strip()
                continue
            if name in (".", ".."):
                continue
            require(name not in ("", ".", "..") and "/" not in name and "\\" not in name
                    and "\x00" not in name,
                    f"entry name {name!r} is not a single path component")
            full = f"{path}/{name}" if path else name
            require(full not in self.entries, f"path {full} repeats in the directory tree")
            require(len(self.entries) < MAX_INVENTORY,
                    f"more than {MAX_INVENTORY} directory entries")
            if attr & 0x10:
                self.entries[full] = {"path": full, "dir": True, "cluster": cluster,
                                      "size": 0}
                if cluster != 0:
                    clusters = self.chain(cluster, f"directory {full}")
                    self.parse_dir(self.read_clusters(clusters,
                                                      len(clusters) * self.cluster_bytes),
                                   full, depth + 1)
            else:
                require(size <= MAX_JSN_BYTES or not name.lower().endswith(".jsn"),
                        f".jsn file {full} exceeds {MAX_JSN_BYTES} bytes")
                self.entries[full] = {"path": full, "dir": False, "cluster": cluster,
                                      "size": size}


def is_jsn(path):
    return path.lower().endswith(".jsn")


def check_int(container, key, where):
    value = container[key]
    require(isinstance(value, int) and not isinstance(value, bool)
            and 0 <= value <= 0xFFFFFFFF,
            f"{where} {key} is not a non-negative 32-bit integer")
    return value


def check_str(container, key, where):
    value = container[key]
    require(isinstance(value, str) and value and value == value.strip()
            and "/" not in value,
            f"{where} {key} is not a non-empty trimmed string without '/'")
    return value


def check_sr_version(obj, where):
    # sr_version is optional; the stock modem_a dump (#92, dump sha256
    # 08a5caf8…) carries it as {"major": 1, "minor": 1, "patch": 1} in every
    # .jsn, and upstream pd_load_map() ignores the key entirely. Accept the
    # stock object form and the historical plain non-negative integer; any
    # other shape stays a hard failure.
    if "sr_version" not in obj:
        return None
    value = obj["sr_version"]
    if isinstance(value, bool):
        raise ValueError(f"{where} sr_version is not an int or version object")
    if isinstance(value, int):
        check_int(obj, "sr_version", where)
        return value
    if isinstance(value, dict) and set(value) == {"major", "minor", "patch"}:
        return {"major": check_int(value, "major", f"{where} sr_version"),
                "minor": check_int(value, "minor", f"{where} sr_version"),
                "patch": check_int(value, "patch", f"{where} sr_version")}
    raise ValueError(f"{where} sr_version is not an int or version object")


def validate_jsn(path, data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} is not valid UTF-8 text") from exc
    try:
        obj = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {str(exc)[:80]}") from exc
    require(isinstance(obj, dict), f"{path} is not a JSON object")
    where = f"{path}"
    if TOP_NESTED_REQUIRED <= set(obj) <= TOP_NESTED_REQUIRED | TOP_NESTED_OPTIONAL:
        domain = obj["sr_domain"]
        require(isinstance(domain, dict) and
                DOMAIN_REQUIRED <= set(domain) <= DOMAIN_REQUIRED | DOMAIN_OPTIONAL,
                f"{where} sr_domain keys are not within "
                f"{sorted(DOMAIN_REQUIRED | DOMAIN_OPTIONAL)} with "
                f"{sorted(DOMAIN_REQUIRED)} required: got "
                f"{sorted(domain) if isinstance(domain, dict) else type(domain).__name__}")
        soc = check_str(domain, "soc", f"{where} sr_domain")
        domain_name = check_str(domain, "domain", f"{where} sr_domain")
        subdomain = check_str(domain, "subdomain", f"{where} sr_domain")
        qmi_instance_id = (check_int(domain, "qmi_instance_id", f"{where} sr_domain")
                           if "qmi_instance_id" in domain else None)
        provider = None
    else:
        require(set(obj) == TOP_FLAT_KEYS,
                f"{where} top-level keys are neither the nested "
                f"{sorted(TOP_NESTED_REQUIRED | TOP_NESTED_OPTIONAL)} (sr_version "
                "optional) nor the flat "
                f"{sorted(TOP_FLAT_KEYS)} pd-mapper schema: got {sorted(obj)}")
        soc = check_str(obj, "soc", where)
        domain_name = check_str(obj, "domain", where)
        subdomain = check_str(obj, "subdomain", where)
        provider = check_str(obj, "provider", where)
        qmi_instance_id = None
    sr_version = check_sr_version(obj, where)
    services = obj["sr_service"]
    require(isinstance(services, list) and services,
            f"{where} sr_service is not a non-empty array")
    parsed = []
    for s_index, service in enumerate(services):
        s_where = f"{where} sr_service[{s_index}]"
        require(isinstance(service, dict), f"{s_where} is not a JSON object")
        require(SERVICE_REQUIRED <= set(service) <= SERVICE_REQUIRED | SERVICE_OPTIONAL,
                f"{s_where} keys are not within {sorted(SERVICE_REQUIRED | SERVICE_OPTIONAL)} "
                f"with {sorted(SERVICE_REQUIRED)} required: got {sorted(service)}")
        entry = {
            "provider": check_str(service, "provider", s_where),
            "service": check_str(service, "service", s_where),
        }
        for key in ("instance", "qmi_instance_id", "service_data"):
            if key in service:
                entry[key] = check_int(service, key, s_where)
        if "dcomment" in service:
            comment = service["dcomment"]
            require(isinstance(comment, str) and len(comment) <= MAX_DCOMMENT,
                    f"{s_where} dcomment is not a string of at most "
                    f"{MAX_DCOMMENT} bytes")
            entry["dcomment"] = comment
        if "service_data_valid" in service:
            valid = check_int(service, "service_data_valid", s_where)
            require(valid in (0, 1), f"{s_where} service_data_valid is not 0 or 1")
            entry["service_data_valid"] = valid
        parsed.append(entry)
    return {
        "soc": soc, "domain": domain_name, "subdomain": subdomain,
        "provider": provider, "qmi_instance_id": qmi_instance_id,
        "sr_version": sr_version, "services": parsed,
    }


def derive_config(jsn_files):
    groups = {}
    for record in jsn_files:
        entry = record["entries"]
        key = (entry["soc"], entry["domain"], entry["subdomain"], entry["provider"],
               entry["qmi_instance_id"])
        group = groups.setdefault(key, {"sr_version": entry["sr_version"], "services": {}})
        require(group["sr_version"] == entry["sr_version"],
                "conflicting sr_version for " + "/".join(str(k) for k in key if k is not None))
        for service in entry["services"]:
            s_key = (service["provider"], service["service"],
                     service.get("instance"), service.get("qmi_instance_id"),
                     service.get("service_data"))
            previous = group["services"].get(s_key)
            require(previous is None or previous == service,
                    "conflicting service " + "/".join(str(k) for k in s_key[:2]) +
                    " for " + "/".join(str(k) for k in key if k is not None))
            group["services"][s_key] = dict(service)
    providers = []
    for key in sorted(groups, key=lambda item: tuple(str(part) for part in item)):
        group = groups[key]
        providers.append({
            "soc": key[0], "domain": key[1], "subdomain": key[2], "provider": key[3],
            "qmi_instance_id": key[4], "sr_version": group["sr_version"],
            "services": [group["services"][s_key] for s_key in sorted(
                group["services"],
                key=lambda item: tuple(str(part) for part in item))],
        })
    require(providers, "validated .jsn files yielded no provider/service entry")
    return providers


def inside_git_worktree(path):
    current = path.resolve()
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return True
    return False


def parse_args(argv):
    dump = None
    out = None
    expect_synthetic = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--out":
            require(index + 1 < len(argv) and out is None,
                "usage: extract-modem-domain-maps.py DUMP --out OUTDIR "
                "[--expect-synthetic]")
            out = argv[index + 1]
            index += 2
        elif arg == "--expect-synthetic":
            expect_synthetic = True
            index += 1
        elif not arg.startswith("--") and dump is None:
            dump = arg
            index += 1
        else:
            raise ValueError(usage_message())
    require(dump is not None and out is not None, usage_message())
    return dump, out, expect_synthetic


def usage_message():
    return ("usage: extract-modem-domain-maps.py DUMP --out OUTDIR "
            "[--expect-synthetic]")


def main():
    dump_arg, out_arg, expect_synthetic = parse_args(sys.argv[1:])
    dump = pathlib.Path(dump_arg)
    require(dump.is_file(), f"{dump} is not an existing regular file")
    out = pathlib.Path(out_arg)
    require(not inside_git_worktree(out),
            f"output directory {out} must stay outside any Git worktree")
    if out.exists():
        require(out.is_dir() and not any(out.iterdir()),
                f"output directory {out} exists and is not empty")
    dump_sha = sha256_file(dump)
    image = FatImage(dump)
    label, entries = image.walk()
    synthetic = bool(label) and "SYNTHETIC" in label.upper()
    if expect_synthetic:
        require(synthetic,
                "volume label does not mark this dump as a synthetic fixture")
    require(f"{IMAGE_ROOT}" in entries and entries[IMAGE_ROOT]["dir"],
            f"the dump carries no {IMAGE_ROOT}/ directory: not the stock firmware layout")
    jsn_paths = sorted(path for path in entries if not entries[path]["dir"] and is_jsn(path))
    under_image = [path for path in jsn_paths if path.startswith(f"{IMAGE_ROOT}/")]
    require(under_image,
            f"no .jsn file under {IMAGE_ROOT}/: refusing to invent a domain map")
    jsn_files = []
    for path in jsn_paths:
        record = entries[path]
        data = image.read_file(record)
        require(len(data) == record["size"], f"{path} read length differs from its size")
        jsn_files.append({
            "path": path,
            "size": record["size"],
            "sha256": hashlib.sha256(data).hexdigest(),
            "under_image": path in under_image,
            "bytes": data,
            "entries": validate_jsn(path, data),
        })
    providers = derive_config(jsn_files)
    image.stream.close()

    source = {"path": str(dump.resolve()), "size": image.size, "sha256": dump_sha}
    stamp = {"synthetic": synthetic, "non_flashable": True, "stock_verified": False,
             "note": NON_STOCK_NOTE, "source_dump": source}
    maps = dict(stamp)
    maps["files"] = [{"path": item["path"], "size": item["size"],
                      "sha256": item["sha256"], "under_image": item["under_image"],
                      "map": item["entries"]} for item in jsn_files]
    config = dict(stamp)
    config["generator"] = "scripts/extract-modem-domain-maps.py"
    config["providers"] = providers
    config["jsn_files"] = [{"path": item["path"], "sha256": item["sha256"]}
                           for item in jsn_files]
    staging = pathlib.Path(tempfile.mkdtemp(prefix=".extract-", dir=out.parent))
    try:
        maps_dir = staging / "maps"
        maps_dir.mkdir()
        for item in jsn_files:
            output = maps_dir / item["path"]
            require(output.resolve().is_relative_to(maps_dir.resolve()),
                    f"refusing to write extracted path outside maps/: {item['path']}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(item["bytes"])
        (staging / MAPS_NAME).write_text(json.dumps(maps, indent=2) + "\n")
        (staging / CONFIG_NAME).write_text(json.dumps(config, indent=2) + "\n")
        lines = [
            f"dump_path={source['path']}",
            f"dump_size={image.size}",
            f"dump_sha256={dump_sha}",
            f"fat_type={image.kind}",
            f"volume_label={label or ''}",
            f"synthetic={'true' if synthetic else 'false'}",
            f"non_flashable=true",
            f"stock_verified=false",
            f"jsn_under_image={len(under_image)}",
            f"jsn_outside_image={len(jsn_paths) - len(under_image)}",
            f"providers={len(providers)}",
            "verdict=PASS",
        ]
        for item in jsn_files:
            lines.append(f"jsn_file={item['path']} size={item['size']} "
                         f"sha256={item['sha256']} under_image="
                         f"{'yes' if item['under_image'] else 'no'}")
        for path in sorted(entries):
            entry = entries[path]
            lines.append(f"{'dir' if entry['dir'] else 'inventory_file'}={path}"
                         + ("" if entry["dir"] else f" size={entry['size']}"))
        (staging / MANIFEST_NAME).write_text("\n".join(lines) + "\n")
        os.replace(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"PASS: {len(under_image)} .jsn under {IMAGE_ROOT}/ "
          f"({len(jsn_paths) - len(under_image)} elsewhere), "
          f"{len(providers)} provider groups, synthetic={synthetic}, "
          f"dump sha256 {dump_sha[:12]}…")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error, KeyError) as exc:
        raise SystemExit(f"FAIL: {str(exc)[:200]}") from exc
