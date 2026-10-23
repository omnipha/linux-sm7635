#!/usr/bin/env python3
import argparse
import array
import collections
import hashlib
import importlib.util
import os
import pathlib
import posixpath
import re
import struct
import subprocess
import sys
import zlib

BASE = 0xFFFFFFC008000000
IMAGE_SIZE = 37198336
GZIP_SIZE = 14782792
PAYLOAD_BOUND = 13967360
EXCESS = GZIP_SIZE - PAYLOAD_BOUND
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03"
STOCK_CONFIG_SHA256 = "90203e06c0608d471f2bd260c3c3075112507408e59c3d7d8bec72706899f478"
LEN_BASE = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83,
            99, 115, 131, 163, 195, 227, 258)
LEN_EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5,
             5, 5, 0)
DIST_BASE = (1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769,
             1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577)
DIST_EXTRA = (0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11,
              12, 12, 13, 13)
CL_ORDER = (16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15)

INIT_EVIDENCE = (
    ("CONFIG_PROC_FS", "mount -t proc proc /proc"),
    ("CONFIG_SYSFS", "mount -t sysfs sysfs /sys"),
    ("CONFIG_TMPFS", "mount -t tmpfs devtmpfs /dev"),
    ("CONFIG_CONFIGFS_FS", "mount -t configfs configfs /sys/kernel/config"),
    ("CONFIG_UNIX98_PTYS", "mount -t devpts devpts /dev/pts"),
    ("CONFIG_DEBUG_FS", "mount -t debugfs debugfs /sys/kernel/debug"),
    ("CONFIG_TTY", "setsid cttyhack /bin/sh"),
    ("CONFIG_USB_GADGET", "/sys/class/udc/"),
    ("CONFIG_USB_LIBCOMPOSITE", "usb_gadget/g1"),
    ("CONFIG_USB_CONFIGFS", "usb_gadget/g1"),
    ("CONFIG_USB_CONFIGFS_NCM", "functions/ncm.usb0"),
    ("CONFIG_USB_F_NCM", "functions/ncm.usb0"),
    ("CONFIG_USB_CONFIGFS_ECM", "functions/ecm.usb0"),
    ("CONFIG_USB_F_ECM", "functions/ecm.usb0"),
    ("CONFIG_NET", "ip link set usb0 up"),
    ("CONFIG_INET", "172.16.42.2/24"),
    ("CONFIG_NETDEVICES", "ip addr add 172.16.42.2/24 dev usb0"),
)
INFRA_REQUIRED = ("CONFIG_BLK_DEV_INITRD", "CONFIG_IKCONFIG")
IKCONFIG_NOTE = ("BLK_DEV_INITRD and IKCONFIG evidenced by the boot flow and "
                 "verify-volcano-usb.py board mode reading the embedded config")

# (label, controlling Kconfig symbols, kind, groups)
#   kind "section": groups are output-section names; the bytes are generated or
#     codegen-flag driven (BTF, unwind tables), not per-object link inputs.
#   kind "owner":   groups are exact map owner keys (generated rodata).
#   kind "prefix":  groups are object-path prefixes; saving is the masked delta
#     of every linked object under them.
# The byte ranges come from the linker map, so the gzip saving is a real
# recompression of the exact Image bytes each group occupies. Whether flipping
# the symbol also shrinks kallsyms/BTF/relocations for those objects is not
# modelled; the masked delta is therefore an estimate, and a rebuild is out of
# scope for this issue.
CANDIDATES = (
    ("DEBUG_INFO_BTF", ("CONFIG_DEBUG_INFO_BTF",), "section", (".BTF",)),
    ("UNWIND_TABLES", ("CONFIG_UNWIND_TABLES", "CONFIG_UNWIND_PATCH_PAC_INTO_SCS"),
     "section", (".eh_frame",)),
    ("KALLSYMS_ALL", ("CONFIG_KALLSYMS_ALL",), "owner", ("<generated:kallsyms>",)),
    ("DRM", ("CONFIG_DRM",), "prefix", ("drivers/gpu/drm/",)),
    ("SOUND", ("CONFIG_SOUND",), "prefix", ("sound/",)),
    ("MEDIA_SUPPORT", ("CONFIG_MEDIA_SUPPORT",), "prefix", ("drivers/media/",)),
    ("KVM", ("CONFIG_KVM",), "prefix", ("arch/arm64/kvm/", "virt/kvm/")),
    ("EXT4_FS", ("CONFIG_EXT4_FS",), "prefix", ("fs/ext4/", "fs/jbd2/", "fs/mbcache")),
    ("F2FS_FS", ("CONFIG_F2FS_FS",), "prefix", ("fs/f2fs/",)),
    ("NLS", ("CONFIG_NLS",), "prefix", ("fs/nls/",)),
    ("ANDROID_BINDER_IPC", ("CONFIG_ANDROID_BINDER_IPC",), "prefix",
     ("drivers/android/binder",)),
    ("NETFILTER", ("CONFIG_NETFILTER",), "prefix",
     ("net/netfilter/", "net/ipv4/netfilter/", "net/ipv6/netfilter/", "net/bridge/netfilter/")),
    ("NET_SCHED", ("CONFIG_NET_SCHED",), "prefix", ("net/sched/",)),
    ("IPV6", ("CONFIG_IPV6",), "prefix", ("net/ipv6/",)),
    ("BPF_SYSCALL", ("CONFIG_BPF_SYSCALL",), "prefix", ("kernel/bpf/",)),
    ("ARM_SCMI_PROTOCOL", ("CONFIG_ARM_SCMI_PROTOCOL",), "prefix",
     ("drivers/firmware/arm_scmi/",)),
    ("ZSTD_COMPRESS", ("CONFIG_ZSTD_COMPRESS",), "prefix", ("lib/zstd/",)),
)


UNKNOWN_RUNTIME = {
    "DEBUG_INFO_BTF": ".BTF in closure modules; effect of dropping vmlinux BTF not measured",
    "UNWIND_TABLES": ".eh_frame in closure modules; effect of dropping kernel unwind tables not measured",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config_values(text):
    values = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip('"')
    return values


def raw_deflate(data):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, 8, zlib.Z_DEFAULT_STRATEGY)
    return compressor.compress(data) + compressor.flush()


def gzip_size(data):
    return len(GZIP_HEADER) + len(raw_deflate(data)) + 8


def huffman(lengths):
    max_bits = max(lengths)
    counts = [0] * (max_bits + 2)
    for length in lengths:
        counts[length] += 1
    counts[0] = 0
    next_code = [0] * (max_bits + 2)
    code = 0
    for bits in range(1, max_bits + 1):
        code = (code + counts[bits - 1]) << 1
        next_code[bits] = code
    size = 1 << max_bits
    symbols = array.array("i", bytes(4 * size))
    widths = array.array("b", bytes(size))
    for symbol, length in enumerate(lengths):
        if length:
            value = next_code[length]
            next_code[length] += 1
            reverse = int(format(value, "0{}b".format(length))[::-1], 2)
            for index in range(reverse, size, 1 << length):
                symbols[index] = symbol
                widths[index] = length
    return max_bits, symbols, widths


FIXED_LITERAL = huffman([8] * 144 + [9] * 112 + [7] * 24 + [8] * 8)
FIXED_DISTANCE = huffman([5] * 30)


def deflate_costs(body, expected):
    cost = array.array("f", bytes(4 * len(expected)))
    out = bytearray(len(expected))
    position = 0
    produced = 0
    blocks = 0
    while True:
        window = int.from_bytes(body[position >> 3:(position >> 3) + 9], "little") >> (position & 7)
        final, kind = window & 1, (window >> 1) & 3
        position += 3
        blocks += 1
        if kind == 0:
            position = (position + 7) & ~7
            length = int.from_bytes(body[position >> 3:(position >> 3) + 2], "little")
            position += 32
            start = position >> 3
            out[produced:produced + length] = body[start:start + length]
            for index in range(length):
                cost[produced + index] = 8.0
            produced += length
            position += length * 8
        else:
            if kind == 1:
                literal, distance = FIXED_LITERAL, FIXED_DISTANCE
            else:
                window = int.from_bytes(body[position >> 3:(position >> 3) + 9], "little") >> (position & 7)
                hlit, hdist, hclen = (window & 31) + 257, ((window >> 5) & 31) + 1, ((window >> 10) & 15) + 4
                position += 14
                window = int.from_bytes(body[position >> 3:(position >> 3) + 9], "little") >> (position & 7)
                code_lengths = [0] * 19
                for index in range(hclen):
                    code_lengths[CL_ORDER[index]] = (window >> (3 * index)) & 7
                position += 3 * hclen
                bits, symbols, widths = huffman(code_lengths)
                lengths = []
                while len(lengths) < hlit + hdist:
                    window = int.from_bytes(body[position >> 3:(position >> 3) + 9], "little") >> (position & 7)
                    index = window & ((1 << bits) - 1)
                    symbol = symbols[index]
                    position += widths[index]
                    window = int.from_bytes(body[position >> 3:(position >> 3) + 9], "little") >> (position & 7)
                    if symbol < 16:
                        lengths.append(symbol)
                    elif symbol == 16:
                        lengths += [lengths[-1]] * (3 + (window & 3))
                        position += 2
                    elif symbol == 17:
                        lengths += [0] * (3 + (window & 7))
                        position += 3
                    else:
                        lengths += [0] * (11 + (window & 127))
                        position += 7
                literal, distance = huffman(lengths[:hlit]), huffman(lengths[hlit:])
            lit_bits, lit_symbols, lit_widths = literal
            dist_bits, dist_symbols, dist_widths = distance
            lit_mask, dist_mask = (1 << lit_bits) - 1, (1 << dist_bits) - 1
            while True:
                window = int.from_bytes(body[position >> 3:(position >> 3) + 9], "little") >> (position & 7)
                index = window & lit_mask
                symbol, width = lit_symbols[index], lit_widths[index]
                position += width
                if symbol < 256:
                    out[produced] = symbol
                    cost[produced] = width
                    produced += 1
                elif symbol == 256:
                    break
                else:
                    symbol -= 257
                    extra = LEN_EXTRA[symbol]
                    window >>= width
                    length = LEN_BASE[symbol] + ((window & ((1 << extra) - 1)) if extra else 0)
                    window >>= extra
                    index = window & dist_mask
                    dsym, dwidth = dist_symbols[index], dist_widths[index]
                    window >>= dwidth
                    dextra = DIST_EXTRA[dsym]
                    back = DIST_BASE[dsym] + ((window & ((1 << dextra) - 1)) if dextra else 0)
                    position += extra + dwidth + dextra
                    source = produced - back
                    if back >= length:
                        out[produced:produced + length] = out[source:source + length]
                    else:
                        for offset in range(length):
                            out[produced + offset] = out[source + offset]
                    cost[produced:produced + length] = array.array("f", [(width + extra + dwidth + dextra) / length]) * length
                    produced += length
        if final:
            break
    return cost, bytes(out[:produced]), blocks, position


def elf_sections(path):
    data = pathlib.Path(path).read_bytes()
    shoff = struct.unpack_from("<Q", data, 0x28)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x3A)
    headers = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + index * shentsize) for index in range(shnum)]
    strtab = headers[shstrndx][4]
    sections = []
    for name, kind, flags, address, offset, size, *_ in headers:
        end = data.index(b"\0", strtab + name)
        sections.append((data[strtab + name:end].decode(), kind, flags, address, offset, size))
    return sections


def image_sections(path):
    result = []
    for name, kind, flags, address, offset, size in elf_sections(path):
        if flags & 2 and kind != 8 and size and address >= BASE:
            result.append((name, address - BASE, size))
    return result


def rodata_bytes(path):
    data = pathlib.Path(path).read_bytes()
    for name, kind, flags, address, offset, size in elf_sections(path):
        if name == ".rodata":
            return data[offset:offset + size]
    raise ValueError("no .rodata section in " + str(path))


def parse_map(path, image_len):
    ranges = []
    output = None
    for line in pathlib.Path(path).read_text(errors="replace").splitlines():
        if len(line) < 50:
            continue
        try:
            address = int(line[:16].strip(), 16)
            size = int(line[34:42].strip(), 16)
        except ValueError:
            continue
        text = line[49:]
        indent = len(text) - len(text.lstrip(" "))
        text = text.strip()
        if indent == 0:
            output = text
            continue
        if indent != 8 or address < BASE or not size or output in (".bss", ".sbss", None):
            continue
        offset = address - BASE
        if offset + size > image_len:
            continue
        match = re.match(r"^(.*?)(?:\((.*?)\))?:\((.*)\)$", text)
        if not match:
            continue
        container, member, section = match.groups()
        if member:
            owner = member if container == "vmlinux.a" else posixpath.normpath(
                posixpath.join(posixpath.dirname(container), member))
            owner = re.sub(r"\.(stub|pi)\.o$", ".o", owner)
        elif container.startswith("<internal>"):
            owner = "<merged:" + section + ">"
        elif container == ".btf.vmlinux.bin.o":
            owner = "<generated:btf>"
        elif container == ".tmp_vmlinux.kallsyms2.o":
            owner = "<generated:kallsyms>"
        elif container == ".vmlinux.export.o":
            owner = "<generated:export-crc>"
        else:
            owner = "<link:" + container + ">"
        ranges.append((offset, size, output, owner, section))
    return ranges


def attribute_crc(ranges):
    owner_of = {}
    for offset, size, output, owner, section in ranges:
        if section.startswith("___ksymtab"):
            owner_of[section.split("+", 1)[1]] = owner
    result = []
    for offset, size, output, owner, section in ranges:
        if section.startswith("___kcrctab") and "+" in section:
            symbol = section.split("+", 1)[1]
            if symbol in owner_of:
                owner = owner_of[symbol]
        result.append((offset, size, output, owner, section))
    return result


def strip_comments(line):
    return re.sub(r"(^|\s)#.*$", "", line)


def split_args(text):
    args, depth, current = [], 0, ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            args.append(current)
            current = ""
        else:
            current += char
    args.append(current)
    return args


class Kbuild:
    def __init__(self, src, config):
        self.src = pathlib.Path(src)
        self.config = config
        self.cache = {}

    def expand(self, text, env, depth=0):
        out = ""
        index = 0
        while index < len(text):
            if text[index] == "$" and index + 1 < len(text) and text[index + 1] in "({":
                close = ")" if text[index + 1] == "(" else "}"
                level, scan = 1, index + 2
                while scan < len(text) and level:
                    if text[scan] in "({":
                        level += 1
                    elif text[scan] in ")}":
                        level -= 1
                    scan += 1
                inner = text[index + 2:scan - 1]
                out += self.evaluate(inner, env, depth)
                index = scan
            else:
                out += text[index]
                index += 1
        return out

    def evaluate(self, inner, env, depth):
        if depth > 8:
            return ""
        head = inner.split(None, 1)
        if len(head) == 2 and re.fullmatch(r"[a-z][a-z-]*", head[0]):
            name, rest = head
            args = [self.expand(arg, env, depth + 1) for arg in split_args(rest)]
            args = [arg.strip() for arg in args]
            if name == "patsubst" and len(args) == 3:
                pattern = re.escape(args[0]).replace("%", "(.*)")
                words = []
                for word in args[2].split():
                    match = re.fullmatch(pattern, word)
                    words.append(args[1].replace("%", match.group(1)) if match and "%" in args[1]
                                 else (args[1] if match else word))
                return " ".join(words)
            if name == "subst" and len(args) == 3:
                return args[2].replace(args[0], args[1])
            if name == "addprefix" and len(args) == 2:
                return " ".join(args[0] + word for word in args[1].split())
            if name == "addsuffix" and len(args) == 2:
                return " ".join(word + args[0] for word in args[1].split())
            if name in ("filter", "filter-out") and len(args) == 2:
                patterns = [re.escape(p).replace("%", ".*") for p in args[0].split()]
                keep = name == "filter"
                return " ".join(word for word in args[1].split()
                                if any(re.fullmatch(p, word) for p in patterns) == keep)
            if name == "sort" and args:
                return " ".join(sorted(set(args[0].split())))
            if name == "strip" and args:
                return args[0]
            return ""
        key = inner.strip()
        if key.startswith("CONFIG_"):
            return self.config.get(key, "")
        return env.get(key, "")

    def parse(self, directory, inherited, preset=None):
        key = (directory, inherited)
        if key in self.cache:
            return self.cache[key]
        result = {"objs": [], "dirs": [], "comp": collections.defaultdict(list)}
        self.cache[key] = result
        path = next((self.src / directory / name for name in ("Kbuild", "Makefile")
                     if (self.src / directory / name).exists()), None)
        if path is None:
            return result
        env = {"srctree": ".", "src": directory, "obj": directory, "SRCARCH": "arm64",
               "ARCH": "arm64"}
        env.update(preset or {})
        lines = self.logical_lines(path)
        self.run(lines, directory, inherited, env, result)
        return result

    def logical_lines(self, path):
        lines, pending = [], ""
        for raw in path.read_text(errors="replace").split("\n"):
            raw = strip_comments(raw)
            if raw.rstrip().endswith("\\"):
                pending += raw.rstrip()[:-1] + " "
            else:
                lines.append(pending + raw)
                pending = ""
        return lines

    def run(self, lines, directory, inherited, env, result):
        stack = []
        active = lambda: all(frame[0] for frame in stack)
        for line in lines:
            text = line.strip()
            if not text:
                continue
            match = re.match(r"^(ifeq|ifneq)\s*(.*)$", text)
            if match:
                body = self.expand(match.group(2), env).strip()
                pair = (re.match(r"^\(\s*(.*?)\s*,\s*(.*?)\s*\)$", body) or
                        re.match(r"^[\"'](.*)[\"']\s*[\"'](.*)[\"']$", body))
                equal = bool(pair) and pair.group(1).strip() == pair.group(2).strip()
                value = equal if match.group(1) == "ifeq" else not equal
                stack.append([value, value])
                continue
            match = re.match(r"^(ifdef|ifndef)\s+(\S+)\s*$", text)
            if match:
                present = bool(self.expand("$(" + match.group(2) + ")", env).strip())
                value = present if match.group(1) == "ifdef" else not present
                stack.append([value, value])
                continue
            if text == "else" or text.startswith("else "):
                if stack:
                    taken = stack[-1][1]
                    stack[-1][0] = not taken
                    rest = text[4:].strip()
                    if rest and not taken:
                        sub = re.match(r"^(ifeq|ifneq)\s*(.*)$", rest)
                        if sub:
                            body = self.expand(sub.group(2), env).strip()
                            pair = re.match(r"^\(\s*(.*?)\s*,\s*(.*?)\s*\)$", body)
                            equal = bool(pair) and pair.group(1) == pair.group(2)
                            stack[-1][0] = equal if sub.group(1) == "ifeq" else not equal
                        stack[-1][1] = stack[-1][1] or stack[-1][0]
                continue
            if text == "endif":
                if stack:
                    stack.pop()
                continue
            if not active():
                continue
            match = re.match(r"^include\s+(.*)$", text)
            if match:
                name = self.expand(match.group(1), env).strip()
                target = posixpath.normpath(posixpath.join(".", name)) if name else ""
                if target and (self.src / target).is_file():
                    self.run(self.logical_lines(self.src / target), directory, inherited, env, result)
                continue
            match = re.match(r"^([A-Za-z0-9_.$(){}/%-]+?)\s*(\+=|:=|\?=|=)\s*(.*)$", text)
            if not match:
                continue
            raw_key, operator, raw_value = match.groups()
            name = self.expand(raw_key, env).strip()
            value = self.expand(raw_value, env)
            gates = tuple(sorted(set(re.findall(r"CONFIG_[A-Za-z0-9_]+", raw_key))))
            if operator == "+=":
                env[name] = (env.get(name, "") + " " + value).strip()
            elif operator == "?=":
                env.setdefault(name, value)
            else:
                env[name] = value
            if name in ("obj-y", "lib-y"):
                for token in value.split():
                    if token.endswith("/"):
                        result["dirs"].append((token, tuple(sorted(set(inherited) | set(gates)))))
                    elif token.endswith(".o"):
                        result["objs"].append((token, tuple(sorted(set(inherited) | set(gates)))))
            elif name.endswith("-y") or name.endswith("-objs"):
                base = name.rsplit("-", 1)[0] + ".o"
                for token in value.split():
                    if token.endswith(".o"):
                        result["comp"][base].append((token, gates))

    def linked(self, roots):
        objects = {}
        seen = set()

        def leaves(directory, name, gates, result, depth=0):
            members = result["comp"].get(name)
            if not members or depth > 6:
                objects.setdefault(posixpath.normpath(posixpath.join(directory, name)), set()).update(gates)
                return
            for member, member_gates in members:
                leaves(directory, member, set(gates) | set(member_gates), result, depth + 1)

        def walk(directory, inherited):
            if (directory, inherited) in seen:
                return
            seen.add((directory, inherited))
            result = self.parse(directory, inherited)
            for name, gates in result["objs"]:
                leaves(directory, name, gates, result)
            for sub, gates in result["dirs"]:
                walk(posixpath.normpath(posixpath.join(directory, sub.rstrip("/"))), gates)

        top = self.parse(".", (), {"ARCH_CORE": "", "ARCH_LIB": "arch/arm64/lib/ lib/",
                                    "ARCH_DRIVERS": ""})
        for sub, gates in top["dirs"]:
            walk(posixpath.normpath(sub.rstrip("/")), gates)
        for root in roots:
            walk(root, ())
        return objects


def nm_symbols(src, objects):
    defined, undefined = collections.defaultdict(set), collections.defaultdict(set)
    paths = sorted(objects)
    for start in range(0, len(paths), 400):
        chunk = paths[start:start + 400]
        result = subprocess.run(["llvm-nm-17", "-A", "-g", "--no-demangle"] + chunk, cwd=src,
                                capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            match = re.match(r"^(.*?): +(?:[0-9a-f]+ +)?([A-Za-z?-]) (\S+)$", line)
            if not match:
                continue
            path, kind, symbol = match.groups()
            if kind == "U":
                undefined[path].add(symbol)
            elif kind in "TtDdRrBbSsCcGgVv" and kind.isupper():
                defined[symbol].add(path)
    return defined, undefined


def closure_module_undefined(repo, vendor_boot):
    closure = load_module(pathlib.Path(repo) / "scripts/vendor-module-closure.py",
                          "vendor_module_closure")
    vendor = pathlib.Path(vendor_boot).read_bytes()
    archive = closure.vendor_ramdisk_cpio(vendor, closure.lz4_library())
    files = closure.vendor_files(archive)
    order, _ = closure.compute_eud_order(files)
    undefined = set()
    sections = {".BTF": 0, ".eh_frame": 0}
    for name in order:
        data = files[closure.MODULE_DIR + "/" + name]["data"]
        result = subprocess.run(["llvm-nm-17", "-u", "-"], input=data,
                                capture_output=True, check=False)
        require(result.returncode == 0, "nm failed on closure module " + name)
        undefined.update(re.findall(r"\bU\s+(\S+)", result.stdout.decode()))
        result = subprocess.run(["llvm-readelf-17", "-S", "-"], input=data,
                                capture_output=True, check=False)
        require(result.returncode == 0, "readelf failed on closure module " + name)
        listing = result.stdout.decode()
        for section in sections:
            if re.search(r"\s\.(?:init\.)?" + re.escape(section.lstrip(".")) + r"\s", listing):
                sections[section] += 1
    return len(order), undefined, sections


def run_olddefconfig(src, scratch, name, base_config, disable):
    target = pathlib.Path(scratch) / (name + ".config")
    values = dict()
    lines = []
    wanted = {symbol: True for symbol in disable}
    for line in base_config.splitlines():
        match = re.match(r"^(?:# )?(CONFIG_[A-Za-z0-9_]+)[= ]", line)
        if match and match.group(1) in wanted:
            lines.append("# %s is not set" % match.group(1))
            wanted[match.group(1)] = False
        else:
            lines.append(line)
    for symbol, missing in wanted.items():
        if missing:
            lines.append("# %s is not set" % symbol)
    target.write_text("\n".join(lines) + "\n")
    env = dict(os.environ)
    env.update({"srctree": str(src), "ARCH": "arm64", "SRCARCH": "arm64", "LLVM": "-17",
                "LLVM_IAS": "1", "CC": "clang-17", "LD": "ld.lld-17", "AR": "llvm-ar-17",
                "NM": "llvm-nm-17", "OBJCOPY": "llvm-objcopy-17", "OBJDUMP": "llvm-objdump-17",
                "READELF": "llvm-readelf-17", "STRIP": "llvm-strip-17", "PAHOLE": "pahole",
                "HOSTCC": "gcc", "HOSTCXX": "g++", "LC_ALL": "C",
                "CLANG_FLAGS": "--target=aarch64-linux-gnu -fintegrated-as",
                "KERNELVERSION": "6.1.78", "KCONFIG_CONFIG": str(target),
                "CC_VERSION_TEXT": subprocess.run(["clang-17", "--version"], capture_output=True,
                                                   text=True, check=True).stdout.splitlines()[0]})
    result = subprocess.run([str(pathlib.Path(src) / "scripts/kconfig/conf"), "--olddefconfig",
                             str(pathlib.Path(src) / "Kconfig")], cwd=scratch, env=env,
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, "olddefconfig failed for " + name + ": " + result.stderr[-300:])
    return target.read_text()


def kallsyms_reduction(src, scratch):
    syms = pathlib.Path(src) / ".tmp_vmlinux.kallsyms2.syms"
    generated = pathlib.Path(scratch) / "kallsyms-text.S"
    assembled = pathlib.Path(scratch) / "kallsyms-text.o"
    result = subprocess.run([str(pathlib.Path(src) / "scripts/kallsyms"), "--base-relative", str(syms)],
                            capture_output=True, check=False)
    require(result.returncode == 0, "kallsyms regeneration failed: " + result.stderr.decode()[-300:])
    generated.write_bytes(result.stdout)
    includes = ["-I", "arch/arm64/include", "-I", "arch/arm64/include/generated",
                "-I", "include", "-I", "include/generated"]
    result = subprocess.run(["clang-17", "--target=aarch64-linux-gnu", "-c"] + includes +
                            ["-x", "assembler-with-cpp", "-o", str(assembled), str(generated)],
                            cwd=src, capture_output=True, text=True, check=False)
    require(result.returncode == 0, "kallsyms assembly failed: " + result.stderr[-300:])
    full = len(rodata_bytes(pathlib.Path(src) / ".tmp_vmlinux.kallsyms2.o"))
    text_only = rodata_bytes(assembled)
    require(0 < len(text_only) < full, "text-only kallsyms table is not smaller than the shipped one")
    return full - len(text_only), text_only


def masked_gzip(image, ranges):
    data = bytearray(image)
    for offset, size in ranges:
        data[offset:offset + size] = bytes(size)
    return gzip_size(bytes(data))


def merge_ranges(ranges):
    merged = []
    for offset, size in sorted(ranges):
        if merged and offset <= merged[-1][0] + merged[-1][1]:
            end = max(merged[-1][0] + merged[-1][1], offset + size)
            merged[-1] = (merged[-1][0], end - merged[-1][0])
        else:
            merged.append((offset, size))
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gz", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--replay-elf", required=True)
    parser.add_argument("--replay-image", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--vendor-boot", required=True)
    parser.add_argument("--top", type=int, default=24)
    args = parser.parse_args()
    src, scratch, repo = pathlib.Path(args.src), pathlib.Path(args.scratch), pathlib.Path(args.repo)

    image = pathlib.Path(args.image).read_bytes()
    packed = pathlib.Path(args.gz).read_bytes()
    config_text = pathlib.Path(args.config).read_text()
    require(len(image) == IMAGE_SIZE, "Image is not the 37,198,336-byte #55 image")
    require(len(packed) == GZIP_SIZE and packed[:10] == GZIP_HEADER,
            "gzip is not the 14,782,792-byte stock-framed #55 payload")
    require(gzip_size(image) == GZIP_SIZE and packed == GZIP_HEADER + raw_deflate(image) +
            struct.pack("<II", zlib.crc32(image) & 0xFFFFFFFF, len(image)),
            "zlib level 9 does not reproduce the #55 payload bytes")
    print("inputs: Image %d bytes, payload %d bytes (reproduced bit-exactly), bound %d, excess %d"
          % (len(image), len(packed), PAYLOAD_BOUND, EXCESS))

    replay = pathlib.Path(args.replay_image).read_bytes()
    require(len(replay) == len(image), "relinked Image length differs")
    differing = [index for index in range(len(image)) if image[index] != replay[index]]
    notes = [s for s in image_sections(args.replay_elf) if s[0] == ".notes"][0]
    require(all(notes[1] <= index < notes[1] + notes[2] for index in differing),
            "relinked Image differs outside the .notes build-id")
    print("relink: %d of %d bytes differ, all inside .notes (build-id)" % (len(differing), len(image)))

    cost, decoded, blocks, bits = deflate_costs(packed[10:-8], image)
    require(decoded == image, "decoded deflate stream does not equal the Image")
    require((bits + 7) // 8 + 18 == GZIP_SIZE, "deflate bit count does not match the payload size")
    stream = sum(cost) / 8
    print("deflate: %d blocks, %.0f stream bytes + 18 framing = %d" % (blocks, stream, round(stream) + 18))

    ranges = attribute_crc(parse_map(args.map, len(image)))
    covered = sum(size for offset, size, *_ in ranges)
    sections = image_sections(args.replay_elf)
    section_bytes = sum(size for _, _, size in sections)
    print("map: %d input-section ranges cover %d of %d loaded bytes (%.2f%%); %d bytes are alignment "
          "or linker-script gaps" % (len(ranges), covered, len(image), 100.0 * covered / len(image),
                                     len(image) - covered))

    owner_cost = collections.Counter()
    owner_bytes = collections.Counter()
    owner_sections = collections.defaultdict(collections.Counter)
    owner_ranges = collections.defaultdict(list)
    mark = bytearray(len(image))
    for offset, size, output, owner, section in ranges:
        owner_bytes[owner] += size
        owner_cost[owner] += sum(cost[offset:offset + size]) / 8
        owner_sections[owner][output] += size
        owner_ranges[owner].append((offset, size))
        mark[offset:offset + size] = b"\1" * size
    gap_cost = sum(cost[index] for index in range(len(image)) if not mark[index]) / 8 if covered < len(image) else 0

    print("\nper output section (bytes, in-stream gzip bytes, standalone gzip, zero-masked delta)")
    section_rows = []
    for name, offset, size in sections:
        in_stream = sum(cost[offset:offset + size]) / 8
        standalone = gzip_size(image[offset:offset + size])
        delta = GZIP_SIZE - masked_gzip(image, [(offset, size)]) if size >= 100000 else 0
        section_rows.append((name, size, in_stream, standalone, delta))
    for name, size, in_stream, standalone, delta in sorted(section_rows, key=lambda row: -row[2])[:14]:
        print("  %-20s %10d %10d %10d %10s" % (name, size, in_stream, standalone, delta or "-"))

    def directory(owner, depth):
        if owner.startswith("<"):
            return owner
        return "/".join(owner.split("/")[:depth])

    for depth in (1, 2, 3):
        buckets_cost, buckets_bytes = collections.Counter(), collections.Counter()
        for owner in owner_bytes:
            buckets_cost[directory(owner, depth)] += owner_cost[owner]
            buckets_bytes[directory(owner, depth)] += owner_bytes[owner]
        print("\nper directory, depth %d (bytes, in-stream gzip bytes)" % depth)
        for name, value in sorted(buckets_cost.items(), key=lambda item: (-item[1], item[0]))[:args.top]:
            print("  %-46s %10d %10d" % (name, buckets_bytes[name], round(value)))
        (scratch / ("dirs-depth%d.tsv" % depth)).write_text("".join(
            "%s\t%d\t%d\n" % (name, buckets_bytes[name], round(value))
            for name, value in sorted(buckets_cost.items(), key=lambda item: (-item[1], item[0]))))
    (scratch / "objects.tsv").write_text("".join(
        "%s\t%d\t%d\t%s\n" % (owner, owner_bytes[owner], round(owner_cost[owner]),
                              ",".join("%s=%d" % pair for pair in sorted(owner_sections[owner].items())))
        for owner in sorted(owner_bytes, key=lambda item: (-owner_cost[item], item))))
    print("\ntop objects (bytes, in-stream gzip bytes)")
    for owner in sorted(owner_bytes, key=lambda item: (-owner_cost[item], item))[:args.top]:
        print("  %-52s %10d %10d" % (owner, owner_bytes[owner], round(owner_cost[owner])))
    print("\nunattributed gap bytes: %d (in-stream %d)" % (len(image) - covered, round(gap_cost)))

    usb = load_module(repo / "scripts/verify-volcano-usb.py", "verify_volcano_usb")
    fragment = (repo / "configs/asteroids-volcano-usb-builtin.fragment").read_bytes()
    usb.check_config(config_text.encode(), fragment)
    required = set(usb.BUILTINS)
    print("\nusb closure: verify-volcano-usb.py check_config passes on the #55 config "
          "(%d built-in symbols, %d selected)" % (len(usb.BUILTINS), len(usb.SELECTED)))
    init_text = (repo / "initramfs/init").read_text()
    config = config_values(config_text)
    for symbol, evidence in INIT_EVIDENCE:
        require(evidence in init_text, "init evidence for %s not found: %s" % (symbol, evidence))
        require(config.get(symbol) == "y", "%s is not built in" % symbol)
        required.add(symbol)
    for symbol in INFRA_REQUIRED:
        require(config.get(symbol) == "y", "%s is not built in" % symbol)
        required.add(symbol)
    print("init closure: %d symbols evidenced by initramfs/init; %s"
          % (len(INIT_EVIDENCE), IKCONFIG_NOTE))

    kbuild = Kbuild(src, config)
    linked = kbuild.linked([])
    real = {re.sub(r"\.(stub|pi)\.o$", ".o", line.strip())
            for line in (src / ".vmlinux.objs").read_text().splitlines() if line.strip()}
    print("kbuild evaluator: %d of %d linked objects reproduced from Makefiles and the #55 config "
          "(%d extra)" % (len(real & set(linked)), len(real), len(set(linked) - real)))

    defined, undefined = nm_symbols(src, real)
    base_text = config_text
    section_ranges = collections.defaultdict(list)
    for name, offset, size in sections:
        section_ranges[name].append((offset, size))

    def group_ranges(kind, groups):
        if kind == "section":
            return [r for name in groups for r in section_ranges.get(name, [])]
        if kind == "owner":
            return [r for name in groups for r in owner_ranges.get(name, [])]
        return [r for owner in owner_ranges for prefix in groups if owner.startswith(prefix)
                for r in owner_ranges[owner]]

    def group_objects(kind, groups):
        if kind != "prefix":
            return []
        return sorted(owner for owner in owner_ranges
                      if any(owner.startswith(prefix) for prefix in groups))

    count, module_imports, module_sections = closure_module_undefined(repo, args.vendor_boot)
    print("\nvendor closure: %d modules; undefined symbols %d; modules carrying .BTF %d, .eh_frame %d"
          % (count, len(module_imports), module_sections[".BTF"], module_sections[".eh_frame"]))
    kall_removed, kall_text = kallsyms_reduction(src, scratch)
    kall_ranges = sorted(owner_ranges.get("<generated:kallsyms>", []), key=lambda r: -r[1])
    require(kall_ranges and kall_ranges[0][1] >= kall_removed, "kallsyms owner range not found")
    kall_offset, kall_size = kall_ranges[0]
    kall_image = image[:kall_offset] + kall_text + image[kall_offset + kall_size:]
    print("KALLSYMS_ALL=n: text-only table regenerated by scripts/kallsyms without --all-symbols; "
          ".rodata %d -> %d bytes (-%d)" % (kall_size, len(kall_text), kall_removed))

    rows = []
    print("\ncandidate gzip estimates (recompression of the exact map bytes; Kconfig probe in "
          "scratch, nothing built)")
    for name, symbols, kind, groups in CANDIDATES:
        text = run_olddefconfig(src, scratch, "cand-" + name, base_text, symbols)
        after = config_values(text)
        flipped = sorted(key for key, value in config.items() if value == "y" and after.get(key) != "y")
        still = [symbol for symbol in symbols if after.get(symbol) == "y"]
        broken = sorted(symbol for symbol in required if after.get(symbol) != "y")
        ranges_g = merge_ranges(group_ranges(kind, groups))
        if name == "KALLSYMS_ALL":
            saving = GZIP_SIZE - gzip_size(kall_image)
            raw = kall_removed
            in_stream = 0.0
        else:
            saving = GZIP_SIZE - masked_gzip(image, ranges_g) if ranges_g else 0
            raw = sum(size for _, size in ranges_g)
            in_stream = sum(sum(cost[o:o + s]) for o, s in ranges_g) / 8
        objects = group_objects(kind, groups)
        gone = set(objects)
        coupled = sorted({user for user, used in undefined.items() if user not in gone and
                          any(defined.get(s) and defined[s] <= gone for s in used)})
        needed = sorted(symbol for symbol in module_imports
                        if gone and defined.get(symbol) and defined[symbol] <= gone)
        if broken or needed:
            verdict = "REQUIRED"
        elif name in UNKNOWN_RUNTIME or still or coupled:
            verdict = "UNKNOWN"
        else:
            verdict = "NOT-REQUIRED"
        rows.append((name, symbols, kind, still, broken, flipped, raw, saving, in_stream, coupled,
                     needed, verdict))
        print("  %-20s raw %9d saving %9d in-stream %9d flipped %4d  %s" % (
            name, raw, saving, round(in_stream), len(flipped), verdict))
        if broken:
            print("      closure symbols turned off: %s" % ", ".join(broken))
        if needed:
            print("      closure-module imports provided only here: %d (%s)"
                  % (len(needed), ", ".join(needed[:3])))
        if still:
            print("      kept by select: %s" % ", ".join(still))
        if coupled:
            print("      link-coupled from %d other linked objects (e.g. %s)" % (len(coupled), coupled[0]))
        if name in UNKNOWN_RUNTIME:
            print("      unknown: %s" % UNKNOWN_RUNTIME[name])
    (scratch / "candidates.tsv").write_text("".join(
        "%s\t%s\t%d\t%d\t%s\t%d\t%d\t%s\n" % (row[0], ",".join(row[1]), row[6], row[7],
                                                 ",".join(row[4]), len(row[9]), len(row[10]), row[11])
        for row in rows))

    candidate_dirs = {
        "fs/ext4": "EXT4_FS", "fs/f2fs": "F2FS_FS", "drivers/gpu/drm": "DRM",
        "drivers/media": "MEDIA_SUPPORT", "fs/nls": "NLS", "net/ipv6": "IPV6",
        "kernel/bpf": "BPF_SYSCALL", "net/netfilter": "NETFILTER", "net/sched": "NET_SCHED",
        "arch/arm64/kvm": "KVM", "drivers/firmware/arm_scmi": "ARM_SCMI_PROTOCOL",
        "lib/zstd": "ZSTD_COMPRESS", "sound": "SOUND",
    }
    verdicts = {row[0]: row[11] for row in rows}
    required_objects = {owner for owner, gates in linked.items() if set(gates) & required}
    for symbol in module_imports:
        if len(defined.get(symbol, ())) == 1:
            required_objects.update(defined[symbol])
    for depth in (2, 3):
        buckets = collections.defaultdict(list)
        for owner in owner_bytes:
            buckets[directory(owner, depth)].append(owner)
        labels = []
        for name, owners in sorted(buckets.items(),
                                   key=lambda item: -sum(owner_cost[owner] for owner in item[1])):
            if name in candidate_dirs:
                verdict = verdicts[candidate_dirs[name]]
            elif any(owner in required_objects for owner in owners):
                verdict = "REQUIRED"
            else:
                verdict = "UNKNOWN"
            labels.append((name, sum(owner_bytes[owner] for owner in owners),
                           round(sum(owner_cost[owner] for owner in owners)), verdict))
        (scratch / ("classified-depth%d.tsv" % depth)).write_text("".join(
            "%s\t%d\t%d\t%s\n" % row for row in labels))
        print("\nlarge directories, depth %d (raw bytes, in-stream gzip bytes, whole-group status)" % depth)
        for name, raw, stream_bytes, verdict in labels[:args.top]:
            print("  %-44s %9d %9d  %s" % (name, raw, stream_bytes, verdict))
    print("  REQUIRED means the whole group cannot be removed; it does not mean every byte is needed.")
    print("  UNKNOWN includes mixed groups and generated tables with only partial-removal estimates.")

    safe = [row for row in rows if row[11] == "NOT-REQUIRED"]
    union_symbols = [symbol for row in safe for symbol in row[1]]
    text = run_olddefconfig(src, scratch, "union", base_text, union_symbols)
    after = config_values(text)
    broken = sorted(symbol for symbol in required if after.get(symbol) != "y")
    names = {row[0] for row in safe}
    union_ranges = []
    for name, symbols, kind, groups in CANDIDATES:
        if name in names and name != "KALLSYMS_ALL":
            union_ranges += group_ranges(kind, groups)
    merged = merge_ranges(union_ranges)
    data = bytearray(image)
    for offset, size in merged:
        data[offset:offset + size] = bytes(size)
    if "KALLSYMS_ALL" in names:
        data[kall_offset:kall_offset + kall_size] = kall_text
    union_saving = GZIP_SIZE - gzip_size(bytes(data))
    summed = sum(row[7] for row in safe)
    print("\nnot-required set: %s" % (", ".join(row[0] for row in safe) if safe else "(none)"))
    print("  closure symbols turned off when all are disabled together: %s"
          % (", ".join(broken) if broken else "none"))
    print("  sum of individual estimates %d, joint estimate %d" % (summed, union_saving))
    print("  bound excess %d -> %s" % (EXCESS,
          "REACHES" if union_saving >= EXCESS else "DOES NOT REACH"))
    margin = union_saving - EXCESS
    print("  margin: %d bytes %s the excess" % (abs(margin), "above" if margin >= 0 else "short of"))
    unknown = [row for row in rows if row[11] == "UNKNOWN"]
    print("  unknown groups, not counted: %s" % (", ".join("%s(%d)" % (row[0], row[7]) for row in unknown)
                                                  or "none"))
    print("  residuals: %d map-gap bytes (in-stream %d), %d deflate block-header bytes"
          % (len(image) - covered, round(gap_cost), GZIP_SIZE - 18 - round(stream)))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error, KeyError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
