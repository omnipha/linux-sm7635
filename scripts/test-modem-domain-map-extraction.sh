#!/bin/sh
# Synthetic-only tests for extract-modem-domain-maps.py (#88).
# Every fixture is a generated synthetic FAT12 image, explicitly marked
# SYNTHETIC NON-STOCK NON-FLASHABLE. Nothing here is stock evidence and no
# device is touched.
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
WORK=$(mktemp -d /tmp/issue88-synthetic-tests.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
EXTRACT="$HERE/extract-modem-domain-maps.py"
MAKE="$HERE/make-synthetic-modem-dump.py"

failures=0
expect_pass() {
    name=$1; shift
    if "$@" >"$WORK/$name.out" 2>&1; then
        echo "pass (expected success): $name"
    else
        echo "FAIL (unexpected failure): $name"
        cat "$WORK/$name.out"
        failures=$((failures + 1))
    fi
}
expect_fail() {
    name=$1; shift
    if "$@" >"$WORK/$name.out" 2>&1; then
        echo "FAIL (unexpected success): $name"
        failures=$((failures + 1))
    else
        message=$(cat "$WORK/$name.out")
        if [ "$(printf '%s' "$message" | wc -c)" -le 220 ]; then
            echo "pass (expected bounded failure): $name"
        else
            echo "FAIL (error message unbounded): $name"
            failures=$((failures + 1))
        fi
    fi
}

python3 "$MAKE" "$WORK/good.img" good
expect_pass good python3 "$EXTRACT" "$WORK/good.img" --out "$WORK/out-good" --expect-synthetic
grep -q '^jsn_under_image=2$' "$WORK/out-good/extraction-manifest.txt" ||
    { echo "FAIL: good fixture must record two .jsn under image/"; failures=$((failures + 1)); }
grep -q '^jsn_outside_image=0$' "$WORK/out-good/extraction-manifest.txt" ||
    { echo "FAIL: good fixture must record zero outside .jsn"; failures=$((failures + 1)); }
grep -q '^synthetic=true$' "$WORK/out-good/extraction-manifest.txt" ||
    { echo "FAIL: good fixture must be stamped synthetic"; failures=$((failures + 1)); }
grep -q '^non_flashable=true$' "$WORK/out-good/extraction-manifest.txt" ||
    { echo "FAIL: outputs must be stamped non-flashable"; failures=$((failures + 1)); }
grep -q '^stock_verified=false$' "$WORK/out-good/extraction-manifest.txt" ||
    { echo "FAIL: outputs must not claim stock verification"; failures=$((failures + 1)); }
grep -q '"providers"' "$WORK/out-good/pd-mapper.conf.json" ||
    { echo "FAIL: derived config must carry providers"; failures=$((failures + 1)); }
[ -f "$WORK/out-good/maps/image/first.jsn" ] && [ -f "$WORK/out-good/maps/image/nested/second.jsn" ] ||
    { echo "FAIL: exact .jsn bytes must be preserved under maps/"; failures=$((failures + 1)); }
if python3 - "$WORK/out-good" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
config = json.loads((out / "pd-mapper.conf.json").read_text())
maps = json.loads((out / "domain-maps.json").read_text())
assert config["synthetic"] is True and config["non_flashable"] is True
assert config["stock_verified"] is False
assert len(config["providers"]) == 2, config["providers"]
assert all(p["sr_version"] == 1 for p in config["providers"])
assert sorted(p["subdomain"] for p in config["providers"]) == ["modem", "wlan"]
assert all(s["provider"] == "synthetic" and s["service"]
           for p in config["providers"] for s in p["services"])
assert len(maps["files"]) == 2
assert all(f["under_image"] for f in maps["files"])
assert {f["path"] for f in maps["files"]} == {"image/first.jsn", "image/nested/second.jsn"}
print("pass: derived config and map records match the synthetic input")
PY
then :
else
    echo "FAIL: config assertion block failed"
    failures=$((failures + 1))
fi

python3 "$MAKE" "$WORK/elsewhere.img" elsewhere
expect_pass elsewhere python3 "$EXTRACT" "$WORK/elsewhere.img" --out "$WORK/out-elsewhere" --expect-synthetic
grep -q '^jsn_outside_image=1$' "$WORK/out-elsewhere/extraction-manifest.txt" ||
    { echo "FAIL: elsewhere fixture must record one outside .jsn"; failures=$((failures + 1)); }
grep -q '^jsn_file=outside.jsn .*under_image=no$' "$WORK/out-elsewhere/extraction-manifest.txt" ||
    { echo "FAIL: outside .jsn must be listed with its hash"; failures=$((failures + 1)); }

python3 "$MAKE" "$WORK/empty.img" empty
expect_fail empty python3 "$EXTRACT" "$WORK/empty.img" --out "$WORK/out-empty" --expect-synthetic
[ ! -e "$WORK/out-empty" ] ||
    { echo "FAIL: failed extraction must not leave an output directory"; failures=$((failures + 1)); }

for case in no-image bad-json bad-schema duplicate invalid-name loop conflict; do
    python3 "$MAKE" "$WORK/$case.img" "$case"
    expect_fail "$case" python3 "$EXTRACT" "$WORK/$case.img" --out "$WORK/out-$case" --expect-synthetic
done

python3 "$MAKE" "$WORK/flat.img" flat
expect_pass flat python3 "$EXTRACT" "$WORK/flat.img" --out "$WORK/out-flat" --expect-synthetic
if python3 - "$WORK/out-flat" <<'PY'
import json, pathlib, sys
config = json.loads((pathlib.Path(sys.argv[1]) / "pd-mapper.conf.json").read_text())
assert len(config["providers"]) == 2
flat = [p for p in config["providers"] if p["subdomain"] == "modem"][0]
assert flat["provider"] == "synthetic" and flat["qmi_instance_id"] is None
service = flat["services"][0]
assert service["service_data_valid"] == 1 and service["service_data"] == 7
print("pass: flat stock-string schema is accepted without dropping fields")
PY
then :
else
    echo "FAIL: flat-schema assertion failed"
    failures=$((failures + 1))
fi

python3 "$MAKE" "$WORK/noversion.img" noversion
expect_pass noversion python3 "$EXTRACT" "$WORK/noversion.img" --out "$WORK/out-noversion" --expect-synthetic
grep -q '^providers=2$' "$WORK/out-noversion/extraction-manifest.txt" ||
    { echo "FAIL: upstream nested schema without sr_version must still derive groups"; failures=$((failures + 1)); }

expect_fail bad-arg python3 "$EXTRACT" "$WORK/good.img" --out "$WORK/x" --expect-synthetic --bogus

head -c 1024 "$WORK/good.img" > "$WORK/short.img"
expect_fail short python3 "$EXTRACT" "$WORK/short.img" --out "$WORK/out-short"
printf 'not a fat image, just text padding to a sector boundary\n%0.sX' $(seq 1 480) > "$WORK/text.img"
expect_fail text python3 "$EXTRACT" "$WORK/text.img" --out "$WORK/out-text"
expect_fail missing python3 "$EXTRACT" "$WORK/does-not-exist.img" --out "$WORK/out-missing"

cp "$WORK/good.img" "$WORK/in-repo.img"
expect_fail in-repo-output python3 "$EXTRACT" "$WORK/in-repo.img" --out "$HERE/../tmp-issue88-out" --expect-synthetic
[ ! -e "$HERE/../tmp-issue88-out" ] ||
    { echo "FAIL: refused in-repo output must not create a directory"; failures=$((failures + 1)); }

echo "negative: repeated run into a non-empty output directory"
expect_fail reuse python3 "$EXTRACT" "$WORK/good.img" --out "$WORK/out-good" --expect-synthetic

if [ "$failures" -eq 0 ]; then
    echo "ALL SYNTHETIC TESTS PASSED"
    exit 0
fi
echo "$failures FAILURE(S)"
exit 1
