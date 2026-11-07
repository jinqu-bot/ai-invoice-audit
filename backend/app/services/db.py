"""SQLite 落库（D5）。

为什么用标准库 sqlite3 而不是 ORM：这个项目的查询就那几条，
引入 SQLAlchemy 只会多一层抽象、多一堆依赖，答辩时也不好讲。
**数据在进程死掉之后还在**，这才是 D5 真正要解决的事。

四张表：
- batches      一个批次一行，含汇总数字与失败清单
- invoices     一张发票一行，复杂结构（字段/规则/引用/轨迹）存 JSON 列
- reimbursements  报销台账，查重靠它
- counters     每日批次号序号，重启后不会重号
- images       上传原图在磁盘上的位置

并发：FastAPI 的同步路由跑在线程池里，所以连接用 check_same_thread=False，
写操作加一把进程内的锁。数据量在演示规模内，够用。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id      TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    status        TEXT NOT NULL,
    provider      TEXT NOT NULL DEFAULT 'fixture',
    invoice_count INTEGER NOT NULL DEFAULT 0,
    total_amount  REAL NOT NULL DEFAULT 0,
    pass_count    INTEGER NOT NULL DEFAULT 0,
    suspect_count INTEGER NOT NULL DEFAULT 0,
    reject_count  INTEGER NOT NULL DEFAULT 0,
    manual_count  INTEGER NOT NULL DEFAULT 0,
    elapsed_ms    INTEGER NOT NULL DEFAULT 0,
    failures_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id     TEXT PRIMARY KEY,
    batch_id       TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    filename       TEXT,
    verdict        TEXT NOT NULL,
    headline       TEXT NOT NULL,
    confidence     REAL NOT NULL,
    amount_incl_tax REAL NOT NULL DEFAULT 0,
    invoice_number TEXT,
    invoice_date   TEXT,
    seller_name    TEXT,
    category       TEXT,
    payload_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_invoices_batch ON invoices(batch_id);

CREATE TABLE IF NOT EXISTS reimbursements (
    invoice_number  TEXT PRIMARY KEY,
    invoice_code    TEXT,
    seller_name     TEXT,
    amount_incl_tax REAL,
    invoice_date    TEXT,
    reimbursement_no TEXT,
    employee        TEXT,
    dept            TEXT,
    submitted_at    TEXT,
    invoice_id      TEXT
);

CREATE TABLE IF NOT EXISTS audit_history (
    invoice_number  TEXT NOT NULL,
    source TEXT NOT NULL,
    invoice_code    TEXT,
    seller_name     TEXT,
    amount_incl_tax REAL,
    invoice_date    TEXT,
    reimbursement_no TEXT,
    employee        TEXT,
    dept            TEXT,
    submitted_at    TEXT,
    invoice_id      TEXT,
    PRIMARY KEY (source, invoice_number)
);

CREATE TABLE IF NOT EXISTS counters (
    day TEXT PRIMARY KEY,
    seq INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    image_id TEXT PRIMARY KEY,
    path     TEXT NOT NULL,
    mime     TEXT NOT NULL
);
"""


def _db_path() -> Path:
    return Path(settings.db_path)


def connection() -> sqlite3.Connection:
    """全局一个连接。第一次用时才建库建表。"""
    global _conn
    with _lock:
        if _conn is None:
            path = _db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            conn.commit()
            _conn = conn
        return _conn


def init() -> None:
    connection()


def execute(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    with _lock:
        conn = connection()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def query(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with _lock:
        return connection().execute(sql, params).fetchall()


def one(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with _lock:
        return connection().execute(sql, params).fetchone()


def close() -> None:
    """关掉连接，下次访问自动重连。

    测试用它模拟"后端重启"：如果重启后数据还在，说明真的落盘了，
    而不是内存里还记得。
    """
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def reset() -> None:
    """测试用：换库、清空、重建。生产代码不该调用。"""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except sqlite3.Error:
                pass
            _conn = None
        path = _db_path()
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(path) + suffix)
            if candidate.exists():
                candidate.unlink()
        connection()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default