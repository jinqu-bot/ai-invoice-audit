"""全局配置。密钥一律从环境变量读，不写进代码。"""

import os
from pathlib import Path


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """把 backend/.env 读进环境变量。

    没装 python-dotenv，是因为这里只需要 KEY=VALUE 一种写法：多一个依赖，
    换台机器就多一个装不上的风险。真环境变量优先，方便临时覆盖、也方便
    在 CI 或命令行里直接给值。
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # 行尾注释：只有不带引号时才切，免得值本身含 # 被误伤
        if "#" in value and not value.startswith(('"', "'")):
            value = value.split("#", 1)[0].strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip('"').strip("'")


_load_dotenv(BASE_DIR / ".env")


class Settings:
    app_name = "AI 报销审核台 API"
    version = "0.6.0"
    stage = "D6-realtime"  # 每次阶段推进改这里，前端可以显示在页脚

    demo_mode: bool = _bool("DEMO_MODE")
    cors_origins: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    upload_max_mb: int = int(os.getenv("UPLOAD_MAX_MB", "20"))

    # ---- 识别模型（D2）----
    vlm_api_key: str = os.getenv("VLM_API_KEY", "")
    vlm_base_url: str = os.getenv("VLM_BASE_URL", "")
    vlm_model: str = os.getenv("VLM_MODEL", "qwen-vl-max")
    vlm_timeout_s: int = int(os.getenv("VLM_TIMEOUT_S", "60"))
    vlm_force_json: bool = _bool("VLM_FORCE_JSON")
    # 只在没有 key 时有意义：把 mock 的返回值钉死，用来验证某条分支
    # （0/1/2 对应三张样例票，non_invoice 对应"这不是发票"）
    mock_variant: str = os.getenv("MOCK_VARIANT", "")

    # ---- 文本模型（D6 编排器 / D9 意见生成）----
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # ---- 抽取策略 ----
    image_max_edge: int = int(os.getenv("IMAGE_MAX_EDGE", "1024"))
    confidence_threshold: float = _float("CONFIDENCE_THRESHOLD", "0.8")
    max_retry: int = int(os.getenv("EXTRACT_MAX_RETRY", "1"))
    cache_enabled: bool = _bool("EXTRACT_CACHE")
    cache_dir: Path = BASE_DIR / "data" / "cache"

    # ---- 存储（D5）----
    db_path: Path = Path(os.getenv("DB_PATH") or (BASE_DIR / "data" / "app.db"))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR") or (BASE_DIR / "data" / "uploads"))

    @property
    def has_vlm(self) -> bool:
        """没配 key 时自动走 mock，保证没有密钥也能把链路跑通。"""
        return bool(self.vlm_api_key and self.vlm_base_url)


settings = Settings()
