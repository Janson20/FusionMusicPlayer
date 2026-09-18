#!/usr/bin/env python3
"""版本发布脚本。

一条命令完成：校验工作区 → 跑测试 → 更新版本号 → 提交 → 打 tag → 推送，
推送 tag 后 GitHub Actions 会自动构建并发布 Release（见
``.github/workflows/release.yml``）。

用法::

    python scripts/release.py patch          # 1.0.0 -> 1.0.1
    python scripts/release.py minor          # 1.0.0 -> 1.1.0
    python scripts/release.py major          # 1.0.0 -> 2.0.0
    python scripts/release.py 1.2.3          # 指定版本号
    python scripts/release.py patch --dry-run  # 只预览，不做任何改动
    python scripts/release.py patch --no-push  # 提交并打 tag，但不推送
    python scripts/release.py patch -y         # 跳过确认

版本号会写进 ``app/_version.py``（唯一来源）；发布流水线在打包前还会依据
git tag 覆写一次，因此「源码里显示的版本」与「tag」不会漂移。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "app" / "_version.py"
TESTS = ROOT / "tests" / "test_core.py"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_DECL_RE = re.compile(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
BUMP_KINDS = ("major", "minor", "patch")


# ──────────────────────────────────────────────────────────────
# 输出（GBK 控制台下 emoji 会炸，检测不到就退回 ASCII）
# ──────────────────────────────────────────────────────────────


def _encodable(text: str) -> bool:
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _mark(emoji: str, ascii_fallback: str) -> str:
    return emoji if _encodable(emoji) else ascii_fallback


OK = _mark("✅", "[ OK ]")
WARN = _mark("⚠️ ", "[WARN]")
ERR = _mark("❌", "[FAIL]")
INFO = _mark("ℹ️ ", "[INFO]")
ROCKET = _mark("🚀", "[>>]")
TAG = _mark("🏷️ ", "[TAG]")
PEN = _mark("📝", "[EDIT]")


def info(msg: str) -> None:
    print(f"{INFO} {msg}")


def ok(msg: str) -> None:
    print(f"{OK} {msg}")


def warn(msg: str) -> None:
    print(f"{WARN} {msg}")


def fail(msg: str, code: int = 1) -> None:
    print(f"{ERR} {msg}", file=sys.stderr)
    sys.exit(code)


# ──────────────────────────────────────────────────────────────
# 命令执行
# ──────────────────────────────────────────────────────────────


def run(cmd: list[str], *, check: bool = True, capture: bool = True,
        dry_run: bool = False) -> subprocess.CompletedProcess:
    if dry_run:
        print(f"    [dry-run] {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(
        cmd, cwd=str(ROOT), check=check, text=True, encoding="utf-8",
        errors="replace", capture_output=capture,
    )


def git(*args: str, check: bool = True, capture: bool = True,
        dry_run: bool = False) -> str:
    proc = run(["git", *args], check=check, capture=capture, dry_run=dry_run)
    return (proc.stdout or "").strip() if capture else ""


# ──────────────────────────────────────────────────────────────
# 版本号
# ──────────────────────────────────────────────────────────────


def read_version() -> str:
    if not VERSION_FILE.exists():
        fail(f"找不到版本文件: {VERSION_FILE}")
    match = VERSION_DECL_RE.search(VERSION_FILE.read_text(encoding="utf-8"))
    if not match:
        fail(f"无法从 {VERSION_FILE.name} 中解析出 APP_VERSION")
    return match.group(1)


def write_version(new_version: str, *, dry_run: bool = False) -> None:
    content = VERSION_FILE.read_text(encoding="utf-8")
    updated = VERSION_DECL_RE.sub(f'APP_VERSION = "{new_version}"', content, count=1)
    if updated == content:
        warn(f"{VERSION_FILE.name} 已经是 {new_version}，跳过写入")
        return
    if dry_run:
        print(f"    [dry-run] 写入 {VERSION_FILE.relative_to(ROOT)}: APP_VERSION = \"{new_version}\"")
        return
    VERSION_FILE.write_text(updated, encoding="utf-8")
    ok(f"已更新 {VERSION_FILE.relative_to(ROOT)}")


def resolve_version(current: str, target: str) -> str:
    """把 ``patch`` / ``1.2.3`` 之类的入参解析成具体版本号。"""
    target = target.strip().lstrip("vV")

    if target in BUMP_KINDS:
        match = SEMVER_RE.match(current)
        if not match:
            fail(f"当前版本号 {current!r} 不是 major.minor.patch，无法按 {target} 递增")
        major, minor, patch = (int(x) for x in match.groups())
        if target == "major":
            return f"{major + 1}.0.0"
        if target == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"

    if not SEMVER_RE.match(target):
        fail(
            f"无效的版本号: {target}\n"
            f"       应为 major.minor.patch（如 1.2.3），或 major/minor/patch 之一"
        )
    return target


# ──────────────────────────────────────────────────────────────
# 前置检查
# ──────────────────────────────────────────────────────────────


def check_worktree(*, dry_run: bool = False) -> None:
    status = git("status", "--porcelain", dry_run=dry_run)
    if status:
        lines = status.splitlines()
        fail(
            "存在未提交的变更，请先提交\n"
            + "\n".join(f"       {line}" for line in lines[:15])
            + (f"\n       … 另有 {len(lines) - 15} 项" if len(lines) > 15 else "")
        )
    ok("工作区干净")


def check_branch() -> str:
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch in ("HEAD", ""):
        fail("当前处于游离 HEAD 状态，请先切换到分支")
    if branch != "main":
        warn(f"当前分支是 {branch}（发布通常在 main 上进行）")
    return branch


def check_tag_free(tag: str) -> None:
    if git("tag", "-l", tag):
        fail(f"标签 {tag} 已存在，请换一个版本号或先删除该标签")
    ok(f"标签 {tag} 未被占用")


def check_remote() -> str | None:
    remotes = git("remote").splitlines()
    return remotes[0] if remotes else None


def run_tests() -> None:
    if not TESTS.exists():
        warn(f"找不到 {TESTS}，跳过测试")
        return
    info("运行核心回归测试…")
    proc = subprocess.run(
        [sys.executable, str(TESTS)], cwd=str(ROOT),
        text=True, encoding="utf-8", errors="replace", capture_output=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        fail("测试未通过，已中止发布")
    tail = [ln for ln in (proc.stdout or "").splitlines() if "passed" in ln]
    ok(f"测试通过（{tail[-1].strip() if tail else 'ok'}）")


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────


def confirm(question: str) -> bool:
    try:
        answer = input(f"{question} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="release.py",
        description="更新版本号、提交、打 tag 并推送，触发 GitHub Actions 发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/release.py patch\n"
            "  python scripts/release.py minor -y\n"
            "  python scripts/release.py 1.2.3 --dry-run\n"
        ),
    )
    parser.add_argument("version", help="目标版本号，或 major / minor / patch")
    parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不做任何改动")
    parser.add_argument("--no-push", action="store_true", help="提交并打 tag，但不推送")
    parser.add_argument("--skip-tests", action="store_true", help="不运行测试")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="允许存在未提交的变更（不推荐）")
    args = parser.parse_args(argv)

    current = read_version()
    new_version = resolve_version(current, args.version)
    tag = f"v{new_version}"

    print()
    print(f"  当前版本 : {current}")
    print(f"  目标版本 : {new_version}")
    print(f"  标签     : {tag}")
    print(f"  模式     : {'预览（不做改动）' if args.dry_run else '正式发布'}")
    print()

    if new_version == current:
        fail(f"目标版本与当前版本相同（{current}），无需发布")

    # ── 前置检查 ────────────────────────────────────────────
    info("检查工作区…")
    if args.allow_dirty:
        warn("已跳过工作区检查（--allow-dirty）")
    else:
        check_worktree(dry_run=args.dry_run)
    branch = check_branch()
    check_tag_free(tag)
    remote = check_remote()
    if remote is None:
        warn("未配置 git remote，稍后将跳过推送")

    # ── 测试 ────────────────────────────────────────────────
    if args.skip_tests:
        warn("已跳过测试（--skip-tests）")
    elif not args.dry_run:
        run_tests()
    else:
        info("预览模式：跳过测试")

    # ── 确认 ────────────────────────────────────────────────
    if not args.yes and not args.dry_run:
        print()
        if not confirm(f"确认发布 {tag}？"):
            info("已取消")
            return 1

    # ── 执行 ────────────────────────────────────────────────
    print()
    info("更新版本号…")
    write_version(new_version, dry_run=args.dry_run)

    info("提交变更…")
    git("add", str(VERSION_FILE.relative_to(ROOT)), dry_run=args.dry_run)
    git("commit", "-m", f"chore: release {tag}", dry_run=args.dry_run)
    ok("已提交")

    info(f"创建标签 {tag}…")
    git("tag", "-a", tag, "-m", f"Release {new_version}", dry_run=args.dry_run)
    ok(f"已创建标签 {tag}")

    if args.no_push:
        warn("已跳过推送（--no-push）")
    elif remote is None:
        warn("未配置 git remote，跳过推送")
    else:
        info(f"推送分支 {branch}…")
        git("push", remote, branch, dry_run=args.dry_run, capture=False)
        info(f"推送标签 {tag}…")
        git("push", remote, tag, dry_run=args.dry_run, capture=False)
        ok("已推送到远端")

    print()
    if args.dry_run:
        ok("预览完成，未做任何改动")
    else:
        print(f"{ROCKET} 发布完成！GitHub Actions 将自动构建并创建 Release：")
        print(f"       {tag}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
