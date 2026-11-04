#!/usr/bin/env python3
import hashlib
import importlib.util
import lzma
import pathlib
import struct
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = "omnipha-sm7635-route-cache-pair-v1"
MANIFEST_NAME = "root-contract-route-cache-pair.manifest.json"
IMAGES = (("init_boot_a", "init_boot-route-cache-candidate.img", 8388608),
          ("vendor_boot_b", "vendor_boot_b-route-cache-candidate.img", 100663296))
USAGE = ("usage: verify-route-cache-pair-manifest.py "
         "write|verify INIT CARRIER MANIFEST STOCK_INIT BASE STOCK_VENDOR_B LOCK "
         "[--lock-fd N] | invalidate INIT CARRIER MANIFEST LOCK [--lock-fd N]")


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest = load("verify-dependent-pair-manifest.py", "route_cache_pair_manifest")
CANONICAL_SCHEMA = manifest.SCHEMA
CANONICAL_NAMES = frozenset((manifest.MANIFEST_NAME, *(item[1] for item in manifest.IMAGES)))
manifest.SCHEMA = SCHEMA
manifest.MANIFEST_NAME = MANIFEST_NAME
manifest.IMAGES = IMAGES
manifest.USAGE = USAGE


def verified_pair(init_path, carrier_path, refs):
    init, init_identity = manifest.snapshot(init_path, IMAGES[0][2])
    carrier, carrier_identity = manifest.snapshot(carrier_path, IMAGES[1][2])
    stock_init, base_image, stock_carrier = (manifest.read_reference(path) for path in refs)
    variant = load("build-init-boot-route-cache-candidate.py", "route_cache_pair_variant")
    checker = manifest.load("verify-init-boot-psoc-hold-wlan-node.py", "route_cache_pair_decode")
    digest, carrier_digest, _cpio_size, _frame_size = variant.verify_candidate(
        init, carrier, stock_init, base_image, stock_carrier,
        variant.verifier.base.lz4(), checker.hostkey_checker.decode_frame)
    manifest.require(digest == hashlib.sha256(init).hexdigest() and
                     carrier_digest == hashlib.sha256(carrier).hexdigest())
    manifest.unchanged(init_path, IMAGES[0][2], digest, init_identity)
    manifest.unchanged(carrier_path, IMAGES[1][2], carrier_digest, carrier_identity)
    return (digest, carrier_digest), (init_identity, carrier_identity)


manifest.verified_pair = verified_pair


def check_wrapper():
    names = (MANIFEST_NAME, *(item[1] for item in IMAGES))
    manifest.require(SCHEMA != CANONICAL_SCHEMA and len(set(names)) == 3 and
                     set(names).isdisjoint(CANONICAL_NAMES) and
                     manifest.SCHEMA == SCHEMA and manifest.MANIFEST_NAME == MANIFEST_NAME and
                     manifest.IMAGES == IMAGES and manifest.USAGE == USAGE and
                     manifest.verified_pair is verified_pair and
                     manifest.main.__globals__ is manifest.__dict__,
                     "unsafe route-cache candidate manifest wrapper")


def main():
    check_wrapper()
    manifest.main()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError, struct.error,
            lzma.LZMAError, tarfile.TarError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
