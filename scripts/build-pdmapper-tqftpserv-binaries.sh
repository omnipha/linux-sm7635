#!/usr/bin/env bash
# Host-only, reproducible static aarch64 build of pd-mapper and tqftpserv for
# issue #86, from hash-pinned upstream sources. Nothing here touches a device,
# and no output may enter this repository.
set -euo pipefail
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
STAGE=${STAGE:-$WORK/i86-sources}
MAPS=${MAPS:-$HOME/phone-second-life-data/mb003/acquire/attempt-20261025-0632-modem-a/issue-86-maps}

QRTR_TARBALL=${QRTR_TARBALL:-$STAGE/qrtr-v1.2.tar.gz}
PDMAPPER_TARBALL=${PDMAPPER_TARBALL:-$STAGE/pd-mapper-v1.1.tar.gz}
TQFTPSERV_TARBALL=${TQFTPSERV_TARBALL:-$STAGE/tqftpserv-v1.3.tar.gz}
MUSL_TARBALL=${MUSL_TARBALL:-$STAGE/musl-1.2.5.tar.gz}
XZ_TARBALL=${XZ_TARBALL:-$STAGE/xz-5.6.4.tar.xz}

QRTR_SHA256=7a82bf80246fe71287b13c66c0466208822e8337fcd4aaf302eee6c5fcb48a52
PDMAPPER_SHA256=7654a7fb8b70b0c7670f98ad9313649abc48eabcef84dad086ed01408fd538a2
TQFTPSERV_SHA256=87a3845e8f47b42f31d8aaad04c5e0707e391b3954d096aeff6f0a03467dc33f
MUSL_SHA256=a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4
XZ_SHA256=829ccfe79d769748f7557e7a4429a64d06858e27e1e362e25d01ab7b931d9c95
QRTR_COMMIT=b51ffaf22707b6000ecfb894c5b750f3bb7843b2
PDMAPPER_COMMIT=5ecd2fe926aca7abfe40724177f63b942cff3947
TQFTPSERV_COMMIT=b31de6db4f31d09119293203d39636b827f16321

# Byte-exact stock .jsn maps recorded on closed #89 (extraction by the merged
# #92 extractor from the hash-pinned 08a5caf8 dump). The maps never enter Git.
declare -A JSN_SHA256=(
	[adspr.jsn]=66ce8531efb7979d234e0f0eabbe18d038ac97da771a8a194f613df8f0724e81
	[adsps.jsn]=12ac2f3ae8ced12aa4b06b3ab3a01bc4d8efe1c92ebea503c002f209a6ec176f
	[adspua.jsn]=982a99853495e34726b8e44697fdfad303334de0a67cbf6cde306c8f1731000b
	[battmgr.jsn]=be8c6fba330908e4683fb6282761cb08485a302d6a66e09721e102e342f27236
	[cdspr.jsn]=6d01cd7dce745204d5de20efe57e2511149ca2a5b48ee562fbedefda573ca465
	[modemr.jsn]=07138bd0e249fa43db4eeb1a4516037db3bfe4bb88285e8c36f594be2b2a4b43
)
# Upstream binaries compiled for this issue; musl 1.2.5 / gcc 15.2.0 cross.
# The publish-line observability patch below is included in both pins.
PDMAPPER_BIN_SHA256=40acf0b06856205cb6cb9d53084afe5f6619fd1330c13242be1464b1dede3f43
PDMAPPER_BIN_SIZE=199008
TQFTPSERV_BIN_SHA256=4eacb4ae30fe9c1ee3078bf140bd391c0179c2e8599461c67636d26006313965
TQFTPSERV_BIN_SIZE=132592

export PYTHONDONTWRITEBYTECODE=1

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing tool: $1"; }
for tool in curl sha256sum tar make gcc aarch64-linux-gnu-gcc aarch64-linux-gnu-ar \
	aarch64-linux-gnu-strip file qemu-aarch64 python3; do
	need "$tool"
done
[ "$#" -eq 0 ] || die 'usage: build-pdmapper-tqftpserv-binaries.sh (no arguments)'
case "$(realpath -m "$OUT")/" in
	"$ROOT"/*) die "build artifacts must stay outside this repository" ;;
esac
[ -d "$OUT" ] || die "missing output directory: $OUT"

fetch() {
	local path=$1 url=$2 sha=$3
	if [ ! -f "$path" ]; then
		mkdir -p "$(dirname -- "$path")"
		curl -fL --retry 3 --retry-delay 2 -o "$path" "$url" ||
			die "could not fetch $url"
	fi
	read -r got _ < <(sha256sum "$path")
	[ "$got" = "$sha" ] || die "$path is not the pinned upstream source (sha256 $sha)"
}

mkdir -p "$STAGE"
fetch "$QRTR_TARBALL" \
	"https://github.com/andersson/qrtr/archive/refs/tags/v1.2.tar.gz" "$QRTR_SHA256"
fetch "$PDMAPPER_TARBALL" \
	"https://github.com/andersson/pd-mapper/archive/refs/tags/v1.1.tar.gz" "$PDMAPPER_SHA256"
fetch "$TQFTPSERV_TARBALL" \
	"https://github.com/andersson/tqftpserv/archive/refs/tags/v1.3.tar.gz" "$TQFTPSERV_SHA256"
fetch "$MUSL_TARBALL" "https://musl.libc.org/releases/musl-1.2.5.tar.gz" "$MUSL_SHA256"
fetch "$XZ_TARBALL" \
	"https://github.com/tukaani-project/xz/releases/download/v5.6.4/xz-5.6.4.tar.xz" \
	"$XZ_SHA256"

# The stock domain maps must be present, hash-pinned, exactly as recorded on #89.
[ -d "$MAPS/maps/image" ] || die "missing validated stock maps under $MAPS (run the #92 extractor)"
for name in "${!JSN_SHA256[@]}"; do
	[ -f "$MAPS/maps/image/$name" ] || die "missing stock map: $MAPS/maps/image/$name"
	got=$(sha256sum "$MAPS/maps/image/$name" | cut -d ' ' -f 1)
	[ "$got" = "${JSN_SHA256[$name]}" ] ||
		die "stock map $name is not the #89-recorded ${JSN_SHA256[$name]}"
done

# One build at a time on this host.
exec 9>"$WORK/i86-binaries.lock"
flock 9 || die "another i86 build holds $WORK/i86-binaries.lock"

# A deterministic stage path is mandatory: liblzma embeds LOCALEDIR (the
# install prefix) in its objects, so a random mktemp directory would make the
# pinned binary hash unreproducible.
stage=$WORK/i86-stage
rm -rf -- "$stage"
mkdir -p "$stage"
prefix=$stage/prefix
trap 'rm -rf -- "$stage"' EXIT

tar xf "$MUSL_TARBALL" -C "$stage"
tar xf "$XZ_TARBALL" -C "$stage"
tar xf "$QRTR_TARBALL" -C "$stage"
tar xf "$PDMAPPER_TARBALL" -C "$stage"
tar xf "$TQFTPSERV_TARBALL" -C "$stage"
# Observability only: upstream publishes successfully without writing a line.
# These one-line additions make a QRTR publish failure visible in /run logs.
python3 - "$stage/pd-mapper-1.1/pd-mapper.c" "$stage/tqftpserv-1.3/tqftpserv.c" <<'PY'
import pathlib, sys
pd, tq = map(pathlib.Path, sys.argv[1:])
old = """\tret = qrtr_publish(fd, SERVREG_QMI_SERVICE,
\t\t\t   SERVREG_QMI_VERSION, SERVREG_QMI_INSTANCE);
\tif (ret < 0) {
\t\tfprintf(stderr, "failed to publish service registry service\\n");
\t\texit(1);
\t}"""
new = old + """

\tfprintf(stderr, "pd-mapper: published QRTR service %u version %u instance %u\\n",
\t\tSERVREG_QMI_SERVICE, SERVREG_QMI_VERSION, SERVREG_QMI_INSTANCE);
\tfflush(stderr);"""
text = pd.read_text()
if text.count(old) != 1:
    raise SystemExit("pd-mapper publish anchor missing")
pd.write_text(text.replace(old, new, 1))
old = """\tret = qrtr_publish(fd, 4096, 1, 0);
\tif (ret < 0) {
\t\tfprintf(stderr, "failed to publish service registry service\\n");
\t\texit(1);
\t}"""
new = old + """

\tlog_err("tqftpserv: published QRTR service 4096 version 1 instance 0\\n");"""
text = tq.read_text()
if text.count(old) != 1:
    raise SystemExit("tqftpserv publish anchor missing")
tq.write_text(text.replace(old, new, 1))
PY

# musl 1.2.5 cross-built with the distro aarch64 gcc; AR/RANLIB are not
# target-prefixed by musl's configure when CC is an unprefixed cross gcc.
(
	cd "$stage/musl-1.2.5"
	CC=aarch64-linux-gnu-gcc ./configure --prefix="$prefix" --target=aarch64-linux-musl \
		>"$stage/musl-configure.log" 2>&1 || { tail -5 "$stage/musl-configure.log" >&2; exit 1; }
	sed -i 's/^AR = .*/AR = aarch64-linux-gnu-ar/;s/^RANLIB = .*/RANLIB = aarch64-linux-gnu-ranlib/' config.mak
	make -j"${JOBS:-2}" >"$stage/musl-make.log" 2>&1 || { tail -5 "$stage/musl-make.log" >&2; exit 1; }
	make install >"$stage/musl-install.log" 2>&1
)

mkdir -p "$stage/xz-build"
(
	cd "$stage/xz-build"
	../xz-5.6.4/configure --host=aarch64-musl-linux --build=x86_64-linux-gnu \
		CC="aarch64-linux-gnu-gcc -nostdinc -isystem $prefix/include -isystem /usr/lib/gcc-cross/aarch64-linux-gnu/15/include" \
		--disable-shared --enable-static --disable-nls --disable-doc --disable-lzma-links \
		--disable-scripts --with-pic=yes --prefix="$prefix" >"$stage/xz-configure.log" 2>&1 ||
		{ tail -5 "$stage/xz-configure.log" >&2; exit 1; }
	make -C src/liblzma -j"${JOBS:-2}" >"$stage/xz-make.log" 2>&1 ||
		{ tail -5 "$stage/xz-make.log" >&2; exit 1; }
	make -C src/liblzma install >"$stage/xz-install.log" 2>&1
)

XCC="aarch64-linux-gnu-gcc -nostdinc -isystem $prefix/include -isystem /usr/aarch64-linux-gnu/include -isystem $prefix/include -isystem /usr/lib/gcc-cross/aarch64-linux-gnu/15/include -fno-stack-protector -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -Os -Wall"
MLIB=$prefix/lib
LINK="-nostdlib -static -Wl,--gc-sections $MLIB/crt1.o $MLIB/crti.o -L$prefix/lib -llzma -L/usr/lib/gcc-cross/aarch64-linux-gnu/15 -lgcc $MLIB/libc.a -lgcc $MLIB/crtn.o"

mkdir -p "$stage/libqrtr"
(
	cd "$stage/libqrtr"
	for source in logging qmi qrtr; do
		# shellcheck disable=SC2086
		$XCC -c -I"$stage/qrtr-1.2/include" "$stage/qrtr-1.2/lib/$source.c" \
			-o "$source.o" 2>"$stage/libqrtr-$source.log"
	done
	aarch64-linux-gnu-ar rcs libqrtr.a logging.o qmi.o qrtr.o
)

# shellcheck disable=SC2086
$XCC -I"$stage/qrtr-1.2/include" -I"$stage/pd-mapper-1.1" \
	"$stage/pd-mapper-1.1/pd-mapper.c" "$stage/pd-mapper-1.1/assoc.c" \
	"$stage/pd-mapper-1.1/json.c" "$stage/pd-mapper-1.1/servreg_loc.c" \
	"$stage/pd-mapper-1.1/lzma_decomp.c" "$stage/libqrtr/libqrtr.a" \
	-o "$stage/pd-mapper.unstripped" $LINK 2>"$stage/pd-mapper-build.log"
# shellcheck disable=SC2086
$XCC -I"$stage/qrtr-1.2/include" \
	"$stage/tqftpserv-1.3/tqftpserv.c" "$stage/tqftpserv-1.3/translate.c" \
	"$stage/libqrtr/libqrtr.a" \
	-o "$stage/tqftpserv.unstripped" $LINK 2>"$stage/tqftpserv-build.log"

aarch64-linux-gnu-strip --strip-all -R .comment "$stage/pd-mapper.unstripped" \
	"$stage/tqftpserv.unstripped"

check_binary() {
	local path=$1 want_sha=$2 want_size=$3
	[ "$(stat -c '%s' "$path")" -eq "$want_size" ] || die "$path is not $want_size bytes"
	file "$path" | grep -q 'ARM aarch64' || die "$path is not arm64"
	file "$path" | grep -q 'statically linked' || die "$path is not static"
	read -r got _ < <(sha256sum "$path")
	[ "$got" = "$want_sha" ] || die "$path is not the pinned reproducible binary: $got"
}
[ "$PDMAPPER_BIN_SHA256" = PLACEHOLDER ] ||
	check_binary "$stage/pd-mapper.unstripped" "$PDMAPPER_BIN_SHA256" "$PDMAPPER_BIN_SIZE"
[ "$TQFTPSERV_BIN_SHA256" = PLACEHOLDER ] ||
	check_binary "$stage/tqftpserv.unstripped" "$TQFTPSERV_BIN_SHA256" "$TQFTPSERV_BIN_SIZE"

# Rebuild once and compare: two independent builds must agree byte for byte.
second=$stage/second
mkdir -p "$second"
(
	cd "$second"
	for source in logging qmi qrtr; do
		# shellcheck disable=SC2086
		$XCC -c -I"$stage/qrtr-1.2/include" "$stage/qrtr-1.2/lib/$source.c" -o "$source.o" 2>/dev/null
	done
	aarch64-linux-gnu-ar rcs libqrtr.a logging.o qmi.o qrtr.o
)
# shellcheck disable=SC2086
$XCC -I"$stage/qrtr-1.2/include" -I"$stage/pd-mapper-1.1" \
	"$stage/pd-mapper-1.1/pd-mapper.c" "$stage/pd-mapper-1.1/assoc.c" \
	"$stage/pd-mapper-1.1/json.c" "$stage/pd-mapper-1.1/servreg_loc.c" \
	"$stage/pd-mapper-1.1/lzma_decomp.c" "$second/libqrtr.a" \
	-o "$stage/pd-mapper.second" $LINK 2>/dev/null
# shellcheck disable=SC2086
$XCC -I"$stage/qrtr-1.2/include" \
	"$stage/tqftpserv-1.3/tqftpserv.c" "$stage/tqftpserv-1.3/translate.c" \
	"$second/libqrtr.a" -o "$stage/tqftpserv.second" $LINK 2>/dev/null
aarch64-linux-gnu-strip --strip-all -R .comment "$stage/pd-mapper.second" "$stage/tqftpserv.second"
cmp -s "$stage/pd-mapper.unstripped" "$stage/pd-mapper.second" || die "pd-mapper builds differ"
cmp -s "$stage/tqftpserv.unstripped" "$stage/tqftpserv.second" || die "tqftpserv builds differ"

qemu-aarch64 "$stage/tqftpserv.unstripped" -h 2>&1 | grep "Usage:" ||
	die 'tqftpserv does not run under qemu-aarch64'

cp "$stage/pd-mapper.unstripped" "$OUT/pd-mapper"
cp "$stage/tqftpserv.unstripped" "$OUT/tqftpserv"
chmod 755 "$OUT/pd-mapper" "$OUT/tqftpserv"
{
	echo "pd-mapper: qrtr $QRTR_COMMIT + pd-mapper $PDMAPPER_COMMIT, musl 1.2.5, static aarch64"
	sha256sum "$OUT/pd-mapper"
	echo "tqftpserv: qrtr $QRTR_COMMIT + tqftpserv $TQFTPSERV_COMMIT, musl 1.2.5, static aarch64"
	sha256sum "$OUT/tqftpserv"
} | tee "$OUT/i86-binaries-sha256.txt"
