import hashlib
import pathlib
import struct
import sys
import zlib

PAGE = 4096
STOCK_BOOT_SHA256 = "197aff11679301ca4a2d6f74dfcb942c3543ac9d41628e4e2116af0bdb706d4d"
STOCK_BOOT_SIZE = 100663296
STOCK_KERNEL_SIZE = 13949926
PREFIX_SIZE = 13955072
PAYLOAD_BOUND = 13967360
KERNEL_SIZE_OFFSET = 8
GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03"
SIZE_MSG = "payload does not fit before the stock signed-tail AVB0 record"
STOCK_MSG = "stock boot_a is not the verified slot-A reference"
FRAME_MSG = "payload does not carry the stock gzip framing"
LEVEL_MSG = "payload is not deterministic zlib level 9 of its decompressed Image"
BOUND_MSG = "payload exceeds the 13967360-byte signed-tail bound"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def recompress(image):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, 8, zlib.Z_DEFAULT_STRATEGY)
    body = compressor.compress(image) + compressor.flush()
    return (GZIP_HEADER + body +
            struct.pack("<II", zlib.crc32(image) & 0xFFFFFFFF, len(image) & 0xFFFFFFFF))


def check_payload(payload):
    require(len(payload) <= PAYLOAD_BOUND, BOUND_MSG)
    require(payload[:10] == GZIP_HEADER, FRAME_MSG)
    require(PAGE + len(payload) <= PREFIX_SIZE, SIZE_MSG)
    image = zlib.decompress(payload[10:-8], -zlib.MAX_WBITS)
    require(struct.unpack_from("<II", payload, len(payload) - 8) ==
            (zlib.crc32(image) & 0xFFFFFFFF, len(image) & 0xFFFFFFFF), FRAME_MSG)
    require(payload == recompress(image), LEVEL_MSG)
    return image


def assemble(stock, payload):
    require(len(stock) == STOCK_BOOT_SIZE and sha256(stock) == STOCK_BOOT_SHA256, STOCK_MSG)
    require(struct.unpack_from("<I", stock, KERNEL_SIZE_OFFSET)[0] == STOCK_KERNEL_SIZE, STOCK_MSG)
    check_payload(payload)
    image = bytearray(stock)
    struct.pack_into("<I", image, KERNEL_SIZE_OFFSET, len(payload))
    image[PAGE:PREFIX_SIZE] = payload + bytes(PREFIX_SIZE - PAGE - len(payload))
    return bytes(image)


def main():
    require(len(sys.argv) == 6 and sys.argv[1] == "--build",
            "usage: build-diagnostic-signed-tail-payload.py --build STOCK_BOOT GZIP CONFIG OUTPUT")
    stock, payload, config = (pathlib.Path(name).read_bytes() for name in sys.argv[2:5])
    require(b"\n# CONFIG_EXT4_FS is not set\n" in config and b"\nCONFIG_EXT4_FS=" not in config,
            "config is not the EXT4_FS-off diagnostic config")
    image = assemble(stock, payload)
    pathlib.Path(sys.argv[5]).write_bytes(image)
    print(f"boot image: {len(image)} bytes, SHA-256 {sha256(image)}")
    print(f"payload: {len(payload)} bytes, bound {PAYLOAD_BOUND}, "
          f"{PAYLOAD_BOUND - len(payload)} bytes of margin")
    print(f"kernel-size field: {STOCK_KERNEL_SIZE} -> {len(payload)}")
    print(f"zero padding: [{PAGE + len(payload)}, {PREFIX_SIZE}) = "
          f"{PREFIX_SIZE - PAGE - len(payload)} bytes")
    print(f"stock tail from offset {PREFIX_SIZE} through the AVBf footer: "
          f"{STOCK_BOOT_SIZE - PREFIX_SIZE} bytes, unchanged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, struct.error, zlib.error) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
