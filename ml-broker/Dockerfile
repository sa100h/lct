FROM python:3.11-slim AS final

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY ml-broker/requirements.txt .
RUN pip install -r requirements.txt

COPY ml-broker/app ./app
RUN useradd -m appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["python", "-m", "app.main"]
