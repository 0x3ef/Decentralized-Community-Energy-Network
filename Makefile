.DEFAULT_GOAL := help

ROOT_DIR     := $(shell pwd)
DEV_TOOLS ?= $(ROOT_DIR)/.dev-tools
COMPOSE_FILE := $(ROOT_DIR)/infrastructure/docker/compose.prototype.yml
COMPOSE      := docker compose --env-file $(ROOT_DIR)/infrastructure/docker/.env -f $(COMPOSE_FILE)

.PHONY: help setup recover-demo up down logs ps build migrate seed test test-contracts test-iot \
        test-backend lint format typecheck contracts-deploy clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Bootstrap the local environment
	./scripts/setup.sh

recover-demo: ## Archive a broken local demo and commission an isolated replacement
	python scripts/recover_local_demo.py --new-demo

up: ## Start the full stack
	$(COMPOSE) up -d

down: ## Stop the stack (keep volumes)
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

build: ## Build all Docker images
	$(COMPOSE) build

seed: ## Load ungoverned SQLModel fixtures into the running DB
	./scripts/seed_db.sh

migrate: ## Apply Alembic migrations to the running DB
	$(COMPOSE) run --rm migrate

test: test-contracts test-backend test-iot test-frontend ## Run contract, backend and IoT verification

test-contracts: ## Run Foundry tests
	$(DEV_TOOLS)/node_modules/.bin/forge test --root contracts --use $(DEV_TOOLS)/solc-0.8.24

test-iot: ## Run iot unit tests
	./scripts/test_iot.sh

test-backend: ## Run backend unit tests in Docker
	./scripts/test_backend.sh

lint: ## Run ruff on backend and iot
	cd apps/backend && ruff check .
	cd iot && ruff check .

format: ## Run ruff format on backend and iot
	cd apps/backend && ruff format .
	cd iot && ruff format .

typecheck: ## Run mypy on backend and iot
	cd apps/backend && mypy .
	cd iot && mypy .

contracts-build: ## Compile reviewed contract artifacts
	$(DEV_TOOLS)/node_modules/.bin/forge build --root contracts --use $(DEV_TOOLS)/solc-0.8.24

demo: ## Commission deterministic governed local users, nodes and meters
	python scripts/init_local_env.py
	python scripts/bootstrap_demo.py

demo-scenario: ## Verify actual MQTT, automatic settlement, SUN retirement and earnings withdrawal
	PYTHONPATH=apps/backend python scripts/demo_scenario.py

simulate: ## Start the registered REALTIME MQTT simulator for the governed demo
	$(COMPOSE) --env-file $(ROOT_DIR)/.run/demo/compose.env -f infrastructure/docker/compose.iot.yml --profile simulation up -d --build simulator

contracts-deploy: ## Run native Sepolia preflight; broadcasting is always explicit
	@echo "scripts/deploy.sh COMMUNITY_UUID --network sepolia [--broadcast]"

test-frontend: ## Verify strict frontend types, lint, tests and production build
	cd apps/frontend && npm run typecheck && npm run lint && npm test && npm run build

test-browser: ## Start a fresh native fixture and run all real API browser journeys
	cd apps/frontend && npm run test:e2e:all

clean: ## Stop the stack and delete volumes + build artifacts
	$(COMPOSE) down -v
	rm -rf contracts/out contracts/cache contracts/broadcast
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
