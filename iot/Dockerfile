# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Checked-in protobuf stubs are exercised by contract tests; build never rewrites them.
COPY . .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir '.[dev]'
FROM base AS simulator
ENTRYPOINT ["python", "-m", "simulator.main"]
FROM base AS gateway
EXPOSE 50051
ENTRYPOINT ["python", "-m", "gateway.main"]
FROM base AS tests
ENTRYPOINT ["python", "-m", "pytest"]
