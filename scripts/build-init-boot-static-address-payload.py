import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).parent


def load(name, module):
    spec = importlib.util.spec_from_file_location(module, HERE / name)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


peripheral = load("build-init-boot-peripheral-mode-payload.py", "peripheral_builder")
eud = peripheral.eud
base = peripheral.base
modules = peripheral.modules
MEASURED_PERIPHERAL = "9f89fe8d614e213de1d197b78b2faf7f88ba190ba66cc41d5e3cd6c144d64af3"
PRIOR_IMAGES = (*peripheral.PRIOR_IMAGES, MEASURED_PERIPHERAL)
INIT_SOURCE = "init"
FROZEN_SOURCE = "init-51-peripheral-mode"
FROZEN_SHA256 = "995d9c84289502f77b8fb893e748524bcef84db07d1f2dd74cb403a017601263"
DISCARDED = (
    b"\t\tip link set usb0 up 2>/dev/null || true\n"
    b"\t\tip addr add 172.16.42.2/24 dev usb0 2>/dev/null || true\n"
    b"\t\tip link set usb1 up 2>/dev/null || true\n"
    b"\t\tip addr add 172.16.43.2/24 dev usb1 2>/dev/null || true\n")
ADDRESS_BLOCK = (
    b"\t\tif err=$(ip link set usb0 up 2>&1); then\n"
    b"\t\t\tlog 'usb0 link up: ok'\n"
    b"\t\telse\n"
    b'\t\t\tlog "usb0 link up failed: $err"\n'
    b"\t\tfi\n"
    b"\t\tif err=$(ip addr add 172.16.42.2/24 dev usb0 2>&1); then\n"
    b"\t\t\tlog 'usb0 address 172.16.42.2/24: added'\n"
    b"\t\telse\n"
    b'\t\t\tlog "usb0 address 172.16.42.2/24 failed: $err"\n'
    b"\t\tfi\n"
    b"\t\tif err=$(ip link set usb1 up 2>&1); then\n"
    b"\t\t\tlog 'usb1 link up: ok'\n"
    b"\t\telse\n"
    b'\t\t\tlog "usb1 link up failed: $err"\n'
    b"\t\tfi\n"
    b"\t\tif err=$(ip addr add 172.16.43.2/24 dev usb1 2>&1); then\n"
    b"\t\t\tlog 'usb1 address 172.16.43.2/24: added'\n"
    b"\t\telse\n"
    b'\t\t\tlog "usb1 address 172.16.43.2/24 failed: $err"\n'
    b"\t\tfi\n"
    b"\t\t{\n"
    b"\t\t\techo '== ip addr show dev usb0'\n"
    b"\t\t\tip addr show dev usb0 2>&1\n"
    b"\t\t\techo '== ip addr show dev usb1'\n"
    b"\t\t\tip addr show dev usb1 2>&1\n"
    b"\t\t\techo '== ip route'\n"
    b"\t\t\tip route 2>&1\n"
    b"\t\t} | {\n"
    b"\t\t\tan=0\n"
    b"\t\t\tat=0\n"
    b"\t\t\twhile IFS= read -r line; do\n"
    b"\t\t\t\tat=$((at + 1))\n"
    b'\t\t\t\tif [ "$an" -lt 32 ]; then\n'
    b'\t\t\t\t\tlog "net: $line"\n'
    b"\t\t\t\t\tan=$((an + 1))\n"
    b"\t\t\t\tfi\n"
    b"\t\t\tdone\n"
    b'\t\t\tlog "net lines logged: $an of $at (cap 32)"\n'
    b"\t\t}\n")
LISTENER_BLOCK = (
    b"if command -v ss >/dev/null 2>&1; then\n"
    b"\tLISTEN_TOOL='ss -ltn'\n"
    b"\tLISTEN_OUT=$(ss -ltn 2>&1)\n"
    b"elif LISTEN_OUT=$(/bin/busybox netstat -ltn 2>&1); then\n"
    b"\tLISTEN_TOOL='netstat -ltn'\n"
    b"else\n"
    b"\tLISTEN_TOOL='dropbear process and /proc/net/tcp'\n"
    b"\tLISTEN_OUT=$(\n"
    b"\t\t/bin/busybox ps 2>&1 | while IFS= read -r line; do\n"
    b'\t\t\tcase "$line" in\n'
    b'\t\t\t*dropbear*) echo "ps: $line" ;;\n'
    b"\t\t\tesac\n"
    b"\t\tdone\n"
    b"\t\twhile IFS= read -r line; do\n"
    b'\t\t\tcase "$line" in\n'
    b'\t\t\t*022A10AC:0016\\ 00000000:0000\\ 0A\\ *) echo "tcp: $line" ;;\n'
    b"\t\t\tesac\n"
    b"\t\tdone </proc/net/tcp\n"
    b"\t)\n"
    b"fi\n"
    b'log "listener check via $LISTEN_TOOL for 172.16.42.2:22"\n'
    b"printf '%s\\n' \"$LISTEN_OUT\" | {\n"
    b"\tln=0\n"
    b"\tlt=0\n"
    b"\tfound=0\n"
    b"\twhile IFS= read -r line; do\n"
    b"\t\tlt=$((lt + 1))\n"
    b'\t\tcase "$line" in\n'
    b"\t\t*172.16.42.2:22* | *022A10AC:0016*) found=1 ;;\n"
    b"\t\tesac\n"
    b'\t\tif [ "$ln" -lt 64 ]; then\n'
    b'\t\t\tlog "listen: $line"\n'
    b"\t\t\tln=$((ln + 1))\n"
    b"\t\tfi\n"
    b"\tdone\n"
    b'\tlog "listener lines logged: $ln of $lt (cap 64)"\n'
    b'\tif [ "$found" -eq 1 ]; then\n'
    b"\t\tlog 'listener 172.16.42.2:22: present'\n"
    b"\telse\n"
    b"\t\tlog 'listener 172.16.42.2:22: not found'\n"
    b"\tfi\n"
    b"}\n")
SSHD = b"if /bin/dropbear -R -p 172.16.42.2:22 >/dev/console 2>&1; then\n"
CONSOLE = b"log 'console ready'\n"
ADDRESS_MSG = "the two link and two address commands are missing or still discard their result"
ADDRESS_COUNT_MSG = "the address log is missing or duplicated"
NET_MSG = "read-only ip addr and ip route logging is missing, duplicated or not capped at 32 lines"
LISTENER_MSG = "the listener check is missing, duplicated, unbounded or not read-only"
SSHD_MSG = "the key-only sshd command changed"
DELTA_MSG = "init is not frozen #51 plus the exact address and listener logging"
FROZEN_MSG = "frozen #51 init is missing or already contains the address logging"
SOURCE_MSG = "embedded init differs from the committed address-logging source"
TIMER_MSG = peripheral.TIMER_MSG
LIST_MSG = peripheral.LIST_MSG
KO_MSG = peripheral.KO_MSG
ENVELOPE_MSG = peripheral.ENVELOPE_MSG
SHA_MSG = peripheral.SHA_MSG
require = peripheral.require


def require_frozen(frozen):
    require(frozen.startswith(eud.SHEBANG) and frozen.count(DISCARDED) == 1 and
            frozen.count(ADDRESS_BLOCK) == 0 and frozen.count(LISTENER_BLOCK) == 0 and
            frozen.count(SSHD) == 1 and
            frozen.count(CONSOLE) == 1 and frozen.count(peripheral.ROLE_WRITE) == 1 and
            frozen.count(eud.TIMER) == 1, FROZEN_MSG)
    require(modules.sha256(frozen) == FROZEN_SHA256, FROZEN_MSG)
    return frozen


def frozen_init():
    return require_frozen((HERE.parent / "initramfs" / FROZEN_SOURCE).read_bytes())


def expected_init(frozen):
    require(frozen.count(DISCARDED) == 1 and frozen.count(CONSOLE) == 1, DELTA_MSG)
    result = frozen.replace(DISCARDED, ADDRESS_BLOCK, 1)
    return result.replace(CONSOLE, LISTENER_BLOCK + CONSOLE, 1)


def check_address(init):
    discards = (b"ip link set usb0 up 2>/dev/null", b"ip addr add 172.16.42.2/24 dev usb0 2>/dev/null",
                b"ip link set usb1 up 2>/dev/null", b"ip addr add 172.16.43.2/24 dev usb1 2>/dev/null")
    require(init.count(DISCARDED) == 0 and not any(item in init for item in discards) and
            b"|| true" not in init[init.index(b'log "gadget bound to $UDC"\n'):], ADDRESS_MSG)
    commands = (b"ip link set usb0 up 2>&1", b"ip addr add 172.16.42.2/24 dev usb0 2>&1",
                b"ip link set usb1 up 2>&1", b"ip addr add 172.16.43.2/24 dev usb1 2>&1")
    require(all(init.count(command) == 1 for command in commands), ADDRESS_COUNT_MSG)
    require(init.count(b"\t\t\tip addr show dev usb0 2>&1") == 1 and
            init.count(b"\t\t\tip addr show dev usb1 2>&1") == 1 and
            init.count(b"\t\t\tip route 2>&1") == 1 and
            init.count(b'if [ "$an" -lt 32 ]; then') == 1 and
            init.count(b'log "net: $line"') == 1, NET_MSG)
    require(init.count(ADDRESS_BLOCK) == 1, ADDRESS_COUNT_MSG)
    bound = init.index(b'log "gadget bound to $UDC"\n')
    block = init.index(ADDRESS_BLOCK)
    failed = init.index(b'log "gadget bind failed for $UDC: $err"\n')
    require(bound < block and block + len(ADDRESS_BLOCK) < failed and
            init[block + len(ADDRESS_BLOCK):failed] == b"\telse\n\t\t", ADDRESS_MSG)
    return block


def check_listener(init):
    require(init.count(LISTENER_BLOCK) == 1, LISTENER_MSG)
    sshd = init.index(SSHD)
    block = init.index(LISTENER_BLOCK)
    require(sshd < init.index(b"sshd listening at 172.16.42.2:22") < block <
            init.index(CONSOLE), LISTENER_MSG)
    require(init.count(b"ss -ltn") == 2 and init.count(b"netstat -ltn") == 2 and
            init.count(b"/proc/net/tcp") == 2 and init.count(b'if [ "$ln" -lt 64 ]; then') == 1 and
            init.count(b'log "listen: $line"') == 1, LISTENER_MSG)
    require(init.count(b"022A10AC:0016") == 2 and b"172.16.42.2:22" in init, LISTENER_MSG)
    require(b"ss -ltnp" not in init and b"netstat -ltnp" not in init, LISTENER_MSG)
    return block


def check_sshd(init):
    require(init.count(SSHD) == 1 and init.count(b"/bin/dropbear -R -p") == 1 and
            init.count(b"-R -p 172.16.42.2:22") == 1, SSHD_MSG)


def check_timer(init):
    require(init.count(eud.TIMER) == 1 and
            init.index(eud.TIMER) < init.index(eud.LOAD_BEGIN), TIMER_MSG)
    eud.check_timer(init)


def check_init(init, order):
    require(init.startswith(eud.SHEBANG), DELTA_MSG)
    peripheral.check_list(init, order)
    check_timer(init)
    eud.check_marker(init)
    peripheral.check_eud_log(init)
    eud.check_bind(init)
    peripheral.check_mode(init)
    peripheral.check_wait(init, init.index(peripheral.ROLE_WRITE))
    peripheral.check_logs(init)
    check_address(init)
    check_listener(init)
    check_sshd(init)
    frozen = frozen_init()
    peripheral.check_init(frozen, order)
    require(init == expected_init(frozen), DELTA_MSG)
    return init.index(ADDRESS_BLOCK)


def candidate_cpio(source, init, helper, vendor_files, recovery_entries, order):
    return eud.candidate_cpio(source, init, helper, vendor_files, recovery_entries, order,
                              init_check=check_init)


def assemble(stock, frame):
    require(len(frame) <= base.MAX_FRAME, ENVELOPE_MSG)
    image, digest = peripheral.assemble(stock, frame)
    require(digest not in PRIOR_IMAGES and digest != MEASURED_PERIPHERAL, SHA_MSG)
    return image, digest


def prepare(paths):
    require(len(paths) == 10, "expected STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY "
            "CONFIG KERNEL_SOURCE DECOMPRESSOR_SOURCE PSTORE HELPER")
    stock, source, boot, vendor_boot, recovery, config, kernel, decompressor, pstore, helper = (
        pathlib.Path(path).read_bytes() for path in paths)
    library = base.lz4()
    vendor_files, recovery_entries = eud.vendor.verify_host_path(
        boot, vendor_boot, stock, recovery, config, kernel, decompressor, pstore, library)
    order, outside = modules.compute_eud_order(vendor_files)
    require(len(order) == 127, LIST_MSG)
    eud.vendor.check_stock(stock, library)
    init = (HERE.parent / "initramfs" / INIT_SOURCE).read_bytes()
    cpio = candidate_cpio(source, init, helper, vendor_files, recovery_entries, order)
    return stock, cpio, eud.vendor.encode_frame(cpio, library), order, outside


def main():
    args = sys.argv[1:]
    require(len(args) == 12 and args[0] in ("--preflight", "--build"),
            "usage: build-init-boot-static-address-payload.py --preflight|--build "
            "STOCK_INIT GZIP STOCK_BOOT STOCK_VENDOR RECOVERY CONFIG KERNEL_SOURCE "
            "DECOMPRESSOR_SOURCE PSTORE HELPER OUTPUT")
    stock, cpio, frame, order, outside = prepare(args[1:-1])
    image, digest = assemble(stock, frame)
    print(f"vendor module closure: {len(order)} modules; unchanged order; list SHA-256 "
          f"{modules.EUD_ORDER_SHA256[:8]}")
    print(f"debug cpio: {len(cpio)} bytes, zero .ko, SHA-256 {modules.sha256(cpio)}")
    print(f"LZ4 HC-{base.HC_LEVEL} frame: {len(frame)} bytes, block {len(frame) - 8} bytes")
    print("address log: two link and two address commands keep their result; ip addr and "
          "ip route capped at 32 lines; listener check capped at 64 lines")
    print(f"self-recovery timer: {eud.TIMER_BUDGET} s, unchanged; helper {eud.HELPER_SIZE} "
          f"bytes, SHA-256 {eud.HELPER_SHA256[:8]}")
    print(f"stock signed tail: {base.IMAGE_SIZE - base.TAIL_OFFSET} bytes, unchanged")
    print(f"candidate: {base.IMAGE_SIZE} bytes, SHA-256 {digest}")
    if args[0] == "--build":
        pathlib.Path(args[-1]).write_bytes(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
