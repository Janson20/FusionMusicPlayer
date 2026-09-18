"""Rewrite deprecated signal-handler parameter injection into function form.

Preserves each file's original line endings byte-for-byte: reading/writing via
``open(..., newline="")`` avoids the platform newline translation that
``Path.read_text()``/``write_text()`` perform (which would silently convert an
LF file to CRLF on Windows and blow up the diff).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "app" / "ui"

RULES = [
    ("onPageRequested", "pageId"),
    ("onRequestPlayNow", "track"),
    ("onRequestPlayNext", "track"),
    ("onRequestAppend", "track"),
    ("onRequestFavorite", "track"),
    ("onToggled", "value"),
]


def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


total = 0
for path in sorted(UI.rglob("*.qml")):
    text = read_text(path)
    lines = text.splitlines(keepends=True)
    changed = 0
    for i, line in enumerate(lines):
        body_line = line.rstrip("\r\n")
        ending = line[len(body_line):]          # 保留原有的 \n 或 \r\n
        for handler, param in RULES:
            stripped = body_line.lstrip()
            if not stripped.startswith(f"{handler}:"):
                continue
            indent = body_line[: len(body_line) - len(stripped)]
            body = stripped[len(handler) + 1:].strip()
            if body.startswith("function") or not body:
                continue
            if not re.search(rf"\b{param}\b", body):
                continue
            lines[i] = f"{indent}{handler}: function ({param}) {{ {body} }}{ending}"
            changed += 1
            break
    if changed:
        write_text(path, "".join(lines))
        print(f"{path.relative_to(ROOT).as_posix()}: {changed} 处")
        total += changed

print(f"\n共修改 {total} 处")
