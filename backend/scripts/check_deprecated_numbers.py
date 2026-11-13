#!/usr/bin/env python3
"""扫描仓库里已作废的评测数字，防止旧口径混进答辩材料。

为什么需要它：
    11/11 把全项目数字收敛成三个（规则 60/60、识别 44/50 + 544/550、端到端 56/60），
    但仓库里躺着大量按日期写的旧报告，里面还有 40/40、58/58、55/60……
    这些数字**在当时是对的**，现在引用就是错的。
    人眼扫 md 一定会漏，所以让它扫。

判定规则（两条，满足任一条就算"已标注"，放过）：
    1. 文件顶部 ARCHIVE_WINDOW 行内有作废/历史/存档类字样 → 整份文件视为存档件；
    2. 命中行本身（或上下 NEAR_WINDOW 行内）有同类字样 → 该处引用被视为已标废。

用法：
    python backend/scripts/check_deprecated_numbers.py          # 只看已提交的 .md
    python backend/scripts/check_deprecated_numbers.py --all    # 含未提交文件
    python backend/scripts/check_deprecated_numbers.py -v       # 逐条列出放过原因

退出码：0 = 干净；1 = 发现未标注的旧数字。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 已作废的数字。注意 **故意不包含 9/10**：
# 它在识别分组统计里是合法子桶（noise 9/10），单看数字无法区分，扫进来全是噪声。
DEPRECATED = [
    "40/40",
    "58/58",
    "55/60",
    "37/40",
    "38/40",
    "36/40",
    "92.5%",
    "20/24",
]

# 出现这些词，视为"已标注为作废/存档"。
# 注意 **故意不包含"过期"**：它在制度描述里正常出现（"逾期需附情况说明"），
# 当标记词会造成整份文件被静默放过——那是比漏报更糟的假阴性。
ARCHIVE_MARKERS = [
    "作废",
    "已被",
    "取代",
    "历史记录",
    "存档",
    "不再引用",
    "不得引用",
    "一律不再",
]

ARCHIVE_WINDOW = 15   # 文件顶部多少行内有标注，算整份存档件
NEAR_WINDOW = 6       # 命中行上下多少行内有标注，算该处已标废

SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "_local", "dist", "__pycache__"}


def _tracked_markdown(all_files: bool) -> list[Path]:
    if all_files:
        out: list[Path] = []
        for p in ROOT.rglob("*.md"):
            if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
                continue
            out.append(p)
        return sorted(out)

    try:
        res = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _tracked_markdown(all_files=True)

    return [ROOT / line for line in res.stdout.splitlines() if line.strip()]


def _has_marker(text: str) -> bool:
    return any(m in text for m in ARCHIVE_MARKERS)


def check_file(path: Path, verbose: bool) -> list[tuple[int, str, str]]:
    """返回未标注的命中：[(行号, 数字, 该行内容)]"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    head = "\n".join(lines[:ARCHIVE_WINDOW])
    file_archived = _has_marker(head)
    if file_archived and verbose:
        print(f"  [存档件] {path.relative_to(ROOT)}")

    hits: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        for token in DEPRECATED:
            if token not in line:
                continue
            if file_archived:
                break
            lo = max(0, idx - NEAR_WINDOW)
            hi = min(len(lines), idx + NEAR_WINDOW + 1)
            if _has_marker("\n".join(lines[lo:hi])):
                if verbose:
                    print(f"  [已标废] {path.relative_to(ROOT)}:{idx + 1}  {token}")
                break
            hits.append((idx + 1, token, line.strip()))
            break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描已作废的评测数字")
    ap.add_argument("--all", action="store_true", help="扫描全部 .md，不只 git 已跟踪的")
    ap.add_argument("-v", "--verbose", action="store_true", help="列出被放过的位置及原因")
    args = ap.parse_args()

    files = _tracked_markdown(args.all)
    if not files:
        print("没有找到任何 .md 文件", file=sys.stderr)
        return 1

    total = 0
    problems = 0
    for path in files:
        hits = check_file(path, args.verbose)
        if not hits:
            continue
        problems += 1
        total += len(hits)
        print(f"\n{path.relative_to(ROOT)}")
        for lineno, token, content in hits:
            print(f"  L{lineno:<4} {token:<7} {content[:88]}")

    print(f"\n扫描 {len(files)} 份 markdown，发现 {total} 处未标注的旧数字，涉及 {problems} 份文件。")
    if total:
        print(
            "\n处理方式（二选一）：\n"
            "  1) 在文件顶部加一行存档声明：> ⚠️ 本文是历史记录，数字已作废，现行见 docs/评测口径总表.md\n"
            "  2) 若该处仍被当作现行口径引用，直接改成三个冻结数字之一\n"
            "现行只有三个：规则 60/60、识别 44/50（544/550 = 98.9%）、端到端 56/60（93.3%）。"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
