# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `01-localhost-vs-production/develop/app.py`

1. **Secret hardcode** (dòng 17–18): `OPENAI_API_KEY = "sk-..."` và `DATABASE_URL` có cả mật khẩu nằm ngay trong code. Push lên GitHub là lộ.
2. **Không có config management** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` cố định, không đổi được giữa dev/staging/production nếu không sửa code.
3. **`print()` thay cho logging** (dòng 33, 38, 48), và dòng 34 còn **in secret ra log**: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Tôi đã chạy và thấy dòng `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this` xuất hiện trong log của server.
4. **Không có health check** (dòng 42–43): platform không biết agent còn sống hay đã treo. Gọi `GET /health` trả **404**.
5. **Port và host cố định** (dòng 47–53): `host="localhost"` (container/cloud không truy cập được), `port=8000` không đọc từ biến `PORT` mà Railway/Render cấp.
6. **`reload=True`** (dòng 53): chế độ debug tự reload không dùng cho production.
7. **Không xử lý shutdown**: không có `lifespan` hay xử lý SIGTERM, nên request đang chạy có thể bị cắt khi platform dừng container.
8. **Không xác thực, không rate limit, không validate đầu vào**: ai gọi `/ask` cũng được, không giới hạn độ dài `question`.

### Exercise 1.2: Chạy bản develop

Chạy bản develop (dùng cổng khác vì cổng 8000 trên máy đang có tiến trình khác):

```
$ curl -i -X POST "http://localhost:18001/ask?question=Hello"
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -i -X POST http://localhost:18001/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 422 Unprocessable Content
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

$ curl -i http://localhost:18001/health
HTTP/1.1 404 Not Found
```

Quan sát: nó chạy, nhưng `question` là query param nên gửi JSON bị 422 (đúng như *Lưu ý* số 3 trong README), không có `/health`, và secret bị in ra log. Vì vậy nó chưa sẵn sàng cho production.

### Exercise 1.3: Bảng so sánh develop và production

| Feature | Develop | Production | Tại sao quan trọng? |
|---|---|---|---|
| Config | Hardcode trong code (`DEBUG=True`, key, URL) | Đọc từ env qua `config.py` (`os.getenv`), có validate | Cùng một image chạy được ở dev/staging/prod, đổi cấu hình không cần build lại (12-Factor) |
| Secrets | Key và mật khẩu DB nằm trong code, bị `print` ra log | Chỉ lấy từ env, `.env.example` không chứa giá trị thật, không log secret | Tránh lộ secret qua git và log |
| Health check | Không có (`/health` → 404) | `GET /health` (liveness) trả status, uptime, version | Platform biết khi nào cần restart container |
| Readiness | Không có | `GET /ready` trả 503 khi chưa sẵn sàng | Load balancer không gửi traffic vào instance đang khởi động hoặc đang tắt |
| Logging | `print()`, có cả secret | `logging` với format JSON, không log secret | Log aggregator (Loki, Datadog) parse và lọc được |
| Shutdown | Đột ngột, không có `lifespan` | `lifespan` + handler SIGTERM, đánh dấu `is_ready=False` rồi dọn dẹp | Không mất request đang xử lý khi deploy hoặc scale |
| Host / Port | `localhost`, cố định 8000 | `0.0.0.0`, đọc `PORT` từ env | Container và cloud truy cập được và cấp port động |
| Reload | `reload=True` luôn bật | Chỉ bật khi `DEBUG=true` | Reload tốn tài nguyên và không an toàn ở production |
| CORS | Không cấu hình | `allowed_origins` từ env | Giới hạn nguồn được gọi API từ trình duyệt |
| Validate đầu vào | Không | Trả 422 khi thiếu `question` | Từ chối dữ liệu xấu sớm |

**Phát hiện thêm khi chạy thật bản production** (`uvicorn app:app`): dù code có cấu hình log JSON, log của app không hiện ra, chỉ thấy `WARNING:root:OPENAI_API_KEY not set` theo format mặc định. Nguyên nhân khả dĩ: `config.py` gọi `logging.warning()` lúc import, việc này tự cấu hình root logger trước khi `logging.basicConfig(...)` của `app.py` chạy, nên lệnh `basicConfig` sau đó không có tác dụng. Ngoài ra format `'{"msg":"%(message)s"}'` sẽ cho JSON sai nếu `message` đã chứa dấu ngoặc kép (như `json.dumps(...)`). Trong Part 6 tôi viết `JsonFormatter` riêng (`json.dumps` cả dòng) để tránh cả hai lỗi này.

## Part 2: Docker

### Exercise 2.1: Câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image:** `python:3.11` (bản đầy đủ, khoảng 1 GB theo comment trong file).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Vì sao `COPY requirements.txt` trước:** Docker cache theo từng layer. Dependencies ít đổi còn code đổi liên tục. Nếu copy requirements và `pip install` trước, sửa code chỉ build lại các layer sau, còn layer cài thư viện (chậm nhất) được dùng lại từ cache. Nếu `COPY . .` trước thì mỗi lần sửa một dòng code đều phải cài lại toàn bộ thư viện.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định và bị thay thế được khi `docker run <image> <lệnh khác>`. `ENTRYPOINT` là chương trình cố định của container, tham số truyền vào `docker run` được nối thêm làm đối số của nó. Thường dùng `ENTRYPOINT` cho file thực thi chính và `CMD` cho đối số mặc định.

### Exercise 2.2: Build và chạy bản develop

Chạy từ gốc repo (đo trong WSL2, Docker 29.10.1):

```
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d --rm --name p2dev -p 18020:8000 my-agent:develop
$ curl -i -X POST "http://localhost:18020/ask?question=What%20is%20Docker%3F"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

(Dùng cổng 18020 vì cổng 8000 trên máy đang có tiến trình khác.)

```
$ docker images | grep my-agent
my-agent:develop     0f3d77d5f0d1   1.67GB   (content size 426MB)
my-agent:advanced    9405e79d12db   240MB    (content size 57.4MB)
```

### Exercise 2.3: Multi-stage (`02-docker/production/Dockerfile`)

- **Stage 1 (`builder`):** từ `python:3.11-slim`, cài `gcc`, `libpq-dev` rồi `pip install --user -r requirements.txt` vào `/root/.local`. Stage này có đủ công cụ build và **không** được dùng để deploy.
- **Stage 2 (`runtime`):** cũng từ `python:3.11-slim`, tạo user không phải root (`appuser`), chỉ `COPY --from=builder /root/.local` sang `/home/appuser/.local`, copy code, `chown`, chuyển `USER appuser`, thêm `HEALTHCHECK`, chạy `uvicorn --workers 2`.
- **Vì sao nhỏ hơn:** (1) base là `slim` thay vì bản đầy đủ; (2) `gcc`, `libpq-dev` và cache `apt` ở stage builder không đi vào image cuối; (3) chỉ có Python và site-packages cần để chạy. Đồng thời an toàn hơn vì chạy bằng non-root và ít công cụ cho kẻ tấn công.

Kích thước image (đo bằng `docker images`):

| Image | Kích thước |
|---|---|
| `my-agent:develop` | 1670 MB (1.67 GB, cột DISK USAGE của `docker images`; content size 426 MB) |
| `my-agent:advanced` | 240 MB (content size 57.4 MB) |
| Chênh lệch | giảm khoảng **85.6%** theo DISK USAGE: (1670 − 240) / 1670. Theo content size: giảm khoảng 86.5% (426 → 57.4 MB) |

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

Có 4 service, cùng nằm trong mạng bridge `internal` và gọi nhau bằng tên service (DNS nội bộ của Docker):

```
Client ──80/443──▶ nginx ──▶ agent:8000 ──▶ redis:6379
                                  └────────▶ qdrant:6333
```

- `nginx` (nginx:alpine): cổng duy nhất mở ra ngoài (80, 443). Reverse proxy và load balancer, có rate limit 10 req/s mỗi IP (`limit_req`) và security headers.
- `agent`: FastAPI, không publish port trực tiếp. Nhận `REDIS_URL=redis://redis:6379/0` và `QDRANT_URL=http://qdrant:6333`.
- `redis` (redis:7-alpine): cache session và rate limiting, có volume `redis_data` và healthcheck `redis-cli ping`.
- `qdrant` (v1.9.0): vector database cho RAG, có volume `qdrant_data`.
- `agent` chỉ khởi động khi `redis` và `qdrant` đã `service_healthy` (`depends_on` + `condition`).

Đã chạy `docker compose -p k5-day14-docker up -d --build` trong `02-docker/production/` (sau `touch .env.local`). Cả 4 service lên: `redis` và `qdrant` ở trạng thái `healthy` trước, rồi `agent`, rồi `nginx` (đúng thứ tự `depends_on`), chỉ `nginx` mở cổng ra ngoài (`0.0.0.0:80->80`, `443`).

```
$ curl -i http://localhost/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.5,"version":"2.0.0","timestamp":"2026-11-26T10:40:33.194570"}

$ curl -i http://localhost/ask -X POST -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Sau đó đã `docker compose -p k5-day14-docker down`.

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6

- Nền tảng: Render (Blueprint `06-lab-complete/render.yaml`, gói free, web service Docker + Redis)
- URL public: https://ai-agent-iuyb.onrender.com
- Ảnh: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`
- Chi tiết xem `DEPLOYMENT.md`.

### So sánh `railway.toml` với `render.yaml`

| | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng | TOML, chỉ mô tả build và deploy của **một** service | YAML kiểu Blueprint, mô tả cả hạ tầng gồm nhiều service |
| Build | `builder = "NIXPACKS"` (tự nhận diện) hoặc `"DOCKERFILE"` | `runtime: python` kèm `buildCommand`, hoặc `runtime: docker` |
| Chạy | `startCommand` | `startCommand` |
| Health check | `healthcheckPath`, `healthcheckTimeout` | `healthCheckPath` |
| Restart | `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries` | Render tự quản lý |
| Biến môi trường | Đặt qua CLI hoặc dashboard (`railway variables set`), không nằm trong file | Khai báo trong `envVars`: `value` cố định, `sync: false` (nhập tay), `generateValue: true` (Render tự sinh) |
| Redis | Không khai báo trong file, phải thêm Redis thủ công trên dashboard | Khai báo luôn trong file bằng service `type: redis` |
| Khác | Không có region hay plan trong file | Có `region`, `plan`, `autoDeploy` |

### Exercise 3.3: Pipeline Cloud Run (chỉ đọc, không deploy)

`cloudbuild.yaml` là pipeline CI/CD chạy mỗi khi push lên main, gồm 4 bước nối tiếp bằng `waitFor`: (1) chạy `pytest`, test lỗi là dừng cả pipeline; (2) build image Docker, gắn tag theo `$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cache; (3) push image lên registry; (4) `gcloud run deploy` bản image theo commit SHA, truyền `ENVIRONMENT` qua `--set-env-vars` và lấy `OPENAI_API_KEY` từ Secret Manager qua `--set-secrets`. `service.yaml` mô tả service ở dạng khai báo (Knative): `minScale: 1` tránh cold start, `maxScale: 10` chặn chi phí, `containerConcurrency: 80`, giới hạn CPU/RAM, `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready`, secret lấy từ `secretKeyRef` thay vì ghi thẳng giá trị.

## Part 4: API Security

### Exercise 4.1: API key (`04-api-gateway/develop`)

- **API key được kiểm ở đâu:** hàm dependency `verify_api_key` (dòng 39–54), gắn vào `/ask` bằng `Depends(verify_api_key)`. Key đúng đọc từ env `AGENT_API_KEY`.
- **Sai key thì sao:** thiếu header → **401**; có header nhưng sai → **403**.
- **Rotate key:** đổi biến `AGENT_API_KEY` rồi restart/redeploy; không cần sửa code vì key nằm trong env. Code hiện chỉ chấp nhận **một** key nên mọi client phải đổi cùng lúc. Muốn rotate không downtime thì cho phép danh sách hai key (cũ và mới) trong giai đoạn chuyển.

Output đã chạy (`AGENT_API_KEY=secret-key-123`):

```
# không có key
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
# sai key
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
# đúng key
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2: JWT (`04-api-gateway/production`)

Flow: `POST /auth/token` với `student`/`demo123` → server kiểm tra rồi ký JWT (HS256, claim `sub`, `role`, `iat`, `exp` sau 60 phút) → client gửi `Authorization: Bearer <token>` → `verify_token` kiểm chữ ký và hạn, trả `username` và `role`, **không cần tra database** (stateless). Token hết hạn → 401, token sai chữ ký → 403.

```
# không có token
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
# có token (token đã che, dài 168 ký tự)
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

### Exercise 4.3: Rate limiting

- **Thuật toán:** sliding window log. Mỗi user có một `deque` chứa timestamp, mỗi request bỏ các timestamp quá 60 giây rồi đếm; nếu đã đủ giới hạn thì trả 429.
- **Giới hạn:** user 10 request/phút (`rate_limiter_user`), admin 100 request/phút (`rate_limiter_admin`).
- **Bypass cho admin:** không phải bỏ hẳn giới hạn mà là dùng một limiter riêng có ngưỡng cao hơn, chọn theo `role` trong JWT (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`).
- **Hạn chế:** state nằm trong RAM của từng process, nên khi chạy nhiều worker hoặc nhiều instance thì mỗi cái đếm riêng và giới hạn thực tế bị nhân lên. Đó là lý do Part 6 chuyển sang Redis.

Vòng lặp 15 request liên tiếp (tài khoản `student`; trước đó đã có 1 request ở bước 4.2 nên request thứ 10 của vòng lặp là request thứ 11 trong cửa sổ):

```
req  1 -> 200 ... req  9 -> 200
req 10 -> 429 ... req 15 -> 429

HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 58
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":58}}
```

### Exercise 4.4: Cost guard

- **Bản mẫu `04-api-gateway/production/cost_guard.py`:** lưu trong RAM, mỗi user có ngân sách $1/ngày và toàn hệ thống $10/ngày. `check_budget` chạy **trước** khi gọi LLM (user vượt → 402, toàn cục vượt → 503), `record_usage` chạy **sau** khi gọi, cộng token vào bản ghi. Sau 10 request, `/me/usage` báo `cost_usd = 0.000181`.
- **Bản tôi viết ở Part 6 (`06-lab-complete/app/cost_guard.py`):** lưu trong **Redis** để mọi worker dùng chung và không mất khi restart. Chi phí cộng dồn bằng `INCRBYFLOAT` vào hai key theo thời gian (`cost:day:YYYY-MM-DD` hết hạn sau 2 ngày, `cost:month:YYYY-MM` hết hạn sau 32 ngày), nên "reset" là tự động khi sang ngày/tháng mới. `check_budget()` vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` thì trả **402**. Pipeline `MULTI/EXEC` để cộng và đặt TTL cùng lúc.
- **Vì sao cần cả rate limit và cost guard:** rate limit bảo vệ *tốc độ* (chặn spam, bảo vệ server), cost guard bảo vệ *tiền* (một user gửi ít request nhưng prompt rất dài vẫn có thể đốt ngân sách mà không chạm rate limit).

## Part 5: Scaling & Reliability

### Exercise 5.1: Health và readiness

- `/health` (liveness): "process còn sống không?". Trả 200 miễn là app chạy; nếu fail, platform **restart** container. Bản develop còn kiểm RAM bằng `psutil`.
- `/ready` (readiness): "sẵn sàng nhận traffic chưa?". Trả 503 khi đang khởi động, đang tắt hoặc mất kết nối phụ thuộc (Redis); fail thì load balancer **ngừng gửi traffic nhưng không restart**.
- Khác nhau: liveness fail nghĩa là app hỏng, cần khởi động lại; readiness fail nghĩa là tạm thời chưa nhận việc được, chờ là hết. Ở Part 6, `/health` vẫn 200 khi Redis chết (restart agent không sửa được Redis, chỉ gây vòng lặp restart vô ích) còn `/ready` trả 503 (đừng cho traffic vào khi chưa dùng được).

### Exercise 5.2: Graceful shutdown

Bản develop (`05-scaling-reliability/develop/app.py`): middleware đếm `_in_flight_requests`; khi nhận SIGTERM, uvicorn ngừng nhận kết nối mới, chạy phần sau `yield` của `lifespan`, đặt `_is_ready=False` rồi chờ tối đa 30 giây cho đến khi số request đang chạy về 0; `uvicorn.run(..., timeout_graceful_shutdown=30)` cho phép chờ. Ở Part 6 tôi không tự đăng ký handler SIGTERM mà dựa vào cơ chế sẵn có của uvicorn (tự đăng ký mà không gọi lại handler cũ thì process sẽ không bao giờ tắt).

Đã chạy trong WSL2 (`PORT=18030 python app.py`), gửi `POST /ask` rồi gửi `kill -TERM` ngay sau đó (cách nhau khoảng 30 ms):

```
[request result] HTTP 200
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
[server exit code] 0

INFO:     Shutting down
INFO:     127.0.0.1:53022 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
INFO ... 🔄 Graceful shutdown initiated...
INFO ... ✅ Shutdown complete
INFO:     Finished server process
INFO ... Received signal 15 — uvicorn will handle graceful shutdown
```

Quan sát: request đang xử lý vẫn trả **200** dù SIGTERM đã đến (log `Shutting down` xuất hiện trước dòng 200 OK của request), sau đó mới chạy phần shutdown của `lifespan` và process thoát với exit code **0**. Lưu ý: mock LLM chỉ ngủ khoảng 0.1 giây nên request rất ngắn; thử nghiệm này xác nhận thứ tự shutdown nhưng chưa thử với request chạy lâu.

### Exercise 5.3: Stateless

`05-scaling-reliability/production/app.py` lưu session và history trong Redis (`setex` với TTL 1 giờ, giữ tối đa 20 message) thay vì dict trong RAM. Lý do: khi scale thành nhiều instance, mỗi instance có RAM riêng, request thứ hai của user rơi vào instance khác sẽ mất lịch sử. Lưu ý: file này có đường lui sang dict trong RAM khi không có Redis, và phần đó **không** scale được (log in ra `Redis not available — using in-memory store (not scalable!)`).

### Exercise 5.4 / 5.5: Load balancing và test stateless

Đã chạy trong `05-scaling-reliability/production/` (sau `touch .env.local`):

```
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down
```

`docker compose ps` thấy 3 container `agent` đều `healthy`, cùng `nginx` và `redis`. Output của `test_stateless.py`:

```
Session ID: c839f5e1-3eea-44a1-9b6b-246b7c257a71
Request 1: [instance-eaf066]  Q: What is Docker?
Request 2: [instance-d83ed8]  Q: Why do we need containers?
Request 3: [instance-f66bb2]  Q: What is Kubernetes?
Request 4: [instance-eaf066]  Q: How does load balancing work?
Request 5: [instance-d83ed8]  Q: What is Redis used for?
Total requests: 5
Instances used: {'instance-d83ed8', 'instance-eaf066', 'instance-f66bb2'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

5 request trong **cùng một session** được 3 instance khác nhau phục vụ (Nginx chia vòng), nhưng history vẫn liền mạch đủ 10 message (5 câu hỏi + 5 câu trả lời), vì session lưu ở Redis chứ không nằm trong RAM của instance nào. Đó là điều kiện để scale ngang.

Lưu ý trung thực: trong **lần chạy đầu tiên**, `POST /chat` qua Nginx trả `502 Bad Gateway` dù `/health` đã 200, và `test_stateless.py` dừng ở request 1. Sau khi bật lại stack, 6 request `/chat` liên tiếp đều 200 và test chạy đủ. Tôi chưa xác định chắc nguyên nhân của lần 502 đó (có thể do vừa khởi động, Nginx chưa kết nối được tới các instance), nên chỉ ghi lại hiện tượng.

## Part 6: Final Project

Kết quả `python check_production_ready.py` (bản đầy đủ, chạy trong WSL2, có Docker):

```
📋 Checklist Deliverable
   ✅ Dockerfile (multi-stage, < 500 MB)
   ✅ docker-compose.yml (agent + redis)
   ✅ .dockerignore
   ✅ Health check endpoint (GET /health)
   ✅ Readiness endpoint (GET /ready)
   ✅ API Key authentication
   ✅ Rate limiting
   ✅ Cost guard
   ✅ Config từ environment variables
   ✅ Structured logging
   ✅ Graceful shutdown
   ✅ Public URL ready (Railway / Render config)
Result: 12/12 tiêu chí đạt · 42/42 checks passed
🎉 PASS 12/12 — PRODUCTION READY!
```

Một số số đo từ lần chạy này: image `06-lab-complete` là **297 MB** (< 500 MB), build 2 giây (có cache), `docker stop` thoát với exit code 0 trong 0.8 giây, rate limit trả 429 sau 5 request thành công (`RATE_LIMIT_PER_MINUTE=5`) và vẫn 429 sau khi restart agent (state nằm trong Redis), 17 dòng log đều là JSON hợp lệ.

### Quyết định thiết kế trong `06-lab-complete/app/`

- `config.py`: đọc tất cả từ env với giá trị mặc định an toàn; `AGENT_API_KEY` mặc định rỗng nên chưa cấu hình thì mọi request `/ask` bị 401 (không vô tình mở công khai).
- `auth.py`: `APIKeyHeader(auto_error=False)` rồi tự trả 401 (nếu để mặc định hoặc dùng `Header(...)` bắt buộc thì thiếu header sẽ ra 422/403). So sánh bằng `hmac.compare_digest` để chống timing attack.
- `redis_client.py`: `redis.from_url` chỉ tạo client, không kết nối lúc import, nên app khởi động được khi chưa có Redis; `redis_healthy()` bắt lỗi và trả `False`.
- `rate_limiter.py`: sliding window bằng sorted set trong Redis, bốn lệnh `ZREMRANGEBYSCORE → ZADD → ZCARD → EXPIRE` chạy trong `MULTI/EXEC` để nhiều worker không chen ngang; request bị từ chối thì `ZREM` ra khỏi cửa sổ; trả `Retry-After` tính từ request cũ nhất. Key Redis dùng hash của API key, không lưu key thô. Redis lỗi thì trả 503 (fail closed).
- `cost_guard.py`: xem Exercise 4.4.
- `main.py`: `JsonFormatter` tự viết dùng `json.dumps` (mỗi dòng log là một object JSON hợp lệ); middleware ghi log mỗi request; `/health` không đụng Redis; `/ready` trả 503 khi Redis không ping được; `/ask` chạy theo thứ tự `verify_api_key → check_rate_limit → check_budget → LLM → record_cost`.

## AI log

Theo `RULES.md` mục 1, đây là phần ghi lại việc dùng AI (Claude Code) trong bài này: hỏi gì, nhận gì, ai kiểm tra thế nào.

### Phần AI làm

| Phần | Tôi hỏi / nhờ | AI đã làm | Kiểm tra |
|---|---|---|---|
| Part 6 `06-lab-complete/app/*.py`, `.env.example` | Viết các file Python còn `TODO` theo hợp đồng trong `06-lab-complete/README.md` | Code cho config, auth, redis_client, rate_limiter, cost_guard, main | AI chạy thử bằng `fakeredis` và `TestClient` (12 tình huống: health, ready, 401, 429, 402, Redis chết, log JSON), sau đó chính tôi chạy `python check_production_ready.py` bản đầy đủ trong WSL2 và được `PASS 12/12` |
| Part 6 `render.yaml` | Viết cấu hình Render | AI viết `render.yaml` (web service Docker, Redis, `generateValue` cho `AGENT_API_KEY`) | Render đọc được file và deploy lên trạng thái Live; tôi chạy 4 lệnh curl ra `200, 200, 401, 200` (`screenshots/test.png`) |
| Part 1, 4 | Chạy thử các bản develop/production và tổng hợp output | Output `curl` ghi trong các mục tương ứng (AI tự chạy trên máy này, dùng cổng khác 8000 vì cổng 8000 đã bị chiếm) | Số liệu là output thật của lệnh đã chạy |
| Part 2, 3, 5 | Đọc Dockerfile, compose, `cloudbuild.yaml`, mã nguồn và viết câu trả lời; đo các số cần Docker | Phần giải thích bằng chữ; AI tự chạy các lệnh Docker trong WSL2 (build 2 image Part 2 và đo kích thước, stack Compose Part 2.4, `--scale agent=3` và `test_stateless.py` Part 5, thử SIGTERM Part 5.2) | Đã đối chiếu với file; các số trong Part 2 và Part 5 là output thật của các lệnh đó. Trong lần chạy đầu của `test_stateless.py` có một lỗi 502 chưa rõ nguyên nhân, đã ghi trung thực trong Part 5 |
| Part 7 | Chạy benchmark local (load test, eval), stack Docker (Locust, alert, trace) và tổng hợp vào báo cáo | Chạy các lệnh, đọc Prometheus/Jaeger API, điền `BENCHMARK_REPORT.md`. AI cũng sửa `06-lab-complete/benchmark-observability/production/Dockerfile` (thêm `ENV PYTHONUSERBASE=/home/agent/.local`) vì bản gốc làm agent crash với `No module named 'uvicorn'` | Số mục 2–3 lấy từ các file JSON trong `reports/`; số mục 4 lấy từ log và API của Prometheus/Jaeger. Mục 5 (scale) **chưa có số đo hợp lệ**: hai lần đo đầu không chạy đúng số instance (`docker compose run` ghi đè `--scale`), đã bỏ và ghi rõ trong báo cáo |
| Rà soát file của tôi | Xem lại `Dockerfile`, `docker-compose.yml`, `.dockerignore` | AI chỉ ra `__pycache__/` không khớp thư mục con trong `.dockerignore`, cổng compose lệch README, còn khối `TODO` thừa | Tôi đồng ý sửa; AI sửa, build lại image kiểm tra `__pycache__` không còn trong image và `docker compose config` hợp lệ |

Lỗi của AI trong quá trình làm, đã phát hiện và sửa: một kịch bản điền `MISSION_ANSWERS.md` làm file phình hơn 1800 dòng (đã khôi phục và kiểm tra lại các mục); hai lần đo scale sai (xem trên); một nhận định ban đầu về nguyên nhân log JSON của `01-localhost-vs-production/production` trong Part 1 chỉ là suy đoán và được ghi là "khả dĩ", chưa kiểm chứng.

### Phần tôi tự làm

- **`06-lab-complete/Dockerfile`**: tôi tự gõ và build từng phiên bản (v1 đến v5, từ một stage chạy bằng root đến multi-stage, user non-root, `HEALTHCHECK`, `PORT`, uvicorn là PID 1), theo các bước và đoạn mã mẫu do AI hướng dẫn. Tôi gặp và tự sửa các lỗi: cổng bind (`port is already allocated`), `CMD --port` không khớp cổng map (`Empty reply from server`), mở `0.0.0.0` trong trình duyệt (`ERR_ADDRESS_INVALID`), curl khi container chưa kịp khởi động (mã `000`). Mỗi phiên bản tôi kiểm tra bằng `docker run`, `docker logs`, `curl`, `docker exec whoami`.
- **`.dockerignore`**: tôi tự viết; AI phát hiện lỗi hai pattern trên một dòng (`.env.* !.env.example`) và tôi sửa thành ba dòng riêng.
- **`docker-compose.yml`**: tôi viết dựa trên khung AI đưa (service `agent` và `redis`, `env_file` với `required: false`, `REDIS_URL`, `depends_on` với `service_healthy`), tạo file `.env` cục bộ với `AGENT_API_KEY` (đã `.gitignore`), và tự kiểm tra `200, 200, 401, 200` cùng cặp `/health` 200, `/ready` 503 khi dừng Redis.
- **Deploy**: tôi tự tạo Blueprint trên Render, push code, lấy `AGENT_API_KEY` từ dashboard, chạy 4 lệnh curl, và chụp ảnh `dashboard.png`, `running.png`, `test.png`.
- **Part 7 Bước 2**: tôi tự chụp 4 ảnh `grafana-dashboard.png`, `jaeger-slow-trace.png`, `jaeger-error-trace.png`, `prometheus-alert-firing.png` trên Grafana, Jaeger, Prometheus khi stack đang có tải.
- **`check_production_ready.py`**: tôi chạy trong WSL2 và được `PASS 12/12`.
