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
VBMETA_SIZE = 832
FOOTER_OFFSET = IMAGE_SIZE - 64
STOCK_RAMDISK_SIZE = 2113581
RAMDISK_SIZE = 1672600
STOCK_SHA256 = "baa33fd43c3da1d9f3358ced9249c42abecc704fc5707a5241ea69e77c1e3193"
RAMDISK_SHA256 = "caa3eb8218b9ee3024ec884e2e8619705e91732860628b363b933944cc56f37f"
RESULT_SHA256 = "f4a00ce3a1926f9b54eaa958158691efaabe90a9ea715d2bac3d424095f2f948"
PRIOR_IMAGES = (
    STOCK_SHA256,
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
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def build(stock, ramdisk):
    require(len(stock) == IMAGE_SIZE, "stock init_boot is not 8388608 bytes")
    require(sha256(stock) == STOCK_SHA256,
            "stock init_boot is not the verified baa33fd4 slot-A reference")
    require(len(ramdisk) == RAMDISK_SIZE, "debug ramdisk is not 1672600 bytes")
    require(sha256(ramdisk) == RAMDISK_SHA256,
            "debug ramdisk is not the verified caa3eb82 gzip cpio")

    require(stock[:8] == b"ANDROID!", "stock init_boot magic is not ANDROID!")
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", stock, 8)
    require(struct.unpack_from("<I", stock, 40)[0] == 4 and header_size == HEADER_SIZE and
            os_version == 0 and kernel_size == 0 and ramdisk_size == STOCK_RAMDISK_SIZE and
            struct.unpack_from("<I", stock, 1580)[0] == 0,
            "stock init_boot is not header v4 with an empty kernel and the stock ramdisk size")
    require(not any(stock[HEADER_SIZE:PAGE]), "stock header padding is not zero")
    require(not any(stock[PAGE + ramdisk_size:TAIL_OFFSET]),
            "stock gap before the signed tail is not zero")
    footer = stock[FOOTER_OFFSET:]
    require(footer[:4] == b"AVBf" and
            struct.unpack_from(">QQQ", footer, 12) == (TAIL_OFFSET, TAIL_OFFSET, VBMETA_SIZE),
            "stock AVBf footer does not point at the signed tail")
    require(stock[TAIL_OFFSET:TAIL_OFFSET + 4] == b"AVB0",
            "stock signed tail does not start with an AVB0 block")
    require(len(ramdisk) < ramdisk_size,
            "debug ramdisk is not smaller than the stock generic ramdisk")
    require(ramdisk[:3] == b"\x1f\x8b\x08", "debug ramdisk is not gzip")
    require(gzip.decompress(ramdisk).startswith(b"070701"),
            "debug ramdisk is not a gzip newc cpio")

    header = bytearray(stock[:PAGE])
    struct.pack_into("<I", header, RAMDISK_SIZE_OFFSET, len(ramdisk))
    image = (bytes(header) + ramdisk + bytes(TAIL_OFFSET - PAGE - len(ramdisk)) +
             stock[TAIL_OFFSET:])
    require(len(image) == IMAGE_SIZE, "built image is not 8388608 bytes")
    digest = sha256(image)
    require(digest == RESULT_SHA256, "built image SHA-256 is not f4a00ce3")
    require(digest not in PRIOR_IMAGES and digest != STOCK_SHA256,
            "built image repeats a prior image SHA-256")
    return image, digest


def main():
    require(len(sys.argv) == 4,
            "usage: build-init-boot-debug-ramdisk-payload.py STOCK_INIT_BOOT RAMDISK OUTPUT")
    stock = pathlib.Path(sys.argv[1]).read_bytes()
    ramdisk = pathlib.Path(sys.argv[2]).read_bytes()
    image, digest = build(stock, ramdisk)
    output = pathlib.Path(sys.argv[3])
    output.write_bytes(image)
    print(f"init_boot bytes: {len(image)}")
    print(f"ramdisk bytes: {len(ramdisk)}")
    print(f"gap bytes: {TAIL_OFFSET - PAGE - len(ramdisk)}")
    print(f"signed tail bytes: {IMAGE_SIZE - TAIL_OFFSET}")
    print(f"init_boot SHA-256: {digest}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
