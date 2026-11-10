# syntax=docker/dockerfile:1.7
# ============================================================================
# Stage 1 — builder: generate gRPC stubs
# ============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Only the .proto is needed at this stage.
COPY protos/sensor.proto ./protos/sensor.proto

# Generate stubs and patch the absolute import to a package-relative one.
# - `sed -i` works because /bin/sh is available in python:3.12-slim.
# - The final `grep -q` makes the build FAIL if the patch did not apply,
#   so a broken image can never be produced silently.
RUN pip install --upgrade pip "grpcio-tools>=1.62,<1.63" \
 && mkdir -p ./grpc_client \
 && python -m grpc_tools.protoc \
        -I./protos \
        --python_out=./grpc_client \
        --grpc_python_out=./grpc_client \
        ./protos/sensor.proto \
 && sed -i 's|^import sensor_pb2 as sensor__pb2$|from grpc_client import sensor_pb2 as sensor__pb2|' \
        ./grpc_client/sensor_pb2_grpc.py \
 && grep -q "from grpc_client import sensor_pb2" ./grpc_client/sensor_pb2_grpc.py

# ============================================================================
# Stage 2 — base runtime (shared by simulator, gateway, tests)
# ============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy packaging metadata first so pip layer is cached when only code changes.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[dev]"

# Copy the rest of the source tree.
COPY . .

# Copy the already-generated stubs from the builder stage.
COPY --from=builder /build/grpc_client/sensor_pb2.py       ./grpc_client/sensor_pb2.py
COPY --from=builder /build/grpc_client/sensor_pb2_grpc.py  ./grpc_client/sensor_pb2_grpc.py

# ============================================================================
# Stage 3 — simulator
# ============================================================================
FROM base AS simulator
ENTRYPOINT ["python", "-m", "simulator.main"]

# ============================================================================
# Stage 4 — gateway
# ============================================================================
FROM base AS gateway
ENTRYPOINT ["python", "-m", "gateway.main"]

# ============================================================================
# Stage 5 — tests
# ============================================================================
FROM base AS tests
RUN pip install ".[dev]"
ENTRYPOINT ["pytest"]