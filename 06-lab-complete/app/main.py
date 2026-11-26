"""
Production AI Agent — Part 6 Final Project

Chạy:   uvicorn app.main:app --workers 2
Chấm:   python check_production_ready.py
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# ── Structured logging (tiêu chí 10) ─────────────────────────
class JsonFormatter(logging.Formatter):
    """Mỗi dòng log là đúng 1 JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]  # mọi log đi qua root cũng thành JSON
    root.setLevel(logging.INFO)
    return logging.getLogger("agent")


logger = _setup_logging()


def log(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


# ── Lifespan + graceful shutdown (tiêu chí 11) ───────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    log("startup", environment=settings.environment, port=settings.port)
    yield
    # Uvicorn nhận SIGTERM → ngừng nhận kết nối mới, chờ request đang chạy xong,
    # chạy đoạn này rồi thoát với exit code 0. Không tự đăng ký signal handler
    # để khỏi chặn cơ chế tắt của uvicorn.
    log("shutdown", detail="finished in-flight requests, exiting")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log(
            "request",
            method=request.method,
            path=request.url.path,
            status=status,
            ms=round((time.perf_counter() - start) * 1000, 1),
        )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


# ── Health / Readiness (tiêu chí 4, 5) ───────────────────────
@app.get("/health")
def health():
    """Liveness: 200 miễn là process còn sống, KHÔNG phụ thuộc Redis."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness: 200 khi Redis kết nối được, 503 khi không."""
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"ready": False, "reason": "redis unavailable"})
    return {"ready": True}


# ── Endpoint chính ───────────────────────────────────────────
@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)  # 429 khi vượt giới hạn
    check_budget()  # 402 khi hết budget

    answer = llm_ask(body.question)

    # Mock LLM không trả số token → ước lượng theo số từ
    cost = record_cost(
        input_tokens=len(body.question.split()) * 2,
        output_tokens=len(answer.split()) * 2,
    )
    log("ask", user_id=body.user_id, cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
