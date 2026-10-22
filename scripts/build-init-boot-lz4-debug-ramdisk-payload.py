import ctypes
import gzip
import hashlib
import pathlib
import struct
import sys

PAGE = 4096
IMAGE_SIZE = 8388608
HEADER_SIZE = 1584
RAMDISK_SIZE_OFFSET = 12
TAIL_OFFSET = 2121728
MAX_FRAME = TAIL_OFFSET - PAGE
VBMETA_SIZE = 832
FOOTER_OFFSET = IMAGE_SIZE - 64
STOCK_RAMDISK_SIZE = 2113581
STOCK_CPIO_SIZE = 3900160
GZIP_SIZE = 1672600
CPIO_SIZE = 3481088
HC_LEVEL = 12
LZ4_VERSION = 11000
LZ4_MAGIC = b"\x02\x21\x4c\x18"
STOCK_SHA256 = "baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193"
GZIP_SHA256 = "caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f"
CPIO_SHA256 = "2998685ec31696017828f92934e867b47fe14df375c259d37e98b40f3dd52ee7"
FRAME_SIZE = 1927750
BLOCK_SIZE = 1927742
RESULT_SHA256 = "3932504af4a962d39d4c44def68eb9bd0c9a87e79d415279b40ed2e432243527"
PRIOR_IMAGES = (
    STOCK_SHA256,
    "f4a00ce3a1926f9b54eaa958158691efaabe90a9ea715d2bac3d424095f2f948",
    "f4b987ee9a6082a22201c763e1d437dcc1dee0c62f2e2e0d8e7a3ffad8078e89",
    "bde3a3b3bc7ea587f195de63de76db5f14f8dfd197d6d3224904f722af18fd31",
    "6078269d48d1aba27688dc9a8694dc2bf89156622680bcd6c99554b444ecfc4d",
    "237259404601045205715a71b88016744c73729d4513349cfe90c754b0dc1253",
    "5e866c5416791d873b8da1a9d4ac3da63ac4dd05cf36a85aa65da1a084eb7efb",
    "84f7f5eab84f5043898ec742cddd943ad6432a71c24ced800532b78b7a3d724a",
    "116b1662760757d5a2652a55766c28f259c967c91f5de8b4c7168fc46ed174ce",
    "1fdc25705bbc93a6a7a57082e7054a02f5a29a59690d5958567921ad4350acc7",
    "55fa78ca428ea84f62bde55f4ee5468f84fd34f45ce9e6a6ba1fed2f119e47af",
    "968625c761b8d8d8c35aafc30b86919aa03d51d1f82c7956b4d714df42e530fc",
    "db2c635d5c51aed47cf6a626244bba5be6e6eeb240f0dd2d0ed0e72d85fdff00",
    "13a48ff9d11116d83cd420abffe47bc976f9378da87c2df7276db7e77b75e450",
    "6891dc5194eeada689ad530a73c8d57c6d672d8cdde3912ae0e0f1ede7c20555",
    "d966172c9bfbcbc7c70f8be3b6cd84be2947986baf7cf02bcbaa987baa913131",
    "5a513998cda8d0a47d69d9b1369b7019c5cdd30bb317fc9fe741ff056de0113b",
    "dc990b9517d53431fcaeebb2b0498e6e64d3e7cbbc7e469d3e0bfc73abe00075",
    "e7fd20222371b4d8d81140422fd7bc74974029999770e3fea0b5c98f5e3eab5f",
    "7c409cdefe9e0f24cbe53e44d5bbab8ff50adadb9fbfb26d64917fe1a6fc4ddf",
    "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d",
    "7cd886a24121c878a62839424b6b7f88840ba7504eb09cd0720eec96cb8ecfe5",
    "f1406364c3e393cb0a779edfdf4da657eb69169bfc54f5b379cd462c4a5653d3",
    "65fc21c462e681bf046c10d3dbe55ac6c8de3fdab975a70b2fb423358a31123f",
    "93e7625f003ce1b67792d32fdc302b7f903eeb61fbc9d1a44396d0e73e7a2afd",
    "c4f7dbee6d3770b0991b891f6f9a7d9b3685ed3dec3d28cbddfdc0f6b9b50244",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def lz4():
    library = ctypes.CDLL("liblz4.so.1")
    require(library.LZ4_versionNumber() == LZ4_VERSION, "liblz4.so.1 is not version 1.10.0")
    library.LZ4_compressBound.argtypes = [ctypes.c_int]
    library.LZ4_compressBound.restype = ctypes.c_int
    library.LZ4_compress_HC.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    library.LZ4_compress_HC.restype = ctypes.c_int
    library.LZ4_decompress_safe.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    library.LZ4_decompress_safe.restype = ctypes.c_int
    return library


def compress_hc(library, data, level):
    bound = library.LZ4_compressBound(len(data))
    output = ctypes.create_string_buffer(bound)
    size = library.LZ4_compress_HC(data, output, len(data), bound, level)
    require(size > 0, "LZ4 HC compression failed")
    return output.raw[:size]


def decompress(library, block, size):
    output = ctypes.create_string_buffer(size)
    decoded = library.LZ4_decompress_safe(block, output, len(block), size)
    require(decoded == size, "LZ4 block does not decompress to the expected size")
    return output.raw


def check_newc(archive):
    pos = 0
    names = []
    while True:
        require(pos + 110 <= len(archive) and archive[pos:pos + 6] == b"070701",
                "debug cpio is not a newc archive ending in TRAILER!!!")
        try:
            fields = [int(archive[pos + 6 + 8 * i:pos + 14 + 8 * i], 16) for i in range(13)]
        except ValueError as exc:
            raise ValueError("debug cpio is not a newc archive ending in TRAILER!!!") from exc
        filesize, namesize = fields[6], fields[11]
        name_end = pos + 110 + namesize
        require(namesize > 0 and name_end <= len(archive) and archive[name_end - 1] == 0,
                "debug cpio is not a newc archive ending in TRAILER!!!")
        name = archive[pos + 110:name_end - 1]
        data_start = (name_end + 3) // 4 * 4
        pos = (data_start + filesize + 3) // 4 * 4
        require(pos <= len(archive), "debug cpio is not a newc archive ending in TRAILER!!!")
        if name == b"TRAILER!!!":
            require(filesize == 0, "debug cpio is not a newc archive ending in TRAILER!!!")
            break
        names.append(name)
    require(names and not any(archive[pos:]),
            "debug cpio is not a newc archive ending in TRAILER!!!")
    return names


def legacy_frame(library, archive):
    block = compress_hc(library, archive, HC_LEVEL)
    require(decompress(library, block, len(archive)) == archive,
            "LZ4 HC block does not round-trip to the debug cpio")
    frame = LZ4_MAGIC + struct.pack("<I", len(block)) + block
    require(len(frame) == 8 + len(block) <= MAX_FRAME,
            "LZ4 legacy frame does not fit before the signed tail")
    require(len(frame) == FRAME_SIZE and len(block) == BLOCK_SIZE,
            "LZ4 HC level 12 frame is not the verified size")
    return frame


def build(stock, gzip_bytes):
    require(len(stock) == IMAGE_SIZE, "stock init_boot is not 8388608 bytes")
    require(sha256(stock) == STOCK_SHA256,
            "stock init_boot is not the verified baa33fd4 slot-A reference")
    require(len(gzip_bytes) == GZIP_SIZE, "debug gzip is not 1672600 bytes")
    require(sha256(gzip_bytes) == GZIP_SHA256,
            "debug gzip is not the verified caa3eb82 archive")
    require(gzip_bytes[:3] == b"\x1f\x8b\x08", "debug input is not gzip")
    try:
        archive = gzip.decompress(gzip_bytes)
    except (OSError, EOFError) as exc:
        raise ValueError("debug gzip does not decompress") from exc
    require(len(archive) == CPIO_SIZE and sha256(archive) == CPIO_SHA256,
            "unpacked debug cpio is not the verified archive")
    check_newc(archive)

    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", stock, 8)
    require(stock[:8] == b"ANDROID!" and struct.unpack_from("<I", stock, 40)[0] == 4 and
            header_size == HEADER_SIZE and os_version == 0 and kernel_size == 0 and
            ramdisk_size == STOCK_RAMDISK_SIZE and struct.unpack_from("<I", stock, 1580)[0] == 0
            and not any(stock[HEADER_SIZE:PAGE]) and
            not any(stock[PAGE + ramdisk_size:TAIL_OFFSET]),
            "stock init_boot is not header v4 with an empty kernel and the stock ramdisk size")
    stock_frame = stock[PAGE:PAGE + ramdisk_size]
    stock_block_size = struct.unpack_from("<I", stock_frame, 4)[0]
    require(stock_frame[:4] == LZ4_MAGIC and stock_block_size == len(stock_frame) - 8,
            "stock generic ramdisk is not one Android LZ4 legacy frame")
    footer = stock[FOOTER_OFFSET:]
    require(footer[:4] == b"AVBf" and
            struct.unpack_from(">QQQ", footer, 12) == (TAIL_OFFSET, TAIL_OFFSET, VBMETA_SIZE) and
            stock[TAIL_OFFSET:TAIL_OFFSET + 4] == b"AVB0",
            "stock AVBf footer does not point at the signed tail")

    library = lz4()
    require(compress_hc(library, decompress(library, stock_frame[8:], STOCK_CPIO_SIZE),
                        HC_LEVEL) == stock_frame[8:],
            "LZ4 HC level 12 does not reproduce the stock compressed block")
    frame = legacy_frame(library, archive)
    require(frame != gzip_bytes and not frame.startswith(b"\x1f\x8b"),
            "built frame reuses the gzip bytes")

    header = bytearray(stock[:PAGE])
    struct.pack_into("<I", header, RAMDISK_SIZE_OFFSET, len(frame))
    require(bytes(header[:RAMDISK_SIZE_OFFSET]) == stock[:RAMDISK_SIZE_OFFSET] and
            bytes(header[RAMDISK_SIZE_OFFSET + 4:PAGE]) == stock[RAMDISK_SIZE_OFFSET + 4:PAGE],
            "header differs from stock beyond the ramdisk-size field")
    image = (bytes(header) + frame + bytes(TAIL_OFFSET - PAGE - len(frame)) +
             stock[TAIL_OFFSET:])
    require(len(image) == IMAGE_SIZE and image[TAIL_OFFSET:] == stock[TAIL_OFFSET:],
            "built image moved the signed tail")
    digest = sha256(image)
    require(digest == RESULT_SHA256, "built image SHA-256 is not 3932504a")
    require(digest not in PRIOR_IMAGES, "built image repeats a prior image SHA-256")
    return image, digest


def main():
    require(len(sys.argv) == 4, "usage: build-init-boot-lz4-debug-ramdisk-payload.py "
            "STOCK_INIT_BOOT GZIP OUTPUT")
    stock = pathlib.Path(sys.argv[1]).read_bytes()
    gzip_bytes = pathlib.Path(sys.argv[2]).read_bytes()
    image, digest = build(stock, gzip_bytes)
    pathlib.Path(sys.argv[3]).write_bytes(image)
    print(f"init_boot bytes: {len(image)}")
    print(f"lz4 legacy frame bytes: {FRAME_SIZE}")
    print(f"lz4 block bytes: {BLOCK_SIZE}")
    print(f"lz4 hc level: {HC_LEVEL}")
    print(f"gap bytes: {TAIL_OFFSET - PAGE - FRAME_SIZE}")
    print(f"signed tail bytes: {IMAGE_SIZE - TAIL_OFFSET}")
    print(f"init_boot SHA-256: {digest}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
