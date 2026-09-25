FROM python:3.11-slim AS final

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY ml-service/requirements.txt .
RUN pip install -r requirements.txt

COPY ml-service/app ./app
COPY ml-service/scripts ./scripts
RUN useradd -m appuser \
    && mkdir -p /app/models /app/data \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000

# Liveness probe: /healthz is a static route (no model-registry dependency),
# so the container is "up" the moment uvicorn accepts connections. /status
# reports readiness/model state and can 500 while models are absent — do not
# tie restarts to it. fastapi is a pinned dependency, so the probe does not
# need the app's heavier import graph (app.main).
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
