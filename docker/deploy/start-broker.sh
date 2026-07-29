#!/bin/sh
# Free-hosting entrypoint for the broker: Render's free plan doesn't support
# a separate one-off "migrate" job the way the local docker-compose stack's
# migrate service does, so migrations run here, once, before the app starts.
# `alembic upgrade head` is idempotent -- safe to run on every boot/redeploy.
set -eu

cd /app/database/migrations
alembic upgrade head
cd /app

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
