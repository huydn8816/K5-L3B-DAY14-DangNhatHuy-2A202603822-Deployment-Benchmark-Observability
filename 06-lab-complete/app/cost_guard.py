"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM (tính theo token) vào Redis, theo ngày và theo tháng
  • Tổng chi phí vượt DAILY_BUDGET_USD hoặc MONTHLY_BUDGET_USD → HTTP 402
"""
import time

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _keys() -> tuple[str, str]:
    return (
        "cost:day:" + time.strftime("%Y-%m-%d", time.gmtime()),
        "cost:month:" + time.strftime("%Y-%m", time.gmtime()),
    )


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    day_key, month_key = _keys()
    try:
        day_spent = float(r.get(day_key) or 0)
        month_spent = float(r.get(month_key) or 0)
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable (Redis)")

    if day_spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget exhausted: ${day_spent:.4f} / ${settings.daily_budget_usd:.2f}",
        )
    if month_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly budget exhausted: ${month_spent:.4f} / ${settings.monthly_budget_usd:.2f}",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    day_key, month_key = _keys()
    try:
        pipe = r.pipeline(transaction=True)
        pipe.incrbyfloat(day_key, cost)
        pipe.expire(day_key, 2 * 86400)
        pipe.incrbyfloat(month_key, cost)
        pipe.expire(month_key, 32 * 86400)
        pipe.execute()
    except redis.RedisError:
        # Request đã phục vụ xong; mất một lần ghi chi phí không đáng làm hỏng response.
        pass
    return cost
