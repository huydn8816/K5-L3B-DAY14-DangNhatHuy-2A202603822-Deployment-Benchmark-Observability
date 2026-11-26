# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** ⏳ BẠN ĐIỀN
**Ngày chạy:** 2026-11-26 (Mục 2–3). Mục 4–5: ⏳ BẠN ĐIỀN
**Môi trường:** Mục 2–3: Windows 10, 8 logical CPU, Python 3.14, agent và load test chạy cùng một máy (không dùng Docker). Mục 4–5: ⏳ BẠN ĐIỀN (cấu hình Docker Desktop)

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

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
