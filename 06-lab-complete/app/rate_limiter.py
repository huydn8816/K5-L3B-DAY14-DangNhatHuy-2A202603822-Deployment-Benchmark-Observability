"""
Rate limiting (tiêu chí 7).

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State lưu trong Redis (sorted set) nên mọi worker / instance dùng chung
    và vẫn còn sau khi restart agent
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    # Băm key để không lưu API key thô trong Redis
    bucket = "rate:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex}"  # member duy nhất, tránh 2 request cùng timestamp đè nhau
    try:
        # MULTI/EXEC: 4 lệnh chạy nguyên khối nên nhiều worker không chen ngang nhau
        pipe = r.pipeline(transaction=True)
        pipe.zremrangebyscore(bucket, 0, now - WINDOW_SECONDS)  # bỏ request ngoài cửa sổ
        pipe.zadd(bucket, {member: now})
        pipe.zcard(bucket)
        pipe.expire(bucket, WINDOW_SECONDS + 1)
        _, _, count, _ = pipe.execute()

        if count > settings.rate_limit_per_minute:
            r.zrem(bucket, member)  # request bị từ chối thì không tính vào cửa sổ
            oldest = r.zrange(bucket, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
                headers={"Retry-After": str(retry_after)},
            )
    except redis.RedisError:
        # Không kiểm soát được tốc độ thì không cho đi tiếp (fail closed)
        raise HTTPException(status_code=503, detail="Rate limiter unavailable (Redis)")
