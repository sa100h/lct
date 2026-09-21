FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY test-event-feeder/requirements.txt .
RUN pip install -r requirements.txt

COPY test-event-feeder/app ./app
RUN useradd --create-home appuser \
    && mkdir -p /cache \
    && chown -R appuser:appuser /app /cache

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5m --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

