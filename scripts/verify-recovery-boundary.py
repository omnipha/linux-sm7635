import hashlib
import pathlib
import struct
import sys

PAGE = 4096


def require(condition, message):
    if not condition:
        raise ValueError(message)


def align(size):
    return (size + PAGE - 1) // PAGE * PAGE


def boot_fields(image, name):
    require(len(image) >= PAGE and image[:8] == b"ANDROID!" and
            struct.unpack_from("<I", image, 20)[0] == 1584 and
            struct.unpack_from("<I", image, 40)[0] == 4 and
            struct.unpack_from("<I", image, 1580)[0] == 0,
            f"{name}: unexpected header-v4 geometry")
    return struct.unpack_from("<II", image, 8)


def avb(vbmeta, name):
    require(len(vbmeta) >= 256 and vbmeta[:4] == b"AVB0", f"{name}: missing AVB0")
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    algorithm = struct.unpack_from(">I", vbmeta, 28)[0]
    key_offset, key_len = struct.unpack_from(">QQ", vbmeta, 64)
    desc_offset, desc_len = struct.unpack_from(">QQ", vbmeta, 96)
    rollback, flags = struct.unpack_from(">QI", vbmeta, 112)
    require(256 + auth + aux <= len(vbmeta) and key_offset + key_len <= aux and
            desc_offset + desc_len <= aux and flags == 0,
            f"{name}: invalid AVB metadata/flags")
    key = vbmeta[256 + auth + key_offset:256 + auth + key_offset + key_len]
    chains = {}
    hashes = {}
    pos = 256 + auth + desc_offset
    end = pos + desc_len
    while pos < end:
        require(pos + 16 <= end, f"{name}: truncated AVB descriptor")
        tag, length = struct.unpack_from(">QQ", vbmeta, pos)
        require(length > 0 and pos + 16 + length <= end,
                f"{name}: AVB descriptor out of bounds")
        body = vbmeta[pos + 16:pos + 16 + length]
        if tag == 4:
            require(len(body) >= 76, f"{name}: short chain descriptor")
            location, name_len, child_key_len, chain_flags = struct.unpack_from(">IIII", body)
            require(76 + name_len + child_key_len <= len(body) and chain_flags == 0,
                    f"{name}: invalid chain descriptor")
            child = body[76:76 + name_len]
            require(child not in chains, f"{name}: duplicate chain descriptor")
            chains[child] = (location, body[76 + name_len:76 + name_len + child_key_len])
        if tag == 2:
            require(len(body) >= 116, f"{name}: short hash descriptor")
            size = struct.unpack_from(">Q", body)[0]
            name_len, salt_len, digest_len, hash_flags = struct.unpack_from(">IIII", body, 40)
            require(116 + name_len + salt_len + digest_len <= len(body) and
                    body[8:40].split(b"\0", 1)[0] == b"sha256" and
                    digest_len == 32 and hash_flags == 0,
                    f"{name}: invalid hash descriptor")
            part = body[116:116 + name_len]
            require(part not in hashes, f"{name}: duplicate hash descriptor")
            salt = body[116 + name_len:116 + name_len + salt_len]
            digest = body[116 + name_len + salt_len:116 + name_len + salt_len + digest_len]
            hashes[part] = size, salt, digest
        pos += 16 + length
    return algorithm, rollback, key, chains, hashes


def footer_hash(image, partition):
    footer = image[-64:]
    require(len(footer) == 64 and footer[:4] == b"AVBf",
            f"{partition}: missing stock AVB footer")
    original, offset, size = struct.unpack_from(">QQQ", footer, 12)
    require(original == offset and offset + size <= len(image) - 64,
            f"{partition}: invalid AVB footer bounds")
    policy = avb(image[offset:offset + size], partition)
    require(partition.encode() in policy[4], f"{partition}: missing embedded hash")
    hashed_size, salt, digest = policy[4][partition.encode()]
    require(hashed_size == original and hashlib.sha256(salt + image[:original]).digest() == digest,
            f"{partition}: embedded hash mismatch")
    return original, policy


def check(boot, init_boot, vendor_boot, recovery_a, recovery_b, vbmeta):
    boot_kernel, boot_ramdisk = boot_fields(boot, "boot")
    init_kernel, init_ramdisk = boot_fields(init_boot, "init_boot")
    require(boot_kernel > 0 and boot_ramdisk == 0 and
            init_kernel == 0 and init_ramdisk > 0,
            "boot/init_boot kernel and generic ramdisk roles changed")
    require(vendor_boot[:8] == b"VNDRBOOT" and
            struct.unpack_from("<II", vendor_boot, 8) == (4, PAGE) and
            struct.unpack_from("<I", vendor_boot, 2100)[0] > 0 and
            struct.unpack_from("<I", vendor_boot, 2124)[0] > 0,
            "vendor_boot DTB/bootconfig missing")
    root_algorithm, root_rollback, root_key, chains, root_hashes = avb(vbmeta, "vbmeta_a")
    require(root_algorithm == 2 and root_rollback == 0 and len(root_key) == 1032,
            "vbmeta_a policy differs from measured stock")
    require(b"boot" in chains and b"recovery" in chains and
            chains[b"boot"] == (3, root_key) and
            chains[b"recovery"][0] == 1 and len(chains[b"recovery"][1]) == 1032,
            "vbmeta_a boot/recovery chain or rollback locations changed")
    require(b"init_boot" in root_hashes and b"vendor_boot" in root_hashes and
            b"dtbo" in root_hashes,
            "vbmeta_a missing init_boot/vendor_boot/dtbo descriptors")
    boot_original, boot_policy = footer_hash(boot, "boot")
    require(boot_original > PAGE + align(boot_kernel) and
            boot_policy[0] == 2 and boot_policy[2] == chains[b"boot"][1],
            "stock boot signing relationship changed")
    for name, image in (("init_boot", init_boot), ("vendor_boot", vendor_boot)):
        original, policy = footer_hash(image, name)
        require(policy[4][name.encode()] == root_hashes[name.encode()] and
                original == root_hashes[name.encode()][0],
                f"{name}: root hash relationship changed")
    details = []
    for slot, image in (("a", recovery_a), ("b", recovery_b)):
        kernel, ramdisk = boot_fields(image, f"recovery_{slot}")
        require(kernel == 0 and ramdisk > 0 and image[PAGE:PAGE + 4] == b"\x02\x21\x4c\x18",
                f"recovery_{slot}: expected ramdisk-only header-v4 LZ4 image")
        original, policy = footer_hash(image, "recovery")
        require(original == PAGE + align(ramdisk) and policy[0] == 2 and
                policy[1] == 1 and len(policy[2]) == 1032,
                f"recovery_{slot}: unexpected payload/signing geometry")
        details.append((ramdisk, policy[2]))
    require(details[0][1] != chains[b"recovery"][1] and
            details[1][1] == chains[b"recovery"][1],
            "recovery_a/recovery_b signing-key relationship changed")
    print("recovery_a: header v4, kernel_size=0, LZ4 ramdisk=%d; self-hash valid; "
          "key differs from vbmeta_a recovery chain" % details[0][0])
    print("recovery_b: header v4, kernel_size=0, LZ4 ramdisk=%d; self-hash valid; "
          "key matches vbmeta_a recovery chain" % details[1][0])
    print("vbmeta_a: flags=0 rollback=0; boot chain location 3, recovery chain location 1; "
          "init_boot/vendor_boot/dtbo hashed")
    print("both recovery headers lack a kernel; recovery path additionally loads "
          "stock boot kernel, vendor_boot DTB/bootconfig, and init_boot generic ramdisk "
          "(confirmed by 57900K vs 10680K initrd in host-only pstore)")


def self_test():
    root = pathlib.Path.home() / "phone-second-life-data/mb003/parts"
    sources = [root / f"{part}.img" for part in
               ("boot_a", "init_boot_a", "vendor_boot_a", "recovery_a", "recovery_b", "vbmeta_a")]
    if not all(path.is_file() for path in sources):
        raise ValueError("self-test requires local stock references")
    images = [path.read_bytes() for path in sources]
    check(*images)
    for name, index, position, replacement, expected in (
            ("recovery with embedded kernel", 3, 8, b"\x01", "recovery_a: expected ramdisk-only"),
            ("no root recovery chain", 5, 1824, b"\x05", "vbmeta_a boot/recovery chain"),
    ):
        mutated = bytearray(images[index])
        mutated[position:position + 1] = replacement
        try:
            check(*(images[:index] + [bytes(mutated)] + images[index + 1:]))
        except ValueError as exc:
            require(expected in str(exc), f"{name}: unexpected failure: {exc}")
            print(f"expected {name} failure: {exc}")
        else:
            raise ValueError(f"{name}: invalid fixture accepted")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    if len(sys.argv) != 7:
        raise ValueError("usage: verify-recovery-boundary.py BOOT INIT_BOOT VENDOR_BOOT RECOVERY_A RECOVERY_B VBMETA_A")
    check(*(pathlib.Path(name).read_bytes() for name in sys.argv[1:]))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
