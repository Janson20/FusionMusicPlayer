"""Find QML signal handlers that rely on deprecated parameter injection.

Qt 6.7+ warns: 'Parameter "x" is not declared. Injection of parameters into
signal handlers is deprecated. Use JavaScript functions with formal parameters
instead.'

This script collects every `signal foo(Type name, ...)` declared in the project's
QML, then flags handlers written as an expression or `{...}` block that reference
one of those parameter names. `function (name) {...}` form is correct.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "app" / "ui"

SIGNAL_RE = re.compile(r"^\s*signal\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE)
HANDLER_RE = re.compile(r"^\s*on([A-Z]\w*)\s*:\s*(.*)$")

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def collect_signals() -> dict[str, list[str]]:
    sigs: dict[str, list[str]] = {}
    for path in UI.rglob("*.qml"):
        text = path.read_text(encoding="utf-8")
        for m in SIGNAL_RE.finditer(text):
            name, params = m.group(1), m.group(2).strip()
            names = []
            for p in params.split(","):
                p = p.strip()
                if not p:
                    continue
                # "string pageId" -> pageId ; "var track" -> track
                names.append(p.split()[-1])
            sigs[name] = names
    return sigs


def handler_body(lines: list[str], start: int) -> tuple[str, int]:
    """Return (body, next_index) for the handler beginning at `start`."""
    first = lines[start].split(":", 1)[1]
    if first.strip().startswith("function"):
        return "", start + 1
    depth = first.count("{") - first.count("}")
    body = [first]
    i = start + 1
    if depth <= 0 and "{" not in first:
        return first, i
    while i < len(lines) and depth > 0:
        depth += lines[i].count("{") - lines[i].count("}")
        body.append(lines[i])
        i += 1
    return "\n".join(body), i


def main() -> int:
    sigs = collect_signals()
    if not sigs:
        print("没有找到任何自定义 signal")
        return 0

    problems = []
    for path in sorted(UI.rglob("*.qml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            m = HANDLER_RE.match(lines[i])
            if not m:
                i += 1
                continue
            handler = m.group(1)
            # onPageRequested -> signal pageRequested（首字母小写）
            signal_name = handler[0].lower() + handler[1:]
            if signal_name not in sigs:
                i += 1
                continue
            body, nxt = handler_body(lines, i)
            if body:
                for pname in sigs[signal_name]:
                    if re.search(rf"\b{re.escape(pname)}\b", body):
                        problems.append(
                            (path.relative_to(ROOT).as_posix(), i + 1,
                             f"on{handler}", pname)
                        )
            i = max(nxt, i + 1)

    print(f"扫描到 {len(sigs)} 个自定义 signal：{', '.join(sorted(sigs))}")
    print()
    if not problems:
        print("OK：没有依赖参数注入的信号处理器")
        return 0
    print(f"发现 {len(problems)} 处使用了已废弃的参数注入：\n")
    for rel, line, handler, pname in problems:
        print(f"  {rel}:{line}  {handler} 使用了未声明的参数 '{pname}'")
        print(f"      -> 改成 {handler}: function ({pname}) {{ ... }}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
