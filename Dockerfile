# Q-Canvas for a public host (Hugging Face Spaces, Docker SDK, port 7860).
# Public mode: code written by a model is never executed (the agent runs Q-Canvas's own template code), and billed
# model calls stop at QCANVAS_DAILY_CALLS per UTC day, after which the labelled offline models answer.

FROM node:24-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    QCANVAS_PUBLIC=1 \
    QCANVAS_MODEL_PROVIDER=meta \
    QCANVAS_DAILY_CALLS=300 \
    QCANVAS_CACHE_DIR=/app/backend/seed_cache
RUN useradd -m -u 1000 app
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY --chown=app backend/ backend/
COPY --chown=app examples/ examples/
COPY --chown=app --from=web /app/frontend/dist frontend/dist
USER app
EXPOSE 7860
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "qcanvas.api.app:app", "--host", "0.0.0.0", "--port", "7860"]
