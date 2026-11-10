"""全局测试夹具。

两件事必须每个测试单独做：

1. **换成临时库**。D5 起数据写进 SQLite，不隔离的话每个测试都会往
   backend/data/app.db 里塞数据，跑第二遍就全是"重复报销"。
2. **清空台账**。同上，台账也会持久化。

用 tmp_path 而不是 :memory:，是为了验证"真的落盘了"这件事本身。
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import db, history, jobs, store


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    # 识别缓存也要隔离：不然上一轮测试留下的同名图会让"第一次上传"直接命中缓存，
    # cached 标记、延迟断言全都不作数（D7 加缓存标记时踩到过）。
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    db.reset()
    history.reset()
    jobs.reset()
    yield
    db.reset()
    jobs.reset()