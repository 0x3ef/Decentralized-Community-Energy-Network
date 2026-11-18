.DEFAULT_GOAL := help

ROOT_DIR     := $(shell pwd)
DEV_TOOLS ?= $(ROOT_DIR)/.dev-tools
COMPOSE_FILE := $(ROOT_DIR)/infrastructure/docker/compose.prototype.yml
COMPOSE      := docker compose --env-file $(ROOT_DIR)/infrastructure/docker/.env -f $(COMPOSE_FILE)

.PHONY: help setup recover-demo repair-demo up down logs ps build migrate seed test test-contracts test-iot \
        test-backend lint format typecheck contracts-deploy clean recover backup doctor demo simulate blockchain-check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Bootstrap the local environment
	python scripts/stack.py setup

repair-demo recover-demo: recover ## Compatibility aliases: recover on the SAME database

recover: ## Recover lost local-chain contracts; retain SQL rows and archive old financial history
	python scripts/stack.py recover

backup: ## Create a private verified SQL backup without changing databases
	python scripts/stack.py backup

doctor: ## Inspect containers, disk, blockchain deployment and application readiness
	python scripts/stack.py doctor

up: ## Start the full stack
	python scripts/stack.py up

down: ## Stop the stack (keep volumes)
	python scripts/stack.py down

logs: ## Tail logs from all services
	python scripts/stack.py logs

ps: ## Show container status
	python scripts/stack.py ps

build: ## Build all Docker images
	python scripts/stack.py build

seed: ## Load ungoverned SQLModel fixtures into the running DB
	./scripts/seed_db.sh

migrate: ## Apply Alembic migrations to the running DB
	$(COMPOSE) run --rm migrate

test: test-contracts test-backend test-iot test-frontend ## Run contract, backend and IoT verification

test-contracts: ## Run Foundry tests
	$(DEV_TOOLS)/node_modules/.bin/forge test --root contracts --use $(DEV_TOOLS)/solc-0.8.24

test-iot: ## Run iot unit tests
	./scripts/test_iot.sh

test-backend: ## Run backend integration tests against isolated Docker services
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
	python scripts/stack.py up

demo-scenario: ## Verify actual MQTT, automatic settlement, SUN retirement and earnings withdrawal
	PYTHONPATH=apps/backend python scripts/demo_scenario.py

blockchain-check: ## Insert validated SQLModel test readings and verify real local ETH/SUN operations
	PYTHONPATH=apps/backend python scripts/check_blockchain.py

simulate: ## Start the registered REALTIME MQTT simulator for the governed demo
	python scripts/stack.py simulate

contracts-deploy: ## Run native Sepolia preflight; broadcasting is always explicit
	@echo "scripts/deploy.sh COMMUNITY_UUID --network sepolia [--broadcast]"

test-frontend: ## Verify strict frontend types, lint, tests and production build
	cd apps/frontend && npm run typecheck && npm run lint && npm test && npm run build

test-browser: ## Start a fresh native fixture and run all real API browser journeys
	cd apps/frontend && npm run test:e2e:all

clean: ## Remove compiler artifacts only; retain all SQL data, volumes and configuration
	python scripts/stack.py clean
