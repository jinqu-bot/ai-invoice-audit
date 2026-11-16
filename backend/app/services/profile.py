"""公司档案：抬头、税号、提交期限、费用标准。

**一处存放**：数据库 `app_settings` 表里的一行 JSON。为什么放库不放 `.env`：
它要在页面上改、改完立刻生效、并且跟着库一起备份；放环境变量就得重启进程，
演示现场改一次公司名要重启一次服务，那是给自己找故障。

**为什么不做内存缓存**：一次 SQLite 读是微秒级，审核本来慢在模型调用上；
缓存出错的表现恰恰是"页面上保存成功、判定还是老公司"——最不该省的地方。

没配置过就用默认值（`company.py` 的虚构公司 + 内置制度档位），
所以演示批次和现有一套测试都不受影响。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.company import COMPANY_NAME, COMPANY_TAX_ID
from app.services import db

KEY = "company_profile"

# 只有这三个类目在制度里写了标准，改成配置后仍然只认这三个
LIMIT_CATEGORIES: tuple[str, ...] = ("住宿", "招待", "办公")

DEFAULT: dict[str, Any] = {
    "name": COMPANY_NAME,
    "tax_id": COMPANY_TAX_ID,
    "deadline_days": 30,
    "limits": {"住宿": 800.0, "招待": 2000.0, "办公": 5000.0},
}


def defaults() -> dict[str, Any]:
    """深拷贝：调用方改了不会污染模块级默认值。"""
    return db.loads(db.dumps(DEFAULT), {})


def _clean(raw: dict[str, Any] | None) -> dict[str, Any]:
    """把库里的 / 请求里的半成品补成完整档案：缺的用默认，脏的不参与。"""
    out = defaults()
    data = raw or {}

    name = str(data.get("name") or "").strip()
    tax_id = str(data.get("tax_id") or "").strip().upper()
    if name:
        out["name"] = name
    if tax_id:
        out["tax_id"] = tax_id

    try:
        days = int(data.get("deadline_days"))
    except (TypeError, ValueError):
        days = 0
    if 1 <= days <= 365:
        out["deadline_days"] = days

    limits = data.get("limits") or {}
    if isinstance(limits, dict):
        for category in LIMIT_CATEGORIES:
            try:
                value = float(limits.get(category))
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 10_000_000:
                out["limits"][category] = round(value, 2)
    return out


def get() -> dict[str, Any]:
    """当前生效的公司档案。任何异常都退回默认值，宁可宽松也不阻塞审核。"""
    try:
        row = db.one("SELECT value FROM app_settings WHERE key = ?", (KEY,))
    except Exception:  # 库没建好、表不存在、连接断了
        return defaults()
    if row is None:
        return defaults()
    return _clean(db.loads(row["value"], {}))


def get_with_meta() -> dict[str, Any]:
    """给接口用：在档案上补 updated_at / is_default，页面要显示"改没改过"。"""
    data = get()
    updated_at: str | None = None
    try:
        row = db.one("SELECT updated_at FROM app_settings WHERE key = ?", (KEY,))
        updated_at = row["updated_at"] if row else None
    except Exception:
        pass
    data["updated_at"] = updated_at
    data["is_default"] = updated_at is None
    return data


def save(payload: dict[str, Any]) -> dict[str, Any]:
    data = _clean(payload)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (KEY, db.dumps(data), now),
    )
    return get_with_meta()


def reset() -> None:
    """恢复默认（复位脚本与测试用）。"""
    db.execute("DELETE FROM app_settings WHERE key = ?", (KEY,))