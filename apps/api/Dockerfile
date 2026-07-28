FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/apps/api

COPY apps/api/pyproject.toml ./
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY scripts/demo_seed.py /app/scripts/demo_seed.py

RUN python -m pip install --upgrade pip \
    && python -m pip install -e . \
    && groupadd --system cloudops \
    && useradd --system --gid cloudops --home-dir /app --no-create-home cloudops \
    && chown -R cloudops:cloudops /app

USER cloudops

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
