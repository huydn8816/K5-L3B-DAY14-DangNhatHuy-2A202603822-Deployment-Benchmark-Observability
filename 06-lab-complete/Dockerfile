# ============================================================
# TODO (tiêu chí 1): viết lại thành Dockerfile production
#   • Multi-stage build: stage builder cài dependencies, stage runtime chỉ copy kết quả
#   • Base image slim (vd python:3.11-slim) và chạy bằng user non-root
#   • Có HEALTHCHECK gọi GET /health
#   • Image cuối < 500 MB
#   • CMD lắng nghe theo biến PORT (mặc định 8000) và uvicorn phải là PID 1
#     (exec form, hoặc `sh -c "exec uvicorn ..."`) để nhận SIGTERM khi `docker stop`
#
# Bản dưới đây build và chạy được nhưng CHƯA đạt yêu cầu nào ở trên.
# ============================================================

# ── Stage 1: builder ──
FROM python:3.11-slim AS builder                 
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt    

# ── Stage 2: runtime ──
FROM python:3.11-slim AS runtime                 
RUN groupadd -r appuser && useradd -r -g appuser -m appuser 
WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local       
COPY app/ ./app/
COPY utils/ ./utils/
RUN chown -R appuser:appuser /app /home/appuser/.local     
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUSERBASE=/home/appuser/.local \
    PYTHONUNBUFFERED=1 \
    PORT=8000                                             
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.getenv('PORT','8000'))"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
