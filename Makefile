.DEFAULT_GOAL := help

ROOT_DIR     := $(shell pwd)
COMPOSE_FILE := $(ROOT_DIR)/infrastructure/docker/docker-compose.yml
COMPOSE      := docker compose -f $(COMPOSE_FILE)

.PHONY: help setup up down logs ps build migrate seed test test-contracts test-iot \
        test-backend lint format typecheck contracts-deploy clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Bootstrap the local environment
	./scripts/setup.sh

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

seed: ## Load SQL seeds into the running DB
	./scripts/seed_db.sh

migrate: ## Apply Alembic migrations to the running DB
	$(COMPOSE) run --rm migrator

test: ## Run every test suite (unit only)
	./scripts/test.sh

test-contracts: ## Run Foundry tests
	cd contracts && forge test -vvv

test-iot: ## Run iot unit tests
	cd iot && make test

test-backend: ## Run backend unit tests in Docker
	$(COMPOSE) run --rm tests -m "not integration"

lint: ## Run ruff on backend and iot
	cd apps/backend && ruff check .
	cd iot && ruff check .

format: ## Run ruff format on backend and iot
	cd apps/backend && ruff format .
	cd iot && ruff format .

typecheck: ## Run mypy on backend and iot
	cd apps/backend && mypy .
	cd iot && mypy .

contracts-deploy: ## Deploy contracts to the running Anvil
	./scripts/deploy.sh contracts

clean: ## Stop the stack and delete volumes + build artifacts
	$(COMPOSE) down -v
	rm -rf contracts/out contracts/cache contracts/broadcast
	find . -type d -name __pycache__ -prune -exec rm -rf {} +