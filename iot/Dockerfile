# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Dependencies are pinned and cached separately from code/tests. Runtime images
# do not include compilers, test runners or type-checking packages.
COPY requirements.lock ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.lock
# Checked-in protobuf stubs are used as-is; builds never regenerate them.
COPY config ./config
COPY generators ./generators
COPY grpc_client ./grpc_client
COPY models ./models
COPY publishers ./publishers
COPY schemas ./schemas
COPY simulator ./simulator
COPY gateway ./gateway
COPY pyproject.toml ./
FROM base AS simulator
ENTRYPOINT ["python", "-m", "simulator.main"]
FROM base AS gateway
EXPOSE 50051
ENTRYPOINT ["python", "-m", "gateway.main"]
FROM base AS tests
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir '.[dev]'
COPY tests ./tests
ENTRYPOINT ["python", "-m", "pytest"]
