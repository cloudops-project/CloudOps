FROM python:3.12.13-alpine3.24 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/apps/api

COPY apps/api/pyproject.toml ./
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY scripts/demo_seed.py /app/scripts/demo_seed.py
COPY scripts/selfhost/container_env.sh /app/scripts/selfhost-container-env.sh

RUN python -m pip install --upgrade pip \
    && python -m pip install -e . \
    && apk add --no-cache su-exec \
    && chmod 0555 /app/scripts/selfhost-container-env.sh \
    && addgroup -S -g 10001 cloudops \
    && adduser -S -u 10001 -G cloudops -h /app -H cloudops \
    && chown -R cloudops:cloudops /app

USER cloudops

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
