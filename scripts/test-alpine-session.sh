#!/bin/sh
set -eu
HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
BUILD="$HERE/build-alpine-session.py"
CACHE=${CACHE:-$HOME/sm7635-build/i139-userspace/cache}
WORK=$(mktemp -d /tmp/issue139-session-tests.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

failures=0
fail() { echo "FAIL: $*"; failures=$((failures + 1)); }

for s in "$HERE/pmos-session-stage.sh" "$HERE/pmos-session-teardown.sh"; do
	if grep -qEi 'fastboot|adb |flash|reboot|mkfs|\bdd\b|/data|init_boot|vbmeta|super|partition' "$s"; then
		fail "$s references a forbidden device/persistent operation"
	fi
done

python3 -B - "$BUILD" "$CACHE" "$WORK" <<'PY'
import importlib.util, pathlib, shutil, sys
build, cache, work = (pathlib.Path(a) for a in sys.argv[1:4])
spec = importlib.util.spec_from_file_location("b", build)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
text = m.LOCK.read_text()
fails = []

def expect_reject(label, fn):
    try:
        fn()
        fails.append(label + " was accepted")
    except ValueError:
        pass

def lock_of(body):
    p = work / "lock.lock"
    p.write_text(body)
    old = m.LOCK
    m.LOCK = p
    try:
        return m.parse_lock(p.read_text())
    finally:
        m.LOCK = old

base = lock_of(text)
assert len(base) == 134, "expected 134 pinned packages"

dup = text + "main musl 1.2.5-r12 1 1 " + "0" * 64 + "\n"
expect_reject("duplicate package", lambda: lock_of(dup))

bad_sha = text.replace("f37e73d41880bbc653b771c7d8962c8739bff773503f5155c14fab1bd7c4d52f",
                       "Z" * 64, 1)
expect_reject("non-hex digest", lambda: lock_of(bad_sha))

short = text.replace("main musl 1.2.5-r12 418096", "main musl 1.2.5-r12 0", 1)
expect_reject("zero apk size", lambda: lock_of(short))

badrepo = text.replace("main musl ", "bogusrepo musl ", 1)
expect_reject("unknown repository", lambda: lock_of(badrepo))

expect_reject("incomplete closure", lambda: lock_of(text.replace("main musl 1.2.5-r12", "# x", 1)))

no_pmos = "\n".join(l for l in text.splitlines() if not l.startswith("postmarketos postmarketos-base "))
expect_reject("missing postmarketos-base", lambda: lock_of(no_pmos + "\n"))

expect_reject("cache==output", lambda: m.assemble(work, work, True))
inrepo = build.parent.parent / "tmp-issue139-forbidden"
expect_reject("in-repo output", lambda: m.assemble(cache, inrepo, True))
assert not inrepo.exists(), "refused in-repo output must not be created"

if cache.is_dir():
    good = cache / "musl-1.2.5-r12.apk"
    if good.exists():
        c2 = work / "corrupt-cache"
        c2.mkdir()
        for f in cache.iterdir():
            (c2 / f.name).symlink_to(f)
        corrupt = c2 / "musl-1.2.5-r12.apk"
        corrupt.unlink()
        data = bytearray(good.read_bytes())
        data[len(data) // 2] ^= 0xFF
        corrupt.write_bytes(bytes(data))
        try:
            m.fetch(c2, "musl-1.2.5-r12.apk", "x", base["musl"][4], True)
            fails.append("corrupt cached APK was accepted")
        except ValueError as e:
            if "checksum" not in str(e):
                fails.append("corrupt APK raised wrong error: " + str(e))

        bad_index = c2 / "main-APKINDEX.tar.gz"
        bad_index.unlink()
        altered = bytearray((cache / "main-APKINDEX.tar.gz").read_bytes())
        altered[len(altered) // 2] ^= 0xFF
        bad_index.write_bytes(bytes(altered))
        try:
            m.fetch(c2, "main-APKINDEX.tar.gz", "x", m.SOURCES["main"][1], True)
            fails.append("corrupt index was accepted")
        except ValueError as e:
            if "checksum" not in str(e):
                fails.append("corrupt index raised wrong error: " + str(e))

for f in fails:
    print("PYFAIL:", f)
raise SystemExit(1 if fails else 0)
PY
[ $? -eq 0 ] || fail "python negative-fixture block reported failures"

python3 -B - "$BUILD" "$CACHE" "$WORK" <<'PY'
import importlib.util, pathlib, struct, sys, tarfile
build, cache, work = (pathlib.Path(a) for a in sys.argv[1:4])
spec = importlib.util.spec_from_file_location("b", build)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
fails = []

def reject(label, fn):
    try:
        fn()
        fails.append(label + " was accepted")
    except ValueError:
        pass

stage = work / "x86"
(stage / "lib").mkdir(parents=True)
(stage / "usr/lib").mkdir(parents=True)
bad = stage / "bin"
bad.mkdir()
elf = bytearray(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 10)
elf[18:20] = struct.pack("<H", 62)  # EM_X86_64
(bad / "prog").write_bytes(bytes(elf))
reject("wrong-architecture ELF", lambda: m.check_runtime(stage))

if cache.is_dir() and (cache / "iw-6.9-r0.apk").exists():
    stage2 = work / "missinglib"
    (stage2 / "lib").mkdir(parents=True)
    (stage2 / "usr/lib").mkdir(parents=True)
    (stage2 / "usr/sbin").mkdir(parents=True)
    (stage2 / "bin").mkdir(parents=True)
    with tarfile.open(cache / "iw-6.9-r0.apk") as arc:
        data = arc.extractfile(arc.getmember("usr/sbin/iw")).read()
    (stage2 / "usr/sbin/iw").write_bytes(data)
    (stage2 / "usr/sbin/iw").chmod(0o755)
    (stage2 / "usr/lib/os-release").write_text('ID="postmarketos"\n')
    (stage2 / "bin/sh").symlink_to("busybox")
    (stage2 / "usr/sbin/dropbear").write_bytes(data)
    (stage2 / "sbin").mkdir()
    (stage2 / "sbin/wpa_supplicant").write_bytes(data)
    reject("missing NEEDED library", lambda: m.check_runtime(stage2))

for f in fails:
    print("PYFAIL:", f)
raise SystemExit(1 if fails else 0)
PY
[ $? -eq 0 ] || fail "check_runtime negative fixtures reported failures"

if [ -d "$CACHE" ] && command -v qemu-aarch64 >/dev/null 2>&1 &&
   command -v bwrap >/dev/null 2>&1 && command -v readelf >/dev/null 2>&1; then
	if python3 -B "$BUILD" --cache "$CACHE" --output "$WORK/out1" --offline \
	   >"$WORK/build1.json" 2>&1; then
		python3 -B "$BUILD" --cache "$CACHE" --output "$WORK/out2" --offline \
			>"$WORK/build2.json" 2>&1 || fail "second offline build failed"
		cmp -s "$WORK/out1/postmarketos-session-aarch64.tar.gz" \
		     "$WORK/out2/postmarketos-session-aarch64.tar.gz" ||
			fail "two offline builds are not byte-identical"
		grep -q '"packages": 134' "$WORK/build1.json" ||
			fail "summary must report 134 packages"
		stage_pin=$(grep '^PMOS_SHA256=' "$HERE/pmos-session-stage.sh" | cut -d= -f2)
		archive_hash=$(sha256sum "$WORK/out1/postmarketos-session-aarch64.tar.gz" | cut -d' ' -f1)
		[ "$stage_pin" = "$archive_hash" ] || fail "guest staging SHA does not match the reproduced archive"
		mkdir -p "$WORK/rootfs"
		tar -xzf "$WORK/out1/postmarketos-session-aarch64.tar.gz" -C "$WORK/rootfs"
		bwrap --bind "$WORK/rootfs" / --proc /proc --dev /dev \
			--unshare-all --chdir / /bin/sh -c \
			'/bin/busybox cat /etc/os-release | /bin/busybox grep -q "ID=\"postmarketos\""; /sbin/apk --version; /usr/sbin/dropbear -V; /usr/sbin/iw --version; /sbin/wpa_supplicant -v' \
			>"$WORK/smoke.out" 2>&1 || { fail "chroot smoke failed"; cat "$WORK/smoke.out"; }
		grep -q "postmarketOS v24.12" "$WORK/rootfs/usr/lib/os-release" ||
			fail "staged userspace is not postmarketOS v24.12"
		[ ! -e "$WORK/rootfs/root/.ssh/authorized_keys" ] ||
			fail "stage must not contain credentials"
		echo "pass: offline reproducible build + real chroot smoke (host QEMU/bwrap only)"
	else
		cat "$WORK/build1.json"
		fail "positive offline build failed"
	fi
else
	echo "skip: positive build/smoke needs pinned cache + qemu-aarch64 + bwrap + readelf"
fi

if [ "$failures" -ne 0 ]; then
	echo "$failures FAILURE(S)"
	exit 1
fi
echo "pass: build-alpine-session.py guards reject corrupt/incomplete/misplaced inputs"
echo "synthetic + host-cached only: no device, flash, SSH or network write"
