"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Không hard-code secret trong code. Biến nào cũng có mặc định an toàn để chạy local,
riêng AGENT_API_KEY mặc định rỗng → app từ chối mọi request /ask cho tới khi được đặt.
"""
import os
from dataclasses import dataclass

try:  # .env chỉ dùng khi chạy local; biến môi trường thật luôn được ưu tiên
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    port: int
    environment: str
    agent_api_key: str
    redis_url: str
    rate_limit_per_minute: int
    daily_budget_usd: float
    monthly_budget_usd: float


def load_settings() -> Settings:
    return Settings(
        port=_int("PORT", 8000),
        environment=os.getenv("ENVIRONMENT", "development"),
        agent_api_key=os.getenv("AGENT_API_KEY", ""),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 10),
        daily_budget_usd=_float("DAILY_BUDGET_USD", 1.0),
        monthly_budget_usd=_float("MONTHLY_BUDGET_USD", 30.0),
    )


settings = load_settings()
