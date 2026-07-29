# Free-hosting variant of the broker service. Unlike docker/backend.Dockerfile
# (used by local docker-compose, where a separate one-shot `migrate` service
# runs first), this image also carries database/migrations and the seed
# policy config so it can run its own migration on startup -- Render's free
# plan has no equivalent to Compose's `depends_on: service_completed_successfully`
# one-off job. See start-broker.sh.
FROM python:3.12.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY services/broker/app ./app
COPY database ./database
COPY policies/policy_config.json ./policies/policy_config.json
COPY docker/deploy/start-broker.sh ./start-broker.sh
RUN chmod +x ./start-broker.sh

EXPOSE 8000
CMD ["./start-broker.sh"]
