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

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/status', timeout=3).status == 200 else 1)"

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
