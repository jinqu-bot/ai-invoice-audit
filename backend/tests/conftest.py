"""全局测试夹具。

规则引擎会往"报销台账"里记账，批次存在内存里——不清理的话，
上一个测试上传过的发票会让下一个测试变成"重复报销"，测试就随顺序飘了。
"""

from __future__ import annotations

import pytest

from app.services import history, store


@pytest.fixture(autouse=True)
def clean_state():
    history.reset()
    store.reset()
    yield
    history.reset()
    store.reset()