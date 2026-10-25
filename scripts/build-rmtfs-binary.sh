#!/usr/bin/env bash
set -euo pipefail
WORK=${WORK:-$HOME/sm7635-build}
OUT=$WORK/out
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SOURCES=${SOURCES:-$WORK/i96-sources}
RMTFS_TARBALL=${RMTFS_TARBALL:-$SOURCES/rmtfs-v1.3.tar.gz}
QRTR_TARBALL=${QRTR_TARBALL:-$WORK/i86-sources/qrtr-v1.2.tar.gz}
MUSL_TARBALL=${MUSL_TARBALL:-$WORK/i86-sources/musl-1.2.5.tar.gz}
RMTFS_SOURCE_SHA=4b6c398806a1046e2256a685d592833de0f37b7245b8adc4797e1791f0e117ee
QRTR_SOURCE_SHA=7a82bf80246fe71287b13c66c0466208822e8337fcd4aaf302eee6c5fcb48a52
MUSL_SOURCE_SHA=a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4
RMTFS_BINARY_SHA=d66204e7895a6fd4cf78af369a45cee5bf1c88fa3f8cdad27e24690f233251bd
RMTFS_BINARY_SIZE=134088

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
for tool in curl tar make sha256sum aarch64-linux-gnu-gcc aarch64-linux-gnu-ar \
	aarch64-linux-gnu-strip qemu-aarch64 python3 file flock; do
	command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
done
[ "$#" -eq 0 ] || die 'usage: build-rmtfs-binary.sh (no arguments)'
case "$(realpath -m "$OUT")/" in "$ROOT"/*) die 'artifacts must stay outside this repository' ;; esac
[ -d "$OUT" ] || die "missing output directory: $OUT"
mkdir -p "$SOURCES"
if [ ! -f "$RMTFS_TARBALL" ]; then
	curl -fL --retry 3 --retry-delay 2 -o "$RMTFS_TARBALL" \
		'https://github.com/andersson/rmtfs/archive/refs/tags/v1.3.tar.gz' || die 'rmtfs fetch failed'
fi
for item in "$RMTFS_TARBALL:$RMTFS_SOURCE_SHA" "$QRTR_TARBALL:$QRTR_SOURCE_SHA" \
	"$MUSL_TARBALL:$MUSL_SOURCE_SHA"; do
	path=${item%:*}
	[ -f "$path" ] || die "missing source: $path"
	[ "$(sha256sum "$path" | cut -d ' ' -f 1)" = "${item##*:}" ] || die "source hash mismatch: $path"
done
exec 9>"$WORK/i96-binaries.lock"
flock 9 || die 'another #96 build is running'
stage=$WORK/i96-stage
rm -rf -- "$stage"
mkdir -p "$stage"
trap 'rm -rf -- "$stage"' EXIT
tar xf "$RMTFS_TARBALL" -C "$stage"
tar xf "$QRTR_TARBALL" -C "$stage"
tar xf "$MUSL_TARBALL" -C "$stage"
prefix=$stage/prefix
(
	cd "$stage/musl-1.2.5"
	CC=aarch64-linux-gnu-gcc ./configure --prefix="$prefix" --target=aarch64-linux-musl >"$stage/musl-configure.log" 2>&1
	python3 - "$stage/musl-1.2.5/config.mak" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
import re
s = re.sub(r'^AR = .*$', 'AR = aarch64-linux-gnu-ar', s, flags=re.MULTILINE)
s = re.sub(r'^RANLIB = .*$', 'RANLIB = aarch64-linux-gnu-ranlib', s, flags=re.MULTILINE)
p.write_text(s)
PY
	make -j"${JOBS:-2}" >"$stage/musl-make.log" 2>&1 || { tail -10 "$stage/musl-make.log" >&2; exit 1; }
	make install >"$stage/musl-install.log" 2>&1
)
python3 - "$stage/rmtfs-1.3/sharedmem.c" "$stage/rmtfs-1.3/rmtfs.c" "$stage/rmtfs-1.3/storage.c" <<'PY'
import pathlib, sys
mem, service, storage = map(pathlib.Path, sys.argv[1:])
s = mem.read_text()
start = s.index('#ifndef ANDROID\n#include <libudev.h>')
end = s.index('#include <stdbool.h>', start)
s = s[:start] + '#include <endian.h>\n' + s[end:]
start = s.index('#ifndef ANDROID\n\nstatic int parse_hex_sysattr')
end = s.index('struct rmtfs_mem *rmtfs_mem_open(void)', start)
patch = '''static int rmtfs_mem_open_rfsa(struct rmtfs_mem *rmem, int client_id)
{
	return -ENOENT;
}

static int read_uio_sysfs(const char *path, uint64_t *value)
{
	char buf[64];
	char *end;
	ssize_t count;
	int fd = open(path, O_RDONLY);

	if (fd < 0)
		return -1;
	count = read(fd, buf, sizeof(buf) - 1);
	close(fd);
	if (count <= 0)
		return -1;
	buf[count] = 0;
	errno = 0;
	*value = strtoull(buf, &end, 16);
	return end != buf && errno == 0 && (*end == '\\n' || *end == 0) ? 0 : -1;
}

static int rmtfs_mem_open_uio(struct rmtfs_mem *rmem, int client_id)
{
	DIR *dir = opendir("/sys/class/uio");
	struct dirent *entry;
	char path[PATH_MAX];
	char name[32];
	ssize_t count;
	int fd;

	if (!dir) {
		fprintf(stderr, "rmtfs: stock rmtfs UIO missing or unusable\\n");
		return -ENODEV;
	}
	while ((entry = readdir(dir))) {
		if (strncmp(entry->d_name, "uio", 3))
			continue;
		snprintf(path, sizeof(path), "/sys/class/uio/%s/name", entry->d_name);
		fd = open(path, O_RDONLY);
		if (fd < 0)
			continue;
		count = read(fd, name, sizeof(name) - 1);
		close(fd);
		if (count <= 0)
			continue;
		name[count] = 0;
		if (strcmp(name, "rmtfs\\n") && strcmp(name, "rmtfs"))
			continue;
		snprintf(path, sizeof(path), "/sys/class/uio/%s/maps/map0/addr", entry->d_name);
		if (read_uio_sysfs(path, &rmem->address))
			break;
		snprintf(path, sizeof(path), "/sys/class/uio/%s/maps/map0/size", entry->d_name);
		if (read_uio_sysfs(path, &rmem->size) || rmem->size == 0)
			break;
		snprintf(path, sizeof(path), "/dev/%s", entry->d_name);
		fd = open(path, O_RDWR);
		if (fd < 0)
			break;
		rmem->base = mmap(NULL, rmem->size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
		if (rmem->base == MAP_FAILED) {
			rmem->base = NULL;
			close(fd);
			break;
		}
		rmem->fd = fd;
		fprintf(stderr, "rmtfs: mapped stock UIO %s address 0x%llx size 0x%llx\\n",
			path, (unsigned long long)rmem->address, (unsigned long long)rmem->size);
		closedir(dir);
		return 0;
	}
	closedir(dir);
	fprintf(stderr, "rmtfs: stock rmtfs UIO missing or unusable\\n");
	return -ENODEV;
}

'''
s = s[:start] + patch + s[end:]
old = '''		} else if (ret < 0) {
			fprintf(stderr, "falling back to /dev/mem access\\n");'''
if s.count(old) != 1:
    raise SystemExit('rmtfs /dev/mem fallback anchor missing')
start = s.index(old)
end = s.index('\n\t\t}', start)
s = s[:start] + '''		} else if (ret < 0) {
			goto err;''' + s[end:]
mem.write_text(s)
s = service.read_text()
old = '''	if (ret < 0) {
		fprintf(stderr, "failed to publish rmtfs service");
		return ret;
	}'''
if s.count(old) != 1:
    raise SystemExit('rmtfs publish anchor missing')
s = s.replace(old, old + '''
	fprintf(stderr, "rmtfs: published QRTR service 14 version 1 instance 0\\n");
	fflush(stderr);''', 1)
old = '\treturn 0;\n}'
if not s.endswith(old + '\n'):
    raise SystemExit('rmtfs exit anchor missing')
s = s[:-len(old + '\n')] + '\treturn ret < 0 ? 1 : 0;\n}\n'
service.write_text(s)
s = storage.read_text()
old = '''\t{ "/boot/modem_fsc", "modem_fsc", "fsc" },
\t{ "/boot/modem_fsg", "modem_fsg", "fsg" },'''
if s.count(old) != 1:
    raise SystemExit('rmtfs fsc/fsg table anchor missing')
s = s.replace(old, '', 1)
start = s.index('\t{ "/boot/modem_study"')
end = s.index('\t{}', start)
s = s[:start] + s[end:]
old = '''\tif (use_partitions) {
\t\tif (!storage_root)
\t\t\tstorage_dir = BY_PARTLABEL_PATH;
\t\tstorage_use_partitions = true;
\t}'''
if s.count(old) != 1:
    raise SystemExit('rmtfs storage init anchor missing')
s = s.replace(old, old + '''

\tfprintf(stderr, "rmtfs: exposing /boot/modem_fs1 -> modemst1 and /boot/modem_fs2 -> modemst2 under %s\\n", storage_dir);''', 1)
storage.write_text(s)
PY
XCC="aarch64-linux-gnu-gcc -nostdinc -isystem $prefix/include -isystem /usr/aarch64-linux-gnu/include -isystem $prefix/include -isystem /usr/lib/gcc-cross/aarch64-linux-gnu/15/include -fno-stack-protector -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -Os -Wall"
MLIB=$prefix/lib
LINK="-nostdlib -static -Wl,--gc-sections $MLIB/crt1.o $MLIB/crti.o -L$prefix/lib -L/usr/lib/gcc-cross/aarch64-linux-gnu/15 -lgcc $MLIB/libc.a -lgcc $MLIB/crtn.o"
build_one() {
	local dest=$1
	mkdir -p "$dest"
	for source in logging qmi qrtr; do
		$XCC -c -I"$stage/qrtr-1.2/include" "$stage/qrtr-1.2/lib/$source.c" -o "$dest/$source.o"
	done
	aarch64-linux-gnu-ar rcs "$dest/libqrtr.a" "$dest/logging.o" "$dest/qmi.o" "$dest/qrtr.o"
	$XCC -I"$stage/qrtr-1.2/include" -I"$stage/rmtfs-1.3" \
		"$stage/rmtfs-1.3/rmtfs.c" "$stage/rmtfs-1.3/sharedmem.c" \
		"$stage/rmtfs-1.3/storage.c" "$stage/rmtfs-1.3/qmi_rmtfs.c" \
		"$stage/rmtfs-1.3/qmi_tlv.c" "$stage/rmtfs-1.3/rproc.c" \
		"$stage/rmtfs-1.3/util.c" "$dest/libqrtr.a" \
		-o "$dest/rmtfs" $LINK 2>"$dest/rmtfs-build.log" || { tail -15 "$dest/rmtfs-build.log" >&2; return 1; }
	aarch64-linux-gnu-strip --strip-all -R .comment "$dest/rmtfs"
}
build_one "$stage/first"
build_one "$stage/second"
cmp -s "$stage/first/rmtfs" "$stage/second/rmtfs" || die 'two rmtfs builds differ'
file "$stage/first/rmtfs" | grep -q 'ARM aarch64' || die 'rmtfs is not aarch64'
file "$stage/first/rmtfs" | grep -q 'statically linked' || die 'rmtfs is not static'
qemu-aarch64 "$stage/first/rmtfs" -r -P -o /nonexistent 2>"$stage/qemu.log" && die 'rmtfs ran without stock UIO'
grep -q 'stock rmtfs UIO missing or unusable' "$stage/qemu.log" || die 'rmtfs did not fail closed without UIO'
if [ "$RMTFS_BINARY_SHA" != PLACEHOLDER ]; then
	[ "$(sha256sum "$stage/first/rmtfs" | cut -d ' ' -f 1)" = "$RMTFS_BINARY_SHA" ] || die 'rmtfs hash differs'
	[ "$(stat -c '%s' "$stage/first/rmtfs")" = "$RMTFS_BINARY_SIZE" ] || die 'rmtfs size differs'
fi
cp "$stage/first/rmtfs" "$OUT/rmtfs"
chmod 755 "$OUT/rmtfs"
sha256sum "$OUT/rmtfs" | tee "$OUT/i96-rmtfs-sha256.txt"
