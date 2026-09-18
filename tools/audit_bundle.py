"""Audit a PyInstaller bundle for missing (non-system) DLL dependencies.

Usage::

    python tools/audit_bundle.py dist/FusionMusicPlayer

Scans every .dll/.pyd in the bundle, resolves its PE import table and reports
dependencies that are neither bundled nor part of Windows itself. This is what
caught the truncated ``Qt6ShaderTools.dll`` dependency of
``Qt5CompleGraphicalEffects``'s private plugin — a breakage that only shows up
at runtime as "cannot load library".
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

# 控制台可能是 GBK，避免中文/异常字符触发 UnicodeEncodeError
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

# 只接受看起来像 DLL 文件名的条目：部分 PE（延迟加载、特殊布局）会让解析
# 出空串或乱码，这类噪音直接丢掉，避免误报。
_DEP_NAME_RE = re.compile(r"^[\x20-\x7e]{1,120}\.(dll|pyd|drv|ocx|so)$", re.IGNORECASE)

SYSTEM_PREFIXES = (
    "kernel32", "user32", "advapi32", "ole32", "oleaut32", "shell32", "gdi32",
    "msvcrt", "api-ms-", "ext-ms-", "ucrtbase", "ws2_32", "shlwapi", "version",
    "dwmapi", "uxtheme", "crypt32", "netapi32", "userenv", "d3d11", "dxgi",
    "d2d1", "dwrite", "opengl32", "winmm", "imm32", "wtsapi32", "comdlg32",
    "mpr", "rpcrt4", "secur32", "bcrypt", "ncrypt", "dnsapi", "iphlpapi",
    "setupapi", "propsys", "authz", "cabinet", "winspool", "msimg32",
    "ntdll", "powrprof", "psapi", "dbghelp", "windowscodecs", "wldap32",
    "winhttp", "normaliz", "d3dcompiler", "mfplat", "mfreadwrite", "mfuuid",
    "strmiids", "oleacc", "avrt", "dsound", "hid", "cfgmgr32", "bluetoothapis",
    "bthprops", "sensorsapi", "portabledeviceapi", "wevtapi", "twinapi",
    "dcomp", "d3d9", "d3d12", "dxva2", "evr", "ksuser", "mswsock", "npapi",
)


def read_imports(path: Path) -> list[str]:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("not a PE file")
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise ValueError("bad PE signature")
    coff = pe_off + 4
    num_sections, = struct.unpack_from("<H", data, coff + 2)
    opt_size, = struct.unpack_from("<H", data, coff + 16)
    opt_off = coff + 20
    magic, = struct.unpack_from("<H", data, opt_off)
    dd_off = opt_off + (112 if magic == 0x20B else 96)
    import_rva, _ = struct.unpack_from("<II", data, dd_off + 8)

    sections = []
    sec_off = opt_off + opt_size
    for i in range(num_sections):
        base = sec_off + i * 40
        _, vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIIII", data, base + 8)
        sections.append((vaddr, max(vsize, rawsize), rawptr))

    def rva_to_off(rva: int):
        for vaddr, size, rawptr in sections:
            if vaddr <= rva < vaddr + size:
                return rawptr + (rva - vaddr)
        return None

    names: list[str] = []
    if import_rva:
        off = rva_to_off(import_rva)
        while off:
            entry = data[off:off + 20]
            if len(entry) < 20 or entry == b"\0" * 20:
                break
            _, _, _, dll_rva, _ = struct.unpack("<IIIII", entry)
            if not dll_rva:
                break
            n_off = rva_to_off(dll_rva)
            if n_off is None:
                break
            end = data.index(b"\0", n_off)
            raw = data[n_off:end].decode("ascii", "replace")
            if _DEP_NAME_RE.match(raw):
                names.append(raw)
            off += 20
    return names


def is_system(dep: str) -> bool:
    low = dep.lower()
    return low.startswith(SYSTEM_PREFIXES)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 2

    present = {p.name.lower() for p in root.rglob("*") if p.suffix.lower() in (".dll", ".pyd")}
    binaries = sorted(p for p in root.rglob("*") if p.suffix.lower() in (".dll", ".pyd"))
    print(f"扫描 {len(binaries)} 个二进制，已打包依赖 {len(present)} 个\n")

    missing: dict[str, list[str]] = {}
    unreadable = 0
    for b in binaries:
        try:
            deps = read_imports(b)
        except Exception:
            unreadable += 1
            continue
        for dep in deps:
            if is_system(dep):
                continue
            if dep.lower() not in present:
                missing.setdefault(dep, []).append(str(b.relative_to(root)))

    if unreadable:
        print(f"（{unreadable} 个文件不是 PE 或无法解析，已跳过）\n")

    if not missing:
        print("OK：没有发现缺失的非系统依赖")
        return 0

    print(f"发现 {len(missing)} 个缺失依赖：\n")
    for dep, users in sorted(missing.items()):
        print(f"  MISS {dep}")
        for u in users[:4]:
            print(f"        <- {u}")
        if len(users) > 4:
            print(f"        ... 另有 {len(users) - 4} 个使用者")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
