# Deployment Information

## Public URL
https://ai-agent-iuyb.onrender.com

## Platform
Render (Blueprint `06-lab-complete/render.yaml`, gói Free). Gồm hai service:
- `ai-agent`: web service chạy Docker, build từ `06-lab-complete/Dockerfile`, health check `/health`.
- `agent-cache`: Redis, kết nối nội bộ qua `REDIS_URL`.

## Test Commands

Đặt biến (không in key ra màn hình):
```bash
export BASE=https://ai-agent-iuyb.onrender.com
read -rs AGENT_API_KEY && export AGENT_API_KEY   # dán key lấy từ Render → Environment
```

Gói Free ngủ khi không có request, lần gọi đầu có thể mất khoảng một phút.

### Health check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Expected: 200
```

### Readiness (Redis kết nối được)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Expected: 200
```

### API không có key
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
# Expected: 401
```

### API có key
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
```

Kết quả đã chạy: `200, 200, 401, 200` (xem `screenshots/test.png`).

## Environment Variables Set
Giá trị không ghi trong repo, chỉ đặt trên Render.

| Biến | Nguồn |
|---|---|
| `AGENT_API_KEY` | Render tự sinh (`generateValue: true`) |
| `REDIS_URL` | Lấy từ service `agent-cache` (`fromService`) |
| `ENVIRONMENT` | `production` (khai báo trong `render.yaml`) |
| `PORT` | Render tự cấp, app đọc từ biến này |

Các biến tuỳ chọn (có giá trị mặc định trong code): `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD`.

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running (log JSON)](screenshots/running.png)
- [Test results](screenshots/test.png)
