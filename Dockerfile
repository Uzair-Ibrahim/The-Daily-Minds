FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm test && npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATABASE_BACKEND=postgres \
    DATABASE_PATH=/app/data/daily_mind.sqlite3 \
    STORY_SEMANTIC_ENABLED=false \
    CREDIT_SEARCH_CONFIRMED_FREE=false
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend/ ./backend/
RUN python -m pip install . \
    && python -m playwright install --with-deps chromium \
    && groupadd --system daily-mind \
    && useradd --system --gid daily-mind --create-home daily-mind \
    && mkdir -p /app/data \
    && chown -R daily-mind:daily-mind /app/data
COPY --from=frontend /build/frontend/dist ./frontend/dist
USER daily-mind
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
