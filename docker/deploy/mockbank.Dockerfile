# Free-hosting variant of the mock-bank service. Same app as
# docker/backend.Dockerfile (SERVICE_DIR=services/mock-bank), just listening
# on Render's assigned $PORT instead of the fixed 8000 local Compose uses.
# No migration step here -- the broker's own startup (docker/deploy/broker.Dockerfile)
# runs the one shared Alembic history that creates both the broker and bank schemas.
FROM python:3.12.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY services/mock-bank/app ./app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
