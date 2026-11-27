# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Đặng Nhật Huy
**Ngày chạy:** 2026-11-26 (mục 2–4). Mục 5: chưa có số đo hợp lệ, xem giải thích ở mục 5.
**Môi trường:** Mục 2–3: Windows 10, 8 logical CPU, Python 3.14, agent và load test chạy cùng một máy (không dùng Docker). Mục 4: WSL2 + Docker 29.10.1 (stack `production/`, mỗi agent giới hạn 0.5 CPU / 256 MB theo `docker-compose.yml`); tài nguyên Docker Desktop: ⏳ BẠN ĐIỀN

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Ngưỡng mặc định của `load_test.py`; người dùng chat thấy chậm khi quá nửa giây. Đặt theo p95 vì average che mất tail latency |
| Error rate `/ask` | < 2 % | Ngưỡng mặc định của `load_test.py`; mock LLM đã có sẵn 1% lỗi upstream nên 2% chừa vừa đủ biên |
| Accuracy trên golden dataset | ≥ 80 % (quality gate mặc định); sau khi sửa KB nâng lên 100 % | 80% là ngưỡng mặc định của `run_eval.py`; sau khi sửa tri thức thì đặt cao hơn để không cho tụt lại |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.66 | 211.5 | 250.2 | 1735.4 | 0.67% | PASS |
| 10 | 34.59 | 214.0 | 477.5 | 1706.0 | 2.00% | PASS |
| 50 | 53.07 | 501.6 | 1825.1 | 2544.0 | 0.67% | FAIL (p95) |
| 100 | 32.38 | 1321.3 | 6027.4 | 6948.3 | 0.67% | FAIL (p95) |

**Nhận xét:** RPS tăng gần tuyến tính từ c=1 lên c=10 (3.66 → 34.59, gấp 9.5 lần) vì mỗi request chủ yếu là chờ (mock LLM ngủ khoảng 120–180 ms) nên chạy song song được. Từ c=10 lên c=50 RPS chỉ tăng 1.5 lần (34.59 → 53.07) trong khi p50 tăng từ 214 ms lên 501.6 ms và p95 vượt SLO: hệ thống bắt đầu bão hoà, request phải xếp hàng. Ở c=100 RPS **giảm** (32.38) còn p95 lên 6027 ms: quá tải thật sự. Nguyên nhân khả dĩ là agent chạy một process uvicorn và load generator chạy chung máy, nên cả hai tranh CPU; tôi chưa đo riêng từng nguyên nhân. Điểm vận hành tối đa còn đạt SLO nằm quanh c=10. Tỉ lệ lỗi dao động 0.67–2.00% là do mock cố ý trả 503 ngẫu nhiên khoảng 1% (`MOCK_ERROR_RATE`), mỗi mức chỉ 300 request nên số lỗi (2–6 request) dao động lớn; mức c=10 có 6 lỗi (2.00%) và vẫn được đánh dấu PASS.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 231.1 | 501.9 | 540.5 |
| 0.03 (mặc định) | 283.5 | 547.6 | 1710.1 |
| 0.1 | 387.9 | 1705.9 | 1776.9 |

**Nhận xét:** (Mỗi mức chạy 300 request, concurrency 20.) Từ `MOCK_SLOW_RATE=0` lên `0.1`, avg tăng 1.68 lần (231.1 → 387.9 ms) nhưng p99 tăng 3.3 lần (540.5 → 1776.9 ms) và p95 tăng 3.4 lần (501.9 → 1705.9 ms). Average pha loãng vài request rất chậm vào hàng trăm request nhanh nên chỉ nhích nhẹ, trong khi người dùng gặp request chậm vẫn chờ khoảng 1.7 giây. Với 3% request chậm (khoảng 9/300) thì p99 (3 request cuối) đã rơi vào đuôi chậm còn p95 thì chưa (547.6 ms); với 10% (khoảng 30/300) thì p95 cũng rơi vào đuôi. Vì vậy SLO phải đặt theo p95/p99 chứ không theo average. Lưu ý: ngay cả mức 0, p95 là 501.9 ms, vượt ngưỡng 500 ms chỉ 1.9 ms (nằm trong dao động đo), nên cờ SLO của dòng đó là FAIL sát ngưỡng.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57.3 | 109.0 | 113.7 |
| Tổng cost (USD) | 0.000407 | 0.000759 | 0.000790 |
| Cost / câu đúng (USD) | 0.00040695 | 0.00003616 | 0.00003436 |
| Quality gate | FAIL (min 80%) | PASS (min 80%) | PASS (min 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` (JWT khác gì API key) | `token`, `hết hạn`, `chữ ký` | Thêm vào cuối `KNOWLEDGE_BASE` (file `develop/utils/mock_llm.py`) một tài liệu kích hoạt bởi từ khoá `jwt`, nội dung nêu rõ API key là chuỗi cố định không tự hết hạn còn JWT là token có chữ ký số và hạn dùng |
| `scaling-03` (HPA dựa trên chỉ số nào) | `cpu`, `memory`, `custom metrics` | Thêm tài liệu kích hoạt bởi `hpa`, `kubernetes`, `autoscal`, nội dung nêu HPA scale theo CPU, memory hoặc custom metrics |

Kết quả: 2 câu được cải thiện, 0 regression, quality gate `--min-accuracy 1.0` PASS (`reports/eval_v2_fixed.json`). Từ khoá mới đủ hẹp (`jwt`, `hpa`...) nên không chen vào các câu hỏi khác.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 (có retrieval) đắt hơn v1 khoảng 1.86 lần mỗi lần chạy eval (0.000759 so với 0.000407 USD) vì prompt dài hơn (avg 109.0 so với 57.3 token) và chậm hơn một chút (eval p50 199.7 ms so với 169.0 ms, p95 235.9 ms so với 201.3 ms). Nhưng accuracy tăng từ 4.3% lên 91.3%, nên **cost / câu đúng** giảm khoảng 11 lần (0.00040695 → 0.00003616). Nếu chỉ nhìn "cost / câu" thì v1 trông rẻ hơn, trong khi gần như toàn bộ chi phí của v1 là câu trả lời sai. Sau khi sửa KB, cost/câu đúng giảm tiếp còn 0.00003436 dù tổng cost nhích lên, và p95 tăng nhẹ lên 248.8 ms (+12.9 ms).

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: `screenshots/grafana-dashboard.png` (error rate 22.45%, p95 5.00 s, 2 instance, cost $0.5789)
- [x] Một trace chậm trong Jaeger: `screenshots/jaeger-slow-trace.png` (trace `8ff3bbe1…`, 1.7 s)
- [x] Một trace lỗi trong Jaeger: `screenshots/jaeger-error-trace.png` (trace `6759cd74…`, `POST /ask` 503, các span có dấu lỗi)
- [x] Trang Alerts của Prometheus: `screenshots/prometheus-alert-firing.png` (`AgentHighErrorRate` và `AgentHighLatencyP95` cùng FIRING)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (lúc firing: error rate 19.57%, ngưỡng 5%) | 93 giây | Error rate và Requests/s theo status code |
| B | `MOCK_SLOW_RATE=0.3` (áp dụng thêm lên A, A vẫn đang firing) | `AgentHighLatencyP95` (lúc firing: p95 1.903 s, ngưỡng 1 s) | 146 giây | Latency /ask p50/p95/p99 |
| C | `LLM_MODEL=mock-llm-large` | không chạy | không chạy | không chạy |
| D | `docker pause` 1 instance | không chạy | không chạy | không chạy |
| E | `AGENT_VERSION=v1` | không chạy (đề chỉ yêu cầu ≥ 2 thí nghiệm) | không chạy | không chạy |

Cách đo thời gian: tính từ lúc chạy `docker compose up -d` với cấu hình mới (gồm cả thời gian tạo lại container) đến lúc Prometheus API báo alert ở trạng thái `firing`. Cả hai con số khớp với mệnh đề `for:` trong `alert_rules.yml`: A có `for: 1m` nên không thể nhanh hơn 60 giây (93 giây = `for` + chu kỳ scrape/đánh giá + thời gian tạo lại container), B có `for: 2m` nên không thể nhanh hơn 120 giây (146 giây). Mỗi thí nghiệm chỉ đo một lần, nên con số là một mẫu, không phải trung bình. Trước khi bắt đầu, `LLMCostBurnRateHigh` đã firing do tải 100 user của bước benchmark (chưa phải từ thí nghiệm).

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Tôi không chạy thí nghiệm E nên đây là phân tích chứ không phải kết quả đo. Alert hạ tầng chỉ nhìn thấy lỗi, độ trễ và instance còn sống, mà agent v1 vẫn trả lời nhanh và trả 200, chỉ là trả lời **sai**. Loại sự cố chất lượng này chỉ bắt được bằng eval: chạy golden dataset theo lịch (hoặc trước mỗi lần deploy, như job `.github/workflows/eval.yml` fail khi accuracy dưới ngưỡng) và so sánh với baseline. Ở phía vận hành có thể thêm metric chất lượng (ví dụ tỉ lệ retrieval hit) và alert khi tỉ lệ này tụt.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `8ff3bbe1cb80a59baf0bb0364134172f`
- Tổng thời gian: 1733.0 ms (span `POST /ask`; log `http_request` ghi 1727.5 ms)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1689.4 ms, khoảng 97.5%); `agent.run` 1710.4 ms bao quanh nó, còn `agent.retrieve_context` chỉ 20.1 ms. Thời gian nằm ở LLM, không phải code của agent
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T11:18:55.834281+00:00", "level": "INFO", "service": "observable-agent", "instance": "2f394e69e99c", "event": "llm_call", "trace_id": "8ff3bbe1cb80a59baf0bb0364134172f", "span_id": "744c45405d1034fe", "request_id": "c56537c490fc", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1683.9}
{"ts": "2026-11-26T11:18:55.849570+00:00", "level": "INFO", "service": "observable-agent", "instance": "2f394e69e99c", "event": "http_request", "trace_id": "8ff3bbe1cb80a59baf0bb0364134172f", "span_id": "744c45405d1034fe", "request_id": "c56537c490fc", "method": "POST", "route": "/ask", "status": 200, "ms": 1727.5}
```

Trace lỗi (xem `screenshots/jaeger-error-trace.png`), tìm từ dòng log `llm_error` bằng `trace_id`:

- `trace_id`: `6759cd74fd0b157252ebc2fe522d6c0a`, tổng 115 ms trên Jaeger, `POST /ask` trả 503, span `agent.run` và `chat mock-llm-small` có lỗi `LLMError: Upstream LLM error: 503 Service Unavailable (mock)` kèm event `exception`.

```json
{"ts": "2026-11-26T11:16:01.177371+00:00", "level": "INFO", "service": "observable-agent", "instance": "2f394e69e99c", "event": "llm_error", "trace_id": "6759cd74fd0b157252ebc2fe522d6c0a", "span_id": "51f93cd3e9ece013", "request_id": "e2f12177026f", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T11:16:01.180406+00:00", "level": "INFO", "service": "observable-agent", "instance": "2f394e69e99c", "event": "http_request", "trace_id": "6759cd74fd0b157252ebc2fe522d6c0a", "span_id": "51f93cd3e9ece013", "request_id": "e2f12177026f", "method": "POST", "route": "/ask", "status": 503, "ms": 111.9}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | chưa có số đo hợp lệ | | | | |
| 3 | chưa có số đo hợp lệ | | | | |

**Giải thích kết quả:** Tôi chưa có số đo hợp lệ cho mục này, nên không đưa ra kết luận về việc scale có cải thiện p95 hay không và không nộp file `scale_1_stats.csv` / `scale_3_stats.csv`.

Lý do: tôi đã chạy Locust headless theo hướng dẫn (`docker compose up -d --scale agent=N` rồi `docker compose run --rm locust ...`) nhưng kiểm tra lại thì cả hai lần **đều không chạy đúng N instance**. `docker compose run` tự khởi động lại các service phụ thuộc (`nginx` → `agent`) theo `deploy.replicas: 2` trong file compose, nên ghi đè `--scale`: sau lần chạy "3 instance" chỉ còn 2 container `agent` (log của `agent-3` có 0 request `/ask`, Prometheus chỉ có 2 target). Lần chạy "1 instance" cũng có dấu hiệu bị đưa lên 2 (container `agent-2` xuất hiện ngay lúc lần chạy đó bắt đầu), nhưng tôi không kiểm chứng trực tiếp bằng số request theo từng container. Vì thế hai file CSV đó thực chất đều đo 2 instance và tôi đã bỏ chúng.

Cách đo lại đúng (chưa chạy): thêm `--no-deps` vào lệnh `run`, và trước khi chạy kiểm tra số container và số target (`docker compose -p k5-day14-observability ps -q agent | wc -l`, trang Prometheus *Status → Target health*):
```bash
docker compose -p k5-day14-observability up -d --scale agent=1
docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_1
docker compose -p k5-day14-observability up -d --scale agent=3
docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_3
```
⏳ BẠN ĐIỀN: bảng trên và phần giải thích, từ hai file CSV mới (lấy dòng `/ask`).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Average che giấu tail latency.** Với `MOCK_SLOW_RATE` từ 0 lên 0.1 (mục 2.2), average chỉ tăng khoảng 68% (231.1 → 387.9 ms) trong khi p99 tăng khoảng 229% (540.5 → 1776.9 ms), nên SLO phải đặt theo p95/p99.
  2. **Phải kiểm chứng điều mình đang đo.** Lần đầu stack trả 502 hoàn toàn vì Dockerfile của stack thiếu `PYTHONUSERBASE` (agent crash với `No module named 'uvicorn'`, tôi đã thêm một dòng để sửa). Lần đo scale sau đó trông hợp lý nhưng sai, vì `docker compose run` ghi đè `--scale`; chỉ khi đối chiếu số request theo từng container và số target Prometheus mới phát hiện. Số liệu trông hợp lý chưa chắc đúng.
  3. **Trace và log nối với nhau bằng `trace_id`.** Từ một dòng log `llm_error` tìm ra đúng trace trong Jaeger, và trace chậm cho thấy khoảng 97.5% thời gian nằm ở span `chat mock-llm-small`, không phải ở code của agent.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

  Tôi sẽ thêm: (a) giám sát ở tầng load balancer hoặc kiểm tra từ bên ngoài (synthetic check), vì lỗi 502/504 của Nginx không được tính vào metric của agent (README mục 2.6, thí nghiệm D); (b) metric và alert chất lượng, như tỉ lệ retrieval hit và điểm eval theo lịch, vì thí nghiệm E (v1) không làm alert hạ tầng nào firing; (c) alert theo tốc độ tiêu hao error budget thay vì chỉ ngưỡng tức thời; (d) cost theo từng model và từng người dùng, vì `LLMCostBurnRateHigh` đã firing ngay trong lúc benchmark bình thường.
