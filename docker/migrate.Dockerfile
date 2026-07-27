# One-shot schema migration/seed runner. Uses the admin Postgres role because
# it must create objects in both the broker and bank schemas; application
# services only ever connect with their scoped role (see database/init).
FROM python:3.12.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Mirrors the repository layout (database/migrations/... and policies/...)
# so the seed migration's relative path to policy_config.json resolves the
# same way here as it does when run locally from a repo checkout.
COPY database ./database
COPY policies/policy_config.json ./policies/policy_config.json

WORKDIR /app/database/migrations

CMD ["alembic", "upgrade", "head"]
