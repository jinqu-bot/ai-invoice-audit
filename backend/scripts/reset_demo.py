"""演示前复位：把联调留下的痕迹清掉，让"第二幕（R3+R4）"能正常演。

为什么需要它：
    查重（R1）按台账查。今天为了验收，同一张发票被反复上传过；
    只要有一次被记进台账（pass/suspect 会记），下次再传就会**先命中 R1 并短路**，
    R3/R4 根本不会跑——第二幕就演不出来了。

这个脚本删的是**联调产生的测试记录**，不是真实报销数据（线上从来没有真实报销）。
线上台账里预置的 3 条"已报过"样例会保留，因为演示批次 B20261104-001 的 R1 故事要用它们。

用法：
    python scripts/reset_demo.py            # 只报告，不动手
    python scripts/reset_demo.py --yes      # 执行
    python scripts/reset_demo.py --yes --flush-cache   # 连识别缓存一起清（首次上传真的等 3-4 秒）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.services import db, history, store  # noqa: E402


def counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("batches", "invoices", "reviews", "audit_history"):
        try:
            row = db.one(f"SELECT COUNT(*) AS n FROM {table}")
            out[table] = int(row["n"]) if row else 0
        except Exception:  # 表可能还不存在（新库第一次跑）
            out[table] = -1
    return out


def files_in(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for p in folder.glob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="演示前复位（清联调痕迹）")
    parser.add_argument("--yes", action="store_true", help="真的执行；不带就是只报告")
    parser.add_argument("--flush-cache", action="store_true",
                        help="连识别缓存一起清（清完首次上传会真的调模型）")
    args = parser.parse_args()

    upload_dir = Path(settings.upload_dir)
    cache_dir = Path(settings.cache_dir)
    before = counts()
    print(f"库文件      : {settings.db_path}")
    print(f"上传目录    : {upload_dir}（{files_in(upload_dir)} 个文件）")
    print(f"识别缓存    : {cache_dir}（{files_in(cache_dir)} 个 json）")
    print(f"当前条数    : {before}")

    ledger = [dict(r) for r in db.query(
        "SELECT source, invoice_number, seller_name FROM audit_history "
        "ORDER BY rowid DESC LIMIT 10")]
    if ledger:
        print("\n台账最近的记录（演示时会被当成『报过』）：")
        for row in ledger:
            print(f"  [{row['source']}] {row['invoice_number']}  {row['seller_name']}")

    if not args.yes:
        print("\n这是只读报告。要执行请加 --yes。")
        return 0

    store.reset()           # 批次 / 发票 / 图片 / 上传文件
    db.execute("DELETE FROM reviews")
    history.reset()         # 台账清零后重新种 3 条预置样例
    flushed = 0
    if args.flush_cache and cache_dir.exists():
        for item in cache_dir.glob("*.json"):
            try:
                item.unlink()
                flushed += 1
            except OSError:
                pass

    after = counts()
    print("\n复位完成：")
    print(f"  条数    : {before} → {after}")
    print(f"  上传件  : {files_in(upload_dir)} 个")
    print(f"  缓存    : {files_in(cache_dir)} 个（本次清掉 {flushed}）")
    print(f"  台账    : {after.get('audit_history', 0)} 条（应为 3 条预置样例）")
    print("\n现在这张发票再上传，会正常走到 R3/R4，不会先被判重复报销。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
