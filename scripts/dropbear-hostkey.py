import base64
import hashlib
import pathlib
import subprocess

KEY_MSG = ("Dropbear host key is missing, unpinned, malformed, not an ed25519 key, "
           "or its private material is committed")

SSH_TYPE = b"ssh-ed25519"
HOST_KEY_PATH = "etc/dropbear/dropbear_ed25519_host_key"
HOST_KEY_DIR = "etc/dropbear"
HOST_KEY_MODE = 0o100600
HOST_KEY_DIR_MODE = 0o40700
KNOWN_HOSTS_NAME = "[172.16.42.2]:22"
PINNED_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA2ioqI4txcs3PSJWvcgSd/qBuDuCC50OIvIpKsjrjql"
SEED_LEN = 32
PUB_LEN = 32
DROPBEAR_CMD = (b"if /bin/dropbear -r /etc/dropbear/dropbear_ed25519_host_key "
                b"-p 172.16.42.2:22 >/dev/console 2>&1; then\n")
GENERATED_CMD = b"if /bin/dropbear -R -p 172.16.42.2:22 >/dev/console 2>&1; then\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _u32(value):
    return len(value).to_bytes(4, "big") + value


def parse_blob(blob):
    require(len(blob) == 4 + len(SSH_TYPE) + 4 + SEED_LEN + PUB_LEN and
            blob[:4] == (len(SSH_TYPE)).to_bytes(4, "big") and
            blob[4:4 + len(SSH_TYPE)] == SSH_TYPE and
            int.from_bytes(blob[4 + len(SSH_TYPE):8 + len(SSH_TYPE)], "big") ==
            SEED_LEN + PUB_LEN, KEY_MSG)
    seed = blob[8 + len(SSH_TYPE):8 + len(SSH_TYPE) + SEED_LEN]
    public = blob[8 + len(SSH_TYPE) + SEED_LEN:]
    require(len(seed) == SEED_LEN and len(public) == PUB_LEN, KEY_MSG)
    return seed, public


def ssh_wire(public):
    return _u32(SSH_TYPE) + _u32(public)


_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P


def _recover_x(y, sign):
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * pow(2, (_P - 1) // 4, _P) % _P
    if (x * x - x2) % _P or (x & 1) != sign:
        x = _P - x
    return x if (x & 1) == sign else None


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _recover_x(_BY, 0)
_B = (_BX, _BY, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    dd = 2 * z1 * z2 % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalarmult(point, scalar):
    result = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def derive_public(seed):
    require(len(seed) == SEED_LEN, KEY_MSG)
    digest = hashlib.sha512(seed).digest()
    scalar = bytearray(digest[:32])
    scalar[0] &= 248
    scalar[31] &= 127
    scalar[31] |= 64
    x, y, z, _ = _scalarmult(_B, int.from_bytes(scalar, "little"))
    inv = pow(z, _P - 2, _P)
    encoded = bytearray((y * inv % _P).to_bytes(32, "little"))
    if (x * inv % _P) & 1:
        encoded[31] |= 0x80
    return bytes(encoded)


def openssh_public_line(public):
    return f"{SSH_TYPE.decode()} {base64.b64encode(ssh_wire(public)).decode()}"


def known_hosts_line(public):
    return f"{KNOWN_HOSTS_NAME} {openssh_public_line(public)}"


def public_fingerprint(public):
    digest = hashlib.sha256(ssh_wire(public)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def directory_entry():
    return {"name": HOST_KEY_DIR,
            "fields": [0, HOST_KEY_DIR_MODE, 0, 0, 2, 0, 0, 0, 0, 0, 0,
                       len(HOST_KEY_DIR) + 1, 0],
            "mode": HOST_KEY_DIR_MODE, "data": b""}


def host_key_entry(blob):
    return {"name": HOST_KEY_PATH,
            "fields": [0, HOST_KEY_MODE, 0, 0, 1, 0, 0, 0, 0, 0, 0,
                       len(HOST_KEY_PATH) + 1, 0],
            "mode": HOST_KEY_MODE, "data": blob}


def committed_private_key(root, blob):
    seed, _public = parse_blob(blob)
    needles = (blob, seed, base64.b64encode(seed))
    files = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                           check=True, capture_output=True).stdout
    for name in files.split(b"\0"):
        if not name:
            continue
        path = root / pathlib.Path(name.decode())
        if not path.is_file():
            continue
        data = path.read_bytes()
        if any(needle in data for needle in needles):
            return True
    return False
