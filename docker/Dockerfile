# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /w
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements/ requirements/
RUN pip wheel --no-cache-dir -r requirements/production.txt -w /wheels

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.production
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 libjpeg62-turbo libwebp7 && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 10001 -m app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY --chown=app:app . .
RUN SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/x.db python manage.py collectstatic --noinput
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8000/healthz/')" || exit 1
CMD ["gunicorn", "config.wsgi:application", "-b", "0.0.0.0:8000", "-w", "3", "-k", "gthread", "--threads", "4", "--timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "100"]
