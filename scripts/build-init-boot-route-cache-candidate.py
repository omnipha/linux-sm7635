import hashlib
import importlib.util
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN113_INIT = "d7bba4548fb47c170e374b3cc070ef8494e33f82054f8aba0523beb468e9e45c"
RUN113_CARRIER = "221bfd82e142d262473fe3a094b81882e5572e405d95d9df45de45f078fb5500"
VARIANT_MSG = "route-cache candidate is not the exact pinned variant"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canonical = load("build-init-boot-persistent-root.py", "route_cache_canonical_builder")
builder = load("build-init-boot-persistent-root.py", "route_cache_variant_builder")
route_cache = load("derive-route-cache-gated-ack.py", "route_cache_deriver")
require = builder.require
require(canonical.GATED_POST_SHA == route_cache.OLD_POST_SHA and
        canonical.GATED_HOOK_SHA == route_cache.OLD_HOOK_SHA and
        builder.GATED_POST_SHA == route_cache.OLD_POST_SHA and
        builder.GATED_HOOK_SHA == route_cache.OLD_HOOK_SHA, VARIANT_MSG)


def gated_artifacts(staged_radio, source_post, probe):
    artifacts = canonical.gated_artifacts(staged_radio, source_post, probe)
    post, hook = route_cache.derive(artifacts[builder.FRESH_POST], artifacts[builder.GATED_HOOK])
    return {**artifacts, builder.FRESH_POST: post, builder.GATED_HOOK: hook}


builder.GATED_POST_SHA = route_cache.POST_SHA
builder.GATED_HOOK_SHA = route_cache.HOOK_SHA
builder.gated_artifacts = gated_artifacts
builder.REFUSED = builder.REFUSED | frozenset((RUN113_INIT, RUN113_CARRIER))
verifier = load("verify-init-boot-persistent-root.py", "route_cache_variant_verifier")
verifier.builder = builder
require(verifier.builder is builder and RUN113_INIT in verifier.refused() and
        RUN113_CARRIER in verifier.refused(), VARIANT_MSG)


def replace_count(data, old, new, count):
    require(isinstance(data, bytes) and bool(old) and count > 0 and data.count(old) == count, VARIANT_MSG)
    return data.replace(old, new, count)


def runtime_scripts():
    original = canonical.runtime_scripts()
    candidate = builder.runtime_scripts()
    expected = dict(original)
    expected[builder.FRESH_POST], expected[builder.GATED_HOOK] = route_cache.derive(
        original[builder.FRESH_POST], original[builder.GATED_HOOK])
    stage_name = "pmos-session-stage.sh"
    self_stage_name = "pmos-self-stage.sh"
    expected[stage_name] = replace_count(original[stage_name], route_cache.OLD_HOOK_SHA.encode(),
                                         route_cache.HOOK_SHA.encode(), 1)
    self_stage = replace_count(original[self_stage_name], route_cache.OLD_POST_SHA.encode(),
                               route_cache.POST_SHA.encode(), 3)
    self_stage = replace_count(self_stage, route_cache.OLD_HOOK_SHA.encode(),
                               route_cache.HOOK_SHA.encode(), 3)
    old_pin = b"STAGE_SHA=" + hashlib.sha256(original[stage_name]).hexdigest().encode()
    new_pin = b"STAGE_SHA=" + hashlib.sha256(expected[stage_name]).hexdigest().encode()
    require(original[self_stage_name].count(old_pin) == 1, VARIANT_MSG)
    expected[self_stage_name] = replace_count(self_stage, old_pin, new_pin, 1)
    require(candidate == expected, VARIANT_MSG)
    verifier.check_runtime_scripts(candidate)
    return candidate


def build_candidate(stock, base_image, stock_carrier, library, decode_frame):
    current = runtime_scripts()
    built = builder.build(stock, base_image, current, library, decode_frame, stock_carrier)
    checked = verifier.check_pair(built[0], built[1], stock, base_image, stock_carrier,
                                  current, library, decode_frame)
    require(checked == (built[2], built[3], built[4], built[5]), VARIANT_MSG)
    return built


def verify_candidate(init_image, carrier, stock, base_image, stock_carrier, library, decode_frame):
    return verifier.check_pair(init_image, carrier, stock, base_image, stock_carrier,
                               runtime_scripts(), library, decode_frame)


def main():
    raise SystemExit("host-only variant module: image output is disabled pending candidate manifest and migration review")


if __name__ == "__main__":
    main()
