"""全局配置。D1 只有开关和占位，密钥一律从环境变量读，不写进代码。"""

import os


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    app_name = "AI 报销审核台 API"
    version = "0.1.0"
    stage = "D1-mock"  # 每次阶段推进改这里，前端可以显示在页脚

    demo_mode: bool = _bool("DEMO_MODE")
    cors_origins: list[str] = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    upload_max_mb: int = int(os.getenv("UPLOAD_MAX_MB", "20"))

    # D2 起才会真正使用；D1 只做占位，避免以后调整结构
    vlm_api_key: str = os.getenv("VLM_API_KEY", "")
    vlm_base_url: str = os.getenv("VLM_BASE_URL", "")
    vlm_model: str = os.getenv("VLM_MODEL", "qwen-vl-max")

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")


settings = Settings()
