.DEFAULT_GOAL := help

# Paths (relative to iot/)
PROTO_DIR  := protos
OUT_DIR    := grpc_client
PROTO_FILE := $(PROTO_DIR)/sensor.proto

# Path to the compose file (relative to iot/)
COMPOSE    := docker compose -f ../infrastructure/docker/docker-compose.yml

.PHONY: help install protos clean-protos \
        test test-unit test-integration test-all test-cov \
        lint format typecheck \
        build up down logs ps clean

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Install / stubs
# ---------------------------------------------------------------------------
install: ## Install package with dev dependencies (editable)
	pip install -e ".[dev]"

protos: ## Generate gRPC stubs from protos/sensor.proto
	@mkdir -p $(OUT_DIR)
	python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=$(OUT_DIR) \
		--grpc_python_out=$(OUT_DIR) \
		$(PROTO_FILE)
	@# Patch absolute import to package-relative import
	sed -i.bak 's/^import sensor_pb2 as sensor__pb2/from grpc_client import sensor_pb2 as sensor__pb2/' \
		$(OUT_DIR)/sensor_pb2_grpc.py
	@rm -f $(OUT_DIR)/sensor_pb2_grpc.py.bak
	@echo "✓ Generated $(OUT_DIR)/sensor_pb2.py and $(OUT_DIR)/sensor_pb2_grpc.py"


clean-protos: ## Remove generated gRPC stubs
	rm -f $(OUT_DIR)/sensor_pb2.py $(OUT_DIR)/sensor_pb2_grpc.py

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test: protos ## Run unit tests on the host (no network, fast)
	pytest -m "not integration"

test-unit: ## Run unit tests inside the container (no network)
	$(COMPOSE) run --rm tests -m "not integration"

test-integration: ## Run integration tests inside the container
	$(COMPOSE) run --rm tests -m "integration"

test-all: ## Run the full suite inside the container
	$(COMPOSE) run --rm tests

test-cov: ## Full suite with coverage report
	$(COMPOSE) run --rm tests --cov --cov-report=term-missing

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------
lint: ## Run ruff
	ruff check .

format: ## Format with ruff
	ruff format .
	ruff check --fix .

typecheck: protos ## Run mypy
	mypy .

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
build: ## Build all images
	$(COMPOSE) build

up: ## Start the full local stack
	$(COMPOSE) up --build -d

down: ## Stop the stack (keep volumes)
	$(COMPOSE) down

clean: ## Stop the stack and delete volumes
	$(COMPOSE) down -v

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

