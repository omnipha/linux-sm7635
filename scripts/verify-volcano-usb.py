import argparse
import gzip
import pathlib
import struct
import subprocess
import sys

CONTROLLER = "/soc/ssusb@a600000"
CHILD = CONTROLLER + "/dwc3@a600000"
DRIVERS = {
    "qcom,dwc-usb3-msm": "CONFIG_USB_DWC3_MSM",
    "snps,dwc3": "CONFIG_USB_DWC3",
    "qcom,usb-snps-eusb2-phy": "CONFIG_USB_MSM_EUSB2_PHY",
    "qcom,usb-ssphy-qmp-dp-combo": "CONFIG_USB_MSM_SSPHY_QMP",
    "qcom,pmic-eusb2-repeater": "CONFIG_QTI_PMIC_EUSB2_REPEATER",
    "qcom,msm-eud": "CONFIG_QCOM_EUD",
    "qcom,volcano-gcc": "CONFIG_SM_GCC_VOLCANO",
    "qcom,volcano-rpmh-clk": "CONFIG_QCOM_CLK_RPMH",
    "qcom,gdsc": "CONFIG_QCOM_GDSC_REGULATOR",
    "qcom,rpmh-vrm-regulator": "CONFIG_REGULATOR_RPMH",
    "qcom,rpmh-arc-regulator": "CONFIG_REGULATOR_RPMH",
    "qcom,rpmh-rsc": "CONFIG_QCOM_RPMH",
    "qcom,volcano-pinctrl": "CONFIG_PINCTRL_VOLCANO",
    "qcom,volcano-aggre1_noc": "CONFIG_INTERCONNECT_QCOM_VOLCANO",
    "qcom,volcano-mc_virt": "CONFIG_INTERCONNECT_QCOM_VOLCANO",
    "qcom,volcano-cnoc_cfg": "CONFIG_INTERCONNECT_QCOM_VOLCANO",
    "qcom,volcano-gem_noc": "CONFIG_INTERCONNECT_QCOM_VOLCANO",
    "qcom,bcm-voter": "CONFIG_INTERCONNECT_QCOM_BCM_VOTER",
    "qcom,qsmmu-v500": "CONFIG_ARM_SMMU",
    "qcom,spmi-pmic-arb": "CONFIG_SPMI_MSM_PMIC_ARB",
    "qcom,spmi-pmic": "CONFIG_MFD_SPMI_PMIC",
}
BUILTINS = (
    "CONFIG_USB_DWC3_MSM", "CONFIG_USB_DWC3", "CONFIG_USB_MSM_EUSB2_PHY",
    "CONFIG_USB_MSM_SSPHY_QMP", "CONFIG_USB_REPEATER",
    "CONFIG_QTI_PMIC_EUSB2_REPEATER", "CONFIG_QCOM_EUD",
    "CONFIG_USB_REDRIVER", "CONFIG_QCOM_WCD_USBSS_I2C", "CONFIG_IPC_LOGGING",
    "CONFIG_COMMON_CLK_QCOM", "CONFIG_SM_GCC_VOLCANO", "CONFIG_QCOM_CLK_RPMH",
    "CONFIG_QCOM_GDSC_REGULATOR", "CONFIG_QCOM_COMMAND_DB", "CONFIG_QCOM_RPMH",
    "CONFIG_REGULATOR_RPMH", "CONFIG_INTERCONNECT_QCOM_VOLCANO",
    "CONFIG_INTERCONNECT_QCOM_BCM_VOTER", "CONFIG_INTERCONNECT_QCOM_RPMH",
    "CONFIG_INTERCONNECT_QCOM_QOS", "CONFIG_INTERCONNECT_QCOM_DEBUG",
    "CONFIG_SPMI_MSM_PMIC_ARB", "CONFIG_MFD_SPMI_PMIC",
    "CONFIG_PINCTRL_VOLCANO", "CONFIG_PINCTRL_MSM", "CONFIG_QCOM_PDC",
    "CONFIG_ARM_SMMU", "CONFIG_ARM_SMMU_QCOM", "CONFIG_QCOM_IOMMU_UTIL",
    "CONFIG_QTI_IOMMU_SUPPORT", "CONFIG_QCOM_SCM", "CONFIG_QTI_PMIC_GLINK",
    "CONFIG_UCSI_QTI_GLINK", "CONFIG_QCOM_SOCINFO", "CONFIG_QCOM_CRM",
    "CONFIG_QCOM_AOSS_QMP", "CONFIG_QCOM_SMEM",
    "CONFIG_RPMSG_QCOM_GLINK_SMEM", "CONFIG_RPMSG_QCOM_GLINK",
    "CONFIG_RPMSG_QCOM_SMD", "CONFIG_GH_RM_DRV", "CONFIG_REGMAP_QTI_DEBUGFS",
    "CONFIG_REGULATOR_PROXY_CONSUMER", "CONFIG_REGULATOR_DEBUG_CONTROL",
    "CONFIG_QCOM_MINIDUMP", "CONFIG_HWSPINLOCK_QCOM",
    "CONFIG_NOTHING_ERROR_REPORT", "CONFIG_GH_ARM64_DRV", "CONFIG_GH_MSGQ",
    "CONFIG_GH_DBL", "CONFIG_QCOM_DEBUG_SYMBOL", "CONFIG_QCOM_DMABUF_HEAPS",
    "CONFIG_QCOM_MEM_BUF", "CONFIG_QCOM_MEM_BUF_DEV",
    "CONFIG_QCOM_SECURE_BUFFER", "CONFIG_QCOM_GLINK",
    "CONFIG_RPMSG_QCOM_GLINK_SPSS", "CONFIG_QCOM_LAZY_MAPPING",
    "CONFIG_QCOM_MEM_BUF_MSGQ",
)
SELECTED = (
    "CONFIG_USB_DWC3", "CONFIG_INTERCONNECT_QCOM_BCM_VOTER",
    "CONFIG_INTERCONNECT_QCOM_RPMH", "CONFIG_INTERCONNECT_QCOM_QOS",
    "CONFIG_PINCTRL_MSM", "CONFIG_RPMSG_QCOM_GLINK",
)
SUPPLIERS = {
    CONTROLLER: {
        "clocks": ("qcom,volcano-gcc",) * 5,
        "resets": ("qcom,volcano-gcc",),
        "USB3_GDSC-supply": ("qcom,gdsc",),
        "extcon": ("qcom,msm-eud",),
        "dummy-supply": ("qcom,qsmmu-v500",),
        "interconnects": ("qcom,volcano-aggre1_noc", "qcom,volcano-mc_virt",
                          "qcom,volcano-aggre1_noc", "qcom,volcano-cnoc_cfg",
                          "qcom,volcano-gem_noc", "qcom,volcano-cnoc_cfg"),
    },
    CHILD: {
        "usb-phy": ("qcom,usb-snps-eusb2-phy", "qcom,usb-ssphy-qmp-dp-combo"),
        "iommus": ("qcom,qsmmu-v500",),
    },
    "/soc/hsphy@88e3000": {
        "usb-repeater": ("qcom,pmic-eusb2-repeater",),
        "dummy-supply": ("qcom,pmic-eusb2-repeater",),
        "vdd-supply": ("qcom,rpmh-vrm-regulator",),
        "vdda12-supply": ("qcom,rpmh-vrm-regulator",),
        "clocks": ("qcom,volcano-rpmh-clk",),
        "resets": ("qcom,volcano-gcc",),
    },
    "/soc/ssphy@88e8000": {
        "vdd-supply": ("qcom,rpmh-vrm-regulator",),
        "core-supply": ("qcom,rpmh-vrm-regulator",),
        "usb3_dp_phy_gdsc-supply": ("qcom,gdsc",),
        "clocks": ("qcom,volcano-gcc",) * 3 + ("fixed-clock", "qcom,volcano-rpmh-clk",
                                                   "qcom,volcano-gcc"),
        "resets": ("qcom,volcano-gcc",) * 2,
        "pinctrl-0": ("qcom,volcano-pinctrl",),
    },
}
EXTRA_SUPPLIES = {
    "qcom,pmic-eusb2-repeater": ("vdd18-supply", "vdd3-supply"),
    "qcom,gdsc": ("parent-supply",),
    "qcom,volcano-gcc": ("vdd_cx-supply", "vdd_mx-supply"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def config_values(data):
    values = {}
    for line in data.decode().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            require(key not in values, f"duplicate setting: {key}")
            values[key] = value
    return values


def check_config(config, fragment, modules=()):
    values = config_values(config)
    requests = config_values(fragment)
    require(set(requests) == set(BUILTINS) - set(SELECTED),
            "built-in fragment changed outside the reviewed closure")
    require(all(value == "y" for value in requests.values()),
            "built-in fragment contains a non-additive setting")
    for name in BUILTINS:
        require(values.get(name) == "y",
                f"{name}={values.get(name, 'unset')} has no verified built-in driver; "
                f"initramfs modules/load path not verified ({len(modules)} .ko)")
    return values


def unpack_cpio(archive):
    data = gzip.decompress(archive)
    files = {}
    pos = 0
    while pos < len(data):
        require(data[pos:pos + 6] == b"070701" and pos + 110 <= len(data),
                "invalid initramfs cpio header")
        fields = [int(data[pos + 6 + index * 8:pos + 14 + index * 8], 16)
                  for index in range(13)]
        size, name_size = fields[6], fields[11]
        pos += 110
        name = data[pos:pos + name_size - 1].decode()
        pos = (pos + name_size + 3) & ~3
        if name == "TRAILER!!!":
            break
        files[name] = data[pos:pos + size]
        pos = (pos + size + 3) & ~3
    return files


def check_modules(archive, symbols):
    files = unpack_cpio(archive)
    modules = {}
    for name, body in files.items():
        if not name.endswith(".ko"):
            continue
        require(len(body) >= 64 and body[:6] == b"\x7fELF\x02\x01" and
                struct.unpack_from("<H", body, 18)[0] == 183,
                f"initramfs module is not ARM aarch64 ELF: {name}")
        modules[pathlib.Path(name).name] = body
    if not symbols:
        return modules
    init = files.get("init", b"").decode(errors="ignore")
    require(bool(modules),
            f"{','.join(symbols)}=m has no built-in driver and initramfs has 0 .ko files")
    require("insmod " in init or "modprobe " in init,
            "initramfs/init has no module load path")
    raise ValueError("module symbol dependencies and explicit load order are unverified")


def fdt(dtb, node, prop):
    result = subprocess.run(["fdtget", "-t", "s", str(dtb), node, prop],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, f"DT property missing: {node} {prop}")
    return result.stdout.strip().split()


def read_cells(dtb, node, prop):
    result = subprocess.run(["fdtget", "-t", "x", str(dtb), node, prop],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        return None
    return [int(value, 16) for value in result.stdout.split()]


def compat(dtb, node):
    return tuple(fdt(dtb, node, "compatible"))


def nodes(dtb):
    result = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", str(dtb)],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0, "merged board DTB cannot be decoded")
    stack = []
    found = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.endswith(" {"):
            name = stripped[:-2].strip()
            stack.append(name)
            found.append("/" + "/".join(part for part in stack if part != "/"))
        elif stripped == "};":
            require(bool(stack), "unbalanced DT nodes")
            stack.pop()
    require(not stack, "unbalanced DT nodes")
    return found


def check_board(dtb, config):
    all_nodes = nodes(dtb)
    by_handle = {}
    for node in all_nodes:
        phandle = read_cells(dtb, node, "phandle")
        if phandle is not None:
            require(len(phandle) == 1 and phandle[0] not in by_handle,
                    f"invalid phandle: {node}")
            by_handle[phandle[0]] = node

    def matched(node, expected):
        ancestor = node
        while ancestor != "/":
            try:
                names = compat(dtb, ancestor)
            except ValueError:
                names = ()
            if expected in names:
                symbol = DRIVERS.get(expected)
                if symbol:
                    require(config.get(symbol) == "y", f"{ancestor}: {symbol} is not built in")
                return ancestor
            ancestor = ancestor.rsplit("/", 1)[0] or "/"
        raise ValueError(f"DT supplier {node}: expected {expected}")

    def suppliers(node, prop, expected):
        values = read_cells(dtb, node, prop)
        require(values is not None, f"DT supplier missing: {node} {prop}")
        pos = 0
        paths = []
        for name in expected:
            require(pos < len(values) and values[pos] in by_handle,
                    f"DT supplier unresolved: {node} {prop} index {len(paths)}")
            provider = by_handle[values[pos]]
            path = matched(provider, name)
            paths.append(path)
            pos += 1
            size = {"clocks": "#clock-cells", "resets": "#reset-cells",
                    "interconnects": "#interconnect-cells", "iommus": "#iommu-cells"}.get(prop)
            if size:
                count = read_cells(dtb, provider, size)
                require(count is not None and len(count) == 1 and count[0] <= 4,
                        f"invalid specifier size: {provider} {size}")
                pos += count[0]
        require(pos == len(values), f"DT supplier count/specifier mismatch: {node} {prop}")
        return paths

    matched(CONTROLLER, "qcom,dwc-usb3-msm")
    matched(CHILD, "snps,dwc3")
    require(read_cells(dtb, CONTROLLER, "power-domains") is None and
            read_cells(dtb, CHILD, "power-domains") is None,
            "unexpected USB power-domains dependency")
    require(read_cells(dtb, CONTROLLER, "usb-role-switch") == [] and
            read_cells(dtb, CHILD, "usb-role-switch") == [],
            "USB role switch missing")
    require(fdt(dtb, CHILD, "dr_mode") == ["otg"], "DWC3 is not OTG")
    seen = set()
    for node, props in SUPPLIERS.items():
        for prop, expected in props.items():
            for path in suppliers(node, prop, expected):
                seen.add(path)
    repeater = suppliers("/soc/hsphy@88e3000", "usb-repeater",
                         ("qcom,pmic-eusb2-repeater",))[0]
    matched(repeater.rsplit("/", 1)[0], "qcom,spmi-pmic")
    matched(repeater.rsplit("/", 2)[0], "qcom,spmi-pmic-arb")
    for prop in EXTRA_SUPPLIES["qcom,pmic-eusb2-repeater"]:
        seen.update(suppliers(repeater, prop, ("qcom,rpmh-vrm-regulator",)))
    for path in tuple(seen):
        names = compat(dtb, path)
        if "qcom,gdsc" in names or "qcom,volcano-gcc" in names:
            for prop in EXTRA_SUPPLIES[names[0]]:
                expected = "qcom,rpmh-arc-regulator" if prop in (
                    "vdd_cx-supply", "vdd_mx-supply", "parent-supply") else "qcom,rpmh-vrm-regulator"
                seen.update(suppliers(path, prop, (expected,)))
    for path in seen:
        if "qcom,rpmh-" in " ".join(compat(dtb, path)):
            matched(path, "qcom,rpmh-rsc")
    print(f"Volcano DTB: {CONTROLLER} -> {CHILD}; {len(seen)} resolved suppliers; built-in closure OK")


def self_test():
    fragment = b"\n".join((name + "=y").encode() for name in BUILTINS
                          if name not in SELECTED) + b"\n"
    config = b"\n".join((name + "=y").encode() for name in BUILTINS) + b"\n"
    check_config(config, fragment)
    print("synthetic built-in closure: OK")
    for label, bad, expected in (
        ("module glue without .ko", config.replace(b"CONFIG_USB_DWC3_MSM=y",
                                                       b"CONFIG_USB_DWC3_MSM=m"),
         "CONFIG_USB_DWC3_MSM=m has no verified built-in driver"),
        ("module PHY without .ko", config.replace(b"CONFIG_USB_MSM_EUSB2_PHY=y",
                                                      b"CONFIG_USB_MSM_EUSB2_PHY=m"),
         "CONFIG_USB_MSM_EUSB2_PHY=m has no verified built-in driver"),
    ):
        try:
            check_config(bad, fragment, ())
        except ValueError as exc:
            require(str(exc).startswith(expected), f"{label}: unexpected failure: {exc}")
            print(f"expected {label} failure: {exc}")
        else:
            raise ValueError(f"{label}: invalid fixture accepted")
    def entry(name, content, inode):
        name = name.encode() + b"\0"
        fields = (inode, 0o100755, 0, 0, 1, 0, len(content), 0, 0, 0, 0,
                  len(name), 0)
        body = b"070701" + b"".join(f"{value:08x}".encode() for value in fields) + name
        body += bytes(-len(body) % 4) + content
        return body + bytes(-len(body) % 4)

    archive = gzip.compress(entry("init", b"#!/bin/sh\n", 1) +
                            entry("TRAILER!!!", b"", 2), mtime=0)
    try:
        check_modules(archive, ("CONFIG_USB_DWC3_MSM",))
    except ValueError as exc:
        require(str(exc) == "CONFIG_USB_DWC3_MSM=m has no built-in driver and initramfs has 0 .ko files",
                f"unexpected cpio module rejection: {exc}")
        print(f"expected unpacked zero-.ko initramfs failure: {exc}")
    else:
        raise ValueError("zero-.ko initramfs accepted")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("config", "board"))
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    require(len(args.paths) == (2 if args.mode == "config" else 5), "incorrect inputs")
    config = pathlib.Path(args.paths[0]).read_bytes()
    fragment = pathlib.Path(args.paths[1]).read_bytes()
    values = check_config(config, fragment)
    if args.mode == "board":
        image = gzip.decompress(pathlib.Path(args.paths[2]).read_bytes())
        start = image.find(b"IKCFG_ST")
        end = image.find(b"IKCFG_ED", start + 8)
        require(start >= 0 and end > start and gzip.decompress(image[start + 8:end]) == config,
                "unpacked kernel IKCONFIG does not match verified built-in config")
        modules = check_modules(pathlib.Path(args.paths[4]).read_bytes(), ())
        require(not modules, "Path B initramfs contains .ko; two sides changed")
        check_board(args.paths[3], values)
    else:
        print("Volcano USB built-in Kconfig closure: OK")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, UnicodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
