# Free-hosting variant of the opa service: the local docker-compose setup
# mounts ./policies as a bind volume, which Render's Docker-image-based
# services can't do, so this bakes the policy bundle into the image instead.
# Functionally identical policy content -- see docker-compose.yml's opa
# service for the local equivalent.
FROM openpolicyagent/opa:1.17.0-static

COPY policies /policies

# The opa:*-static image is scratch-based (no shell), so $PORT can't be
# expanded at runtime here -- render.yaml pins this service's PORT env var
# to 8181 to match, and the base image's own ENTRYPOINT (the /opa binary)
# is left as-is; this just supplies its arguments.
CMD ["run", "--server", "--addr=:8181", "--log-level=info", "/policies"]
