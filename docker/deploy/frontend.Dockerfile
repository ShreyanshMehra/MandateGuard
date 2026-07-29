# Free-hosting variant of the frontend. The local docker-compose frontend
# (frontend/Dockerfile) runs the Vite dev server for fast iteration; this
# builds the production bundle instead and serves it with `vite preview`,
# which already respects vite.config.ts's preview.allowedHosts (needed
# since Render puts the app behind a platform-owned hostname).
FROM node:22.23.1-alpine3.24

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .

# Vite bakes VITE_* vars into the built bundle at build time, so this must
# be a build ARG, not a runtime env var.
ARG VITE_BROKER_URL
ENV VITE_BROKER_URL=${VITE_BROKER_URL}
RUN npm run build

EXPOSE 5173
CMD ["sh", "-c", "npx vite preview --host 0.0.0.0 --port ${PORT:-5173}"]
