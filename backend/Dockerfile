# syntax=docker/dockerfile:1.7

# ---- builder: export deps and build a wheel-cache layer ----
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.3.4 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install "poetry==${POETRY_VERSION}" "poetry-plugin-export>=1.8"

WORKDIR /app
COPY pyproject.toml poetry.lock ./
# Export only runtime deps (skip test/dev groups) to a pip requirements file.
RUN poetry export --without-hashes --only main -o requirements.txt \
    && pip wheel --wheel-dir /wheels -r requirements.txt


# ---- runtime: slim image with prebuilt wheels ----
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8001 \
    DJANGO_SETTINGS_MODULE=backend.settings

# libpq5 is the runtime piece psycopg2-binary needs. ffmpeg transcodes
# browser-recorded voice samples (webm/opus) to WAV before forwarding them to
# Dia for voice cloning (its soundfile reader can't open webm).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for the app.
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

COPY --from=builder /wheels /wheels
COPY --from=builder /app/requirements.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels

COPY --chown=app:app . .

# Collect static files into STATIC_ROOT so WhiteNoise can serve them.
# DJANGO_COLLECTSTATIC=0 lets CI skip this if needed.
RUN DJANGO_COLLECTSTATIC=1 SECRET_KEY=build-only DATABASE_URL=sqlite:///tmp/build.sqlite3 \
    python manage.py collectstatic --noinput || true

USER app
EXPOSE 8001

# Run migrations then start gunicorn.
#
# --worker-class gthread + multiple --threads is the right shape for our
# workload: long-lived streaming proxies that spend ~all their time in I/O
# wait. The default sync workers would kill any request that runs longer
# than --timeout (default 30s), which trivially happens with a 27B
# reasoning model streaming hundreds of tokens.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn backend.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --worker-class gthread \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-8} \
    --timeout ${GUNICORN_TIMEOUT:-600} \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - --error-logfile -"]
